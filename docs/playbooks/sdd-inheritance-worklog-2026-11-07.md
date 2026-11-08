# DDSE/sw-design inheritance — work log

CURRENT 2026-11-07. Spec: SpecsDB REQ #73, task #93. Plan: sdd-inheritance-plan-2026-11-07.md (same folder).

## Done

- [DONE] Research: located both resources; mapped all three inheritance routes (sync_skills.ps1, vault+sync-to-claude.ps1, adapter.py SKILL_COPY_TARGETS codex -> .agents/skills). Verify: receipts in critique.md.
- [DONE] Record REQ #73 and task #93 in SpecsDB before execution. Verify: tool confirmations.
- [DONE] Write plan.md / critique.md / critique-todo.md in dated subfolder, preserving the XDA top-level .tmp files. Verify: files exist; XDA files untouched.

## Wave 1 — parallel (disjoint files)

- [DONE] Clone the three external SDD repos into `~\.harness\references\` and disposition them (operator instruction; G1 resolved). Verify: Test-Path + item counts; SpecsDB disposition recorded.
- [DONE] Write distilled DDSE reference to vault `~\.harness\claude\docs\references\ddse-and-other-sdd-resources.md`; raw originals untouched. Verify: file exists.
- [DONE] Manifest: existing subsystem rows cover both new paths — `** | claude/` (L97) and `** | references/` (L151); no new row needed. Verify: grep of file-manifest.md.
- [DONE] Sync sw-design to `~\.claude\skills\sw-design\` — adapter exported to claude, codex, copilot, opencode, hermes, pi; 0 router issues. Verify: SKILL.md present in `.claude\skills\sw-design\`.
- [DONE] Add Design-layer section to `~\.harness\docs\playbooks\playbook-harness-sdd.md` naming sw-design + the distilled doc. Verify: grep lines 99-102.

## Wave 3 — operator gates (nothing proceeds until decided)

- [DONE] G1: vendor vs link-only — operator chose vendor; clones executed and dispositioned 2026-11-07.
- [GATE G2] Name sw-design as the design-layer toolchain in constitution Article I, or keep it a playbook reference?
- [GATE G3] On pi: pi-sdd-kit wholesale, speckit, or import only the four delta skills (idea/review/status/steering) + handoff template?
- [GATE G4] Adopt DDSE concepts: CDR-style contract record, AI-Context block in the ADR template, decision-compliance CI check?

## Wave 2 — sequential (shared tree)

- [DONE] `sync_skills.ps1 -Skill sw-design -Yes` (adapter --target skills --apply --reconcile). Verify: native copies at `~\.claude\skills\sw-design\SKILL.md` and `~\.agents\skills\sw-design\SKILL.md` both True; 6 changed resources; 0 router issues; R19 satisfied for codex.
- [DONE] `sync-to-claude.ps1 -DryRun` showed `create -> docs\references\ddse-and-other-sdd-resources.md` plus FOUR unrelated divergences (CLAUDE.md, rules\orchestration.md, hooks\playbook.py, hooks\test_playbook.py), held: 0. Chose targeted single-file copy over blanket -Push to stay in scope; copy landed in `~\.claude\docs\references\`. The four divergences are an operator decision (push vault->live or pull live->vault) — separate todo.
- [DONE] Smoke: both native skill dirs verified above; live doc verified by Test-Path.

## Carry-over (separate thread — XDA shared workspace, top-level .tmp)

- [OPEN] SpecsDB task #91 close + render (blocked earlier by approval policy).
- [OPEN] One real handoff/resume between installed client routes before claiming live cross-harness transfer.
