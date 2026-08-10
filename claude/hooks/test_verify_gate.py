#!/usr/bin/env python3
"""Battery for verify_gate.decide().

Varies structure and wording across cases so the gate is tested on the RULE, not
on a memorized string. Half the cases are false-positive probes: a Stop gate that
fires on ordinary conversation is worse than no gate, so "must NOT block" carries
as much weight here as "must block".
"""

import sys

sys.path.insert(0, __import__("os").path.dirname(__file__))
from verify_gate import decide  # noqa: E402


def user(text="do the thing"):
    return {"type": "user", "promptSource": "cli", "message": {"content": text}}


def tool_result(**meta):
    """A tool result, which the transcript also records as type 'user'.

    Real transcripts put `promptId` (and sometimes other provenance keys) on
    these rows, so the tests vary that metadata: a tool result must never count
    as a user turn no matter what fields ride along with it.
    """
    row = {
        "type": "user",
        "message": {"content": [{"type": "tool_result", "content": "ok"}]},
    }
    row.update(meta)
    return row


def act(*blocks):
    return {"type": "assistant", "message": {"content": list(blocks)}}


def use(name):
    return {"type": "tool_use", "name": name}


def say(text):
    return {"type": "text", "text": text}


CASES = [
    # ---- must BLOCK -------------------------------------------------------
    (
        "edit + claim, nothing run",
        [user(), act(use("Edit")), tool_result(), act(say("All tests pass now."))],
        True,
    ),
    (
        "write + claim, different wording",
        [user(), act(use("Write")), act(say("The parser is working."))],
        True,
    ),
    (
        "verified BEFORE the edit (ordering trap)",
        [
            user(),
            act(use("Bash")),
            tool_result(),
            act(use("Edit")),
            act(say("Everything is done.")),
        ],
        True,
    ),
    (
        "multi-edit, run in the middle, edit after",
        [
            user(),
            act(use("Edit")),
            act(use("Bash")),
            act(use("MultiEdit")),
            act(say("ready to ship")),
        ],
        True,
    ),
    (
        "notebook edit + claim",
        [user(), act(use("NotebookEdit")), act(say("it's complete"))],
        True,
    ),
    # ---- must NOT block ---------------------------------------------------
    (
        "pure conversation, no tools",
        [user("wtf is a hook?"), act(say("A hook is a command. It is working well."))],
        False,
    ),
    (
        "edit THEN verify, correct order",
        [
            user(),
            act(use("Edit")),
            tool_result(),
            act(use("Bash")),
            tool_result(),
            act(say("All tests pass.")),
        ],
        False,
    ),
    (
        "edit with an explicitly unverified claim",
        [user(), act(use("Edit")), act(say("First pass written, untested so far."))],
        False,
    ),
    (
        "read-only investigation with a claim",
        [user(), act(use("Read")), act(use("Grep")), act(say("The bug is fixed."))],
        False,
    ),
    (
        "prior turn had a violation, current turn is clean",
        [
            user(),
            act(use("Edit")),
            act(say("all tests pass")),
            user("now explain it"),
            act(say("Here is why it is working.")),
        ],
        False,
    ),
    (
        "empty transcript",
        [],
        False,
    ),
    # Real transcripts stamp provenance keys on tool results. If those are read
    # as user turns the window collapses to the last tool call and the gate goes
    # permanently silent -- a false NEGATIVE, the dangerous direction.
    (
        "tool results carrying promptId do not split the turn",
        [
            user(),
            act(use("Edit")),
            tool_result(promptId="abc-123"),
            act(use("Read")),
            tool_result(promptId="def-456", promptSource="cli"),
            act(say("everything is working")),
        ],
        True,
    ),
    (
        "tool results with provenance, correctly verified after edit",
        [
            user(),
            act(use("Write")),
            tool_result(promptId="ghi-789"),
            act(use("Bash")),
            tool_result(promptId="jkl-012"),
            act(say("all checks pass")),
        ],
        False,
    ),
    # Refusals to claim must not read as claims. Phrasings vary so this tests the
    # negation/quotation rule rather than one observed sentence.
    (
        "refuses the claim, quoting the phrase",
        [
            user(),
            act(use("Write")),
            act(say('Created it. Nothing was run, so I can\'t say "all tests pass".')),
        ],
        False,
    ),
    (
        "refuses the claim without quotes",
        [user(), act(use("Edit")), act(say("The tests do not pass yet."))],
        False,
    ),
    (
        "hedged: explicitly untested",
        [user(), act(use("Write")), act(say("Written but unverified - it is not working yet."))],
        False,
    ),
    # Contractions must not be read as quote delimiters -- an apostrophe pair
    # spanning the negator would blank it and re-expose the claim.
    (
        "contraction-heavy refusal",
        [
            user(),
            act(use("Write")),
            act(say("I won't be able to say tests pass; I didn't run anything.")),
        ],
        False,
    ),
    (
        "asserted claim still blocks after the negation fix",
        [user(), act(use("Edit")), act(say("Patched the parser. All tests pass."))],
        True,
    ),
    (
        "PowerShell counts as verification",
        [user(), act(use("Write")), act(use("PowerShell")), act(say("it is done"))],
        False,
    ),
]


def main() -> int:
    failures = 0
    for name, rows, should_block in CASES:
        reason = decide(rows)
        blocked = reason is not None
        ok = blocked == should_block
        if not ok:
            failures += 1
        print(
            f"{'PASS' if ok else 'FAIL'}  "
            f"{'BLOCK ' if should_block else 'ALLOW '}  {name}"
            + ("" if ok else f"   <-- got {'BLOCK' if blocked else 'ALLOW'}")
        )
    print(f"\n{len(CASES) - failures}/{len(CASES)} passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
