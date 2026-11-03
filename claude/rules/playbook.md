<!-- NO GOVERNING SPEC. Basis: operator instruction 2026-08-29 (one task per fresh
     subagent; playbook.md is the ledger AND the log) + same-day second pass
     (`architect` is the keyword; `[OPEN]` replaces `[TODO]`; tasks group into
     parallel/sequential layers and a layer is awaited whole). Enforced-ish by
     hooks/playbook.py (PostToolUse ExitPlanMode = offer; SessionStart +
     UserPromptSubmit = status line). Promote to a REQ before depending on it.
     The naming law below IS spec'd: ~/.harness/specs REQ #36. -->

# Playbook — one task, one agent session, one ledger

Plan mode persists the plan (`~/.harness/policy/plan-mode.md`). This says who executes it.

**The problem it solves:** implementing a 9-step plan inline means the session that
works step 9 is still carrying every file read, failed edit, and test log from step 1.
The last tasks get the worst context. That is context rot, and no amount of care in
the plan prevents it.

**The move:** the architecture becomes `playbook.md`, a ledger of `[OPEN]` items
grouped into layers. Each item is executed by ONE fresh subagent session. The main
session holds only the ledger.

## The word is `architect`

`architect` is the keyword. "architect this", "architect the migration", "/architect"
— it means **author the ledger, do not write code**. It is the same call plan mode
makes, under the word the operator actually uses.

"plan" still triggers it (native plan mode is called plan mode, and the fingers know
the word) — but the artifact is always `playbook.md`, never `plan.md`, and pending
work is always `[OPEN]`, never `[TODO]`. `[TODO]` is the retired spelling; the hook
still parses old ledgers, nothing new ever writes it.

Detected by `~/.claude/hooks/playbook.py --plan` on UserPromptSubmit.

## The name says what it is

**Where it lives: `./.tmp/plans/` in the project, never `~/.claude/plans/`.** The
`plansDirectory` setting points plan mode there, so a plan sits beside the repo it
describes and is disposable scratch. A decision worth keeping is promoted to the
project's spec dir (`.specs/`); the `playbook.md` ledger stays at the repo root.

A plan file is named for its intent. Claude Code mints `plans/<random-slug>.md`
when plan mode opens -- before anything is known about the work -- so
`cosmic-mapping-whisper.md` tells the operator nothing and the directory is only
searchable by opening every file. That name is a placeholder, not a name.

**The rule (REQ #36): the filename is the kebab slug of the artifact's own H1,**
at most 6 words or 60 characters.

```
# Retry the handshake with backoff   ->  retry-the-handshake-with-backoff.md
plans/sharded-floating-dolphin.md    ->  a defect; rename it
```

Renaming is the FIRST act once writes unlock -- `git mv`, then refer to the new
path for the rest of the session. `~/.claude/hooks/playbook.py --pivot` checks it
at `ExitPlanMode` and prints the exact target path; it instructs the move rather
than performing it, because the CLI holds its own reference to that path.

The same phrase names the campaign in the ledger: `# Playbook: <campaign>`.

## The ledger format

`playbook.md` lives at the repo root (or `docs/`, or `.spec/`). It is both the task
list and the log — there is no second file.

```markdown
# Playbook: <campaign>
Source: <path or "this session, YYYY-MM-DD">

## Layer 1 — parallel
- [DONE] T1 Parse the config before the socket opens
  _Files:_ src/config.py
  _Verify:_ pytest tests/test_config.py -q
  _Lessons:_ the loader was already in cli.py — extended it instead of adding one.

- [WIP] T2 Surface the retry count in the status line
  _Files:_ src/status.py
  _Verify:_ pytest tests/test_status.py -q

## Layer 2 — sequential
- [OPEN] T3 Retry the handshake with backoff
  _Files:_ src/net.py
  _Verify:_ pytest tests/test_net.py -q

- [OPEN] T4 Feed the backoff state into the reconnect budget
  _Files:_ src/net.py, src/budget.py
  _Verify:_ pytest tests/test_budget.py -q
```

Statuses: `[OPEN]` → `[WIP]` → `[DONE]`, or `[BLOCKED]` with a one-line reason.
Every task carries `_Files:` — a task that names no files is a wish, not a task
(CLAUDE.md, "every file traces to a task"). `_Verify:` is the command that proves it.

## Layers — parallel vs sequential

Every task lives in exactly one layer, and a layer declares ONE operation type:

| Type | Shape | Analogy | Dispatch |
|---|---|---|---|
| **parallel** | independent — every task reads the same input, none reads another's output | a mean and a stdev over one series | all `[OPEN]` tasks at once, max 4 concurrent |
| **sequential** | serially dependent — task n's input is task n-1's output | an EMA, an RNN | strictly one at a time, in listed order |

**The layer is a barrier.** Nothing in layer N+1 starts until every task in layer N is
`[DONE]`. That is the whole reason layers exist: it is the only place a dependency is
allowed to be expressed, so within a layer nothing has to be reasoned about twice.

- **parallel layer** — fan out every `[OPEN]` task at once, one fresh subagent each,
  max 4 active (CLAUDE.md 12). Their `_Files:` sets **must be disjoint**. Intersecting
  files mean the tasks are not independent: either they belong in a sequential layer,
  or they run in isolated worktrees.
- **sequential layer** — one at a time, in listed order. Each task may read the
  previous task's `_Lessons:` line; that line is the entire handoff between them.
- **`[BLOCKED]` holds the barrier.** Escalate it (below) before opening the next layer.
  A blocked task is not one you route around — its layer is not done.

**Do not mix operation types inside one layer.** It is legal, and the status line will
nag about a layer with no declared type, but a mixed layer strands the parallel siblings
behind the sequential chain and breaks prompt-cache reuse across the fan-out — the
fan-out shares one prefix only when its members are the same shape. A layer whose tasks
split into "these three are independent, then this chain" is two layers.

Layer count is not a virtue. Two layers of six beats six layers of two: every barrier is
idle time spent waiting on the slowest member.

## The party

A hook cannot switch the session model — no such field exists in the hook output
contract. So the tiering lives one level down, on each subagent dispatch, by **agent
type**: each role's model and effort come from `~/.harness/tiers.toml`, rendered into the
agent files by `render_agents.py`. This file names roles, never models, so a change of
provider or model never touches it. The main session stays on whatever the operator set.

| Stage | Role | Writes | Why |
|---|---|---|---|
| Ledger authorship | the **oracle** agent | `playbook.md` only | Widest view, sees the campaign whole — including where the layer boundaries fall. Never code. |
| Per-task subplan | the **Leader** (this session) | `.playbook/T<n>.subplan.md` only | Turns large external scope into a small contract: signatures + docstrings. |
| Implementation | a **doer** agent (a Fighter) | source + `_Lessons:` | Executes a subplan that is already decided; it does not need to re-derive judgment. |
| Unstick | the Leader, then the **oracle** | subplan, then the ledger | Re-enters on `[BLOCKED]` and *only* then. |

The point of the split is that a Fighter never makes an architectural call and the Oracle
never burns context on a `pytest` loop (CLAUDE.md 9).

If the operator wants this *session* on a different model, that is a `/model` keystroke
only they can make. Say it once; do not ask twice.

## The loop

1. Main session takes the **active layer** — the earliest one with unfinished work —
   and reads its declared type.
2. Flip what it is about to dispatch to `[WIP]`: **all** the `[OPEN]` tasks if the layer
   is parallel, **one** if it is sequential.
3. **Subplan (the Leader).** For each task the Leader writes `.playbook/T<n>.subplan.md`
   from the task line, its `_Files:` and its `_Verify:`: what to change in each file, in
   what order, as signatures and docstrings, and what "done" looks like. It touches no
   source bodies, and it is small by construction (a contract).
4. **Implement (a doer).** A *fresh* `doer` subagent. Its brief is the subplan path and
   nothing else — not the playbook, not the sibling tasks, not this session's context.
   That absence IS the feature.
5. It implements, runs `_Verify:`, and appends its own `_Lessons:` line under the task in
   the playbook. No run = not done (Law 7). It returns a **verdict**, not a transcript:
   pass/fail + the one discriminating line.
6. Main session flips `[WIP]` → `[DONE]` (or `[BLOCKED]`).
7. **Await the entire layer.** Only when every task in it is `[DONE]` does the next
   layer open.

The subplan file is scratch, not a deliverable. Delete `.playbook/T<n>.subplan.md` when
the task closes; the `_Lessons:` line is what survives. Gitignore `.playbook/`.

**Never** batch two tasks into one subagent. **Never** carry a subagent to a second task —
a reused session is exactly the rot the ledger exists to avoid. **Never** pull the
subagent's working context back into the main session; the `_Lessons:` line is the
entire handoff, and if it is not enough, the task was scoped too big. **Never** start a
task from the next layer because the current one is still waiting — that is the barrier,
and skipping it is how a sequential dependency gets discovered at merge time.

## Failure — stuck goes up the party, one shot each

A Fighter stuck asks the Leader. The Leader stuck asks the Oracle. The Oracle replans.
Nobody gets two tries at the same wall (the Leader's one clarification is
`leader_attempts` in tiers.toml), and nobody skips a step.

| Role | Gets one shot at | On failure | Writes |
|---|---|---|---|
| **doer** | implementing the subplan | `[BLOCKED]` + evidence → the Leader | source, `_Blocked:` |
| **Leader** | one clarification of the subplan around the blocker | `[BLOCKED]` + evidence → the oracle | subplan, `_Blocked:` |
| **oracle** | replanning the task — including moving it to another layer | the Leader decides and logs the basis | `playbook.md` |

**Escalation carries evidence, not a verdict.** A role that gets stuck appends a
`_Blocked:` line under the task before it hands up — what it tried, the exact failing
output, and what it thinks the real obstacle is:

```markdown
- [BLOCKED] T3 Retry the handshake with backoff
  _Files:_ src/net.py
  _Blocked: doer_ — subplan step 3 says patch `_connect`, but `_connect` is
    generated by the codegen in build.py; the edit is overwritten on every build.
    `pytest tests/test_net.py -q` → 2 failed, AssertionError: retries=0
  _Blocked: leader_ — cannot clarify around this at subplan scope. The task assumes
    net.py is hand-written. That assumption belongs to the ledger, not the subplan.
```

This is the whole reason the playbook is a log and not just a task list. The Oracle
cannot replan a task it only knows failed — it has to read what each role hit and why
they could not get past it. **A `[BLOCKED]` with no `_Blocked:` evidence line is not an
escalation, it is a give-up; send it back to the role that wrote it.**

A common Oracle verdict is that the layering was wrong: a task placed in a parallel layer
turned out to read a sibling's output. The fix is to move that task into a sequential
layer, not to serialise the whole campaign.

After the Oracle replans, the task re-enters at the bottom of its layer: fresh subplan,
fresh doer. If it blocks a second time after the Oracle's replan, the Leader decides and
logs the basis — the Oracle augments a plan at most twice per task
(`rules/orchestration.md`), and the operator is asked only for the standing stops.

## When NOT to use this

- Fewer than 3 tasks — the ledger costs more than it saves.
- Tasks that are genuinely one edit spread across files (a rename) — that is one task.
- Exploration, where the next step depends on what the last one found. A ledger fixes
  the order up front; if the order is unknown, architect first.
