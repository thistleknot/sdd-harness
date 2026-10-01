# Evaluating Google ADK `BaseMemoryService` for the memory-index lane

**Task #7 (deferred → resolved). Verdict: REJECT as a backend. ADOPT as an outbound adapter only.**

> **Scope correction (operator, 2026-08-05).** Task #7 was titled "...for the KG memory
> lane", and this document originally treated the knowledge graph as part of the
> memory-index lane. **It is not — the KG is a separate project.** This evaluation covers
> ADK against **memory-index only**. Nothing here is a finding about the KG, and §4 does
> not prescribe anything for it. The verdict is unaffected: the graph objection was one of
> seven, and the other six are independently disqualifying.

Ground truth: `google-adk` **1.21.0**, installed locally at
`C:\Users\user\py310\lib\site-packages\google\adk\memory`. Interface read from source,
not from docs.

---

## 1. The interface, in full

`base_memory_service.py` — the ABC has exactly **two** abstract methods:

```python
async def add_session_to_memory(self, session: Session)
async def search_memory(self, *, app_name: str, user_id: str, query: str)
      -> SearchMemoryResponse          # .memories: list[MemoryEntry]
```

`MemoryEntry` = `content: types.Content`, `custom_metadata: dict`, `id`, `author`,
`timestamp`.

That is the entire surface. Three implementations ship:

| impl | storage | notes |
|---|---|---|
| `InMemoryMemoryService` | process dict | self-described "**prototyping purpose only**", keyword matching, non-persistent |
| `VertexAiMemoryBankService` | Vertex Agent Engine | needs `project`/`location`/`agent_engine_id`; server-side LLM distillation |
| `VertexAiRagMemoryService` | Vertex RAG corpus | chunked doc retrieval over `ragCorpora` |

## 2. Why it cannot back our lane

The mismatches are not ergonomic, they are structural. Ranked by severity:

**(a) `search_memory` returns no relevance score, and takes no `top_k`.**
This alone is disqualifying. `mem.py:cmd_search` computes `score = 1.0 - dist` and gates
hit-counting on `score >= HIT_MIN_SCORE`. The entire durability ladder — log bit
--3 retrievals--> durable memory --3 retrievals--> SKILL.md — is driven by that threshold.
An ADK-backed search returns an unranked, unscored, unbounded list. **The ladder cannot be
computed from it.** Our central mechanism dies at the interface boundary.

**(b) No update, no delete.** Append + search only. But the ladder requires
`col.update(ids=..., metadatas=...)` to bump `hits`, and `cmd_anneal` requires eviction of
under-recalled entries. Neither is expressible. `mem anneal` becomes unimplementable.

**(c) No filters.** `cmd_search` passes `where={"type": type_filter}`. There is no filter
parameter anywhere in the ADK signature.

**(d) Its retrieval unit is a flat string.** `VertexAiMemoryBankService.search_memory`
unwraps `retrieved_memory.memory.fact` — a **flat string**. The RAG service returns text
chunks. Neither implementation carries structure of any kind: no fields, no typed records,
no relations. This is a weak objection *for memory-index*, which is itself chunk-shaped and
would not miss the structure. Recorded for completeness, not load-bearing — (a), (b), (c),
(e), (f), (g) are each sufficient on their own.

*(This subsection previously argued ADK "is not a knowledge graph" and treated that as the
punchline. That reasoning was scoped to the wrong project and has been withdrawn.)*

**(e) Ingest unit mismatch.** ADK ingests `Session` (app_name, user_id, id, events). Our
unit is a chunked markdown memory with frontmatter (`type`, `scope`, `hits`,
`promoted_to_skill`, `supersedes`) and `[[wikilink]]` edges. Encoding that as a Session is
possible but dishonest — the metadata survives only as opaque `custom_metadata`, unqueryable
per (c).

**(f) It duplicates `mem dream`, with different policy.** `memories.generate` performs
server-side LLM distillation. We already distill locally via the `claude` CLI, and we made a
deliberate, documented decision that distilled memories are live immediately and earn
durability by retrieval. Vertex's distiller has its own opinions we do not control. Two
distillers, two policies, one store.

**(g) Cloud dependency.** Network round-trip, GCP project, and per-call cost on the
UserPromptSubmit hot path — where we currently do a local Chroma query. Also a hard
availability coupling for a hook that must never block a prompt.

## 3. What is worth taking

One thing, and it's cheap: **invert the direction.** Rather than putting ADK underneath
memory-index, implement `BaseMemoryService` as a thin read-mostly *adapter over* memory-index,
so any future ADK-based agent can query our store.

This is safe precisely because the adapter is **read-only and does not count hits** — it
cannot corrupt the ladder by injecting retrievals that no agent actually used. Scores are
dropped at the boundary (unavoidable, per (a)), but they were never the caller's to see.

Feasibility confirmed — see `adk_memory_adapter.py`, which satisfies the ABC and instantiates
cleanly against ADK 1.21.0.

## 4. Recommendation

- **Do not** adopt `BaseMemoryService` as the memory-index backend. Keep Chroma +
  `events.sqlite3`.
- **Do not** adopt `VertexAiMemoryBankService`; it conflicts with `mem dream` by design.
- Keep the adapter as an export seam only if/when an ADK agent needs our memories.
- **Nothing here applies to the KG.** That is a separate project and was not evaluated. If
  someone wants ADK assessed against it, that is a distinct task with distinct requirements.

## 5. Caveat on scope

There is **no written KG-lane design** anywhere in `plans/` or `memory-index/` — greps for
`knowledge graph|entity|relation|triple|edge` return nothing but the one `meta-knowledge-graph`
reference. So this evaluation answers "is ADK a fit for a graph memory lane?" (no) but it
cannot check ADK against requirements that were never recorded. If the KG lane has
requirements living outside these trees, this verdict should be re-tested against them.
