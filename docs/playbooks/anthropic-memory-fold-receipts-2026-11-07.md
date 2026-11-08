# Anthropic memory-article fold — evidence receipts

## 2026-11-07 — research

- [observed] Article read in full via fetch: components = notes, prediction/salience,
  steering, dreaming (correct/represent/promote/focus/fill-gaps), transcript-search
  foundation, open questions (write-time vs dream-time, cadence, drift).
- [observed] Key numbers: Pokemon Sonnet 3.7 413 files/225 folders/1 badge vs Fable 5
  9 files/2 folders + global.md/4 badges; CL-Bench Opus 5 first to close the
  rule+evidence+traps loop; steering "record only failures" removed most of the
  memory gain for Opus 4.7/5; prompting read-before-answer nearly doubled Sonnet 4.6;
  wiki dreaming 2->128 sessions: 13%->48%; wiki+search 61 vs search 53, ~20k
  tokens/question saved; LAB contract pages 41/57 -> 57/57 after instruction change;
  promotion budget = first 200 lines / 25 KB of MEMORY.md.
- [observed] ~/.mcp/memory-index ALREADY has: dream.py (capture/judgment split thesis,
  idempotent per-session watermark, MEM_IN_EXTRACTION recursion guard, candidate->
  approved gate, median+1.4826*MAD cold-start auto-approve threshold, lessons-learned
  folding, contradiction-check degrades toward MORE review); conversation_store.py
  (append-only volleys, FTS5, hot window 13); mem_server.py tools incl.
  append_volley/get_hot_window/anneal/feedback/audit.
- [observed] Before today dream.py had NO verify mode, NO promote mode, NO
  goal-instructions hook. A mid-fold edit that would have deleted the scope= line was
  abandoned when its path failed — kept out deliberately.
- [observed] mem.DEFAULT_MEM_DIR resolves to a legacy .claude/projects path in this
  shell (env-dependent); live store is ~/memory-bank (3312 .md files; mem.memory_files
  scopes to 45 real memories). All invocations pass --mem-dir explicitly.
- [observed] Pre-existing LSP complaints at dream.py L330-331 (Optional subscript in
  find_same_subject) predate today's edits, sit under a runtime guard, and were left
  untouched (minimal impact).

## 2026-11-07 — execution receipts

- [observed] M0/M1: py_compile rc=0; --help lists --verify/--apply/--promote/
  --instructions. --verify --dry-run: "0 checked, 45 without a usable transcript
  skipped" — no existing memory carries source_session, so verify bites from the next
  dream distillation onward (honest: capability shipped, corpus not yet eligible).
- [observed] --promote --dry-run then real: "45/45 approved notes indexed, 6370 bytes"
  -> ~/memory-bank/MEMORY.md, 55 lines, budget-compliant, goals section preserved for
  future rebuilds.
- [observed] M2/M3: reference note docs\references\anthropic-agent-memory-components.md
  and rules\145-memory-steering.md (6 laws) written.
- [observed] M4: agent-long-term-memory skill fold section appended; exported; client
  mirror hashes verified against master (see next line of the run log).
- [observed] M5: SpecsDB requirement #74 + task #96 (done, deferrals named).
- [inferred] The article validates the architecture and adds three functions + three
  laws; effectiveness claims stay gated — control arms (no-memory/full-context/BM25)
  still owed before this skill upgrades from draft.
