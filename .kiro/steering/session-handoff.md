---
inclusion: manual
---

# Session Handoff Protocol

## Purpose

Avoid context rot by packaging session state into a `prompt.md` file that can seed a fresh continuation. This replaces the "start a new session" suggestion with an actual transfer mechanism.

## Three Disposition Paths

| Mode | When | What happens |
|------|------|--------------|
| **migrate** | Context is heavy but work continues | Write `prompt.md`, re-read it as new seed context (simulates compact) |
| **close** | Task is complete | Archive final state to `~/memory-bank/handoffs/`, no continuation |
| **handoff** | Logical breakpoint, next session picks up | Write `prompt.md` + optional conversation log reference |

## How It Works

### On Session End (Stop hook)

The agent is prompted to offer the user a choice: migrate, close, or handoff. If accepted, the agent invokes:

```
python ~/.harness/hooks/session_handoff.py --mode <mode> --workspace <cwd> \
  --objective "<what we're doing>" \
  --state '{"done":[],"in_progress":[],"pending":[],"blocked":[]}' \
  --decisions '["settled decision 1","settled decision 2"]' \
  --files '["path/to/file1","path/to/file2"]' \
  --next-steps '["step 1","step 2"]' \
  --blockers '["blocker if any"]' \
  --conversation-log "optional/path/to/log"
```

### On Session Start (SessionStart hook)

A command hook checks for an existing `prompt.md` at:
1. `~/memory-bank/projects/<repo>/prompt.md` (project-specific)
2. `~/memory-bank/handoffs/prompt-*.md` (latest global fallback)

If found, its content is injected as seed context via stdout.

### Mid-Session (Agent-Invoked)

The agent can invoke the handoff script at any point when it detects context weight building up — not just at session end. Use mode `migrate` to reset conversational memory while preserving state.

## prompt.md Structure

```markdown
# Session Handoff — MODE
Generated: timestamp
Mode: migrate|close|handoff

## Objective
What we're trying to achieve

## State
### Done / In Progress / Pending / Blocked

## Key Decisions (settled)
Things that shouldn't be re-litigated

## Files Touched
Modified or read during the session

## Uncommitted Changes
Git diff --stat summary

## Recent Commits
Last 5 onelines for orientation

## Blockers
What's preventing progress

## Next Steps
Concrete numbered actions to resume from

## Resumption Instructions (handoff only)
Don't re-derive settled decisions. Resume from Next Steps.
```

## File Locations

| Artifact | Path |
|----------|------|
| Handoff script | `~/.harness/hooks/session_handoff.py` |
| Stop hook config | `.kiro/hooks/session-handoff-stop.json` |
| SessionStart hook config | `.kiro/hooks/session-handoff-resume.json` |
| Output (project) | `~/memory-bank/projects/<repo>/prompt.md` |
| Output (archive/close) | `~/memory-bank/handoffs/<repo>-closed-<timestamp>.md` |
| Output (global fallback) | `~/memory-bank/handoffs/prompt-<timestamp>.md` |

## Agent Behavior

- **On Stop**: Always offer the choice. Default to handoff if work is incomplete, close if done.
- **On migrate**: After writing prompt.md, treat prior conversational context as stale. Re-read the prompt.md as your new ground truth.
- **Fail-open**: If the user declines or doesn't respond, do nothing. Never block session end.
- **Don't re-litigate**: Decisions marked as "settled" in the prompt.md are final unless new evidence falsifies them.
