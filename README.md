# SDD Harness

A cross-harness agentic development environment — spec-driven development, debugging, reasoning, and code quality — that works identically across Claude Code, opencode, and pi. One skill store, one spec workflow, one memory system. The model tier adapts; the behavioral contract doesn't.

## What This Is

A drop-in developer harness that gives your AI coding agent:

- **Spec-first enforcement** — a PreToolUse hook that blocks file mutations until a spec is approved
- **Semantic skill retrieval** — ColBERT-reranked auto-injection of relevant skills per prompt ([skill store](https://github.com/thistleknot/skills), separate repo)
- **Constitutional gates** — 9 immutable articles + Phase -1 checklists that prevent over-engineering, premature abstraction, and speculative code
- **Annealing memory** — bits you work out get logged; recalled 3+ times they promote to durable markdown; unused bits decay
- **Session lifecycle** — automatic handoff/resume between sessions so context survives across boundaries
- **Batched change review** — Kiro-style "show what changed, ask before proceeding" at task boundaries
- **Automatic test generation** — PostToolUse hook triggers unit test creation after code writes
- **Self-review guard** — catches TODOs, placeholders, and incomplete work before the agent declares done
- **Cross-harness adapter** — one config (`harness.json`) syncs MCP servers and model routing to Claude Code, opencode, and pi simultaneously
- **Security scanning** — blocks credential exposure before it hits disk

## Why

Every AI coding agent shares the same failure mode: it generates functional code that misses business requirements, over-engineers the solution, or silently drifts from the plan.

SDD harness solves this by making the spec the source of truth and enforcing that relationship mechanically — not through discipline alone.

## Quick Start

### 1. Clone

```bash
git clone https://github.com/thistleknot/sdd-harness ~/.harness
```

### 2. Clone the skill store (separate repo)

```bash
git clone https://github.com/thistleknot/skills ~/.skills
```

The skill store covers debugging, spec workflows, reasoning, code quality, data science, orchestration, and more. The harness references this store via the retrieve-skills server.

### 3. Run setup

```bash
python ~/.harness/setup.py
```

This:
- Detects which harnesses you have (Claude Code, opencode, Kiro, pi)
- Syncs MCP server registrations to all detected harnesses
- Configures the retrieve-skills server to index `~/.skills/`
- Optionally wires the todo and memory-index MCP servers

### 4. Start the retrieve-skills server

The server must be running for skill retrieval to work (one process for all sessions):

```powershell
# Windows
Start-Process -FilePath python -ArgumentList "C:/Users/user/.skills/retrieve-skills/server.py" -WindowStyle Hidden

# Linux/macOS
cd ~/.skills/retrieve-skills && nohup python server.py &
```

### 5. Import the constitution

Add to the top of your `~/.claude/CLAUDE.md` or project-level `CLAUDE.md`:

```markdown
@~/.harness/constitution.md
```

### 6. Verify

```powershell
powershell -File ~/.harness/scripts/verify.ps1
```

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    SHARED INFRASTRUCTURE                          │
├──────────────────────┬──────────────────────────────────────────┤
│ retrieve-skills:8765 │ memory-index:8055                         │
│ (ColBERT reranker)   │ (Chroma + annealing)                     │
├──────────────────────┼──────────────────────────────────────────┤
│ todo (stdio)         │ data-science-skills (stdio)               │
└──────────┬───────────┴──────────────────────┬───────────────────┘
           │                                  │
    ┌──────┴──────┐    ┌──────────────┐    ┌──┴────────────┐
    │ Claude Code │    │   opencode   │    │    pi / Kiro   │
    │ (API models)│    │ (OpenRouter) │    │  (OpenRouter)  │
    └─────────────┘    └──────────────┘    └───────────────┘
```

## Hooks

The harness ships 7 hooks that fire at different lifecycle events:

| Hook | Event | What It Does |
|------|-------|-------------|
| `security_scan.py` | PreToolUse (Write/Edit) | Blocks credential exposure |
| `turn_write_log.py` | PostToolUse (Write/Edit) | Logs files written this turn for batched review |
| `test_gen.py` | PostToolUse (Write/Edit) | Prompts unit test generation for modified source files |
| `codebase_map.py` | UserPromptSubmit | Injects project structure on first prompt |
| `self_review.py` | Stop | Catches TODOs, placeholders, incomplete work (regex-anchored, deduped) |
| `review_changes.py` | Stop | Batched diff of this turn's writes — asks "proceed, revert, or adjust?" |
| `session_handoff.py` | Stop | Packages context into prompt.md for cross-session continuity |
| `session_resume.py` | SessionStart | Injects prior session's prompt.md as seed context |
| `pre_compact.py` | PreCompact | Backs up transcript before context compaction |
| `session_end.py` | SessionEnd | Auto-updates last_session.md |
| `convergence.py` | Manual | Compares implementation vs spec, reports gaps |

### Batched Change Review (Kiro-style)

The `turn_write_log.py` + `review_changes.py` pair implements Kiro's supervised-mode pattern:

1. During a task — every write silently logs the file path
2. At task boundary — the Stop hook reads the log, diffs each file, shows the batch
3. Agent presents changes grouped by file (changed lines only) and asks for approval
4. User says proceed/revert/adjust before the agent continues

Set `REVIEW_IN_VSCODE=1` to also open diff tabs in VS Code.

### Test Generation (adapted from dotnet/skills)

After writing source code, `test_gen.py` prompts the agent to generate unit tests using the [Direct strategy from dotnet/skills code-testing-generator](https://github.com/dotnet/skills/blob/main/plugins/dotnet-test/agents/code-testing-generator.agent.md):

- Polyglot — detects language, matches existing test framework
- Gate logic — skips test files, config, hooks/infra (only fires for business logic)
- Asserts concrete values — tests must fail if the function body is emptied
- Runs the test suite and fixes failures before reporting

### Session Lifecycle

Cross-session continuity without manual effort:

- **Handoff** (Stop) — writes `~/memory-bank/projects/<repo>/prompt.md` with objective, state, decisions, next steps
- **Resume** (SessionStart) — injects that prompt.md as seed context in the next session
- **Staleness guard** — the Stop hook won't overwrite a richer agent-written handoff (10-min recency check)
- **Modes** — `handoff` (continue later), `migrate` (fresh context now), `close` (archive and done)

## The Constitution

Nine immutable articles that constrain how specs become code:

1. **Spec-First** — no code before spec + design + tasks exist
2. **Simplicity Gate** — max 3 new files per feature, no future-proofing
3. **Anti-Abstraction** — use frameworks directly, no wrappers without measured justification
4. **Test-First** — acceptance criteria are testable assertions; tests run before done
5. **Integration-First** — real environments over mocks; minimum 3 varied inputs
6. **Root-First Isolation** — fix the earliest broken link; nothing downstream until upstream is clean
7. **Bounded Execution** — <15 min per test, 3 stacked max before disposition
8. **Change Discipline** — touch only what the change requires; anti-sprawl gates A+B+C
9. **Memory at Decision Time** — update docs before code; spec changes first

Phase -1 Gates enforce these as pre-implementation checklists.

## Capability Plugin Pattern

Each cross-harness behavior follows the same structure:

| Layer | Purpose | Example |
|-------|---------|---------|
| **Script** | Portable logic (stdin JSON, stdout JSON) | `session_handoff.py` |
| **Wiring** | Per-harness native integration | Claude: `settings.json`. Kiro: `.kiro/hooks/*.json`. Pi/opencode: AGENTS.md |
| **Manifest** | Declares strategy per harness (LINK/GENERATE/SKIP) | `manifest.toml` |
| **Skill** | Optional retrieval target for self-discovery | `continuity-log` SKILL.md |

Scripts are harness-agnostic. Wiring is the only harness-specific layer. See `design.md` for the full pattern documentation.

## Skill Retrieval

The skill store lives in a [separate repository](https://github.com/thistleknot/skills) (`~/.skills/`). The retrieve-skills server:

1. Embeds skill descriptions (MiniLM-L6, 384-dim)
2. Indexes in SQLite with content-hash checkpointing
3. On each prompt, retrieves top-k by cosine similarity
4. Reranks with jina-colbert-v2 (late interaction, token-level matching)
5. Gates on median margin (1.5) — only injects skills that clearly outrank noise
6. Caps at 2 skills per prompt to avoid context bloat

### Adding Skills

Drop a `SKILL.md` into `~/.skills/my-skill/`:

```yaml
---
name: my-skill
description: >
  What this skill does and when to use it. Write the description to match
  the prompts that should trigger it.
---

# Instructions here
```

Then reindex: `curl -X POST http://127.0.0.1:8765/reindex`

## File Structure

```
~/.harness/                        # THIS REPO
├── README.md
├── constitution.md                # 9 immutable articles + Phase -1 Gates
├── design.md                      # Architecture, data flow, capability plugin pattern
├── requirements.md                # EARS requirements
├── tasks.md                       # Implementation tasks
├── manifest.toml                  # Capability matrix (artifact x harness strategies)
├── harness.json                   # Shared config (MCP servers + model routing)
├── adapter.py                     # Syncs harness.json -> all harness configs
├── setup.py                       # One-command installer
├── inspirations.md                # Competitive analysis + reference repos
├── hooks/
│   ├── security_scan.py           # PreToolUse: blocks credentials
│   ├── turn_write_log.py          # PostToolUse: logs files for batched review
│   ├── test_gen.py                # PostToolUse: triggers unit test generation
│   ├── review_changes.py          # Stop: batched diff presenter
│   ├── self_review.py             # Stop: catches incomplete work
│   ├── session_handoff.py         # Stop: cross-session context packaging
│   ├── session_resume.py          # SessionStart: injects prior context
│   ├── codebase_map.py            # UserPromptSubmit: project structure
│   ├── pre_compact.py             # PreCompact: transcript backup
│   ├── convergence.py             # Manual: spec vs implementation gaps
│   └── session_end.py             # SessionEnd: updates last_session.md
├── .kiro/
│   ├── hooks/                     # Kiro-native hook JSONs
│   │   ├── test-gen-post-write.json
│   │   ├── turn-write-log.json
│   │   ├── review-changes-stop.json
│   │   ├── session-handoff-stop.json
│   │   └── session-handoff-resume.json
│   └── steering/
│       └── session-handoff.md
├── scripts/
│   └── verify.ps1                 # Health check all harnesses
├── tests/
│   └── test_claude_code.py        # Conformance suite via claude -p
├── conformance/                   # Cross-harness test specs
├── policy/                        # Gate policy files
└── agents/                        # Sub-agent definitions

~/.skills/                         # SEPARATE REPO: github.com/thistleknot/skills
├── retrieve-skills/               # Server + indexer + router
├── debugging/                     # Root-first isolation protocol
├── spec/                          # SDD workflow skill
├── reasoning/                     # Six Hats, TRIZ, OODA
├── continuity-log/                # Session lifecycle skill
├── ...                            # many more
└── README.md
```

## Model Routing

| Role | Claude Code | Local (opencode/pi via OpenRouter) |
|------|-------------|-----------------------------------|
| Orchestrator/Coder | claude-sonnet-5 | deepseek/deepseek-v4-flash |
| Planner | claude-opus-5 | deepseek/deepseek-v4-flash |
| Critic | claude-sonnet-5 | deepseek/deepseek-v4-flash |
| Architect | claude-fable-5 | gemma-4-12B-agentic |
| Worker | claude-haiku-4.5 | qwen3.5-oc:2b |

The adapter writes per-harness model configs from `harness.json`.

## Cross-Harness Sync

Two mechanisms depending on what changed:

**MCP server changes:**
```powershell
# Edit source of truth, sync everywhere
notepad ~/.harness/harness.json
python ~/.harness/adapter.py --target all
```

**Everything else** depends on `manifest.toml` strategy:

| Strategy | What happens |
|----------|-------------|
| **LINK** | Directory junction — edit once, propagates instantly |
| **GENERATE** | Formats differ — re-run generator or `install.py` |
| **SKIP** | Capability absent in that harness (documented reason) |

## How Sessions Work

You don't do anything special — open a session and talk:

1. `SessionStart` → memory loads + prior session context injects
2. `UserPromptSubmit` → skill retrieval fires, codebase map injects
3. Agent works → writes are logged silently
4. Task complete → Stop fires → self-review checks → change review shows diffs → handoff packages context
5. Next session → resume hook injects where you left off

The **routing gate** decides mode automatically (Answer/Do/Spec). The `spec_gate.py` hook denies file writes until a spec is approved in spec-armed repos.

## Evaluation

The harness hasn't been formally benchmarked yet. The self-review, test-gen, and change-review hooks are designed to catch incomplete work and regressions, but their lift hasn't been measured against a baseline (e.g., SWE-bench or controlled A/B on real tasks). This is a known gap.

An env-var kill-switch (`HARNESS_HOOKS_ENABLED=0`) for A/B testing is planned but not yet implemented.

## License

MIT

## Contributing

PRs welcome. The constitution governs this repo's own development — spec first, then code.
