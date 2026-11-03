---
name: session-continuity
description: >
  Cross-session memory and handoff. Use at session start to load prior context,
  and at session end to package state for the next session. Ensures no work is
  lost between sessions and the agent can resume from where it left off.
---

# Session Continuity

## At Session Start
1. Read the handoff injected by `session_resume.py` when this harness has lifecycle wiring; it selects the newest readable local prompt or exact-project archive.
2. Compare its objective, next action, and project identity with the current user request, workspace, and active spec; the current user request sets the objective when they differ.
3. `search_memory("<current task context>", workspace_root=<absolute_workspace>, session_id=<session>)` — recall scoped evidence; open and cite source records before relying on them.
4. `list_todos(workspace_root=<git_root>)` — surface pending work.
5. `retrieve_skills("<task description>")` — load relevant specialized instructions.
6. Resume from the verified handoff state; don't re-derive settled decisions unless new evidence challenges them.

## During Work
- `log_memory(content, scope="local", repo=<root>)` — capture significant decisions
- `add_todo(task, workspace_root=<root>)` — track follow-ups not done now
- `complete_todo(id, workspace_root=<root>)` — mark done as you go

## At Session End
- Write a handoff at a task boundary or when work pauses; include the objective, completed and pending work, blockers, settled decision references, files changed, and the next action.
- Use `close` only when the work is complete; use `migrate` when continuing immediately in a fresh context.
- Record any follow-up in the project todo list and evidence-backed lessons in the existing memory store.

## Memory Lifecycle
- Recall alone never promotes or strengthens memory; record outcomes through the explicit evidence-backed feedback contract.
- Model-generated memory candidates require explicit review; confidence alone does not approve them.
- Keep reusable lessons linked to their source observations and outcome evidence.

## Shared Decision and Editing Rules
- Cite settled choices from the active spec or SpecsDB decision; flag disagreements in the handoff with the new evidence instead of creating a second decision register.
- Concurrent agents may edit the same checkout only when their owned files are disjoint; use a task worktree or serialize edits when ownership overlaps.

## Lifecycle Coverage
- Check `manifest.toml` for the selected harness's lifecycle route; native hooks and instruction-driven handoffs differ, and an undeclared route has no automatic resume guarantee.
