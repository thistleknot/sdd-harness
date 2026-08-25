<!--
SUPERSEDED 2026-08-24. Historical record, not live doctrine. Do not load as policy.

Archived verbatim from claude/AGENTS.md lines 1-53 (dated 2026-07-29) during the
slop-review cleanup, before -Pull replaced that file with the reduced Operating
Contract.

Why it is not live:
  * Names three agents that do not exist in either tree: opus_coder,
    opus_architect, haiku_worker. The real ladder is opus_planner ->
    sonnet_critic -> opus_fixer_low -> opus_fixer_med.
  * Describes a superseded pipeline (Opus spec -> Haiku impl -> Sonnet verify)
    that contradicts the four-gate ladder in rules/orchestration.md.
  * Hardcodes Claude model IDs, so it cannot travel to the pi / opencode /
    hermes / codex / gemini harnesses the plugin targets.

Its surviving idea -- role -> capability-tier routing -- belongs in a
harness-agnostic profile artifact, with per-harness model bindings.
-->

﻿# Multi-Model Agent Registry

## Model Tiers & Cost Profiles

| Agent | Model ID | Cost Profile | Role |
|-------|----------|-------------|------|
| Sonnet 5 (you) | `claude-sonnet-5` | Medium | Orchestrator + Critic (verify vs spec, fault attribution, first-pass QA) |
| `opus_coder` | `claude-opus-4-8` | High | Spec author: plan → spec (incl. pseudocode), OOP defs; spec repair + root cause on escalated failures |
| `opus_architect` | `claude-fable-5` | Highest | Refactor specs of undetermined scope only |
| `haiku_worker` | `claude-haiku-4-5-20251001` | Low | Implementer: code from pseudocode; read, transcribe, rote, enumerated edits |

> Pipeline: `Opus spec → Haiku impl → Sonnet verify`. Haiku is back — not as a
> cost-saver, but as the rote executor whose quality risk is bounded by Opus's
> pseudocode and Sonnet's spec-cited verification.

## Capability Map

### Sonnet 5 — Orchestrator + Critic
- Routes tasks into the pipeline; decides who specs (Opus vs Fable vs own enumeration)
- Verifies Haiku output against the governing spec — every verdict cites a spec clause
- Fault attribution: haiku-fault → bounce down (≤2, spec-cited); spec-fault or ceiling → bounce up to Opus
- First-pass QA: runs tests/validation before declaring success
- Manages context health (compaction, clearing)
- Does NOT implement, except trivial mechanical one-liners; does NOT silently fix Haiku output

### Opus 4.8 — Spec Author (`opus_coder`)
- Plan → spec: requirements, acceptance criteria, pseudocode precise enough for rote implementation
- Translates specs to OOP definitions: classes, method signatures, contracts (Require/Guarantee/Maintain/Assert)
- Escalated failures only: spec repair and root-cause diagnosis when Sonnet attributes spec-fault or the Haiku retry ceiling is hit
- Does not implement final code — Haiku does; does not take undetermined-scope work — Fable does

### Fable 5 — Refactor Architect (`opus_architect`)
- Refactor specs where scope is undetermined: system-wide changes, multi-module blast radius
- Scope decomposition that Opus then turns into per-module specs
- Terminal escalation: task still failing after an Opus spec repair means the scope was misjudged
- Writes to `docs/decisions/` or structured response

### Haiku 4.5 — Implementer (`haiku_worker`)
- Implements code from Opus pseudocode / OOP defs — faithful translation, no design decisions
- Read, transcribe, rote work, enumerated edit lists
- On ambiguity in the spec: stop and report the gap; never improvise a design choice

## Routing Rules (Summary)

1. **Spec-worthy work** → `opus_coder` writes the spec (incl. pseudocode) → `haiku_worker` implements → Sonnet verifies
2. **Enumerable-but-trivial edits** → Sonnet enumerates the edit list → `haiku_worker` executes
3. **Trivial mechanical one-liner** → Sonnet does it directly
4. **Verification fails, impl deviates from spec (haiku-fault)** → bounce to `haiku_worker` with spec clause cited, retry ceiling = 2
5. **Verification fails, spec is wrong/ambiguous (spec-fault), or ceiling hit** → `opus_coder` repairs the spec + root cause, pipeline re-enters at Haiku
6. **Undetermined scope / system-wide refactor, or failure survives an Opus spec repair** → `opus_architect` delivers the refactor/scope spec first

Full routing decision tree: `.claude/rules/orchestration.md`

