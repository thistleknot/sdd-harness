#!/usr/bin/env python3
"""Stop hook: block a turn that claims completion after editing files without
running anything to verify it.

Thesis
------
Law 6 says "it does not count until it runs." As prose, that is advice the model
can talk past. As a Stop hook returning exit 2, it is a wall. This enforces the
narrowest defensible reading of the law, because a Stop gate that fires on
ordinary conversation is worse than no gate at all.

The rule
--------
Block only when ALL THREE hold for the current turn (since the last real user
prompt):

  1. A file-mutating tool ran   (Edit / Write / NotebookEdit)
  2. The closing text claims completion  ("done", "fixed", "working", ...)
  3. No verification command ran AFTER the last mutation
     (Bash / PowerShell / a test-running tool)

Ordering in (3) is load-bearing. Running the suite and *then* editing proves
nothing about the edit -- that is the exact failure mode the law targets.

Deliberately NOT blocked
------------------------
- Conversational turns, explanations, plans (no mutation -> condition 1 fails)
- Edits that make no completion claim ("here is a first pass, untested")
- Turns the user explicitly ended
- Anything where the transcript cannot be parsed (fail open)

Contract
--------
Require   - stdin carries the Stop payload with `transcript_path`.
Guarantee - exit 2 + a reason on stderr when all three conditions hold; exit 0
            otherwise. Never emits JSON (exit 2 ignores it anyway).
Maintain  - fails OPEN on every unexpected condition. A gate that blocks when it
            is confused would make the session unrecoverable, which is a worse
            failure than a missed check.
Assert    - honors `stop_hook_active` so a blocked turn can always terminate on
            its second pass. Without that guard this loops forever.
"""

from __future__ import annotations

import json
import os
import re
import sys

MUTATING = {"Edit", "Write", "NotebookEdit", "MultiEdit"}
VERIFYING = {"Bash", "PowerShell", "BashOutput"}

# Deliberately narrow. These are claims that the work is finished and correct,
# not mere narration of an action ("I updated the file" is not a claim of
# correctness; "the tests pass" is).
# Text inside quotes is being MENTIONED, not asserted. Measured false positive:
# `so I can't say "all tests pass"` -- a refusal to claim -- matched the claim
# pattern and blocked a turn that had done nothing wrong.
#
# Apostrophe is deliberately NOT a delimiter. Treating it as one made "won't be
# able to say tests pass ... can't" parse as a quoted span, which blanked the
# negator and re-exposed the claim -- turning the negation fix into a no-op.
# Contractions are far more common here than single-quoted mentions.
QUOTED = re.compile(r"""(["`])(?:\\.|(?!\1).)*\1""", re.DOTALL)

# A negator shortly before the phrase inverts it. The window is characters, not
# tokens, because the intervening words vary too much to enumerate.
NEGATOR = re.compile(
    r"\b(?:can'?t|cannot|won'?t|will not|don'?t|do not|didn'?t|did not|"
    r"not|no|never|unable to|without|before|until|unverified|untested)\b",
    re.IGNORECASE,
)
NEGATION_WINDOW = 45

CLAIM = re.compile(
    r"\b("
    r"all (?:tests?|checks?|gates?) pass\w*"
    r"|tests? (?:now )?pass\w*"
    r"|(?:is|are|it'?s|now) (?:fully )?(?:working|fixed|done|complete)"
    r"|verified (?:and )?(?:working|passing|complete)"
    r"|everything (?:is )?(?:working|done|passes)"
    r"|ready to (?:use|ship|merge)"
    r"|shipped and verified"
    r")\b",
    re.IGNORECASE,
)


def claims_completion(text: str) -> bool:
    """True only for an ASSERTED completion claim.

    Two things defeat a naive phrase match, both observed on real output:
      - quotation: `I can't say "all tests pass"` mentions the phrase
      - negation:  "the tests do not pass yet"
    Quoted spans are blanked (length-preserving, so offsets stay valid for the
    negation window), then any match with a negator just before it is discarded.
    """
    scrubbed = QUOTED.sub(lambda m: " " * len(m.group(0)), text)
    for match in CLAIM.finditer(scrubbed):
        window = scrubbed[max(0, match.start() - NEGATION_WINDOW): match.start()]
        if not NEGATOR.search(window):
            return True
    return False


def is_real_user_turn(row: dict) -> bool:
    """True for an actual human prompt, false for a tool_result echo.

    Content SHAPE is the only reliable discriminator. Tool results are recorded
    with type 'user' and DO carry `promptId` (measured: 113 of 122 'user' rows in
    a real transcript were tool results, all with promptId set), so provenance
    keys cannot be trusted. Treating them as prompts shrinks the turn window to
    the last tool call and makes the gate silently never fire.
    """
    if row.get("type") != "user":
        return False
    content = row.get("message", {}).get("content")
    if isinstance(content, str):
        return True
    if isinstance(content, list):
        return not any(
            isinstance(b, dict) and b.get("type") == "tool_result" for b in content
        )
    return False


def decide(rows: list[dict]) -> str | None:
    """Return a block reason, or None to allow the turn to end.

    Pure function over parsed transcript rows so it can be unit-tested against
    synthetic transcripts rather than live sessions.
    """
    # Scope to the current turn: everything after the last real user prompt.
    start = 0
    for i, row in enumerate(rows):
        if is_real_user_turn(row):
            start = i + 1
    turn = rows[start:]
    if not turn:
        return None

    last_mutation = -1
    last_verification = -1
    closing_text: list[str] = []

    for i, row in enumerate(turn):
        if row.get("type") != "assistant":
            continue
        for block in row.get("message", {}).get("content", []):
            if not isinstance(block, dict):
                continue
            if block.get("type") == "tool_use":
                name = block.get("name", "")
                if name in MUTATING:
                    last_mutation = i
                elif name in VERIFYING:
                    last_verification = i
            elif block.get("type") == "text":
                closing_text.append(block.get("text", ""))

    if last_mutation < 0:
        return None                       # nothing was changed; nothing to verify

    text = "\n".join(closing_text[-3:])   # the wrap-up, not the whole turn
    if not claims_completion(text):
        return None                       # no completion claim was asserted

    if last_verification > last_mutation:
        return None                       # verified after the last change

    if last_verification < 0:
        detail = "nothing was run this turn"
    else:
        detail = "the last command ran BEFORE the last edit, so it did not test it"

    return (
        f"VERIFY GATE: this turn edited files and claims completion, but {detail}. "
        "Law 6: it does not count until it runs. Run the relevant test, build, or "
        "script now and report the real output -- or restate the claim as unverified."
    )


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0                          # fail open

    # Second pass of an already-blocked turn: always allow, or this never ends.
    if payload.get("stop_hook_active"):
        return 0

    path = payload.get("transcript_path")
    if not path or not os.path.isfile(path):
        return 0

    rows = []
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except OSError:
        return 0

    reason = decide(rows)
    if reason:
        sys.stderr.write(reason + "\n")
        return 2                          # only exit 2 blocks
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        sys.exit(0)                       # a confused gate must not trap the session
