# Instruction rule registry

`C:\Users\user\.rules\*.md` is the canonical authored source. The SQLite registry holds revisioned publication views for `shared`, `claude`, and `codex`; it is not an independent source of rule text. A rule enters a view only after its frontmatter has an explicitly reviewed `harnesses: [...]` audience and stable `order: NN`; `source` and `source_file` are provenance only. Missing audience is unmapped, not universal, and client-only wording stays scoped to its declared client. The legacy `shared` view remains consumed by both OpenCode and VS Code; canonical export uses separate per-client views.

The independently targetable `adapter.py --target instructions` command reads top-level `~/.rules/*.md` fragments. It selects content only when each fragment declares a known `harnesses: [...]` list and integer `order`; `source` and `source_file` remain provenance. Missing scope/order is reported as unmapped, superseded fragments are excluded, unknown audiences fail visibly, and known unsupported Gemini/Hermes destinations are reported and skipped. A mapped client whose audience becomes empty has its generated region removed after the usual baseline checks and backup; an unmapped destination stays untouched. The reviewed source set now has 39 eligible fragments and 16 excluded fragments (15 unmapped and one superseded). Preview is still required before baseline mapping or publication. Do not edit registry nodes as canonical rule changes or publish a stale view as if it reflected `~/.rules`.

## Export as a native plugin

Base instruction export remains the default. Add `--plugin` to preview a client-native rules plugin; add `--apply` to publish and activate it. The two modes use separate RuleStore document IDs and destinations, so plugin export does not replace a client's base instruction file:

```powershell
python adapter.py --target instructions --plugin
python adapter.py --target instructions --client opencode --plugin
python adapter.py --target instructions --client claude --plugin --apply
```

Verified plugin routes are OpenCode and Claude Code CLI. OpenCode receives a separately registered system-prompt plugin. Claude Code receives a local marketplace package with ordered `UserPromptSubmit` hooks; apply validates, installs or updates, enables, and verifies the user-scope plugin through the Claude Code CLI. Reload the client session after apply. This does not automatically install a plugin into the Claude Desktop/Cowork account UI. Other targets fail closed and never fall back to base export. Preview before apply; RuleStore drift checks and backups apply to the plugin-owned rule hook.

The source, scope, preview, drift, backup, and readback contract is documented in [instruction-publication-contract.md](../.specs/reqs/instruction-publication-contract.md). The exporter has native formats for all seven requested clients. Isolated native-loader checks verified OpenCode system-rule injection and Claude Code `UserPromptSubmit` context injection; the Claude model-response check was blocked by the local Hitch gateway rejecting the temporary model alias. Gemini and Hermes remain skipped or unverified.

## Inspect current views

From `C:\Users\user\.harness`, use the registry CLI:

```powershell
$db = (Resolve-Path .\instructions\rules.db).Path
python -m instructions.cli --db $db outline shared --limit 200
python -m instructions.cli --db $db render shared --out .\instructions\shared-preview.md
```

`outline` reports stable node IDs and the current revision is stored per document. `render` writes a preview of a registry view. The registry's `edit`, `insert`, `move`, and `split` commands remain maintenance primitives; their output is not an authored rule change until it is reconciled to the canonical `~/.rules` fragment and reviewed source-to-view mapping.

## Publish a view

The existing registry publisher remains available for maintained views. For canonical fragment export, preview first; preview is read-only. `--map-baseline` is a separate registry write that records a selected target's current hash without publishing. For Claude and Codex it transfers the old registry mapping only when the old recorded digest still matches. `--apply` requires that mapping and refuses drift:

```powershell
python -m instructions.cli --db $db publish claude C:\Users\user\.claude\AGENTS.md .\backups\instructions
python -m instructions.cli --db $db publish claude C:\Users\user\.claude\AGENTS.md .\backups\instructions --apply
python adapter.py --target instructions --client claude
python adapter.py --target instructions --client claude --map-baseline
python adapter.py --target instructions --client claude --apply
```

T4 reuses RuleStore source hashing, destination baselines, backup, atomic writing, and exact readback. The adapter emits native outputs for all seven requested clients. Markdown destinations preserve pre-existing text outside the adapter's marked region. VS Code gets a separate additive prompt file, so `sync_vscode` continues to own `harness-core.instructions.md`. Export is opt-in and separate from MCP, skills, and default `--target all`; isolated T5 checks verified OpenCode and Claude Code CLI native loading. Claude model-response fidelity remains unverified on the local gateway. Claude and Codex load global `AGENTS.md`; OpenCode loads its registry Markdown through `opencode.json` and `sdd-harness.js`.

`sync-to-claude.ps1` skips `AGENTS.md` once the registry exists. It is not a route for changing canonical rules. Save a client-side edit as a proposal, reconcile it to the appropriate `~/.rules` fragment and reviewed view mapping, then publish through the adapter. Do not import over a live document as a shortcut: import replaces node IDs and audit history.

## Recovery

Create and verify a SQLite snapshot before a large edit or publication:

```powershell
python -m instructions.cli --db $db backup .\backups\rules.sqlite
python -m instructions.cli --db $db verify-backup .\backups\rules.sqlite
```

The database preserves node IDs, hierarchy, emitted byte order, target mappings, current render hashes, and edit receipts. `export-review` writes a deterministic JSON text representation for Git review; `restore-review` restores it into an empty database and verifies all render hashes. Generated Markdown is not a backup source.

```powershell
python -m instructions.cli --db $db export-review .\instructions\rules-review.json
python -m instructions.cli --db .\instructions\restored.sqlite restore-review .\instructions\rules-review.json
```
