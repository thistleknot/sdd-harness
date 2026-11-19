# Instruction rule registry

`C:\Users\user\.rules\*.md` is the canonical authored source. The SQLite registry holds revisioned publication views for `shared`, `claude`, and `codex`; it is not an independent source of rule text. A rule enters a view only after its frontmatter has an explicitly reviewed `harnesses: [...]` audience and stable `order: NN`; `source` and `source_file` are provenance only. Missing audience is unmapped, not universal, and client-only wording stays scoped to its declared client. The shared view is consumed by both OpenCode and VS Code, so an OpenCode-only rule is rejected until an OpenCode-specific view exists.

The registry currently has no importer from `~/.rules`. Until the adapter export story adds that path, changing a source fragment does not update client views. Do not edit registry nodes as canonical rule changes or publish a stale view as if it reflected `~/.rules`.

The source, scope, preview, drift, backup, and readback contract is documented in [instruction-publication-contract.md](../.specs/reqs/instruction-publication-contract.md). Four rule routes are currently verified; the manifest keeps three planned harness targets marked `NOT_WIRED` and records Gemini and Hermes as skipped or unverified. The seven-client coverage requirement remains open until those three planned routes are wired or evidence changes the requirement.

## Inspect current views

From `C:\Users\user\.harness`, use the registry CLI:

```powershell
$db = (Resolve-Path .\instructions\rules.db).Path
python -m instructions.cli --db $db outline shared --limit 200
python -m instructions.cli --db $db render shared --out .\instructions\shared-preview.md
```

`outline` reports stable node IDs and the current revision is stored per document. `render` writes a preview of a registry view. The registry's `edit`, `insert`, `move`, and `split` commands remain maintenance primitives; their output is not an authored rule change until it is reconciled to the canonical `~/.rules` fragment and reviewed source-to-view mapping.

## Publish a view

Targets must be mapped with their observed baseline digest before publication. The initial registry maps shared, Claude, and Codex views independently. Preview first, then add `--apply`:

```powershell
python -m instructions.cli --db $db publish claude C:\Users\user\.claude\AGENTS.md .\backups\instructions
python -m instructions.cli --db $db publish claude C:\Users\user\.claude\AGENTS.md .\backups\instructions --apply
```

This publisher currently publishes a registry view and checks its stored source hash and destination baseline; it does not ingest `~/.rules`. The adapter export story will add preview, reviewed fragment-to-view selection, per-target drift disposition, backups, exact readback, and no-op reporting before claiming canonical-source propagation. Claude and Codex load their global `AGENTS.md`; VS Code generation reads the shared view through `adapter.py`; OpenCode loads the shared Markdown through `opencode.json` and `sdd-harness.js`.

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
