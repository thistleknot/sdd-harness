# Cross-harness MCP loading baseline superseded 2026-10-22

This prior disposition is retained as a baseline; the active task #82 disposition is in
`repair-cross-harness-mcp-loading.md`.

The seven registry entries project to six MCP-capable user configs; Pi keeps its
existing retrieval extension. Six isolated F: Python projects and the Graphify
MCP tool are provisioned. All four HTTP services now use their F: environments,
all health endpoints pass, and live MCP initialize/tool-list checks return 2,
9, 6, and 30 tools. The existing `skill-router-probe` action also uses F:.
OpenCode connects to all ten configured servers. Claude connects to every
registered server when its documented `MCP_TIMEOUT` is set to 240000 ms. A
measured 112.7-second cold import of data-science-skills exposed why the prior
OpenCode 120000 ms timeout was too tight; the central adapter now projects
240000 ms. Migration-created C: artifacts remain untouched pending exact-path
identification; py310 remains available to unrelated consumers.

| Link | Status | Evidence / remaining gate |
|---|---|---|
| Registry -> adapter | TESTED | Seven entries flow through the existing adapter and safe writer. |
| Adapter -> native configs | TESTED | Claude, Kiro, Copilot, VS Code, OpenCode, and Codex each contain all seven entries; second sync leaves the MCP server maps unchanged; Pi extension remains. |
| Python env -> server imports | TESTED | Six locked F: environments pass their server imports; F: hardlinks point into F: uv cache; Graphify includes its MCP extra. |
| F: server -> MCP initialize/list | TESTED | retrieve 2, memory 9, todo 6, specs 30, data-science 2, kanban 13, Graphify 10 tools. |
| Supervisor -> live listener | TESTED | Four NSSM Application values and the existing retrieve probe action use F:; services are running and ports 8765, 8055, 8056, and 8057 pass health. |
| HTTP service -> MCP tools | TESTED | Direct MCP initialize/list succeeds with retrieve 2, memory 9, todo 6, and specs 30 tools. |
| Native clients -> registered servers | TESTED | OpenCode connects to all ten configured servers; Claude connects to every registered server with the 240000 ms startup timeout; Codex and Copilot show the F: registrations. |
| Cleanup of migration-created C: artifacts | OPEN | Exact migration-created paths are not identified; retain them and py310 until their ownership is verified. |
