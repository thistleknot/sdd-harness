# Constitution — Cross-Harness SDD

Immutable principles governing how specifications become code. These are not
guidelines — they are gates. The spec_gate.py PreToolUse hook enforces Phase -1
compliance before allowing file mutations.

Version: 1.0
Adopted: 2026-08-06

---

## Article I: Spec-First Imperative

No implementation code shall be written before:
1. A governing spec exists (requirements with acceptance criteria)
2. The spec has been reviewed (no unresolved `[NEEDS CLARIFICATION]` markers)
3. A design exists (structural + behavioral layers)
4. Tasks exist (numbered, with dependencies)

**Enforcement:** `spec_gate.py` denies Edit/Write/MultiEdit until the active spec
reaches an approved `implement` phase. Repos without `.spec/` are ungated.

**Exception:** Mechanical edits (typos, formatting, semantically neutral renames)
skip this gate with explicit one-line justification.

---

## Article II: Simplicity Gate

Every implementation must pass the simplicity check before proceeding:

- [ ] Maximum 3 new files for a single feature (justify more)
- [ ] No future-proofing — solve the current problem only
- [ ] No speculative abstractions — if one function and one call site solve it, stop
- [ ] If a pattern isn't needed yet, don't introduce it

**Enforcement:** Phase -1 Gate checklist in design.md. Agent must confirm before
writing code.

---

## Article III: Anti-Abstraction Gate

Use frameworks and libraries directly. Do not wrap them unless the wrapper
eliminates a measured, repeated failure mode.

- [ ] Using the framework's API directly? (not wrapping it)
- [ ] Single model representation? (not duplicating across layers)
- [ ] No "just in case" interfaces — add when the second consumer exists
- [ ] If extending an incumbent, the extension lands INSIDE it (not beside it)

**Enforcement:** Anti-sprawl Gate A (search for incumbent before creating) +
Gate B (collapse pass before declaring done).

---

## Article IV: Test-First Imperative

No implementation shall ship without verification:

1. Acceptance criteria from the spec are testable assertions
2. Tests run and pass before declaring done
3. The self-review hook catches: TODOs, placeholders, mocks, empty bodies
4. Scale: debug 5→10→20→40→80. Validate 1→10→20→100→200→production.

**Exception:** Exploratory/throwaway code that will not be committed. Say so
explicitly when invoking this exception.

---

## Article V: Integration-First Testing

Prefer real environments over mocks:

- [ ] Real database over in-memory stubs where feasible
- [ ] Actual service calls over hand-rolled fakes (stub only at network boundary)
- [ ] Contract tests mandatory before implementation
- [ ] A single passing case against a stochastic component is noise, not a gate — minimum 3 varied inputs

---

## Article VI: Root-First Isolation

Walk backward to the earliest broken link. Fix that. Nothing downstream is worth
touching until upstream is confirmed clean.

- A persisted artifact existing is not proof the stage that wrote it finished
- Check a stage's COMPLETE output, not the one signal you were staring at
- If the same class of error repeats, stop patching and revisit the approach

---

## Article VII: Bounded Execution

Every test carries an ETA. Say "ain't nobody got time for that" before quoting
any ETA over 15 minutes.

- < 15 min per test, ≤ 3 stacked tests before disposition
- Reduce sample, epochs, scope — whatever it takes to hit the bound
- Hour-plus runs are a design failure
- Parallelize anything non-sequential

---

## Article VIII: Change Discipline

- Touch only what the change requires. Clean up only your own mess.
- Whole functions, never snippets. One contiguous block per instruction set.
- No temporal or subjective names (`_v2`, `_new`, `optimized`, `enhanced`)
- Remove dead code first, add features second
- Anti-sprawl gates A + B + C on every code task (see AGENTS.md)

---

## Article IX: Memory at Decision Time

Update documentation BEFORE code changes. The spec changes first; the code
follows. If behavior changed during delivery, reconcile the spec afterward.

- Lessons learned: state + action + observed outcome → the law it implies
- A pattern earns promotion to durable rule after 3 independent reuses
- Current disposition on top of every living document; superseded material spilled to supporting file

---

## Phase -1 Gates (Pre-Implementation Checklist)

Before any file mutations, the agent MUST confirm:

### Gate 1: Spec Completeness
- [ ] No `[NEEDS CLARIFICATION]` markers remain
- [ ] Requirements are testable and unambiguous
- [ ] Acceptance criteria are measurable
- [ ] Scope boundary stated (what's IN, what's explicitly OUT)

### Gate 2: Simplicity (Article II)
- [ ] ≤ 3 new files for this feature?
- [ ] No future-proofing?
- [ ] No speculative abstractions?

### Gate 3: Anti-Abstraction (Article III)
- [ ] Using framework directly?
- [ ] Single model representation?
- [ ] No wrapper without measured justification?

### Gate 4: Incumbent Search (Anti-Sprawl Gate A)
- [ ] Searched for existing code that does this?
- [ ] If found → extending it, not duplicating?
- [ ] If not found → stated "no incumbent found"?

### Gate 5: Test Strategy (Articles IV + V)
- [ ] Acceptance criteria mapped to test assertions?
- [ ] Integration-first approach where feasible?
- [ ] Minimum 3 varied inputs for non-deterministic components?

---

## Amendment Process

Modifications to this constitution require:
1. Explicit documentation of the rationale for change
2. Evidence from ≥ 2 independent cases showing the current article fails
3. The amendment names what it supersedes and why
4. Date stamped, appended to the end of this file

No amendments yet.
