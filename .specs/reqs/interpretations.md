# Current interpretations

## 2026-12-31 — Dynamic rule context for OpenCode

- Decision: Apply plan-do through the local plan-todo alias and compare programmatic selection with summarization as an experiment. Basis: the latest request reopens both as candidates and the capability-cone draft prohibits scoring on its runtime route. Feature 14 already owns implementation.

## 2026-11-18: Integration backport planning

- Decision: Use plan-do through planning and board handoff. Extend existing registry publication after checking source ownership, and use prior SATNA deployment receipts and bounded routing results to decide what belongs in the export. Basis: plan-todo is absent, the operator requested planning, and existing service and client evidence narrows the remaining work.

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
