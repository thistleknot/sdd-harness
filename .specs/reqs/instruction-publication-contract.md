# Instruction publication contract

**Status:** Current design contract for Kanban feature 15. T2 settled source ownership and audiences; T4 adds the adapter execution contract; T5 owns fresh-client acceptance.

**Authority:** Project requirements #5–#14 in `.specs/reqs/requirements.db`; the current decision and its evidence are recorded in `.specs/reqs/interpretations.md`. The attempted global Specs decisions #63–#64 were not returned by a later query and are not treated as persisted records.

## Ownership and flow

`C:\Users\user\.rules\*.md` is the authored source. The 55 Markdown fragments contain migration provenance such as `source` and `source_file`; those fields identify where text came from and do not grant publication scope. A fragment is eligible only with an explicit, reviewed `harnesses: [...]` list and stable `order: NN` frontmatter. An omitted audience is unmapped, not universal; an unknown harness name is an error; a known harness without a supported destination is reported and skipped. The existing design already uses these frontmatter fields, so no separate mapping file is introduced. SQLite keeps ordered, revisioned view structure, target baselines, and publish receipts. It must not become a second authored source.

The publication flow is:

`approved ~/.rules fragment -> explicit source-to-view mapping -> rendered SQLite view -> mapped client destination -> exact readback receipt`

Each view has a declared consumer set. Current sets are `claude -> {claude}`, `codex -> {codex}`, and `shared -> {opencode, vscode}`. A fragment may enter a view only when every consumer of that view is included in the fragment's explicit `harnesses` audience. A fragment scoped to one member of a shared view is rejected as `audience_view_mismatch`; it is never broadened to the other consumer. Publishing such a fragment requires a dedicated view and destination for that client. Shared text may reach multiple views only after review of placement in each view. Existing client-only material stays in its view and destination. A missing audience produces `unmapped`; an unsupported declared target produces `unsupported`; neither is permission to broadcast.

## Preview and apply behavior

Preview is read-only. For every selected destination it reports the source fragment and digest, view and revision, destination path, recorded baseline digest, current digest, planned digest, and disposition: `would_write`, `unchanged`, `drift_refused`, `audience_view_mismatch`, `unmapped`, or `unsupported`.

Apply considers each explicitly selected destination independently. If its current digest differs from the recorded baseline, that destination is refused without modifying its bytes or timestamp. Other selected destinations may proceed and must receive separate results. A changed destination is backed up before writing; publication then verifies exact bytes by readback and records source revision/hash and destination digest. If planned bytes already match the destination, publication performs no write and preserves its timestamp.

The adapter must expose instruction publication as a targetable operation. MCP, skills, and other adapter targets must not be required for a rule-only export to run. If a previously published client has no approved fragments left, publication removes only its managed region using the same target-baseline, backup, and exact-readback checks; a client with no prior mapping remains untouched. Known harnesses without a native route, currently Gemini and Hermes, are reported and skipped while supported members of the same audience continue.

## Contract cases

| Case | Input and mapping | Preview expectation | Apply expectation | Current implementation status |
| --- | --- | --- | --- | --- |
| Approved shared rule change | An approved edit to `~/.rules/010-operating-core.md` declares `harnesses: [claude, opencode, codex, vscode]` and `order: 10`. | Report all four destinations, their current and planned digests, and no file writes. | Back up and update only changed mapped outputs, verify exact readback, and leave the output unchanged on a repeated run. | Export path is implemented; current source fragments remain unmapped until their audiences and order are reviewed. |
| Client-only rule | A fixture fragment declares `harnesses: [claude]` and a stable order. Its `source: claude` provenance alone is not sufficient to create this scope. | Show the Claude destination; report other clients as unmapped or unsupported. | Publish only the Claude destination and preserve shared, Codex, OpenCode, and VS Code output bytes. | Per-client output filtering is implemented; the live source has no approved audiences yet. |
| OpenCode-only rule | A fixture fragment declares `harnesses: [opencode]` and a stable order. The legacy `shared` registry view is consumed by OpenCode and VS Code. | Select only the OpenCode export view; do not add the fragment to the legacy shared view. | Publish only the OpenCode destination and preserve VS Code output bytes. | Dedicated per-client export prevents shared-view leakage; the legacy shared-view mismatch check does not govern this route. |
| Drifted destination | A selected generated destination has bytes different from its recorded baseline. | Report `drift_refused` with expected and observed digests, without writes. | Preserve the drifted file and timestamp, refuse that target, and report outcomes for any other selected target independently. | Digest checks, backups, exact readback, and isolated target disposition are implemented; targeted scratch acceptance passed. |
| Audience withdrawal | A mapped client's last approved source fragment is removed, superseded, or no longer names that client. | Plan removal of only the adapter-managed region; preserve unmanaged bytes and use normal baseline checks. | Back up and remove stale generated rules, verify exact readback, and retain the mapping for repeatable no-op behavior. | Implemented; scratch Claude withdrawal preserved user-owned text and removed the prior rule. |
| Known unsupported audience | A fragment declares `harnesses: [claude, hermes]`, where Claude has a renderer and Hermes does not. | Report Hermes as unsupported and include the fragment only in Claude's selected view. | Publish Claude normally and skip Hermes without failing the supported route. | Implemented; scratch preview reported Hermes and kept Claude eligible. |

These cases define the contract. T4 implements the importer and isolated publication path for all seven requested native output routes; T5 must exercise fresh-client loading on scratch destinations before claiming end-to-end propagation. Live `.rules` content remains unpublished until the audience/order review story completes.

## T4 adapter export specification

**Specification layer:** Structural and Behavioral. This change extends the `RuleStore` import/publish boundary and adds an independently targetable adapter operation with ordered preview, baseline mapping, and apply steps.

The adapter reads only top-level Markdown files from `~/.rules`. A fragment is eligible only when its YAML frontmatter contains a nonempty known `harnesses` list and a nonnegative integer `order`; missing scope/order is reported as `unmapped`, malformed frontmatter and names outside the known manifest harness set are errors. Known harnesses without supported destinations (currently Gemini and Hermes) are reported and skipped, while supported recipients still receive the fragment. A fragment with `superseded_by` is excluded. `source` and `source_file` remain provenance and MUST NOT select recipients. Eligible bodies are rendered by ascending `order`, with filename as the stable tie-breaker, and source frontmatter is removed from client output. When a client has a prior publication mapping but no eligible fragments remain, the adapter removes its generated managed content through the usual baseline, backup, and readback checks; without a prior mapping, its target remains untouched.

The adapter maintains one derived SQLite view per client so client-only fragments never enter another client's output. The existing `shared`, `claude`, and `codex` registry documents remain available for their existing maintenance workflows; new export views use generated IDs and are never manually edited. Each view is rendered to a scratch Markdown file, imported into the same `instructions/rules.db` through `RuleStore`, and published only through its mapped target. Existing target text outside the adapter-owned `HARNESS_RULES_START` / `HARNESS_RULES_END` region is preserved. Preview MUST be read-only, including SQLite; only `--map-baseline` and `--apply` may update the registry or targets.

| Client | Native target | Encoding |
| --- | --- | --- |
| Claude | `~/.claude/AGENTS.md` | Markdown |
| OpenCode | `~/.config/opencode/harness-registry-shared.md` | Markdown; preserve legacy loaded text outside the generated markers |
| Codex | `~/.codex/AGENTS.md` | Markdown |
| VS Code | `~/AppData/Roaming/Code/User/prompts/harness-rules.instructions.md` | Additive `applyTo: '**'` prompt Markdown; `harness-core.instructions.md` remains owned by `sync_vscode` |
| Pi | `~/.pi/agent/extensions/harness-steering/index.ts` | TypeScript extension; `before_agent_start` appends the generated instruction body |
| Kiro | `~/.kiro/steering/harness-core.md` | Global steering Markdown with `inclusion: always` |
| GitHub Copilot CLI | `~/.copilot/instructions/harness-rules.instructions.md` | Additive personal modular instruction Markdown with `applyTo: '**'` |

The source fragment audience maps to one dedicated client view per audience member. T4 implements native output routes for Claude, OpenCode, Codex, VS Code, Pi, Kiro, and Copilot using their documented loaders; known unsupported clients Gemini and Hermes are reported and skipped. T5 must verify supported loaders at runtime before any manifest status is promoted to WIRED. A selected client's preview includes its planned target, selected fragment names and source digests, current and planned destination digests, the stored baseline digest, and one of `would_write`, `unchanged`, `drift_refused`, `audience_view_mismatch`, `unmapped`, or `unsupported`. Preview performs no filesystem or SQLite writes. `--map-baseline` records the observed current target digest without publishing; for Claude and Codex, it transfers prior RuleStore ownership only when the existing owner's digest still matches, preserving its publication history. `--apply` requires an existing mapping, refuses a changed target, writes a backup before changed bytes, verifies exact readback, and leaves identical bytes and timestamps untouched. When a mapped audience becomes empty, it clears the managed instructions using the same safety checks. Each target is dispositioned independently.

`adapter.py --target instructions` is preview-only by default; `--client` limits recipients, `--map-baseline` records selected baselines, and `--apply` publishes selected views. The instruction target is independently selectable from MCP, skills, agents, and other service projections. T4 routes are kept separate from MCP and skills targets. Fragments that currently lack `harnesses` or `order` remain unmapped and produce no client bytes. The seven-client coverage requirement remains open; no route is promoted to `WIRED` until downstream loading evidence passes.

## Client routes from T1 inventory

| Client | Manifest target | Current loader/writer evidence | Disposition |
| --- | --- | --- | --- |
| Claude Code | `C:\Users\user\.claude\AGENTS.md` | `CLAUDE.md` imports `AGENTS.md`; registry publisher writes the mapped view; `sync-to-claude.ps1` skips the file after registry setup. | Generated route implemented; fresh-client loading acceptance pending T5. |
| OpenCode | `C:\Users\user\.config\opencode\harness-registry-shared.md` | `opencode.json` and the installed `sdd-harness.js` load this file; the exporter preserves its existing text outside its managed region. | Generated route implemented; existing OpenCode loader acceptance pending T5. |
| Codex CLI | `C:\Users\user\.codex\AGENTS.md` | Codex loads its global `AGENTS.md`; the registry publisher writes the Codex view. | Generated route implemented; fresh-client loading acceptance pending T5. |
| VS Code | `C:\Users\user\AppData\Roaming\Code\User\prompts\harness-rules.instructions.md` | Additive native prompt file; `sync_vscode` continues to own `harness-core.instructions.md`. | Generated route implemented; runtime loading acceptance pending T5. |
| Pi | `C:\Users\user\.pi\agent\extensions\harness-steering\index.ts` | Official extension API supports global TypeScript extensions and `before_agent_start`; deployed loading remains for T5. | Generated route implemented in T4; T5 runtime verification pending. |
| Kiro | `C:\Users\user\.kiro\steering\harness-core.md` | Official docs support global steering and `inclusion: always`; deployed loading remains for T5. | Generated route implemented in T4; T5 runtime verification pending. |
| GitHub Copilot CLI | `C:\Users\user\.copilot\instructions\harness-rules.instructions.md` | Official docs support personal modular `*.instructions.md` files; deployed loading remains for T5. | Generated route implemented in T4; T5 runtime verification pending; prior `~/.github` route was incorrect. |
| Gemini CLI | None verified | CLI is not installed. | Skip and report unverified. |
| Hermes | None established | No shared rule renderer or live instruction destination was found. | Skip and report unsupported. |

## Acceptance boundary

T2 is complete when this contract agrees with the requirements, README, manifest, and T1 evidence. T4 generates all seven requested client formats; T5 still owns runtime loader acceptance. Canonical propagation remains unclaimed until T5 verifies real loader outputs.
