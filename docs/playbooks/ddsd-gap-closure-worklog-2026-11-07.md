# DDSD gap closure — work log (v2) — CLOSED 2026-11-07

Spec: REQ #73 + task #95. Plan: ddsd-gap-closure-plan-2026-11-07.md (same folder). Every DONE has verify
evidence in ddsd-gap-closure-receipts-2026-11-07.md. Promoted to docs/playbooks/ on close.

## Gates — closed by falsifier logic
- [DONE] Q1 revised: gate trust = FAIL-on-fixture first, then clean runs (both seen).
- [DONE] Q2: allowlist only; nothing outside it executes.
- [DONE] Q3: MDD = token + Owner line, no board ceremony.

## V2 waves — all executed

- [DONE] V2-W0 SPIKE: pyecoregen 0.5.1 DROPS EAnnotations (rc=0, files generated, zero decision trace). Verdict recorded (decision #41): stage-5 decision backlinks ride the GENERATED header pass, not the .ecore annotation. This gated every later wave and is why the header script is required, not polish.
- [DONE] V2-W1 allowlist: check_decision_convention.py rejects non-allowlisted Verification commands at record time (static, never executes). Verify: decision #40's `powershell ...` + `sync_skills` commands flagged "not on allowlist"; #41's allowlisted commands pass.
- [DONE] V2-W2 project gate: scripts/decision_gate.py (project-local template) + playbook "Decision gate wiring" section. verify.ps1 stays harness self-check (V1 category error fixed — no project commands there).
- [DONE] V2-W3 violation fixture FIRST: decision-gate-fixture — FAIL(6 loans) → PASS(5) → FAIL(expired waiver) → WAIVED(active) → clean PASS. Gate earned trust by failing on a known break.
- [DONE] V2-W4 lifecycle+store: MDD token + Status:/Owner: lines; architecture-decision SKILL gains "Lifecycle, ownership, and canonical store" (SpecsDB canonical, markdown = rendered view, CDR needs an executable command). Verify: checker flags #40 missing Status/Owner.
- [DONE] V2-W5 CDR teeth: label-only CDR → WARN (decision #40 trips it); FORBIDDEN handled as grep-able static constraint, never executed.
- [DONE] V2-W6 expiring waivers: docs/waivers.md + gate rule expired=FAIL (fixture R3 proves it). Manifest row added.
- [DONE] V2-W7 ladder collapse: code-graph-tools.md gains "Canonical routing (v2)" — graphify/pyreverse/pycallgraph2 canonical, code2flow fallback, gitnexus + understand-anything reclassified as DUPLICATES (deferred, not rungs). Verify: one tool per evidence class.
- [DONE] V2-W8 triage discriminator: lane (c)/(d) now keyed on observable "touches data model or public contract", story points demoted to advisory. Verify: 5 sample lanes re-classify deterministically.
- [DONE] V2-W9 close-out: receipts appended, trio promoted, pointers re-anchored, skills exported (sw-design + reverse-engineer + architecture-decision, 0 router issues), task #95 closed with deferrals named.

## Corrections logged during execution (honesty)
- My "review_changes.py fabricated hook" flag was WRONG — the hook exists (~/.harness/hooks/review_changes.py) and file_manifest.py DOES check GENERATED (L140). Caught by verifying before asserting, per the second-pass rule.
- First fixture run failed PASS because PS 5.1 Set-Content wrote a UTF-8 BOM that broke json.load; fixed with utf-8-sig + [IO.File]::WriteAllText. Re-ran clean.

## Deferred (named, not silent)
- Cross-artifact citation scanner (walk a project's .ecore/headers, resolve every D-id to an Accepted decision) — the gate skips non-Accepted decisions so a citation to a Deprecated one already gets no pass; a dedicated scanner is a later increment.
- gitnexus / understand-anything installs (duplicates of graphify); Tessl trial; CI enforcement wiring (needs a real project CI to wire into); SpecsDB type-column migration (only if the convention falsifies — it is holding).

## Gates — DECIDED 2026-11-07 (operator delegated; deltas folded)

- [DONE] G1 scope: adopt the decision-governance CORE (typed TDR hierarchy, AI-Context block, decision lifecycle, decision→code traceability) now; defer enterprise ceremony (full Decision Authority Matrix, automated mock-server/typegen tooling) to a later increment. Rationale: the core is what prevents AI drift (the threat model); the ceremony is what a solo harness does not need yet.
- [DONE] G2 placement: new constitution Article XVI (Decision Governance) + sw-design Stage 0 (Decision records, before Specification) + rules/decision-governance.md. Rationale: decisions precede specs (DDSE: decisions are the system of record, specs are derived); the feeder gate already exists and decision records feed it.
- [DONE] G3 CDR: adopt CDR as a decision TYPE with a required contract section (endpoints, schemas, auth, error codes); contract tests required (Article V); defer automated mock/typegen tooling. Rationale: the contract section is the value; the tooling is a later increment.
- [DONE] G4 lifecycle+traceability: adopt the full lifecycle (Proposed→Accepted→Deprecated→Superseded) + decision→code traceability (code annotations cite decision ids); enforce via review (Stage 0 gate 0→1) now, a decision_gate check later. Rationale: this is the core of DDSE's "decisions run the enterprise" claim.

## Deltas folded 2026-11-07

- [DONE] constitution.md: added Article XVI (Decision Governance) — typed TDR hierarchy, AI-Context block, lifecycle, CDR contract, decision→code traceability, design-layer vs entity-model.
- [DONE] sw-design SKILL.md: added Stage 0 (Decision records) before Specification; Flow line now leads with decision records.
- [DONE] rules/decision-governance.md: created — the 7 decision-governance rules (typed TDRs, AI-Context, lifecycle, CDR contract, traceability, design-layer vs entity-model, enforcement).
