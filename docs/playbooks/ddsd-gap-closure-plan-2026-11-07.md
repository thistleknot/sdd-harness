# DDSD gap closure — REVISED (v2) after second-pass falsification

CURRENT 2026-11-07. v1 waves W0-W4 SUPERSEDED by this revision — reason recorded in
ddsd-gap-closure-receipts-2026-11-07.md (same folder). The misunderstanding ledger M1-M6 below STANDS; only the countermeasures changed.
Promote this trio to docs/playbooks/ddsd-gap-closure-* AT CLOSE (not before — v1's
premature-promotion error is itself a logged finding).

## Misunderstanding ledger (unchanged, verdicts confirmed)

- M1 "we adopted DDSE enforcement" → NO — format only; verification commands never executed.
- M2 "type tokens = typed governance" → PARTIAL — no MDD, no Owner/Status semantics.
- M3 "one decision system of record" → NO (latent) — skill instructs ADR files; checker reads SpecsDB; no files exist yet.
- M4 "CDR = contract primitive" → NO — label only, no executable check.
- M5 "WARN-only is safe" → NO — undated WARN is DDSD §5's forever-note.
- M6 "small-team escape hatch applies" → NO — threat model is AI drift; two in-session specimens.

## v1 → v2: what the second pass killed and why

| v1 claim | Verdict | Evidence |
|---|---|---|
| CI runs verification | NO CI exists | recursive check: no .github/workflows, Jenkinsfile, or CI config in ~/.harness |
| Runner lives in verify.ps1 | category error | verify.ps1 is a harness SELF-check (settings/MCP/hooks); project commands belong at the PROJECT's gate |
| Execute free-text Verification commands | security hole | a spec artifact becomes an exec surface; needs allowlist, never raw shell |
| 6-rung code-graph ladder | sprawl | graphify/gitnexus/understand-anything all do code-knowledge-graphs; pyreverse/code2flow overlap on static structure. A list, not a routing decision |
| Stage-5 EAnnotation citations | UNVERIFIED | spike attempts inconclusive (pyecoregen invocation finicky, malformed fixture ecore). Load-bearing, never proven |
| Gate after 2 clean runs | wrong metric | measures script execution, not violation detection |
| ~3 points lane discriminator | non-deterministic | nobody estimates points observably |

## Chosen approach v2 — enforce at the project's gate, prove by failing first

| Wave | Closes | Change | Verify |
|---|---|---|---|
| V2-W0 SPIKE (blocks all others) | M1 + unverified assumption | known-good .ecore fixture + pyecoregen run + grep: do EAnnotations survive codegen? Verdict picks the stage-5 citation carrier: EAnnotation (if survives) or generated-header comment (if dropped — header we control). Record verified pyecoregen flags | one discriminating grep result, PASS or FAIL, in critique.md |
| V2-W1 | security | Verification-commands ALLOWLIST spec: `pytest <path>`, `python -m pytest <path>`, `python <test-file>` only; format checker rejects non-conforming commands at RECORD time (static, safe) | a decision with `curl … | sh` fails the format check |
| V2-W2 | M1, category error | harness DEFINES convention; project ENFORCES it: template `scripts/decision_gate.py` (project-local: reads that project's Accepted decisions, runs allowlisted commands, non-zero on FAIL) + playbook section on wiring it into a project's pre-commit/CI. verify.ps1 keeps format checks only | gate script runs against fixture in V2-W3 |
| V2-W3 | wrong metric | violation fixture FIRST: scratch project, one Accepted decision, one deliberate contract break; gate proven by FAILING; then fix, clean run. "2 clean runs" = gate runs on the fixture project | FAIL output on broken state; PASS on fixed state |
| V2-W4 | M2, M3 | lifecycle tokens: add MDD: to set; `Status:` + `Owner:` lines; checker validates cited decision ids (needs/EAnnotations/headers) resolve to Accepted decisions (static resolution, no exec); architecture-decision skill rewired to SpecsDB-canonical (markdown = rendered view, per harness doctrine) | superseded-citation sample flagged; round-trip decision visible |
| V2-W5 | M4 | CDR teeth: a CDR with no allowlisted executable command gets FAIL "label-only CDR"; `FORBIDDEN:` lines become greppable static constraints (grep, never exec) | sample-run D-002 upgraded clears it; a bare CDR trips it |
| V2-W6 | M5 | docs/waivers.md (decision, scope, expiry); gate: expired waiver = FAIL; blanket WARN retired for waived decisions | backdated waiver trips FAIL |
| V2-W7 | sprawl | ladder COLLAPSED to canonical routing: graphify = structure+communities (MCP, installed, canonical); pyreverse = UML/entity candidates; pycallgraph2 = dynamic confirmation; code2flow demoted to fallback; gitnexus + understand-anything reclassified as DUPLICATES (deferred, not rungs). Update reverse-engineer reference + integrated-flow article, re-export | grep: one tool per evidence class in the reference |
| V2-W8 | non-deterministic gate | triage lane (d) discriminator: "touches the data model or a public contract" (observable); points advisory only | re-classify the 5 sample inputs under the new wording |
| V2-W9 | close-out | receipts + burndown; promote trio to docs/playbooks/ddsd-gap-closure-*; update article + distilled reference; export; SpecsDB #95 closed with deferrals named | pointers resolve to new paths; zero stale .tmp refs |

Rejected (recorded, do not re-litigate): runner inside harness verify.ps1; raw command
execution; 6-tool ladder; point-based lane threshold; authority-matrix ceremony;
mock/type generation.

## Wave counts

9 waves remain; expected passes V2-W0 1/1, W1 1/1, W2 2/2, W3 2/2, W4 3/3, W5 2/2,
W6 1/1, W7 2/2, W8 1/1, W9 3/3. V2-W0 gates everything: no later wave builds on the
EAnnotation claim until its verdict lands.

## Acceptance

- Spike verdict recorded and the stage-5 citation mechanism matches it.
- Gate FAILS on the violation fixture before it is allowed to claim PASS anywhere.
- No executed command anywhere in the enforcement layer that isn't on the allowlist.
- One canonical tool per evidence class in the ladder reference.
- Records promoted at close, not before; all inbound pointers re-anchored.
