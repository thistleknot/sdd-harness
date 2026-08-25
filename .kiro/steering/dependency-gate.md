---
inclusion: always
---

# Dependency Gate

Before executing any task, verify its upstream dependencies are met. A task executed on unverified upstream assumptions is a wasted run — this is decoherence at the execution layer.

## The Rule

1. **Before starting a task**, identify every upstream dependency (prior task output, running service, schema state, file existence, test pass).
2. **Probe each dependency** — don't assume it's met because it was met last session or because a prior task was marked done.
3. **If any dependency is unmet**, stop and resolve it first. Do not proceed downstream hoping it will work out.
4. **If you cannot resolve it**, surface it as a blocker immediately — don't discover it 30 minutes into a failed run.

## What counts as a dependency

- A service that must be healthy (use `ensure_services.ps1` or probe `/health` directly)
- A prior task whose output this task consumes (check the artifact exists and is current)
- A schema or DB state that must be present (verify table/column existence)
- A file that must exist at a path (verify before importing/reading)
- A test suite that must pass before building on top of it
- A config that must be in a specific state (verify the value, don't assume)

## How to apply

- At session start: `ensure_services.ps1` handles service dependencies automatically via the SessionStart hook
- Before each implementation task: check `specs list_tasks` for the parent task's status; if parent is not `done`, do not start the child
- Before any test run: verify the module under test imports cleanly
- Before any multi-step plan: state the dependency chain explicitly, then execute in topological order

## The failure mode this prevents

Executing task N while task N-1's output is broken, stale, or missing. The run completes, looks like progress, and is then invalidated when the upstream defect is discovered. Every downstream minute spent was waste. This is the same pattern as debugging a symptom while the root cause is upstream — applied to task sequencing instead of code.

## Anti-patterns

- "I'll start here and check upstream later" — you won't, and the run is wasted
- "It was working last session" — sessions are discontinuous; probe, don't assume
- "The task is marked done in specs" — the spec says done, but is the artifact actually there and current?
- Starting parallel work on tasks that share a dependency without verifying the dependency first
- Branching into new specification work when the prior implementation task is still open
