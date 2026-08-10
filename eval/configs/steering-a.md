# Spec-Driven Development Steering

You have access to a `specs` MCP server that tracks requirements, decisions,
tasks, settings, and findings in a persistent database.

## Before implementing any edit:

1. Record acceptance criteria: `add_requirement(title, criteria, priority)`
2. Add a task for the work: `add_task(title, "doing", details)`
3. If making an architecture choice: `add_decision(title, chosen, rationale)`

## After verifying each edit works:

1. Mark the task done: `update_task(id, status="done")`
2. If you learned something reusable: `add_canon(claim, verdict, evidence)`
3. If a parameter matters: `add_setting(key, value, citation)`

## Query your own state:

- `list_tasks()` — see what's done, what's next
- `query_specs(type, query)` — search prior decisions or requirements

## Why this matters:

Your context window is finite. These tools persist your reasoning across edits
so you don't re-derive decisions or forget constraints from earlier work.
