# Harness Integration: Kiro as Orchestrator

This Kiro workspace IS the `.harness` project — the SDD (Spec-Driven Development)
orchestration layer. Kiro is the Manager in the MEA loop.

## Role Distribution

| Role | Agent | Responsibility |
|---|---|---|
| **Manager** | Kiro (this) | Specs, decisions, task planning, failure registry, memory |
| **Executor** | Claude Code CLI | Fresh-context task execution, file edits, tests |
| **Auditor** | Kiro (this) | Verify Claude's claims against environment state |

## Available Infrastructure

### MCP Servers (Kiro-side)
- **specs** (:8057) — requirements, decisions, tasks, settings, canon, failures, dispositions
- **memory-index** (:8055) — vector search over decisions/patterns/lessons
- **retrieve-skills** (:8765) — skill routing by task description
- **todo** (:8056) — project-local work tracking
- **data-science-skills** — DS/ML/RL technique corpus

### Claude Code (executor-side)
- Native file Read/Edit/Write
- Bash/PowerShell execution
- Git operations
- Web search/fetch
- Its own CLAUDE.md context (in this repo)

## Workflow

### For implementation tasks:
1. Spec the task in Kiro (add_task, define acceptance criteria)
2. Check failure registry (check_failures) — has this been tried?
3. Dispatch to Claude Code via `scripts/dispatch_claude.ps1`
4. Audit the output (read files, run tests, verify claims)
5. Update task state only on verification
6. Log lessons (failures or canon) based on outcome

### For design/planning tasks:
- Stay in Kiro. Use specs tools, memory search, skill retrieval.
- Claude Code doesn't plan. It executes.

### For debugging:
- Kiro diagnoses (hypothesis, evidence, isolation)
- Claude Code performs the mechanical fix
- Kiro audits the fix (tests pass, no regression)

## Teacher-Student Pattern

Kiro writes the steering rules that Claude Code follows (via CLAUDE.md).
When Claude Code makes mistakes:
1. Understand why (missing constraint? ambiguous spec? wrong assumption?)
2. Fix the steering (update CLAUDE.md or add to failure registry)
3. The lesson improves both agents' future performance

When Claude Code succeeds unexpectedly:
1. Understand what worked (fresh context? different approach?)
2. Port the insight to Kiro steering rules
3. Both environments improve

## Cost Discipline

- Don't dispatch trivial tasks (< 30 seconds in Kiro → just do it here)
- Don't dispatch design work (Claude will execute, not deliberate)
- DO dispatch: file-heavy refactors, test writing, multi-file implementations
- DO dispatch: tasks that benefit from fresh-context (avoid accumulated bias)
- Cap `--max-turns` at 10-15 for bounded cost
- Review dispatch logs weekly for waste patterns
