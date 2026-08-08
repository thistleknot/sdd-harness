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
