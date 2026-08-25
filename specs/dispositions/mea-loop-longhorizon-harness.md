<!-- GENERATED — DO NOT EDIT — source: specs/specs.db -->
# MEA Loop: Manage-Execute-Audit for Long-Horizon Agent Execution

**Slug:** `mea-loop-longhorizon-harness`
**Tags:** orchestration,verification,long-horizon,paper-extraction
**Created:** 2026-08-15T04:19:13+00:00

---

## Source
arXiv:2608.01964 — Ziyu Ma et al. (2026-08-03)

## Core Insight
Long-horizon execution fails because growing context makes task state hard to track and incorrect self-assessments propagate into later decisions. The fix: externalize task state, update it only with independently verified facts, and use fresh-context executors so errors don't compound.

## The MEA Loop (Manage-Execute-Audit)

```
┌──────────────────────────────────────────────────────┐
│                    MANAGER                            │
│  Maintains explicit task state (outside execution)   │
│  Determines next subtask from verified state only    │
└──────────────────────┬───────────────────────────────┘
                       │ subtask spec
                       ▼
┌──────────────────────────────────────────────────────┐
│                    EXECUTOR                           │
│  Fresh context (no accumulated conversation)         │
│  Performs one subtask, returns raw outcome            │
└──────────────────────┬───────────────────────────────┘
                       │ raw result
                       ▼
┌──────────────────────────────────────────────────────┐
│                    AUDITOR                            │
│  Read-only environment inspection                    │
│  Verifies actual state vs claimed state              │
│  Only verified facts update the task state           │
└──────────────────────────────────────────────────────┘
```

## Results
- Qwen 3.7-Plus: 51.8% → 80.7% on WeaveBench (+28.9pp)
- Same model: 69.7% → 77.2% on Terminal-Bench 2.1
- Claude Opus 4.7: 20.0% → 34.3% on OSWorld 2.0 subset
- Consistent gains across models, harnesses, and domains

## What This Maps To In Our System

**We already have the skeleton:**
- Manager = primary agent (decision layer per orchestration rules)
- Executor = sub-agents (context-gatherer, general-task-execution)
- Auditor = ??? (this is what's MISSING)

**The gap is the Auditor.** We dispatch sub-agents and trust their self-report. The MEA insight is: verify the environment state independently before updating your task state. The cartographer `/wrapup` digest-first pattern is the same idea applied to session synthesis.

## Implementation Options

### Option A: PostTaskExec verification hook
A hook that fires after each spec task completion, reads the actual file/test state, and compares to what was claimed. Blocks task transition if the environment contradicts the claim.

### Option B: Auditor sub-agent pattern
After a sub-agent returns, dispatch a second (cheap, read-only) sub-agent that:
1. Reads the files the first agent claimed to modify
2. Runs the tests the first agent claimed pass
3. Returns a verified/unverified verdict
4. Only on "verified" does the task state advance

### Option C: Fresh-context executor mandate
Instead of long-running sub-agents that accumulate context, enforce that each subtask gets a fresh dispatch. This is already partially true (sub-agents are one-shot) but we could enforce it structurally by splitting multi-step sub-agent work into multiple dispatches.

## Key Design Principle

> Task state must be updated ONLY with facts independently verified from the environment.

This is the anti-confabulation principle applied to task tracking, not just memory. Our specs system already externalizes task state — but we update it on self-report ("I did X"), not on verified environment state ("the file now contains X and the test passes").

## The AgentAdapter Pattern

Their AgentAdapter wraps any model/harness backend without modifying native agent loops. This is the same shape as our `adapter.py` — a thin shim that lets the orchestration layer work with different backends. Validates our architecture.

## What We Should Build

1. A `PostTaskExec` hook that runs verification (option A) — cheapest, most immediate
2. Over time, evolve toward option B (auditor sub-agent) for high-stakes tasks
3. The fresh-context principle is already in our sub-agent design — document it as intentional
