# Python server environments

SUPERSEDED 2026-10-20: The retrieve-skills-only plan was replaced by the approved
cross-harness MCP migration. Current scope and implementation tracking live in
`~/.mcp/specs/specs.db` (task 75) and `~/.harness/docs/playbooks/repair-cross-harness-mcp-loading.md`.
The superseding evidence is the user's explicit scope correction to include all
registered MCP servers through the shared `~/.harness` convention.

HISTORICAL (SUPERSEDED): 2026-10-20; resume the recovered Claude session by migrating the broken
retrieve-skills server first, then use its verified contract for other servers.

## Pipeline

| Stage | Mechanism | Contract |
| --- | --- | --- |
| INVENTORY | Resolve the supervisor, canonical source, interpreter and dependencies | [mandatory] R1 |
| LOCK | Resolve a minimal Python 3.12 project with a CPU-only torch source | [mandatory] R2 |
| SYNC | Install the lock into the canonical server's .venv from uv's C: cache | [mandatory] R3 |
| VERIFY | Check imports, real cached-model embeddings and the existing unit battery | [mandatory] R4 |
| CUTOVER | Point the existing launcher and health-probe task at the verified environment | [mandatory] R5 |
| CONFIRM | Exercise health, three distinct retrieval queries and MCP skill reading | [mandatory] R6 |

## Requirements

R1: The migration MUST preserve the canonical store and SQLite index at
`C:\Users\user\.skills` and `retrieve-skills\index.db` respectively.

R2: The project MUST declare directly imported third-party runtime dependencies;
the lock MUST resolve all transitive versions. Torch MUST use the explicit CPU
index because the incumbent embedder defaults to CPU. Vision/audio packages and
the unused local reranker MUST remain absent from the default runtime.

R3: When syncing, uv MUST use hardlink mode with the cache and environment on C:.
Verification MUST inspect a real installed package's hardlinks, rather than infer
deduplication from matching drive letters. Existing py310 packages MUST remain intact.

R4: If imports, offline MiniLM embeddings or the existing unit battery fail,
the launcher MUST remain unchanged until the failing dependency is corrected.

R5: When R4 passes, the canonical launcher MUST execute its own .venv interpreter.
The Scheduled Task MUST retain its existing trigger and restart settings. Its
compatibility launcher under `.mcp` MUST delegate to the canonical launcher.
The health probe and its CLI reindex path MUST use the same environment.

R6: Completion MUST include the existing supervisor running the new interpreter,
a populated health response, successful retrieval for three distinct relevant
queries, and a successful MCP initialize/list/read round trip. A failed quality
check MUST be reported, not converted to a passing assertion.

R7: If a cutover fails, the previous launcher/task definitions MUST be available
in the dated workspace backup; no destructive py310 cleanup is authorized here.

## Acceptance

- Given the locked environment, When importing server dependencies and encoding
  three varied strings offline, Then all imports MUST succeed and embeddings MUST
  be finite, nonzero and match the existing index's dimension.
- Given the canonical source, When running test_router_core.py and
  test_health_probe.py with the locked interpreter, Then every existing test MUST pass.
- Given a running Scheduled Task, When inspecting its server process, Then the
  interpreter MUST belong to the canonical .venv and its upstream base interpreter.
- Given the running endpoint, When retrieving debugging, specification and MCP
  server guidance, Then each response MUST include relevant indexed candidates.
- Given a package file in .venv, When listing its hardlinks, Then at least one
  link MUST reside in the configured uv cache.

## CLOSED

- Shared tool environment: rejected because the recovered service trace shows
  torchvision::nms import failure in the shared py310 environment.
- CUDA torch for retrieve-skills: rejected because the current backend selects
  CPU by default; no GPU execution is needed to preserve its behavior.
- Broad uninstall or py310 removal: excluded because hooks and other servers
  still reference it in harness.json and live process command lines.
- Algorithm or retrieval threshold changes: excluded from dependency isolation.

## Preconditions and failure modes

Requires the installed Python 3.12.9 interpreter, uv, the cached MiniLM model,
network access for missing wheels, and permission to update the external server
directory and Scheduled Tasks. Stop before cutover on dependency or model failure.
Retain logs and backups on supervisor or retrieval failure.

## Evidence and state

- TESTED: Claude transcript `cadf8cc0-1b1a-458d-b201-49668b073285` contains no venv migration.
- TESTED: retrieve-skills task delegates through `.mcp/retrieve-skills/launch.ps1`
  to server code under `.skills/retrieve-skills`, using py310.
- TESTED: service log records `RuntimeError: operator torchvision::nms does not exist`.
- TESTED: CPU is the incumbent default device; MiniLM snapshot exists locally.
- OPEN: locked environment, dependency checks, live cutover, package hardlink proof.

Spec validation: PASS; requirements are atomic, failure gates precede cutover,
acceptance checks trace to R1-R7, and no source/API ownership changes are proposed.
