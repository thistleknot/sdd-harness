<!-- GENERATED — DO NOT EDIT — source: specs/specs.db -->
# Canon (Settled Claims)

- **YES** — SDD exists to prevent three failure modes: sprawl (orphaned artifacts from context drift), decoherence (progressive agent drift from original intent across sessions), and Karp (explaining anomalies away instead of checking them)
  - Evidence: Observed in production: 222 untracked files accumulated without census, .conflict files never resolved, router dead 29hrs without detection. Literature: arXiv 2601.04170 decomposes agent drift into semantic/coordination/behavioral drift.
  - Tags: mission,sprawl,decoherence,karp

- **NO** — The current harness implementation meets the full SDD mission against sprawl, decoherence, and Karp
  - Evidence: NO: README.md defines the mission, but no sprawl census or orphan metric exists; hooks/convergence.py ignores code_dir and counts checkboxes rather than implementation evidence; no persisted anomaly schema/gate exists; conformance/ is empty; canonical specs contained unrelated rows and stale root documents. Requirements #3-#9 and tasks #11-#18 now define the missing controls but are not yet implemented.
  - Tags: sdd,sprawl,decoherence,karp,audit

- **YES** — MGPO (maxent-guided RL) improves macroF1@112 over SFT baseline by eliminating over-abstention errors
  - Evidence: SFT macroF1@112=0.5307 (tp=18 fn=4 fp=2 tn=88) → RL maxent macroF1@112=0.5400 (tp=18 fn=4 fp=0 tn=90). Delta +0.0093. RL fixed 2 over-abstention errors (fp 2→0), improved f1_abstain 0.857→0.900, preserved confabulation rate (fn=4 unchanged). Adapter max|B|=5.92e-3, frac_reward_zero_std=[0.20, 0.17]. Scored with prompt_style=abstain on n=112. Paired CI not yet computed.
  - Tags: rl, mgpo, vibethinker, macroF1, abstention, lift

- **YES** — Shortcuts that collapse required dimensions cost more than doing it right
  - Evidence: bootstrap_cohort used regime-only stratification (domain=ALL collapse) instead of the spec'd 2-axis MMR (regime x dataset). Production run at n=200 covers cells by volume but not by construction. The downstream crash on boxcox (equal-sized cells assumed) and the axis collapse both required rollback. Total cost: full session wasted + rollback + re-implementation vs 30 min to implement correctly.
  - Tags: anti-pattern,sampling,spec-violation

- **YES** — SFT conflicts across tasks (norm-limited interference), RL coexists (variance-limited, orthogonal updates). Parallel per-task RL with adapter merging retains 94-103% of single-task gains.
  - Evidence: Zhu et al. arXiv 2608.03573. Multi-stage SFT degrades -23.1% avg. Multi-stage RL gains +24.9%. RL updates: 20% params active, ||dW||=3e-2, cosine sim 1e-5 between tasks. SFT: 93% params, ||dW||=7.4, cosine sim 0.95+. GRPO advantage normalization cancels shared gradient direction, leaving variance-limited residuals. Naive Parallel-RL retains 94.2%, adapted (5% mixed data) reaches 103.2%. Temperature sweet spot ~0.65 for reasoning.
  - Tags: parallel-rl, grpo, orthogonal-updates, multi-task, merging, architecture

- **YES** — CPT/midtraining should gradually anneal from general to specialized data, not switch abruptly. Best checkpoint is judged by post-training performance, not immediate midtraining metrics.
  - Evidence: Cameron Wolfe deep dive (cameronrwolfe.substack.com/midtraining-notes). Key: align midtraining with downstream use cases, specialize gradually to avoid forgetting, retain general capabilities by mixing data, optimize for post-trainability not immediate benchmark. PRISM framework for empirical tuning via cheap proxy experiments.
  - Tags: cpt, midtraining, annealing, forgetting, post-trainability

- **YES** — Agent leaderboards rank specialization (agent×task interaction), not capability (agent main effect)
  - Evidence: DDR paper (arXiv:2608.11323): across TheAgentCompany, τ2-bench, AppWorld — agent main effect &lt;3% of total variance in every dataset/check type, while agent×task interaction accounts for 7-23%. Three estimators (Henderson Method-I, REML, Bayesian GLMM) agree to 3dp.
  - Tags: eval,reliability,generalizability-theory

- **YES** — Aggregate eval reliability collapses on the hardest task quartile
  - Evidence: DDR paper: Eρ² on τ2 action_checks falls from 0.752 (full set) to 0.000 (hardest quartile). Implication: our eval must stratify by difficulty — aggregate pass rates on hard tasks are noise.
  - Tags: eval,reliability,task-difficulty

- **YES** — Training-cell reliability negatively correlates with held-out reliability in agent evals
  - Evidence: DDR paper: r=-0.90 on τ2-bench. Designs that look most reliable on training data replicate worst on holdout. Overfitting the eval is a real and measured failure mode.
  - Tags: eval,overfitting,reliability

- **YES** — Trace-level failure mode profiles are idiosyncratic but cell-level profiles generalize
  - Evidence: DDR paper MAST taxonomy: trace-level MAE=0.261 (noise), cell-level MAE=0.056 with r=0.83. Implication: classify failures at the agent×task-class level, not per-trace.
  - Tags: eval,failure-taxonomy,aggregation

- **YES** — Externalizing task state and verifying it independently from execution produces large gains on long-horizon tasks
  - Evidence: LongHorizon-Harness (arXiv:2608.01964): MEA loop (Manager determines subtask, fresh-context Executor performs it, read-only Auditor verifies environment state). +28.9pp on WeaveBench, +7.5pp on Terminal-Bench, consistent across models. The mechanism: preventing incorrect self-assessments from propagating.
  - Tags: orchestration,long-horizon,verification

- **YES** — Fresh-context executors outperform accumulated-context agents on multi-step tasks
  - Evidence: LongHorizon-Harness: executor gets clean context per subtask (no conversation history leak). Prevents error propagation where a wrong self-assessment in step N poisons step N+1. Gains are model-independent (works for Qwen, Claude Opus across different harnesses).
  - Tags: orchestration,context-management,sub-agents

- **YES** — Memory should be a structured action space the agent navigates, not a passive retrieval interface
  - Evidence: NapMem (arXiv:2607.05794): multi-granularity memory pyramid (raw conversations → typed records → topic tracks → profile) exposed as tools. Agent trained with memory-tool RL to select granularity per query. Competitive on PersonaMem-v2, LongMemEval, LoCoMo while preserving general reasoning abilities.
  - Tags: memory,architecture,active-navigation

- **YES** — Provenance links between memory layers enable navigation that flat retrieval cannot
  - Evidence: NapMem: linked multi-granularity pyramid where raw conversations, typed records, topic tracks, and profiles are connected through provenance relations. Agent inspects different granularities based on query and intermediate evidence. Without links, a record found via search has no path to the source conversation or the broader topic.
  - Tags: memory,provenance,navigation

- **YES** — A meta-harness optimizer that recursively improves harness design from rollout feedback outperforms static harness configurations
  - Evidence: AutoDesign (arXiv:2608.13560): meta-harness optimizer guides a code agent to recursively improve harness based on rollout feedback. Across 7 code-agent-model configs, integrating the learned DesignHarness improves average score from 54.99 to 67.39 (+12.4%). Surpasses Claude Design (closed-source commercial) by 7.45 points on PosterBench Main Track.
  - Tags: harness,meta-optimization,self-improvement

- **YES** — Harness design is itself a long-horizon agentic process that benefits from accumulated reusable experience
  - Evidence: AutoDesign: conceptualizes multimodal-source → structured-output as a model-harness system. An ideal harness aligns with human design priors AND accumulates reusable experience through empirical exploration to drive recursive self-improvement. Static paradigms fall short. The paper instantiates this with 253 tool calls and 11 editing turns within 40 minutes for under $3.
  - Tags: harness,self-improvement,experience-accumulation
