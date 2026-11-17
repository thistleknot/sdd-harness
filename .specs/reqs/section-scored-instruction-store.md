# Section-scored instruction store

Spec layers: Requirements (observable behavior) and Structural (section hierarchy).
Governing registry: `instructions/rules.db`, rendered by `instructions/rules.py`.
Operator intent, 2026-11-17, verbatim: "store sections as their own complete section to be scored, and we construct from the data this way. and we can identify child-dependent hierarchies (sub sections). Then have an llm score each section for importance (considering only the whole section) to get synthetic scores (temp 0)."

## Requirements

- R1: The system shall store each instruction section as one complete, self-contained unit, and that whole section is the scoring unit.
- R2: The system shall record child-dependent hierarchy between sections (sub-sections under a parent section).
- R3: WHEN a section is ingested or its text changes, the system shall score its importance with an LLM that receives only that section's full text, at temperature 0.
- R4: The system shall store each score with the model identifier, the prompt version, and the hash of the scored text.
- R5: The system shall store scores apart from section text, so rescoring with another model or prompt adds a score record and leaves the text unchanged.
- R6: WHEN a prompt is constructed, the system shall select sections by score within a stated budget, and shall include each selected section's required ancestors.
- R7: The system shall keep the byte-exact rendering contract of the existing registry: an unchanged rule set renders the same bytes as the source file.
- R8: IF a section's text changes after scoring, THEN its score is marked stale until rescored, and the system shall not select it on the stale score.

## Structural

- Section: id, parent id (nullable), ordered position among siblings, full text, text hash.
- Score: section id, model id, prompt version, text hash, score value, created time.
- Hierarchy: parent-child edges only. A child is never selected without its parent.

## Open (not decided; each needs a discriminating test before it governs)

- [unknown] Score scale and range.
- [unknown] Budget unit (characters, tokens, or per-model profile).
- [unknown] How a parent's score relates to its children's. Under R1, children are scored on their own text only.
- [unknown] Whether temperature 0 yields repeatable scores in practice. Measure: score the same section three times and record the spread.

## Acceptance

- Three varied sections (short prose, nested bullets, fenced code) each receive a score from text alone.
- Rescoring one section with a second prompt version creates a new score record; section text and its render hash are unchanged.
- An edited section is marked stale and is excluded from selection until rescored.
- An unchanged registry renders byte-identical to the current `shared` view.
