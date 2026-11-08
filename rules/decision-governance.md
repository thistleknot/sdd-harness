# Decision Governance Rules

Source: `docs/references/ddse.md` (DDSE) + `docs/references/ddse and other sdd resources.md`
(Kiro design layer vs AIUP entity model). Governs: constitution Article XVI, sw-design
Stage 0. These rules make decisions the system of record; specs and code are derived.

## 1. Typed TDR hierarchy

Every durable choice is a typed Technical Decision Record (TDR), in-repo, cross-linked
to the work and code it governs:

| Type | Scope | Changes |
|---|---|---|
| MDD | Mission — what the system is for | rarely |
| ADR | Architecture — structure, components, technology | on a redesign |
| CDR | Contract — an API/interface agreement | with versioning |
| EDR | Entity/Data — schema, data model, persistence | with the data model |
| IDR | Implementation — local, changeable | per task |

A choice that fits no type is either not a decision (record it as a note) or a new
type (propose it; do not invent a one-off).

## 2. AI-Context block (required)

Every TDR carries a machine-parsable AI-Context block so agents follow the constraint,
not just the prose:

```
AI-Context:
  Constraints: <limits the implementer must not cross>
  Patterns: <incumbent patterns to reuse>
  Anti-patterns: <rejected approaches this decision forbids>
  Verification commands: <commands proving conformance>
```

A TDR without an AI-Context block is incomplete and may not be `Accepted`.

## 3. Lifecycle

`Proposed → Accepted → Deprecated → Superseded-by:<id>`.

- Code and specs may cite only `Accepted` decisions.
- A `Deprecated`/`Superseded` decision names its replacement; the old record is kept,
  never deleted (Decision Memory — the rationale lineage survives).
- Re-litigating an `Accepted` decision requires superseding it, not re-debating it.

## 4. CDR contract

A CDR carries a required **contract** section: the API/interface agreement (endpoints,
request/response schemas, auth, error codes). The contract section is the source of
truth; contract tests are required (constitution Article V). Automated mock-server /
type-generation tooling is a later increment — the contract section is the value.

## 5. Decision→code traceability

- Code annotations reference the decision ids they realise.
- A code path that contradicts an `Accepted` decision is a spec violation, not a refactor.
- A decision with no citing artifact is either dead (deprecate it) or unenforced
  (find the gap).

## 6. Design layer vs entity model (Kiro vs AIUP)

- The **design layer** (design.md) is the whole-system blueprint: architecture, tech
  stacks, API contracts, component diagrams, sequence flows.
- The **entity model** is the data structure at rest: domain entities, data types,
  validation rules, structural relationships (Mermaid.js ER). It is nested inside the
  design layer as the data-architecture section, not a peer.
- A design that is only an entity model is missing the system; an entity model that
  is a peer of the design is a layering error.

## 7. Enforcement

- `spec_gate.py` (existing) gates spec→code.
- A `decision_gate` check (later increment) gates decision→spec and decision→code:
  it verifies cited decisions are `Accepted`, carry an AI-Context block, and that
  `CDR` contracts have contract tests.
- Until the `decision_gate` lands, the rules above are enforced by review (the
  sw-design Stage 0 gate 0→1).
