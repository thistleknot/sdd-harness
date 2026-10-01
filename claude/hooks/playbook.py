#!/usr/bin/env python3
"""Playbook pivot: turn an approved architecture into a ledger worked one task per subagent.

NO GOVERNING SPEC. Basis: operator instruction 2026-08-29 ("when a plan is offered,
we can pivot to 'iterate over playbook' which uses a subagent to do one TODO at a
time... each task is done by one agent's session and the playbook serves as the
ledger, each new task gets a fresh agent, and the playbook.md works as a log") and
2026-08-29 second pass ("the keyword architect used instead of plan"; "instead of
TODO, I want OPEN"; "sets of tasks identified as either parallel (independent) or
serially dependent... submitted as parallel subagent calls, and we await the entire
layer before moving onto the next"). Promote to a REQ before anything depends on it.

The naming half IS spec'd: ~/.harness/specs REQ #36 ("Architect artifacts are named
for their intent") -- a plan file's basename must be the kebab slug of its own H1,
and this hook is named there as the surface that checks it at ExitPlanMode.

Thesis
------
Plan mode already persists its output (`~/.harness/policy/plan-mode.md`: the first
write on exit is the plan itself). That policy stops at "the plan is on disk" and
says nothing about WHO executes it. Executing a 9-step plan inline means the main
session accumulates every file read, every failed edit, and every test log from
step 1 while it works step 9 -- context rot, and the last tasks are done worst.

This hook closes that by offering, at the exact moment the architecture is approved,
the alternative: it becomes `playbook.md`, a ledger of `[OPEN]` items grouped into
LAYERS, and each item is executed by ONE fresh subagent session. The main session
holds only the ledger. The subagent's context dies with the task; what survives is
the status flip and one `_Lessons:` line it appended.

The word is `architect`
-----------------------
"architect X" is the operator's keyword for this whole move: author the ledger, do
not write code. "plan" stays recognised -- native plan mode is called plan mode and
the fingers know the word -- but the artifact is always `playbook.md`, never
`plan.md`, and pending work is always `[OPEN]`, never `[TODO]`.

Layers
------
Tasks group into layers, and a layer declares ONE operation type:

    parallel    -- independent, like a mean and a stdev: every task reads the same
                   input, none reads another's output. All its OPEN tasks dispatch
                   at once (max 4 concurrent), `_Files:` sets must not intersect.
    sequential  -- serially dependent, like an EMA or an RNN: task n's input is
                   task n-1's output. Strictly one at a time, in listed order.

A layer is a BARRIER: nothing in layer N+1 starts until every task in layer N is
[DONE]. Mixing op types inside one layer is legal but discouraged -- it strands the
parallel siblings behind the sequential chain and breaks prompt-cache reuse across
the fan-out.

On the model ladder
-------------------
A hook CANNOT change the session model -- no such field exists in the hook output
contract (checked against the official hooks reference: zero mentions of `model`).
Only the operator can, via `/model`. So the tiering lives one level down, where it
IS controllable: the `model` parameter on each subagent dispatch.

    ledger authorship -> fable   (widest view, writes the playbook, no code)
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

# Below this, an architecture is a to-do list, not a campaign. Inline is cheaper.
PIVOT_MIN_STEPS = 3

# CLAUDE.md 12 / rules/playbook.md: never more than this many subagents at once.
MAX_PARALLEL = 4

# Searched in order, relative to the repo root (or cwd when not a repo).
PLAYBOOK_NAMES = ("playbook.md", "docs/playbook.md", ".spec/playbook.md")

# REQ #36: a plan file is named for its intent. The name is the kebab slug of the
# plan's own H1, so it is checkable rather than a matter of taste -- these two caps
# are the whole of the "descriptive, not a sentence" judgement.
NAME_MAX_WORDS = 6
NAME_MAX_CHARS = 60

# Truncating at a word cap strands the title on a preposition or an article
# ("plan-files-are-named-for-their"). Trailing function words carry no intent, so
# they come off. Never below two words -- "fix-the" is worse than "fix-the-loader".
NAME_TAIL_STOPWORDS = frozenset(
    "a an the of to for and or in on at by is are was were be been its their this "
    "that these those with from as it into over under but so than then".split())

# The first `# ` heading, which IS the intent phrase. Setext headings and `##` do
# not count: the plan template puts the title on line 1 as an ATX h1.
H1_RE = re.compile(r"^#[ 	]+(\S.*?)\s*#*\s*$", re.M)

# The prompt reads as "architect this", not "do a thing". Deliberately narrow: a
# false positive costs an unwanted ultrathink and a paragraph of context on every
# prompt containing the word "plan", which is how this hook earns a disable.
# `architect` is the operator's keyword; the plan/spec forms stay as synonyms.
ARCHITECT_REQUEST_RE = re.compile(
    r"\barchitect(?:\s+(?:out|this|it|me)\b|\s+(?:a|an|the)\b|\s+\w+\s+(?:for|into|so)\b)"
    r"|\b(?:let.s|please|can you|could you|go)\s+architect\b"
    r"|^\s*/?architect\b"
    r"|\b(?:make|write|draft|give me|come up with|propose|lay out|sketch)\s+"
    r"(?:me\s+)?(?:a|an|the)?\s*(?:implementation\s+|migration\s+|detailed\s+)?"
    r"(?:plan|roadmap|playbook|spec)\b"
    r"|\bplan (?:out|for) how\b|\bhow would you (?:approach|implement|structure)\b"
    r"|\bspec (?:this |it )?out\b|\bplan mode\b",
    re.I)

# Raising reasoning effort is not a hook-settable knob; the keyword prepended to the
# prompt is. One notch above the normal default, per the operator's brief.
THINK_KEYWORD = "ultrathink"

# TODO is the retired spelling of OPEN. Still parsed so pre-2026-08-29 ledgers keep
# reporting; never emitted.
STATUS_RE = re.compile(r"\[(OPEN|TODO|WIP|DONE|BLOCKED)\]")

# "## Layer 2 -- parallel" / "## Layer 2 (sequential)" / "### Layer 2: sequential".
LAYER_RE = re.compile(
    r"^#{1,4}\s*Layer\s+([^\n:(\-–—]+?)\s*[:(\-–—\s]*"
    r"(parallel|sequential|mixed)?\s*\)?\s*$", re.I)

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


def _parse(path: str) -> tuple[dict[str, int], list[dict]]:
    """(counts by status, task records in file order).

    A record is {status, line, layer, mode}. `layer` is None for tasks written
    before any Layer heading -- an unlayered ledger still parses, it just gets no
    fan-out advice.
    """
    counts = {"OPEN": 0, "WIP": 0, "DONE": 0, "BLOCKED": 0}
    tasks: list[dict] = []
    layer = mode = None
    try:
        with open(path, encoding="utf-8") as f:
            lines = f.read().splitlines()
    except Exception:
        return counts, tasks
    for line in lines:
        h = LAYER_RE.match(line.strip())
        if h:
            layer, mode = h.group(1).strip(), (h.group(2) or "").lower() or None
            continue
        m = STATUS_RE.search(line)
        if not m:
            continue
        st = "OPEN" if m.group(1) == "TODO" else m.group(1)
        counts[st] += 1
        tasks.append({"status": st, "line": line.strip(), "layer": layer, "mode": mode})
    return counts, tasks


def _active_layer(tasks: list[dict]) -> tuple[str | None, str | None, list[dict]]:
    """The earliest layer still holding unfinished work: (name, mode, its tasks)."""
    for t in tasks:
        if t["status"] in ("OPEN", "WIP", "BLOCKED"):
            layer, mode = t["layer"], t["mode"]
            return layer, mode, [x for x in tasks if x["layer"] == layer]
    return None, None, []


def _title_slug(plan: str) -> str | None:
    """Kebab slug of the plan's H1, or None when it has no H1 (REQ #36).

    "# Retry the handshake with backoff" -> "retry-the-handshake-with-backoff".
    Truncation is by whole words first, then a hard character cap, so a long title
    degrades to its opening phrase instead of a mid-word stump.
    """
    m = H1_RE.search(plan or "")
    if not m:
        return None
    words = [w for w in re.split(r"[^a-z0-9]+", m.group(1).lower()) if w]
    if not words:
        return None
    words = words[:NAME_MAX_WORDS]
    while len(words) > 2 and words[-1] in NAME_TAIL_STOPWORDS:
        words.pop()
    slug = "-".join(words)
    if len(slug) > NAME_MAX_CHARS:
        slug = slug[:NAME_MAX_CHARS].rsplit("-", 1)[0] or slug[:NAME_MAX_CHARS]
    return slug.strip("-") or None


def _rename_note(payload: dict) -> str | None:
    """The rename directive when the plan file's name is not its intent (REQ #36).

    Returns None when the payload carries no plan path, the plan has no H1, or the
    name is already correct. The hook instructs; it does not move the file -- the
    CLI holds its own reference to that path.
    """
    ti = payload.get("tool_input") or {}
    path = (ti.get("planFilePath") or "").replace("\\", "/")
    if not path:
        return None
    want = _title_slug(ti.get("plan") or "")
    if not want:
        return None
    base = os.path.basename(path)
    stem, ext = os.path.splitext(base)
    if stem == want:
        return None                    # already named for what it is
    target = os.path.join(os.path.dirname(path), want + (ext or ".md")).replace("\\", "/")
    return ("""PLAN NAME -- `%s` is a generated slug, not what this plan is about
(REQ #36: a plan file is named for its intent). FIRST action now that writes are
unlocked, before anything else: rename it.
    git mv %s %s      # or Move-Item if the repo does not track it
Then refer to it by the new path for the rest of the session."""
            % (base, path, target))


def _pivot(payload: dict) -> int:
    tool = payload.get("tool_name") or ""
    if tool != "ExitPlanMode":
        return 0
    plan = (payload.get("tool_input") or {}).get("plan") or ""
    rename = _rename_note(payload)
    if len(STEP_RE.findall(plan)) < PIVOT_MIN_STEPS:
        # Short plan: inline is the cheaper path, so no ledger pitch -- but a
        # misnamed file is misnamed at any length.
        if rename:
            _emit("PostToolUse", rename)
        return 0

    root = _root(payload.get("cwd") or os.getcwd())
    existing = _find_playbook(root)
    where = (existing or os.path.join(root, "playbook.md")).replace("\\", "/")

    if existing:
        counts, _ = _parse(existing)
        head = ("PLAYBOOK PIVOT -- a playbook already exists at %s (%d done / %d open). "
                "Append this architecture's tasks to it as [OPEN] under a new Layer "
                "heading rather than starting a new file."
                % (existing, counts["DONE"], counts["OPEN"] + counts["WIP"]))
    else:
        head = ("PLAYBOOK PIVOT -- this architecture has %d+ steps. Before implementing, "
                "offer the operator the choice IN THEIR OWN TERMS (CLAUDE.md, 'Options in "
                "the operator's terms'): work it one task at a time so each task gets a "
                "clean session, or just do the whole thing here. Name the trade, not the "
                "machinery." % PIVOT_MIN_STEPS)

    _emit("PostToolUse", (rename + chr(10) * 2 if rename else "") + head + """

Iterate over playbook means:
  1. Write the architecture to %s as a layered ledger:
     ## Layer 1 - parallel
     - [OPEN] T1 <what observable thing changes>
       _Files:_ path/one.py
       _Verify:_ <command that proves it>
  2. Group tasks into LAYERS, one operation type per layer. parallel = independent
     (a mean and a stdev). sequential = each task eats the last one's output (an
     EMA, an RNN). Do not mix types inside a layer -- it strands the parallel
     siblings and breaks cache reuse across the fan-out.
  3. Work the active layer only. A parallel layer dispatches ALL its [OPEN] tasks
     at once, max %d concurrent, one fresh subagent each, `_Files:` sets disjoint.
     A sequential layer runs strictly one at a time in listed order.
  4. The layer is a BARRIER: await every task in it before opening the next layer.
  5. Each subagent implements, VERIFIES (no run = not done), and appends its own
     `_Lessons:` line under its task. It reports a verdict, not a transcript. The
     main session flips [WIP] -> [DONE] and never reads its working context.
  Never batch two tasks into one subagent. Never carry one subagent to a second task.

Full protocol: ~/.claude/rules/playbook.md""" % (where, MAX_PARALLEL))
    return 0


def _status(payload: dict) -> int:
    root = _root(payload.get("cwd") or os.getcwd())
    path = _find_playbook(root)
    if not path:
        return 0
    counts, tasks = _parse(path)
    if counts["OPEN"] + counts["WIP"] == 0:
        return 0                       # nothing open: say nothing

    layer, mode, in_layer = _active_layer(tasks)
    wip = next((t["line"] for t in tasks if t["status"] == "WIP"), None)
    nxt = wip or next((t["line"] for t in tasks if t["status"] == "OPEN"), "")
    if len(nxt) > 160:
        nxt = nxt[:157] + "..."

    if layer is None:
        advice = "  (dispatch it to a fresh subagent, one task only)"
    else:
        open_here = sum(1 for t in in_layer if t["status"] == "OPEN")
        held = [t for t in in_layer if t["status"] == "BLOCKED"]
        if mode == "parallel":
            advice = ("  Layer %s is parallel: dispatch its %d open task%s together "
                      "(max %d concurrent, disjoint _Files:), then await the whole layer."
                      % (layer, open_here, "" if open_here == 1 else "s", MAX_PARALLEL))
        elif mode == "sequential":
            advice = ("  Layer %s is sequential: one task at a time, in order; %d left "
                      "before the barrier lifts." % (layer, open_here))
        else:
            advice = ("  Layer %s (%d open): declare it parallel or sequential before "
                      "dispatching." % (layer, open_here))
        if held:
            advice += (" %d task%s BLOCKED -- it holds the barrier; escalate one tier "
                       "(sonnet -> opus -> fable) before opening the next layer."
                       % (len(held), "" if len(held) == 1 else "s"))

    _emit(payload.get("hook_event_name") or "UserPromptSubmit",
          "PLAYBOOK %s: %d done / %d open / %d wip%s. Next: %s\n%s"
          % (os.path.relpath(path, root), counts["DONE"], counts["OPEN"], counts["WIP"],
             (" / %d blocked" % counts["BLOCKED"]) if counts["BLOCKED"] else "",
             nxt, advice))
    return 0


def _architect_request(payload: dict) -> int:
    prompt = payload.get("prompt") or ""
    if not ARCHITECT_REQUEST_RE.search(prompt):
        return 0

    root = _root(payload.get("cwd") or os.getcwd())
    existing = _find_playbook(root)
    if existing:
        counts, _ = _parse(existing)
        if counts["OPEN"] + counts["WIP"]:
            return 0        # a campaign is already open; --status owns this prompt

    _emit("UserPromptSubmit", THINK_KEYWORD + """

ARCHITECT REQUEST DETECTED. Author the ledger on the top tier, then hand down:

  1. Do NOT draft it in this session. Dispatch ONE subagent with model="fable"
     whose only job is to author the architecture. It writes no code.
  2. Its output lands in `playbook.md` at the repo root as a LAYERED ledger --
     `## Layer <n> - parallel|sequential` headings, and under each one
     `- [OPEN] T<n> <observable change>` with `_Files:` and `_Verify:`.
     See ~/.claude/rules/playbook.md for the exact format.
  3. One operation type per layer: parallel = independent tasks (a mean and a
     stdev); sequential = each eats the last one's output (an EMA, an RNN).
     Mixing inside a layer is legal but costs cache reuse -- avoid it.
  4. Present the ledger to the operator and STOP. No implementation before they
     agree. Approval of an architecture is not approval to implement it inline.
  5. On approval, work ONE LAYER at a time. A parallel layer fans its [OPEN]
     tasks out to fresh subagents at once (max %d, disjoint `_Files:`); a
     sequential layer runs them one by one. Await the ENTIRE layer before the
     next. Each task runs the ladder: opus drafts the subplan -> sonnet
     implements it. Stuck goes up one tier, one shot each -- sonnet -> opus ->
     fable -> stop -- and each tier appends its `_Blocked:` evidence first.

A hook cannot switch this session's model, so the tiering happens per dispatch.
If the operator wants the SESSION on fable too, they type /model -- say so once,
do not ask twice.""" % MAX_PARALLEL)
    return 0


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0
    try:
        if "--pivot" in sys.argv:
            return _pivot(payload)
        if "--plan" in sys.argv or "--architect" in sys.argv:
            return _architect_request(payload)
        return _status(payload)
    except Exception:
        return 0                       # fail open: never trap a turn


if __name__ == "__main__":
    sys.exit(main())
