# Harvested capabilities

**Disposition: read-only inventory.** The active status and work belong in [`features-todo.md`](../features-todo.md), with governed task state in the Specs DB and kanban. Current result (2026-10-21): the no-model skill package validator, fail-closed retrieval evaluation, agent-render assertions, manifest integrity checks, and a read-only MCP/skill/hook/plugin capability report are shipped. The report checks declared projections and artifact presence; it does not certify live behavior in every harness. Changing this inventory requires new source or implementation evidence.

## Current system shape

`~/.harness` is the shared cross-harness control plane. `manifest.toml` describes capability projection, `harness.json` owns shared MCP and hook registrations, `adapter.py` projects them, `render_agents.py` renders the party, `~/.skills` is the separate reusable skill corpus, `~/.mcp` holds server projects, `~/.rules` holds shared operating policy, and repository `hooks/` plus harness-native hook configuration enforce lifecycle behavior. `plan.md` is already read-only and board-rendered. The new inventory does not replace these sources.

## Source-by-source observations and disposition

### Agency agents

*Source:* [msitarzewski/agency-agents](https://github.com/msitarzewski/agency-agents). The roster groups specialists by work domain; each prompt emphasizes a distinct role, process, and deliverable. Integrations map agents into native formats across many coding harnesses.

*Incumbent:* `agents/`, `render_agents.py`, `party.py`, provider templates, `manifest.toml`.

*Disposition:* adopt the audit criteria (role boundary, outputs, cross-harness instruction preservation); reject wholesale roster import and a second installer. The same capability-rendering problem is already solved locally.

### wshobson agents

*Source:* [wshobson/agents](https://github.com/wshobson/agents). The project combines plugins, agents, skills, commands, hooks, and MCP setup; it adapts shared Markdown sources to Claude Code, Codex, Cursor, OpenCode, Copilot, Antigravity, and Pi. Its `plugin-eval` offers deterministic quick scoring and optional semantic judging; a content-hash snapshot catches scoring drift and stale coverage ([workflow](https://github.com/wshobson/agents/blob/main/plugins/plugin-eval/commands/eval.md), [snapshot](https://github.com/wshobson/agents/blob/main/evals/README.md)).

*Incumbent:* `plugin/`, `manifest.toml`, `adapter.py`, `render_agents.py`, `conformance/`, and `eval/`.

*Disposition:* retain local projection architecture. We implemented a read-only package check in `scripts/validate_skills.py`: YAML `name`/`description`, directory/name agreement, and prose-relative Markdown references. Five synthetic tests cover valid and invalid exits, malformed metadata, missing links, and fenced example links; all 198 current immediate skills pass. This validates structure/portability, not semantic quality.

### Anthropic knowledge-work plugins

*Source:* [anthropics/knowledge-work-plugins](https://github.com/anthropics/knowledge-work-plugins). Job-centered bundles contain guidance, skills, connectors, commands, and subagents; teams customize terminology, tool access, and process.

*Incumbent:* `plugin/`, `harness.json`, `mcp/`, `agents/`, `~/.skills`, and `manifest.toml` already own those component types separately.

*Disposition:* keep the separate canonical stores. Manifest tests reject undeclared harnesses, duplicate artifact/harness cells, unsupported strategies, and SKIP rows without reasons. `scripts/capability_drift.py` now reports MCP registrations, adapter targets, skill targets, global hook wiring, and plugin metadata/skill artifacts in read-only mode. It does not open credential files or claim full live harness parity.

### Anthropic Claude quickstarts

*Source:* [anthropics/claude-quickstarts](https://github.com/anthropics/claude-quickstarts). The repository provides application examples, including support and finance agents, managed agents, browser automation, and computer-use tooling. Its computer-use reference highlights explicit tool contracts, bounded image context, prompt caching, compaction, batching, sandboxing, and trajectory records.

*Incumbent:* MCP servers and registry, security rules/hooks, session continuity, tool routing, and harness evaluations cover adjacent concerns.

*Disposition:* no code adopted. These examples target Claude API applications, not the shared coding-agent control plane. The local board declares tool inputs/refusals, worktrees isolate changes, and board events retain trajectory evidence; computer-use image/cache practices do not fit this workload.

### Addy Osmani agent skills

*Source:* [addyosmani/agent-skills](https://github.com/addyosmani/agent-skills). Skills and commands cover define, plan, build, test, review, and ship stages; integrations translate packages to native harness formats. Its evaluation cases specify at least three positive triggers, two negative triggers, and one behavioral case ([eval guidance](https://github.com/addyosmani/agent-skills/blob/main/evals/README.md)). Setup documentation identifies a portability issue where single-skill installation can omit companion references.

*Incumbent:* `~/.rules`, `~/.skills`, `.specs/`, repository hooks, `plugin/`, adapters, and conformance tests already cover the lifecycle and distribution.

*Disposition:* do not duplicate lifecycle skills. Local reference integrity is covered by the validator. `~/.skills/retrieve-skills/test_retrieval.py` now requires each expected positive skill, rejects forbidden negative skills, checks selected instruction files are readable, and uses isolated session IDs so canaries do not suppress one another. The live seven-case canary passed after this correction.

## Generalized reusable feature set

1. **Canonical capability -> harness projections.** Each role, skill, hook, command, or tool keeps one canonical owner and declares native projections/unsupported cells. Mostly present; audit for drift instead of designing a parallel marketplace.
2. **Contract-rich roles.** Agent definitions name when to use the role, what it does, expected deliverables, and review/verification boundary. Roster exists; test these properties across rendered outputs.
3. **Portable skill packages.** Skill dependencies and local reference files resolve after supported installation/projection routes. Not yet verified; test before expanding the skill catalog.
4. **Static quality gates.** Validate frontmatter, triggers, links/references, size, and artifact shape without model calls. Package shape, references, strict positive/negative retrieval triggers, and a deterministic selected-skill handoff check are covered.
5. **Bundle dependency/parity report.** Cross-check MCP entries, skill targets, hooks, plugin artifacts, and adapter availability while each source of truth remains in its current registry. The read-only first-pass report is implemented; complete native behavior parity remains outside its claim.
6. **Lifecycle safety examples.** Use Claude quickstarts as evidence for tool contracts, sandboxing, context limits, and trajectory recording only where the current cross-harness evaluation lacks that property. Not adopted as a package.

## Evidence and limits

This first pass used upstream README and repository-tree evidence, dated 2026-10-21; public evaluation instructions were inspected for two sources. It mapped advertised features to local incumbents and verified the first implementation tranche. It does not claim upstream implementations were independently tested or certify all live harness behavior.
