<!-- GENERATED — DO NOT EDIT — source: specs/specs.db -->
# NapMem: Active Memory Navigation as Structured Action Space

**Slug:** `napmem-active-memory-navigation`
**Tags:** memory,navigation,multi-granularity,rl,paper-extraction
**Created:** 2026-08-15T04:20:30+00:00

---

## Source
arXiv:2607.05794 — Yue Xu et al. (2026-07-07)

## Core Insight
Memory should be a **structured action space** the agent navigates, not a passive retrieval interface where pre-selected evidence is handed to the model. The agent learns WHEN to inspect which granularity — inspecting raw conversations vs typed records vs topic tracks vs user profiles — before answering.

## NapMem Architecture: Multi-Granularity Memory Pyramid

```
┌─────────────────────────────────────────┐
│          USER PROFILE (coarsest)         │  ← standing preferences, patterns
├─────────────────────────────────────────┤
│          TOPIC TRACKS                    │  ← threads of related work
├─────────────────────────────────────────┤
│          TYPED MEMORY RECORDS            │  ← decisions, facts, procedures
├─────────────────────────────────────────┤
│          RAW CONVERSATIONS (finest)      │  ← verbatim session transcripts
└─────────────────────────────────────────┘
    Connected via provenance relations (child → parent links)
```

Each level is exposed as a **memory tool**. The agent is trained (via RL on memory-tool use) to select the right granularity per query.

## Key Results
- Competitive across PersonaMem-v2, LongMemEval, LoCoMo (diverse memory-intensive tasks)
- Memory-tool RL preserves general reasoning and tool-use abilities
- The learned policy navigates up/down the pyramid based on query type

## Mapping to Our Existing Stack

| NapMem Layer | Our Equivalent | Gap |
|---|---|---|
| Raw conversations | `append_volley` / `get_hot_window` / `get_project_history` | ✓ exists |
| Typed memory records | `log_memory` / `search_memory` (Chroma) | ✓ exists |
| Topic tracks | **MISSING** — no thread-level grouping | needs work |
| User profile | `~/.harness/constitution.md` + steering rules | partial (static, not derived) |
| Provenance relations | **MISSING** — no links between layers | needs work |
| Learned navigation policy | **MISSING** — we use rules in steering, not learned routing | biggest gap |

## What This Means For Our Memory Skills Plan

The existing MEMORY_SKILLS_PLAN already has:
- `cognitive-taxonomy` — classification system (maps to NapMem's typed records)
- `procedural-memory` — SK-Gen pipeline (maps to NapMem's topic tracks for procedures)
- `memory-architecture` — layered stack (same shape as the pyramid)

**What NapMem ADDS that the plan doesn't have:**

### 1. Memory Tools as Actions (not just retrieval)
Current: `search_memory(query)` → get results passively
NapMem: agent CHOOSES which tool to call based on query analysis:
- `inspect_profile()` — "what's my usual deploy process?" → profile level
- `inspect_track(topic)` — "what happened with the auth refactor?" → topic level
- `inspect_record(id)` — "what was the exact decision about caching?" → record level
- `inspect_conversation(session_id)` — "what did we discuss yesterday?" → raw level

### 2. Provenance Links Between Layers
A typed record should link DOWN to the conversation turn that produced it, and UP to the topic track it belongs to. This enables navigation: find a record, then drill into the source conversation for full context, or zoom out to the topic for related decisions.

### 3. The Navigation Policy (RL-trained vs rule-based)
NapMem trains the policy with RL. We can approximate with rules initially:
- Standing/preference questions → profile first
- "What happened with X" → topic track first
- Specific factual recall → typed records (search_memory)
- "Show me the exact conversation" → raw volleys
- If first level insufficient → navigate to adjacent granularity via provenance links

## Concrete Changes to Build

### A. Add topic_track grouping to memory-index
Group related memory entries by topic/project/thread. A topic track is a set of memory entries + volleys that share a common theme. Could be as simple as a `track_id` column on memory entries, auto-assigned by semantic clustering.

### B. Add provenance_id to memory entries
Each `log_memory` call should optionally carry a `source_volley_id` pointing to the conversation turn that produced it. Each promoted entry should carry the `log_id` it was promoted from.

### C. Expose granularity-specific memory tools
Instead of one `search_memory`, expose:
- `search_memory` (unchanged — searches typed records, the default)
- `recall_track(topic)` — returns all entries in a topic cluster
- `recall_context(memory_id)` — returns the source conversation around a memory entry
- `get_standing_profile()` — returns the derived profile summary

### D. Navigation heuristic in the memory-and-tools steering rule
Update the "Memory (memory-index, port 8055) → Reading" section to specify granularity routing:
- Task starts: search typed records first (cheap, structured)
- If insufficient: check topic tracks for related threads
- If still unclear: fall back to raw conversation history
- Standing questions go straight to profile

## Relationship to Session-Cartographer

Session-cartographer's `/remember` (search events) + `/focus` (project orientation) + profile.md is essentially the same pyramid:
- profile.md = user profile layer
- `/focus` co-occurrence graph = topic tracks
- `/remember` event search = typed records
- transcripts = raw conversations

The difference: session-cartographer is bash+awk external tooling. NapMem's insight is that this should be MODEL-INTERNAL decision-making trained via RL, not external routing logic.
