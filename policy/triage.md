# SDD Triage — policy/triage.md

Repo: `C:\Users\user\.harness` · Mode: policy

## Objective

Define the feeder gate for the SDD (Spec-Driven Development) chain: classify incoming change requests into five lanes (a–e) and route them to the appropriate process. Every request that enters the SDD chain carries a lane assignment that determines how it is processed, what documentation is required, and what authority approves it.

## The five lanes

| Lane | When it applies | Process |
|---|---|---|
| **a** | mechanical edit (typo/format/semantically-neutral rename) | skip spec chain, one-line justification |
| **b** | small bug with obvious fix | ticket, fix, test |
| **c** | feature that does NOT touch the data model or a public contract (size is advisory, not the trigger) | speckit flow (specify, plan, tasks, implement, review) |
| **d** | any change that touches the data model OR a public/API contract (observable trigger; points no longer gate it) | full sw-design 6-stage chain |
| **e** | greenfield module | full chain + typed decision records + spec-as-source marking on generated code |

### Lane definitions

**a — mechanical edit**

- **What:** A change that is purely mechanical: a typo, a formatting fix, or a semantically neutral rename (e.g., `foo` → `bar` with no domain shift).
- **When:** The change does not alter requirements, control flow, data models, or observable behavior.
- **Process:**
  1. The operator writes a one-line justification in the repo's `INTAKE.md`.
  2. The change is made directly to the source file.
  3. The change is reviewed by the operator via the `review_changes.py` hook.
  4. The change is committed; no spec, no plan, no design is required.
- **Authority:** Operator (the person who wrote the one-line justification).
- **Spec chain:** None. The change is not recorded in the specs DB.

**b — small bug with obvious fix**

- **What:** A bug that is localized, its root cause is evident from the code, and the fix is straightforward (no new features, no data model changes, no multi-file complexity).
- **When:** The bug is reported in a ticket (GitHub issue, Jira, etc.), the fix is a single or two-file change, and the operator judges the fix to be "obvious".
- **Process:**
  1. The operator creates a ticket referencing the bug.
  2. The operator writes a one-line scope in `INTAKE.md` and assigns lane `b`.
  3. The fix is implemented directly in the source files.
  4. The operator writes a one-line test fix in `INTAKE.md` and assigns lane `b`.
  5. The operator commits the fix and the test.
- **Authority:** Operator.
- **Spec chain:** None. The fix is not recorded in the specs DB.

**c — feature under ~3 story points**

- **What:** A relatively small feature (roughly 1–3 story points) that does not touch the data model.
- **When:** The feature is scoped in a ticket, the operator estimates it as ≤3 story points, and the feature does not require data model changes.
- **Process:**
  1. The operator specifies the feature in a ticket.
  2. The operator writes a speckit flow entry in `INTAKE.md`:
     
     `| YYYY-MM-DD | source | c | specify, plan, tasks, implement, review |`
     
     with the five stages spelled out: specify, plan, tasks, implement, review.
  3. The operator creates a spec file (`docs/feature-<id>.md`) that contains the feature requirements.
  4. The operator creates a plan file (`docs/plan-<id>.md`) that contains the execution plan.
  5. The operator creates a tasks file (`docs/tasks-<id>.md`) that lists the implementation tasks.
  6. The operator implements the feature.
  7. The operator reviews the feature via the `review_changes.py` hook.
  8. The operator commits the feature.
- **Authority:** Operator.
- **Spec chain:** The spec is recorded in the specs DB, but the full sw-design chain is not required.

**d — feature ~3 points or above, or any change touching the data model**

- **What:** A feature of moderate to large scope (≥3 story points) or any change that touches the data model (tables, columns, constraints, relationships).
- **When:** The feature is scoped in a ticket, the operator estimates it as ≥3 story points, or the feature requires data model changes.
- **Process:**
  1. The operator specifies the feature in a ticket.
  2. The operator writes a full sw-design 6-stage entry in `INTAKE.md`:
     
     `| YYYY-MM-DD | source | d | specify, plan, sw-design, impl, review, deploy |`
     
     with the six stages spelled out: specify, plan, sw-design, impl, review, deploy.
  3. The operator creates a spec file (`docs/feature-<id>.md`) that contains the feature requirements.
  4. The operator creates a plan file (`docs/plan-<id>.md`) that contains the execution plan.
  5. The operator creates a sw-design file (`docs/sw-design-<id>.md`) that contains the full system design (architecture, data model, interfaces, deployment plan, risk assessment, etc.).
  6. The operator implements the feature.
  7. The operator reviews the feature via the `review_changes.py` hook.
  8. The operator deploys the feature (or records the deployment plan in the sw-design).
- **Authority:** Operator (for features ≤3 story points) or product owner (for features ≥3 story points or data model changes).
- **Spec chain:** The spec is recorded in the specs DB, and the full sw-design chain is required.

**e — greenfield module**

- **What:** A new module that has no prior code, no prior spec, and no prior design. This is a completely new capability.
- **When:** The module is greenfield: no existing code, no requirements, no architecture.
- **Process:**
  1. The operator specifies the module in a ticket.
  2. The operator writes a full chain entry in `INTAKE.md`:
     
     `| YYYY-MM-DD | source | e | specify, plan, sw-design, impl, review, deploy, typed-decision |`
     
     with the seven stages spelled out: specify, plan, sw-design, impl, review, deploy, typed-decision.
  3. The operator creates a spec file (`docs/module-<id>.md`) that contains the module requirements.
  4. The operator creates a plan file (`docs/plan-<id>.md`) that contains the execution plan.
  5. The operator creates a sw-design file (`docs/sw-design-<id>.md`) that contains the full system design.
  6. The operator creates typed decision records (`docs/decision-<id>-typed.md`) that document architectural decisions, trade-offs, and alternatives considered.
  7. The operator implements the module.
  8. The operator reviews the module via the `review_changes.py` hook.
  9. The operator deploys the module (or records the deployment plan in the sw-design).
  10. The operator marks generated code with `GENERATED, DO NOT EDIT` (see below).
- **Authority:** Operator (for modules ≤3 story points) or product owner (for modules ≥3 story points or data model changes).
- **Spec chain:** The spec is recorded in the specs DB, and the full sw-design chain is required.

### Typed decision records

For lane `e` (greenfield module), the operator must create typed decision records. Each record documents an architectural decision, the alternatives considered, the trade-offs, and the rationale. Each record is written in Markdown with a YAML frontmatter that declares the decision type, the decision id, the date, the author, and the category.

**Example decision record format:**

```
---
type: decision
id: DEC-001
date: 2026-11-07
author: Operator Name
category: architecture
---

## Decision: Use SQLite for the module's data store

### Context

[What problem is this decision solving?]

### Decision

[What was decided?]

### Alternatives considered

[What alternatives were considered and why were they rejected?]

### Trade-offs

[What trade-offs were made and why?]

### Rationale

[Why was the chosen alternative the best?]
```

### Spec-as-source marking on generated code

For lane `e` (greenfield module), any code that is generated (by a tool, script, or external process) must be marked as `GENERATED, DO NOT EDIT`. This marking is a string literal placed at the top of each generated file, immediately after the shebang or file header.

**Example generated file header:**

```python
# GENERATED, DO NOT EDIT — source: docs/module-001.md
# This file was generated by the module generator.
# Edits to this file will be overwritten.

import sqlite3
```

The `GENERATED, DO NOT EDIT` string must be a literal (quoted or unquoted, depending on the language) and must be present in every generated file. If a generated file is missing this string, the `file_manifest.py` hook will deny the write.

## Maintenance strategy

| File type | Spec chain | Maintenance strategy |
|---|---|---|
| speckit spec (`docs/feature-*.md`) | spec-first | Retire after merge; link to PR |
| AIUP UC-*.md | spec-anchored | Living document; status line updated |
| pyecoregen output | spec-as-source | GENERATED, DO NOT EDIT |

### speckit spec — spec-first

A speckit spec (`docs/feature-*.md`) is created when a feature is assigned lane `c`. The spec is the first artifact in the feature's lifecycle; it is created before any code is written. The spec is merged and retired after the feature is accepted in the PR. The PR description must contain a link to the spec file.

**Example PR description:**

```
PR: #123 — Add user profile feature
Spec: docs/feature-001.md
```

### AIUP UC-*.md — spec-anchored

AIUP UC-*.md files (User Acceptance Criteria) are created when a feature is assigned lane `d` or `e`. These files are living documents that track the acceptance criteria for the feature. The status line at the top of the file is updated as the feature progresses through the sw-design chain.

**Example UC file header:**

```
---
type: uc
id: UC-001
status: pending
---
```

### pyecoregen output — spec-as-source

Code generated by `pyecoregen` (or any other tool) is treated as the source of truth for the generated artifact. The generated code must be marked `GENERATED, DO NOT EDIT`. The `pyecoregen` tool must be configured to read the spec file and generate the code from it. If the spec file changes, the generated code must be regenerated.

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

**Example speckit flow entry (lane c):**

```
| 2026-11-07 | operator request (SDD integration) | c | specify, plan, tasks, implement, review |
```

**Example full sw-design chain entry (lane d):**

```
| 2026-11-07 | operator request (SDD integration) | d | specify, plan, sw-design, impl, review, deploy |
```

**Example greenfield module entry (lane e):**

```
| 2026-11-07 | operator request (SDD integration) | e | specify, plan, sw-design, impl, review, deploy, typed-decision |
```

## Rule

Every entry appends, never edits history.

The `INTAKE.md` file must be append-only. No entry may edit an existing entry. New entries must be added at the end of the file. The file must never be edited to change an existing entry.

## Definition of done

- Every change request that enters the SDD chain has a lane assignment.
- The lane assignment determines how the change is processed.
- The `INTAKE.md` file is append-only; no entries are edited.
- Lane `e` entries include typed decision records and spec-as-source marking.
- The `triage.md` policy is enforced by the `file_manifest.py` hook.

---

*Generated by SDD harness — DO NOT EDIT.*
