<!-- NO GOVERNING SPEC. Basis: operator instruction 2026-08-29 (one TODO per fresh
     subagent; playbook.md is the ledger AND the log). Enforced-ish by
     hooks/playbook.py (PostToolUse ExitPlanMode = offer; SessionStart +
     UserPromptSubmit = status line). Promote to a REQ before depending on it. -->

# Playbook — one task, one agent session, one ledger

Plan mode persists the plan (`~/.harness/policy/plan-mode.md`). This says who executes it.

**The problem it solves:** implementing a 9-step plan inline means the session that
works step 9 is still carrying every file read, failed edit, and test log from step 1.
The last tasks get the worst context. That is context rot, and no amount of care in
the plan prevents it.

**The move:** the plan becomes `playbook.md`, a ledger of `[TODO]` items. Each item is
executed by ONE fresh subagent session. The main session holds only the ledger.

## The ledger format

`playbook.md` lives at the repo root (or `docs/`, or `.spec/`). It is both the task
list and the log — there is no second file.

```markdown
# Playbook: <campaign>
Source plan: <path or "this session, YYYY-MM-DD">

- [DONE] T1 Parse the config before the socket opens
  _Files:_ src/config.py, src/net.py
  _Verify:_ pytest tests/test_config.py -q
  _Lessons:_ the loader was already in cli.py — extended it instead of adding one.

- [WIP] T2 Retry the handshake with backoff
  _Files:_ src/net.py

- [TODO] T3 Surface the retry count in the status line
  _Files:_ src/status.py
```

Statuses: `[TODO]` → `[WIP]` → `[DONE]`, or `[BLOCKED]` with a one-line reason.
Every task carries `_Files:` — a task that names no files is a wish, not a task
(CLAUDE.md, "every file traces to a task"). `_Verify:` is the command that proves it.

## The model ladder

A hook cannot switch the session model — no such field exists in the hook output
contract. So the tiering lives one level down, on each subagent dispatch, where the
`model` parameter *is* controllable. This is the better place regardless: the main
session stays on whatever the operator set, and every task still gets the full ladder.

| Stage | Model | Writes | Why |
|---|---|---|---|
| Plan authorship | **fable** | `playbook.md` only | Widest view, sees the campaign whole. Never code. |
| Per-task subplan | **opus** | `.playbook/T<n>.subplan.md` only | Turns large external scope into small internal scope. |
| Implementation | **sonnet** | source + `_Lessons:` | Executes a subplan that is already decided. Cheap, and it does not need to re-derive judgment. |
| Unstick | **opus** | subplan only | Re-enters on `[BLOCKED]` and *only* then. |

Cheapest model that suffices, per stage (CLAUDE.md 9). The point of the split is that
sonnet never makes an architectural call and opus never burns context on a `pytest` loop.

If the operator wants this *session* on fable too, that is a `/model` keystroke only
they can make. Say it once; do not ask twice.

## The loop

1. Main session picks the topmost `[TODO]`, flips it to `[WIP]`.
2. **Subplan (opus).** Dispatch one subagent, `model: opus`, read+write-subplan tools
   only. Its brief: the task line, its `_Files:`, its `_Verify:`, and the playbook path.
   It writes `.playbook/T<n>.subplan.md` — the internal decomposition of that one task:
   what to change in each file, in what order, and what "done" looks like. It touches
   no source.
3. **Implement (sonnet).** Dispatch a *fresh* subagent, `model: sonnet`. Its brief is
   the subplan path and nothing else — not the playbook, not the prior task's findings,
   not this session's context. That absence IS the feature.
4. It implements, runs `_Verify:`, and appends its own `_Lessons:` line under the task in
   the playbook. No run = not done (Law 7).
5. It returns a **verdict**, not a transcript: pass/fail + the one discriminating line.
6. Main session flips `[WIP]` → `[DONE]` (or `[BLOCKED]`) and moves to the next `[TODO]`.

The subplan file is scratch, not a deliverable. Delete `.playbook/T<n>.subplan.md` when
the task closes; the `_Lessons:` line is what survives. Gitignore `.playbook/`.

**Never** batch two TODOs into one subagent. **Never** carry a subagent to a second task —
a reused session is exactly the rot the ledger exists to avoid. **Never** pull the
subagent's working context back into the main session; the `_Lessons:` line is the
entire handoff, and if it is not enough, the task was scoped too big.

Independent tasks may fan out in parallel (max 4, per CLAUDE.md 12) when their
`_Files:` sets do not intersect. Intersecting sets run in sequence or in isolated
worktrees.

## Failure — stuck goes up one tier, one shot each

Sonnet stuck asks opus. Opus stuck asks fable. Fable re-plans. Nobody gets two tries at
the same wall, and nobody skips a tier.

| Tier | Gets one shot at | On failure | Writes |
|---|---|---|---|
| **sonnet** | implementing the subplan | `[BLOCKED]` + evidence → opus | source, `_Blocked:` |
| **opus** | revising the subplan around the blocker | `[BLOCKED]` + evidence → fable | subplan, `_Blocked:` |
| **fable** | re-scoping the task in the ledger | STOP, hand to the operator | `playbook.md` |

**Escalation carries evidence, not a verdict.** A tier that gets stuck appends a
`_Blocked:` line under the task before it hands up — what it tried, the exact failing
output, and what it thinks the real obstacle is:

```markdown
- [BLOCKED] T4 Retry the handshake with backoff
  _Files:_ src/net.py
  _Blocked: sonnet_ — subplan step 3 says patch `_connect`, but `_connect` is
    generated by the codegen in build.py; the edit is overwritten on every build.
    `pytest tests/test_net.py -q` → 2 failed, AssertionError: retries=0
  _Blocked: opus_ — cannot revise around this at subplan scope. The task assumes
    net.py is hand-written. That assumption belongs to the plan, not the subplan.
```

This is the whole reason the playbook is a log and not just a task list. Fable cannot
re-scope a task it only knows failed — it has to read what each tier hit and why they
could not get past it. **A `[BLOCKED]` with no `_Blocked:` evidence line is not an
escalation, it is a give-up; send it back to the tier that wrote it.**

After fable re-scopes, the task re-enters at the bottom: fresh subplan, fresh sonnet.
If it blocks a second time at fable's tier, stop and hand it to the operator — that is
`rules/orchestration.md`'s bounded re-plan law (2 rounds, never a third) applied at
task scope.

## When NOT to use this

- Fewer than 3 tasks — the ledger costs more than it saves.
- Tasks that are genuinely one edit spread across files (a rename) — that is one task.
- Exploration, where the next step depends on what the last one found. A ledger fixes
  the order up front; if the order is unknown, plan first.
