# Instruction rule registry

The SQLite registry is the editing authority for the three captured views: `shared`, `claude`, and `codex`. The Markdown files remain client-facing generated outputs. The views stay separate until a rule has been reviewed for text and placement in each destination.

## Inspect and edit

From `C:\Users\user\.harness`, use the registry CLI:

```powershell
$db = (Resolve-Path .\instructions\rules.db).Path
python -m instructions.cli --db $db outline shared --limit 200
python -m instructions.cli --db $db render shared --out .\instructions\shared-preview.md
```

`outline` reports stable node IDs and the current revision is stored per document. `edit`, `insert`, and `move` print a whole-document diff and commit under the supplied revision. Use `split` to expose exact byte spans within a line; the split itself preserves the rendered bytes, and later edits to an individual span change only that span. Insert and move take explicit sibling and document positions; cross-parent movement is rejected until an explicit layout operation exists.

## Publish a view

Targets must be mapped with their observed baseline digest before publication. The initial registry maps the shared harness source, global Claude source, and global Codex source independently. Preview first, then add `--apply`:

```powershell
python -m instructions.cli --db $db publish claude C:\Users\user\.claude\AGENTS.md .\backups\instructions
python -m instructions.cli --db $db publish claude C:\Users\user\.claude\AGENTS.md .\backups\instructions --apply
```

Publication refuses source or target drift, writes through `harness_write`, backs up changed bytes, and verifies exact readback. A second publish of identical bytes is a no-op. Claude and Codex load their global `AGENTS.md`; VS Code instruction generation reads the `shared` document from SQLite through `adapter.py`.

`sync-to-claude.ps1` skips `AGENTS.md` once the registry exists. Use registry publication to update it. If a client-side edit must be retained, save it as a proposal, compare it with the registry render, and apply the reviewed change to the corresponding rule nodes. Do not import over the live document as a shortcut: import replaces that document's node IDs and audit history.

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
