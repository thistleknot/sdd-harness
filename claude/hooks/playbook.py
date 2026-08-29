#!/usr/bin/env python3
"""Playbook pivot: turn an approved plan into a ledger worked one TODO per subagent.

NO GOVERNING SPEC. Basis: operator instruction 2026-08-29 ("when a plan is offered,
we can pivot to 'iterate over playbook' which uses a subagent to do one TODO at a
time... each task is done by one agent's session and the playbook serves as the
ledger, each new task gets a fresh agent, and the playbook.md works as a log").
Promote to a REQ before anything depends on it.

Thesis
------
Plan mode already persists its output (`~/.harness/policy/plan-mode.md`: the first
write on exit is the plan itself). That policy stops at "the plan is on disk" and
says nothing about WHO executes it. Executing a 9-step plan inline means the main
session accumulates every file read, every failed edit, and every test log from
step 1 while it works step 9 -- context rot, and the last tasks are done worst.

This hook closes that by offering, at the exact moment the plan is approved, the
alternative: the plan becomes `playbook.md`, a ledger of `[TODO]` items, and each
item is executed by ONE fresh subagent session. The main session holds only the
ledger. The subagent's context dies with the task; what survives is the status
flip and one `_Lessons:` line it appended.

Two modes, one file
-------------------
  --pivot   PostToolUse on ExitPlanMode. Fires only when the plan is actually
            multi-task (>= PIVOT_MIN_STEPS steps) -- offering to build a ledger
            for a two-step plan is ceremony, and ceremony gets hooks disabled.
  --status  SessionStart / UserPromptSubmit. Silent unless a playbook with open
            items exists. One line: counts + the next TODO. This is what keeps a
            resumed session on the ledger instead of re-deriving the plan.
  --plan    UserPromptSubmit. Fires when the prompt reads as a request to plan.
            Prepends the `ultrathink` keyword (raising reasoning effort the only
            way a hook can) and routes plan AUTHORSHIP to a Fable subagent.

On the model ladder
-------------------
A hook CANNOT change the session model -- no such field exists in the hook output
contract (checked against the official hooks reference: zero mentions of `model`).
Only the operator can, via `/model`. So the tiering lives one level down, where it
IS controllable: the `model` parameter on each subagent dispatch.

    plan authorship   -> fable   (widest view, writes the playbook, no code)
    per-task subplan  -> opus    (large scope -> small internal scope)
    implementation    -> sonnet  (executes the subplan, verifies)

Stuck goes UP one tier, one shot each: sonnet -> opus -> fable -> stop. Each tier
appends its `_Blocked:` evidence to the ledger before handing up, because fable
cannot re-scope a task it only knows failed -- it has to read what each tier hit.

This is strictly better than switching the session model: the main session keeps
whatever the operator set, and every task gets the full ladder regardless.

Contract
--------
Require   - stdin carries the hook payload as JSON.
Guarantee - exit 0 always. Emits additionalContext only when its mode's trigger
            holds; prints nothing otherwise.
Maintain  - fails OPEN and SILENT on every unexpected condition. This hook offers
            a workflow; it never blocks one.
Assert    - read-only. It never creates or edits playbook.md -- the model writes
            the ledger, so a malformed payload can never fabricate a task list.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys

# Below this, a plan is a to-do list, not a campaign. Inline is cheaper than a ledger.
PIVOT_MIN_STEPS = 3

# Searched in order, relative to the repo root (or cwd when not a repo).
PLAYBOOK_NAMES = ("playbook.md", "docs/playbook.md", ".spec/playbook.md")

# The prompt reads as "produce a plan", not "do a thing". Deliberately narrow: a
# false positive costs an unwanted ultrathink and a paragraph of context on every
# prompt containing the word "plan", which is how this hook earns a disable.
PLAN_REQUEST_RE = re.compile(
    r"\b(?:make|write|draft|give me|come up with|propose|lay out|sketch)\s+"
    r"(?:me\s+)?(?:a|an|the)?\s*(?:implementation\s+|migration\s+|detailed\s+)?"
    r"(?:plan|roadmap|playbook|spec)\b"
    r"|\bplan (?:out|for) how\b|\bhow would you (?:approach|implement|structure)\b"
    r"|\bspec (?:this |it )?out\b|\bplan mode\b",
    re.I)

# Raising reasoning effort is not a hook-settable knob; the keyword prepended to the
# prompt is. One notch above the normal default, per the operator's brief.
THINK_KEYWORD = "ultrathink"

STATUS_RE = re.compile(r"\[(TODO|WIP|DONE|BLOCKED)\]")

# A "step" in an approved plan: a markdown list item or a numbered line. Prose
# paragraphs and headings deliberately do not count.
STEP_RE = re.compile(r"^\s*(?:[-*+]\s+|\d+[.)]\s+)\S", re.M)


def _emit(event: str, text: str) -> None:
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": event,
        "additionalContext": text,
    }}))


def _root(cwd: str) -> str:
    try:
        p = subprocess.run(["git", "rev-parse", "--show-toplevel"],
                           cwd=cwd, capture_output=True, text=True, timeout=10)
        if p.returncode == 0 and p.stdout.strip():
            return p.stdout.strip()
    except Exception:
        pass
    return cwd


def _find_playbook(root: str) -> str | None:
    for name in PLAYBOOK_NAMES:
        p = os.path.join(root, *name.split("/"))
        if os.path.isfile(p):
            return p
    return None


def _ledger(path: str) -> tuple[dict[str, int], str | None, str | None]:
    """(counts by status, first WIP line, first TODO line)."""
    counts = {"TODO": 0, "WIP": 0, "DONE": 0, "BLOCKED": 0}
    wip = todo = None
    try:
        with open(path, encoding="utf-8") as f:
            lines = f.read().splitlines()
    except Exception:
        return counts, None, None
    for line in lines:
        m = STATUS_RE.search(line)
        if not m:
            continue
        st = m.group(1)
        counts[st] += 1
        if st == "WIP" and wip is None:
            wip = line.strip()
        elif st == "TODO" and todo is None:
            todo = line.strip()
    return counts, wip, todo


def _pivot(payload: dict) -> int:
    tool = payload.get("tool_name") or ""
    if tool != "ExitPlanMode":
        return 0
    plan = (payload.get("tool_input") or {}).get("plan") or ""
    if len(STEP_RE.findall(plan)) < PIVOT_MIN_STEPS:
        return 0                       # short plan: inline is the cheaper path

    root = _root(payload.get("cwd") or os.getcwd())
    existing = _find_playbook(root)
    where = (existing or os.path.join(root, "playbook.md")).replace("\\", "/")

    if existing:
        counts, _, _ = _ledger(existing)
        head = ("PLAYBOOK PIVOT -- a playbook already exists at %s (%d done / %d open). "
                "Append this plan's tasks to it as [TODO] rather than starting a new file."
                % (existing, counts["DONE"], counts["TODO"] + counts["WIP"]))
    else:
        head = ("PLAYBOOK PIVOT -- this plan has %d+ steps. Before implementing, offer the "
                "operator the choice IN THEIR OWN TERMS (CLAUDE.md, 'Options in the "
                "operator's terms'): work it one task at a time so each task gets a clean "
                "session, or just do the whole thing here. Name the trade, not the "
                "machinery." % PIVOT_MIN_STEPS)

    _emit("PostToolUse", head + """

Iterate over playbook means:
  1. Write the plan to %s as a ledger -- one line per task:
     - [TODO] T1 <what observable thing changes>
       _Files:_ path/one.py, path/two.py
  2. Work ONE task per fresh subagent. Flip it to [WIP], dispatch a subagent whose
     whole brief is that task plus the playbook path, and give it nothing else.
  3. The subagent implements, VERIFIES (no run = not done), and appends its own
     `_Lessons:` line under the task. It reports back a verdict, not a transcript.
  4. The main session flips [WIP] -> [DONE] and moves to the next [TODO]. It does
     not read the subagent's working context. That is the whole point.
  Never batch two TODOs into one subagent. Never carry one subagent to the next task.

Full protocol: ~/.claude/rules/playbook.md""" % where)
    return 0


def _status(payload: dict) -> int:
    root = _root(payload.get("cwd") or os.getcwd())
    path = _find_playbook(root)
    if not path:
        return 0
    counts, wip, todo = _ledger(path)
    if counts["TODO"] + counts["WIP"] == 0:
        return 0                       # nothing open: say nothing
    nxt = wip or todo or ""
    if len(nxt) > 160:
        nxt = nxt[:157] + "..."
    _emit(payload.get("hook_event_name") or "UserPromptSubmit",
          "PLAYBOOK %s: %d done / %d todo / %d wip%s. Next: %s%s"
          % (os.path.relpath(path, root), counts["DONE"], counts["TODO"], counts["WIP"],
             (" / %d blocked" % counts["BLOCKED"]) if counts["BLOCKED"] else "",
             nxt,
             "  (dispatch it to a fresh subagent, one task only)"))
    return 0


def _plan_request(payload: dict) -> int:
    prompt = payload.get("prompt") or ""
    if not PLAN_REQUEST_RE.search(prompt):
        return 0

    root = _root(payload.get("cwd") or os.getcwd())
    existing = _find_playbook(root)
    if existing:
        counts, _, _ = _ledger(existing)
        if counts["TODO"] + counts["WIP"]:
            return 0        # a campaign is already open; --status owns this prompt

    _emit("UserPromptSubmit", THINK_KEYWORD + """

PLAN REQUEST DETECTED. Author the plan on the top tier, then hand down:

  1. Do NOT draft the plan in this session. Dispatch ONE subagent with
     model="fable" whose only job is to author the plan. It writes no code.
  2. Its output lands in `playbook.md` at the repo root as a ledger -- one
     `- [TODO] T<n> <observable change>` per task, each with `_Files:` and
     `_Verify:`. See ~/.claude/rules/playbook.md for the exact format.
  3. Present the ledger to the operator and STOP. No implementation before
     they agree. Approval of a plan is not approval to implement it inline.
  4. On approval, work it one task per fresh subagent, each task running the
     ladder: opus drafts the subplan -> sonnet implements it. Stuck goes up one
     tier, one shot each -- sonnet -> opus -> fable -> stop -- and each tier
     appends its `_Blocked:` evidence to the ledger before handing up.

A hook cannot switch this session's model, so the tiering happens per dispatch.
If the operator wants the SESSION on fable too, they type /model -- say so once,
do not ask twice.""")
    return 0


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0
    try:
        if "--pivot" in sys.argv:
            return _pivot(payload)
        if "--plan" in sys.argv:
            return _plan_request(payload)
        return _status(payload)
    except Exception:
        return 0                       # fail open: never trap a turn


if __name__ == "__main__":
    sys.exit(main())
