#!/usr/bin/env python3
"""PreToolUse hook: block source edits until an approved spec authorizes them.

Thesis
------
CLAUDE.md Law 7 says "spec-first is mandatory" and AGENTS.md adds a hard gate
listing what must block. Both are delivered as a user message after the system
prompt, so they are advice the model can talk past -- and does, exactly when the
session is long and busy. As a PreToolUse hook returning `permissionDecision:
deny`, the same rule is a wall that holds regardless of what the model decides.

This is the Law 7 counterpart to `verify_gate.py`'s Law 6 wall, and follows its
shape deliberately: a pure `decide()` over an explicit payload, fail-open on
confusion, and a battery of synthetic cases rather than live-session testing.

The rule
--------
Deny a file-mutating tool call when ALL of these hold:

  1. The repo is armed          (a `.spec/` directory exists above cwd)
  2. The gate is not bypassed   (no `.spec/BYPASS`, no SPEC_GATE=off)
  3. The target is not exempt   (not `.spec/`, `.claude/`, `.git/`, markdown)
  4. The governing spec has not reached the `implement` phase
     -- or the path falls outside that spec's declared `scope`

Deliberately NOT blocked
------------------------
- Any repo without a `.spec/` tree. Scratch work, foreign repos, and one-line
  fixes are untouched. This is what the CLAUDE.md foreign-repo guard requires.
- The spec artifacts themselves, or the gate would deadlock: you could not write
  the document that unlocks the repo.
- Markdown anywhere. Docs and notes are not the thing Law 7 is protecting.
- Anything at all when the payload cannot be parsed (fail open).

Why `deny` and not `exit 2`
---------------------------
Both block. Only `deny` puts the reason in front of the model as a permission
decision, which makes the block self-correcting -- the next action is to write
the missing spec rather than to retry the same edit. `exit 2` routes through
stderr as a generic error, which reads as a malfunction rather than a rule.

Contract
--------
Require   - stdin carries a PreToolUse payload with `tool_input` and `cwd`.
Guarantee - prints a deny decision and exits 0 when the rule fires; exits 0
            silently otherwise. Never exits non-zero.
Maintain  - fails OPEN on every unexpected condition, per verify_gate.py: a
            gate that blocks when confused makes the session unrecoverable,
            which is a worse failure than a missed check.
Assert    - never blocks a path `spec_paths.is_exempt` marks exempt, so the
            unlock path is always reachable from inside a blocked state.
"""

from __future__ import annotations

import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from spec_paths import (  # noqa: E402
    FIRST_ARTIFACT,
    PHASES,
    approved_through,
    find_spec_root,
    in_scope,
    is_bypassed,
    is_exempt,
    load_state,
    resolve_active,
)

MUTATING = {"Edit", "Write", "NotebookEdit", "MultiEdit"}

# Shells reach the filesystem without a `file_path`, so `target_path` cannot see
# them and `is_exempt` never runs. Both are gated: on Windows the PowerShell
# tool is the primary shell, and gating only Bash would leave the hole open by
# the more convenient route.
SHELL_TOOLS = {"Bash", "PowerShell"}

# The two files that are the gate's own authority. Rationale in
# `spec_paths.is_exempt`: writable approvals mean the model approves its own
# phases, and a writable store means `render` faithfully reproduces a forgery.
GUARDED = ("state.json", "spec.db")

# The sanctioned mutation route. These run as shell commands themselves, so a
# blanket deny on any command naming a guarded file would block the very tool
# that performs legitimate writes -- and the unlock path with it.
#
# Split by shape, because they are recognised differently: a script is matched
# on the tail of a token (`python C:/.../hooks/spec_store.py`), whereas
# `/spec-` is a front-end command and must lead its segment. See
# `_is_sanctioned` -- membership anywhere in the string is not enough.
SANCTIONED_SCRIPTS = ("spec_store.py", "spec_cli.py")

_G = r"(?:state\.json|spec\.db)"
_SEG = r"[^;|&\n]*"

# Redirection *into* a guarded file. Anchored on the target so that a read
# piped elsewhere (`cat state.json > notes.txt`) is not caught.
_REDIRECT = re.compile(r">>?\s*['\"]?" + _SEG.replace("*", "*?") + _G, re.I)

# A sqlite3 invocation naming a guarded file, carrying a mutating statement.
_SQLITE = re.compile(r"sqlite3" + _SEG + _G + _SEG, re.I)
_SQL_WRITE = re.compile(
    r"\b(insert|update|delete|drop|alter|replace|vacuum|attach)\b", re.I
)

# File operations that clobber, move, or truncate a guarded file.
_FILEOP = re.compile(
    r"\b(rm|del|erase|mv|move|cp|copy|touch|truncate|tee|dd|"
    r"set-content|add-content|clear-content|out-file|remove-item|new-item)\b"
    + _SEG + _G,
    re.I,
)

# Inline interpreter writes: `python -c "open('.spec/state.json','w')"`.
_INLINE_WRITE = re.compile(r"open\(" + _SEG + _G + _SEG + r"['\"][wa]", re.I)

# Command separators. The rules above are written against a single segment
# (`_SEG` already excludes these), so the command is split before matching.
_SEP = re.compile(r"\|\||&&|[;|&\n]")

# The phase machine itself. `python spec_state.py approve requirements` names
# no guarded file, so the GUARDED fast-path never sees it -- yet it forges
# precisely the approval the guarded-file rules exist to protect.
#
# This deny is unconditional, and that is the point rather than an oversight.
# A legitimate approval is a human act that never reaches the model's tool
# surface at all: pi's `registerCommand` handler spawns the phase machine
# directly and emits no `tool_call`, so it is never judged here. Anything that
# does arrive here came through a tool, and a tool call is by construction
# something the model could have written. Intent cannot be recovered from
# command text -- an env marker or a magic argument is as forgeable as the
# approval it would authorise -- so the verb is simply not available by shell.
_STATE_CLI = re.compile(r"\bspec_state\.py\b", re.I)
_STATE_MUTATE = re.compile(r"\b(approve|advance|set[-_]?phase)\b", re.I)


def _is_sanctioned(segment: str) -> bool:
    """True when this segment's *invoked program* is a sanctioned route.

    Substring containment is not enough, and was the bug this replaces:
    `echo "/spec-" > .spec/state.json` contains a sanctioned marker while
    invoking `echo`, and so was allowed to clobber the store. Only the program
    actually being run -- or a script path handed to an interpreter -- may
    sanction a segment, and only up to the first redirection, after which the
    tokens are targets rather than the command.
    """
    for i, tok in enumerate(segment.strip().lower().split()):
        if ">" in tok or "<" in tok:
            return False
        # A front-end command sanctions only as the program being run. As an
        # argument it is just text: `grep /spec- > spec.db` invokes grep.
        if i == 0 and tok.startswith("/spec-"):
            return True
        # A script may follow an interpreter and its flags, so it is accepted
        # at any position ahead of a redirection: `py -3 .../spec_store.py`.
        if tok.endswith(SANCTIONED_SCRIPTS):
            return True
    return False


def shell_write_reason(command: str) -> str | None:
    """Deny reason for a shell command that mutates the gate's own authority.

    Judged on the command string alone: there is no phase or scope question
    here, because forging an approval is wrong in `implement` too.

    Heuristic, and deliberately narrow. It matches redirection into a guarded
    file, mutating sqlite3 statements, clobbering file operations, and inline
    interpreter writes. It will not catch a write hidden behind a variable, a
    heredoc, or a base64 round-trip. That is an accepted limit: this closes the
    convenient route, not every conceivable one, and the honest claim is
    "raises the cost of forgery", not "makes it impossible".
    """
    if not command:
        return None

    for segment in _SEP.split(command):
        if _STATE_CLI.search(segment) and _STATE_MUTATE.search(segment):
            return (
                "SPEC GATE: this command drives the phase machine's approval "
                "verb from a shell. Approval is a human act, and the human "
                "route never passes through a tool -- the front-end command "
                "spawns the phase machine directly. A tool call reaching this "
                "verb is therefore not the operator, whatever it asserts, so "
                "it is refused rather than argued with. To approve, run the "
                "/spec-approve command. For a genuine manual repair, that is "
                "what .spec/BYPASS and SPEC_GATE=off are for."
            )

    if not any(g in command.lower() for g in GUARDED):
        return None

    hit = None
    for segment in _SEP.split(command):
        if _is_sanctioned(segment):
            continue
        hit = (
            _REDIRECT.search(segment)
            or _FILEOP.search(segment)
            or _INLINE_WRITE.search(segment)
            or (_SQLITE.search(segment) and _SQL_WRITE.search(segment))
        )
        if hit:
            break
    if not hit:
        return None

    return (
        "SPEC GATE: this command writes to the spec gate's own record "
        "(state.json / spec.db) through a shell, which bypasses the approval "
        "flow -- a wall the model can edit is decorative. Approvals must route "
        "through the /spec-approve commands and the store, so that history is "
        "recorded rather than asserted. If the operator genuinely intends a "
        "manual repair, that is what .spec/BYPASS and SPEC_GATE=off are for."
    )


def target_path(tool_input: dict) -> str:
    """The file a mutating tool is about to touch.

    Edit/Write/NotebookEdit all use `file_path`; `notebook_path` is accepted as
    a fallback so a schema change in one tool cannot silently disarm the gate by
    making every call look pathless.
    """
    for key in ("file_path", "notebook_path", "path"):
        value = tool_input.get(key)
        if isinstance(value, str) and value:
            return value
    return ""


def phase_reason(feature: str, state: dict) -> str:
    """Explain which approval is missing and name the command that grants it.

    A deny that only says "no" costs a round trip. Naming the next command makes
    the block actionable on the first read.
    """
    kind = state.get("kind", "feature")
    phase = state.get("phase", "requirements")
    done = approved_through(state)
    artifact = FIRST_ARTIFACT.get(kind, "requirements.md")

    if phase == "requirements":
        pending = f"{artifact} needs drafting and approval"
        nxt = "/spec-approve requirements"
    elif phase == "design":
        pending = "design.md is drafted but unapproved"
        nxt = "/spec-approve design"
    elif phase == "tasks":
        pending = "tasks.md is drafted but unapproved"
        nxt = "/spec-approve tasks"
    else:
        pending = f"the spec is in an unrecognized phase '{phase}'"
        nxt = "/spec-status"

    approved = ", ".join(done) if done else "nothing yet"
    return (
        f"SPEC GATE: spec '{feature}' is in phase '{phase}', not 'implement'. "
        f"{pending}. Approved so far: {approved}. "
        f"Law 7 is spec-first: draft and approve the phase before editing source. "
        f"Next step is for the operator to run {nxt} "
        f"(or /spec-next to draft the next artifact)."
    )


def decide(payload: dict) -> str | None:
    """Return a deny reason, or None to let the tool call proceed.

    Pure over the payload so it can be exercised against synthetic trees in
    `test_spec_gate.py` rather than against live sessions.
    """
    tool = payload.get("tool_name")
    if tool not in MUTATING and tool not in SHELL_TOOLS:
        return None

    tool_input = payload.get("tool_input") or {}
    if not isinstance(tool_input, dict):
        return None

    cwd = payload.get("cwd") or os.getcwd()

    spec_root = find_spec_root(cwd)
    if not spec_root:
        return None                       # repo not armed; nothing to enforce

    if is_bypassed(spec_root):
        return None                       # operator disarmed it on purpose

    if tool in SHELL_TOOLS:
        # Shells are judged on the command string, not on phase or scope: the
        # guarded files are the gate's authority in every phase. Everything
        # else a shell does is none of this gate's business.
        return shell_write_reason(str(tool_input.get("command") or ""))

    path = target_path(tool_input)
    if is_exempt(path):
        return None                       # spec artifacts, docs, config

    feature, error = resolve_active(spec_root)
    if not feature:
        return (
            f"SPEC GATE: this repo is spec-driven ({spec_root}) but no spec governs "
            f"this edit -- {error}. Law 7 is spec-first. The operator should run "
            f"/spec-new <name> to open one, or /spec-status to see what exists."
        )

    state = load_state(spec_root, feature)
    if state is None:
        return None                       # unparseable state -> fail open, not shut

    phase = state.get("phase")
    if phase not in PHASES:
        # Valid JSON, meaningless phase. Denying here would deadlock the repo:
        # state.json is itself unwritable by Edit/Write, so there would be no
        # in-tool route back. Confusion fails open; /spec-status reports it.
        return None

    if phase != "implement":
        return phase_reason(feature, state)

    if not in_scope(path, state):
        declared = ", ".join(state.get("scope") or [])
        return (
            f"SPEC GATE: '{path}' is outside the declared scope of spec "
            f"'{feature}' ({declared}). An approved spec authorizes the files it "
            f"named, not the whole repo. The operator should widen `scope` in "
            f"state.json or open a separate spec for this file."
        )

    return None


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0                          # fail open

    try:
        reason = decide(payload)
    except Exception:
        return 0                          # a confused gate must not trap the session

    if reason:
        print(json.dumps({
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": reason,
            }
        }))
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    try:
        sys.exit(main())
    except Exception:
        sys.exit(0)
