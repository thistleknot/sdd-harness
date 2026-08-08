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

### 2. Install the skill-router (semantic retrieval)

```bash
cd ~/.harness/retrieve-skills
pip install -r requirements.txt
python indexer.py  # embeds skill descriptions (first run downloads MiniLM-L6)
```

Start the retrieval server (persistent, one process for all sessions):
```bash
# Linux/macOS
nohup python server.py &

# Windows (register as service via NSSM, or Start-Process)
Start-Process -FilePath python -ArgumentList server.py -WindowStyle Hidden
```

### 3. Wire your harness

```bash
python ~/.harness/adapter.py --target all
```

This syncs `harness.json` → Claude Code (`.claude.json`), opencode (`opencode.json`), and Kiro (`~/.kiro/settings/mcp.json`).

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
├── requirements.md        # 13 EARS requirements
├── design.md              # Architecture + data flow
├── tasks.md               # 11 implementation tasks
├── constitution.md        # 9 immutable articles + Phase -1 Gates
├── inspirations.md        # Competitive analysis + 11 reference repos
├── harness.json           # Shared config (MCP servers + model routing)
├── adapter.py             # Syncs harness.json → all harness configs
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

## License

MIT

## Contributing

PRs welcome. The constitution governs this repo's own development — spec first, then code.
