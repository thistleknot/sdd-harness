# Current interpretations

## CURRENT 2026-11-18 — Canonical instruction source and publication views

- Decision: Treat `~/.rules/*.md` as the only authored source of instruction rules; treat SQLite as revisioned publication views, target mappings, and delivery receipts. Require an explicit `harnesses` audience and stable `order` on each published fragment, preserve client-only content, preview without writes, refuse drifted destinations, back up changed targets, verify exact readback, and report unsupported clients without claiming parity. Preserve the seven-harness coverage requirement; T1 verified four routes and left three planned routes `NOT_WIRED`.
- Basis: The existing harness requirements say rules are authored once at `~/.rules` and projection covers seven installed harnesses; `migrate_rules.py` calls the source canonical. T1 found 55 source fragments without an importer or explicit publication audiences. `source` and `source_file` fields record provenance only. The existing design already uses `harnesses` and `order`, so no second mapping file is introduced. Project requirements #5–#10 in `.specs/reqs/requirements.db` record the publication contract. Global Specs decision IDs #63–#64 were attempted during this work but a follow-up query did not find them; the committed interpretation and registered contract are the durable decision records.
- View-consumer rule: `shared` is consumed by OpenCode and VS Code, so a fragment scoped only to OpenCode cannot use that view. Reject the audience/view mismatch until a dedicated OpenCode view exists; this prevents shared-view leakage.
- Supersedes the 2026-11-18 integration-backport interpretation below, which proposed extending registry publication before resolving the canonical source conflict. Its original wording is preserved in [interpretations-history-2026-11-18.md](interpretations-history-2026-11-18.md).

## 2026-12-31 — Dynamic rule context for OpenCode

- Decision: Apply plan-do through the local plan-todo alias and compare programmatic selection with summarization as an experiment. Basis: the latest request reopens both as candidates and the capability-cone draft prohibits scoring on its runtime route. Feature 14 already owns implementation.

## Superseded interpretation pointer — integration backport planning (2026-11-18)

- Original decision and basis moved to [interpretations-history-2026-11-18.md](interpretations-history-2026-11-18.md); T1 established that `~/.rules` has no importer and the SQLite editing-authority wording conflicts with the existing canonical-source requirement.

## 2026-11-18: Tower defense rerun handoff

- Decision: Use the planning portion of plan-do for Todo #4 and stop at the checklist. Base the six-arm rerun on the original first game prompt, with a common Ninja Multi-Config build under x64 MSVC and independent verification. Basis: plan-todo is absent as a standalone skill, the operator requested a Luna handoff, and the available CMake lacks the VS 2026 generator.

## 2026-11-18: SATNA transcript capture and deployment

- Decision: Index PreCompact transcripts only when the host supplies transcript path, workspace, and session identity; skip the hook in VS Code because it does not write the Claude JSONL source. Keep the deployed analyzer source change separate from live service completion until the NSSM service can be restarted.
- Basis: Isolated tests proved scoped capture and retrieval, while the connected Specs MCP still returned the pre-change prefix-collision result; existing service records require Administrator access to restart.

## 2026-11-17: SATNA feature review

- Decision: Use the planning portion of plan-do and the workspace Todo queue for the feature review. Basis: the named plan-todo skill was absent from the retriever and local skill roots, and the requested deliverable was a review queue.

## 2026-11-17: SATNA reference integration

- Decision: Extract reusable features from the eight local checkouts and apply Harbor's separate-verifier pattern to the existing paired eval spec. Basis: the saved arms report process status only, the declared requirement coverage depends on an arm-specific Specs DB, and the existing RSI process already governs promotion.

## 2026-11-14: side-by-side project MCP deployment

- Decision: Serve the updated workspace-scoped Specs MCP on port 8058 and register it in OpenCode as `specs-project`; retain the existing 8057 service as backup.
- Basis: Restarting the NSSM-managed service returned Windows `OpenService(): Access is denied`, while the user identified MCP as backup and asked to focus on completing the task. A separate user-mode endpoint passed health, discovery, project write/query, artifact containment, and OpenCode/Gemma invocation checks without altering the 8057 endpoint.


## 2026-11-14: project specification ownership and order

- Decision: Store each project's requirement registry at `.specs/reqs/requirements.db` and write detailed design artifacts under dedicated `.specs` subfolders.
- Basis: The harness Specs MCP CRUD tools previously wrote to one global database, which could mix unrelated project requirements; the operator requested project-local registries and explicit folder population order.
- Decision: Populate requirements, business use cases, entity model, system use cases, and functional diagrams sequentially.
- Basis: Each later artifact depends on a prior stage, and the entity model must exist before system use cases assign operations to entities.
- Decision: Use globally unique `UC-XXX` IDs across the business and system use-case directories, and standard EARS comma forms validated by the current Specs MCP validator.
- Basis: The retrieved use-case validator requires unique three-digit UC IDs, and the deployed EARS validator accepts comma-form triggers such as `When ..., the system shall ...`.
