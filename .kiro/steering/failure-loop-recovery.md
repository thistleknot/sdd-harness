---
inclusion: always
---

# Failure-Loop Archaeology Gate

This is a cross-harness execution gate. It supplements Constitution Articles VI, VII, and IX.

## Trigger

Enter the gate after the second materially identical failure, whenever a previously successful mechanism regresses, when current evidence contradicts a prior run, or when the operator says the behavior was already solved or proven.

## Gate

Before any third attempt or further mutation:

1. Freeze retries, edits, instrumentation, fallbacks, and new abstractions.
2. Identify the correct repository root, branch, worktree status, and relevant diff.
3. Recover the last known-good implementation with path-scoped git log, pickaxe history, and `git show`.
4. Inspect prior successful artifacts and their exact commands, parameters, hashes, and environment.
5. Read repository steering, `AGENTS.md`, `HARNESS.md`, active specs/plans, progress, and lessons learned.
6. Query memory-bank, skill retrieval, failure registry, and dispositions using the concrete failing mechanism.
7. Compare current state to last good and name the earliest behavioral divergence.
8. Restore the proven mechanism before proposing a replacement.
9. Run one bounded discriminating test with a matched control.

Required checkpoint:

`Failure-loop gate: ARCHAEOLOGY COMPLETE — last-good=<commit/run/artifact>; divergence=<first changed behavior>; next-test=<one discriminating test>; matched-control=<control>`

If no incumbent exists, the checkpoint must say `no incumbent found` and enumerate the searched sources.

## Denials

Deny or halt work that:

- repeats a failed command/test without new discriminating evidence;
- modifies a proven harness while debugging its payload;
- labels behavior flaky before historical comparison;
- adds retries, fallbacks, or instrumentation before isolating the regression;
- proceeds downstream while an upstream setup gate is broken;
- attempts to end the task with an unresolved repeated-failure loop.

## Learning Contract

Capture the final problem, root cause, last-good reference, divergence, restoration, validation, and dead ends. An insight is not a rule until the evidence chain is preserved.