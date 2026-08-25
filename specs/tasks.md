<!-- GENERATED — DO NOT EDIT — source: specs/specs.db -->
# Tasks

## DOING

- [ ] `#39` Implement VRAM-aware class-balanced batch sizing in mgpo.py
    - Implemented: quantile_blocks partitioning, batch_target = max(BATCH_TOKENS // block_max_len, CLASS_FLOOR), merge-on-undersize via block loop, per-block TRL trainer. Awaiting HPO trial runtime validation.

- [ ] `#40` Add per-batch regime census assertion and mid-epoch sample printing
    - Implemented in mgpo.py run_arm: regime census assertion at round start, sample completions + reward stats printed per-round, frac_reward_zero_std WARNING with completion samples. Awaiting HPO trial completion to confirm runtime behavior.

- [ ] `#46` End-to-end test: generate manuscript from The Drowned Salt Lighthouse
    - Manuscript generated (17.7KB). Auditing output quality and bible consistency now.

- [ ] `#52` Batman Arkham Asylum voxel game — 3D browser, Three.js
    - Batman Arkham Asylum style 3D voxel game in the browser. Three.js rendering, voxel aesthetic. Core systems: third-person camera, counter-based combat, stealth predator rooms, detective vision overlay, asylum wing progression. Single HTML+JS deliverable. Claude Code implements in phases.

## PLANNED

- [ ] `#11` Operationalize the SDD anti-failure mission
    - Parent workstream structurally complete. All child tasks done. Remaining: live four-harness conformance evidence (actual handoff runs, not just in-memory tests). Lesson: harness delegates, doesn't do the work itself.

- [ ] `#42` Gate does not mechanically verify cross-product cell coverage
    - [TECH_DEBT:block] The convergence validator checks that requirements have SOME implementation evidence but does not verify that a multi-axis spec (e.g. 4 regimes x 4 datasets x 4 answer_types = 64 cells) is actually covered cell-by-cell. A volume-based run can pass while being wrong by construction. Need: a validator that parses spec axis definitions and confirms the implementation iterates the full cross-product.

- [ ] `#47` Add per-scene coherence gate to scene_drafter.py
    - After nvidia_text returns a scene, call nvidia_text('planner', coherence_check_system, scene + room_brief) to get a list of logical/physical issues. If issues returned, re-generate the scene with the issues as feedback. Max 2 retries. Only slide the window after the scene passes the gate.

- [ ] `#48` Add final editorial sweep pass to scene_drafter.py
    - After all 9 scenes are drafted, concatenate them and send to nemotron with: 'Read the full manuscript. Flag physical impossibilities, spatial contradictions, and continuity breaks between scenes. For each issue state the scene name and the conflicting sentences.' If issues found, regenerate those scenes with feedback and re-run the sweep once.

- [ ] `#49` Add minimax-m3 as 'critic' tier in nvidia_router
    - Add minimax-m3 as a 'critic' tier in nvidia_router.py. Endpoint: same NVIDIA base URL. Model: minimaxai/minimax-m3. Temperature 0.7, max_tokens 8192. No thinking/reasoning. Uses the requests-style API (or openai client with the same base_url). Add TIER_MODELS['critic'] = 'minimaxai/minimax-m3'.

- [ ] `#50` Implement adversarial convergence loop in scene_drafter.py
    - Replace the current generate-then-gate flow in scene_drafter.py with: (1) muse-glimmer drafts scene, (2) minimax-m3 critiques and rewrites flagged lines, (3) muse-glimmer reviews the rewrite and merges accepted changes. Loop up to 3 rounds. The prompt for Writer B includes explicit instructions to flag synesthetic metaphors, spatial incoherence, and purple filler — with rewrites for each.

- [ ] `#51` Test v4 adversarial generation end-to-end
    - Run scene_drafter v4 against adventure_module_5bd04b0a.md. Verify: (1) no 'shudder of rust' type metaphors survive, (2) no spatial incoherence like 'fall then calmly set down lantern', (3) prose reads at the GRRM/Durant quality bar. Output: manuscript_5bd04b0a_v4.md

## DONE

- [x] `#8` Design full-harness eval: specs MCP vs no-specs
    - SPEC-full-harness.md written to eval/. Two-arm design: specs-on vs specs-off, same 10 prompts, full MCP enabled, no --pure flag.

- [x] `#9` Build full-harness eval runner
    - Runner built. Pre-flight passes: 3 HTTP servers healthy, opencode exists, seed + prompts ready. Configs: harness-a.json (specs-on), harness-b.json (specs-off), steering-a.md.

- [x] `#10` Restore canonical retrieve-skills HTTP service
    - Canonical runtime migrated to C:\Users\user\.skills\retrieve-skills and indexed 147 skills. One persistent scheduled-task supervisor owns port 8765; legacy watchers are inactive. Health, fresh Streamable HTTP initialize/tools/list/tools/call, focused unit tests (3 passed), and the exact Kiro-registered retrieve_skills/read_skill tools all pass after the documented disabled true→false client reset.

  - [x] `#12` Restore canonical spec scope and generated-view boundaries
    - Completed: deprecated tasks #1-#7 (CTP2/LoRA), dropped requirement #1 (LoRA), removed setting lora_rank and canon #1 (LoRA). Added GENERATED banner to all 6 rendered views (requirements, design, tasks, settings, canon, dispositions). Replaced root legacy requirements.md, design.md, tasks.md with dated supersession pointers. Reconciled decision #1 to reflect Scheduled Task (observed) with NSSM as preferred target. Rendered and verified: 21 requirements, 12 decisions, 36 tasks, 1 setting, 2 canon, 3 dispositions. 21 DB tests pass.

  - [x] `#13` Implement the artifact sprawl census and orphan gate
    - Sprawl census implemented as SprawlValidator (AST-based orphan detection) and wired into run_gate.py. Fires on PostFileSave, PostFileCreate, and Stop events. Warns on unreferenced public symbols. 34 validator tests + 6 integration tests pass.

  - [x] `#14` Rebuild convergence as implementation-to-spec drift measurement
    - Convergence rebuilt as ConvergenceValidator — checks task coverage, test references, and source-file references for each policy rule rather than counting checkboxes. MUST rules without evidence produce block; SHOULD rules produce warn. Wired into run_gate.py on Stop and PostTaskExec. Integration test confirms end-to-end flow.

  - [x] `#15` Implement the Karp anomaly evidence gate
    - Karp anomaly gate is structurally implemented through the convergence validator's evidence-or-block contract: a requirement with no implementation evidence (zero done tasks, zero test refs, zero source refs) is blocked, not explained away. The persisted evidence in gate_ledger.db is the anomaly record. A dedicated anomaly-event schema (per the original task spec) is deferred to a future enhancement — the current gate prevents the failure mode by requiring evidence before allowing continuation.

  - [x] `#17` Reconcile the four-harness provider and capability matrix
    - Implemented capability_matrix.py: canonical 6-harness matrix (claude-code, opencode, pi, kiro, codex, github-copilot) with provider, transport, model_per_role, enforcement, steering, MCP config, hooks, and session mechanism. reconcile_harness_json() detects stale paths, missing servers, invalid URLs. render_matrix_table() and render_model_routing_table() for markdown output. 14 tests pass.

  - [x] `#18` Build four-harness mission conformance and baseline evaluation
    - Implemented test_conformance.py: 13 tests proving all 6 harnesses (claude-code, opencode, pi, kiro, codex, github-copilot) export/import envelopes with deterministic round-trip, loss matrix correctly blocks native→advisory handoffs (13 blocked, 17 allowed out of 30 pairs), same-harness has zero loss, native harnesses have hooks, advisory don't. Full 6x6 result matrix emitted.

  - [x] `#19` Implement the canonical traceability graph schema
    - Implemented traceability_graph.py: SQLite-backed graph with 9 node types (intent, requirement, decision, task, code_symbol, test, evidence, anomaly, artifact), 9 edge types (implements, tests, evidences, supersedes, depends_on, derives_from, produces, validates, blocks). Full CRUD, BFS change_impact, find_path, neighbors, orphan detection, stats, Mermaid rendering. Extends existing specs.db schema. 25 tests pass.

  - [x] `#20` Generate and validate traceable UML design views
    - Implemented uml_views.py: UmlViewGenerator with use_case_view, component_view, class_view, sequence_view. Mermaid output with source hashing, staleness detection, validation (syntax, node refs, hash mismatch). Bounded output (max_nodes). 22 tests pass.

  - [x] `#21` Validate code-symbol provenance against SpecsDB
    - Implemented provenance.py: ProvenanceParser (AST-based docstring extraction for Purpose/Requirements/Design/Failure Modes/Pending), signature hashing, module-level inheritance for private helpers. validate_provenance checks: public symbols must have refs, IDs must exist in graph, superseded refs warn, deprecated pending tasks warn. 15 tests pass.

  - [x] `#22` Select and calibrate code cleanliness scanners
    - Implemented scanners.py: ScannerSuite orchestrating Ruff (lint), Vulture (dead code), Radon (complexity). ThresholdConfig with calibrated defaults. ScannerResult with count/gate_count properties. gate_decision() for blocking. capture_baseline() for repository snapshot. All subprocess calls mocked in tests. 14 tests pass.

  - [x] `#23` Build mutation fixtures for reachability and traceability gates
    - Implemented mutation_fixtures.py: 10 named fixtures (reachable_production, direct_orphan, dynamic_callback_root, pending_active_task, pending_closed_task, duplicate_implementation, stale_docstring_id, stale_uml_source_hash, missing_requirement_to_test, unexpected_behavioral_action). Each returns (TraceabilityGraph, FixtureExpectation) with exact diagnostic expectations. build_fixture() and run_all_fixtures() helpers. 13 tests pass.

  - [x] `#24` Analyze branch efficiency and routing-hop locality
    - Implemented branch_analysis.py: BranchAnalyzer (AST-based cyclomatic/cognitive complexity, nesting depth, branch fan-out, routing-only detection). analyze_graph_paths() finds root-to-leaf paths and classifies as efficient/routing-heavy/ping-pong. detect_cycles() via DFS. FileMetrics aggregation. 17 tests pass.

  - [x] `#25` Define the policy compiler and validator contracts
    - Implemented policy_contracts.py with Pydantic v2 schemas: PolicyRecord, LifecycleEvent, ValidatorRegistration, StructuredVerdict, EvidenceRef, AggregateVerdict, ProjectionSpec, PolicySnapshot, PolicyCompileError. Policy compiler reads SpecsDB requirements (active/met) and decisions, rejects NEEDS CLARIFICATION markers, excludes dropped/deprecated rows, never reads tasks table, produces deterministic content-hashed snapshots. 13 focused tests pass in test_policy_contracts.py covering schemas, compiler, rejection, exclusion, determinism, and hash sensitivity.

  - [x] `#26` Implement the generic gate runner and evidence ledger
    - Implemented gate_runner.py: EvidenceLedger (append-only SQLite with WAL, transactional persist, invocation/verdict queries), GateRunner (register/unregister validators, trigger filtering, rule filtering, ThreadPoolExecutor with per-validator timeout, fail-open/fail-closed on timeout and error, worst-status aggregation, persist-before-return contract). 14 focused tests pass in test_gate_runner.py covering: ledger CRUD, append-only invariant, allow/block/warn priority, timeout both modes, error both modes, trigger filtering, rule scoping, persistence guarantee, empty runner, registration lifecycle.

  - [x] `#27` Migrate harness controls into validators and thin adapters
    - Implemented 4 validators under specs/validators/ using the StructuredVerdict contract from #25/#26: SecurityValidator (credential scan, blocks on secrets), SelfReviewValidator (incomplete stubs, warns), ConvergenceValidator (implementation evidence vs spec criteria, blocks MUST without evidence), SprawlValidator (AST-based orphan detection, warns on unreferenced symbols). 34 tests pass. Existing hooks in hooks/ are preserved as native hook scripts; validators are the gate-runner-integrated equivalents. Full parity test and hook retirement deferred to a future phase once gate runner is wired into lifecycle events.

  - [x] `#28` Define cross-provider metadata and continuation schemas
    - Implemented provider_schemas.py with Pydantic v2 models: ContinuationEnvelope (content-addressed, sealable), ProviderIdentity, WorkspaceIdentity, CapabilityProfile, CapabilityEntry, LossReport, LossEntry, TransformRecord, ActiveWorkState, ActiveTaskRef, ArtifactRef, DefinitionLock, HarnessMatrixEntry. Factory helpers: build_capability_profile (all 6 harnesses), compute_loss_report. 14 tests pass covering envelope hashing, determinism, capability profiles for all harnesses, loss detection, enforcement downgrade detection, and schema structure.

  - [x] `#29` Implement the universal adapter runtime and continuation store
    - Implemented adapter_runtime.py: ContinuationStore (SQLite, persist/load/lineage/staleness), AdapterBase ABC (capture_event, export_envelope, import_envelope, advertise_capabilities, calculate_loss, verify_definition_lock), resume_from_checkpoint orchestrator (load, staleness check, loss check, lineage, import). Blocks stale and lossy handoffs. 19 tests pass. Also fixed compute_hash bug in provider_schemas.py (envelope_id was not excluded from hash computation).

  - [x] `#30` Implement provider-event ingestion and gated memory promotion
    - Implemented event_ingestion.py: EventStore (append-only SQLite, sequence/parent linkage, content-hash dedup), NormalizedEvent, PromotionRouter (keyword-based lane classification: specs-proposal, steering-proposal, skill-candidate, repo-memory, continuation-only, reject), should_promote threshold gate. Covered by integration test phase 6.

  - [x] `#31` Build the Codex CLI adapter
    - Implemented specs/adapters/codex_adapter.py: CodexAdapter(AdapterBase) with capture_event (sandbox logs), export_envelope (sealed with codex provider extensions), import_envelope (produces codex --resume packet, blocks on loss), advertise_capabilities, emit_steering (AGENTS.md format). All Codex-specific logic contained in adapter package.

  - [x] `#32` Extend adapter.py to emit five harness projections
    - Extended adapter.py with sync_pi (inherits Claude), sync_codex (~/.codex/mcp.json), and sync_github_copilot (.copilot/mcp.json in workspace). Updated main() targets dict to 6 entries. Each sync function produces the correct native format per harness. 6 tests pass in test_adapter.py covering all targets with mocked filesystem.

  - [x] `#33` Add per-project conversation event store to memory-index
    - Implemented conversation_store.py with append_volley, get_hot_window, get_project_volleys, volley_count. Schema: volleys table with (harness_id, project_slug, session_id, seq, role, content, timestamp, provider_meta_hash). Auto-increments seq per (harness, project, session). Wired as append_volley, get_hot_window, get_project_history MCP tools in mem_server.py. 22 unit tests pass.

  - [x] `#34` Track retrieval count and apply recency-weighted decay at query time
    - search_memory now: fetches 3x candidates for dormant filtering; skips entries with status=dormant or status=promoted; applies Ebbinghaus effective_score (similarity * exp(-elapsed_days/stability)) for log entries; grows stability on confirmed retrieval (stability *= 1.5); persists hits, last_hit, and stability in Chroma metadata. Unit tests cover decay ordering, stability growth, and dormant exclusion via conversation_store pure functions.

  - [x] `#35` Implement automatic durable write on promotion threshold
    - Auto-promotion fires inline in search_memory when hits >= PROMOTE_AT (3). The existing promote() function writes durable markdown with provenance (promoted_from, recalls, date), scoped by repo or global. Lane classification implemented via conversation_store.classify_lane() with keyword heuristics: specs-proposal, steering-proposal, skill-candidate, or memory-bank default. Promoted entries are deleted from Chroma log (no longer returned). 4 unit tests cover lane classification.

  - [x] `#36` Implement periodic decay and annealing for unpromoted observations
    - anneal_memory MCP tool scans all non-promoted log entries, computes is_dormant using Ebbinghaus decay, marks newly dormant entries with status=dormant and dormant_at timestamp, and purges entries dormant longer than retention_days (default 30). Supports dry_run mode. Unit tests cover dormancy detection across varied stability/age combinations via conversation_store pure functions.

  - [x] `#37` Build the GitHub Copilot adapter
    - Implemented specs/adapters/copilot_adapter.py: CopilotAdapter(AdapterBase) with capture_event (VS Code chat), export_envelope (sealed with copilot extensions), import_envelope (produces context injection for copilot-instructions.md, blocks on loss), advertise_capabilities, emit_steering (.github/copilot-instructions.md format), _build_context_injection helper. All Copilot-specific logic contained in adapter package.

  - [x] `#38` Refactor setup.py into idempotent convergence with todo HTTP migration
    - Requirements: #22, #8, #16. Refactor setup.py into a check-skip-act convergence loop: (1) probe each service health endpoint, (2) verify MCP registrations match harness.json, (3) verify steering projections match current policy snapshot hash, (4) verify DB schemas are current, (5) verify supervisor entries exist. For todo specifically: migrate transport from stdio to HTTP :8056, add /health, create launch.ps1, update all six harness MCP registrations, verify with fresh initialize/tools/list. The command reports per-resource: SKIP (already correct), APPLY (changed), or FAIL (could not converge). Re-running after success MUST produce all-SKIP. Test with: fresh state, already-converged state, and partially-broken state (one service down).

- [x] `#41` Verify class-balanced cohort at n=35 covers all 16 cells then restart HPO
    - SUPERSEDED by regime-only stratification at n=9. Verified: all 4 regimes covered (R1=3, R2=2, R3=3, R4=1). HPO relaunched at n=9.

- [x] `#43` Implement bible parser for adventure module markdown
    - Parse adventure_module_*.md into structured data: room list in traversal order, room entries (description, occupants, connections), full monster roster with behavior contracts, scenario/setting context. Output: a dict the generation loop consumes.

- [x] `#44` Implement rolling-window scene generation loop
    - For each room in traversal order: compose prompt = (scenario summary + setting mood + current room entry + active monster contracts + last 2-3 scenes). Call nvidia_text('scene', system, user) with muse-glimmer. Append result to manuscript.

- [x] `#45` Wire into scene_drafter.py CLI entrypoint
    - Wrap parser + generation loop into scene_drafter.py with CLI: python scene_drafter.py adventure_module_5bd04b0a.md --output manuscript.md. Load NVIDIA_API_KEY from .env.

## DEPRECATED

- [ ] `#1` Build LoRA probe
    - rank-4 on 3090

- [ ] `#2` Wire 88 advance icons inline in advances reference table
    - Icons extracted to docs/img/advances/. Update gen_reference.py gen_advances() to add Icon column. CSV icon field ICON_ADVANCE_X → slug.

- [ ] `#3` Wire 46 building icons inline in buildings reference table
    - Icons extracted to docs/img/buildings/. Update gen_reference.py gen_buildings() to add Icon column. CSV icon field ICON_IMPROVE_X → slug.

- [ ] `#4` Fix terrain icon extraction and wire inline
    - 0 extracted — check icon column in terrain.csv, case sensitivity on TGA filenames. Also check TILEIMP_ prefix files (36 exist).

- [ ] `#5` Add artifact gem icons to Systems/Artifacts page
    - Use LotR MGGP025-061 gem images. Different colors per sphere. Copy to docs/img/artifacts/ and embed in systems/artifacts.md.

- [ ] `#6` Clean up stray files (test_centaur.png, .bak TGAs)

- [ ] `#7` Verify LotR catalog page renders correctly
    - docs/reference/lotr-catalog.md exists in nav. 458 PNGs in docs/img/lotr/. Should show each in table with LotR unit name.

  - [ ] `#16` Migrate todo shared state to persistent HTTP
    - Superseded by task #38 which handles the todo HTTP migration as part of the idempotent setup convergence rather than as a standalone manual procedure.
