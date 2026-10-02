<!-- NO GOVERNING SPEC. Basis: operator request 2026-10-01 ("write this as a playbook-harness-sdd.md ... so I can get to this tomorrow morning and have sdd implemented for use with codex"). Row: .specs/file-manifest.md, docs/playbooks/. Promote to tasks.md before anything here is depended on. -->

# Playbook: SDD on Codex CLI

Source: this session, 2026-10-01
Objective (operator's words): "have sdd implemented for use with codex" at work, now that Kiro limits have struck, and to know whether OpenHarness is still needed.

## Answer first

**Codex CLI runs SDD directly. OpenHarness is not required.** Layers 1-2 get you SDD on Codex with no OpenHarness. OpenHarness is only an optional test of whether write-blocking is possible (Layer 3).

What Codex can do today: read steering from `AGENTS.md`, load plugin skills, call MCP servers, run on your gateway.
What Codex cannot do today: block a write. The spec gate stays advisory until a deny hook is shown to work.

## Where things stand (observed 2026-10-01)

```
codex-cli 0.121.0
~/.codex/config.toml          model = "gpt-5.4", base_url = "http://localhost:4000/v1" (nothing was listening on :4000 on this machine)
~/.codex/plugins/sdd-harness  plugin.json + 3 skills (spec-driven-development, session-continuity, failure-archaeology)
codex mcp list                "No MCP servers configured yet."
~/.codex/mcp.json             exists, written by adapter.py sync_codex, and Codex does not read it
~/.codex/AGENTS.md            does not exist
codex features list           codex_hooks  under development  false
```

So the skills are installed, the MCP servers are not wired, and there is no steering file.

## Start here (tomorrow, 10 minutes)

1. At work, find the gateway URL and a model name: `curl <BASE>/v1/models`. The playbook uses `<BASE>` and `<PLANNER>` / `<WORKER>` for these. Nothing below runs until you have them.
2. Work through Layer 1, then Layer 2. Stop there if you only want SDD on Codex.
3. Layer 3 is the OpenHarness question. Do it only if you want enforcement.

## Layer 1 — parallel

- [OPEN] T1 Put the constitution and rules in one steering file Codex can read
  _Files:_ instructions/codex.md, ~/.codex/AGENTS.md
  _Basis:_ `claude/AGENTS.md` says the constitution is "not an @-import outside Claude Code", so the Codex file must inline it rather than reference it.
  _Verify:_ in a scratch repo run `codex exec "In one sentence, what does Article I of the constitution require?"` and the answer matches the constitution's Spec-First Imperative.

- [OPEN] T2 Make the MCP servers visible to Codex
  _Files:_ adapter.py
  _Basis:_ `adapter.sync_codex` writes `~/.codex/mcp.json`, and `codex mcp list` shows nothing, so that path is dead. Codex reads `[mcp_servers.*]` from `config.toml`; confirm with `codex mcp add --help` before changing the adapter.
  _Verify:_ `codex mcp list` shows the five servers from `harness.json` (retrieve-skills, memory-index, todo, data-science-skills, specs).

- [OPEN] T3 Name the models Codex should use for planner and worker
  _Files:_ harness.json, tiers.toml
  _Basis:_ `model_routing` names Claude models only. Collapse to one planner and one worker from the gateway, using the existing `local` block as the shape.
  _Verify:_ `python render_agents.py --check` passes, and `codex exec -m <WORKER> "reply PONG"` returns PONG.

## Layer 2 — sequential

- [OPEN] T4 Record Codex as a harness in the capability matrix
  _Files:_ manifest.toml
  _Basis:_ only claude, pi, opencode, and kiro have entries. Add `[harness.codex]` with `can_gate = false`, `gate_style = "none"`, and a note that it is advisory until Layer 3 says otherwise. Add cells for policy, instructions, mcp, and skills.
  _Verify:_ `python plugin/install.py --verify` still passes, and the codex row appears.

- [OPEN] T5 Catch violations at commit time, since Codex cannot block them at write time
  _Files:_ scripts/verify.ps1
  _Basis:_ the file manifest and task-lineage checks exist as hooks. Run them from a pre-commit step instead. This needs a one-line spec before it is written (changes observable behavior).
  _Verify:_ a commit containing a file with no manifest row is rejected.

- [OPEN] T6 Smoke-test SDD end to end on three varied prompts
  _Files:_ none (scratch repo under `.tmp/`)
  _Basis:_ one passing prompt against a stochastic agent is noise, so use three: a feature request, a typo fix (should skip the spec), a bug report (should just fix).
  _Verify:_ the feature request makes Codex draft a spec and call the specs MCP before writing code; the typo fix does not.

## Layer 3 — parallel (optional: can the harness block writes?)

- [OPEN] T7 Test whether OpenHarness honors a deny hook
  _Files:_ none (scratch repo under `.tmp/`)
  _Basis:_ OpenHarness has `pre_tool_use` events in `src/openharness/hooks/events.py`. Whether it accepts your hooks' deny format is untested. Check that work allows `pip install openharness-ai` first.
  _Verify:_ with a deny hook configured in `~/.openharness/settings.json`, `openh -p "create file x.txt"` is refused and `x.txt` does not exist.

- [OPEN] T8 Test whether Codex's own hook flag can deny a write
  _Files:_ none (scratch repo under `.tmp/`)
  _Basis:_ `codex_hooks` is `under development` in 0.121.0. Enable it in the scratch repo only: `codex features enable codex_hooks`.
  _Verify:_ a pre-tool hook that exits with a deny stops `codex exec "create file x.txt"` and `x.txt` does not exist.

## Layer 4 — sequential

- [OPEN] T9 Record what Layer 3 found and pick the runtime
  _Files:_ manifest.toml, docs/playbooks/playbook-harness-sdd.md
  _Basis:_ if T8 passes, set `can_gate = true` on codex and stop; OpenHarness is unnecessary. If only T7 passes, use OpenHarness as the enforcing runtime on the same gateway. If neither passes, Codex stays advisory and T5 is the enforcement.
  _Verify:_ the matrix row matches the test result, with the log line from the passing test pasted in `_Lessons:`.

## Not known yet

- The work gateway URL and its model names.
- Whether `gpt-5.4` exists at work.
- Whether OpenHarness installs on the work machine.
- Whether either runtime accepts a Claude-format deny hook.
