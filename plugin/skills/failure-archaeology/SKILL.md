---
name: failure-archaeology
description: >
  Failure-loop recovery protocol. Activate after the second identical failure,
  when a previously working mechanism regresses, or when evidence contradicts
  a prior successful run. Prevents blind retries and wasted compute.
---

# Failure-Loop Archaeology Gate

## Trigger Conditions
- Same test/command/error fails twice without new discriminating evidence
- A change regresses a mechanism that previously worked
- Current observations contradict a prior successful run
- About to modify a test harness or control plane that has prior successful use

## Mandatory Sequence (FREEZE first)

1. **Current state**: repo root, branch, status, relevant diff, exact failing artifact
2. **Commit history**: path-scoped `git log`, pickaxe for the changed behavior
3. **Prior evidence**: successful run artifacts, logs, exact commands/hashes
4. **Repository docs**: AGENTS.md, active plans, lessons_learned
5. **Memory search**: `search_memory("<concrete failure mechanism>")`
6. **Diff against last good**: identify earliest behavioral divergence
7. **Restore before innovate**: smallest restoration of proven mechanism first

## Required Checkpoint
```
Failure-loop gate: ARCHAEOLOGY COMPLETE
last-good=<commit/run/artifact>
divergence=<first changed behavior>
next-test=<one discriminating test>
matched-control=<control>
```

## Prohibitions
- No third attempt without new evidence
- No rewriting a proven harness while debugging its payload
- No adding retries/fallbacks before isolating the regression
- No proceeding downstream while upstream gate is broken
