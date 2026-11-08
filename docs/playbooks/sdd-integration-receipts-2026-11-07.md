# SDD integration — evidence receipts

## 2026-11-07 — re-review of all operator-provided material

- [observed] Operator verdict on the prior pass: materials were stored (clones,
  disposition, distilled doc, playbook pointer) but never bonded into the workflow;
  the stage 1–6 description cites only S and my own additions — no D1/A1/P1/G2/W1–W4
  content appears in any stage. Diagnosis accepted: records, not integration.
- [observed] DDSE is absent from sw-design entirely [full read of SKILL.md]; its
  natural insertion point is the two decision points S itself mandates recording at
  stage 3 (composite PK; containment-vs-reference) — today free prose, under D1 typed
  CDR/ADR records with AI Context.
- [observed] specky's contributions are already absorbed: the specs MCP surface
  exposes validate_ears, check_drift, cross_analyze, graph (decision nodes,
  implements/evidences edges) [observed tool list]. CLOSED — do not re-test.
- [observed] wiki `SDD.md` is a mirror of incumbent skill `spec-driven-development`
  (same three-phase structure, EARS, checklists; front matter author "Kiro Team").
  Sprawl call: extend the incumbent, never create a second SDD skill.
- [observed] wiki `reify` note (TRIZ + six hats + surviving premises) is already
  implemented in `plan-do`'s required reasoning sequence [full read of plan-do]. CLOSED.
- [observed] `harness resources.txt`: Tessl listed as an alternate AIUP distribution
  route for codex (`tessl init --agent codex` + `tessl install aiup-core`) — competes
  with the adapter R19 native-copy route; treat as premise to test (W9), not adopt.
  Tessl `document --code` reverse-generation maps to S's brownfield recovery rule.
- [observed] G2 (Birgitta): spec-first/spec-anchored/spec-as-source ladder; one-
  workflow-size critique; MDD caution — deterministic parseable specs trade against
  LLM non-determinism. S stage 6 (pyecoregen) is deliberately the deterministic side;
  extending it to behavior would repeat MDD's failure [inferred from S's Known limits + G2].
- [observed] W2 (Warp): PRODUCT.md carries user-perspective invariants the agent
  verifies in code and via computer use; TECH.md carries code-line refs, validation
  mapping, parallelization; /validate-changes-match-specs reports invariant→code
  mismatches. Our incumbents: use-case-coverage/test-case-coverage do spec↔code
  coverage; headless-browser-verification/agent-browser exist for the computer-use
  step; the INVARIANT framing itself has no incumbent.
- [observed] P1 deltas beyond speckit: sdd-idea, sdd-review, sdd-status (.status
  single-file truth), sdd-steering, handoff template [tree read].
- [observed] W4 full-project patterns: numbered stable ids (already ours: REQ/UC/TC),
  append-only intake log (no incumbent at project root), rule-conflict-log +
  resolution protocol (spec-review detects contradictions; no resolution artifact).
- [observed] W3 holdouts unread: agentic-spec.com book, marcelsud, xcapit, addyosmani
  adoption count stale.

## Critique of the prior approach (what was left out)

1. No stage-level enhancement from any source; 2. no new layers (decision, review,
intake); 3. no problem-size routing (G2's core critique); 4. no maintenance-strategy
commitment (first/anchored/as-source never stated per artifact); 5. no product
invariants; 6. no rule-conflict protocol; 7. W3 resources undispositioned.

## Weak premises / falsifiers

- Premise: AI-Context blocks will be obeyed by agents. G2's "false sense of control"
  evidence says instruction-following is imperfect — falsifier: if the sample
  end-to-end run ignores ai-context constraints, move enforcement to the CI check
  (W0→W7 dependency) rather than trusting prose.
- Premise: `.status` file adds value over SpecsDB. Falsifier: if agents in tests
  still call the specs MCP, retire `.status` (Q4).
- Premise: >10-entity threshold is the right promote-to-standalone line. Arbitrary;
  measure on the first two real runs, adjust as config not law.
- Premise: Tessl distribution viable for codex. Untested; W9 only reads/tries in a
  scratch dir — the adapter route stays canonical until proven otherwise.

## Options analysis (TRIZ/Bono pass per plan-do)

- A stage-injection only: cheap, but no traceability/CI/review — half the material.
- B cross-cutting layers: matches D1/P1/W2/W4 which are inherently cross-stage.
- C pi-sdd-kit wholesale: two stacks, constitution collision — rejected.
- D feeder gate: answers G2's strongest critique directly.
- Winner: **B + D** (A is subsumed — stages still get injected where a source names a
  stage). Six Hats check: risks (routing-gate over-engineering for tiny changes →
  mitigated by the mechanical/bug lanes); benefits (every source gets a consumer);
  process (waves W0–W10 with per-wave verify).

## 2026-11-07 — gates Q1–Q4 closed by discriminating evidence (SpecsDB #36–39)

- [observed] Amendment Process (constitution L158+): requires ≥2 independent failure cases
  against the article being amended. Article I has not failed → amendment route
  procedurally invalid → **Q1 = policy/triage.md** (manifest rows `*.md | policy/`).
- [observed] scripts/verify.ps1 EXISTS (compliance substrate real); specs.db decisions
  columns lack `type` → schema surgery unjustified before the convention earns it →
  **Q2 = convention-first** (AI-Context block + type token in context; migration + CI
  wiring deferred to falsifier evidence).
- [observed] spec_gate.py keys on `.spec/state.json` (PHASES, approved_through; L65-66,
  L119, L126); markdown exempt (L22) → **Q4: P1's `.status` already exists as
  state.json**; sidecar retired; W3/W7 rewritten to 'state.json phase advance'.
- [inferred] **Q3 = separate PRODUCT.md**: G2 names functional/technical separation as
  the recurring failure; invariants and TECH have different consumers; specs/<issue>/
  is speckit's existing home; no gate collision.
- Falsifiers per decision: triage ignored in 2+ runs → amendment case opens; convention
  parse-fails/ignored in 2+ runs → column + CI wiring; PRODUCT/spec drift in 2+ runs →
  merge; state.json vocabulary can't express new gates → reopen as PHASES schema question.

## 2026-11-07 — execution start (Wave A)

- [inferred] W2–W6 are all edits to ONE file (sw-design SKILL.md); plan-do wave rule 1
  (group by file ownership) collapses them into a single delegation, not five sequential ones.
- [observed] Manifest `*.md | policy/` row already covers policy/triage.md and
  policy/rule-conflict-protocol.md — no new rows needed; docs-root files (INTAKE.md,
  rule-conflict-log.md) require explicit rows added BEFORE creation per the declared process.

## 2026-11-07 — Wave A verification: two fixers returned false/defective work

- [observed] sw-design fixer claimed 8 section additions; master file unchanged (101 lines, zero new markers) and mirror likewise. Parent executed the edits directly (now 123 lines, 15 marker lines, original tables intact).
- [observed] policy fixer OVERWROTE .specs/file-manifest.md (the governing artifact) with its own 2-row table instead of appending. Restored via `git checkout -- .specs/file-manifest.md`; rows appended after the docs/playbooks row.
- [observed] verify.ps1 fixer wrote `[System.Data.SqlClient.SqlConnection]` SQL-Server code against a SQLite file (runtime-fatal) and PS 5.1 mangles embedded double quotes in `python -c` here-strings (SyntaxError '(' never closed). Replaced with standalone scripts/check_decision_convention.py.
- [observed] The specs-mcp service WORKDIR is C:\Users\user\.mcp\specs — live DB there; ~/.harness/specs/specs.db is a stale duplicate (mtime 2026-09-04). created_at is ISO-8601 text.
- [observed] Convention check first real run: checked 5, skipped 35 legacy, WARN #36-39 (pre-convention gate decisions — grandfathered by design), #40 clean, exit 0.
- [inferred] Lesson: specialist DONE claims are not evidence; the parent must re-read the touched artifact (file size, markers, git status) before appending receipts. Logged to memory.

## 2026-11-07 — W11: code-graph ladder (operator addendum)

- [observed] Corpus-wide grep: zero mentions of pycallgraph/code2flow/pyreverse/gitnexus/understand-anything/code2prompt in any skill; graphify exists only as its own skill, never referenced from reverse-engineer. Operator's suspicion confirmed: the reverse-engineer skill was not about these tools.
- [observed] Availability: pyreverse + graphify installed; code2flow 2.5.1 + pycallgraph2 1.1.3 pip-installed this wave (exit 0). gitnexus and understand-anything identified by researcher with URLs (sipher-git-nexus npm; Lum1104/understand-anything Claude plugin) — installs deferred.
- [inferred] The ladder's citation rule (static + dynamic-or-historical per recovered artifact) is the walk-back equivalent of the chain's decision-trace discipline: reverse-engineered requirements earn non-Draft status the same way generated code earns merge status.

## 2026-11-07 — end-to-end sample run (acceptance item; 1 of 2 runs)

- [observed] Library-book-lending lane-(d) feature walked the full chain in scratch: INTAKE row, spec.md (3 EARS + decision ids), PRODUCT.md (3 invariants), sphinx-needs build with AI-Context needs, class diagram rendered (via plantuml.jar fallback), design.md + TECH.md + EDR/CDR records, UC-001/002 passed the bundled validator --strict (0 errors), lending.ecore loads with 8 decision-id citations, pyecoregen output imports with GENERATED header. Full report promoted to `docs/playbooks/sdd-integration-samplerun-2026-11-07.md`.
- [observed] Finding 1 (command rot): every quoted stage-5/6 command failed against installed versions; skill Commands section rewritten with verified invocations.
- [observed] Finding 2 (needuml silent no-op without sphinxcontrib-plantuml): installed 0.31; skill documents both render paths.
- [observed] Finding 3 (backlink snaps at codegen): EAnnotations load from .ecore but vanish from generated Python; validation report honestly flagged INV-1 unenforced (structure-only, per S's Known limits + G2's MDD caution). Consequence: the GENERATED-header annotation script moves from polish to REQUIRED for the stage-5→6 traceability claim.
