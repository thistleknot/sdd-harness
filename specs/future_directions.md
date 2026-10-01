<!-- GENERATED — DO NOT EDIT — source: specs/specs.db -->
# Future Directions (Uncommitted)

Work that MIGHT be worth doing. Nobody owns these and none is scheduled — that is what separates a direction from a `planned` task in tasks.md.

Each carries the **trigger** that would promote it. A direction with no trigger never gets revisited, because nothing tells you to look.

## OPEN — harness

- **#1** Teach specs_mcp per-repo DB resolution
  - Why: specs_mcp.py pins HERE = Path(__file__).parent, so one server serves exactly one project. Individual repos therefore keep hand-written .specs/future-directions.md instead of the queryable machinery.
  - Revisit when: a second repo accumulates more than ~3 entries under a repo:<name> scope, or someone wants query_specs to span repos
  - Tags: architecture,specs-server

- **#2** Decide whether the failures registry is load-bearing or dead machinery
  - Why: failures table, signature matching, check_failures and revive_failure are all built and wired, and hold 0 rows. CLAUDE.md 13: unused patterns decay out.
  - Revisit when: the next genuine dead end — log it and see whether check_failures catches a repeat before it costs a cycle
  - Tags: hygiene
