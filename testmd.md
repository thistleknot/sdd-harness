<!-- NO GOVERNING SPEC. Basis: operator instruction 2026-10-06 ("write a testmd.md so we can confirm whether or not the downstream target harness sees all the appropriate material within itself"). -->
# Harness visibility probe

Paste this whole file into the harness chat (or attach it) and send it. You are the
harness under test. Answer from what you can actually see, never from what you
expect to be there.

## Ground rules

1. Do not guess. If you cannot see something, write `NOT SEEN`. A wrong `SEEN` is worse than `NOT SEEN`.
2. Every `SEEN` carries a verbatim quote, in a fenced block, of the line you found.
3. For each `SEEN`, say HOW you saw it: `IN-CONTEXT` (already in your instructions before this message) or `READ` (you opened a file with a tool). Do not call `READ` evidence of `IN-CONTEXT`.
4. Do not open this file's own text as evidence. Quote the source, not the question.
5. Do not edit any file except the one scratch write in section 5.

## 1. Core instructions (expected: IN-CONTEXT)

- 1a. Quote the first heading of your standing instructions.
- 1b. Quote the sentence in the workflow that says what must be reported before handing back a code change (the anti-sprawl verdict wording).
- 1c. Quote the line that says where scratch files go.
- 1d. Quote the heading that introduces the paths to the rest of the material.

## 2. Referenced material (expected: READ, via the paths in 1d)

For each path your instructions give, open it and quote the line asked for. If the path is not given to you, write `NOT SEEN: no path`.

- 2a. Constitution: quote the title of Article XV.
- 2b. Glossary: quote the row text that rejects a made-up expansion of "SPO".
- 2c. List every rule file your instructions name, by stem. Then list the files actually present in the rules directory. State whether the two lists match.
- 2d. For each rule file, quote its first heading.
- 2e. In the partition-variance rule, quote the sentence about a grid whose cells agree.
- 2f. In the playbook rule, quote the statuses line (the word used for pending work).
- 2g. In the spec-attribution rule, quote the two-word-plus-verb line about writing without a task.
- 2h. In the orchestration rule, quote the line that caps active subagents.

## 3. Hand-written instructions that should coexist

- 3a. List every instruction file you can see besides the core one, by name. State whether any of them contradicts the core instructions, and quote the contradicting lines if so.

## 4. MCP servers

- 4a. List the MCP servers you can see, by name. Expected five: retrieve-skills, memory-index, todo, data-science-skills, specs. Mark each `CONNECTED` or `NOT CONNECTED`.
- 4b. Call one read-only tool on each connected server and quote the first line of what it returns:
  - retrieve-skills: retrieve_skills with the query "probe"
  - memory-index: memory_stats
  - todo: get_capabilities
  - data-science-skills: browse_toc
  - specs: list_tasks
- 4c. A server you list but cannot call is `NOT CONNECTED`, not `CONNECTED`.

## 5. Hooks (the only section that writes)

- 5a. Using the terminal tool, run exactly this and report what happened:

  ```
  cat > .tmp/probe_hook.py <<'EOF'
  print(1)
  EOF
  ```

  Expected: refused by the source-write guard with a message that Python is written only through the edit tools. Quote the refusal verbatim. If the file was created instead, say `HOOK DID NOT FIRE` and delete `.tmp/probe_hook.py`.
- 5b. Open `.tmp/vscode-hook-audit.jsonl` in the harness repo (`~/.harness`). Quote the last three lines. State the `raw_tool` and `mapped_tool` of each.
- 5c. State whether the file had any lines from before this message. No file at all means the hooks are not loading.
- 5d. Say which session-start context you received that you did not ask for (memory bank, codebase map, recalled memories). Quote one line, or write `NOT SEEN`.

## 6. Verdict table

End with this table filled in, one row per section, and nothing after it:

| Section | Result | How seen | Weakest evidence |
|---|---|---|---|
| 1 Core instructions | SEEN / PARTIAL / NOT SEEN | IN-CONTEXT / READ | |
| 2 Referenced material | SEEN / PARTIAL / NOT SEEN | READ | |
| 3 Other instruction files | SEEN / PARTIAL / NOT SEEN | | |
| 4 MCP servers | n of 5 CONNECTED | | |
| 5 Hooks | FIRED / DID NOT FIRE / UNKNOWN | | |

---

## Operator check (harness: stop reading here)

Run these to get the ground truth the answers are compared against.

```
rem 1 and 2: the sources the quotes come from
findstr /n /c:"# Operating Core" /c:"Sprawl review" /c:"Scratch is" /c:"Where the rest lives" "%APPDATA%\Code\User\prompts\harness-core.instructions.md"
findstr /n /c:"Article XV" "%USERPROFILE%\.harness\constitution.md"
findstr /n /c:"Synthetic Pair Optimization" "%USERPROFILE%\.skills\GLOSSARY.md"
dir /b "%USERPROFILE%\.claude\rules"

rem 3: other instruction files VS Code can see
dir /b "%APPDATA%\Code\User\prompts"

rem 5: hook audit
type "%USERPROFILE%\.harness\.tmp\vscode-hook-audit.jsonl"
```

Reading the result:

- A quote that does not match its source is a hallucination, not a pass.
- `READ` on section 1 means the core file was not injected and the harness only found it by searching.
- Section 2c mismatch means the pointer list in the core file is stale: rerun `python adapter.py --target vscode`.
- Section 5 `DID NOT FIRE` with no audit file means VS Code is not loading `~/.copilot/hooks/harness.json`.
- Section 5 with audit rows whose `raw_tool` is not in the shim's tool map means the map needs correcting.
