<!-- GENERATED — DO NOT EDIT — source: specs/specs.db -->
# SDD harness mission coverage audit

**Slug:** `sdd-mission-coverage-audit`
**Tags:** sdd,sprawl,decoherence,karp,audit
**Created:** 2026-08-10T20:07:05+00:00

---

## Verdict
NO — the harness states the right mission but does not yet prove or enforce it.

## Problem
Determine whether the canonical harness specification and implementation satisfy the implied intentions behind SDD: prevent artifact sprawl, prevent trajectory decoherence, and prevent mutable-growing-Karp.

## Observed coverage
- `README.md` explicitly defines all three failure modes.
- `constitution.md` provides incumbent search, diff review, root-first debugging, and verification rules.
- Lifecycle hooks preserve some cross-session context.
- SpecsDB provides a canonical reference trajectory.

## Discriminating gaps
### Sprawl
No implementation inventories allocations or detects untracked, duplicate, superseded, and unreferenced artifacts. Gate A/B/C statements are not persisted as evidence. No orphan-count baseline or threshold exists.

### Decoherence
`hooks/convergence.py` ignores `code_dir`; it extracts text criteria and counts task checkboxes. It does not map implementation behavior to criteria, compare current state with an approved snapshot, separate semantic/coordination/behavioral drift, or persist gaps through SpecsDB.

### Karp
No event record requires raw anomaly, explanation, falsification condition, exact check, result, and disposition before continuation. The retrieve-skills incident demonstrated the gap: `/health` passed while Kiro's registered client failed.

### Canonical integrity
The canonical DB included unrelated LoRA and game-documentation rows. Root spec files conflict with rendered DB views and contain stale skill-store, model-provider, harness-count, and task-status claims. Generated views lack a do-not-edit banner.

### Multi-session architecture
Todo remains a stdio server over shared SQLite, contrary to the persistent HTTP rule.

## Decisions recorded
- Requirements #3-#9 operationalize mission coverage, sprawl census, three drift dimensions, anomaly evidence, canonical integrity, shared-state HTTP safety, and the four-harness capability matrix.
- Decision #2 makes these independent evidence-bearing convergence gates.
- Tasks #11-#18 are the bounded remediation workstream.

## What would change the verdict
The verdict becomes YES only after tasks #12-#18 produce passing evidence: orphan delta <= 0, zero drift counts for all MUST criteria, complete checked anomaly records, one coherent canonical spec, no shared-SQLite stdio service, and a four-harness result matrix distinguishing native and advisory enforcement.
