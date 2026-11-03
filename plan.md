<!-- NO GOVERNING SPEC. Basis: operator instruction 2026-10-13 (stated order: playbook.md, specs, plan.md, agentic-kanban). Requirements: specs.db REQ #39-#44. Design: playbook.md. -->
# Plan: Route new features through an agentic-kanban board

Scratch todo list. Fed from playbook.md (design) and the specs (REQ #39-#44, spec tasks #64-#71). Statuses move here as work happens: `[OPEN]` -> `[WIP]` -> `[DONE]`, or `[BLOCKED]`. Layers are barriers.

**One source of truth for task state.** Until the board server exists (layer 3, T4), this file is the truth and is edited by hand. At T4 it is imported into the board once, and from then on the board is the truth: this file is regenerated from it and is never edited, the same way the rendered specs are views of `specs.db`. Two writers would drift. Until T4 is done, nothing is imported and nothing is regenerated.

## Layer 1 - sequential
- [DONE] T1 Specify the feature board (spec task #64)
  _Files:_ specs/specs.db (rendered views), .specs/file-manifest.md
  _Verify:_ requirements and tasks queryable and rendered
  _Lessons:_ rows added through the specs MCP, not by editing the rendered markdown. Gate run afterwards (`python -m specs.run_gate --event Stop`): BLOCK, 52 blocking / 55 warnings / 162 verdicts, every blocker from the `convergence` validator across the whole repo; a search of the verdict messages, subjects and evidence for `board` and `worktrees` found nothing, so none of it is attributable to these files. The earlier "validators pass" line was never true and is dropped. The run created `specs/gate_ledger.db`, which I deleted.

## Layer 2 - parallel
- [DONE] T2 Board store keyed by project (spec task #65)
  _Files:_ board.py, test_board.py
  _Verify:_ `python -m pytest test_board.py -q` -> 10 passed (run by me, not only the doer)
  _Lessons:_ dependencies can only name existing stories, so a cycle cannot be built; the cycle check in the spec is satisfied by construction and the test covers self, missing and negative ids instead.
- [DONE] T3 Worktree manager (spec task #66)
  _Files:_ worktrees.py, test_worktrees.py
  _Verify:_ `python -m pytest test_worktrees.py -q` -> 13 passed (re-run by me inside the 23- and 31-test runs)
  _Lessons:_ ignoring `.worktrees/` goes through the repo's `info/exclude`, so no tracked file changes.

## Layer 3 - sequential (T4 first; then T4b and T5, which touch disjoint files, together)
- [DONE] T4 The agentic-kanban MCP server (spec task #67)
  _Files:_ board_mcp.py, test_board_mcp.py
  _Verify:_ `python -m pytest test_board.py test_worktrees.py test_board_mcp.py -q` -> 31 passed (run by me). Real stdio spawn of `python board_mcp.py` lists 10 tools and `whoami` returns a pid.
  _Lessons:_ the in-memory client passes where a real stdio spawn could still fail, so the stdio smoke was run separately (the traceback printed after it is a Windows pipe close as the scratch script exits). Still open from this task: whether a subagent gets its own server process; `whoami` is the probe and needs a live session.
- [DONE] T4b Build plan import and render in the board (spec task #72, REQ #45); the cutover itself moved to T9
  _Files:_ board.py, board_mcp.py, test_board.py, test_board_mcp.py
  _Verify:_ `python -m pytest test_board.py test_worktrees.py test_board_mcp.py -q` -> 42 passed (my run); `python .tmp/roundtrip.py` on the real plan.md -> 6930 bytes in, 6930 out, 8 of 8 lessons, 0 diff lines. Concurrent lessons: 2 processes x 25 on one story lost 22 of 50 before the fix and keep 50 of 50 after (`.tmp/lesson_race.py`, run twice; a 3 x 25 regression test is in test_board.py).
  _Blocked:_ first pass imported and rendered but was lossy. Real plan.md through import then render: 10 tasks kept, 7 of 7 `_Lessons:_` lines, the header and intro paragraphs lost (6010 bytes -> 2836), a sequential layer relabeled parallel. Making this file generated at that point would have erased the handoff notes. Requirement #45 now demands a byte-identical round trip plus an `add_lesson` tool (lessons are the one thing agents must still write once the file is read-only); fix dispatched. The plan.md row stays as it is until that round trip passes.
  _Lessons:_ observed in `file_manifest.py:138-141,419`: `generated` is advisory, only `read-only` and `append-only` are enforced. So the plan.md row switches to `read-only` at import time; the board server writes the file from Python, which the Edit/Write gate does not see. No new hook. The import from this file into the board happens once, in this task.
- [DONE] T5 `feature:` trigger in the existing hook (spec task #68)
  _Files:_ C:/Users/user/.claude/hooks/playbook.py, C:/Users/user/.claude/hooks/test_playbook.py
  _Verify:_ `python -m pytest C:/Users/user/.claude/hooks/test_playbook.py -q`; positive, negative, subagent, `.worktrees/` and non-git cases
  _Lessons:_ the live hook is `~/.claude/hooks/playbook.py` (settings.json runs it, `--plan` on prompt submit); `claude/hooks/` here is the archive, so the edit goes in the live file and the archive is refreshed by pulling afterwards. Riding the existing `--plan` registration avoids a settings.json edit.
  Result (my own run, live hook): 15 passed; `feature: demo` in this repo -> 1144 chars of context; `how do I add a feature` -> 0; `hello` -> 0; `architect this` -> 1735 (unchanged behaviour); `feature: demo` from a non-git cwd -> 0. This hook is live in every Claude session now. NOT TESTED: the subagent guard against a real Claude subagent payload (only a synthetic `agent_id` was tested).

## Layer 4 - sequential
- [DONE] T6 Register the server and project it to Claude (spec task #69)
  _Files:_ harness.json
  _Verify:_ `~/.claude.json` lists `agentic-kanban`; `claude mcp get agentic-kanban` -> `Status: ✔ Connected`. Dry run before writing showed one change: add `agentic-kanban`; the five existing entries were identical and `caveman` and `github` untouched. `python -m pytest test_adapter.py -q` -> 14 passed.
  _Lessons:_ only `sync_claude_code` was run, not the whole `python adapter.py`, so no other harness's config was touched. A running Claude session needs a restart to load the new server; the live tool call from a session is still to be seen (T8).
- [DONE] T6b Fix the Codex MCP projection (spec task #69)
  _Result:_ `python -m pytest test_board.py test_worktrees.py test_board_mcp.py test_adapter.py specs/test_harness_write.py -q` -> 88 passed (my run). Dry run showed a pure append of a marked block after the `rea` table; applied through `sync_codex` with a backup in `backups/20261013-195720/`; `codex mcp list` now shows `agentic-kanban`, `data-science-skills`, `memory-index`, `retrieve-skills`, `specs`, `todo` and the original `rea`. "Enabled" is not "connected": a live Codex tool call is still to be seen (T8).
  _Lessons:_ a test that read the real plan.md and assumed the edited task was its last one broke when a task was added after it; the test now computes where the lesson lands. Tests that read the live plan.md are fragile to edits of it.
  _Files:_ adapter.py, test_adapter.py
  _Verify:_ after `python adapter.py`, `codex mcp list` shows `agentic-kanban` and the other harness servers. Today it shows only `rea`, because `sync_codex` writes `~/.codex/mcp.json`, which Codex does not read. Write `[mcp_servers.*]` into `~/.codex/config.toml` through `harness_write.py` (merge-only, backed up), and keep the existing `rea` entry.
- [DONE] T7 Trigger export for Codex (spec task #70); needs your one-time `/hooks` trust in Codex
  _Result:_ `~/.codex/hooks.json` carries a `UserPromptSubmit` entry that runs `playbook.py --feature`; 108 tests passed before the live run, 109 after the stdio fix. In a live headless Codex run the hook fired and the model followed it (create_feature, preview, stop for confirmation). My runs used `--dangerously-bypass-hook-trust` for that one invocation only, and `-c mcp_servers.agentic-kanban.default_tools_approval_mode="approve"` as a one-off; neither is written into your config. For interactive Codex you must review and trust the hook once in `/hooks`, and decide whether to set that approval mode (without it Codex asks before every board call).
  _Blocked:_ the first live Codex runs failed: `create_feature` hung 300 s. Cause (stack from `faulthandler`, then moved step by step): every `git` child process inherited the stdio server's stdin pipe on Windows and never finished, at `board_mcp.py:50`, then `board.py:109`, then `worktrees.py:31`. The in-memory test client shares the test's process and never showed it. Fix: `stdin=subprocess.DEVNULL` on all three; a real-stdio regression test fails with the fix removed (McpError timeout) and passes with it.
  _Lessons:_ a green in-memory suite does not prove a stdio server works; the real spawn is the test. Codex followed "stop for confirmation" even when the prompt said it was pre-confirmed, so a headless run needs a second turn (`codex exec resume --last`).
  _Files:_ adapter.py, instructions/
  _Verify:_ fresh Codex session in a scratch repo follows the board procedure on `feature:`.
  _Lessons:_ Codex does fire `UserPromptSubmit` with `prompt`, `cwd`, `session_id` and takes `additionalContext` back, so the Claude hook's output shape carries over; write the hook into `~/.codex/hooks.json` through `harness_write.py`. Still to test: whether a written hook needs one-time trust approval before it fires, and how to tell a subagent prompt (subagent hooks share the parent's `session_id`).

## Layer 5 - sequential
- [DONE] T8b Refuse submit on an empty or uncommitted story (spec task #74, REQ #42)
  _Files:_ worktrees.py, board_mcp.py, test_worktrees.py, test_board_mcp.py
  _Verify:_ all suites -> 110 passed (my run); new test: submit refused with no commits ("no commits ahead") and with an uncommitted file ("uncommitted"), story stays in-progress, accepted after commit.
  _Lessons:_ found by the live Codex runs: reviewers rejected three submissions for an empty diff because the implementer had not committed. One later Codex run was clean, but an unguarded single-story run was also clean, so that run does not show the guard changed behaviour.
- [DONE] T8 Live end-to-end on a throwaway repo (spec task #71)
  _Result:_ six live runs, each on its own scratch repo, all through the board's real stdio server, all merged with passing tests. Codex: single story (`demo`, merge 8c90d9b), dependency chain mul then power (story 6 accepted before 7 claimed, 8 tests pass), one story rejected (div: `rejected` for the missing docstring, resubmitted, accepted, 3 tests pass). Claude: single story (merge c19da95), dependency chain (mul then power, merged in order), one rejection (`reviewer-3` rejected "no one-line docstring", `doer-3` resubmitted commit 78ef14d, accepted). Evidence is in `board/board.db` events and `git log --graph` of each `.tmp/e2e/*` repo.
  _Blocked:_ first Codex attempts failed (create_feature hung 300 s) and later ones raced on `resume --last`; both were found and fixed (see T7) before these results.
  _Lessons:_ (1) a Claude subagent shares its parent's board server process (same pid), so the review gate is advisory; Codex unanswered because its headless subagent launch failed. (2) The Codex implementer, not the board, produced the empty-diff submissions. (3) Codex follows "stop for confirmation" even when told in the prompt, so every run needs a confirm turn.
  _Files:_ .tmp/ only
  _Verify:_ three varied features (a dependency chain, a single story, one rejected once) run `feature:` to merged in Claude and in Codex; board rows, `git worktree list` and `git log` quoted verbatim
- [DONE] T9 Cut plan.md over to the board (spec task #73)
  _Files:_ .specs/file-manifest.md, plan.md
  _Verify:_ import plan.md into the live `~/.harness/board/board.db` (feature "Route new features through an agentic-kanban board", project `C:/Users/user/.harness/.git`), render it back over plan.md and diff (0 lines); switch the plan.md manifest row to `read-only`; an agent Edit to plan.md is denied by `file_manifest.py`; a status change through the board changes plan.md on the next render; two renders identical
  Runs last, after the live run, so there is one writer at a time: until here this file was edited by hand, afterwards only the board writes it. This is the last hand edit.
  _Lessons:_ to change this file from now on: use the board (`add_lesson`, or a new feature imported from a fresh plan), or flip the plan.md row in `.specs/file-manifest.md` back from `read-only` (the deny message names both). Imported stories have no worktree, so a story imported as OPEN or WIP can only be finished by claiming it and committing real work on a story branch; all of this campaign's stories were imported as DONE.
