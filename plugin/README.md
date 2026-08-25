# SDD Harness Plugin

Cross-harness plugin for Spec-Driven Development. One install, five agent surfaces.

## Supported Harnesses

| Harness | Format | How it loads |
|---------|--------|-------------|
| **Claude Code** | `.claude-plugin/` + skills/ + hooks/ | Plugin registry + MCP |
| **OpenCode** | `.opencode/plugins/sdd-harness.js` | Plugin array in opencode.json |
| **Codex** | `.codex-plugin/plugin.json` + skills/ | Plugin directory |
| **Pi** | `.pi/extensions/sdd-harness.ts` | Extension loader |
| **Kiro** | `.kiro/settings/mcp.json` + steering/ | MCP + steering files |

## Install

```powershell
python ~/.harness/plugin/install.py
```

Auto-detects which harnesses are installed and wires into each one.

```powershell
# Install for specific targets
python ~/.harness/plugin/install.py --target claude opencode

# Verify MCP services are running
python ~/.harness/plugin/install.py --verify

# Install for all regardless of detection
python ~/.harness/plugin/install.py --all
```

## What Gets Installed

### MCP Servers (shared across all harnesses)
| Server | Port | Purpose |
|--------|------|---------|
| sdd-specs | 8057 | Requirements, decisions, tasks, settings, canon |
| sdd-memory | 8055 | Semantic vector memory with annealing |
| sdd-skills | 8765 | Skill retrieval by semantic similarity |
| sdd-todo | 8056 | Project-local work tracking |

### Skills (bundled prompt-based workflows)
- `spec-driven-development` — enforce spec-first methodology
- `session-continuity` — cross-session memory and handoff
- `failure-archaeology` — break out of failure loops

### Hooks (lifecycle automation)
- `SessionStart` — resume prior context
- `Stop` — package handoff state
- `PreToolUse` — spec gate enforcement on writes

## Architecture

```
~/.harness/plugin/
├── .claude-plugin/     # Claude Code manifest
├── .codex-plugin/      # Codex manifest
├── .opencode/          # OpenCode plugin (JS)
├── .pi/                # Pi extension (TS)
├── hooks/              # Shared hook configs + scripts
├── skills/             # Shared SKILL.md files
├── install.py          # Cross-harness installer
└── README.md
```

The key insight: **scripts are harness-agnostic** (stdin JSON, stdout JSON). Only the *wiring* layer (how hooks get registered) is harness-specific. The installer handles that translation.

## Prerequisites

MCP services must be running before any agent session uses them:

```powershell
# Verify all services are up
python ~/.harness/plugin/install.py --verify
```

## Development

The plugin lives at `~/.harness/plugin/`. Edit skills, hooks, or manifests and re-run `install.py` to propagate changes.

For the OpenCode plugin specifically, after editing `.opencode/plugins/sdd-harness.js`, restart OpenCode to pick up changes (no build step needed — it's plain JS).
