---
harnesses: [claude, opencode, codex, vscode, pi, kiro, copilot]
order: 150
---

# CURRENT — Four-role orchestration

Use role labels as task contracts over the current harness's available models and tools. The role name alone does not require a context switch. Keep the task moving in the current capable context unless a different role adds necessary expertise or saves real work.

## Roles

| Role | Responsibility | Tool boundary |
|---|---|---|
| Leader / orchestrator | Owns the objective, plan, task contracts, integration, and completion; may implement a bounded fix directly. | Uses the current session's tools and policy. |
| Fighter / doer | Implements an assigned file set to the Leader's contract and runs its named checks. | Read/write tools for the assigned work. |
| Scout / reader | Reads broadly, then returns concise findings with source pointers. | Read-only; no edits or commands. |
| Oracle | Handles high-uncertainty diagnosis or an explicitly assigned implementation when its expertise justifies the escalation. | Consult mode is read-only. Fix mode may edit only assigned files and run named checks. |

## Routing

- Start with the Leader when it can resolve the task with the available evidence and tools.
- Use a Fighter for a bounded implementation that benefits from a separate executor or independent file set.
- Use a Scout for bulk reading, search, or log inspection whose output can be a pointer-rich digest.
- Escalate to Oracle when the problem needs higher expertise, independent diagnosis, or a direct fix that avoids an unnecessary handoff.
- Escalation is not a mandatory ladder. The role that receives the task may complete it if its mode, tools, and assigned scope allow.
- Preserve useful task context across handoffs. A handoff must state the goal, evidence, exact file scope, role mode, constraints, and acceptance checks.

## Oracle dispatch contract

Every Oracle task declares one mode:

- `Consult`: inspect evidence and return a bounded diagnosis or plan; do not mutate files or run commands.
- `Fix`: implement the assigned change, run only the named checks, and return changed paths and results. Do not dispatch or delegate to another agent.

If the dispatch omits a mode, use `Consult`. If a Fix assignment omits file scope or checks, report the missing contract and do not guess. The Leader remains accountable for integration and acceptance. Tool allowlists constrain available actions; prompts and task scopes are instructions, not a filesystem sandbox.

## Evidence and completion

- A Scout digest helps locate evidence; it is not itself a pass/fail result.
- The assigned executor reports exact checks and their observed outcomes.
- The Leader integrates the result, verifies the acceptance conditions, and records unresolved unknowns.
- Do not make model, cost, latency, or success-rate claims without measurements for the selected route.

## Superseded rule

The fixed Opus/Sonnet gate ladder and read-only-only Oracle contract were superseded 2026-11-22. Prior wording is summarized in `150-orchestration.superseded-2026-11-22.md`.
