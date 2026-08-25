---
inclusion: manual
---

# Claude Code as Executor

Kiro is the orchestrator (Manager). Claude Code is a fresh-context executor.
This follows the MEA loop pattern (LongHorizon-Harness, arXiv:2608.01964).

## When to Use Claude Code

Dispatch to Claude Code when:
- The task is self-contained and well-specified (executor pattern)
- You want a fresh-context perspective (no accumulated session bias)
- The task benefits from Claude Code's native tools (Edit, Bash, direct file access)
- You want to test whether a task spec is clear enough for an independent agent to execute

Do NOT dispatch when:
- The task requires this session's accumulated context
- The task needs MCP tools only available here (specs, memory-index, retrieve-skills)
- You're still in the spec/design phase (Kiro decides, Claude executes)

## Dispatch Pattern

```powershell
# One-shot task execution
$task = "your task description here"
$cwd = "C:\path\to\project"
Start-Process -FilePath "claude" `
  -ArgumentList @("-p", $task, "--max-turns", "10", "--output-format", "text", "--cwd", $cwd) `
  -NoNewWindow -PassThru -Wait `
  -RedirectStandardOutput "$env:USERPROFILE\.harness\events\claude-exec-out.txt" `
  -RedirectStandardError "$env:USERPROFILE\.harness\events\claude-exec-err.txt"
```

## Task Framing Rules

Always include in the task prompt:
1. **What to do** — specific, bounded, one objective
2. **What NOT to do** — constraints (don't commit, don't install, don't modify X)
3. **Verification** — how to confirm it worked (run this test, check this output)
4. **Scope boundary** — files/dirs you may touch, nothing else

Example:
```
TASK: Add a health endpoint to scripts/my_server.py that returns {"status":"ok"}.
CONSTRAINTS: Do not modify any other files. Do not install new dependencies.
VERIFY: Run 'python scripts/my_server.py &' then 'curl localhost:PORT/health' returns 200.
SCOPE: scripts/my_server.py only.
```

## Audit After Execution

After Claude Code returns:
1. Read the output file (`claude-exec-out.txt`)
2. Verify the claimed changes exist (read the files)
3. Run the verification step yourself
4. If verified → advance task state in specs
5. If unverified → log to failure registry with evidence

This IS the Auditor in the MEA loop.

## Capturing Lessons

When Claude Code makes a mistake Kiro wouldn't:
- Record it: `add_failure(approach, evidence, context)`
- Distill the pattern: what was the instruction gap?
- Port the fix: update this steering file or add to CLAUDE.md

When Claude Code succeeds at something Kiro struggled with:
- Record it: `add_canon(claim, verdict="yes", evidence)`
- Understand why: was it fresh context? Different tools? Better framing?
- Port the advantage: update Kiro steering rules

## Session Isolation

Claude Code ALWAYS reads project-level CLAUDE.md and its own session memory.
You cannot prevent this. Instead, work WITH it:

- The CLAUDE.md in .harness IS your steering for Claude's executor behavior
- Prefix tasks with clear framing so it doesn't default to "resume last session"
- Use `--no-session-persistence` to prevent new sessions from accumulating
- The dispatch script pipes the task via stdin to avoid PowerShell quoting issues
- If Claude ignores the task and resumes old context, the framing was too weak

The `dispatch_claude.ps1` script handles all of this. Use it instead of raw CLI.

## Cost Awareness

Claude Code Pro = $200/mo. Each dispatch costs tokens. Prefer:
- Batching related subtasks into one dispatch
- Using `--max-turns` to cap runaway exploration
- Capturing output so failed runs aren't repeated (failure registry)
