# SDD Harness

A cross-harness Spec-Driven Development system that works identically across Claude Code, opencode, pi, and Kiro. One spec, three+ harnesses. The workflow is the same everywhere — only the model tier adapts.

Built on the same principles as [Kiro](https://kiro.dev)'s structured requirements → design → tasks workflow, extended with machine-enforced gates, semantic skill retrieval, annealing memory, and a constitutional framework that constrains LLM output quality.

## What This Is

A drop-in developer harness that gives your AI coding agent:

- **Spec-first enforcement** — a PreToolUse hook that blocks file mutations until a spec is approved
- **Semantic skill retrieval** — ColBERT-reranked auto-injection of relevant skills per prompt (166+ skills indexed)
- **Constitutional gates** — 9 immutable articles + Phase -1 checklists that prevent over-engineering, premature abstraction, and speculative code
- **Annealing memory** — bits you work out get logged; recalled ≥3 times they promote to durable markdown; unused bits decay
- **Cross-harness adapter** — one config (`harness.json`) syncs MCP servers and model routing to Claude Code, opencode, and Kiro simultaneously
- **Security scanning** — blocks credential exposure before it hits disk
- **Convergence checking** — verifies implementation matches spec, reports gaps

## Why

Every AI coding agent shares the same failure mode: it generates functional code that misses business requirements, over-engineers the solution, or silently drifts from the plan.

SDD harness solves this by making the spec the source of truth and enforcing that relationship mechanically — not through discipline alone.

## Quick Start

### 1. Clone

```bash
git clone https://github.com/thistleknot/sdd-harness ~/.harness
```

### 2. Run setup

```bash
python ~/.harness/setup.py
```

This single command:
- Copies core skills to `~/.skills` (the shared skill store all harnesses read from)
- Installs retrieve-skills dependencies and indexes the store
- Detects which harnesses you have (Claude Code, opencode, Kiro, pi)
- Syncs MCP server registrations to all detected harnesses
- Asks if you want to wire the optional todo and memory-index MCP servers

**Flags:**
```bash
python setup.py --all            # non-interactive, install everything
python setup.py --skip-optional  # core only (retrieve-skills), no todo/memory-index
python setup.py --target claude  # sync to one harness only
```

### 3. Start the retrieve-skills server

The server must be running for skill retrieval to work (one process for all sessions):

```bash
# Linux/macOS
cd ~/.claude/skills/retrieve-skills && nohup python server.py &

# Windows (register as service via NSSM, or Start-Process)
Start-Process -FilePath python -ArgumentList "C:/Users/user/.claude/skills/retrieve-skills/server.py" -WindowStyle Hidden
```

### 4. (Optional) Start memory-index server

If you wired memory-index during setup:

```bash
# Windows
Start-Process -FilePath python -ArgumentList "C:/Users/user/.skills/memory-index/mem_server.py" -WindowStyle Hidden
```

### 4. Import the constitution into your CLAUDE.md

Add to the top of your `~/.claude/CLAUDE.md` or project-level `CLAUDE.md`:

```markdown
@~/.harness/constitution.md
```

### 5. Register hooks (Claude Code)

Copy the hook registrations from `templates/settings.json` into your `~/.claude/settings.json`, or merge manually. The key hooks:

| Hook | Event | What It Does |
|------|-------|-------------|
| `security_scan.py` | PreToolUse (Write/Edit) | Blocks credential exposure |
| `self_review.py` | Stop | Catches TODOs, placeholders, incomplete work |
| `pre_compact.py` | PreCompact | Backs up transcript before context compaction |
| `codebase_map.py` | UserPromptSubmit | Injects project structure on first prompt |
| `convergence.py` | Manual | Compares implementation vs spec, reports gaps |
| `session_end.py` | SessionEnd | Auto-updates last_session.md |

### 6. Verify

```powershell
powershell -File ~/.harness/scripts/verify.ps1
```

Expected: 20/20 pass.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    SHARED INFRASTRUCTURE                          │
├──────────────────────┬──────────────────────────────────────────┤
│ retrieve-skills:8765 │ memory-index:8055                         │
│ (ColBERT reranker)   │ (Chroma PersistentClient)                 │
├──────────────────────┼──────────────────────────────────────────┤
│ todo (stdio)         │ data-science-skills (stdio)               │
└──────────┬───────────┴──────────────────────┬───────────────────┘
           │                                  │
    ┌──────┴──────┐    ┌──────────────┐    ┌──┴────────────┐
    │ Claude Code │    │   opencode   │    │    pi / Kiro   │
    │ (API models)│    │ (OpenRouter) │    │  (OpenRouter)  │
    └─────────────┘    └──────────────┘    └───────────────┘
```

## Skill Retrieval — Avoiding Context Rot

The `retrieve-skills/` module is the core differentiator. Instead of loading ALL skills into context (which bloats the prompt and causes "lost in the middle" effects), it:

1. **Embeds** skill descriptions once (MiniLM-L6, 384-dim)
2. **Indexes** them in SQLite with content-hash checkpointing (only re-embeds on change)
3. **On each prompt**, embeds the query, retrieves top-k by cosine similarity
4. **Reranks** with jina-colbert-v2-64 (late interaction, token-level matching)
5. **Gates** on median margin (1.5) — only injects skills that clearly outrank ambient noise
6. **Caps** at max_accept (2 per prompt) to avoid context bloat

Result: only the 1-2 most relevant skills appear in context per prompt. No rot. No bloat. Measured at 100% precision on ground-truth queries.

### Adding Your Own Skills

Drop a `SKILL.md` into the skill store with YAML frontmatter:

```yaml
---
name: my-skill
description: >
  What this skill does and when to use it. This description is the
  retrieval unit — write it to match the prompts that should trigger it.
---

# Instructions here
```

Then reindex:
```bash
python retrieve-skills/indexer.py
# or POST http://127.0.0.1:8765/reindex
```

## The Constitution

Nine immutable articles that constrain how specs become code:

1. **Spec-First** — no code before spec + design + tasks exist
2. **Simplicity Gate** — max 3 new files per feature, no future-proofing
3. **Anti-Abstraction** — use frameworks directly, no wrappers without measured justification
4. **Test-First** — acceptance criteria are testable assertions; tests run before done
5. **Integration-First** — real environments over mocks; minimum 3 varied inputs
6. **Root-First Isolation** — fix the earliest broken link; nothing downstream until upstream is clean
7. **Bounded Execution** — <15 min per test, ≤3 stacked before disposition
8. **Change Discipline** — touch only what the change requires; anti-sprawl gates A+B+C
9. **Memory at Decision Time** — update docs before code; spec changes first

Phase -1 Gates enforce these as pre-implementation checklists.

## Model Routing

| Role | Claude Code | Local (opencode/pi via OpenRouter) |
|------|-------------|-----------------------------------|
| Orchestrator/Coder | claude-sonnet-5 | deepseek/deepseek-v4-flash ($0.14/M) |
| Planner | claude-opus-5 | deepseek/deepseek-v4-flash or qwen3.5-reasoning:9b |
| Critic | claude-sonnet-5 | deepseek/deepseek-v4-flash |
| Architect (terminal) | claude-fable-5 | gemma-4-12B-agentic |
| Worker (rote) | claude-haiku-4.5 | qwen3.5-oc:2b |

The adapter writes per-harness model configs from `harness.json`.

## Cross-Harness Proof

All three harnesses implemented Conway's Game of Life in 3D from the same `spec.md`:

| Harness | Model | Cost | Result |
|---------|-------|------|--------|
| Claude Code | claude-opus-5 | ~$0.15 | Spec + design + tasks for 14 specs |
| opencode | deepseek-v4-flash | ~$0.003 | Full index.html in one shot |
| pi | deepseek-v4-flash | ~$0.004 | Full index.html in one shot |

## File Structure

```
~/.harness/
├── README.md              # This file
├── setup.py               # One-command installer for all harnesses
├── requirements.md        # 13 EARS requirements
├── design.md              # Architecture + data flow
├── tasks.md               # 11 implementation tasks
├── constitution.md        # 9 immutable articles + Phase -1 Gates
├── inspirations.md        # Competitive analysis + 11 reference repos
├── harness.json           # Shared config (MCP servers + model routing)
├── manifest.toml          # Capability matrix (artifact × harness strategies)
├── adapter.py             # Syncs harness.json → all harness configs (MCP only)
├── hooks/
│   ├── security_scan.py   # PreToolUse: blocks credentials
│   ├── codebase_map.py    # UserPromptSubmit: project structure injection
│   ├── self_review.py     # Stop: catches incomplete work
│   ├── pre_compact.py     # PreCompact: transcript backup
│   ├── session_end.py     # SessionEnd: updates last_session.md
│   └── convergence.py     # Manual: spec vs implementation gap report
├── scripts/
│   └── verify.ps1         # 20-point health check
├── tests/
│   └── test_claude_code.py # Conformance suite via claude -p
├── retrieve-skills/       # Semantic skill retrieval (ColBERT + MiniLM)
│   ├── server.py          # FastMCP HTTP server (:8765)
│   ├── router_core.py     # top_k + margin gate logic
│   ├── model_backends.py  # Embedder + reranker singletons
│   ├── indexer.py         # Reindex skill store
│   ├── sweep.py           # CV hyperparameter tuning
│   └── hook.py            # UserPromptSubmit hook (calls /route)
└── references/            # 11 cloned repos for inspiration

~/.skills/                 # SHARED SKILL STORE (all harnesses read from here)
├── retrieve-skills/       # SKILL.md for the retrieval gate itself
├── todo/                  # todo_mcp.py + SKILL.md
├── memory-index/          # mem_server.py + SKILL.md-equivalent
├── spec/                  # SDD workflow skill
├── debugging/             # Root-first isolation protocol
├── ...                    # 160+ more skills
└── README.md              # Instructions for adding skills
```

## Inspirations

Built on patterns from:
- [GitHub Spec Kit](https://github.com/github/spec-kit) — constitutional framework, 5-phase workflow
- [The Stoa](https://github.com/denson/the-stoa) — recursive 3-role architecture, beadwork substrate
- [Everything-Claude-Code](https://github.com/aXp-Engineering/Everything-Claude-Code) — instincts, cross-harness adapters
- [claudekit](https://github.com/carlrannaberg/claudekit) — self-review, checkpointing, 20+ subagents
- [claude-code-hooks-mastery](https://github.com/disler/claude-code-hooks-mastery) — all 13 hook events
- [OSpec](https://github.com/clawplays/ospec) — plan→act→verify goal loop
- [Agentic Coding with Claude Code](https://www.packtpub.com/) (Eden Marco, Packt 2026) — HookHub patterns

## What We Have That Others Don't

| Capability | spec-kit | Kiro | Cosmos | This Harness |
|-----------|----------|------|--------|-------------|
| Machine-enforced gate | ✗ (discipline) | ✗ (workflow) | ✗ (checkpoint) | ✓ (PreToolUse denial) |
| Semantic skill retrieval | ✗ | ✗ | ✗ | ✓ (ColBERT margin gate) |
| Annealing memory | ✗ | ✗ | ✗ | ✓ (Chroma + promotion/decay) |
| Cross-harness | ✗ (multi-agent) | ✗ (single IDE) | ✓ (cloud) | ✓ (3 local harnesses) |
| Constitutional framework | ✓ (9 articles) | ✗ | ✗ | ✓ (9 articles + Phase -1) |
| CV-tuned retrieval | ✗ | ✗ | ✗ | ✓ (sweep.py, top_k=34, rerank_keep=21) |

## FAQ

### How do I port updates across all 3 harnesses?

There are two mechanisms depending on what changed:

**MCP server changes** (adding/removing/reconfiguring a server):
```powershell
# Edit the single source of truth
notepad ~/.harness/harness.json

# Sync to all harnesses in one command
python ~/.harness/adapter.py --target all
```

This handles the polarity inversion automatically (opencode uses `enabled: true`, Kiro uses `disabled: false`).

**Everything else** depends on the strategy in `manifest.toml`:

| Strategy | What happens | Your action |
|----------|-------------|-------------|
| **LINK** | Directory junction — both sides see the same bytes | Nothing. Edit once, propagates instantly. |
| **GENERATE** | Formats differ — must emit native form from canonical source | Re-run the generator (or `install.py` once built) |
| **SKIP** | Capability absent in that harness | Nothing to port. |

Current LINK cells (zero-effort sync):
- `policy/` → Claude + pi + opencode (all share the same gate logic)
- `steering/` → Kiro (native frontmatter = our interlingua)
- `agents/` → Claude (markdown + YAML frontmatter matches)
- `skills/` → Claude + pi (same SKILL.md format)

Current GENERATE cells (need regeneration on change):
- Instructions → Claude (`CLAUDE.md`), opencode (plugin), pi (extension)
- Adapter/gate → Claude (`settings.json` hooks entry), opencode (`spec-gate.ts`)
- MCP → all three (handled by `adapter.py`)

**The gap:** A full `install.py` that reads manifest.toml and dispatches all GENERATE cells doesn't exist yet. Until then: `adapter.py` for MCP, junctions for LINK cells, and manual regeneration for instructions/adapter GENERATE cells.

### How do I use this in a new Claude Code session?

You don't do anything special — just open a session and talk to it.

The framework self-activates through hooks:
1. `SessionStart` → memory loads
2. `UserPromptSubmit` → skill retrieval fires, codebase map injects
3. `CLAUDE.md` + `@AGENTS.md` → always-on operating contract (routing gate, agent ladder, memory protocol)

The **routing gate** decides automatically: if your task touches observable behavior, control flow, persistence, or public interfaces → it enters Spec mode. If it's trivial → it just does it. If it's a question → it answers.

The `spec_gate.py` hook **denies file writes** until a spec exists and reaches the `implement` phase. You don't have to remember — the machine enforces it.

**One prerequisite:** the HTTP services must be running:
```powershell
# Verify both are alive
(Invoke-WebRequest "http://127.0.0.1:8765/health" -UseBasicParsing).Content  # retrieve-skills
(Invoke-WebRequest "http://127.0.0.1:8055/health" -UseBasicParsing).Content  # memory-index
```

If they're down, skills and memory won't inject, but the spec gate and CLAUDE.md instructions still work (they're local hooks/files).

### How do I use this in Kiro?

Kiro has explicit workflow modes you select at session start:

| Kiro Mode | SDD Equivalent |
|-----------|----------------|
| **Default** | Routing gate → "Do" (trivial, unambiguous tasks) |
| **Spec** | Routing gate → "Spec" (full requirements → design → tasks) |
| **Quick Spec** | Compressed spec flow (skip user review loop) |
| **Bug Fix** | Root-first isolation (Article VI) |
| **Plan** | Read-only planning mode (no file mutations) |

**Key difference from Claude Code:** Kiro has no `spec_gate.py` enforcement — it cannot deny tool calls (`can_gate = false` in manifest). You are the enforcement. Pick **Spec** mode for any non-trivial feature work. For small fixes, **Bug Fix** or **Default** is fine.

The steering files in `~/.kiro/steering/` provide the same instructions (they're LINKed from this repo — zero drift), and the MCP servers (retrieve-skills, memory-index) work identically. Kiro is actually the best-served harness for skill retrieval since it's a native MCP client.

### How do I use this in opencode?

opencode receives the SDD framework through three channels:

1. **AGENTS.md** — the full operating contract (same content as Claude Code's, GENERATE'd into opencode's native format)
2. **MCP servers** — retrieve-skills and memory-index wire as `streamable-http` entries in `opencode.json`
3. **Plugin gate** — `spec-gate.ts` enforces spec-first via opencode's plugin system (throws to abort tool calls)

**In practice:** open a session and work normally. The routing gate (Answer/Do/Spec) is in AGENTS.md, so the model follows it. The plugin gate blocks writes without an approved spec, same as Claude Code's hook — just different machinery.

**Limitation:** opencode's `tool.execute.before` hook cannot intercept subagent calls (opencode#5894). The adapter maps task/agent delegation to a DELEGATE pattern that works around this — subagents are not gated, so keep spec-critical work in the main session.

**Model tier:** opencode routes to OpenRouter (deepseek-v4-flash at $0.14/M for orchestrator/coder/critic, or local ollama models). Same SDD workflow, cheaper compute.

```bash
# Invoke headlessly for conformance testing
opencode run "list all MCP servers"
```

### How do I use this in pi?

pi inherits most of its SDD configuration from Claude Code's user-scope settings, plus:

1. **Extensions** — `~/.pi/agent/extensions/spec-gate/` provides the gate (returns `{block: true, reason}` to deny writes)
2. **Skills** — `~/.pi/skills/` is a symlink to `~/.skills`, so it reads the same store
3. **Skill router** — pi has no native MCP client, so `retrieve-skills/` is an extension that POSTs to the HTTP `/route` endpoint directly

**In practice:** same as Claude Code — open a session, the framework self-activates. The spec gate fires on writes, skills inject per-prompt via the extension, memory and todos work through inherited Claude Code MCP registrations.

**Key strength:** pi has the most complete gate today — it can intercept shell commands AND delegation calls, which Claude Code and opencode both miss in some form.

**Model tier:** routes through litellm to local ollama (same models as opencode) or OpenRouter.

```bash
# Invoke headlessly for conformance testing
pi -p "list all MCP servers"
```

### Why can't Kiro enforce the spec gate?

Kiro has no PreToolUse interception point. It cannot inspect a tool call before execution and return a "deny" decision. The manifest records this as `can_gate = false, gate_style = "none"`.

This means Kiro receives the same instructions and skills as Claude Code, but compliance is advisory — the LLM follows the constitution because it's told to, not because a hook blocks it when it doesn't.

For critical spec-governed work, use Claude Code (machine-enforced) or treat Kiro's **Spec** mode as your manual enforcement layer.

### What if the HTTP services aren't running?

The system degrades gracefully:

| Service down | Impact | Workaround |
|-------------|--------|------------|
| retrieve-skills (:8765) | No automatic skill injection. Agent works from CLAUDE.md + memory only. | Start it: `Start-Process python server.py` in the retrieve-skills dir |
| memory-index (:8055) | No semantic recall of prior decisions/patterns. | Start it: `Start-Process python server.py` in the memory-index dir |
| Both down | Core SDD still works — spec gate, constitution, CLAUDE.md, and agents are all local files/hooks. Just no dynamic context enrichment. | Run `verify.ps1` to diagnose |

### How is this different from just using Kiro's built-in Spec mode?

Kiro's Spec mode gives you a structured requirements → design → tasks workflow inside the IDE. This harness extends that pattern with:

1. **Machine enforcement** (Claude Code only) — you can't skip the spec even if you try
2. **Semantic skill retrieval** — 166+ skills auto-injected per prompt based on relevance
3. **Annealing memory** — decisions persist across sessions, promote on reuse, decay when unused
4. **Cross-harness portability** — same workflow in Claude Code, opencode, pi, and Kiro
5. **Constitutional framework** — 9 articles + Phase -1 gates that prevent over-engineering
6. **Agent ladder** — escalation chain (critic → fixer_low → fixer_med → planner) for self-correction

Kiro's Spec mode is the closest native equivalent to what this harness provides — but scoped to a single IDE without the retrieval, memory, or enforcement layers.

### Where do I put new skills?

All skills live in `~/.skills/`. This is the single shared store that all harnesses read from via the retrieve-skills MCP server.

To add a skill:

1. Create a folder: `~/.skills/my-skill/`
2. Add a `SKILL.md` with YAML frontmatter:
   ```yaml
   ---
   name: my-skill
   description: >
     What this skill does and when to use it. This description is the
     retrieval unit — write it to match the prompts that should trigger it.
   ---
   
   # Instructions here
   ```
3. Reindex: `curl -X POST http://127.0.0.1:8765/reindex`

The `description` field is what gets embedded and matched against your prompts. If it doesn't match the language you'd use to describe the task, the skill won't surface. Write descriptions in terms of *what the user would ask for*, not internal terminology.

Skills are NOT loaded into context by default — they're only injected when the retrieval gate decides they're relevant (ColBERT reranker, margin gate at 1.5). This prevents context bloat.

### What does the todo MCP server do?

Persistent task tracking across sessions. When the agent identifies follow-up work that won't be done immediately, it logs a todo. Next session, it calls `list_todos` at startup to surface pending work.

- Stored in SQLite (per-project `.todo/todos.db` or global `~/todos.db`)
- Runs as stdio (started fresh per session by the harness — no persistent process needed)
- Tools: `add_todo`, `list_todos`, `complete_todo`, `update_todo`, `remove_todo`

### What does the memory-index MCP server do?

Semantic memory that persists across sessions. The agent can:
- `search_memory("query")` — recall prior decisions, patterns, or lessons
- `log_memory("what I learned")` — jot ephemeral bits (cheap, anneals away if unused)
- `add_memory(name, type, desc, body)` — write durable entries

The annealing lifecycle: logged bits that get recalled ≥3 times auto-promote to durable markdown in `~/memory-bank/`. Unused bits decay over time. Useful patterns rise; noise disappears.

Requires:
- Ollama running with `nomic-embed-text` pulled (`ollama pull nomic-embed-text`)
- The memory-index server running on port 8055

### What's the "core product" — what's the minimum viable install?

The minimum that gives you the full SDD experience:

1. **`~/.skills/`** — the shared skill store with at least the core skills
2. **retrieve-skills server** (:8765) — semantic skill injection per prompt
3. **Steering/instructions** — the constitution + operating rules in your harness's native format

That's it. Todo and memory-index are force multipliers but not required for the core spec-driven workflow to function.

The full stack adds:
- **todo MCP** — cross-session task continuity
- **memory-index MCP** — semantic recall of prior decisions/patterns
- **spec_gate hook** — machine-enforced spec compliance (Claude Code only)
- **Agent ladder** — self-correcting escalation chain

## License

MIT

## Contributing

PRs welcome. The constitution governs this repo's own development — spec first, then code.
