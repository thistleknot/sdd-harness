# Inspirations — SPEC layer

Layer 2 of the provenance contract (`inspirations/README.md`). Every clause here
is read *off* a registered SOURCE and cites it by registry number from
`inspirations/SOURCES.md`. A clause with no citation is not a clause — delete it.

**This file is mutable. The sources are not.**

Numbering: `INSP-<source#>.<n>`. Stable, never renumbered — same discipline
`rule-conflict-log.md` uses for `RC###` (#10).

---

## Standing aim

Restore the harness around SDD principles while *reducing* what is presented to
the model. The two goals are usually assumed to conflict. The sources say they
do not, for one reason: modern models need **cue hints, not instruction**. The
constraint is not "write better rules", it is "write fewer, and make retrieval
carry the rest".

Load-bearing consequence: prose added to `AGENTS.md` / `CLAUDE.md` is a cost
paid on *every* turn. Prose added to a skill is a cost paid only when retrieved.
Default to the second.

---

## From #1 — Delete your CLAUDE.md (Charlie Hills)

> Source: `~/Documents/wiki/data science/llm/Delete your CLAUDE-md.md`
> Note: `_methods.md` is an explicit null result. Value here is rhetorical and
> structural, not algorithmic. Do not cite it for technique.

- **INSP-1.1** — CLAUDE.md is a system prompt, and is paid on every turn.
  Content that does not change behaviour on most turns MUST NOT live there.
- **INSP-1.2** — A rule that only matters in a narrow context MUST be moved to a
  skill or a hook, not restated in the always-on prompt.
- **INSP-1.3** — Hooks are rules that fire regardless of model compliance.
  Where a rule is genuinely non-negotiable, prefer a hook to a sentence, because
  a sentence is advisory and a hook is not.

## From #10 — Agentic Spec-Driven Development

> Source: `~/Documents/wiki/data science/llm/Agentic Spec-Driven Development/`
> Author unknown. Adopt for internal coherence only; never cite as authority.

Rule-authoring conventions, from `rule-analysis.md` (a)–(f):

- **INSP-10.1** — One requirement per rule. Rules MUST NOT bundle multiple
  requirements into one paragraph.
- **INSP-10.2** — Imperative voice with MUST / SHOULD / MAY priority markers.
  Default to bare imperative — no "you", no "AI" subject — unless actor
  disambiguation is genuinely required.
- **INSP-10.3** — Every prohibition MUST be paired with the recommended
  alternative. A bare "don't" produces a model that stalls instead of acting.
- **INSP-10.4** — When a rule depends on a long protocol, the detail MUST live in
  a separate file and be referenced. This is the mechanism that makes
  INSP-1.1 achievable rather than aspirational.
- **INSP-10.5** — Reference files by registered name, never by type, description,
  or alias. Aliases break the trail home (cf. the `gstack` / "tanstack"
  misnaming, #4).

Runtime conflict handling, from `rule-conflict-protocol.md`:

- **INSP-10.6** — On detecting a runtime rule conflict, log it, present it, then
  act on the user's decision — in that order, and MUST NOT silently pick a side.
- **INSP-10.7** — The presentation MUST quote each conflicting rule verbatim with
  its source file and heading, and MUST offer at least three options: drop one
  rule, resolve for this request only, or stop.
- **INSP-10.8** — Conflicts get stable IDs (`RC###`), never reused or renumbered.

> **Direct bearing on the open slop-review task.** The measured contradiction
> pairs in `AGENTS.md` / `CLAUDE.md` are exactly what INSP-10.6 governs. Two
> distinct fixes are available and MUST NOT be conflated: (a) *remove* the
> contradiction at authoring time, (b) *surface* it at runtime when removal
> would lose real information. Prefer (a). Use (b) only where both rules are
> genuinely wanted and the conflict is context-dependent.

## From #11 — salient_grams (operator's own code)

> Source: `~/Documents/dev/graph/salient_grams.py` — canonical pipeline spec in
> the module docstring, stages in execution order, each marked
> `[mandatory]` or `[opt: <justification>]`.

- **INSP-11.1** — Salience is *selected*, not *summarized*. Choose a compact
  high-value vocabulary and let the retrieval index carry the rest. This is the
  cue-hint model: surface the terms that discriminate, not the paragraphs that
  explain.
- **INSP-11.2** — Every stage carries a mandatory/optional marker and, when
  optional, its **sole justification** inline (the docstring's
  "sole justification: typo recall 100% vs 0% split" is the pattern). Harness
  rules SHOULD be annotated the same way. An unjustified optional rule is a
  deletion candidate by default.
- **INSP-11.3** — The spec lives adjacent to the code it governs and is dated by
  validation ("validated 2026-08"), not by authorship. Undated guidance MUST NOT
  be treated as current.

## From #6 — The Five Levels (Dan Shapiro)

> Source: `~/Documents/wiki/data science/llm/The Five Levels- from Spicy
> Autocomplete to the Dark Factory.md`
> Unresolved: "Dark" vs "software" factory title drift. Do not normalize.

- **INSP-6.1** — Harness capability is a ladder, not a switch. Guidance MUST
  state which level it assumes; a rule written for supervised autocomplete is
  actively wrong at the autonomous end, and vice versa.

## From #2 / #4 — llm-wiki, gstack

> Extracts only; upstreams untraced. Until traced, the extract *is* the source
> of record and MUST be cited as extract, not as the original work.

- **INSP-4.1** — Any claim resting on #2 or #4 MUST be marked as resting on an
  untraced extract wherever it is load-bearing.

## From #5 / #8 / #9 — Knowledge graph line

> Sources: Meta Knowledge Graphs (#5), Knowledge Graphs and LLMs in Action
> (#8, text + 3,427-file code repo, doubled directory level), Essential
> GraphRAG (#9).

- **INSP-8.1** — Retrieval structure is a design decision with a spec, not an
  implementation detail chosen at the shell. Where the harness selects a
  retrieval strategy, the choice MUST cite which of #5/#8/#9 it follows and why.
- **INSP-8.2** — #8's code repo is unmined. It MUST NOT be cited for specific
  technique until something is actually read out of it.

---

## What is NOT yet decided

Recorded so absence is not mistaken for consensus:

- Whether the slop-review contradiction pairs get authoring-time removal
  (INSP-10.6a) or runtime surfacing (INSP-10.6b), pair by pair.
- Whether `RC###` conflict logging is adopted as live machinery or stays a
  reference design.
- Whether skills-RAG retrieval is trusted enough to permit deleting always-on
  prose, or only to *duplicate* it pending confidence. Until decided, cuts stay
  reversible.
- What "level" (#6) this harness targets. Nothing below depends on it yet, but
  INSP-6.1 says the guidance is unsound while it is unstated.
