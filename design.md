# Design — Cross-Harness SDD

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    SHARED INFRASTRUCTURE                          │
├──────────────────────┬──────────────────────────────────────────┤
│ retrieve-skills:8765 │ memory-index:8055                         │
│ (skill retrieval)    │ (semantic memory)                         │
├──────────────────────┼──────────────────────────────────────────┤
│ todo (stdio)         │ data-science-skills (stdio)               │
└──────────┬───────────┴──────────────────────┬───────────────────┘
           │                                  │
    ┌──────┴──────┐    ┌──────────────┐    ┌──┴────────────┐
    │ Claude Code │    │   opencode   │    │      pi       │
    │ (API models)│    │ (ollama local)│    │ (ollama local) │
    │             │    │              │    │               │
    │ Hooks:      │    │ Steering:    │    │ Steering:     │
    │ spec_gate.py│    │ AGENTS.md    │    │ AGENTS.md     │
    │ hook.py     │    │ opencode.json│    │ (inherits CC) │
    │ membank.py  │    │              │    │               │
    │             │    │ Agents:      │    │ Agents:       │
    │ Agents:     │    │ ~/.config/   │    │ (inherits CC) │
    │ ~/.claude/  │    │  opencode/   │    │               │
    │  agents/    │    │  agents/     │    │               │
    └─────────────┘    └──────────────┘    └───────────────┘
```

## Data Flow: SDD Lifecycle

```
1. SESSION START
   ├─ list_todos(workspace_root) → surface pending work
   ├─ search_memory(project context) → recall prior decisions
   └─ read CLAUDE.md / AGENTS.md → load steering

2. TASK ARRIVES
   ├─ retrieve_skills(task description) → inject relevant skills
   ├─ ROUTING GATE: Answer | Do | Spec
   │   ├─ Answer: respond directly
   │   ├─ Do: implement (trivial/unambiguous)
   │   └─ Spec: enter planning mode
   │
   └─ IF SPEC:
       ├─ PLAN (read-only): research, analyze, produce spec
       ├─ REVIEW: user approves spec
       └─ IMPLEMENT: code from spec

3. IMPLEMENTATION (Agent Ladder)
   ├─ Coder implements from spec
   ├─ Critic verifies (runs tests, cites spec clause)
   │   ├─ PASS → done
   │   └─ FAIL →
   │       ├─ Fixer_low proposes fix (Gate 2)
   │       │   ├─ PASS → done
   │       │   └─ FAIL →
   │       │       ├─ Fixer_med applies directly (Gate 3)
   │       │       │   ├─ PASS → done
   │       │       │   └─ FAIL →
   │       │       │       └─ Planner re-specs (max 2 rounds)
   │       │       │           └─ FAIL → STOP, report to user
   └─ (ladder exhausted)

4. COMPLETION
   ├─ log_memory(what was learned)
   ├─ complete_todo(finished items)
   ├─ add_todo(deferred work)
   └─ update activeContext.md / progress.md
```

## Capability Plugin Pattern

A **capability** is a cross-harness behavior delivered through the shared infrastructure. Each capability follows the same structure:

```
capability/
├── Shared Script(s)    — Python, lives in .harness/hooks/ or .harness/mcp/
├── Per-Harness Wiring  — native config that invokes the script (hook JSON, instruction block, etc.)
├── Manifest Cells      — [[cell]] entries declaring strategy per harness
└── Skill (optional)    — retrieval-routed instruction that teaches agents when/how to invoke
```

### Anatomy

| Layer | Purpose | Example (lifecycle) |
|-------|---------|---------------------|
| **Script** | Portable logic. No harness-specific imports. Reads stdin JSON, writes stdout. | `session_handoff.py`, `session_resume.py` |
| **Wiring** | Native integration point per harness. Maps trigger → script invocation. | Claude: `settings.json` Stop hook. Kiro: `.kiro/hooks/*.json`. Pi/opencode: AGENTS.md instruction. |
| **Manifest** | Declares how the capability reaches each harness (LINK/GENERATE/SKIP). | `[[cell]] artifact="lifecycle"` × 4 harnesses |
| **Skill** | Optional retrieval target so agents self-discover the behavior. | `continuity-log` SKILL.md references session_handoff.py |

### Design Constraints

1. **Scripts are harness-agnostic.** They consume a JSON payload on stdin and emit structured JSON on stdout. No imports from any harness SDK.
2. **Wiring is the only harness-specific layer.** If a harness has native hooks, use them (GENERATE into its config). If not, fall back to instruction-driven (GENERATE into AGENTS.md).
3. **Staleness guard.** When a hook and an agent can both write the same artifact, the hook checks recency before overwriting. A richer agent-written artifact should survive a thin hook invocation.
4. **Fail-open.** Lifecycle hooks exit 0 on any error. They must never block session start or stop.
5. **One manifest cell per (artifact, harness) pair.** The cell declares strategy + target + emit description. `install.py` uses this to generate or link.

### Current Capabilities

| Capability | Artifact | Scripts | Harnesses Wired |
|-----------|----------|---------|-----------------|
| Spec gate | `policy` + `adapter` | `security_scan.py`, adapter per harness | claude, pi, opencode |
| Skill routing | `skills_router` | retrieve-skills HTTP server | kiro (MCP), claude (hook-http), pi (ext-http), opencode (MCP, NOT_WIRED) |
| Session lifecycle | `lifecycle` | `session_handoff.py`, `session_resume.py` | claude, kiro, pi, opencode |
| Self-review | (inline hook) | `self_review.py` | claude (Stop), kiro (Stop) |
| Codebase map | (inline hook) | `codebase_map.py` | claude (UserPromptSubmit), kiro (steering) |

### Adding a New Capability

1. Write the script in `.harness/hooks/` or `.harness/mcp/`. Document: purpose, preconditions, failure modes.
2. Wire each harness using its native mechanism. Document which trigger fires and what stdin/stdout contract applies.
3. Add `[[cell]]` entries to `manifest.toml` for every harness (including SKIP with reason if inapplicable).
4. If agents should self-discover the behavior, create or update a skill in `~/.skills/<name>/SKILL.md`.
5. Run `install.py` to propagate. Verify with conformance test.

## Configuration Files Per Harness

### Claude Code (`~/.claude/`)

| File | Purpose |
|------|---------|
| `CLAUDE.md` | 13-law operating core + @AGENTS.md import |
| `AGENTS.md` | Full operating contract, memory protocol, skill routing |
| `settings.json` | Hooks (UserPromptSubmit, PreToolUse, etc.) |
| `.claude.json` | MCP server registrations (user scope) |
| `agents/*.md` | Sub-agent definitions (opus_planner, sonnet_critic, etc.) |
| `hooks/spec_gate.py` | PreToolUse: blocks writes without approved spec |
| `hooks/hook.py` → `skills/retrieve-skills/hook.py` | UserPromptSubmit: skill injection |
| `hooks/membank.py` | SessionStart + UserPromptSubmit: memory injection |

### opencode (`~/.config/opencode/`)

| File | Purpose |
|------|---------|
| `opencode.json` | Model providers, MCP block, plugins, agent config |
| `AGENTS.md` | Same operating contract (shared from skills repo) |
| `agents/*.md` | Sub-agent definitions (local model variants) |
| `skills/` | Skill files (if standalone mode) |

### pi (`~/.pi/`)

| File | Purpose |
|------|---------|
| `.claude/settings.local.json` | Permissions |
| `skills/retrieve-skills/SKILL.md` | Skill routing instruction |
| `litellm_config.yaml` | Model routing to ollama |
| Inherits Claude Code user-scope MCP registrations |

## Model Routing Logic

```python
def select_model(role: str, harness: str) -> str:
    if harness == "claude-code":
        return {
            "orchestrator": "claude-sonnet-5",
            "coder": "claude-sonnet-5",
            "critic": "claude-sonnet-5",
            "planner": "claude-opus-5",
            "fixer_low": "claude-opus-4-8",
            "fixer_med": "claude-opus-4-8",
            "architect": "claude-fable-5",
            "worker": "claude-haiku-4.5",
        }[role]
    else:  # opencode, pi (local ollama)
        return {
            "orchestrator": "qwopus-coding-thinking-256k:4b",
            "coder": "qwopus-coding-thinking-256k:4b",
            "critic": "qwen3.5-oc:4b",
            "planner": "qwen3.5-reasoning-thinking-256k:9b",
            "fixer_low": "qwen3.5-reasoning-thinking-256k:9b",
            "fixer_med": "qwen3.5-reasoning-thinking-256k:9b",
            "architect": "huihui-gemma-4-12B-agentic-fable5-abliterated",
            "worker": "qwen3.5-oc:2b",
        }[role]
```

## Sub-Agent Definition Format

```markdown
---
name: <agent-name>
description: <when to invoke — used by orchestrator to decide routing>
model: <model-id>  # optional, overrides default
tools: ["Read", "Grep", "Glob", "Bash", "Write", "Edit"]  # least privilege
---

# Role: <Title>

<system prompt — instructions for how the agent operates>

## Output Contract

<what the agent must produce>

## Constraints

<what the agent must NOT do>
```

## Hook Contract

```json
{
  "hooks": {
    "SessionStart": [{"hooks": [{"type": "command", "command": "..."}]}],
    "UserPromptSubmit": [{"hooks": [{"type": "command", "command": "...", "timeout": 5}]}],
    "PreToolUse": [{"matcher": "^(Edit|Write)$", "hooks": [{"type": "command", "command": "..."}]}],
    "Stop": [{"hooks": [{"type": "command", "command": "..."}]}]
  }
}
```

Exit codes:
- 0: success (stdout forwarded for SessionStart/UserPromptSubmit/PreToolUse)
- 2: BLOCK the action (PreToolUse/UserPromptSubmit)
- other: silent failure, no block

## Conformance Test Interface

Each harness exposes a CLI for headless invocation:

| Harness | Command | Example |
|---------|---------|---------|
| Claude Code | `claude -p "<prompt>"` | `claude -p "list all MCP servers"` |
| opencode | `opencode run "<prompt>"` | `opencode run "list all MCP servers"` |
| pi | `pi -p "<prompt>"` | `pi -p "list all MCP servers"` |

Tests invoke via these CLIs and verify output matches expected behavior.
