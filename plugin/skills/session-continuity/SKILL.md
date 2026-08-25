---
name: session-continuity
description: >
  Cross-session memory and handoff. Use at session start to load prior context,
  and at session end to package state for the next session. Ensures no work is
  lost between sessions and the agent can resume from where it left off.
---

# Session Continuity

## At Session Start
1. `search_memory("<current task context>")` — check for prior decisions/patterns
2. `list_todos(workspace_root=<git_root>)` — surface pending work
3. `retrieve_skills("<task description>")` — load relevant specialized instructions
4. Check for `prompt.md` or handoff files in the workspace

## During Work
- `log_memory(content, scope="local", repo=<root>)` — capture significant decisions
- `add_todo(task, workspace_root=<root>)` — track follow-ups not done now
- `complete_todo(id, workspace_root=<root>)` — mark done as you go

## At Session End
- Package current state: what was done, what's pending, what's blocked
- Log lessons learned for retrieval in future sessions
- Update any living documents (progress.md, plan.md)

## Memory Lifecycle
- Ephemeral bits logged via `log_memory` — auto-promote after 3 recalls
- Under-recalled bits decay over time (annealing)
- Durable entries via `add_memory` — for proven patterns only
- Search often — useful stuff rises through recall frequency
