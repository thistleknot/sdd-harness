# Memory and harness integration

CURRENT 2026-11-02: R27-R28 add Codex's native user-skill file projection alongside its shared MCP route. The common skill lifecycle stays canonical; installation, invocation and discovery checks follow each host. The separate memory evaluation OPEN list is unchanged.

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
- R22: WHEN the remote sync runs, it MUST check SSH access before packing archives, then place the vault's Claude instruction files (CLAUDE.md, SOUL.md, AGENTS.md) and its agents, rules, docs and hooks into the remote `~/.claude`, additively (no deletes), plus the two files CLAUDE.md @-imports (`~/.harness/constitution.md`, `~/.skills/GLOSSARY.md`) at those paths. It MUST NOT copy the framework (`.harness`, `.mcp`, `.skills`): the remote runs only Claude. It MUST NOT write the remote `settings.json`: that file is a merge target holding Windows paths, and until a path-translated merge exists, hooks placed remotely stay unwired (see OPEN). The sync MUST pack and upload every archive before it extracts anything on the remote, and MUST abort without touching the remote if any SSH check, pack or upload fails.
  - Given a missing `gzip` or failed `tar`, Then the script MUST stop with the remote unchanged.
  - The sync MUST ask for the remote password at most once per machine: when key login fails it installs this machine's public key on the remote with that one prompt, and every later ssh/scp call runs unattended.

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
3. Remote Claude hook wiring: `claude/settings.json` commands are `python C:/Users/user/...` and 4 of 22 vault hooks hardcode `C:/Users`; the remote needs a path-translated settings merge before its hooks fire. No script does this (neither the local push nor the remote sync writes settings.json).
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
