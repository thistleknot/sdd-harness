# Integrate SDD/DDSE source material into the sw-design chain

CURRENT 2026-11-07. Supersedes `sdd-inheritance-plan-2026-11-07.md` (same folder;
promoted from `.tmp` 2026-11-07) as the campaign objective
(that thread's work shipped: export, clones, disposition #8, distilled doc, playbook
section — but it stored the material as references; it was never bonded into workflow).
Objective now: every source the operator provided is CONSUMED — each material tag
appears in a concrete stage change, gate, or artifact with a verify receipt.

## Materials (tags used by every wave below)

| Tag | Source | Contribution |
|---|---|---|
| S | `~\.skills\sw-design\SKILL.md` | the 6-stage skeleton |
| D1 | `~\.harness\docs\references\ddse.md` | typed TDRs (ADR/CDR/EDR/IDR), AI Context block, decision→code traceability, CI compliance |
| D2 | `~\.harness\docs\references\ddse and other sdd resources.md` | Kiro design.md vs AIUP entity-model scope boundary |
| B1 | `~\.harness\references\spec-driven-development-book` (+ nested sdd-kit) | practitioner book; requirements/design/tasks/handoff/steering templates |
| A1 | `~\.harness\references\anioko-spec-driven-development\docs` | two-tier taxonomy (agent workflow vs spec compiler); four maturity levels |
| P1 | `~\.harness\references\pi-sdd-kit\skills` | sdd-idea/-review/-status/-steering deltas; `.status` single-file truth; review gate |
| G2 | `~\Documents\wiki\harness\SDD review.md` (Birgitta/Thoughtworks) | spec-first/anchored/as-source ladder; one-workflow-size critique; MDD caution |
| W1 | `~\Documents\wiki\harness\SDD.md` | EARS + three-phase checklists + sequencing strategies — MIRROR of incumbent skill `spec-driven-development`; extend, don't duplicate |
| W2 | `~\Documents\wiki\harness\3 skills.md` + `Three skills..._methods.md` | PRODUCT.md invariants / TECH.md split; /validate-changes-match-specs; computer-use validation |
| W3 | `~\Documents\wiki\harness\harness resources.txt` | Tessl (alt AIUP distribution for codex + reverse-doc pattern), agentic-spec book, marcelsud, xcapit, addyosmani re-check; specky = ALREADY ABSORBED into specs MCP (validate_ears/check_drift/cross_analyze) |
| W4 | `~\Documents\wiki\harness\full-project\` | append-only intake log; rule-conflict-log + protocol; numbered stable ids (already ours) |

## Governing contract

Behavioral + Structural. Spec-first: REQ #73 covers inheritance only; integration
changes observable workflow behavior → task #94 recorded. W0 changes the SpecsDB
decision schema → draft its requirement before coding, per constitution Article I.

## Chosen approach

Options analyzed (receipts in critique.md): A stage-injection only; B cross-cutting
layers around the 6 stages; C replace with pi-sdd-kit; D feeder gate by problem size.
**Chosen: B + D.** A alone misses traceability/CI/review; C collides with the
constitution and the speckit incumbents.

### Feeder gate (A1 levels + G2 size critique) — before stage 1

- mechanical edit → existing constitution exception, chain skipped
- small bug → ticket → fix → test
- feature < ~3 points → speckit flow (specify→plan→tasks→implement→review)
- feature ≥ ~3 points OR touches data model → full 6-stage sw-design
- greenfield module → 6-stage + decision layer + spec-as-source marking
Each entry logs to INTAKE.md (W4) and records its maintenance strategy (G2):
speckit = spec-first; AIUP UC files = spec-anchored; pyecoregen output = spec-as-source.

### Stage extensions (source → concrete change)

1. **Specification** (S+D1+W1+W2): spec.md gains assigned decision ids; add
   PRODUCT.md with a `## Product Invariants` block of agent-verifiable assertions;
   acceptance criteria in EARS via existing `specs_validate_ears`.
2. **Requirements** (S+D1): each sphinx-needs `req` carries a decision id and a
   machine-parsable `:ai-context:` block (constraints, patterns, anti-patterns,
   verification commands); req↔decision matrix emitted.
3. **Design/UML** (S+D1+W1+W2+P1+G2): the two decision points sw-design already
   names (composite PK, containment-vs-reference) become CDR/ADR-typed records with
   AI Context; design.md sectioned per W1 (Overview/Architecture/Components/
   DataModels/ErrorHandling/Testing/Migration); TECH.md per W2 (code-line refs,
   tradeoffs, validation mapping, parallelization); `.status` advanced to design
   (P1); brownfield: recover-from-code stays Draft (S rule) using the reverse-
   engineering pass; Tessl `document --code` noted as alternate technique, not adopted.
4. **Use cases + entity model** (S+D2+P1+W4): entity model lives as the DataModels
   subsection of design.md; promoted to standalone `entity_model.md` only when >10
   entities (D2 boundary); sdd-review gate before stage 5; ids stay UC-XXX (already
   the W4 pattern).
5. **Ecore** (S+D1): every mapping choice recorded as an `EAnnotation` citing its
   decision id; gate 4→5 adds: every entity's governed decisions accounted for.
6. **Classes** (S+D1+P1+W2+W4): generated files carry `GENERATED FROM .ecore — DO NOT
   EDIT` header + decision-id backlinks (Tessl marker pattern); each system use case
   maps to a generated operation or documented external step (S rule) AND to
   PRODUCT.md invariants; sdd-review + validate-changes-match-specs after generation.

### Cross-cutting layers

- **A Decision layer (D1):** SpecsDB decisions gain `type` (ADR|CDR|EDR|IDR) +
  AI-Context field; `architecture-decision` template extended; decision-compliance
  check in `scripts/verify.ps1` (advisory on codex per playbook — can_gate=false).
- **B Review/verification (W2+P1):** `/validate-changes-match-specs` skill
  (invariants→code mapping, inconsistencies report); computer-use validation via
  incumbent `headless-browser-verification`/`agent-browser`; `.status` file written
  as a side effect at each gate, SpecsDB stays the system of record.
- **C Intake/conflict (W4):** `INTAKE.md` append-only at project root;
  `rule-conflict-log.md` + resolution protocol wired to spec-review findings.

## Waves — 11 remain; expected passes W0 2/2, W1 2/2, W2 2/2, W3 4/4, W4 3/3,
## W5 2/2, W6 3/3, W7 3/3, W8 2/2, W9 4/4, W10 3/3

W0 decision schema (D1) → W1 feeder gate (A1+G2+W4) → W2 stage 1 (D1+W1+W2) →
W3 stage 3 (D1+W1+W2+P1) → W4 stage 4 (D2+P1) → W5 stage 5 (D1) → W6 stage 6
(D1+P1+W2) → W7 review layer (W2+P1) → W8 intake/conflict layer (W4) →
W9 W3-holdouts read + re-disposition → W10 playbook + distilled doc rewrite, gates closed.
W0–W6 sequential (shared schema/chain); W7–W8 parallel-safe (disjoint files); W9 parallel.

EXECUTION 2026-11-07: Wave A launched — 4 parallel fixers, disjoint file ownership:
(1) sw-design SKILL.md stage extensions W2–W6 collapsed into one file; (2) W0
architecture-decision + verify.ps1; (3) W1+W8 policy/triage.md + prompt-rules pointer +
rule-conflict-protocol + INTAKE/rule-conflict-log seeds + manifest rows; (4) W7 new skill
validate-changes-match-specs. W9 = parent research (agentic-spec, marcelsud, xcapit
fetched; Tessl install deferred — needs scratch npm global, scheduled separately).
Wave C (W10) starts only after Wave A verify receipts land in critique.md.

## Rejected options

- C (pi-sdd-kit wholesale) — two SDD stacks on one harness; deltas adopted instead.
- Re-adopting specky — already absorbed (observed in specs MCP surface). CLOSED, do not re-test.
- Extending pyecoregen to behavior — S's own limits + G2's MDD caution: determinism
  covers structure only.
- Rewriting Article I for the feeder gate — proposed as a companion triage rule file
  (open question Q1).

## Acceptance

- Every material tag S, D1, D2, B1, A1, P1, G2, W1, W2, W3, W4 appears in at least one
  shipped change with a verify receipt in critique.md.
- Feeder gate classifies 5 varied inputs (mechanical/bug/small/feature/greenfield) correctly.
- A sample change run end-to-end produces: PRODUCT.md invariants, ai-context needs,
  CDR records, annotated .ecore, generated headers, validation report, INTAKE.md entry.
- Playbook + distilled doc describe the final chain; G2/G3/G4 predecessor gates closed or
  explicitly deferred with reason.

## Open questions — ALL RESOLVED 2026-11-07 (SpecsDB decisions #36–39)

- Q1: **rule file** `policy/triage.md` + prompt-rules pointer. Amendment route invalidated by
  the constitution's own ≥2-failure-case evidence requirement; Article I has not failed.
- Q2: **convention-first**: AI-Context block inside decisions.context + leading type token
  (decisions table has no type column — verified); compliance function added to the
  existing scripts/verify.ps1; column migration + CI wiring deferred to falsifier evidence.
- Q3: **separate PRODUCT.md** in specs/<issue>/; embedding invalidated by G2's
  functional/technical-separation failure + distinct consumers (computer-use vs code diff).
- Q4: **reuse `.spec/state.json`** — spec_gate.py already reads approved phase from it
  (PHASES/approved_through); the new `.status` file is retired; W3/W7 say 'state.json phase advance'.

No decision gates remain; execution starts at W0.
