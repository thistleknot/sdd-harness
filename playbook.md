<!-- NO GOVERNING SPEC. Basis: operator instruction 2026-10-13 ("write the FULL plan to plan.md"), then operator's stated order: playbook.md (conceptual design), specs, plan.md (local todos), agentic-kanban. Requirements for this design live in specs.db REQ #39-#44. -->
# Playbook: Route new features through an agentic-kanban board

Date: 2026-10-13. Stage 1 of 4 (playbook, specs, plan.md, board). Conceptual design only. Specs: specs.db REQ #39-#44. Todos: plan.md.

## 1. Objective (operator's words)

> "this is a feature for .harness specifically (agentic-kanban) to handle breaking down requests into llm agent backed git worktrees to implement features through a structured board that accepts the feature"

> "install the APPROACH into ~\.harness so it becomes global and then export to codex and claude so downstream project sessions pick it up"

> "I was thinking agentic-kanban as an mcp server honestly"

> "of course this will extend the time to do code, it will be much more principled"

Stated goal: every new feature requested in any project is broken into stories, each story implemented by an LLM agent in its own git worktree, and a story lands only when the board accepts it.

Actual need: a principled, enforced path from feature request to merged code that follows the operator into every project without per-project setup, and cannot be skipped by the implementing agent grading its own work.

Concern raised by the operator and handled in section 6: the "hoses must connect to the right nozzles". Calls defined inside a framework and calls defined outside it in a harness could nest.

## 2. What was examined

Agent Kanban (github.com/saltbo/agent-kanban), cloned to `.tmp/kanban` (scratch, gitignored). Observed:

- It is a Cloudflare Worker (Hono API + React SPA) with a D1 database. `wrangler.toml:16-19` points at `https://id.realmroot.dev/api/auth` (sign-in) and `https://enbor.realmroot.dev` (execution).
- README: "Full sign-in, Agent, Machine, Session, and GitHub flows also require access to the configured Realmroot and Enbor services" and need secrets in `.dev.vars`. The OIDC client id in `wrangler.toml` belongs to the author's deployment.
- Its server makes no LLM calls. A grep for `anthropic|openai|claude-|gpt-` over `server/` and `shared/` matches only the runtime enum `["enbor","claude-code","codex","copilot"]` (`routes.ts:186`, `constants.ts:2`). Sessions run in Enbor, not in the Worker.
- Agents reach it through `realmroot toolbox` calls and four skills (`ak-worker`, `ak-maintainer`, `ak-task`, `ak-plan`) that fix the call order. A claim records a signed runtime and Session binding.
- Task lifecycle: `Todo -> assign -> claim -> In Progress -> submit review -> In Review -> (reject -> In Progress | complete -> Done)`, `cancel` from Todo. The assignee cannot accept or reject its own submission. Tasks can depend on tasks; cycles are rejected.
- License: Functional Source License 1.1 (Apache 2.0 after two years). Not reviewed beyond the README summary.

Conclusion: the real tool cannot run as a local-only board and its call sequence is built on its own identity checks. A generic wrapper in front of it would skip those. Its model is worth borrowing; its code and hosted services are not installed.

## 3. Decisions

Each decision answers the operator's choice directly, credits what was right, gives the alternative, and states when the other choice wins.

### D1. Borrow the approach, do not install Agent Kanban
- Decision: build a small board inside `~/.harness`; take states, dependency rule and review gate from Agent Kanban.
- Right in the operator's framing: the structure (features, stories, dependencies, independent review) is the principled part.
- Why not the real tool: it needs hosted sign-in and execution, so task titles and acceptance criteria would live on third-party servers, and the OIDC client in the repo is not ours. Not verified: Realmroot's terms, whether localhost redirects are allowed, whether Enbor can run Claude Code beyond the enum name.
- Would flip if: the operator wants the web UI and live session observation enough to accept the hosted dependency; then run the real tool once and give it its own onboarding task.

### D2. The board is an MCP server (stdio, fastmcp)
- Decision: server named `agentic-kanban`, registered once in `harness.json`.
- Right in the framing: `adapter.py` already projects every server in `harness.json` into Claude, Codex, opencode, Kiro, pi, Copilot and VS Code, so one registration reaches the other harnesses. Codex is the exception today: `sync_codex` writes `~/.codex/mcp.json`, which Codex does not read (observed 2026-10-13: `codex mcp list` shows only `rea`, none of the harness servers). Codex reads `[mcp_servers.*]` in `~/.codex/config.toml`, so the Codex projection needs its own fix (task in plan.md).
- Alternative considered: no tool layer; agents edit a ledger file, as `playbook.py` does today. No ordering to learn, but nothing outside the model enforces the rules.
- Would flip if: the live run shows models cannot follow the tool flow; then fall back to the ledger file plus a checking hook.

### D3. No service, one shared SQLite file
- Decision: each session spawns its own stdio process. State is `~/.harness/board/board.db` with WAL mode. Rows are keyed by project. No daemon, no Windows service, no per-project instance.
- Alternative: one HTTP server as a Windows service (as `specs/register-specs-service.cmd` does for the specs MCP). It would still not know which project a call belongs to, and adds a service to keep alive.
- Would flip if: sessions must see each other's changes in real time beyond what a shared file gives, or the board needs a UI.

### D4. Project key is the repo's common git directory
- Decision: key = `git rev-parse --git-common-dir` resolved to an absolute path.
- Why: `--show-toplevel` inside a story's worktree returns the worktree itself, so a session there would open a second, empty board. The common directory is identical for the main checkout and every worktree.
- Not yet tested: behavior for repos that are themselves submodules or bare repos.

### D5. Project root is a tool argument, not the server's working directory
- A globally registered stdio server's cwd is not guaranteed to be the project. Every tool call carries the root; the hook injects it into the prompt.

### D6. Explicit trigger
- Decision: a prompt starting with `feature:` or `/feature` fires the hook.
- Alternative: infer "new feature" from free text. It would fire on bug reports and questions, so rejected. Would flip if a classifier is shown to separate the two on real prompts.
- Open: whether Codex has a prompt-submit hook event (section 9).

### D7. Review gate: a different session accepts
- Decision: accept is refused when the reviewing session equals the assigning session. The reviewer sees only the diff, the acceptance checks and their output, never the implementer's context.
- Operator's alternative, offered but not chosen: a human accepts. Both can coexist (a story may require human accept).
- Weakness stated bare: session identity is whatever the caller passes, so a model could pass another name and accept its own story. Until identity the caller cannot choose is shown to exist (see section 9), the gate is advisory.

### D8. Extend the incumbent hook
- `claude/hooks/playbook.py` already handles `architect` on UserPromptSubmit and parses ledger layers. The `feature:` trigger lands inside it, not in a new hook. Search for other incumbents found none for worktrees or a board.

## 4. Architecture

```
user prompt "feature: ..."
   -> hook (playbook.py) injects: decompose into stories, use agentic-kanban tools, project root
   -> session calls agentic-kanban MCP (stdio process per session)
        -> board.py   (SQLite store, state machine, dependency rule)
        -> worktrees.py (git worktree add / merge / remove)
   -> doer subagent works one story inside .worktrees/<story>
   -> reviewer session (different identity) reads diff + checks, accepts or rejects
   -> accept: merge story branch, remove worktree
```

Rules of the layout:
- The board server makes no LLM calls. It stores state and runs git. LLM work happens only in harness sessions: the story's implementer and the reviewer.
- Sequencing lives in the server's state machine, not in the model's memory. Every tool reply names the next allowed action.
- One shared file, no cross-process cache.

## 5. Data model and state machine

Tables (all rows carry `project_key`):

- `feature(id, project_key, title, request_text, status, created_at)`
- `story(id, feature_id, project_key, slug, title, acceptance_checks, status, assignee_session, reviewer_session, branch, worktree_path, review_note, created_at, updated_at)`
- `story_dependency(story_id, depends_on_story_id)` with a cycle check on insert
- `event(id, story_id, kind, session, at, detail)` append-only audit

Story states: `todo`, `in-progress`, `in-review`, `done`, `cancelled`.

Transitions (anything else is rejected by the server):

```
todo         -> in-progress   claim (all dependencies done; creates worktree + branch)
in-progress  -> in-review     submit (records the verification output)
in-review    -> done          accept (reviewer != assignee; merges branch; removes worktree)
in-review    -> in-progress   reject (reviewer note required)
todo|in-progress -> cancelled cancel (removes worktree)
```

Feature status derives from its stories; it is not stored independently of them.

## 6. Nesting and the "right nozzle" concern

Operator concern: calls defined in the framework plus calls defined in the harness could nest.

- Real Agent Kanban: no nesting inside it (no LLM calls in its server). Nesting would occur if Enbor launched a `claude-code` or `codex` session that loaded the harness hook, saw `feature:`, and planned a second layer. Not applicable while the real tool is not installed.
- This board: guards.
  1. The hook ignores prompts from a subagent and anything running inside `.worktrees/`.
  2. Story prompts are written so they never begin with `feature:`.
  3. The server holds no LLM client, so it cannot call back into a harness.
- Not yet tested: that guard 1 can tell a subagent prompt from a user prompt in each harness's hook payload. The hook payload fields differ by harness and have not been compared.

## 7. Tool surface (agentic-kanban MCP)

Every tool takes `project_root` and `session`. Replies include `next_action`.

| Tool | Effect | Refuses when |
|---|---|---|
| `create_feature(title, request_text)` | new feature | root is not a git repo |
| `add_story(feature_id, title, acceptance_checks, depends_on[])` | new story in `todo` | dependency creates a cycle; story already past `todo` |
| `list_stories(feature_id?)` | read | none |
| `claim_story(story_id)` | `todo -> in-progress`, creates worktree and branch | a dependency is not `done`; working tree dirty; slug exists |
| `submit_story(story_id, verification_output)` | `in-progress -> in-review` | caller is not the assignee; verification output empty |
| `accept_story(story_id)` | `in-review -> done`, merge, remove worktree | caller equals assignee; merge conflicts |
| `reject_story(story_id, note)` | `in-review -> in-progress` | note empty; caller equals assignee |
| `cancel_story(story_id, reason)` | to `cancelled`, remove worktree | story already done |

Exact signatures belong to the spec layer.

## 8. Worktree mechanics

- Create: `git worktree add <project>/.worktrees/<story-slug> -b story/<story-slug>` from the project's default branch.
- `.worktrees/` is added to the project's `.gitignore` if absent (the server proposes the edit; it does not rewrite the file silently).
- Merge: on accept, merge `story/<slug>` into the default branch; on conflict the accept is refused and the story stays `in-review` with the conflict listed.
- Remove: `git worktree remove` plus branch delete after merge or cancel. A dirty worktree refuses removal and is reported, never forced.
- Not yet decided: merge strategy (merge commit vs squash). Needs an operator preference or a default recorded in the spec.

## 9. Open questions (NOT TESTED)

Ordered by what blocks the most.

1. **Can the gate be real? Answered for Claude: no.** Probe 2026-10-13: a main Claude session and an `Agent` subagent each called `whoami` on the board server and both got the same pid (`MAIN_PID=184120 SUBAGENT_PID=184120`), so a subagent shares its parent's stdio server process and process identity cannot tell implementer from reviewer. The `session` label is whatever the caller passes. The review gate therefore stops accidents (the observed runs used distinct `doer-*` and `reviewer-*` labels and one rejection round trip worked) and does not stop a model that chooses to pass the same label. Codex is not answered: the Codex subagent launch failed in the headless probe. A gate a model cannot talk its way past needs a human accept or a reviewer identity the board issues out of the model's reach; neither is built.
2. **Codex trigger: answered, one step still open.** Codex fires `UserPromptSubmit` (official Hooks page, learn.chatgpt.com/docs/hooks, fetched 2026-10-13). Input is JSON on stdin with `prompt`, `cwd`, `session_id`, `transcript_path`; plain stdout or `hookSpecificOutput.additionalContext` is added as developer context, which is the same shape the Claude hook already emits. Hooks load from `~/.codex/hooks.json` or inline `[[hooks.<Event>]]` tables in `~/.codex/config.toml`, and user-level hooks do not depend on project trust. Matchers include `Bash`, `Edit|Write` and `mcp__<server>__<tool>`. Not yet tested: Codex also has a persisted-hook-trust step (the CLI has `--dangerously-bypass-hook-trust`), so a hook that is written may still need approving once before it fires. Subagent hooks carry the parent's `session_id`, so the Codex hook cannot tell a subagent by session id; the subagent guard needs another field and that has not been found.
3. **Do models follow the tool order in practice?** Only the live run answers it, in both Claude and Codex.
4. **Hook payload differences** between Claude, Codex and the VS Code shim for the subagent guard (section 6).
5. **Merge strategy** (section 8).
6. **Submodule and bare-repo behavior** of the project key (D4).
7. **Real Agent Kanban terms and local-login feasibility.** Only matters if D1 flips.

## 10. Non-goals

Web UI, live session observation, GitHub app, multi-machine sync, hosting any service, replacing the existing `architect` / playbook flow, and running the real Agent Kanban.

## 11. Acceptance for the whole design

Done means all of:
1. T8 passes in Claude and in Codex, with the raw lines surfaced.
2. A story cannot reach `done` without a submit and a reviewer session different from the assignee's, or the gate is documented as advisory with the evidence for why.
3. A session opened inside a story worktree sees the same board as the main checkout.
4. A subagent prompt and a story prompt do not re-trigger intake.
5. Every new file has a manifest row and a spec citation in its header.

## 12. Risks

- The review gate is advisory until open question 1 is answered.
- Models may skip or reorder tool calls; the server rejects illegal moves but cannot make the model call anything.
- A global hook change affects every downstream project; a bad trigger regex would fire everywhere. T5 tests the negative cases before export.
- `adapter.py` edits are shared by two tasks; run sequentially.
- Extra time per feature is accepted by the operator ("it will be much more principled").
