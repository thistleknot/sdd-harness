# Repair cross-harness MCP loading

## CURRENT — verified acceptance, 2026-10-23

The audit findings are repaired; Specs task #82 closes only after both repositories publish and their remote commit IDs match. SpecsDB holds the publication disposition and exact commit IDs.

Superseded: the implementation checklist is preserved in `repair-cross-harness-mcp-loading-implementation-2026-10-23.md`; the invalidated completion claim remains in `repair-cross-harness-mcp-loading-review-2026-10-23.md`.

Chain: permitted-I/O guard -> canonical registry/dependencies -> native projection -> exported-snapshot tests -> connected MCP tools -> published acceptance.

- R1: When a denylisted path is supplied, the system shall reject it before filesystem access.
- R2: When a repository snapshot is published, the system shall include its imported modules, registered local server sources, and runtime definitions.
- R3: When target coverage is inspected, the system shall reject missing dispositions and incorrect native destinations.
- R4: When Hermes would change existing configuration, the system shall validate all entries and verify a native snapshot before writing.
- R5: When Hermes projection runs, the system shall preserve unrelated configuration and server controls.
- R6: When Hermes projection is unchanged, the system shall leave config bytes and backup count unchanged.
- R7: When local MCP servers connect through Hermes, the system shall permit the existing 240-second startup budget.
- R8: When acceptance is recorded, the system shall distinguish configured entries, connected catalogs, and successfully called tools.

## Verified gates

- Clean core export `67f10623364e084426d2f53b5acb54bf9f40bca0` (commit `5c28c3f`): 139 tests passed; all six UV lockfiles validate offline against the installed Python.
- Owner retrieval contract is published with its sibling runner in skills commit `91b77cc`; its exported tests pass without a home-directory module import.
- Final capability/native-probe tests: 21 passed; report lists all nine MCP dispositions, correct native destinations, seven registrations, and zero discrepancies.
- Native Hermes projection: all seven registrations; first application changes three startup budgets after verified native snapshot; repeat changes zero entries and creates no backup.
- Native Hermes transport probe: seven catalogs, with tools graphify=10, agentic-kanban=13, retrieve-skills=2, todo=6, memory-index=9, specs=30, data-science-skills=2; three named lookups pass in about 40 seconds.
- Claude, OpenCode, Kiro, Codex, Copilot, VSCode: native destinations read back seven canonical entries each, including F: commands/arguments/environment, with zero discrepancies.
- General retrieval battery: `test_retrieval.py --live --url http://127.0.0.1:8765` -> seven passed, zero failed.

## Verification commands

From an exported harness tree, run `python -m pytest test_adapter.py specs/test_harness_write.py tests/test_hermes_projection.py tests/test_capability_drift.py tests/test_validate_skills.py test_setup.py test_board.py test_board_mcp.py test_worktrees.py -q`, `python -m scripts.capability_drift`, and Ruff on the changed Python files. Exported trees contain no databases, credentials, environments, logs, or uncommitted source dependencies.

For native Hermes, invoke `scripts/hermes_mcp.py --verify` with the installed Hermes interpreter and a finite JSON stdin buffer containing canonical server names. On Windows, run the verifier hidden with Start-Process, capture PID/output/error, enforce a 300-second outer deadline, and stop only its recorded child tree on failure. The successful probe loaded the canonical JSON into memory before calling the unchanged verify function; redirected-file stdin probes stalled and were stopped by recorded PIDs.

## Evidence limits

Named lookups test tool usability; they do not prove semantic ranking. Broad Spec Kit and retrieval-gate prompts returned the desired skills as CANDIDATE rather than PASS; this is retained as a ranking limitation. The separate seven-case battery tests general retrieval. The native Specs HTTP client emitted a session-termination warning after successful catalog discovery; the full probe returned success and closed every task. Core tests emitted three existing Redis deprecation warnings and ignored Python 3.10 subprocess-pipe destructor messages after a zero exit.

## Boundaries

F: runtimes, supervisors, service data/model locations, py310 non-MCP consumers, Pi's retrieval extension, and unrelated staged/unstaged work remain intact. Migration-artifact cleanup remains separate. Sprawl review: removed two redundant live-plan test helpers and reused canonical registries and native Hermes APIs.
