# Full-Harness Eval — Specs MCP Impact

## Objective

Measure whether structured spec-tracking (via the specs MCP server) improves
code coherence, requirement satisfaction, and plan adherence when an agent
builds a feature across multiple edits with full MCP access.

## Hypothesis

**Arm A (specs-on)** will produce higher requirement coverage and fewer
regressions because the agent:
- Records acceptance criteria before coding → constrains scope
- Tracks task state → doesn't lose thread across edits
- Records settled findings → avoids re-deriving decisions
- Has a persistent plan → edits build on each other coherently

**Arm B (specs-off)** relies on context window memory alone. Across 10 edits
the agent will lose track of prior decisions, re-implement, and drift.

**Falsification:** If Arm B's final requirement coverage and coherence score
are within 0.05 of Arm A, the specs server adds overhead without measurable
benefit.

## Arms

| Arm | MCP Servers | Description |
|-----|-------------|-------------|
| A (specs-on) | retrieve-skills, memory-index, specs, todo | Full harness |
| B (specs-off) | retrieve-skills, memory-index, todo | No specs server |

Both arms:
- Use same model (local ollama via opencode, no `--pure`)
- Start from identical seed repo
- Get same 10 prompts in same order
- Have full MCP access (except specs for Arm B)
- Run in isolated git repos

## Target Module

Same `taskq/` library from the 10-edit eval. Known surface, comparable baselines.

## Prompts (same 10 from existing eval)

Reuse `prompts.json`. The prompts don't reference the specs server — the agent
independently decides whether to use spec tools based on its steering/skills.

## Steering Difference

Arm A gets a steering doc that says:
> Before implementing, record requirements with `add_requirement`. Track your
> plan with `add_task`/`update_task`. Record decisions with `add_decision`.
> After verifying behavior, record findings with `add_canon`.

Arm B gets no such steering. This simulates the "harness-aware" vs
"vanilla agent" distinction.

## Metrics

### Quantitative (automated, after each edit)

| Metric | How | Weight |
|--------|-----|--------|
| **Requirement coverage** | Parse specs.db requirements → check each criteria against code/tests | 0.25 |
| **Test pass rate** | `pytest taskq/tests/ --tb=no -q` | 0.20 |
| **Dead code** | `vulture taskq/` | 0.15 |
| **Duplication** | AST duplicate detection | 0.10 |
| **Type errors** | `pyright taskq/` | 0.10 |
| **Lint score** | `ruff check taskq/` | 0.10 |
| **Plan completion** | tasks done/total in specs.db (Arm A only, informational for B) | 0.10 |

### Qualitative (post-run)

- Does Arm A's specs.db accurately reflect what was built?
- Did Arm B introduce features not asked for (scope creep without plan)?
- Which arm's commit history reads more coherently?

## Additional Measurement: Spec Quality

For Arm A only, after all 10 edits:
- How many requirements were recorded? Were they testable?
- How many tasks exist? Do they match the 10 prompts?
- Any canon entries? Are they accurate?
- Does the rendered `tasks.md` tell a coherent story?

This is the "self-documentation" metric: does the agent leave useful artifacts
for the next session to pick up from?

## Runner Changes from 10-Edit Eval

1. Remove `--pure` flag (MCP must be enabled)
2. Set `OPENCODE_MCP_CONFIG` env to point at harness.json (or a per-arm variant)
3. For Arm B: use a config that excludes `specs` server
4. For Arm A: inject the steering doc into the working dir as `AGENTS.md`
5. After all edits: dump specs.db contents for Arm A

## Execution Plan

1. Create per-arm configs (harness-a.json with specs, harness-b.json without)
2. Create steering doc for Arm A
3. For each arm:
   a. Create arm repo from seed
   b. Place config + steering
   c. Loop 10 prompts via `opencode run "<prompt>"` (no --pure)
   d. After each: git snapshot + run scorer
4. After both complete: aggregate, compare, plot

## Constraints

- 5 min timeout per edit (same as existing)
- Model: use the same model for both arms (controlled variable)
- No human intervention during run
- Specs DB starts empty for Arm A (no pre-seeded context)

## Open Questions

1. Should Arm A also get retrieve-skills access to the `spec` skill? (Gives it
   instructions on HOW to use the tools.) Leaning yes — that's the full harness.
2. Should we run 3 repetitions per arm for statistical power? (30 edits × 2 arms
   = ~5 hours at 5min/edit.) Leaning: single run first, repeat if signal is weak.
