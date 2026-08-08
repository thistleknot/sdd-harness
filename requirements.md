# Requirements — Cross-Harness SDD

## Introduction

A unified spec-driven development (SDD) workflow that operates identically across Claude Code, opencode, and pi. The workflow separates planning from execution, enforces spec-first discipline, and provides skill retrieval, memory, and task tracking through shared MCP services. The model tier varies by harness (API vs local ollama), but the behavioral contract is constant.

## Glossary

- **Harness**: A coding agent environment (Claude Code, opencode, pi) that hosts the SDD workflow.
- **SDD**: Spec-Driven Development — plan first, implement second, verify third.
- **Planning Mode**: Read-only phase where the agent researches, analyzes, and produces a spec. No file mutations.
- **Spec Gate**: A mechanism that blocks file writes until the governing spec reaches an approved implementation phase.
- **Skill Store**: The corpus at `~/.claude/skills/.skills/` — 166+ SKILL.md files retrievable via the retrieve-skills MCP.
- **Memory Bank**: Durable markdown + Chroma vector store at `~/memory-bank/`.
- **Agent Ladder**: Escalation chain from cheapest model to most expensive, gated by failure evidence.

## Requirements

### Requirement 1: Three-Tier Memory Architecture
**User Story:** As a developer, I want persistent context across sessions regardless of which harness I use.
#### Acceptance Criteria
1. ALL harnesses SHALL read from the same memory-bank (`~/memory-bank/`).
2. ALL harnesses SHALL access memory via the `memory-index` MCP service on port 8055.
3. At session start, the harness SHALL call `search_memory` or read the six canonical markdown files.
4. After significant tasks, the harness SHALL call `log_memory` or update `activeContext.md`/`progress.md`.

### Requirement 2: Skill Retrieval Gate
**User Story:** As a developer, I want task-relevant skills auto-injected regardless of which harness I use.
#### Acceptance Criteria
1. ALL harnesses SHALL access skills via the `retrieve-skills` MCP service on port 8765.
2. At the start of any non-trivial task, the harness SHALL call `retrieve_skills("<task description>")`.
3. Skills that PASS the margin gate SHALL be read and applied.
4. The harness SHALL NOT call retrieve_skills for trivial questions or already-loaded skills.

### Requirement 3: Spec-First Discipline
**User Story:** As a developer, I want the agent to plan before coding, in every harness.
#### Acceptance Criteria
1. WHEN a task touches observable behavior, control flow, persistence, or public interfaces, the harness SHALL produce a spec before writing code.
2. THE spec SHALL contain: requirements with acceptance criteria, scope boundary, and implementation ordering.
3. IN Claude Code, the spec gate (`spec_gate.py`) SHALL enforce this by denying file mutations until the spec is approved.
4. IN opencode/pi, the agent SHALL self-enforce spec-first via steering/AGENTS.md instructions.
5. Mechanical edits (typos, formatting, renames) MAY skip the spec gate with explicit justification.

### Requirement 4: Agent Ladder (Model Routing)
**User Story:** As a developer, I want the cheapest sufficient model used per role, with escalation only on failure.
#### Acceptance Criteria
1. THE harness SHALL define a model-to-role mapping per environment.
2. THE default working model SHALL be the cheapest that can handle routing + implementation (4b for local, Sonnet for API).
3. ESCALATION to a heavier model SHALL occur only when the lighter model's fix ladder is exhausted.
4. THE ladder SHALL be: implement → critic verifies → fixer_low proposes → fixer_med applies → planner re-specs → STOP.

#### Claude Code Model Map
| Role | Model |
|------|-------|
| Orchestrator/Coder | claude-sonnet-5 |
| Planner/Spec Author | claude-opus-5 |
| Architect (terminal) | claude-fable-5 |
| Worker (rote) | claude-haiku-4.5 |

#### Local (opencode/pi) Model Map
| Role | Model |
|------|-------|
| Orchestrator/Coder/Critic | qwopus-coding-thinking-256k:4b |
| Planner/Spec Author | qwen3.5-reasoning-thinking-256k:9b |
| Architect (terminal) | huihui-gemma-4-12B-agentic-fable5-abliterated |
| Worker (rote) | qwen3.5-oc:2b |
| VLM | qwen3-vl:2b |

### Requirement 5: Hook Architecture
**User Story:** As a developer, I want lifecycle hooks that fire consistently across harnesses.
#### Acceptance Criteria
1. THE harness SHALL support hooks on: SessionStart, UserPromptSubmit, PreToolUse, PostToolUse, Stop.
2. UserPromptSubmit hooks SHALL trigger skill retrieval injection (via hook.py or equivalent).
3. SessionStart hooks SHALL trigger memory/todo reads.
4. PreToolUse hooks SHALL enforce the spec gate (Claude Code) or advisory checks.
5. IN opencode/pi where hooks aren't native, equivalent behavior SHALL be achieved via agent instructions (steering).

### Requirement 6: MCP Server Registration
**User Story:** As a developer, I want all four MCP services available in every harness.
#### Acceptance Criteria
1. ALL harnesses SHALL have access to: retrieve-skills, memory-index, todo, data-science-skills.
2. HTTP services (retrieve-skills:8765, memory-index:8055) SHALL use HTTP/streamable-http transport.
3. Stdio services (todo, data-science-skills) SHALL use the py310 interpreter.
4. Multi-session safety: HTTP services MUST be persistent processes; stdio services MUST NOT share SQLite state across concurrent sessions.

### Requirement 7: Sub-Agent Configuration
**User Story:** As a developer, I want reusable sub-agents with isolated context and least-privilege tool access.
#### Acceptance Criteria
1. Sub-agents SHALL be defined as markdown files with YAML frontmatter (name, description, tools, model).
2. Sub-agents SHALL run in isolated context windows (no main conversation pollution).
3. Sub-agents SHALL have least-privilege tool access (only tools needed for their role).
4. Claude Code: agents in `~/.claude/agents/*.md`. Opencode: agents in `~/.config/opencode/agents/`. Pi: inherits Claude Code user scope.

### Requirement 8: Todo Integration
**User Story:** As a developer, I want deferred work tracked automatically across sessions.
#### Acceptance Criteria
1. At session start: `list_todos(workspace_root=<git_root>)`.
2. During work: `add_todo` for deferred follow-ups, `complete_todo` when done.
3. The workspace_root SHALL be the git root of the current working directory.
4. If not in a git repo, workspace_root is omitted (global fallback).

### Requirement 9: Determinism and Reproducibility
**User Story:** As a developer, I want consistent behavior regardless of which harness I use.
#### Acceptance Criteria
1. The same prompt + same skill store + same memory SHALL produce functionally equivalent results across harnesses.
2. Steering rules SHALL be authored once and applied to all three environments (via AGENTS.md, steering files, or equivalent).
3. Configuration drift between harnesses SHALL be detectable by a conformance test suite.

### Requirement 10: Validation and Testing
**User Story:** As a developer, I want a test suite that proves each harness implements the SDD contract correctly.
#### Acceptance Criteria
1. THE test suite SHALL verify: MCP connectivity, skill retrieval, memory read/write, todo CRUD, spec gate enforcement.
2. THE test suite SHALL be runnable against each harness independently.
3. FOR Claude Code: tests invoke via `claude -p` (headless).
4. FOR opencode: tests invoke via `opencode run`.
5. FOR pi: tests invoke via the pi CLI.
6. Results SHALL be comparable across harnesses (same pass/fail criteria).

### Requirement 11: Constitutional Framework
**User Story:** As a developer, I want immutable architectural principles that constrain LLM behavior during implementation, so generated code is consistently modular, testable, and simple.
#### Acceptance Criteria
1. THE harness SHALL define a constitution (`constitution.md`) with immutable principles governing code generation.
2. THE constitution SHALL include at minimum: Simplicity Gate (max complexity justification), Anti-Abstraction Gate (use frameworks directly), Test-First Imperative (no code before tests), and Integration-First Testing (real environments over mocks).
3. THE spec gate SHALL enforce Phase -1 Gates (pre-implementation checklists) before allowing writes.
4. THE constitution SHALL be version-controlled and require explicit amendment process with rationale.
5. ALL harnesses SHALL reference the same constitution (shared artifact, not per-harness copies).

### Requirement 12: Convergence Check
**User Story:** As a developer, I want to assess whether the implementation matches the spec after coding, so drift is caught and remaining work is captured.
#### Acceptance Criteria
1. THE harness SHALL provide a convergence command/workflow that compares implementation against the governing spec.
2. THE convergence check SHALL identify: implemented items, missing items, items that deviate from spec.
3. IF remaining work is identified, THE harness SHALL append it as new tasks to the existing tasks.md.
4. THE convergence check SHALL run after implementation completes (manually triggered or on Stop hook).

### Requirement 13: Explicit Uncertainty Markers
**User Story:** As a developer, I want the agent to mark ambiguities explicitly rather than guessing, so I can review and resolve them before implementation.
#### Acceptance Criteria
1. WHEN producing specs, designs, or tasks, the agent SHALL mark all ambiguities with `[NEEDS CLARIFICATION: <specific question>]`.
2. THE agent SHALL NOT guess or assume when the user's intent is unclear — it SHALL mark and proceed with the marker visible.
3. THE spec gate SHALL NOT approve a spec for implementation if it contains unresolved `[NEEDS CLARIFICATION]` markers.
4. THIS behavior SHALL be enforced via steering/AGENTS.md instructions across all harnesses.
