## CURRENT 2026-11-22 — Shared party-oracle target

- Decision: Preserve the stable `party-oracle` alias and point it to the exact pulled NVIDIA Nemotron 3.5 Bolt E4B Q4_K_M tag through LiteLLM; set the Oracle effort to low and keep its 65,536 context cap. Preserve all other role aliases and Oracle's read-only permissions.
- Basis: The request names the new shared party-oracle and low thinking; Ollama confirms the exact tag is present and reports its 65,536 context. Keeping the alias avoids client-specific route changes.
- Status: LiteLLM was restarted; readiness is healthy, the `party-oracle` alias is listed, and `/model/info` reports the exact Nemotron Ollama target. No inference request has been sent, so tool use and effective reasoning behavior remain unverified.
# Current interpretations

## CURRENT 2026-11-22 — Hermes is a native party-model target

- Decision: Make Hermes model projection part of `adapter.py --target hermes`, with `tiers.toml` as the single role/model source and Hermes' own configuration API as the writer. Set the Leader's LiteLLM alias as the new-session default, the Fighter's alias as the generic delegated-child route, and publish `leader`, `fighter`, `scout`, and `oracle` model aliases for direct selection. Keep `--plugin` scoped to the separate rules-plugin export.
- Basis: A model roster written only into `SOUL.md` does not change the Hermes model route. Hermes' native default delegation provider exposes one model route for every child, so the ordinary adapter can set one Fighter default and selectable role aliases but cannot claim automatic Scout/Oracle child routing.
- Evidence: `tiers.toml` `[binding.litellm]` contains all four party aliases; the Hermes adapter now uses Hermes' native save API, snapshots, and config-path resolution. Two `python adapter.py --target hermes` runs changed the party once, then reported zero changes and no snapshot. Native readback showed `model.default=party-leader`, `delegation.model=party-fighter`, and all four aliases; four direct 4B alias requests returned their expected canaries, and `hermes -z` returned `HERMES_4B_OK`. The first CLI probe waited for an existing Hermes update lock to clear, then passed. The active native config path is `C:\Users\user\AppData\Local\hermes\config.yaml` because `HERMES_HOME` resolves there; `C:\Users\user\.hermes` currently contains only `skills`, so adapter writes follow Hermes' resolved runtime path.

## CURRENT 2026-11-22 — Generic plugin export and direct Oracle fixes

- Decision: Treat `plan-todo` as the available `plan-do` workflow because retrieval returned `plan-do` and no standalone `plan-todo`. Keep `~/.rules` and the existing adapter/RuleStore as the rule source and publisher. Without `--plugin`, preserve the current base managed-block export. With `--plugin --apply`, export and activate the selected target's native rules plugin while preserving base rule bytes and unrelated settings. Claude Code and OpenCode are the first target-specific routes; unsupported plugin targets stop without falling back to base publication.
- Decision: Keep Leader, Fighter, Scout, and Oracle as role contracts over the existing party resolver. Leader may directly perform a bounded fix; Oracle supports separate consult and assigned-fix modes and may implement its assigned repair without another Fighter handoff; Scout remains read-only. Every action stays within the role's explicit native tools and assigned scope; no role label alone forces a context switch.
- Basis: The user requested a target-generic `adapter.py --plugin` mode and stated that an escalated model should be able to finish the fix when that avoids an unnecessary handoff. Existing `sync_instructions()` already owns audience selection and RuleStore publication, while the target adapters have different plugin loaders, so support must be established per native target.
- Evidence: Project requirements #18-#25 in `.specs/reqs/requirements.db`; EARS validation passed for #18-#25; Oracle consultations and source inspection of the incumbent routes; official Claude Code plugin documentation and installed CLI checks. Cowork/Desktop plugin compatibility is not established.

## CURRENT 2026-11-21 — One SSH sync entry point for Claude and Codex

- Decision: Extend `sync-to-remote.ps1` with `-Harness` selection for Claude, Codex, or both; default to both. Keep one SSH sync script. Move `route_instructions.py` from RL_V2's project hooks into `~/.claude/hooks`, register it in global Claude settings, and have the sync merge that managed handler while preserving all unrelated remote settings and hooks. Export Codex's global `AGENTS.md`, its `.tessl/RULES.md` dependency, and all selected packages in `~/.agents/skills`; preserve client configuration and credentials.
- Basis: The operator wants one SSH sync script for multiple harnesses and the global hook fails when its project-specific path is unavailable. The route hook uses `CLAUDE_PROJECT_DIR` to read the active project's `instructions.md`, so it belongs under the Claude home while its context remains project-scoped. Remote inspection found Codex CLI 0.171.0 and its existing `/root/.codex/config.toml` and auth, but no `/root/.codex/AGENTS.md`, `/root/.agents/skills`, or `/root/.tessl/RULES.md`. The local native skill projection contains 29 selected packages.
- Evidence: Local/remote filesystem and CLI probes; `sync-to-remote.ps1`; `adapter.py` Codex native skill target contract; local global-hook invocation; completed both-harness sync; remote settings comparison against the pre-merge backup; three remote hook cases covering instructions, spaces in the project path, and absent instructions; Codex `AGENTS.md` and `.tessl/RULES.md` SHA-256 matched local files, and 29 skill files passed readback.

## CURRENT 2026-11-21 — Context assembly in the shared instruction export

- Decision: Keep one audience-scoped `.rules` fragment in the existing ordered exporter; do not add retrieval behavior, storage, or a separate exporter path. Preserve the current target-drift guard rather than force-rebaseline Codex or Claude.
- Basis: The reference describes context orchestration as selecting, scoping, assembling, and verifying information. The no-write preview selected the fragment in all seven declared views. The requested Codex and Claude baseline transfers then failed because each current target digest differs from its prior RuleStore owner, so the exporter refused transfer without changing either target. The remote sync independently completed and copied the fragment.
- Evidence: `docs/references/context_layer.md`; Codex prior/current digests `043cfe8b9aaafad1443f8601a7c4e5ac1be1b927666166d0ba5ae8838ce5bf1d` / `d01ef9466e33c04a7777f0ed4c73befaf46380dfbf51d2d33b11ffeb953a0b2b`; Claude prior/current digests `b60b9115fbab54b89fb3b429e3e2496d5903b87951da0a2e5c759996b0b2dfb8` / `1b3ac78dbc7c0dd8469dd83e8c83f3a5da586c815d6d94a75f9d3b8513ec9ff2`; remote SHA-256 equals local `055-context-assembly.md`. The earlier preview-only disposition is preserved in [dated history](../../docs/playbooks/history/memory-and-harness-integration-2026-11-21.md).

## CURRENT 2026-11-21 — Request framing across harness instructions

- Decision: Put the four-part request frame (Role/persona, Task/goal, Context/requirements/input with falsifiable evidence, Format/instructions/output) under the Operating Contract in the canonical operating rule and both live Claude/Codex instructions; retain the existing next-step rule from Codex. Do not merge Claude's 30-second command cutoff or sandbox-bypass instruction.
- Basis: The operator explicitly requested this frame for any incoming request. Live-copy comparison found the Codex next-step rule absent from the canonical Operating Contract; the 30-second cutoff conflicts with the current bounded-test policy, and the sandbox-bypass instruction conflicts with current permission controls. The live documents have no instruction-registry markers, so direct edits avoid appending a duplicate full registry view.

## SUPERSEDED 2026-11-21 — Claude-only remote payload

Superseded by the multi-harness SSH sync decision above; prior basis is preserved in [dated history](../../docs/playbooks/history/memory-and-harness-integration-2026-11-21.md).

## CURRENT 2026-11-18 — Canonical instruction source and publication views

- Decision: Treat `~/.rules/*.md` as the only authored source of instruction rules; treat SQLite as revisioned publication views, target mappings, and delivery receipts. Require explicit `harnesses` and stable `order`, preserve unmanaged client text, preview without writes, refuse drift, back up changed targets, verify exact readback, withdraw stale managed rules when a mapped audience empties, and report known unsupported clients without claiming runtime parity. T4 implements seven native export encoders and per-client views; T5 owns fresh-client loader acceptance. Keep live publication gated until selected target baselines are mapped and T5 verifies loaders.
- Basis: The existing requirements say rules are authored at `~/.rules` and project seven harnesses. The initial scan found 55 source fragments, zero with approved audience/order, 54 unmapped, and one superseded; the 2026-11-18 audience review supersedes that count. Scratch acceptance passed all seven output routes, preservation, unique target ownership, source receipts, read-only preview, Claude audience withdrawal, mixed supported/unsupported audiences, and renderer-specific managed-content removal. Requirements #5–#14 in `.specs/reqs/requirements.db` describe the publication contract; global Specs decision IDs #63–#64 were not found by a follow-up query, so this interpretation and the local contract remain durable records.
- View-consumer rule: the legacy `shared` view remains consumed by OpenCode and VS Code; canonical export uses dedicated per-client views, so OpenCode-only content cannot leak to VS Code. The old shared-view mismatch rule remains applicable only to legacy shared-view publication.
- Audience review: 39 of 55 top-level fragments now have explicit reviewed `harnesses` and stable filename-prefix `order`; 15 remain unmapped because their text depends on client-specific loading, memory/skills capabilities, repository scope, an unresolved include target, or agent/delegation interfaces, and one superseded fragment remains excluded. General operating rules target all seven supported clients; the Claude spec-gate rule and Claude/Codex/Copilot memory-bank protocol retain narrower audiences. The seven-client preview passed without changing the registry or target files. No baseline was mapped and no live output was published.
- Supersedes the 2026-11-18 integration-backport interpretation below, which proposed extending registry publication before resolving the canonical source conflict. Its original wording is preserved in [interpretations-history-2026-11-18.md](interpretations-history-2026-11-18.md).

## 2026-12-31 — Dynamic rule context for OpenCode

- Decision: Apply plan-do through the local plan-todo alias and compare programmatic selection with summarization as an experiment. Basis: the latest request reopens both as candidates and the capability-cone draft prohibits scoring on its runtime route. Feature 14 already owns implementation.

## Superseded interpretation pointer — integration backport planning (2026-11-18)

- Original decision and basis moved to [interpretations-history-2026-11-18.md](interpretations-history-2026-11-18.md); T1 established that `~/.rules` has no importer and the SQLite editing-authority wording conflicts with the existing canonical-source requirement.

## 2026-11-18: Tower defense rerun handoff

- Decision: Use the planning portion of plan-do for Todo #4 and stop at the checklist. Base the six-arm rerun on the original first game prompt, with a common Ninja Multi-Config build under x64 MSVC and independent verification. Basis: plan-todo is absent as a standalone skill, the operator requested a Luna handoff, and the available CMake lacks the VS 2026 generator.

## 2026-11-18: SATNA transcript capture and deployment

- Decision: Index PreCompact transcripts only when the host supplies transcript path, workspace, and session identity; skip the hook in VS Code because it does not write the Claude JSONL source. Keep the deployed analyzer source change separate from live service completion until the NSSM service can be restarted.
- Basis: Isolated tests proved scoped capture and retrieval, while the connected Specs MCP still returned the pre-change prefix-collision result; existing service records require Administrator access to restart.

## 2026-11-17: SATNA feature review

- Decision: Use the planning portion of plan-do and the workspace Todo queue for the feature review. Basis: the named plan-todo skill was absent from the retriever and local skill roots, and the requested deliverable was a review queue.

## 2026-11-17: SATNA reference integration

- Decision: Extract reusable features from the eight local checkouts and apply Harbor's separate-verifier pattern to the existing paired eval spec. Basis: the saved arms report process status only, the declared requirement coverage depends on an arm-specific Specs DB, and the existing RSI process already governs promotion.

## 2026-11-14: side-by-side project MCP deployment

- Decision: Serve the updated workspace-scoped Specs MCP on port 8058 and register it in OpenCode as `specs-project`; retain the existing 8057 service as backup.
- Basis: Restarting the NSSM-managed service returned Windows `OpenService(): Access is denied`, while the user identified MCP as backup and asked to focus on completing the task. A separate user-mode endpoint passed health, discovery, project write/query, artifact containment, and OpenCode/Gemma invocation checks without altering the 8057 endpoint.


## 2026-11-14: project specification ownership and order

- Decision: Store each project's requirement registry at `.specs/reqs/requirements.db` and write detailed design artifacts under dedicated `.specs` subfolders.
- Basis: The harness Specs MCP CRUD tools previously wrote to one global database, which could mix unrelated project requirements; the operator requested project-local registries and explicit folder population order.
- Decision: Populate requirements, business use cases, entity model, system use cases, and functional diagrams sequentially.
- Basis: Each later artifact depends on a prior stage, and the entity model must exist before system use cases assign operations to entities.
- Decision: Use globally unique `UC-XXX` IDs across the business and system use-case directories, and standard EARS comma forms validated by the current Specs MCP validator.
- Basis: The retrieved use-case validator requires unique three-digit UC IDs, and the deployed EARS validator accepts comma-form triggers such as `When ..., the system shall ...`.
