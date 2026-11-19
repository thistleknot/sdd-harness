# Instruction publication contract

**Status:** Current design contract for Kanban feature 15, story T2. The importer and adapter export are not implemented yet; T4 owns those changes.

**Authority:** Specs decisions #63–#64 and project requirements #5–#10.

## Ownership and flow

`C:\Users\user\.rules\*.md` is the authored source. The 55 Markdown fragments contain migration provenance such as `source` and `source_file`; those fields identify where text came from and do not grant publication scope. A fragment is eligible only with an explicit, reviewed `harnesses: [...]` list and stable `order: NN` frontmatter. An omitted audience is unmapped, not universal; an unknown harness name is an error; a known harness without a supported destination is reported and skipped. The existing design already uses these frontmatter fields, so no separate mapping file is introduced. SQLite keeps ordered, revisioned view structure, target baselines, and publish receipts. It must not become a second authored source.

The publication flow is:

`approved ~/.rules fragment -> explicit source-to-view mapping -> rendered SQLite view -> mapped client destination -> exact readback receipt`

Shared text may reach multiple views only after review of placement in each view. A client-only fragment declares only that client's name in `harnesses`. Existing client-only material stays in its view and destination. A missing audience produces `unmapped`; an unsupported declared target produces `unsupported`; neither is permission to broadcast.

## Preview and apply behavior

Preview is read-only. For every selected destination it reports the source fragment and digest, view and revision, destination path, recorded baseline digest, current digest, planned digest, and disposition: `would_write`, `unchanged`, `drift_refused`, `unmapped`, or `unsupported`.

Apply considers each explicitly selected destination independently. If its current digest differs from the recorded baseline, that destination is refused without modifying its bytes or timestamp. Other selected destinations may proceed and must receive separate results. A changed destination is backed up before writing; publication then verifies exact bytes by readback and records source revision/hash and destination digest. If planned bytes already match the destination, publication performs no write and preserves its timestamp.

The adapter must expose instruction publication as a targetable operation. MCP, skills, and other adapter targets must not be required for a rule-only export to run.

## Contract cases

| Case | Input and mapping | Preview expectation | Apply expectation | Current implementation status |
| --- | --- | --- | --- | --- |
| Approved shared rule change | An approved edit to `~/.rules/010-operating-core.md` declares `harnesses: [claude, opencode, codex, vscode]` and `order: 10`. | Report all four destinations, their current and planned digests, and no file writes. | Back up and update only changed mapped outputs, verify exact readback, and leave the output unchanged on a repeated run. | Contract defined; the source fragment has no explicit audience today, and no `.rules` importer or adapter rule-export route exists yet. |
| Client-only rule | A fixture fragment declares `harnesses: [claude]` and a stable order. Its `source: claude` provenance alone is not sufficient to create this scope. | Show the Claude destination; report other clients as unmapped or unsupported. | Publish only the Claude destination and preserve shared, Codex, OpenCode, and VS Code output bytes. | Contract defined; fragment scope mapping is not implemented yet. |
| Drifted destination | A selected generated destination has bytes different from its recorded baseline. | Report `drift_refused` with expected and observed digests, without writes. | Preserve the drifted file and timestamp, refuse that target, and report outcomes for any other selected target independently. | Existing registry publication has digest checks; the `.rules`-to-adapter path has not been implemented or exercised. |

These cases validate the intended contract, not the current runtime. T4 must implement the importer and isolated publication path; T5 must exercise the three cases on scratch destinations before claiming propagation.

## Client routes from T1 inventory

| Client | Manifest target | Current loader/writer evidence | Disposition |
| --- | --- | --- | --- |
| Claude Code | `C:\Users\user\.claude\AGENTS.md` | `CLAUDE.md` imports `AGENTS.md`; registry publisher writes the mapped view; `sync-to-claude.ps1` skips the file after registry setup. | Supported route; canonical ingestion pending T4. |
| OpenCode | `C:\Users\user\.config\opencode\harness-registry-shared.md` | `opencode.json` and `plugins/sdd-harness.js` load the shared Markdown; registry publication currently writes it. `adapter.py sync_opencode` writes MCP configuration only. | Supported shared route; canonical ingestion pending T4. |
| Codex CLI | `C:\Users\user\.codex\AGENTS.md` | Codex loads its global `AGENTS.md`; the registry publisher writes the Codex view. | Supported route; canonical ingestion pending T4. |
| VS Code | `C:\Users\user\AppData\Roaming\Code\User\prompts\harness-core.instructions.md` | `adapter.py sync_vscode` renders the SQLite shared view into this prompt file. | Supported shared route; canonical ingestion pending T4. |
| Pi | `C:\Users\user\.pi\agent\extensions\harness-steering\` | Installed `retrieve-skills` extension is separate; `harness-steering` is not installed. | Planned target, `NOT_WIRED`; T4 must verify native loading and preserve the seven-client coverage requirement. |
| Kiro | `C:\Users\user\.kiro\steering` | Native steering files are client-specific; no common-rule registry map or publisher was found. | Planned target, `NOT_WIRED`; preserve existing files and wire only after confirming file-level scope behavior. |
| GitHub Copilot CLI | `C:\Users\user\.github\copilot-instructions.md` | Current projection covers MCP configuration and hooks; no live shared-instruction destination was found. | Planned target, `NOT_WIRED`; verify the intended user-level path before writing. |
| Gemini CLI | None verified | CLI is not installed. | Skip and report unverified. |
| Hermes | None established | No shared rule renderer or live instruction destination was found. | Skip and report unsupported. |

## Acceptance boundary

T2 is complete when this contract agrees with the requirements, README, manifest, and T1 evidence. It does not mean rules now propagate from `~/.rules`; that claim remains blocked until T4 implements the source importer and T5 verifies real loader outputs.
