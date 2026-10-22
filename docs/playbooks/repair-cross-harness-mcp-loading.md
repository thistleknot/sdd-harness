# Repair cross-harness MCP loading

## Current disposition — Specs task #82, 2026-10-22

- `python adapter.py --target hermes` projected all seven registry names through Hermes'
  native `_save_mcp_server`; `hermes mcp list` reports all seven enabled.
- The isolated Hermes writer canary ran twice with HTTP and stdio entries; the unrelated
  model setting, custom setting, and unmanaged MCP entry survived both writes.
- The exact retired C: Graphify commands were removed from live Claude, the Claude vault
  projection, and Codex hooks. The same files retain five F: Graphify hooks; the removal
  check reports zero retired commands.
- Read-only native-config checks report all seven names in Claude Code, OpenCode, Kiro,
  Copilot CLI, VS Code, and Codex. Pi's existing retrieval extension remains present.
- Three retrieval canaries returned `graphify`, `speckit`, and `retrieve-skills` as PASS.
- `pytest -q test_adapter.py specs/test_harness_write.py`: 54 passed; this includes the
  harness credential-file deny tests. The added R7/R8 statements validate as EARS (2/2).
- No F: server runtime or service ownership was changed.

The prior service, cold-start, and MCP tool-count baseline is preserved in
`repair-cross-harness-mcp-loading-baseline-2026-10-22.md`. Migration-created C: artifacts
remain OPEN and untouched; py310 remains available to unrelated consumers.

| Link | Status | Evidence / remaining gate |
|---|---|---|
| Registry -> Hermes writer | TESTED | Seven entries visible through `hermes mcp list`; isolated repeat-write canary preserved unrelated config. |
| Registry -> existing native targets | TESTED | Claude Code, OpenCode, Kiro, Copilot CLI, VS Code, and Codex each contain all seven names; Pi retrieval extension remains. |
| Retired Graphify hook cleanup | TESTED | Five current F: hooks remain across three projected files; zero exact retired C: commands remain. |
| Retrieval canaries | TESTED | Graphify, Spec Kit, and retrieve-skills queries each returned the expected PASS skill. |
| F: runtime and service ownership | UNCHANGED | Task #82 made no service, runtime, or supervisor changes. |
| Cleanup of migration-created C: artifacts | OPEN | Ownership of those separate artifacts is still unidentified; retain them and py310. |

## Objective and boundaries

Make every registered MCP load through the supported native config of each
installed MCP-capable harness, with isolated Python environments and uv cache
under F:. Keep server code, databases, models, and non-MCP Python users in their
current locations. `harness.json` is the registry; `adapter.py` projects it;
`harness_write.py` owns safe writes and backups; `manifest.toml` owns runtime
placement. Details remain in `~/.mcp/specs/specs.db` (task 75).

- Do not remove py310 or move server data/model stores.
- Do not convert Pi's retrieval extension to MCP.
- Keep unrelated Copilot and other user configuration intact.
- Do not add a parallel supervisor where an existing task or NSSM service owns the process.

## Remaining order

1. The elevated cutover and registered-server client checks are complete.
2. Keep py310 and migration rollback artifacts until any C: cleanup target is
   positively identified; cleanup is separate from MCP loading completion.

## Recursion outcomes

- Service cutover and registered-server checks passed; retain rollback records
  and the general py310 environment.
- If future cleanup identifies migration-created C: files, verify each exact
  path and owner before removing it; do not remove py310 or server data.

## Completion check

- Every native MCP-capable harness loads all seven registered names; Pi retains
  its extension and no unrelated user entries are lost.
- Every Python MCP service and stdio process runs from its isolated F:
  environment; Graphify and the uv cache also reside on F:.
- All four HTTP ports answer health and MCP initialize/list; all three stdio
  servers initialize and list tools through their native clients.
- Three distinct retrieval canaries return relevant skills.
- A second adapter sync makes no MCP projection changes and rollback definitions
  remain available; migration-created C: artifacts are retained until identified.
