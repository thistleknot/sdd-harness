# Historical status: memory and harness integration, 2026-10-25

SUPERSEDED 2026-11-02: the following status was current before the scoped skill-projection contract was added. It remains historical evidence; current disposition is at the top of `../memory-and-harness-integration.md`.

CURRENT 2026-10-26: merged the SKILL2 lifecycle review into agent-long-term-memory (R14 admission rule, global-question stratum). Added R19-R21 (caller-contract parity, local-recall scope, dream auto-approval off) and the OPEN list; next work item is the first gate run on Claude's vector-only recall. Status below is unchanged from 2026-10-25.

CURRENT 2026-10-25: memory and autoresearch implementation is live. `mem-server` now
serves `~/memory-bank/conversations.sqlite3`; health reports 130 records and dense
retrieval off. MCP initialize/tool-list succeeds with 14 tools, and a scoped
`search_memory` call returns the expected no-match without error. The focused
memory/RSI suite passes 17/17 and selected skill export has zero drift. OpenCode model
validation remains a separate next stage. Canonical skill packages remain in ~/.skills;
~/.harness owns deployment and policy.
