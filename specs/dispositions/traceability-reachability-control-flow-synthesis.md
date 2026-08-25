<!-- GENERATED — DO NOT EDIT — source: specs/specs.db -->
# Traceability, reachability, and control-flow synthesis

**Slug:** `traceability-reachability-control-flow-synthesis`
**Tags:** sdd,sprawl,traceability,uml,provenance,control-flow,triz,six-hats
**Created:** 2026-08-10T20:18:27+00:00

---

## Objective
Prevent sprawl and decoherence by making every production symbol reachable and traceable while keeping control flow locally understandable and avoiding documentation drift.

## TRIZ synthesis
- Segmentation: separate hard reachability/traceability gates from soft size/complexity warnings.
- Intermediary: use SpecsDB as one graph between requirements, design, code, tests, evidence, tasks, and anomalies.
- Preliminary action: declare roots, provenance IDs, and pending-task ownership before allocating code.
- Dynamization: generate or validate UML and call-path views from the graph and live code.
- Taking out: keep pending symbols outside production roots; an active task is a temporary root that expires with task closure.
- Feedback: compare differential graph and code-health metrics on every non-trivial change.

## Six Hats
- White: the current harness has mission prose but no symbol census, implementation comparison, or anomaly schema; checkbox convergence ignores code_dir.
- Red: small functions and visual paths make review safer, but excessive ceremony and wrapper chains feel harder than direct code.
- Black: fixed LOC limits can be gamed; static analyzers misclassify callbacks; hand-maintained UML and provenance can become sprawl themselves.
- Yellow: one graph enables garbage collection, change impact, live diagrams, and exact requirement-to-test evidence.
- Green: combine static reachability with declared framework roots and dynamic coverage; classify domain-work versus routing-only hops; quarantine pending code.
- Blue: SpecsDB owns identities and edges; generated projections are validated; hard gates block orphans and stale links; warnings are calibrated before promotion.

## Five ranked falsifiable hypotheses
1. A declared-root reachability graph will detect all seeded orphan production symbols while preserving registered callbacks. Falsified if any seeded orphan passes or any declared callback is blocked across the fixture battery.
2. Active-task pending roots will prevent WIP from becoming permanent dead code. Falsified if closing, dropping, or deleting the linked task does not make the pending symbol fail the census.
3. Bidirectional requirement→design→code→test edges will detect seeded semantic drift. Falsified if removing or changing any required edge still allows convergence.
4. Generated/validated Mermaid views will remain aligned with architecture and behavior. Falsified if a relevant source or graph hash changes without stale-diagram detection, or a rendered node cannot resolve to a live graph ID.
5. A soft warning at more than three consecutive routing-only/pass-through hops will identify needless indirection without penalizing legitimate layered domain work. Falsified if calibrated fixtures cannot distinguish wrapper chains and A→B→A ping-pong from controller→service→repository→gateway paths with real contracts.

## Recommended synthesis
Implement one traceability/reachability graph. Hard-fail unreachable or untraceable production symbols, expired pending links, duplicate active implementations, stale UML/provenance, unexplained cycles, duplicated policy, and architecture violations. Warn on LOC, methods per class, complexity, nesting, and more than three routing-only hops; calibrate warnings against repository fixtures. Prefer guard clauses for preconditions, decision tables or match/switch for closed homogeneous variants, and Strategy/State/polymorphism only when the behavior axis recurs. Require profiler evidence for CPU or latency claims.
