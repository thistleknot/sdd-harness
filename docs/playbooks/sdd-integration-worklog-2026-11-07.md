# SDD integration — work log

CURRENT 2026-11-07. Spec: REQ #73 + task #94. Plan: sdd-integration-plan-2026-11-07.md (same folder).
Wave A executed and VERIFIED by the parent; two of four fixers returned false or
defective claims — receipts in critique.md.

## Decision gates — CLOSED (SpecsDB #36-39; sample conforming record #40)

- [DONE] Q1 policy/triage.md · Q2 convention-first · Q3 separate PRODUCT.md · Q4 reuse .spec/state.json.

## W0 — decision convention (D1) [2/2]

- [DONE] Convention documented in architecture-decision SKILL.md (AI-Context block + ADR/CDR/EDR/IDR prefixes).
- [DONE] scripts/check_decision_convention.py (live DB ~/.mcp/specs/specs.db, ISO cutoff, WARN-only) wired into verify.ps1. Verify: run shows checked 5 / skipped 35 / WARN #36-39 (grandfathered, expected) / #40 clean / exit 0; CheckSpec passes.
- [DEFERRED] column migration + CI enforcement wiring (per Q2 falsifier).

## W1 — feeder gate (A1+G2+W4) [2/2]

- [DONE] policy/triage.md (5 lanes + maintenance strategy + INTAKE format).
- [DONE] prompt-rules.md pointer (L115); docs/INTAKE.md seeded with first row; manifest rows added AFTER restoring the overwritten file-manifest.md via git checkout (defect receipt in critique.md).

## W2–W6 — stage extensions (S+D1+D2+W1+W2+P1+W4) [executed by PARENT after fixer false claim]

- [DONE] sw-design SKILL.md 101 -> 123 lines: Feeder gate section; stage table rows 1-6 extended (PRODUCT.md invariants, AI-Context needs, CDR/ADR + design.md + TECH.md + state.json gate, entity nesting >10 rule, EAnnotation citations, GENERATED header + invariant trace); rules + stage-gates lists updated. Verify: 15 marker lines present; original Ecore mapping table + Known limits intact.

## W7 — review layer (W2+P1) [3/3]

- [DONE] validate-changes-match-specs skill created (~/.skills/.../SKILL.md): invariant->diff report, contracts, boundary vs use-case-coverage/test-case-coverage, computer-use lane by reference.
- [DONE] Exported: sync_skills -Yes on 3 skills -> 22 resources, 0 router issues (sw-design, architecture-decision, validate-changes-match-specs -> claude/codex/copilot/hermes/pi/opencode).

## W8 — intake/conflict layer (W4) [2/2]

- [DONE] policy/rule-conflict-protocol.md + docs/rule-conflict-log.md seeded; blocking rule defined.

## W9 — W3 holdouts [3/4, 1 deferred]

- [DONE] agentic-spec.com: notes-only — thesis "the spec is the bottleneck; AI drafts specs, humans judge"; no artifact beyond incumbents.
- [DONE] marcelsud: notes-only — /spec:create (context+requirements EARS+tasks TDD) overlaps speckit; no delta.
- [DONE] xcapit: notes-only — one concept folded into deferred CI item (spec as first-class build artifact with own pipeline); fit/poor-fit lists corroborate triage lanes.
- [DEFERRED] Tessl codex-distribution trial — needs scratch npm global install; adapter R19 route stays canonical until tested.

## W10 — inherited surface rewrite [3/3]

- [DONE] playbook-harness-sdd.md Design-layer section replaced with the integrated chain.
- [DONE] Distilled vault reference rewritten as workflow description (sources -> where they went); targeted copy to live ~/.claude/docs/references/ (push avoided per divergence todo #26).
- [DONE] Skills exported (W7); task #94 closed with deferrals named.

## W11 — code-graph ladder wired into reverse engineering (operator addendum 2026-11-07)

- [DONE] Identified tools: graphify (installed CLI+MCP), pyreverse (installed), code2flow + pycallgraph2 (installed this wave), gitnexus (real: DuyTranSipher/sipher-git-nexus, npm, tree-sitter+MCP, 10 langs), understand-anything (real: Lum1104/understand-anything, Claude Code plugin, 15k stars). Verified the incumbent reverse-engineer skill cited NONE of them before this wave.
- [DONE] reverse-engineer/references/code-graph-tools.md created (ladder + citation rule + REA boundary + Windows notes); SKILL.md gained "Code-graph evidence first" section + step-8 citation check.
- [DONE] sw-design brownfield rule now points at the ladder.
- [DONE] Full traced flow article shipped inside the skill: `sw-design/references/integrated-flow.md` + SKILL.md pointer, so clients inherit the write-up itself, not a chat paste.

## W12 — end-to-end sample run (acceptance)

- [DONE] Lane-(d) feature walked the chain; report at `docs/playbooks/sdd-integration-samplerun-2026-11-07.md`; findings folded into skill Commands + article; sphinxcontrib-plantuml installed.
- [OPEN] Second varied run (a lane-(c) small feature + a brownfield ladder pass) before decisions #36-39 falsifiers are considered satisfied — the convention claims need 2+ runs.
- [OPEN] GENERATED-header annotation script upgraded from deferred to required (todo #28).
- [DEFERRED] gitnexus npm global install; understand-anything plugin install (footprint decision); graphviz check for image rendering.

## Carry-over (other threads, unchanged)

- [OPEN] todo #26: four unrelated vault/live divergences (push or pull decision).
- [OPEN] XDA thread: SpecsDB task #91 close + render; one real cross-client handoff test.
