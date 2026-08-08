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
