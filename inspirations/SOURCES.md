# Source registry

Every row: an immutable SOURCE, its curated extract (if one exists), and status.
`VERIFIED` = path confirmed on disk. `UNVERIFIED` = attribution not yet traced
to an upstream original; do not cite it as settled.

Raw capture root: `~/Documents/wiki/`
Golden-source archive: `~/.skills/integrated/` (est. commit `7925d67`, 2026-05-17,
"Consolidate integrate/ into integrated/ as single golden-source archive", 28 files)

| # | Inspiration | Immutable source | Curated extract | Status |
|---|---|---|---|---|
| 1 | **Delete your CLAUDE.md** — Charlie Hills, 2026-08-09 | `~/Documents/wiki/data science/llm/Delete your CLAUDE-md.md` (+ `.pdf` `.json` `.csv` `_methods.md` `_table_crops/`) | not yet archived | VERIFIED |
| 2 | **llm-wiki** (Karpathy) | *no upstream found in `~/Documents/wiki`* | `~/.skills/integrated/llm-wiki.md`, `llm-wiki.txt`, `llm-wiki-pattern-topology.md` | UNVERIFIED upstream |
| 3 | **llm-wiki v2 / GBrain** | `~/Documents/wiki/data science/llm/RAG, LLM Wiki, or Gbrain-  How Your Agent Remembers Changes Everything.md` (+ `.pdf` `.json` `.csv`); also `RAG LLM Wiki or GBrain.*` | `~/.skills/integrated/` (both titles) | VERIFIED |
| 4 | **gstack** — Garry Tan, MIT | *no upstream found in `~/Documents/wiki`* | `~/.skills/integrated/gstack.md` (header cites `garrytan/gstack`) | UNVERIFIED upstream |
| 5 | **Meta Knowledge Graphs / Context Graphs** — Firat Tekiner | `~/Documents/wiki/data science/llm/Meta Knowledge Graphs Context Graphs.md` (+ `.pdf` `.csv`) | `~/.skills/integrated/Meta_Knowledge_Graphs_Context_Graphs.md` | VERIFIED |
| 6 | **The Five Levels: from Spicy Autocomplete to the Dark Factory** — Dan Shapiro | `~/Documents/wiki/data science/llm/The Five Levels- from Spicy Autocomplete to the Dark Factory.md` (+ `.pdf` `.json` `.csv` `_methods.md`); also `The Five Levels of Spicy.docx` | `~/.skills/integrated/The Five Levels- from Spicy Autocomplete to the Dark Factory.md` | VERIFIED |
| 7 | **Agentic Coding with Claude Code** — Eden Marco, Packt 2026 | `~/Documents/wiki/harness/Agentic Coding with Claude Code.pdf` (78 MB) + `.json` (199 MB, Docling) + `.md` (39 MB) | `../inspirations.md` (615 lines) | VERIFIED |
| 8 | **Knowledge Graphs and LLMs in Action** | `~/Documents/wiki/data science/llm/Knowledge_Graphs_and_LLMs_in_Action.md` (2026-08-02) | not yet archived | VERIFIED |
| 9 | **Essential GraphRAG** | `~/Documents/wiki/data science/llm/Essential_GraphRAG.md` (2026-08-24 19:26) | not yet archived | VERIFIED — newest; may still be extracting |

## Open discrepancies

- **#6 title drift.** The operator's URL is
  `danshapiro.com/blog/2026/01/the-five-levels-from-spicy-autocomplete-to-the-software-factory/`
  ("**software** factory"); every local artifact says "**Dark** Factory". Either
  the post was retitled or the capture predates a rename. Not resolved — do not
  silently normalize one to the other.
- **#4 naming.** Recalled as "gary's tanstack". It is **Garry Tan's `gstack`**,
  unrelated to the TanStack libraries. The wrong name breaks the trail home.
- **#2 and #4** have curated extracts with no located upstream. Either the raw
  was never captured or it lives outside `~/Documents/wiki`. Until traced, the
  extract *is* the source of record.

## Derivation actually in use

`#1 Delete your CLAUDE.md` (SOURCE)
  -> `slop-review/cut-prompt.md` + `slop-review/prompt-draft.md` (SPEC)
  -> cuts applied to `~/.claude/CLAUDE.md` and `AGENTS.md`, commit `8634901`
     against baseline `01a55be` (IMPLEMENTATION)

That chain was executed before it was written down. This file is the retrofit.
