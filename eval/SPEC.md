# 10-Edit Coherence Eval — Spec

## Objective

Measure whether harness hooks (self-review, test-gen, session-handoff) reduce
code quality drift when an LLM makes 10 sequential edits to a small module.

## Arms

| Arm | Env | Description |
|-----|-----|-------------|
| A (hooks-on) | `HARNESS_HOOKS_ENABLED=1` | Full hook suite active |
| B (hooks-off) | `HARNESS_HOOKS_ENABLED=0` | All hooks disabled via kill-switch |

Both arms:
- Start from identical git snapshot (the seed commit)
- Use the same 10 prompts in the same order
- Use `opencode run` headless mode (local ollama models)
- Run in isolated git worktrees to avoid cross-contamination

## Target Module

A **task queue** library (`taskq/`) — small, self-contained, with natural surface
for incremental feature additions that can accumulate tech debt if unchecked.

### Seed State (what both arms start from)

```
taskq/
├── __init__.py        # exports
├── queue.py           # TaskQueue class: add, pop, peek, size
├── task.py            # Task dataclass: id, name, priority, status, created_at
├── worker.py          # Worker class: run loop, process one task
└── tests/
    └── test_queue.py  # 3 basic tests: add/pop/empty
```

~80 LOC total. Deliberately minimal so drift is measurable against a clear spec.

## 10 Edit Prompts (sequential)

Each prompt is given to opencode in the context of the taskq/ directory.

| # | Prompt | What it exercises |
|---|--------|-------------------|
| 1 | "Add a `retry_count` field to Task and make Worker retry failed tasks up to 3 times before marking them dead" | Field addition + logic change |
| 2 | "Add a `delay` method to TaskQueue that moves a task to the back with a scheduled_at timestamp" | New method + datetime handling |
| 3 | "Implement task priorities: Worker should always process highest-priority tasks first" | Reordering logic, potential queue refactor |
| 4 | "Add a `cancel` method that marks a task as cancelled and skips it during processing" | State machine addition |
| 5 | "Add an `on_complete` callback hook to Worker that fires after each task finishes" | Callback pattern |
| 6 | "Implement a `stats()` method on TaskQueue returning counts by status (pending/running/done/dead/cancelled)" | Aggregation, depends on prior state additions |
| 7 | "Add a `max_concurrency` parameter to Worker that limits how many tasks run in parallel using asyncio" | Concurrency refactor (sync → async) |
| 8 | "Add JSON serialization: TaskQueue.to_json() and TaskQueue.from_json() for persistence" | Serialization, must handle all fields from edits 1-6 |
| 9 | "Add a CLI entry point (`python -m taskq`) that starts a worker, accepts tasks via stdin JSON" | New module, integration of prior features |
| 10 | "Refactor: extract task state transitions into a TaskStateMachine class and use it in Worker" | Structural refactor touching multiple files |

## Metrics (scored after each edit)

### Quantitative (automated)

| Metric | How | Weight |
|--------|-----|--------|
| **LOC** | `wc -l` on all .py files | Informational (lower is better, all else equal) |
| **Duplication** | `pylint --disable=all --enable=duplicate-code` or custom AST check | 0.2 |
| **Dead code** | `vulture taskq/` — unused functions/imports | 0.2 |
| **Type errors** | `pyright taskq/` or `mypy taskq/` — static type violations | 0.2 |
| **Test pass rate** | `pytest taskq/tests/ --tb=no -q` | 0.2 |
| **Import graph coherence** | Custom: circular imports, orphan modules | 0.1 |
| **Lint score** | `ruff check taskq/` — style + correctness issues | 0.1 |

### Qualitative (manual spot-check after full run)

- Does the code read as if one person wrote it? (naming consistency)
- Are prior features preserved or silently broken?
- Is the state machine coherent across files?

## Scoring

Each automated metric is normalized 0-1 (higher = better quality).
Composite score = weighted sum per edit.
Final comparison: plot composite score over 10 edits for both arms.

**Hypothesis:** Arm A (hooks-on) will show slower drift (higher composite at edit 10)
because self-review catches regressions and test-gen maintains coverage.

**Falsification condition:** If Arm B's composite at edit 10 is within 0.05 of Arm A,
hooks add friction without measurable benefit for this workload.

## Runner Design

```
eval/
├── SPEC.md            # this file
├── seed/              # the initial taskq/ module (committed)
├── prompts.json       # the 10 prompts as a JSON array
├── run_eval.py        # orchestrator: worktree setup, opencode invocation, git snapshot
├── score.py           # scorer: runs all metrics on each snapshot
└── results/           # output: scores per arm per edit, final comparison
```

## Execution Plan

1. Create seed module, commit to a branch `eval/seed`
2. For each arm:
   a. Create worktree from `eval/seed`
   b. Loop 10 prompts: `opencode run "<prompt>" --pure` in the worktree
   c. After each: `git add -A && git commit -m "edit-N"` to snapshot
   d. Run scorer on the snapshot
3. Aggregate and compare

## Constraints

- Each `opencode run` gets max 5 minutes (timeout and mark as failed if exceeded)
- `--pure` flag to avoid external plugins that might confuse the comparison
- Worktrees are disposable; delete after scoring
- Git log preserved for audit

## Open Questions

None. The design is self-contained.
