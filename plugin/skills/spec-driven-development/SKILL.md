---
name: spec-driven-development
description: >
  Enforce spec-first methodology: requirements before design, design before code.
  Use when starting a new feature, planning a refactor, or any multi-file change.
  The agent should check specs MCP for existing requirements, create specs if missing,
  get approval before implementing.
---

# Spec-Driven Development

## When to activate
- Starting any new feature or multi-file change
- User says "let's build", "add a feature", "implement"
- Before any significant code change that touches observable behavior

## Workflow

1. **Check existing specs**: `query_specs(type="requirements")` — is this already specified?
2. **If no spec exists**: `add_requirement(title, criteria, priority)` — spec it first
3. **Verify phase**: spec must be in `implement` phase before writing code
4. **Implement**: write code that satisfies the acceptance criteria
5. **Update task**: `update_task(id, status="done")` when criteria are met
6. **Log lesson**: `log_memory(content, scope="local")` if something non-obvious was learned

## Phase -1 Gates (check before writing code)

1. Spec Completeness — no unresolved markers, testable criteria, scope stated
2. Simplicity — minimal new files, no future-proofing
3. Anti-Abstraction — use framework directly, no unnecessary wrappers
4. Incumbent Search — check for existing code that does this
5. Test Strategy — acceptance criteria mapped to assertions

## Anti-patterns
- Writing code before specifying what "done" means
- Implementing without checking if something similar already exists
- Skipping the test strategy gate
- Treating a spec as bureaucracy rather than a thinking tool
