<!-- GENERATED — DO NOT EDIT — source: specs/specs.db -->
# Design Decisions

## 1. Canonicalize and singly supervise retrieve-skills

**Context:** The canonical skill directory lacks server.py/router_core.py/indexer.py/tests while the live implementation remains under a stale Claude-specific copy. The client reports `Session not found`, and the PowerShell watcher couples child lifetime to a console via -NoNewWindow.

**Options:** 1) Keep Claude-specific runtime plus watcher; 2) copy runtime into canonical store but keep dual supervisors; 3) canonicalize runtime and use NSSM as the sole supervisor.

**Chosen:** Run the complete incumbent implementation from C:\Users\user\.skills\retrieve-skills under one persistent supervisor (current-user Scheduled Task; NSSM preferred but requires elevation) on port 8765; remove the PowerShell watcher from the supervision path; retain the stale Claude copy only until functional verification succeeds.

**Rationale:** A single canonical executable location eliminates configuration drift, while a single OS service eliminates competing restarts and console-lifetime failures. Fresh MCP initialization is required after restart because prior Streamable HTTP session IDs are server-process state.

---

## 2. Use evidence-bearing mission observables as convergence gates

**Context:** The README states the SDD mission, but the prior canonical spec encoded neither measurements nor enforcement. Existing controls such as incumbent search, lifecycle hooks, and convergence provide partial mechanisms but cannot prove mission outcomes.

**Options:** 1) Keep mission as explanatory prose; 2) infer success from task completion and passing commands; 3) define separate evidence-bearing observables and make them convergence gates.

**Chosen:** Treat sprawl, semantic drift, coordination drift, behavioral drift, and Karp as five independently observable failure signals. Persist their evidence in SpecsDB-linked records; convergence is fail-closed unless every MUST criterion has implementation evidence, all three drift counts are zero, orphan delta is non-positive, and every anomaly has a checked disposition.

**Rationale:** Separate observables prevent one healthy signal from masking another failure, as demonstrated by retrieve-skills health passing while Kiro's registered client failed. Persisted evidence prevents explanations and cross-session retellings from replacing checks.

---

## 3. Record Scheduled Task as current retrieve-skills supervisor

**Context:** Decision #1 selected NSSM, but installation required elevation unavailable during repair. The verified deployment instead uses one current-user Scheduled Task with restart policy and canonical working directory.

**Options:** 1) Continue claiming NSSM despite observed deployment; 2) run both supervisors; 3) record Scheduled Task as current state and defer an explicit one-for-one NSSM replacement.

**Chosen:** Use the current-user Scheduled Task `retrieve-skills` as the active single supervisor until an elevated maintenance action installs NSSM. Treat the prior NSSM choice as preferred target state, not observed current state. No second watcher or supervisor may run concurrently.

**Rationale:** The specification must describe observed operational state. A single Scheduled Task satisfies persistence and single-supervisor safety now; any later NSSM migration must replace it atomically to avoid duplicate process trees.

---

## 4. Use one traceability graph with generated projections

**Context:** The harness needs to prevent sprawl while keeping functions cohesive and every production symbol accountable. Manually maintained UML and prose docstrings can themselves become sprawl, while fixed complexity thresholds can reward fragmentation and be gamed.

**Options:** 1) Gate on fixed LOC and method-count limits; 2) maintain independent prose specs, UML, and docstrings; 3) store stable graph identities centrally and validate all projections against live code and evidence.

**Chosen:** Make SpecsDB the canonical traceability graph. Treat Mermaid UML, structured docstring provenance, code-health reports, call graphs, and test matrices as generated or validated projections. Use hard gates for reachability, traceability, duplicates, stale projections, and architecture violations; use LOC/method-count/complexity as differential warning signals calibrated from the repository baseline.

**Rationale:** A graph supplies garbage-collection semantics: declared roots define reachability, traceability edges establish ownership, pending tasks provide temporary roots, and supersession edges make retirement explicit. Differential complexity metrics identify pressure without misclassifying well-factored code or incentivizing tiny disconnected functions.

---

## 5. Apply the three-hop rule to routing indirection, not domain depth

**Context:** A router-style hop budget can expose needless indirection and cross-class ping-pong, but raw call depth conflates waste with legitimate controller/service/repository/gateway separation.

**Options:** 1) Hard-cap every call path at three functions; 2) ignore path topology and measure only per-function complexity; 3) distinguish routing/pass-through hops from domain-work hops and combine path metrics with architecture boundaries.

**Chosen:** Use a soft three-hop warning only for consecutive nodes that merely route, dispatch, adapt, or forward without domain transformation, validation, persistence, or an intentional architecture-boundary role. Measure complete root-to-outcome paths, but do not cap legitimate domain call depth. Treat cycles, boundary ping-pong, duplicated policy, unreachable branches, and architecture violations as hard failures. Require profiling for CPU or latency claims.

**Rationale:** The distinction preserves separation of concerns while detecting chains of wrappers and distributed if/else policy. It also prevents static maintainability metrics from being misrepresented as runtime performance evidence.

---

## 6. Collapse controls into a policy-and-gate kernel

**Context:** The audit produced many proposed controls—sprawl census, traceability, UML freshness, provenance, anomaly checks, drift convergence, and control-flow analysis. Implementing each as an independent process would reproduce the sprawl the harness exists to prevent.

**Options:** 1) Separate script and workflow for every control; 2) steering-only instructions with no mechanical enforcement; 3) one policy compiler, gate runner, validator registry, evidence ledger, and thin harness adapters.

**Chosen:** Compile canonical policy from SpecsDB into harness steering, route lifecycle events through thin per-harness hook adapters, evaluate registered read-only validators in one generic gate runner, persist structured evidence and verdicts in one ledger, and render diagrams/reports/configuration as downstream projections. Keep tasks as mutable execution state referenced by policy but never interpreted as policy themselves.

**Rationale:** The kernel centralizes lifecycle and evidence semantics while validators remain small and separable. It prevents duplicated hooks, inconsistent verdict formats, and process-specific state stores, yet preserves specialized analysis where computation is required.

---

## 7. Bound the policy-and-gate kernel scope

**Context:** A complete spec needs a boundary that prevents the proposed kernel from absorbing all development tooling or recreating process sprawl.

**Options:** 1) Leave boundaries implicit; 2) make the gate kernel own every tool and workflow; 3) constrain it to policy compilation, event-triggered validation, evidence persistence, and projections.

**Chosen:** IN scope: compiling SpecsDB policy into steering, lifecycle hook adapters, a generic structured-verdict gate runner, validator registration, durable evidence, traceability/reachability/control-flow analyzers, generated UML/provenance projections, and four-harness conformance. OUT of scope: treating tasks as policy, embedding analyzer logic inside hooks, creating one supervisor per validator, inferring runtime performance from static metrics, mandatory formal verification for ordinary code, or accepting hand-maintained diagrams as evidence.

**Rationale:** The boundary keeps hooks thin and validators composable while preserving external profilers, test runners, MCP services, and task execution as independent substrates consumed through evidence contracts.

---

## 8. Use one canonical continuation envelope as the interoperability boundary

**Context:** Each harness emits different session, role, tool, task, path, and response schemas. Direct pairwise integrations scale quadratically and cause metadata loss to be hidden inside provider-specific code.

**Options:** 1) Build pairwise harness-to-harness translators; 2) store only raw provider JSON and let each consumer interpret it; 3) define one canonical core plus namespaced extensions and versioned adapters.

**Chosen:** Use a versioned, content-addressed Provider-Neutral Continuation Envelope as the sole interoperability boundary. Namespace native identities and preserve the immutable raw provider payload by reference; adapters translate at the edge, while the policy kernel, SpecsDB, continuation store, and memory pipeline consume only canonical types.

**Rationale:** A hub-and-spoke canonical contract makes adding a harness O(1), keeps provider quirks out of policy, and preserves unknown metadata for future adapters without letting raw schema define canonical identity.

---

## 9. Separate exact continuation state from semantic memory

**Context:** Vector retrieval is probabilistic and optimized for relevance, while cross-harness resume requires exact latest state. Conflating them risks retrieving an older but semantically similar session and continuing from the wrong substrate.

**Options:** 1) Resume entirely from vector memory; 2) duplicate all state into memory-bank; 3) keep exact checkpoints deterministic and semantic memory as a provenance-linked supplemental layer.

**Chosen:** Maintain two linked but separate stores: an ID-addressed continuation store for exact resumable checkpoints and an append-only provider event store feeding memory-index for semantic recall and promotion candidates. Memory-index may enrich a resume packet but may never be the only source for current task state, artifact hashes, blockers, or next action.

**Rationale:** The split preserves reliable continuation while allowing cross-session learning. Both stores drill down to immutable provider event IDs, so promoted knowledge remains auditable without making semantic ranking a correctness dependency.

---

## 10. Gate cross-harness handoff on capability and loss reports

**Context:** Harnesses differ not only in field names but in actual capabilities and lifecycle semantics. A syntactically valid transform can still be behaviorally unsafe.

**Options:** 1) Best-effort coercion and continue; 2) require identical capabilities across all harnesses; 3) negotiate capabilities, preserve extensions, and gate only load-bearing loss.

**Chosen:** Require adapters to advertise measured capabilities and generate a LossReport before import. Required semantic loss, stale hashes, unresolved anomalies, or missing execution capabilities block resume. Optional loss is preserved as explicit missing_reason or provider_extensions and must appear in the target repeat-back. No adapter may fabricate hooks, tools, roles, or session semantics that the target harness does not support.

**Rationale:** Capability-aware loss reporting permits honest degradation without false equivalence. It turns schema mismatch into explicit evidence and lets the policy layer decide whether a handoff remains safe.

---

## 11. Use Codex CLI as the universal-adapter proof

**Context:** The universal adapter claim needs a new independent harness proof beyond the existing Claude Code, OpenCode, pi, and Kiro surfaces. Codex CLI is named by the user and is not represented in the current matrix.

**Options:** 1) Claim future extensibility without another adapter; 2) add provider-specific fields to the kernel; 3) onboard Codex strictly through the generic adapter contract and conformance suite.

**Chosen:** Implement OpenAI Codex CLI as the next adapter and require a bidirectional handoff with one incumbent harness. Keep Codex-specific session commands, event parsing, and capability gaps inside its adapter package; the canonical schema and gate kernel may not gain Codex-only fields or branches.

**Rationale:** A successful new adapter without kernel modification falsifies the strongest duplication risk and proves that provider differences are metadata/configuration rather than new architecture.

---

## 12. Promote observations inline on retrieval threshold within memory-index

**Context:** The retrieval-count threshold and decay model are already specified in agentic_kg_memory and partially tracked by log_memory, but the actual markdown write-back, lane classification, and conversation intake are not automated. Adding a sixth service would violate the architecture constraint.

**Options:** 1) Keep promotion manual (agent calls add_memory); 2) add a separate scheduler/cron for batch promotion; 3) promote inline within memory-index on retrieval threshold crossing.

**Chosen:** Extend the existing memory-index service (port 8055) with: an append_event tool for the per-project ordered conversation store; retrieval-count tracking on every search_memory hit; Ebbinghaus decay weighting at query time; and an automatic promotion pass that fires after each search when an observation crosses the 3-retrieval threshold. The promotion pass classifies the candidate, writes the appropriate durable artifact, backlinks to source events, and re-indexes. No new MCP service is created; no scheduled cron or external trigger is required for individual promotions. Bulk decay/anneal remains a periodic maintenance task.

**Rationale:** Inline promotion eliminates the gap between earning durability and receiving it; the observation is proven useful at the moment of its third retrieval, so writing it then is both timely and evidence-backed. Bulk decay stays periodic because it is not latency-sensitive and benefits from batch efficiency.

---

## 13. Use setup.py as the single idempotent convergence command

**Context:** The harness currently requires manual steps to start services, toggle MCP configs, run migrations, and verify health. Each manual step is a session-start failure point and a source of decoherence when the state isn't what the agent assumes.

**Options:** 1) Keep manual per-service scripts; 2) write a separate migration tool per change; 3) make setup.py the single convergence command that handles all state transitions idempotently.

**Chosen:** Extend the existing setup.py with a check-skip-act pattern per resource: for each service, config, schema, and projection, probe current state first (health endpoint, file hash, DB schema version), skip if already correct, apply the delta if not, and report the result. Service migrations (like todo stdio→HTTP) are setup steps that the same command handles — not separate manual procedures.

**Rationale:** One command eliminates the gap between 'configured' and 'operational'. Idempotency means it can be re-run after any failure, restart, or config change without risk. Reporting makes it self-documenting for the next session.

---

## 14. Adopt phased execution as the canonical QA enforcement pattern

**Context:** The session demonstrated repeated decoherence from serializing independent work, skipping upstream verification, branching into new specs without closing implementation, and not declaring what passes between phases. Each failure mode was corrected by the same structural pattern: group by dependency, parallelize within groups, gate transitions on disk-persisted verification, and cap complexity per unit.

**Options:** 1) Ad hoc task ordering per session; 2) strict sequential execution regardless of independence; 3) phased DAG execution with parallel batching, artifact manifests, and a script-size cap.

**Chosen:** Phased execution with dependency gating, parallel batching, artifact manifests, and a hard 4-phase cap per script is the canonical QA enforcement mechanism for this harness. It applies to agent task plans, CI pipelines, setup scripts, and validator orchestration equally. The steering files (parallel-phases.md, dependency-gate.md) encode the behavioral contract; the gate runner and evidence ledger enforce it mechanically; scripts that exceed 4 phases are decomposed into chained executables piped together.

**Rationale:** The pattern is both the anti-decoherence mechanism (upstream must pass before downstream starts) and the anti-sprawl mechanism (every phase declares what it produced, and unconsumed outputs are flagged). The 4-phase cap prevents any single script from becoming untestable or unreviewable while still allowing composition through chaining.

---

## 15. Package-relative imports for specs module

**Context:** Prior to Phase 4, specs/ had no __init__.py and all modules used bare imports (from policy_contracts import). This worked only because pytest was invoked from within the specs/ directory. Adding __init__.py broke bare imports; the migration to relative imports is mechanical and necessary.

**Chosen:** Add specs/__init__.py and migrate all internal imports to relative (from .module) or absolute (from specs.module) style

**Rationale:** Adding __init__.py enables proper package discovery by pytest and avoids sys.path hacks. All production modules use relative imports (from .policy_contracts); all test files use absolute imports (from specs.policy_contracts). This is the standard Python package convention.

---

## 16. Adopt Parallel-RL architecture for multi-domain MGPO

**Context:** Our mixed-domain RL showed R3 improving while R1 degraded — task interference within a single training run. The Parallel-RL paper proves per-task RL updates are orthogonal and can be merged with 94-103% retention. This eliminates the overshoot problem (each domain trains to its own optimum without affecting others) and enables modular add/remove of domain capabilities.

**Options:** 1. Continue mixed-domain MGPO with patience (current approach, showed +0.250 at peak but overshoots). 2. Parallel-RL: per-domain adapters merged (paper-proven, modular, no interference). 3. Sequential multi-stage RL (paper shows this also works at +10.2 but less modular).

**Chosen:** Parallel-RL: train one RL adapter per domain (Math, Code, STEM, Instruction), then merge via TIES or adapted summation. Replace sequential mixed-domain MGPO.

**Rationale:** Option 2 eliminates the interference that caused R1 to degrade while R3 improved. It allows independent HPO per domain (different optimal lr/steps). It enables plug-and-play: add domain QA RL later without retraining. Temperature can be tuned per-domain to the exploration-interference sweet spot. Implementation: 4 parallel RL runs (one per VibeThinker domain), then TIES merge + 5% adapted pass.

---

## 17. Single-GPU sequential Parallel-RL + Box-Cox stratified CPT corpus

**Context:** Only one 16GB RTX 5000 Max-Q available. Cannot run parallel GPU jobs. Parallel-RL means independent training runs that don't interfere at the weight level — they still execute sequentially on this hardware. For CPT corpus: user has multiple books/skills and wants coverage of all without picking favorites. Box-Cox over chunk counts per source gives proportional-but-boosted representation to smaller sources.

**Chosen:** Parallel-RL runs sequentially on the single 16GB card (not parallel machines). Each domain adapter trains one at a time, then all merge. CPT uses Box-Cox stratified sampling over text corpus chunk counts to include all books/skills without arbitrary selection.

**Rationale:** Sequential execution of per-domain RL is still valid Parallel-RL — the orthogonality guarantee comes from the GRPO mechanism, not from literal hardware parallelism. The merge happens after all domains complete. For CPT: stratified sampling over corpus chunk counts is the same cross-hatch principle applied to pretraining data — ensures every source text contributes without being dominated by the longest book.

---

## 18. AutoDesign: Harness as learnable artifact, not static config

**Context:** AutoDesign demonstrates that a meta-optimizer guiding recursive harness improvement from rollout feedback produces +12.4% gains across all model configs. Our current harness (steering rules, hooks, skills) is hand-authored and static between sessions. The failure registry + event log we just built provide the rollout feedback loop needed for self-improvement.

**Options:** Option A: Keep harness config static, hand-tuned by user. Option B: Add a periodic review pass that proposes harness changes from accumulated event logs + failure patterns (AutoDesign-lite). Option C: Full meta-optimizer loop where an agent rewrites its own steering/hooks based on measured outcomes.

**Chosen:** Treat harness configuration (steering rules, hooks, skill routing) as a learnable artifact that improves from execution feedback, not a static hand-authored spec

**Rationale:** Option B is the right next step. We already have the ingredients: (1) event-log JSONL captures what tools get used and how, (2) failure registry captures dead ends, (3) specs canon captures settled findings. A periodic review (session-end or weekly) that reads these artifacts and proposes steering/hook/skill updates would close the self-improvement loop without the risk of Option C (unsupervised self-modification). Option C is the endgame but requires the MEA auditor pattern to prevent drift.

---

## 19. Scene-drafting: sequential generation, not ReAct agent

**Context:** The adventure module defines a clear room traversal path (stated in the Approach line). Scenes are generated in that order. No backtracking, no branching, no tool calls needed. A ReAct loop adds complexity without value here — the bible already decided what happens in each room.

**Options:** Option A: ReAct agent with tools (read bible, check consistency, revise). Option B: Simple sequential loop — parse, generate per room, accumulate. Option C: Two-pass (draft then revise).

**Chosen:** Single-pass sequential scene generation with sliding window — no agent loop, no tool use, no ReAct. Just: parse bible → for each room in traversal order → compose prompt → generate → append.

**Rationale:** Option B. The bible is the spec — it already contains everything needed. Adding a ReAct loop means paying for tool-call overhead on every scene when the information is already fully specified. If consistency issues appear, we add a post-hoc verification pass (Option C) rather than over-engineering the generation loop. KISS. Start simple, add complexity only if the output drifts.

---

## 20. Two-model adversarial convergence for scene prose quality

**Context:** Single-model generation produces tics the model can't see (synesthetic metaphors, decorated abstractions). A separate judge model fails because available models either think out loud (nemotron) or can't do analytical tasks (muse-glimmer). The insight: the judge should BE a second writer — critique is implicit in the rewrite, not in a PASS/FAIL verdict.

**Options:** Option A: Better prompt engineering (add more constraints). Option B: Single model + separate judge model for PASS/FAIL. Option C: Two writers trading drafts until convergence (Constitutional AI for prose). Option D: Human-in-the-loop per scene.

**Chosen:** Replace single-model generation + broken judge gate with a two-model adversarial convergence loop: Writer A (muse-glimmer) drafts, Writer B (minimax-m3) critiques and rewrites weak lines, convergence when neither model objects to the other's output. Max 3 rounds.

**Rationale:** Option A failed (v1→v2→v3, still producing 'shudder of rust'). Option B failed (nemotron can't judge, muse-glimmer can't judge). Option D doesn't scale. Option C uses different model biases as mutual quality gates — each model catches the other's blind spots. Bounded at 3 rounds to prevent infinite lateral trading. The convergence criterion is natural: when the rewrite introduces no changes the original model would reject.

---
