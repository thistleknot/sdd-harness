# Repair cross-harness MCP loading

## CURRENT — implementation, 2026-10-23

Specs task #82 remains DOING. Disposition #6 supersedes the prior completion claim; its previous playbook is preserved in `repair-cross-harness-mcp-loading-review-2026-10-23.md`.

Chain: permitted-I/O guard -> canonical registry/dependencies -> native projection -> exported-snapshot tests -> connected MCP tools -> published acceptance.

- R1: When a denylisted path is supplied, the system shall reject it before filesystem access.
- R2: When a repository snapshot is published, the system shall include its imported modules, registered local server sources, and runtime definitions.
- R3: When target coverage is inspected, the system shall reject missing dispositions and incorrect native destinations.
- R4: When Hermes would change existing configuration, the system shall validate all entries and verify a native snapshot before writing.
- R5: When Hermes projection runs, the system shall preserve unrelated configuration and server controls.
- R6: When Hermes projection is unchanged, the system shall leave config bytes and backup count unchanged.
- R7: When local MCP servers connect through Hermes, the system shall permit the existing 240-second startup budget.
- R8: When acceptance is recorded, the system shall distinguish configured entries, connected catalogs, and successfully called tools.

## Acceptance gates

1. Synthetic guard/projection/preservation failures and three varied target forms; all user-home and backup paths isolated.
2. Exported repository snapshots containing the actual intended commits: imports and focused tests pass without uncommitted modules; canonical registry synchronization cannot reinstall C: Graphify hooks.
3. Native client registrations contain all seven names; Hermes initializes/lists all seven and executes a harmless tool call; three task-specific retrieval canaries pass. Run bounded checks with captured PID/logs, without restarting F: services.

## Publication contract

Publish dependency-complete skills, harness-runtime, and capability-report commits. Preserve unrelated staged/unstaged work; do not stage databases, credentials, environments, or logs. Record commit IDs and exact gate outputs in SpecsDB and this current block before task #82 becomes DONE.

## Boundaries

Retain F: runtimes, existing supervisor ownership, server data/model locations, py310 for non-MCP consumers, and Pi's retrieval extension. Migration-artifact cleanup remains a separate OPEN item.
