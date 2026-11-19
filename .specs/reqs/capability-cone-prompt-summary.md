# Capability cone: role-scoped prompt summaries

Spec layers: Requirements (observable behavior) and Behavioral (summarize-then-solve sequence).
Supersedes nothing. Builds on `section-scored-instruction-store.md` only where that spec's scoring is not needed.

Operator intent, 2026-11-17, paraphrased from the session: stronger models have smaller usable context, so the information presented to each role must be partitioned by that role's context ceiling. Use a weaker model to summarize the system prompt as it applies to the task at hand. Skip scoring and rule-based section construction. Present two representations to the strong model: a pointed summary of the governing instructions, and the code or specs relevant to the problem.

## Requirements

- R1: The system shall assign each role a context ceiling in tokens, taken from measured spill evidence for the role's model. A ceiling without a measured source shall be marked `[unknown]`.
- R2: WHEN a role is dispatched a task, the system shall build its prompt from two parts: (a) a summary of the governing instructions as they apply to this task, and (b) the task-relevant artifacts.
- R3: The summary shall be produced by a weaker model whose context fits the full source instructions. The summarizer shall receive the source text and the task context and nothing else.
- R4: Every line of a summary shall cite the source rule it paraphrases. A line with no citation shall be discarded before dispatch.
- R5: The total dispatched prompt shall stay within the receiving role's ceiling (R1). IF it exceeds the ceiling, THEN the system shall drop lowest-relevance artifacts first and shall not drop the summary.
- R6: The system shall not score rules or sections for importance. Relevance is decided per task by the summarizer.
- R7: The system shall record, per dispatch, the summarizer model, the receiving role, the ceiling used, the token count dispatched, and the source-text hash, so a result can be traced to the instructions it was given.

## Behavioral

1. Load the full governing instructions.
2. Summarize them for the task with the summarizer model (R3, R4).
3. Assemble the prompt: summary, then task artifacts, capped at the role ceiling (R5).
4. Dispatch to the role. Record R7 fields.

## Open (not decided; each needs a test before it governs)

- [unknown] Ceiling for each role. Hemmingway spills at 64k (2.19 GB RAM spill; 6.24 tok/s) and runs clean at 32k (10.19 tok/s). Working cap for Hemmingway: 32k. Caps for the Qwen3-VL-8B, Gemma-4-26B-A4B, and Gemma-4-12B models come from `.tmp\bench-models-ctx-20261117.jsonl` and are not yet read.
- [unknown] Whether the summarizer drops rules that change the answer. Measured by the acceptance test below, not assumed.
- [inferred] A structured code view (function and class headers, entity model, and the functions tied to one system use case) would serve the same role for code problems. Not specified here; a separate spec is needed before building it.

## Acceptance

- Three varied problems (different roles, different rule subsets). Each solved twice: once with the full instructions, once with the summary. A pass requires the same governing rule to change or support the answer in both runs.
- A summary check: every source rule cited in a summary exists verbatim in the source text. Any citation that does not match is a failure.
- Dispatched prompt length for each role is at or below its ceiling (R5), recorded per run.
- The 26B-A4B and 12B ceilings are set from measured data, not assumed, before R5 is enforced for them.
