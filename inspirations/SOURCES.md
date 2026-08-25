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
| 4 | **gstack** — Garry Tan, MIT | *no upstream found in `~/Documents/wiki`* | `~/.skills/integrated/gstack.md` (18,708 b; header cites `garrytan/gstack`) — **restored by operator 2026-08-24** after being thought lost | EXTRACT VERIFIED / upstream UNVERIFIED |
| 5 | **Meta Knowledge Graphs / Context Graphs** — Firat Tekiner | `~/Documents/wiki/data science/llm/Meta Knowledge Graphs Context Graphs.md` (+ `.pdf` `.csv`) | `~/.skills/integrated/Meta_Knowledge_Graphs_Context_Graphs.md` | VERIFIED |
| 6 | **The Five Levels: from Spicy Autocomplete to the Dark Factory** — Dan Shapiro | `~/Documents/wiki/data science/llm/The Five Levels- from Spicy Autocomplete to the Dark Factory.md` (+ `.pdf` `.json` `.csv` `_methods.md`); also `The Five Levels of Spicy.docx` | `~/.skills/integrated/The Five Levels- from Spicy Autocomplete to the Dark Factory.md` | VERIFIED |
| 7 | **Agentic Coding with Claude Code** — Eden Marco, Packt 2026 | `~/Documents/wiki/harness/Agentic Coding with Claude Code.pdf` (78 MB) + `.json` (199 MB, Docling) + `.md` (39 MB) | `../inspirations.md` (615 lines) | VERIFIED |
| 8 | **Knowledge Graphs and LLMs in Action** | text: `~/Documents/wiki/data science/llm/Knowledge_Graphs_and_LLMs_in_Action.md` (2026-08-02)<br>code: `~/Documents/wiki/data science/llm/knowledge-graphs-and-llms-in-action-main/knowledge-graphs-and-llms-in-action-main/` (3,427 files — **note the doubled directory level**, the outer dir holds only the inner one) | not yet archived | VERIFIED |
| 9 | **Essential GraphRAG** | `~/Documents/wiki/data science/llm/Essential_GraphRAG.md` (2026-08-24 19:26) | not yet archived | VERIFIED — newest; may still be extracting |
| 10 | **Agentic Spec-Driven Development** — unattributed rule-protocol set, 2026-08-24 | `~/Documents/wiki/data science/llm/Agentic Spec-Driven Development/` (9 files: `claude.md` 14 KB, `rule-analysis.md`, `rule-conflict-protocol.md`, `rule-conflict-log.md`, `disambiguate.md`, `errata-flow-v1.md`, `errata-flow-v2.md`, `gen-errata-flow.md`, `regen-all.md`) | not yet archived | VERIFIED on disk / author UNVERIFIED |
| 11 | **salient_grams** — operator's own code | `~/Documents/dev/graph/salient_grams.py` (38 KB, canonical pipeline spec in module docstring, "validated 2026-08") + `tests/test_salient_grams.py` | none — source is live code | VERIFIED |

## Open discrepancies

- **#6 title drift.** The operator's URL is
  `danshapiro.com/blog/2026/01/the-five-levels-from-spicy-autocomplete-to-the-software-factory/`
  ("**software** factory"); every local artifact says "**Dark** Factory". Either
  the post was retitled or the capture predates a rename. Not resolved — do not
  silently normalize one to the other.
- **#4 naming.** Recalled as "gary's tanstack". It is **Garry Tan's `gstack`**,
  unrelated to the TanStack libraries. The wrong name breaks the trail home.
  The extract was believed lost and was **restored 2026-08-24**; the loss/restore
  cycle is itself the argument for this registry existing.
- **#1 `_methods.md` is a null result, not a gap.** It reads "This is not a
  research paper with methods to extract... **No methods extracted.**" Do not
  re-mine it expecting algorithmic content. #1's value is rhetorical and
  structural, not methodological.
- **#10 unattributed.** No author, URL, or upstream repo is recorded anywhere in
  the nine files. It is internally consistent and immediately usable, but it
  cannot be cited as authority — only as a design that happens to work. Treat
  every rule in it as a proposal to be justified locally, not an appeal.
- **#2 and #4** have curated extracts with no located upstream. Either the raw
  was never captured or it lives outside `~/Documents/wiki`. Until traced, the
  extract *is* the source of record.

## Derivation actually in use

`#1 Delete your CLAUDE.md` (SOURCE)
  -> `slop-review/cut-prompt.md` + `slop-review/prompt-draft.md` (SPEC)
  -> cuts applied to `~/.claude/CLAUDE.md` and `AGENTS.md`, commit `8634901`
     against baseline `01a55be` (IMPLEMENTATION)

That chain was executed before it was written down. This file is the retrofit.
