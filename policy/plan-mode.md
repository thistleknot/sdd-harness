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

## The word is `architect`

`architect` is the operator's keyword for entering this whole mode — "architect this",
"architect the migration". It means author the ledger, do not write code. "plan" stays
a recognised synonym (this state is natively called plan mode), but the artifact is
`playbook.md`, not `plan.md`, and pending work is `[OPEN]`, not `[TODO]`.

**And it is named for what it changes.** Plan mode mints `plans/<random-slug>.md`
before anything is known about the work; that is a placeholder. REQ #36: the
filename is the kebab slug of the artifact's own H1 (<= 6 words / 60 chars), and
renaming it is the first act once writes unlock. `~/.claude/hooks/playbook.py
--pivot` flags a mismatch at `ExitPlanMode` and prints the exact target path.

## Exit → Playbook (the default for multi-task architectures)

Persisting the plan answers *where the plan lives*. It does not answer *who executes
it*, and executing a 9-step plan inline means the session working step 9 still carries
every artifact of steps 1–8. That is context rot, and it makes the last tasks the worst.

For any architecture of **3+ tasks**, the output is `playbook.md` — a ledger of `[OPEN]`
items worked **one task per fresh subagent session**, each running the model ladder
(fable authors the ledger → opus subplans one task → sonnet implements it → opus only
re-enters on `[BLOCKED]`). The main session holds the ledger and nothing else.

Tasks group into **layers**, one operation type per layer:

- **parallel** — independent, like a mean and a stdev. Every `[OPEN]` task in the layer
  is dispatched at once (max 4 concurrent, `_Files:` sets disjoint).
- **sequential** — serially dependent, like an EMA or an RNN. One at a time, in order.

A layer is a **barrier**: nothing in the next layer starts until every task in the
current one is `[DONE]`. Mixing types inside a layer is legal but discouraged — it
strands the parallel siblings and breaks prompt-cache reuse across the fan-out.

Offered automatically by `~/.claude/hooks/playbook.py` (PostToolUse on `ExitPlanMode`;
also `--plan` on UserPromptSubmit, which catches architect requests before plan mode is
even entered). Full protocol and ledger format: `~/.claude/rules/playbook.md`.

Note: a hook cannot switch the session model — no such field exists in the hook output
contract. The ladder is therefore per-dispatch, not per-session.

## Why This Matters

Without this policy, plan mode is "think then forget." The agent exits plan mode, loses the structured reasoning, and either re-derives it (wasting tokens) or proceeds without the structure (losing quality). Persisting the plan as the first write solves both failure modes.
