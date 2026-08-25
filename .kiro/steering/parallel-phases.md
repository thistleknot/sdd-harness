---
inclusion: always
---

# Parallel Phases

Before executing any multi-task plan, decompose it into dependency phases and parallelize within each phase.

## The Rule

1. **Group tasks by dependency.** Tasks that share no inputs or outputs belong in the same phase. Tasks that consume another task's output belong in a later phase.
2. **Execute all tasks within a phase in parallel** — use sub-agents, concurrent tool calls, or batched operations. Never serialize independent work.
3. **Gate phase transitions.** Phase N+1 does not start until every task in phase N passes its verification. A single failure in phase N blocks the entire next phase.
4. **State the plan before executing.** Before any implementation begins, emit the phase structure:

```
Phase 1 (parallel): [task A, task B, task C]  — no dependencies
Phase 2 (parallel): [task D, task E]          — depends on A, B
Phase 3 (serial):   [task F]                  — depends on D, E
```

## When to apply

- Any time you are about to work through more than 2 tasks sequentially
- Any time you are about to ask the user to run something (ask: can I batch this with other independent work first?)
- Any time you identify a task has no dependency on the current in-progress work

## How to identify phases

- Draw the dependency DAG (even mentally)
- Tasks with no incoming edges from unfinished work = current phase
- Tasks whose only dependencies are already-done tasks = current phase
- Tasks that depend on in-progress work = next phase
- Tasks that depend on next-phase work = phase after that

## Anti-patterns

- Serializing independent tasks because they were listed in order
- Starting the next task before verifying the previous one passed (violates the dependency gate)
- Asking the user to run/verify one thing when three independent things could be batched
- Implementing tasks depth-first through the DAG instead of breadth-first by phase
- Treating "I'll do them in parallel" as implicit — state the phase structure explicitly so the user can see the plan and correct it

## Artifact Inventory Between Phases

Each phase boundary MUST declare an explicit artifact manifest: the files and state that phase N produced and phase N+1 consumes. This is the interface contract between phases.

**Before starting phase N+1, emit:**

```
Phase N outputs (checkpoint):
  Files created/modified: [path1, path2, ...]
  State changes: [DB rows added, services started, configs updated, ...]
  Verification: [test results, health checks, hash comparisons, ...]

Phase N+1 inputs (consumed):
  Reads: [which of the above it needs]
  Assumes: [what state must hold]
```

**Rules:**
- Every file produced in a phase MUST be written to disk before the phase is declared complete — no in-memory-only artifacts survive phase boundaries
- Every phase transition MUST log what was produced and what was consumed — this is the checkpoint that enables resume after crash
- If a phase N output is missing or stale when phase N+1 starts, the dependency gate blocks execution
- Artifacts that are not consumed by any subsequent phase are either terminal outputs or sprawl candidates — flag them

**Why:**
- A crash between phases loses nothing — disk state is the checkpoint
- A new session can resume from the last completed phase by reading the artifact manifest
- Cross-harness handoff has a concrete inventory to transfer, not implicit assumptions
- The conversation store captures the manifest as a volley, making it retrievable

## Script Boundaries

Each script is one node: independently runnable, testable, resumable from disk.

**Node complexity cap:** max 4 phases per script. Beyond this, split the script.

**Critical path depth cap:** max 7 sequential dependencies in any pipeline. Beyond this, decompose into independent sub-pipelines sharing artifacts on disk. This follows ETL/CI consensus: deep serial chains are expensive to debug and resume.

**Width is unbounded:** parallelize freely within a phase. Wide is cheap; deep is expensive.

If a pipeline has more than 4 phases, split into separate top-level scripts — one per phase or logical group. Each script:
- Reads its inputs from disk (prior phase's checkpoint files)
- Writes its outputs to disk before exiting
- Runs its own verification (tests, health checks, assertions)
- Exits non-zero on failure
- Can be re-run independently without re-running prior phases

Compose with a thin orchestrator that pipes scripts together:
```
phase1.py && phase2.py && phase3.py
```

Or a manifest that declares the DAG:
```
phases:
  - script: phase1.py
    outputs: [specs/policy_snapshot.json]
    verify: pytest specs/test_policy_contracts.py
  - script: phase2.py
    inputs: [specs/policy_snapshot.json]
    outputs: [specs/validators/*.py]
    verify: pytest specs/validators/test_validators.py
```

**Why this is QA:** each script is a unit-testable, independently deployable artifact. Failures are isolated. Resume costs nothing. Observation is free (check the outputs dir). Cross-session handoff is automatic (disk state IS the handoff).

## Composition with dependency-gate.md

The dependency gate fires per-task at phase boundaries. This steering fires per-plan at the structural level. They compose:
- parallel-phases.md decides WHAT runs together and WHAT passes between phases
- dependency-gate.md decides WHETHER each task's prerequisites are met before it starts
