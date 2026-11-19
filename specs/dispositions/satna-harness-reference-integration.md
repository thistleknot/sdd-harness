<!-- GENERATED — DO NOT EDIT — source: specs/specs.db -->
# SATNA harness reference integration

**Slug:** `satna-harness-reference-integration`
**Tags:** harness,reference-integration,evaluation,verification
**Created:** 2026-11-18T02:31:28+00:00

---

## Current disposition — 2026-11-17

Use Harbor's separate verifier and result records in the [full-harness eval pilot](../../eval/SPEC-full-harness.md). The two arms share an acceptance suite owned by the evaluator, and their reports distinguish the agent's exit status from acceptance, time, usage and operator interventions. The pilot contract is written. The verifier implementation and model run are pending.

Input was the local note at `docs/references/satna.md`. Seven shallow checkouts were cloned into `references/`, and the existing Spec Kit checkout was reused. All eight were clean when inspected. Source links below are pinned to the inspected revisions.

## Extracted features

| Project | Mechanism | Disposition in this harness | Evidence |
| --- | --- | --- | --- |
| Learn Harness Engineering | A generator and a separate evaluator leave revision evidence in the exercise. | Reuse the existing independent reviewer and saved verification output. The exercise is a fixture reference when testing incomplete submissions. | [Project 05](https://github.com/walkinglabs/learn-harness-engineering/blob/f7aa3b0c7aec0a682535b37586281394e07476b7/projects/project-05/README.md), [board submission and review](../../board.py#L407) |
| 12-Factor Agents | Execution state can be derived from workflow events, and launch, pause and resume can expose explicit boundaries. | Keep the existing workflow checkpoint and project handoff. Use the event-derived approach as a design reference when a concrete resume bug involves mismatched business and execution state. | [Factor 5](https://github.com/humanlayer/12-factor-agents/blob/d20c728368bf9c189d6d7aab704744decb6ec0cc/content/factor-05-unify-execution-state.md), [Factor 6](https://github.com/humanlayer/12-factor-agents/blob/d20c728368bf9c189d6d7aab704744decb6ec0cc/content/factor-06-launch-pause-resume.md), [existing checkpoint contract](../../sdd-deliverables-contract.md) |
| AGENTS.md | The format provides a standard place for setup, test and contribution instructions. The upstream site recommends local instructions for nested projects. | Use the existing instruction projection. Treat nested support as host-specific and verify it on the affected host if a project needs it. | [Upstream examples](https://github.com/agentsmd/agents.md/blob/d001185d792eb6402a58e4cbef1c228b309ec25d/README.md), [harness manifest](../../manifest.toml) |
| Spec Kit | An analysis step compares requirements, plan and task artifacts before implementation. | Reuse the existing Spec Kit workflow for initialized projects and the harness receipt workflow for ordered handoffs. The course list provides a reference for the cross-artifact analysis step. | [Analyze command](https://github.com/github/spec-kit/blob/684b3d8e05263a7c1948d3d0699ab1cb4f77c3d5/templates/commands/analyze.md), [existing checkpoint contract](../../sdd-deliverables-contract.md) |
| Deep Agents | Compaction keeps a recent tail and writes evicted messages to a history file addressed by session ID. | Candidate for a compaction follow-up. First reproduce a case where the incumbent project-scoped handoff plus bounded source opening cannot recover evidence needed to finish. Measure retrieval on that case before changing retention. | [Summarization middleware](https://github.com/langchain-ai/deepagents/blob/709070b4128068fa1ce178a78a7065d6874dc15c/libs/deepagents/deepagents/middleware/summarization.py), [existing memory contract](../../docs/playbooks/memory-and-harness-integration.md) |
| Mini SWE Agent | The agent serializes ordered messages with finish status and available model stats in one trajectory. | Use the trajectory structure as a reference if a legacy eval needs more than its output tail. Use the current RSI ledger for experiments it already supports. | [Agent serialization](https://github.com/SWE-agent/mini-swe-agent/blob/04d809ceab9df28f9adaed044884180159172930/src/minisweagent/agents/default.py#L159), [RSI runner](../../eval/rsi/round.py) |
| Awesome AI Anatomy | Cross-project tables link to individual architecture teardowns. | Use as a source map for future comparisons. Treat architecture and security judgments as third-party claims that require independent verification. | [Cross-cutting analysis](https://github.com/NeuZhou/awesome-ai-anatomy/blob/347422e344c81169c30876922ec2bfafe3839106/CROSS-CUTTING.md) |
| Harbor | Trials distinguish execution results, verifier results, exceptions and timings, and support a separate verifier environment. | Adopt the measurement split in the paired-pilot spec. Keep Harbor as a reference until a named benchmark needs its runner and the project can map its task and scoring contracts. | [Trial result model](https://github.com/harbor-framework/harbor/blob/e6c387d2b183cd93c35f5697d380f71143d9cbdf/src/harbor/models/trial/result.py), [separate verifier example](https://github.com/harbor-framework/harbor/blob/e6c387d2b183cd93c35f5697d380f71143d9cbdf/examples/tasks/verifier-mode-matrix/separate-explicit/task.toml) |

## Evidence for the first change

- [observed] The [legacy runner](../../eval/run_full_harness_eval.py) derives edit success from the agent process exit code.
- [observed] The saved [Specs-on](../../eval/results/full-harness/specs-on.json) and [Specs-off](../../eval/results/full-harness/specs-off.json) artifacts each contain ten edit records, zero successful exits and zero acceptance verdicts.
- [observed] The [legacy scorer](../../eval/score.py) reads tests from the workspace being evaluated. The former full-harness spec also assigned comparative weight to a plan-completion metric specific to one arm.
- [inferred] The records cannot establish whether either arm met the same independently defined requirements. A frozen shared verifier closes that measurement gap if both arms can supply usable snapshots.
- [unknown] The pilot's end-to-end feasibility depends on the current runner and available model. A three-case offline verifier test followed by one bounded matched pair would establish it. Effectiveness remains unknown until a matched-control run passes the existing RSI gate.
