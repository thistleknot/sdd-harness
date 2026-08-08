# Plan Mode Policy

## What Plan Mode Is

Plan mode is a native read-only state in all three harnesses (Shift+Tab in Claude Code, Tab in opencode). While active, the agent cannot write files. This policy defines what the agent DOES during plan mode and what happens when it exits.

## The Rule

Plan mode is the **prep phase** for whatever comes next. The agent's job in plan mode is to produce a structured plan that persists as an artifact the moment writes are unlocked.

**On exit from plan mode, the first write is always the plan itself.** Never discard planning work. Never resume with "okay, I'll start implementing" without first committing the plan to disk.

## Plan Mode × SDD Modes

| Mode being prepped | What to do in plan mode | First write on exit |
|-------------------|------------------------|---------------------|
| **Spec** | Research codebase, identify requirements, draft acceptance criteria mentally, identify scope boundaries | Write `requirements.md` (or `plan.md` if spec lifecycle not armed) |
| **Bug Fix** | Read error context, walk backward through the chain, form hypotheses, identify the earliest broken link | Write diagnosis to `plan.md` or directly to `bugfix.md` if `.spec/` is armed |
| **Quick Spec** | Compressed: research + draft requirements + design + task breakdown in one pass | Write the full spec artifact set on exit, then implement |
| **Do** | Overkill for trivial tasks — but if entered: identify files to touch, confirm the change is mechanical | Execute the change (no plan.md needed for mechanical edits) |
| **Plan-only** | The user wants analysis, not action. Produce the plan and stop. | Write `plan.md` and stop. Do not implement. |

## Plan.md Format

When plan mode produces a `plan.md`, use this structure:

```markdown
# Plan: <what's being planned>

## Context
<What was read/discovered during plan mode>

## Approach
<The chosen strategy and why>

## Steps
1. <concrete action>
2. <concrete action>
...

## Risks / Open Questions
- <what could go wrong>
- <what needs clarification before proceeding>

## Acceptance Criteria
- [ ] <how to know it's done>
```

## Interaction with spec_gate

- If the repo is spec-armed (`.spec/` exists), plan mode output feeds directly into the spec lifecycle. `plan.md` becomes `requirements.md` or `design.md` depending on which phase is active.
- If the repo is NOT spec-armed, plan mode output writes to `plan.md` in the project root (or `.spec/plan.md` if the user arms it later).
- The spec gate does NOT block writes to `.spec/` artifacts — only source files. So writing the plan itself is always allowed, even in a gated repo.

## Why This Matters

Without this policy, plan mode is "think then forget." The agent exits plan mode, loses the structured reasoning, and either re-derives it (wasting tokens) or proceeds without the structure (losing quality). Persisting the plan as the first write solves both failure modes.
