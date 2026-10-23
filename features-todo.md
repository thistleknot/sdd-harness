# External feature work

## CURRENT — verified acceptance, 2026-10-23

Prior completion claims are archived in `docs/playbooks/external-feature-work-review-2026-10-23.md`; the audit invalidated four-cell MCP coverage and tests depending on unpublished home-directory code.

Task #82 acceptance: dependency-complete harness core `5c28c3f` and owner tests in skills `91b77cc`; final report/native-probe changes are recorded by this file's publication commit and SpecsDB disposition. Clean core export: 139 passed; native Hermes: seven connected catalogs and three named retrieval lookups; six other native config destinations each contain all seven canonical entries. Pi retains its retrieval extension. General retrieval battery: seven passed, zero failed.


`~/.mtp/features.md` is the read-only source inventory. `plan.md` remains the read-only board render. This file is a concise OPEN/DOING/DONE view; the Specs DB and kanban are authoritative for task state. Promote an item to DONE only with the cited check/result.

## DOING

- None.

## OPEN

- None.

## DONE

- [x] Reviewed all five requested repositories and mapped their advertised capabilities to existing harness incumbents. Evidence and source links: [`~/.mtp/features.md`](.mtp/features.md), `.tmp/pland.md`; Specs REQ #54–57 validated.
- [x] Confirmed `plan.md` is already read-only and board-rendered; retained the Specs DB and kanban as authoritative work trackers.
- [x] Added `scripts/validate_skills.py` for read-only skill metadata/reference checks; 5 synthetic tests pass and all 198 immediate child skills pass. Specs REQ #58–61; tasks #84 and #89.
- [x] Reconciled agent-render expectations to the current `tiers.toml`; 43 manifest/renderer tests pass. Specs task #87.
- [x] Compared quickstart practices with the MCP tool contract, worktree isolation, and append-only event trail; no Claude API application code adopted. Specs task #88.
- [x] Added explicit Codex, Gemini, and Hermes declarations to `manifest.toml`; expanded matrix tests for declarations, unique cells, known strategies, and SKIP reasons. `python -m pytest specs/test_manifest_agents.py -q` -> 9 passed. Specs REQ #62–63; task #86.
- [x] Tightened the five positive and two negative retrieve-skills canaries: expected positives now fail closed, each case gets an isolated session ID, and positive selections must point to readable non-empty `SKILL.md` files. Live canaries -> 7 passed, 0 failed; Specs REQ #64–65; task #85.
- [x] Added `scripts/capability_drift.py`, a read-only report across MCP registrations, manifest/adapter targets, skill targets, global hook wiring, and plugin artifacts. Report -> 0 discrepancies across 7 MCP registrations, 9 MCP dispositions (7 GENERATE, 2 SKIP), 4 skill dispositions, 3 configured hooks, and 3 plugin skill packages; report scope is configuration and artifacts, not live connections; Specs REQ #66–67; task #90.
- [x] Added deterministic contract tests for case coverage, selected-skill usability, supported/SKIP reporting, missing adapter targets, invalid server transports, and the minimum-case guard. Corrective report/native-probe suite -> 21 passed; Ruff passed; owner retrieval contracts live in the skills package and pass from its exported commit.
