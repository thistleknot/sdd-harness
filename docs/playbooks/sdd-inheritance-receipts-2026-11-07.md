# DDSE/sw-design inheritance — evidence receipts

## 2026-11-07 — research

- [observed] `sw-design` exists only at `~\.skills\sw-design\SKILL.md` (101 lines); recursive scan of `~\.claude\skills` for a `sw-design` directory returned nothing.
- [observed] `sync_skills.ps1` present in `.skills`, `.claude`, `.copilot`, `.hermes`, `.pi` skill roots; absent from `.codex`.
- [observed] `~\.codex\skills` contains only `.system`; codex native skill dir per `adapter.py` L85 is `.agents/skills`; R19 requires native copy, R20 makes the native dir the drift-check target.
- [observed] DDSE note at `~\.harness\docs\references\ddse and other sdd resources.md` (5.7 KB): 4 external links + Kiro design.md vs AIUP entity-model comparison; raw chat-paste artifacts present (mojibake bullets, table fragments).
- [observed] Vault `~\.harness\claude\docs\` has no `references` subdir today, so the DDSE note is not inherited by `~\.claude`.
- [observed] `sync-to-claude.ps1` maps vault -> live with a newer-and-smaller hold guard on every synced file; `-DryRun` is the default when no flag is passed.
- [observed] AIUP skills (`entity-model`, `use-case-spec`, `requirements`, `test-case`, ...) already live in `~\.claude\skills`; sw-design is the missing connector chaining speckit -> Sphinx-Needs -> needuml -> AIUP -> Ecore -> pyecoregen.
- [observed] Constitution Article I item 3 requires a design (structural + behavioral) with no producing toolchain named.
- [inferred] sw-design covers the structural half honestly; its Known limits state generated classes carry no behavior — behavioral layers still come from use-case tests, so the plan must not claim sw-design satisfies the behavioral half.
- [inferred] The DDSE note's value is the scope boundary (design.md = whole system; entity model = data structure nested inside it); that boundary is what the playbook's design-layer section should state.

## Weak premises / falsifiers

- Premise "codex inherits skills from .harness": partly observed only. Falsifier: if `adapter.py --target skills` has no such route or drift check fails, codex delivery must go via the plugin dir instead — re-check before claiming W2 pass.
- Premise "the four external repos are worth adopting": unverified beyond the note. Gate G1 exists precisely because vendoring was not evidenced.
- Premise "distilling the note loses nothing": mitigated — the raw original is preserved in place; the distilled file cites it as source.

## Disposition

Proceed with the chosen approach in plan.md; W1 items are parallel-safe (disjoint files); W2 sequential on the shared tree; G1/G2 held for operator decision.

## 2026-11-07 — operator instruction: clone and disposition (G1 resolved)

- [observed] Operator directed cloning the repos to disposition them correctly; G1 is therefore decided: vendor, not link-only.
- [observed] `ddse.md` (9.4 KB) is a full local copy of the HF article; live webfetch of the blog matches its content.
- [observed] All three clones landed with `.git` at `~\.harness\references\{spec-driven-development-book, anioko-spec-driven-development, pi-sdd-kit}`. The first batch's "FAILED" lines were PowerShell false negatives: git writes progress to stderr, NativeCommandError flips `$?`; verification must use Test-Path / `$LASTEXITCODE`.
- [observed] Book license CC BY-NC-SA (internal study only); sdd-kit MIT; pi-sdd-kit LICENSE present, unverified.
- [observed] pi-sdd-kit overlaps the speckit family almost entirely except sdd-idea, sdd-review, sdd-status, sdd-steering + handoff template; Anioko repo is a guide, not a toolkit.
- [inferred] Dispositions: book = reference library; Anioko = notes only; pi-sdd-kit = delta-skill adoption pending gate G3 (one SDD stack per client); DDSE article = concept input onto existing SpecsDB decision/traceability primitives.
- [observed] Recorded: SpecsDB disposition `external-sdd-resources-disposition-2026-11-07`; distilled vault reference written at `~\.harness\claude\docs\references\ddse-and-other-sdd-resources.md` (no incumbent existed).
