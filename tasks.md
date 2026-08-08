# Tasks — Cross-Harness SDD

## Task 1: Validate Claude Code (production baseline)
- **Status**: in progress
- **Requirements**: 1, 2, 3, 5, 6, 8, 10
- **Description**: Confirm Claude Code implements the full SDD contract. Build test suite.

### Sub-tasks
- [x] 1.1 MCP servers registered (retrieve-skills, memory-index, todo, data-science-skills)
- [x] 1.2 Hook.py wired in settings.json UserPromptSubmit
- [ ] 1.3 Write conformance test suite (`~/.harness/tests/test_claude_code.py`)
- [ ] 1.4 Test: `claude -p "retrieve skills for debugging"` → verify skill injection
- [ ] 1.5 Test: `claude -p "list todos"` → verify todo MCP responds
- [ ] 1.6 Test: `claude -p "search memory for skill router"` → verify memory MCP responds
- [ ] 1.7 Test: spec gate blocks writes without approved spec (needs .spec/ directory)
- [ ] 1.8 Test: agent ladder routing (planner → coder → critic → fixer escalation)

## Task 2: Write conformance test suite
- **Status**: not started
- **Requirements**: 10
- **Depends on**: Task 1

### Sub-tasks
- [ ] 2.1 Create `~/.harness/tests/conftest.py` with harness-agnostic fixtures
- [ ] 2.2 Create `~/.harness/tests/test_mcp.py` — MCP connectivity for all 4 services
- [ ] 2.3 Create `~/.harness/tests/test_skill_retrieval.py` — correct skill surfaces for known prompts
- [ ] 2.4 Create `~/.harness/tests/test_memory.py` — search, log, stats
- [ ] 2.5 Create `~/.harness/tests/test_todo.py` — add, list, complete, remove
- [ ] 2.6 Create `~/.harness/tests/test_sdd.py` — spec gate enforcement, planning mode
- [ ] 2.7 Create `~/.harness/tests/test_agent_ladder.py` — model routing verification
- [ ] 2.8 Create `~/.harness/run_tests.py` — runner that targets a specific harness

## Task 3: Port to opencode
- **Status**: not started
- **Requirements**: 4, 6, 7, 9
- **Depends on**: Task 2

### Sub-tasks
- [x] 3.1 Update `~/.config/opencode/opencode.json` MCP block (done)
- [ ] 3.2 Create opencode agent definitions at `~/.config/opencode/agents/`
- [ ] 3.3 Write opencode-specific model routing in agent frontmatter
- [ ] 3.4 Verify AGENTS.md is loaded (check `~/.config/opencode/AGENTS.md`)
- [ ] 3.5 Run conformance tests against opencode: `opencode run "<test prompt>"`
- [ ] 3.6 Fix failures, iterate

## Task 4: Port to pi
- **Status**: not started
- **Requirements**: 4, 6, 7, 9
- **Depends on**: Task 2

### Sub-tasks
- [ ] 4.1 Verify pi inherits Claude Code user-scope MCP registrations
- [ ] 4.2 Verify AGENTS.md is loaded in pi sessions
- [ ] 4.3 Verify litellm_config.yaml routes to correct ollama models
- [ ] 4.4 Run conformance tests against pi
- [ ] 4.5 Fix failures, iterate

## Task 5: Local model agent definitions
- **Status**: not started
- **Requirements**: 4, 7
- **Depends on**: Task 3

### Sub-tasks
- [ ] 5.1 Create `orchestrator.md` (4b default coder, routes to specialists)
- [ ] 5.2 Create `planner.md` (9b reasoning, spec author, never implements)
- [ ] 5.3 Create `critic.md` (4b, verify+run, pass/fail with evidence)
- [ ] 5.4 Create `fixer.md` (9b, root-cause + direct fix on escalation)
- [ ] 5.5 Create `worker.md` (2b, rote execution from pseudocode)
- [ ] 5.6 Test each agent in isolation with a role-appropriate prompt

## Task 6: End-to-end SDD validation
- **Status**: not started
- **Requirements**: 3, 9, 10
- **Depends on**: Tasks 1-5

### Sub-tasks
- [ ] 6.1 Define a test feature (small, well-scoped)
- [ ] 6.2 Run SDD workflow in Claude Code: plan → spec → implement → verify
- [ ] 6.3 Run same workflow in opencode with local models
- [ ] 6.4 Run same workflow in pi with local models
- [ ] 6.5 Compare outputs — verify functional equivalence
- [ ] 6.6 Document drift and remediate

## Task 7: Constitutional framework
- **Status**: not started
- **Requirements**: 11, 13
- **Depends on**: Task 1

### Sub-tasks
- [ ] 7.1 Draft `~/.harness/constitution.md` with immutable principles (Simplicity, Anti-Abstraction, Test-First, Integration-First)
- [ ] 7.2 Define Phase -1 Gates as checklists (pre-implementation checkpoints)
- [ ] 7.3 Integrate gates into spec_gate.py (block writes if Phase -1 not cleared)
- [ ] 7.4 Add `[NEEDS CLARIFICATION]` enforcement to spec templates and steering
- [ ] 7.5 Wire constitution into CLAUDE.md / AGENTS.md / steering across harnesses
- [ ] 7.6 Test: spec with unresolved markers → gate blocks implementation

## Task 8: Convergence workflow
- **Status**: done
- **Requirements**: 12
- **Depends on**: Task 2

### Sub-tasks
- [x] 8.1 Create convergence prompt/command: compare implementation vs spec, report gaps
- [x] 8.2 Wire as Stop hook or manual slash command
- [x] 8.3 Auto-append remaining work to tasks.md when gaps found
- [x] 8.4 Test: implement 80% of a spec → convergence finds the missing 20%

## Task 9: Security scanning hook
- **Status**: not started
- **Requirements**: 11
- **Depends on**: Task 1
- **Inspired by**: ECC (Everything-Claude-Code)

### Sub-tasks
- [ ] 9.1 Create `~/.harness/hooks/security_scan.py` — PreToolUse on Write/Edit
- [ ] 9.2 Detect: hardcoded secrets, API keys, passwords, tokens in file content
- [ ] 9.3 Detect: .env files being written/committed, private key patterns
- [ ] 9.4 Exit code 2 (BLOCK) when credential exposure found, with explanation
- [ ] 9.5 Wire into settings.json PreToolUse matcher
- [ ] 9.6 Test: write a file containing `OPENAI_API_KEY=sk-...` → blocked

## Task 10: Codebase-map injection
- **Status**: not started
- **Requirements**: 2
- **Depends on**: Task 1
- **Inspired by**: claudekit

### Sub-tasks
- [ ] 10.1 Create `~/.harness/hooks/codebase_map.py` — UserPromptSubmit, first prompt only
- [ ] 10.2 Generate project structure summary (directories, key files, tech stack)
- [ ] 10.3 Inject as invisible additionalContext so agent knows the project layout
- [ ] 10.4 Cache the map, regenerate only when file tree changes (mtime check)
- [ ] 10.5 Wire into settings.json UserPromptSubmit
- [ ] 10.6 Test: fresh session → agent knows project structure without being told

## Task 11: Cross-harness adapter
- **Status**: not started
- **Requirements**: 9
- **Depends on**: Tasks 3, 4
- **Inspired by**: ECC, Omnigent

### Sub-tasks
- [ ] 11.1 Create `~/.harness/adapter.py` — reads shared config, writes per-harness config
- [ ] 11.2 Shared config: `~/.harness/harness.json` (MCP servers, model routing, hooks)
- [ ] 11.3 Adapter target: Claude Code (writes .claude.json + settings.json)
- [ ] 11.4 Adapter target: opencode (writes opencode.json mcp block)
- [ ] 11.5 Adapter target: Kiro (writes ~/.kiro/settings/mcp.json)
- [ ] 11.6 Test: change harness.json → run adapter → all 3 configs updated consistently

## Task Dependency Graph

```
Task 1 (validate Claude Code)
   │
   ├───────────────────┬──────────────────┐
   ▼                   ▼                  ▼
Task 2 (test suite)  Task 7 (constitution) Task 9 (security)
   │                   │                  │
   ├──────────┐        │                  │
   ▼          ▼        │                  │
Task 3 (oc) Task 4 (pi)│                  │
   │          │        │                  │
   └────┬─────┘        │                  │
        ▼              ▼                  │
Task 5 (local agents)  Task 8 (convergence)│
        │                                 │
        ▼                                 │
Task 6 (e2e SDD)                          │
                                          │
Task 10 (codebase-map) ◀──── Task 1      │
                                          │
Task 11 (adapter) ◀──── Tasks 3, 4       │
```
