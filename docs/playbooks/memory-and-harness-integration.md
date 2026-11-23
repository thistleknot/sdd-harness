# Memory and harness integration

CURRENT 2026-11-21: R22 and R43-R48 consolidate remote harness sync in one `sync-to-remote.ps1` entry point. It targets Claude and Codex by default, with `-Harness` selecting either or both. Claude keeps its selected instructions and runtime dependencies. The global route-instructions hook lives under `~/.claude/hooks` and is merged into Claude's `UserPromptSubmit` settings without replacing other settings; it reads `instructions.md` from `CLAUDE_PROJECT_DIR` and emits no context when that file is absent. Codex receives global `AGENTS.md`, its `.tessl/RULES.md` import, and all selected native skill packages under `~/.agents/skills`. The both-harness sync completed on `root@192.168.3.17`; readback passed for Claude and all 29 Codex skill packages. Remote Codex `AGENTS.md` and `.tessl/RULES.md` hashes match their local sources, and the existing Codex config and auth files remain present. The no-write preview for R34-R42 selected the context-assembly fragment at order 55 in all seven local client views. The attempted local Codex and Claude instruction exports stopped at baseline transfer because current target digests differ from their prior RuleStore owners; no local client file changed. The earlier remote sync delivered `/root/.rules/055-context-assembly.md`, whose hash matched locally. The superseded Claude-only SSH contract is preserved in [the dated history](history/memory-and-harness-integration-2026-11-21.md); the superseded 2026-11-19 status summary is preserved in [the earlier dated history](history/memory-and-harness-integration-2026-11-19.md).

HISTORICAL STATUS: 2026-10-25 implementation and service-health details are preserved in [the dated archive](history/memory-and-harness-integration-2026-10-25.md).

| Stage | Mechanism | Contract |
|---|---|---|
| IDENTIFY | Normalize workspace and common repository identity | [mandatory] R1 |
| CAPTURE | Keep append-only raw observations and evidence references | [mandatory] R2 |
| DERIVE | Version individual memory records in the existing SQLite store | [mandatory] R2-R4 |
| RECALL | Filter scope before bounded lexical ranking and source opening | [mandatory] R5-R8 |
| CONTINUE | Resume only a matching project handoff | [mandatory] R9 |
| EXPORT | Plan/apply/check selected canonical skill packages for native files and MCP routes | [mandatory] R10-R12, R23-R28 |
| EVOLVE | Implement offline mining and checkpointed evaluation gates | [mandatory] R13-R16 |
| VERIFY | Run bounded deterministic checks after implementation | [contract] R17-R18 |

## Requirements

- R1: Project identity MUST use the normalized full workspace or common Git repository path; basenames MUST be display labels only.
- R2: Every new derived memory MUST retain an immutable raw observation, source reference, origin kind, harness, session, timestamp and epistemic classification.
- R3: Updates and retirement MUST append revisions; raw observations MUST NOT be rewritten or deleted.
- R4: Recall MUST NOT change counters or promote entries; explicit outcome feedback MUST carry evidence and be idempotent by outcome identifier.
- R5: Default project recall MUST include only its project plus explicitly shared reusable memory; working state MUST match its session.
- R6: Project recall without workspace context MUST return an actionable scope error; local MUST remain a project-scope alias.
- R7: Retrieval MUST use SQLite FTS5/BM25, default k=5, maximum k=20 and at most 6000 content characters; source opening MUST enforce the same authorization.
- R8: Unknown, malformed or unsupported legacy metadata MUST remain audit-only; legacy `user` scope maps to shared only when the declared type is `user`. Migration MUST preserve original files and indexed evidence. Markdown imports larger than the per-record limit MUST split deterministically into source-offset chunks without truncation. Generated handoffs and compaction backups MUST stay out of durable imports. Dense retrieval remains optional and off by default.
- R9: Resume MUST select the readable, project-local prompt candidate with the newest modification time. Candidates are the caller workspace prompt, its Git-root prompt, and generated archives whose Project-URI exactly matches the normalized workspace identity; ties MUST resolve by normalized absolute path ascending. Resume MUST NOT select a global or foreign-project archive by recency or basename.
  - Given an older project-local prompt and a newer matching generated archive, When resume runs, Then it selects the generated archive.
  - Given a newer project-local prompt and an older matching generated archive, When resume runs, Then it selects the local prompt.
  - Given only foreign, closed, missing-identity, or unreadable archives, When resume runs, Then it emits no handoff context.
- R10: The adapter MUST support --target skills --skill NAME... with mutually exclusive --apply/--check; the default MUST only plan. `--client NAME...` MAY narrow selected projections; when omitted, existing all-target behavior remains.
- R11: Copies MUST be additive and use timestamped safe-writer backups; selected router targets MUST verify their registered access. Unrelated packages MUST survive. A shared retrieval index is global; reindexing a canonical package makes it available to every client already using that index.
- R23: WHEN `--client` is supplied, the adapter MUST write skill copies only to selected copy targets.
- R24: WHEN `--client` is supplied, the adapter MUST validate only selected router configurations.
- R25: WHEN apply completes with selected router clients, the adapter MUST confirm selected skill membership in the shared index.
- R26: WHEN skill sync refreshes the canonical retrieval index, the adapter MUST report that index visibility is shared across its clients.
  - Given `--client codex claude`, When apply completes, Then no Copilot/OpenCode/Hermes/Pi skill copy is written and the skill is indexed for the selected Codex and Claude routes.
- R27: WHEN Codex is selected, the adapter MUST copy each selected canonical package additively to `$HOME/.agents/skills/<name>` and check every package resource at that destination. A shared retrieval index MUST NOT count as Codex's native skill installation.
- R28: WHEN capability drift checks Codex skills, the declared projection MUST identify both native file copy and MCP route transports while using `$HOME/.agents/skills` as the skill destination. Router membership remains a separate shared-index check.
  - Given a valid canonical skill and `--client codex`, When apply completes, Then Codex's native skill files are present under `$HOME/.agents/skills/<name>` and its configured retrieval route remains independently checked.
- R29: WHEN Claude PreCompact receives a readable `transcript_path`, workspace, and session ID, the hook MUST persist ordered transcript chunks as source-backed session records in the existing memory-index store; IF indexing fails, THEN the hook MUST preserve its payload backup and allow compaction to continue.
- R30: Memory-index tools MUST publish effect-accurate MCP annotations: bounded reads MUST use `readOnlyHint=true`; ordinary appends and revisions MUST use `readOnlyHint=false` and `destructiveHint=false`; retirement, annealing, and reindexing MUST use `destructiveHint=true`; all tools MUST use `openWorldHint=false`. Annotations MUST NOT weaken project/session authorization or source-opening checks.
- R31: WHEN an improvement method is compared, the procedure MUST record its object, stage, label requirement, streaming behavior, scaling mode, and whether the improver itself changes; unsupported or unavailable fields MUST say `not reported` rather than be inferred.
- R32: WHEN candidate harness edits are proposed, the procedure MUST produce two or three behaviorally distinct hypotheses from different lenses, including one that opposes the obvious edit; probes MUST retain a matched control, and composition MUST include only candidates that pass the existing RSI gate. Optional improver updates, task synthesis, and retention checks MUST remain off unless explicitly enabled and measured; enabling them MUST NOT bypass the current frozen-evaluator, held-out, acceptance, or promotion contracts.
- R33: The canonical `recursive-harness-self-improvement` skill MUST be listed in `harness.json`'s default skill packages so the existing adapter projects and checks it using the standard package contract; no RSI-specific adapter path or second skill registry may be added.
- R34: When instruction preview runs, the system shall include each eligible source fragment only in client views named by its explicit audience and place it according to its declared order.
  - Given `055-context-assembly.md` declares seven client audiences and order 55, When instruction preview runs for a declared client, Then that view MUST list the fragment's filename and digest after order 50 and before order 60; a client outside its audience MUST NOT receive it.
- R35: When an agent plans retrieval for a task, the system shall specify the objective, entity and authorization scope, time range, required facts, authoritative source for each fact, and required output shape.
- R36: When retrieval candidates are ranked, the system shall apply authorization and entity-scope filters before relevance ranking. The system shall use structured or authoritative sources for deterministic identifiers, current state, dates, quantities, and calculations; semantic retrieval may find unstructured evidence.
- R37: When evidence is assembled, the system shall retain each selected item's source location, version or timestamp, validity, and scope.
- R38: When evidence is assessed, the system shall keep source authority, freshness, and factual confidence distinct. The system shall use confidence only when it has a defined, calibrated basis.
- R39: When evidence is assembled, the system shall deduplicate and bound it to the task.
- R40: When large deterministic results are retrieved, the system shall preprocess them and preserve necessary supporting records with summaries.
- R41: When sources conflict, the system shall resolve them using authority, version, and validity or expose the unresolved sources.
- R42: When an output is prepared, the system shall verify important claims against evidence, calculations deterministically, and structured outputs against the requested format.
The system shall deliver these rules through the existing canonical `.rules` source and exporter without adding a memory store, retrieval engine, or per-client duplicate rule.
- R12: ~/.skills MUST be the master; reconciliation MUST preserve divergent and unique legacy content before export, and skill synchronization MUST NOT load the full library into Claude natively.
- R13: The runner MUST implement mine/run/verdict with dry execution by default, explicit model execution, call/token/time caps and resumable SQLite checkpoints.
- R14: The evaluator MUST be hashed; held-out outputs MUST NOT reach proposer views; invalid or incomplete runs MUST be NOT TESTED.
- R15: Gates MUST include A/A noise, activation, target headroom, guard regressions, held-out results and matched-budget baseline-k; at most three candidates and one added skill per candidate are allowed.
- R16: Rejections and predicted/observed outcomes MUST remain in history; PASS MUST require separate acceptance before promotion/export.
- R17: Missing/empty code-map session IDs MUST fail open without a marker; Specs startup MUST register every tool before starting stateless HTTP.
- R18: Tests MUST run only after the feature implementation is complete; no OpenCode or model experiments are authorized in this implementation pass.
- R19: Every downstream caller contract (OpenCode plugin, Pi extension, Kiro steering, memory server instructions) MUST state search, then open, then cite, and MUST name `memory_feedback` with an outcome ID and evidence reference.
  - Given the four contract texts, When the acceptance suite runs, Then each contains workspace_root, open_memory and memory_feedback.
- R20: Recall MUST remain local (R7 bounds); a question whose answer spans many items MUST be reported as outside recall scope, not answered from a truncated top-k.
- R21: Derived-memory auto-approval in `mem dream` MUST be off unless the caller passes `--auto-approve`; model confidence alone MUST NOT admit a memory.
  - Given `mem dream --dry-run` without the flag, Then it MUST print that auto-approval is disabled.
- R22: WHEN `sync-to-remote.ps1` runs, the system MUST accept `-Harness` with one or both values `claude` and `codex`, default to both, verify SSH access plus each selected CLI and its local sources, pack every selected archive before upload, upload every archive before extraction, extract additively, and verify every selected destination. IF an SSH/source/CLI/pack/upload check fails, THEN the system MUST stop before replacing destination files and remove its temporary remote staging directory. It MUST retain the one-password SSH-key bootstrap.
  - Given a missing `gzip` or failed `tar`, Then the script MUST stop with the remote unchanged.
  - Given both CLIs and all selected sources exist, When sync runs without `-Harness`, Then Claude and Codex destinations MUST both pass readback.
  - Given only `-Harness codex`, When sync completes, Then Codex's global instruction and selected native skills MUST pass readback and Claude destination bytes MUST remain unchanged.
  - Given only `-Harness codex`, When sync completes, Then the success report MUST NOT claim Claude's managed hook was merged.
  - Given a selected CLI or source is missing, When sync runs, Then it MUST stop before upload or extraction.
  - Given upload fails after staging begins, When sync stops, Then no destination files MUST change and the remote staging directory MUST be removed.
  - Given remote Claude settings contain existing hooks and unrelated keys, When Claude sync completes, Then every prior setting MUST remain and the managed route hook MUST exist exactly once.
  - Given `CLAUDE_PROJECT_DIR` has spaces in its path and contains `instructions.md`, When the managed route hook runs, Then it MUST return valid `UserPromptSubmit` context from that project.
  - Given the active project has no `instructions.md`, When the route hook runs, Then it MUST exit successfully without emitting context.
  - The sync MUST ask for the remote password at most once per machine: when key login fails it installs this machine's public key on the remote with that one prompt, and every later ssh/scp call runs unattended.
- R43: WHEN Claude is selected for remote sync, the system MUST add the vault's Claude instruction files, agents, rules, docs, and hooks under `~/.claude`, and MUST project `.rules/`, `.tessl/RULES.md`, `.skills/GLOSSARY.md`, the `plan-do` and `task-breakdown` packages, `.harness/constitution.md`, `.harness/rules/`, and the declared plan-router hook/helper to their remote home paths. It MUST copy those two skill packages to both `~/.skills/` and `~/.claude/skills/`.
- R44: WHEN Codex is selected for remote sync, the system MUST add the local `~/.codex/AGENTS.md` to remote `~/.codex/AGENTS.md`, copy its `.tessl/RULES.md` import to remote `~/.tessl/RULES.md`, and add every selected package from local `~/.agents/skills/` to remote `~/.agents/skills/`.
- R45: When any harness is selected, the system shall preserve remote client configuration, credentials, and hooks not managed by this sync.
- R46: If any harness is selected for remote sync, then the system shall not copy local `.claude/settings.json`, `.codex/config.toml`, `.codex/auth.json`, or `.codex/hooks.json`.
- R47: The system shall use `sync-to-remote.ps1` as the only per-harness SSH synchronization script; `sync-to-claude.ps1` remains a local tree synchronizer.
- R48: When Claude is configured locally or selected for remote sync, the system shall install `route_instructions.py` under the corresponding user's `~/.claude/hooks/` and register its `UserPromptSubmit` handler in that user's global Claude settings while preserving every existing setting and hook.
- R49: When the managed route hook runs, the system shall read `instructions.md` from `CLAUDE_PROJECT_DIR` and emit no context when that file is absent.

## Structural and behavioral contracts

Extend conversation_store rather than introducing another memory database: scoped
memory entries, FTS cache, append-only revisions, raw volleys and outcome receipts
share its existing SQLite file. New writes normalize identity, validate metadata,
append raw evidence, update one derived entry and its FTS row transactionally.
Lexical reads filter scope in SQL, rank and return stable IDs; open_memory repeats
scope checks and returns the bounded raw source span. Inferred entries remain
identified as inferred. Explicit retirement hides the derived entry only.

Keep existing MCP names and positional arguments. Add workspace_root/session_id/
scope keyword context, source metadata, open_memory, update_memory, retire_memory,
memory_feedback and legacy audit. Legacy repo/local arguments remain aliases.
Reads requiring a project cannot silently fall back to global data. Existing raw
conversation APIs remain available; public reads gain the same project guard.
Claude PreCompact indexes transcript source chunks through `write_record`; the backup
continues to store only the hook payload, and the hook remains fail-open if indexing fails.

Use the existing WorkspaceIdentity and PromotionRouter contracts; add canonical
project URI without introducing a competing identity registry. Keyword routing
can propose a lane but cannot authorize shared memory or durable promotion.

Skills: native copies go to copilot/opencode/hermes/pi; claude/codex/kiro/vscode
use the existing retrieve-skills MCP. Only named packages are exported. Canonical
content wins a divergent path after its legacy bytes have been backed up. Missing
canonical packages are imported with provenance; no mirror purge is allowed.

RSI: three implementation artifacts (round.py, checkers.py, battery.toml) plus a
separate acceptance-test artifact are justified by separate execution, scoring,
data and verification contracts. Mine real correction/error traces deterministically;
use 8 target held-in, 4 target held-out and 8 guard items. Freeze hashes, persist
calls before launching, keep raw outputs, and resume completed items without calls.
Implement the existing campaign gate: 20/20 valid, target headroom >=5/8, target
flips >=5 fixes/0 breaks or >=7 fixes/<=1 break, net above A/A noise, guards within
their band, held-out net >=0 and baseline-k matched by ceiling token ratio. Both
evaluator and budget identities must agree. Optional LLM derivation/consolidation,
graph memory, automatic promotion and automatic model escalation remain off.

## CLOSED

- Latest global handoff and basename-only archive lookup: rejected because recency and a shared repository name do not prove project identity (R9).

- OpenCode tool dispatch as a prerequisite to feature implementation: superseded by the operator's feature-first instruction.
- New memory backends or a Mirascope wrapper: incumbents already own storage and transport.
- Recall count as evidence of utility: a search itself can increment it; R4 separates feedback.
- --thinking as an inference switch: installed OpenCode help defines it as displaying reasoning blocks.
- Reinforce-on-recall decay (stability grows per retrieval; `effective_score`, `grow_stability`): retrieval counts what was searched, not what helped (R4). Never called by the service; removed 2026-10-26.
- Model confidence as the admission signal for derived memories: trust scores accepted mostly poisoned entries in the skill's evidence (agent-long-term-memory R9). Confidence is admissible only if calibrated against helpful/harmful outcomes, which do not yet exist.

## OPEN

Highest-ranked first; the first is the next work item.

1. First gate run on Claude's per-prompt recall (`membank.py` injects dense-only, unscoped results; legacy `mem.py` still promotes at 3 recalls). Arms: no memory, current vector-only, BM25 over raw, hybrid; same reader, judge, k, budget. Both skills call single-vector recall a dead end, but the skill's own gate forbids swapping a stage unmeasured. Status: NOT TESTED.
2. Recurrence admission (agent-long-term-memory R14, flag `--admit`): rule exists, no code. Needs outcome feedback from R19 callers first.
3. Remote Claude hook wiring: the vault `claude/settings.json` commands use Windows paths and include Windows-only integrations; a safe path-translated native settings merge remains unresolved. Syncing hook source files alone does not activate them.
4. Single-source the caller contract through the adapter's instruction cells instead of four hand-kept copies; R19's acceptance test guards drift until then.

## Tasks

- [DONE] F1 Scoped memory, provenance, source-offset imports and continuity pass the local acceptance suite; live memory service serves the SQLite runtime.
- [DONE] F2 One master reconciled: 35 resources imported, 61 divergent copies archived, one unsafe legacy package reported; selected exports and router drift check pass.
- [DONE] F3 Deterministic mining, dry/budgeted runner and offline gate are implemented; dry and paired-gate checks pass, with no model campaign run.
- [DONE] F4 Hooks, Specs startup, policy and caller guidance are reconciled; compile and regression checks pass.
- [DONE] F5 Live health reports the 130-record SQLite store with dense retrieval off; MCP exposes 14 tools and the scoped search smoke passes.

Preconditions: existing stores are backed up; runtime dependencies remain pinned.
Failures: invalid scope/provenance/budget fails explicitly; capture hooks fail open.
Validation: reviewed against the spec skill's structural/behavioral notation,
atomic requirements, acceptance contracts, persistence and closed alternatives.
User approval: Implement the plan, 2026-10-24; no further confirmation is required.
