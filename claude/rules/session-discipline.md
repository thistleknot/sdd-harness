<!-- Reviewed 085-partition-variance.md, orchestration.md, playbook.md, and spec-attribution.md. Contradictions: none; spec-attribution.md:66 treats heredoc as a write operation, consistent with this rule. -->
1. Cap identical stop-hook re-checks at 3 with no new runnable step, then report one sentence.
2. Verify a blocker with one observation before reporting it.
3. Do not use sed -i on scripts; write script files with a quoted heredoc instead.
4. Do not use python on this box until ~\PY310 is confirmed on PATH.
5. When a write-capable codex call is needed use: codex exec --approve-for-me resume <id> "<prompt>".
