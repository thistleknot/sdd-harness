# PyBot routing evidence

## CURRENT — 2026-11-18 — Unsupported for DIRECT/PLANNER numerical routing

**Question**

Can PyBot safely classify agent tasks as DIRECT versus PLANNER before a language-model call, with a numerical score sufficient to avoid the call?

**Evidence and probe**

- Upstream repository `huggingface/pybot`, main revision `7d63c7fbebb44c7e466e5c8b5c1f341ab767929e`; its `pybot.py` identifies bundled `bot/` source revision `24cbc0439e07fd015c0747ab3be6e782a42b5c5b`.
- Public `bot.understanding.understand(text, memory)` returns structured conversational readings (`kind`, `intent`, `topic`, `topic_score`, `asks`); no field or contract represents DIRECT/PLANNER route confidence.
- Ran the 12 frozen cases from `.tmp/jev-routing-eval/results-20261118-191413.json` offline through `understand(text,{})`, six DIRECT and six PLANNER. Total elapsed: 5.2021 seconds; median per case: 0.01495 seconds (cold import contributes 1.3473 seconds to the first case).
- Outputs overlap across classes: D03 (simple code lookup) and P05 (multi-step evaluation) both returned `intent=statement`, `topic=technology`, `topic_score=2`, `asks=[]`. Topic evidence is not an execution-route score.
- Existing controls on the same labels: JEV macro-F1 0.733, accuracy .750, three of six PLANNER cases routed DIRECT, average 42.89 seconds; Qwen baseline macro-F1 .916, accuracy .917, one DIRECT miss, all six PLANNER cases correct, average 5.50 seconds. Full outcomes are in the JEV receipt.

**Disposition**

Do not use PyBot as a numerical DIRECT/PLANNER gate on this interface or add a routing integration story. That mapping has no score contract and weak evidence; accepting it could hide orchestration misroutes. This does not reject PyBot as a conversational chatbot or prove that a future route-specific extension cannot work.

**Reopen condition**

A route-specific score/label contract plus a held-out evaluation that records wrong accepted routes, coverage, abstention, latency, and avoided LLM calls.

No code or tests were changed. The probe was offline and used only the frozen pilot corpus.
