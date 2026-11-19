# Full-Harness Eval — Specs MCP Impact

## Current — 2026-11-18

Run a one-edit paired pilot before using this design to compare the ten-edit
workflows. The pilot asks whether the same independent acceptance check can
produce a valid result for both arms within the cap. The corrected pair finished
in 454 seconds: specs-on exited 0 and failed 2 of 3 checks; specs-off exited 0
and failed 1 of 3 checks (three attempts reached DEAD where four were required).
Both acceptance verdicts are saved in the [pilot receipt](results/pilot-20261118T090000/pilot.json).
This verifies the measurement path only; one paired task does not establish a
harness quality effect or justify promotion to the ten-edit evaluation.

The first run was discarded after config preflight showed both arms inherited
the global Specs server. The 2026-11-18 corrected configs use the OpenCode V1
remote-server schema and explicitly disable inherited tools outside each arm.
The superseded status is preserved in
[the dated pilot note](results/pilot-20261118T090000/superseded-2026-11-17-pilot-status.md).
The ten-edit design below defines the workload. The pilot contract defines how
to compare acceptance. See the
[SATNA source review](../specs/dispositions/satna-harness-reference-integration.md).

### Paired pilot requirements

- P1. When a pilot is registered, the system shall freeze the task inputs, acceptance checks, model identity and resource limits.
- P2. When a pilot is executed, the system shall apply the same evaluator-owned checks to each arm's snapshot.
- P3. If a scheduled arm has no usable snapshot or its verifier cannot produce a verdict, then the system shall mark that observation as unscored.
- P4. When an arm records its result, the system shall record process status separately from the acceptance verdict.
- P5. When a paired pilot is reported, the system shall show elapsed time, reported usage and operator interventions alongside acceptance verdicts.
- P6. If the paired run reaches its cap before recording both acceptance verdicts, then the system shall mark the pair inconclusive.

### Pilot setup and acceptance

- Before either arm runs, resolve each arm with `opencode debug config` and
  `opencode mcp list`. Arm A must expose the declared shared servers and its
  isolated Specs endpoint; Arm B must expose the shared servers with Specs
  explicitly disabled. Disable inherited servers outside the arm contract.
  If the resolved model, MCP set, or connection state differs from the frozen
  setup, mark the pair inconclusive before prompting the model.
- Use the OpenCode configuration schema accepted by the installed CLI. For
  the current V1 CLI, remote servers use `type: remote`; a project entry must
  fully replace a same-named global entry. Local test servers must use an
  arm-scoped database so tool calls cannot alter the user's global records.
- Use the first `taskq` edit and two isolated copies of the same seed. Freeze
  the model revision, reasoning settings, agent version, prompt and check
  digest before either arm runs. The compared treatment is the bundled Specs
  MCP and steering change described below.
- Give each arm four minutes and its verifier one minute. Reserve the remaining
  two minutes of the 12-minute cap for setup and reporting. Apply the frozen
  checks outside the agent's writable
  workspace. For the first edit, check first-attempt success, success after a
  transient failure, and exhaustion of the declared retry allowance.
- Record the start revision, output snapshot, check digest, check result,
  agent exit status and verifier output per arm. Record elapsed seconds,
  provider-reported tokens or cost when available, and the count and kind of
  operator interventions. Mark unavailable usage as unknown. An intervention
  that changes an arm's inputs or state makes the pair incomparable.
- Run `python eval/verify_pilot.py --snapshot <arm-root> --timeout-seconds 55`
  against each immutable arm snapshot. The evaluator injects controlled
  transient failures through a `Worker` subclass and checks first-attempt
  success, recovery after one failure, and terminal `DEAD` after three
  retries; the same assertions and timeout apply to both arms.
- Given an agent exit of zero and a failed acceptance assertion, the
  acceptance verdict is fail. Given the same exit and passing assertions, it
  is pass. Given a missing snapshot or verifier timeout, it is unscored.
- Given an absent or unimportable `taskq` package, the verifier shall report
  unscored with the reason; given an imported package whose behavior violates
  an assertion, it shall report fail with the failed check.
- A complete pair demonstrates the measurement path. Use the
  [existing matched-control and held-out gates](../docs/playbooks/memory-and-harness-integration.md#requirements)
  to judge whether to promote an intervention.

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

**Arm B (specs-off)** has the shared tools listed below. The proposed effect
is that the Specs MCP and steering bundle helps Arm A preserve prior decisions
across the ten edits.

**Falsification:** If Arm B's final requirement coverage and coherence score
are within 0.05 of Arm A, the experiment shows no detectable quality lift
for the Specs MCP and steering bundle on this workload. Use measured time,
usage and interventions to assess overhead.

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
| **Requirement coverage** | Pass fraction on the evaluator-owned acceptance checks common to both arms | 0.25 |
| **Test pass rate** | `pytest taskq/tests/ --tb=no -q` in each arm, reported separately from requirement coverage | 0.20 |
| **Dead code** | `vulture taskq/` | 0.15 |
| **Duplication** | AST duplicate detection | 0.10 |
| **Type errors** | `pyright taskq/` | 0.10 |
| **Lint score** | `ruff check taskq/` | 0.10 |
| **Plan completion** | Tasks done/total in specs.db, Arm A only | Informational |

Normalize the six shared metric weights by their sum (0.90) before computing
the comparative composite. Keep arm-only Specs DB measurements in the spec
quality report.

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
