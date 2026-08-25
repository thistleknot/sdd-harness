<!-- GENERATED — DO NOT EDIT — source: specs/specs.db -->
# DDR: Deployment Decision Reliability Framework for Agent Evals

**Slug:** `ddr-eval-framework`
**Tags:** eval,reliability,g-theory,paper-extraction
**Created:** 2026-08-15T04:18:37+00:00

---

## Source
arXiv:2608.11323 — Srinivasan (2026-08-11)

## Core Insight
Agent benchmarks don't measure what people think they measure. The "agent effect" (how much being Agent A vs Agent B matters) is <3% of variance. What dominates is the agent×task interaction (7-23%) — agents are specialized, not uniformly better/worse.

## The Five DDR Decisions (adapted for our eval)

1. **Size the eval for the decision you're making.** A 50-task eval can reliably rank two agents overall but CANNOT reliably say "Agent A is better at code review." Need variance components to know when you have enough tasks per cell.

2. **Stratify by difficulty quartile.** Aggregate reliability is an illusion when hard tasks contribute zero signal. Report results per quartile or drop the hardest quartile from ranking (use it for qualitative analysis only).

3. **Never trust training-cell reliability.** The designs that look most reliable on the data you tuned on replicate WORST (r=-0.90). Always hold out tasks. Our eval already does this with sealed splits — good.

4. **Classify failures at cell level, not trace level.** Individual trace failures are idiosyncratic (noise). But "Agent A fails on multi-step planning tasks via premature commitment" generalizes (r=0.83). This maps to our failure-registry: signature the approach+task-class, not the specific instance.

5. **Report the capability-gap ratio.** Ratio of agent variance to total variance. Stable at 0.35-0.40 across enterprise benchmarks. If our eval shows a ratio below 0.20, the tasks aren't discriminating between agents — they're too easy or too hard.

## Implications for Our Eval Framework

- Our `eval/score.py` should compute variance components (agent, task, agent×task, residual) not just aggregate scores
- The failure registry's structural signatures already operate at the right level (cell-level, not trace-level)
- We should add a difficulty-stratified breakdown to eval reports
- Our "hooks-on vs hooks-off" comparison needs enough tasks per cell to achieve Eρ² > 0.70

## Method: Generalizability Theory (G-theory)

Four-facet decomposition: agent × task × check_type × replication. Fit with Henderson Method-I (cheap, closed-form), confirmed with REML and Bayesian GLMM. The key output is the G-coefficient (Eρ²) — analogous to Cronbach's alpha but for multi-facet designs.

## What We'd Need to Implement

1. A variance-decomposition function that takes our eval results and computes σ²_agent, σ²_task, σ²_agent×task, σ²_residual
2. Henderson Method-I is just ANOVA expected mean squares — no dependencies needed
3. Report Eρ² per eval run alongside the aggregate score
