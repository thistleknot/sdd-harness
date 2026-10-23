# External feature work

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
- [x] Added `scripts/capability_drift.py`, a read-only report across MCP registrations, manifest/adapter targets, skill targets, global hook wiring, and plugin artifacts. Report -> 0 discrepancies across 7 MCP registrations, 4 skill dispositions, 3 configured hooks, and 3 plugin skill packages; Specs REQ #66–67; task #90.
- [x] Added deterministic contract tests for case coverage, selected-skill usability, supported/SKIP reporting, missing adapter targets, invalid server transports, and the minimum-case guard. Combined focused suite -> 20 passed; Ruff passed.
