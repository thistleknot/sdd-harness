# Inspirations — From "Agentic Coding with Claude Code" (Eden Marco, Packt 2026)

## Source

Book: "Agentic Coding with Claude Code" by Eden Marco (Packt, 2026)
Extracted from: `~/Documents/wiki/harness/Agentic Coding with Claude Code.json` (Docling)
HookHub project: the book's running example — a Next.js app cataloging Claude Code hooks.

## Key Architectural Patterns to Adopt

### 1. Three-Tier Memory Hierarchy (Ch1, §Context Engineering)

The book describes exactly our architecture:
- **Project memory** (`./CLAUDE.md`) — team-shared, version-controlled
- **User memory** (`~/.claude/CLAUDE.md`) — personal preferences across all projects
- **Dynamic memory imports** (`@path/to/file.md`) — inject context from dedicated memory files

**Our implementation:** `~/memory-bank/` (global 6-file layer + project lanes) + Chroma annealing log + `@` imports in CLAUDE.md. Already matches.

### 2. Context-Switching Hooks (Ch1, §Dynamic Memory)

The book shows a `context-switcher.sh` that:
- Detects the current git branch
- Appends relevant `@path` references to CLAUDE.md based on branch
- Uses `grep -qxF` to prevent duplicate entries (idempotent)
- Wired as a UserPromptSubmit hook

**Inspiration for us:** Our `hook.py` does skill retrieval per-prompt. We could extend with branch-aware context injection — different specs/memory for different feature branches.

### 3. Spec-Driven Development (Ch2 + Ch6)

The book's SDD workflow:
1. Enter planning mode (`/plan`) — read-only, no file mutations
2. Produce a SPEC.md with requirements + acceptance criteria
3. Export spec to a markdown file (persists as project memory)
4. Exit planning mode → implement from spec
5. Spec constrains agent behavior during implementation

**Our implementation:** `spec_gate.py` PreToolUse hook enforces this mechanically. The book achieves it through discipline + planning mode toggle. We're ahead here — machine-enforced > discipline-enforced.

### 4. Multi-Agent Parallel Execution (Ch6)

The book demonstrates:
- Identify independent tasks from a spec
- Open multiple Claude Code instances
- Each works on a different section (e.g., hero vs hook cards)
- Commit separately, merge at the end

**Our implementation:** AGENTS.md agent roster + orchestration rules. The book's approach is manual (multiple terminals); ours uses sub-agent delegation within a single session.

### 5. Sub-Agent Configuration Format (Ch7)

The book's format (which matches what we already use):
```yaml
---
name: <agent-name>
description: <when to use>
model: <optional model override>
tools: ["Read", "Bash", "Grep", ...]
---
# System prompt here
```

- **Project scope:** `.claude/agents/*.md`
- **User scope:** `~/.claude/agents/*.md`
- Context isolation: each sub-agent gets its own context window
- Least privilege: explicit tool allowlist

**Our implementation:** Already have `~/.claude/agents/opus_planner.md`, `sonnet_critic.md`, etc. Format matches.

### 6. Hook Event Types (Ch3)

The book catalogs these hook events:
| Event | When | Use Case |
|-------|------|----------|
| `Stop` | Before Claude finishes response | Notifications, post-processing |
| `UserPromptSubmit` | When user sends a prompt | Context injection, skill retrieval |
| `PreToolUse` | Before a tool executes | Spec gate, access control |
| `PostToolUse` | After a tool executes | Logging, post-edit actions |
| `Notification` | When notifications are sent | External alerting |
| `SessionStart` | New session begins | Memory loading, todo listing |

Exit code semantics:
- **exit 0**: success, stdout forwarded
- **exit 2**: BLOCK the action
- **other**: silent failure, no block

**Our implementation:** We use SessionStart (membank), UserPromptSubmit (skill retrieval + spec_state + membank + log_event), PreToolUse (spec_gate + log_event), PostToolUse (spec_state + log_event), Stop (verify_gate + log_event). Covers all the book's patterns plus more.

### 7. Plugins = Bundled Primitives (Ch5)

The book introduces plugins as:
> "Slash commands (skills), sub-agents, MCP servers, and hooks bundled into a single, shareable primitive."

Before plugins, sharing required manual copy of `.claude/` contents. Plugins bundle everything into one install.

**Inspiration for us:** Our skill store + MCP services + hooks could be packaged as a plugin for other Claude Code users. The `retrieve-skills` system IS effectively a plugin that auto-discovers and injects skills.

### 8. Git Worktree Multi-Agent (Ch10)

The book's advanced pattern:
1. Create git worktrees for parallel feature work
2. Each agent works in its own worktree (isolated directory, shared repo)
3. After completion, merge all worktrees into the target branch
4. Integration branch (`project/hookhub-merge`) as intermediate step

**Our implementation:** Referenced in AGENTS.md orchestration rules: "git worktrees for non-dependent features worked by sub-agents, then merge." Same pattern.

### 9. Skills = Progressive Context Loading (Ch9)

The book explains skills as:
> "Progressive context loading — the agent dynamically injects only the relevant instructions for the current task."

This is EXACTLY what our `retrieve-skills` MCP does: query → margin gate → inject only what passes.

### 10. Conformance Test Pattern (Ch6)

The book validates by:
1. Define spec artifact (SPEC.md)
2. Implement from spec
3. Verify implementation matches spec (critic role)
4. If mismatch → escalate (not silently fix)

**Our implementation:** The agent ladder (critic → fixer_low → fixer_med → planner re-spec) is the mechanical version of this pattern.

## Hooks We Should Consider Adding

Based on the book's patterns:

| Hook | Event | Purpose | Priority |
|------|-------|---------|----------|
| **branch-context-switcher** | UserPromptSubmit | Inject branch-specific CLAUDE.md refs based on git branch | Medium |
| **post-edit-indexer** | PostToolUse (Edit/Write) | Trigger `mem index` after memory-bank edits | High |
| **test-on-save** | PostToolUse (Write) | Auto-run relevant tests after file write | Medium |
| **commit-message-enforcer** | PreToolUse (Bash: git commit) | Validate commit message format | Low |
| **session-recap** | Stop | Auto-update `last_session.md` on session end | High |

## What We Have That the Book Doesn't

1. **Machine-enforced spec gate** (book uses planning mode toggle; we use PreToolUse denial)
2. **Semantic skill retrieval** (book manually discovers skills; we have ColBERT-reranked auto-injection)
3. **Annealing memory** (book has static CLAUDE.md; we have Chroma with promotion/decay)
4. **Cross-harness portability** (book is Claude Code only; we target 3 environments)
5. **CV-tuned hyperparameters** (book doesn't tune retrieval; we have sweep.py)
6. **Multi-session HTTP services** (book uses stdio per-session; we solved the lock contention issue)

## Competitive Landscape (from Augment Code analysis, Jun 2026)

| Tool | Spec Approach | Multi-Agent | Model Flex | Open Source | Best For |
|------|--------------|-------------|-----------|-------------|----------|
| **Kiro** | Requirements → Design → Tasks → Code | No | AWS Bedrock only | No | Single IDE SDD |
| **Augment Cosmos** | Spec & intent review checkpoint | Yes (parallel Experts) | BYOK all providers | No | Org-scale agent ops |
| **GitHub Spec Kit** | Static markdown artifacts, 5-phase CLI | No | 30+ agents | Yes (MIT) | Cross-agent portability |
| **OpenSpec** | Single source of truth, delta specs | No | Multiple agents | Yes (MIT) | Brownfield consolidation |
| **Cursor Rules** | Pseudo-specs (.cursorrules) | No | Claude/GPT/Gemini | No | Lightweight IDE guardrails |
| **Codex Desktop** | No spec layer | Yes (parallel threads) | OpenAI only | CLI Apache 2.0 | Parallel autonomous tasks |
| **Devin** | No spec layer (anti-spec) | Single autonomous | Proprietary | No | Well-scoped repetitive tasks |
| **Our harness** | Machine-enforced gate + semantic retrieval | Yes (agent ladder) | API + local ollama | Proprietary | Cross-harness SDD + memory |

### Key Insight from the Landscape

Our system combines:
- Spec Kit's **spec-first methodology** (templates, phases, constitution)
- Kiro's **machine enforcement** (PreToolUse denial, not just discipline)
- Cosmos's **multi-agent orchestration** (ladder with escalation)
- OpenSpec's **single source of truth** (memory-bank as canonical state)
- Codex's **parallel execution** (git worktrees + sub-agents)

None of the competitors have all five. Our gap vs Cosmos: we lack their 400K+ file semantic indexing (our retrieve-skills covers skills, not full codebase). Our gap vs Spec Kit: we lack their CLI tooling (`specify` commands, templates, constitutional framework).

## GitHub Spec-Kit Architecture (cloned at ~/.harness/references/spec-kit/)

## The Stoa — Recursive Three-Role Architecture

Source: https://github.com/denson/the-stoa (MIT)

**What it is:** A multi-agent system for Claude Code with three named roles:
- **POLYBIUS** — the strategic/analytical role (plans, reviews, hardening)
- **PLINY** — the implementation/execution role (builds, tests, iterates)
- **PRINCIPAL** — the human operator (approves, steers, decides dilemmas)

**Key architectural choices:**
- Built on **"beadwork" (bw)** — a durable cross-session substrate (like our memory-bank but structured as versioned beads that survive context resets)
- **Two operational modes:** formal gauntlet (hardening: strict verification before promotion) + pair-programming (fast exploration: looser gates)
- **Recursive:** the roles can invoke each other — POLYBIUS can ask PLINY to prototype, PLINY can escalate to POLYBIUS for design judgment
- **Multi-seat terminal bootstrap** — launches multiple Claude Code sessions in side-by-side panes (Windows Terminal `wt`)
- **Decision surface skill** — distinguishes PROBLEMS (solvable: go find the answer) from DILEMMAS (value-tradeoffs: illuminate, never fake a recommendation)

**What we should adopt:**
- The **two-mode toggle** (gauntlet vs pair-programming) maps to our `effortLevel` setting — high effort = formal gauntlet, low = pair-programming
- The **decision surface** concept (problem vs dilemma classification) — before researching, determine if the question is solvable or a tradeoff
- The **durable substrate** concept — our memory-bank + annealing log is the equivalent, but theirs is more tightly coupled to the agent session

**What we already do better:**
- Our memory is semantic (Chroma vector recall) vs their beadwork (file-structured)
- Our skill retrieval is automatic (ColBERT margin gate) vs their manual skill invocation
- Our spec gate is machine-enforced vs their gauntlet mode being discipline-enforced

## Everything-Claude-Code (ECC) — Production Harness System

Source: https://github.com/aXp-Engineering/Everything-Claude-Code (MIT)

**What it is:** A battle-tested (10+ months) complete agent harness system. Anthropic hackathon winner. Covers: skills, instincts, memory optimization, continuous learning, security scanning, research-first development.

**Key architectural choices:**
- **Cross-harness adapters** — works with Claude Code, Codex, OpenCode, Cursor, Gemini, Zed, GitHub Copilot, Antigravity, Qwen
- **"Instincts"** — automatic behavioral patterns that fire without explicit invocation (similar to our steering rules)
- **Research-first development** — agent grounds claims in evidence before implementing
- **Continuous learning** — patterns discovered during work get promoted to reusable skills
- **Security scanning** — hooks that check for credential exposure, unsafe operations

**What we should adopt:**
- The **"instincts" concept** — behavioral triggers lighter than skills, always-on like steering but more action-oriented
- **Cross-harness adapters** — their approach to making one config work across Claude Code + Codex + OpenCode is exactly our Task 3-4 challenge
- **Security scanning hooks** — we have none; they catch credential exposure in writes

**What we already do better:**
- Our memory system is more sophisticated (annealing + promotion vs their flat memory)
- Our retrieval is semantic (ColBERT) vs their keyword-triggered
- Our constitutional framework is more rigorous (9 articles + Phase -1 gates)

## GitHub Spec-Kit Architecture (cloned at ~/.harness/references/spec-kit/)

### What It Brings That We Don't Have

1. **`specify` CLI** — `specify init`, `specify self upgrade`, project scaffolding
2. **Five-phase workflow as slash commands:**
   - `/speckit.constitution` — project governing principles
   - `/speckit.specify` — requirements from natural language
   - `/speckit.plan` — technical implementation plan
   - `/speckit.tasks` — actionable task breakdown
   - `/speckit.implement` — execute tasks from plan
   - `/speckit.converge` — assess codebase vs spec, append remaining work
3. **Constitutional framework** — 9 immutable articles (Library-First, CLI Interface, Test-First, Simplicity Gate, Anti-Abstraction, Integration-First)
4. **Template-driven LLM constraint** — forces `[NEEDS CLARIFICATION]` markers, prevents premature implementation details, enforces abstraction levels
5. **Phase -1 Gates** — pre-implementation checkpoints (simplicity, anti-abstraction, integration-first)
6. **Extensions system** — community hooks, presets, bundles (role-based setups)
7. **Integration registry** — 30+ agent support via subpackage architecture
8. **Manifest-based install/uninstall** — SHA-256 hash tracking for safe file management

### What We Already Do Better

1. **Enforcement** — their workflow is discipline-only; ours blocks writes mechanically
2. **Memory** — they have no annealing/promotion; we have Chroma + markdown lifecycle
3. **Skill retrieval** — they rely on agent's native context; we have ColBERT-gated injection
4. **Multi-session** — they're single-session CLI; we have persistent HTTP services
5. **Agent ladder** — they have no escalation chain; we have critic → fixer → planner

### What We Should Adopt from Spec-Kit

| Feature | Their Implementation | Our Adaptation |
|---------|---------------------|----------------|
| **Constitution** | `memory/constitution.md` with 9 articles | Add to our CLAUDE.md / steering as immutable principles |
| **Phase -1 Gates** | Simplicity/Anti-Abstraction/Integration-First checklists | Integrate into spec_gate.py PreToolUse enforcement |
| **`[NEEDS CLARIFICATION]` markers** | Templates force explicit uncertainty | Add to our spec skill's EARS template |
| **`/speckit.converge`** | Assess codebase vs spec, append remaining work | New slash command — close the loop after implementation |
| **Template checklists** | Self-review gates in spec/plan templates | Add to our self_review.py Stop hook |
| **Feature numbering** | Auto-scan + sequential numbering + branch creation | Adapt for our .spec/ workflow |

## Next Steps

1. Implement the four high-priority hooks (PreCompact, self-review, SessionEnd, verify-setup)
2. Build the conformance test suite (Task 2 in tasks.md)
3. Run tests against Claude Code to establish the production baseline
4. Port to opencode/pi once GPU is free

## SDD-Specific References

| Source | URL | Why It Matters |
|--------|-----|----------------|
| **SDD Skill (SpillwaveSolutions)** | https://github.com/SpillwaveSolutions/sdd-skill | Installable Claude Code skill implementing the full SDD workflow |
| **Agent Skills SDD (Addy Osmani)** | https://github.com/addyosmani/agent-skills/blob/main/skills/spec-driven-development/SKILL.md | Google's Addy Osmani's take on SDD as a reusable agent skill |
| **The Stoa (denson)** | https://github.com/denson/the-stoa | Recursive three-role agent architecture (POLYBIUS + PLINY + PRINCIPAL) built on "beadwork" as durable cross-session substrate. Two modes: formal gauntlet (hardening) + pair-programming (exploration). MIT. Multi-seat terminal bootstrap. |
| **Everything-Claude-Code (ECC)** | https://github.com/aXp-Engineering/Everything-Claude-Code | Complete agent harness: skills, instincts, memory, security, research-first dev. 10+ months of production use. Cross-harness adapters for Codex, Cursor, OpenCode, Gemini, Zed. Anthropic hackathon winner. |
| **OSpec** | https://github.com/clawplays/ospec | Spec-driven agentic workflow: plan → act → verify goal loop with durable specs. Works across Claude Code, Codex, Gemini, OpenCode, and plain CLI. |
| **shlomoc/spec-driven** | https://github.com/shlomoc/spec-driven | Agile SDD pipeline: 15 executable subagents, 12 slash commands, 3 skill packs. Converts 10xDevelopers methodology into Claude Code automation. |
| **Omnigent** | https://github.com/omnigent-ai/omnigent | Open-source meta-harness: orchestrate Claude Code, Codex, Cursor, Pi. Swap harnesses without rewriting. Enforce policies + sandboxing. Cross-device collaboration. |
| **GitHub spec-kit (official)** | https://github.com/github/spec-kit | GitHub's official SDD toolkit — spec comes first, stays source of truth. Drives architecture, implementation, tests, and docs. |
| **Speck (spec-kit for Claude Code)** | https://github.com/nprbst/speck | Opinionated spec-kit derivative optimized for Claude Code: slash commands, natural language skill, CLI. Three-phase: Specify → Plan → Implement. |
| **BMAD-Speckit-SDD-Flow** | https://github.com/milome/BMAD-Speckit-SDD-Flow | AI-TDD control plane for requirement contracts across Cursor, Claude Code, and Codex. 671 commits, AGENTS.md, full spec governance. |
| **speckit-companion (VS Code)** | https://github.com/alfredoperez/speckit-companion | VS Code extension for SDD — manage specs, workflows, steering docs for AI CLI tools (Claude Code, Gemini CLI, Copilot CLI). |
| **claude-night-market/spec-kit plugin** | https://github.com/athola/claude-night-market/blob/master/plugins/spec-kit/README.md | Plugin packaging of spec-kit: write spec → generate plan → break into tasks → execute with tracking. |
| **documented-speckit-development** | https://github.com/bwazik/documented-speckit-development | Agent-friendly docs and templates for reproducible AI-assisted SDD. |
| **Reddit: SDD Experience Thread** | https://www.reddit.com/r/ClaudeCode/comments/1rg0b9i/has_anyone_tried_the_spec_driven_development/ | Community feedback on SDD in practice — failure modes, workarounds |
| **Martin Fowler: SDD Tools** | https://martinfowler.com/articles/exploring-gen-ai/sdd-3-tools.html | ThoughtWorks analysis of SDD tooling — spec quality vs implementation quality |
| **MCP Market: SDD Skill** | https://app.mcpmarket.com/laferrierejc/skills/spec-driven-development | Published MCP-installable SDD skill — shows the standardized distribution format |
| **Zach Lloyd (Warp CEO) SDD Article** | https://x.com/zachlloydtweets/article/2065154860337508577 | Industry perspective on SDD adoption in production coding agents |
| **GitHub Blog: SDD with AI** | https://github.blog/ai-and-ml/generative-ai/spec-driven-development-with-ai-get-started-with-a-new-open-source-toolkit/ | GitHub's official announcement of spec-kit — the methodology explainer |
| **Arun Gupta: SDD with SpecKit + Claude Code** | https://gist.github.com/arun-gupta/e1c2c3a826a0605f6b615d25da918f75 | Detailed walkthrough of SDD workflow using spec-kit with Claude Code |

## Repos to Clone for Inspiration

From the HookHub catalog (verified real repos from the book):

| Repo | Why | Clone? |
|------|-----|--------|
| [awesome-claude-code](https://github.com/hesreallyhim/awesome-claude-code) | Curated list of hooks, commands, CLAUDE.md files, workflows | YES — reference catalog |
| [claude-code-hooks-mastery](https://github.com/disler/claude-code-hooks-mastery) | All 8 hook lifecycle events + security filtering + TTS + sub-agents | YES — implementation patterns |
| [claude-code-hooks-multi-agent-observability](https://github.com/disler/claude-code-hooks-multi-agent-observability) | Real-time capture + visualization of hook events across concurrent agents | YES — observability for our multi-session setup |
| [claudekit](https://github.com/carlrannaberg/claudekit) | Auto-save checkpointing, code quality hooks, spec generation, 20+ subagents | YES — closest to what we're building |
| [claude-code-infrastructure-showcase](https://github.com/diet103/claude-code-infrastructure-showcase) | Hooks that intelligently select and activate Skills based on context | YES — exactly our retrieve-skills pattern |
| [sdd-skill](https://github.com/SpillwaveSolutions/sdd-skill) | Full SDD workflow as an installable Claude Code skill | YES — reference SDD implementation |
| [agent-skills/sdd](https://github.com/addyosmani/agent-skills/blob/main/skills/spec-driven-development/SKILL.md) | Addy Osmani's SDD skill — the canonical agent-skills standard format | YES — format standard |

### New Hook Types We Haven't Used Yet

From the book's HookType enum:
- `SubagentStart` — fires when a sub-agent is launched
- `SubagentStop` — fires when a sub-agent completes
- `SubagentStream` — fires during sub-agent streaming

These could enable:
- Automatic logging of sub-agent activity to memory-bank
- Cost tracking per sub-agent invocation
- Quality gating on sub-agent output before it merges back

### The Infinite Agentic Loop Pattern

The book's `.claude/commands/infinite.md` is a slash command that:
1. Reads a spec file
2. Analyzes existing output directory
3. Plans iteration strategy
4. Deploys multiple sub-agents in parallel waves
5. Each agent gets isolated context + unique creative direction
6. Waves continue until context exhaustion

**Our equivalent:** The orchestrator in AGENTS.md + the agent ladder. But the wave-based parallel execution is something we could adopt for batch operations (e.g., parallel skill store updates, parallel test execution across harnesses).


## oh-my-opencode-slim — Multi-Agent OpenCode Plugin

Source: https://github.com/alvinunreal/oh-my-opencode-slim

**What it is:** A TypeScript plugin for OpenCode that turns a single agent into a coordinated team of 7 specialized agents (Orchestrator, Explorer, Oracle, Council, Librarian, Designer, Fixer). Routes each sub-task to the agent best suited for it, balancing quality, speed, and cost. Background orchestration dispatches specialists as parallel tasks.

**Key architectural choices:**
- Single plugin entry `{ id, server, setup }` — v1 loads `server`, v2 loads `setup`
- Model routing per-agent with runtime preset switching (`/preset`)
- Council pattern — run multiple models in parallel, synthesize a single answer
- Multiplexer integration — agents visible in tmux/zellij panes
- Skills as permission grants — agent can only activate skills it's been given
- Background job board with wall-clock timeouts and supervisor

**What we adopted:**
- The multi-harness plugin pattern (`.claude-plugin/`, `.codex-plugin/`, `.opencode/`, `.pi/`) — used directly in our `~/.harness/plugin/` scaffold
- The concept of one installer targeting all harnesses simultaneously

**What we already do better:**
- Our skill retrieval is semantic (ColBERT rerank, margin gate) vs their static skill assignment
- Our memory has annealing lifecycle vs no cross-session memory
- Our tool-router collapses tool explosion — they expose all tools raw (they hit 58 too)
- Our spec gate is machine-enforced; they rely on orchestrator prompt discipline

## Munder Difflin — Hive-Mind Multi-CLI Orchestrator

Source: https://github.com/chaitanyagiri/munder-difflin

**What it is:** An Electron desktop app that wraps multiple agent CLIs (Claude, Codex, OpenCode, Grok, etc.) into a self-coordinating team. Each agent gets memory, a mailbox, and a desk on a 2D office floor. A GOD agent (Michael) routes work while you watch. Pixi.js visualization with avatars walking between stations.

**Key architectural choices:**
- Terminal plane: real node-pty processes, byte-for-byte authentic
- Hive: per-agent memory, atomic-file mailboxes, shared blackboard, append-only event log
- Single-committer git design — avoids index.lock corruption
- Circuit breaker: steer → constrain → stop ladder for loops/storms/budget
- Durable cost ledger per agent with real token/cost from transcripts
- Semantic recall index with condensation (memory doesn't grow forever)

**What to adopt:**
- **Circuit breaker** — budget/turn cap enforced at harness level. If session exceeds N turns or $X cost, kill and log failure. Not yet implemented in our harness.
- **Durable cost ledger** — per-dispatch budget tracking. We have usage stats in `.claude.json` but no per-task cost caps.

**What we already do better:**
- Our dispatch pattern (`type TASK.md | claude -p`) is simpler and headless — no Electron needed
- Our memory is vector-indexed with annealing vs their flat markdown with condensation
- Our MEA (Manager-Executor-Auditor) loop is more structured than their GOD-agent-routes-everything pattern

## Specky — 58-Tool SDD MCP Toolkit

Source: https://github.com/paulasilvatech/specky

**What it is:** A CLI toolkit for Spec-Driven Development with 13 agents, 58 MCP tools, 22 prompts, 14 skills, and 16 hooks. Enforces a 10-phase pipeline from init to release with EARS notation validation, cross-artifact analysis, and compliance frameworks. Install via `npm install -g specky-sdd`.

**Key architectural choices:**
- Signed per-feature phase graphs (full, rapid, emergency execution modes)
- EARS validator — programmatic regex enforcement of 6 requirement patterns
- Cross-artifact analysis — automatic alignment checking spec↔design↔tasks
- Intent drift detection — constitutional principles vs downstream artifacts
- Use-case contracts — each feature declares lifecycle, workload, mode, capabilities
- 5 compliance frameworks (HIPAA, SOC2, GDPR, PCI-DSS, ISO 27001)
- MCP-to-MCP routing — outputs structured JSON for GitHub/Jira/Terraform/Figma MCPs

**What we adopted:**
- **EARS validator** — ported as `validate_ears` tool in our specs MCP server
- **Cross-artifact analysis** — ported as `cross_analyze` tool
- **Intent drift detection** — ported as `check_drift` tool

**What we already do better:**
- Our tool-router solves the 58-tool explosion they created — they present all tools raw
- Our memory + skill retrieval is more sophisticated (semantic vs static)
- Our cross-harness plugin works across 5 targets; they need `--target` per install
- Our spec_gate is simpler and equally effective (phase enforcement without signed graphs)
- Our failure-archaeology gate has no equivalent in their system

**What they have that we don't (and may not need):**
- 5 compliance frameworks (HIPAA/SOC2/GDPR/PCI-DSS/ISO 27001) — useful if you ever need regulatory validation
- Figma-to-spec conversion — design-first workflow
- Meeting transcript import (VTT/SRT) — requirements extraction from recordings
- Turnkey spec assembly — structured builder for EARS requirements

## Agentic Spec-Driven Development (Book)

Source: https://agentic-spec.com/ | https://books.google.com/books/about/Agentic_Spec_Driven_Development.html?id=HW7iEQAAQBAJ

**What it is:** A 12+ chapter book covering the full theory of spec-driven development for agentic systems. Chapters span: understanding ASDD, anatomy of specifications, designing for agents, context engineering, requirements engineering, writing specs that eliminate guesswork, architecting agent workflows, specification frameworks/templates, testing/validation, failure modes, security/governance, optimization/performance tuning, application patterns, and the future of ASDD.

**Key concepts (from ToC):**
- Specifications as executable artifacts, not documentation
- EARS notation as the requirement language
- Failure modes taxonomy: hidden assumptions, context fragmentation, late validation, misaligned expectations, validation gaps, objective drift, multi-agent conflicts
- Security governance with RBAC, specification-level access, audit trails
- Optimization: reducing cognitive load, caching strategies, feedback loops, execution time, scalable architectures
- Agentic applications: AI engineering, finance (RL + analytics), NLP, business process automation, healthcare, customer support, game development

**What to adopt:**
- The failure modes taxonomy (Ch10) maps directly to our failure-archaeology gate — could formalize the categories
- Security governance patterns (Ch11) for multi-agent dispatch — we trust Claude with `--dangerously-skip-permissions` which is the opposite of governance
- The optimization chapter's caching/feedback patterns could inform our tool-router's index

## addyosmani/agent-skills — Production-Grade Lifecycle Skills

Source: https://github.com/addyosmani/agent-skills

**What it is:** 24 skills (23 lifecycle + 1 meta) structured as workflows with verification gates and anti-rationalization tables. Covers the full dev lifecycle: Define → Plan → Build → Verify → Review → Ship. Each skill has steps, checkpoints, exit criteria, and a table of common excuses agents use to skip steps.

**Key architectural choices:**
- Skills are workflows, not reference docs — steps agents follow, not docs they read
- Anti-rationalization tables — counters to "I'll add tests later" type excuses
- Progressive disclosure — SKILL.md is entry point, references load on demand
- 8 slash commands mapping to lifecycle phases
- Agent personas (code-reviewer, test-engineer, security-auditor, web-performance-auditor)

**What we adopted (7 skills installed to ~/.skills/):**
- `interview-me` — requirements extraction via one-question-at-a-time interview
- `incremental-implementation` — thin vertical slices with feature flags
- `debugging-and-error-recovery` — five-step triage (reproduce, localize, reduce, fix, guard)
- `code-review-and-quality` — five-axis review with severity labels
- `security-and-hardening` — OWASP Top 10, secrets management, auth patterns
- `doubt-driven-development` — adversarial self-review (CLAIM→EXTRACT→DOUBT→RECONCILE→STOP)
- `context-engineering` — feeding agents the right information at the right time

**What we already do better:**
- Our retrieval auto-discovers and injects relevant skills vs their manual `/command` activation
- Our failure-archaeology gate is more rigorous than their debugging skill
- Our spec-driven-development steering is machine-enforced vs their skill being advisory

## christophacham/agent-skills-library — 2,600+ Skill Catalog

Source: https://github.com/christophacham/agent-skills-library

**What it is:** The largest open-source collection — 2,622 skills from 48 sources, organized into 34 categories. Bulk aggregation, not curated quality. Categories include: ai-ml (314), automation (806), backend-dev (162), game-dev (200), devops (160), design (149), database (137), security (119), git (105).

**What to adopt:**
- Cherry-pick from `finance` (3 skills), `data-science` (17), `security` (119) categories as needed
- Use as a discovery resource when looking for domain-specific skills

**What we already do better:**
- Quality over quantity — our 174 indexed skills are curated and retrieval-tested
- Our ColBERT reranking ensures only genuinely relevant skills activate vs their flat catalog

## jasonkneen/kiro — Kiro Community Tools

Source: https://github.com/jasonkneen/kiro

**What it is:** Community-maintained Kiro IDE extensions, tools, and configurations. Reference for Kiro-specific plugin patterns, steering file conventions, and MCP integration approaches.

**Relevance:** Reference for how the Kiro ecosystem structures extensions. Our `.kiro/steering/sdd-harness.md` follows these conventions.


## marcelsud/spec-driven-agentic-development — Lightweight SDD Slash Commands

Source: https://github.com/marcelsud/spec-driven-agentic-development

**What it is:** A minimal SDD methodology implemented as Claude Code slash commands. Two commands do the work: `/spec:create [feature]` generates a complete spec (context.md + requirements.md + tasks.md), and `/spec:execute [feature]` implements from the tasks. EARS-formatted requirements, TDD task breakdown. Install via `npx degit` into any project's `.claude/` folder.

**Key architectural choices:**
- Extremely minimal — 5 slash commands, 3 output files per feature, no MCP server
- Feature-scoped directory structure: `features/[name]/{context.md, requirements.md, tasks.md}`
- EARS notation for requirements (same as Specky, same as Kiro)
- Context + technical decisions separated from requirements
- TDD task breakdown as the implementation plan

**What's worth noting:**
- This is the **floor** of SDD — the minimum viable version. Two commands, three files. No enforcement, no memory, no retrieval, no cross-analysis. Pure discipline-based.
- The `features/` directory convention is clean — one folder per feature with all artifacts co-located. Simpler than Specky's `.specs/NNN-feature/` numbering.
- The separation of `context.md` (why + constraints + decisions) from `requirements.md` (what) from `tasks.md` (how) is the same three-layer decomposition our specs MCP uses (requirements → decisions → tasks).

**What we already do better:**
- Machine enforcement (spec_gate denies writes without approved spec) vs their discipline-only approach
- Cross-session memory and continuity vs their stateless slash commands
- Semantic skill retrieval vs nothing
- Cross-artifact analysis and drift detection vs nothing
- Multi-harness portability vs Claude Code only

**What to adopt:** Nothing mechanically — but the simplicity is instructive. A new user could adopt SDD with just these 5 commands and graduate to our full harness when they hit the limits of discipline-only enforcement. Could inform an "SDD lite" onboarding mode.


## Spec Kit Agents — Context-Grounded Agentic Workflows (arXiv:2604.05278)

Source: https://arxiv.org/html/2604.05278v1 | https://github.com/marcelsud/spec-driven-agentic-development

**What it is:** An academic paper (Taghavi & Bhavani, Apr 2026) presenting a multi-agent SDD pipeline that adds **phase-level context-grounding hooks** to Spec Kit. PM and developer roles, state-machine orchestrator, with read-only discovery hooks and post-phase validation hooks. Evaluated on 128 runs across 32 features in 5 repos (FastAPI, Airflow, Dexter, Plausible, Strapi). Achieves 58.2% Pass@1 on SWE-bench Lite with MiniMax-M2.5.

**Key findings:**
- Context-grounding hooks improve judged quality by **+0.15** on 1-5 composite score (p<0.05)
- 99.7-100% repository-level test compatibility maintained
- Validation hooks (+1.71%) outperform discovery hooks (+0.57%) individually; combined is best (+4.27%)
- Overhead: +1.1 min for simple workflows, +13.2 min for full workflows
- The problem they solve: **context blindness** — agents produce internally coherent but repository-incompatible artifacts (hallucinated APIs, wrong file paths, architectural violations)

**Key architectural choices:**
- **Discovery hooks** (pre-phase): read-only probing before each stage — glob, grep, git history — to collect repository evidence. Grounds generation in concrete local context rather than generic priors.
- **Validation hooks** (post-phase): check intermediate artifacts for structural/referential consistency. File paths exist? Libraries present? Task list feasible? After implementation: run tests + linters.
- **Tool access control**: PM restricted to read-only analysis. Developer can edit + execute. Discovery hooks read-only. Validation hooks get execution privileges.
- **Separation of generation from evaluation**: different models for work vs judging (avoids self-evaluation bias)
- **State machine orchestrator**: Specify → Plan → Tasks → Implement with explicit phase gates

**What maps to our harness:**

| Their concept | Our equivalent | Gap? |
|---------------|---------------|------|
| Discovery hooks (pre-phase grounding) | `retrieve_skills` + `search_memory` at session start | We ground in skills/memory but don't probe the repo structure per-phase |
| Validation hooks (post-phase) | `spec_gate` PreToolUse + verify at Stop | We gate before writes but don't validate intermediate artifacts |
| PM agent (requirements) | Kiro as Manager | Same role |
| Developer agent (implementation) | Claude as Executor | Same role |
| State machine orchestrator | specs MCP phase tracking | Same pattern |
| Context blindness problem | Our failure-archaeology gate catches this retroactively | They prevent it; we detect and recover |

**What to adopt:**
- **Pre-phase repository probing** — before each spec/design/task phase, automatically glob + grep the repo for relevant files, conventions, existing APIs. Inject as context. This is the biggest delta vs what we do now. Our agents often hallucinate paths because they don't probe first.
- **Intermediate artifact validation** — after writing a spec, validate that referenced files/modules actually exist before moving to implementation. Our spec_gate only checks phase, not content validity.
- **The +0.15 quality lift is modest but real** — and it comes from preventing compounding errors. Each phase that starts grounded propagates less drift downstream. This validates our "spec first" philosophy with hard numbers.

**What we already do better:**
- Our memory layer provides cross-session grounding (they have none — each run is fresh)
- Our failure-archaeology gate recovers from context blindness after the fact; theirs prevents it but has no recovery mechanism
- Our tool-router consolidates tool explosion; they use raw tool access
- Our dispatch pattern allows real parallelism across repos; theirs is single-feature sequential
- Our skill retrieval is semantic; their discovery hooks are regex/glob (structural, not semantic)

**Key insight:** The paper provides empirical evidence that our spec-first methodology works — **explicit intermediate artifacts + validation hooks = fewer compounding errors**. The gap in our system is the pre-phase repository probing. Adding a `codebase_map.py` UserPromptSubmit hook that probes repo structure before work begins would close this gap. We partially have this (`codebase_map.py` exists in hooks/) but it's not phase-scoped — it runs once at prompt time, not at each phase transition.


## Agent-S: LLM Agentic Workflow to Automate Standard Operating Procedures (arXiv:2503.15520)

Source: https://arxiv.org/html/2503.15520v1

**What it is:** A paper proposing an LLM-based agentic workflow for automating Standard Operating Procedures (SOPs). SOPs are logical step-by-step processes — each step is either a user interaction or an API call, with the logical flow defining navigation. Architecture: three task-specific LLMs + Global Action Repository (GAR) + execution memory + multiple environments (API tools, user interface, external knowledge source).

**Key architectural choices:**
- SOPs written as **simple logical blocks of text** — the procedure IS the prompt
- Agent chooses action based on current execution memory + SOP definition
- Two step types: **user interaction** (ask/interpret/collect) and **status check** (API call + decision)
- **Fault-tolerant**: dynamically decides to repeat an action or seek input from external knowledge
- **Global Action Repository (GAR)**: pre-defined actions the agent can invoke (same as our tool registry)
- Execution memory accumulates observations and feedback to decide next action

**The connection to our harness:**
- Your **data-science-skills** corpus and **retrieve-skills** system are SOPs. Each skill IS a standard operating procedure for a domain task — "here's how you do XGBoost hyperparameter tuning" or "here's how you run a ColBERT retrieval pipeline." The agent retrieves the relevant SOP and follows it.
- Your **steering rules** (operating-rules, debugging, feature-lifecycle, etc.) are SOPs for *how to behave* — they define the step-by-step logical flow the agent should follow for debugging, for feature development, for failure recovery.
- The **discovery hooks** from the Spec Kit Agents paper are SOPs for *how to ground* — probe the repo before each phase.
- The **skeleton/codemap** idea is the repository's SOP — "here are the conventions, the APIs, the structure. Follow these, don't invent new ones."

**Key insight for us:** Everything in the harness is SOPs at different scales:

| Layer | SOP type | Example |
|-------|----------|---------|
| Behavioral | How to think/act | steering rules, constitution |
| Procedural | How to do a task | skills (spec-driven-development, debugging, etc.) |
| Domain | How a technique works | data-science-skills corpus |
| Structural | What exists in the repo | skeleton.md, codebase_map |
| Policy | What's allowed/blocked | spec_gate, security_scan |

The paper validates that **encoding procedures as retrievable text + giving agents memory + fault tolerance = reliable automation of multi-step workflows**. That's our entire architecture restated as a formal contribution.

**What to adopt:**
- The **fault-tolerance pattern** (repeat action or seek external knowledge on failure) maps to our failure-archaeology gate — but theirs is more granular (per-step retry vs our per-session recovery). A per-step retry hook could catch errors earlier.
- The **GAR (Global Action Repository)** concept validates our tool-router design — a registry of all available actions the agent can invoke, retrieved by context.

**What we already do better:**
- Our skills are semantically retrieved (ColBERT) vs their SOPs being statically selected by intent classification
- Our memory has annealing lifecycle vs their flat execution memory
- Our multi-harness portability vs their single-environment (customer care only)
- Our failure-archaeology does root-cause analysis vs their simple retry logic


## Code Skeleton as Structural SOP — Compressed Codebase Representation

Source: Original idea, inspired by code2prompt + Spec Kit Agents discovery hooks + Agent-S GAR pattern

**What it is:** A single-file compressed representation of a codebase containing only: constants, class/function headers, docstrings, and a UML class diagram. No implementation bodies. Serves as a quick index for refactoring, a pre-phase grounding artifact, and a structural SOP ("here's what exists — don't reinvent it").

**Why it matters:**
- Prevents context blindness (the core failure mode from arXiv:2604.05278) by giving agents the full API surface before they start working
- Acts as the **structural SOP layer** — "these are the conventions, APIs, and patterns. Follow them."
- Fits in a single context window where full source code wouldn't
- Enables refactoring without reading every function body
- Pairs with the UML class diagram for relationship navigation

**Implementation:** `skeleton_gen.py` — walks a repo, extracts signatures + docstrings + constants via AST, generates Mermaid class diagram from imports/inheritance, outputs `SKELETON.md`. Available as a tool in the specs MCP server and as a standalone script.

**Relationship to other patterns:**
- Discovery hooks (Spec Kit Agents) → skeleton IS the discovery output, precomputed
- GAR (Agent-S) → the skeleton is the "repository of existing APIs/functions" the agent can invoke
- codebase_map.py hook → skeleton is the deeper version (tree + signatures vs tree only)
- data-science-skills corpus → domain SOPs; skeleton is the project-specific structural SOP