<!-- GENERATED — DO NOT EDIT — source: specs/specs.db -->
# Settings

| Key | Value | Citation |
|-----|-------|----------|
| `code_health_initial_warning_policy` | `Warnings: function logical LOC >40; cyclomatic complexity >10; conditional nesting >4; public methods/class >10; class LOC >300; module LOC >500; duplicate code >3%; >3 consecutive routing-only or pass-through hops; repeated A→B→A boundary crossing. Hard failures: unreachable or untraceable production symbols, stale pending links, duplicate active implementations, unexplained cycles, unreachable branches, and architecture-boundary violations. Runtime efficiency requires profiling/benchmark evidence.` | Initial warning-only policy from decisions #4-#5 and simplify/design-patterns skills; repository-local calibration and false-positive testing in tasks #22 and #24 are required before promotion to blocking thresholds. |
| `parallel_rl_adaptation_frac` | `0.05 (5% of mixed data for post-merge adaptation; bumps 94.2% -> 103.2% retention)` | Zhu et al. arXiv 2608.03573 Table 3; adapted parallel RL uses 5% of mixed training data for short adaptation pass after merge |
| `rl_temperature` | `0.65 (per-domain, exploration-interference sweet spot from Parallel-RL paper; current 1.0 is above optimum)` | Zhu et al. arXiv 2608.03573 Fig 5; exploration-interference tradeoff. Sweet spot tau=0.65 for Math reasoning. |
