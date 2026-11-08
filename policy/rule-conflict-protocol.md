# SDD Conflict Resolution — policy/rule-conflict-protocol.md

Repo: `C:\Users\user\.harness` · Mode: policy

## Objective

Define the protocol for resolving spec contradictions: when a spec review or lint finds two rules/specs contradicting, the protocol describes how the contradiction is recorded, how it is resolved, and what authority decides.

## When a contradiction exists

A contradiction exists when two or more rules, specs, or conventions:

1. Assert mutually exclusive behaviors for the same condition, OR
2. Assert the same behavior for different conditions, OR
3. Assert incompatible data formats or constraints, OR
4. Assert incompatible control flow paths.

**Examples:**

- Rule A says "The user must be logged in"; Rule B says "The user may be anonymous".
- Spec X says "The API returns JSON"; Spec Y says "The API returns XML".
- Convention A says "All modules use SQLite"; Convention B says "All modules use PostgreSQL".
- Spec Z says "The table has a `created_at` column"; Spec W says "The table has no `created_at` column".

## Recording the contradiction

When a contradiction is discovered, an entry is appended to the repo's `docs/rule-conflict-log.md` file. The entry must include:

1. **The two conflicting ids** (e.g., `RULE-001` and `RULE-002`, or `SPEC-001` and `SPEC-002`).
2. **The discriminating evidence** (the specific code path, condition, or behavior that shows the contradiction).
3. **The deciding authority** (product owner for requirements, operator for constitution/policy).
4. **The resolution state** (OPEN, RESOLVED-BY-SPEC-CHANGE, RESOLVED-BY-RULE-CHANGE, or WITHDRAWN).

**Example entry:**

```
| 2026-11-07 | spec-review | RULE-001 / RULE-002 | OPEN | RULE-001 requires user login; RULE-002 allows anonymous access | product owner |
```

## Resolution states

### OPEN

The contradiction has been identified but not yet resolved. The entry remains OPEN until the deciding authority makes a decision.

**When an entry is OPEN:**

- The contradiction is known.
- The deciding authority has not made a decision.
- The implement phase is blocked for any spec that has acceptance criteria affected by the contradiction.

### RESOLVED-BY-SPEC-CHANGE

The contradiction was resolved by changing one or more specs. The spec change removed the contradiction.

**When an entry is RESOLVED-BY-SPEC-CHANGE:**

- The spec change has been made and merged.
- The contradiction no longer exists.
- The implementing team can proceed with the implement phase.

### RESOLVED-BY-RULE-CHANGE

The contradiction was resolved by changing one or more rules. The rule change removed the contradiction.

**When an entry is RESOLVED-BY-RULE-CHANGE:**

- The rule change has been made and merged.
- The contradiction no longer exists.
- The implementing team can proceed with the implement phase.

### WITHDRAWN

The contradiction was withdrawn or deemed no longer applicable. The entry is archived but not deleted.

**When an entry is WITHDRAWN:**

- The contradiction no longer applies.
- The entry remains in the log for historical record.
- The deciding authority has documented the reason for withdrawal.

## Blocking rule

A contradiction touching the active spec's acceptance criteria holds the implement phase until an entry leaves OPEN.

**Blocking rule:** If a spec's acceptance criteria is affected by an OPEN contradiction, the implement phase is blocked. No code may be written for the spec until the contradiction is resolved (i.e., the entry leaves the OPEN state).

**Blocking rule enforcement:**

1. The `file_manifest.py` hook checks the `rule-conflict-log.md` file before allowing writes to the active spec.
2. If an OPEN contradiction is found that affects the active spec's acceptance criteria, the hook denies the write.
3. The hook returns a clear error message: "Implement phase blocked: OPEN contradiction in rule-conflict-log.md"
4. The operator must resolve the contradiction before the implement phase can proceed.

## The deciding authority

| Domain | Authority | Reason |
|---|---|---|
| Requirements | Product owner | The product owner owns the requirements and the acceptance criteria. |
| Constitution / Policy | Operator | The operator owns the constitution and policy. |
| Architecture | Operator | The operator owns the architecture decisions and the system design. |

**Decision process:**

1. The deciding authority reviews the contradiction and the discriminating evidence.
2. The deciding authority chooses one of the four resolution states.
3. The deciding authority documents the decision in the `rule-conflict-log.md` entry.
4. The deciding authority updates the entry to leave the OPEN state.

**Example decision:**

```
| 2026-11-07 | spec-review | RULE-001 / RULE-002 | RESOLVED-BY-SPEC-CHANGE | RULE-001 requires user login; RULE-002 allows anonymous access | product owner |
```

In this example, the product owner decided that RULE-001 should be updated to allow anonymous access, resolving the contradiction. The entry is updated to RESOLVED-BY-SPEC-CHANGE.

## INTAKE.md line format

Every entry in the repo's `INTAKE.md` must follow this format:

```
| YYYY-MM-DD | source (issue/PR/operator) | lane a-e | one-line scope |
```

**Example entries:**

```
| 2026-11-07 | operator request (SDD integration) | a | fix typo in README.md |
| 2026-11-07 | operator request (SDD integration) | d | integrate SDD/DDSE material into sw-design chain, task #94 |
```

## Rule

Every entry appends, never edits history.

The `INTAKE.md` file must be append-only. No entry may edit an existing entry. New entries must be added at the end of the file. The file must never be edited to change an existing entry.

## Definition of done

- Every contradiction has an entry in the `rule-conflict-log.md` file.
- The entry includes the two conflicting ids, the discriminating evidence, the deciding authority, and the resolution state.
- The implement phase is blocked for specs affected by OPEN contradictions.
- The deciding authority documents the decision in the `rule-conflict-log.md` entry.
- The `rule-conflict-protocol.md` policy is enforced by the `file_manifest.py` hook.

---

*Generated by SDD harness — DO NOT EDIT.*
