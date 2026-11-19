# Shared instruction sources and client routes

CURRENT 2026-11-19. This inventory distinguishes the ~/.rules source fragments, SQLite registry views, publishers, generated destinations, and client loaders. The checked-in manifest describes intended generation routes, while the live receipts establish which routes were exercised.

## Source inventory

| Source | Role | Evidence |
| --- | --- | --- |
| `C:\Users\user\.rules\*.md` | Migrated fragments from Claude's CLAUDE.md and OpenCode's AGENTS.md. Fragments carry `source` and, for many entries, `source_file` frontmatter. The migration script calls itself one-shot. | `migrate_rules.py`; current hashes were collected for the leading fragments. There are additional fragments without source metadata, so ownership needs per-file classification before promotion. |
| `instructions/rules.db` | Current editable registry for `shared`, `claude`, and `codex`. | `instructions/README.md`; `instructions/rules-review.json`. |
| `instructions/rules-review.json` | Review export of the registry. It maps shared, Claude, and Codex documents at revision 1 to their source files and hashes. It contains no OpenCode view. | Parsed JSON: shared hash `46dce0...bda`, Claude `b60b91...2dfb8`, Codex `043cfe...bf1d`. |
| `C:\Users\user\claude\AGENTS.md` in the harness | Canonical shared render consumed by the VS Code adapter. | Registry map in JSON and `_harness_agents_text()` in `adapter.py`. |

## Client routes

| Client | Source and writer | Live destination or loader | Digest or status |
| --- | --- | --- | --- |
| Claude Code | `rules.db` `claude` view, published with `instructions.cli publish`. `sync-to-claude.ps1` explicitly skips AGENTS.md when the registry exists. | `C:\Users\user\.claude\AGENTS.md` loads general agent instructions. `CLAUDE.md` includes that file and other local references. | The generated AGENTS digest matches the registry export at `b60b91...2dfb8`. Separate AGENTS publication was verified in the registry delivery evidence. |
| OpenCode | `rules.db` `shared` view rendered to the existing shared Markdown file. The adapter's `sync_opencode` only writes MCP config. `sdd-harness.js` reads the shared file and appends it in `experimental.chat.system.transform`. | `C:\Users\user\.config\opencode\harness-registry-shared.md`, loaded by `C:\Users\user\.config\opencode\plugins\sdd-harness.js`. `opencode.json` also lists `harness-registry-shared.md` as an instruction. | File digest `46dce0...bda` matches shared view and the historical fresh-session probe returned the registered filepath rule. Live file is 39,019 bytes. |
| Codex CLI | `rules.db` `codex` view, published with the registry command. The general adapter projects MCP and hooks, not this rule view. | `C:\Users\user\.codex\AGENTS.md`. | Digest `043cfe...bf1d` matches registry and Codex runtime probes are recorded in the registry handoff. |
| VS Code | `adapter.py` reads the shared SQLite view, with a Markdown fallback when no registry exists. | User instruction prompt rendered by `sync_vscode`. | Current shared view is the source. Historical registry handoff records successful generated-prompt markers. |
| Pi | Manifest declares an instruction extension at `C:\Users\user\.pi\agent\extensions\harness-steering\`. Installed extension inventory found `retrieve-skills`, but no `harness-steering` extension. | No shared-rule loader identified. Existing Pi retrieve-skills extension is a different capability. | Not propagated or verified. |
| Kiro | Manifest declares native steering files in `C:\Users\user\.kiro\steering`. | Existing steering files load by Kiro. The registry has no Kiro document or publication map. | Client-specific guidance exists. Shared registry rules are not projected through it. |
| GitHub Copilot CLI | Manifest has no shared instruction publisher in its instruction section. | No live instruction destination found in this inventory. | Unmapped. |
| Hermes | No shared instruction renderer found in `adapter.py` targets. | No live shared-rule destination established. | Unmapped. |

## Prior integration evidence

- SATNA feature review says the SATNA changes passed the selected suite, and adapter projection populated MCP registries across supported clients. It does not publish new instruction text from `~/.rules`.
- The registry's historical acceptance checks verified byte-exact shared, Claude, and Codex documents. Claude and Codex fresh-session probes passed. OpenCode fresh-session probes passed through its plugin. VS Code prompt generation markers passed.
- The `~/.rules` migration is separate from the current registry. No normal command in `adapter.py` consumes the fragment directory or reconciles it back into the SQLite registry.

## Disposition

The `~/.rules` corpus is not currently a single reviewed rule authority. Three useful rule views are already in SQLite, and OpenCode reads the shared projection from its plugin. The missing capability is an approved path for newly promoted `.rules` fragments to enter those views and a repeatable publication command that refreshes each supported destination without erasing client-specific guidance. Pi and Kiro require separate adapters or an explicit not-supported disposition before claiming parity.

SATNA service fixes have already been backported through the MCP adapter and live Specs MCP restart. They do not require another server registration change for this work.
