# Porting the spec-driven gate to opencode

## CURRENT DISPOSITION (2026-08-05, after install)

**Installed and unit-validated. Live agent denial is UNPROVEN — blocked by a
pre-existing config fault, not by this code.**

| Claim | Status |
|---|---|
| Plugin loads inside opencode's own process | **PROVEN** — init marker written with `dir=C:\Users\user` during `opencode debug config` |
| Gate logic (41 cases, real temp trees, bun) | **PROVEN** — 41/41 |
| Directory is `plugin/` **singular** | **PROVEN** — both literals exist in the binary; singular is what loads |
| A live agent is actually denied an edit | **NOT PROVEN** — see below |

**Blocker:** every non-`--pure` session on this box dies with
`ProviderModelNotFoundError: Model not found: ollama/qwen3.5-reasoning-thinking-256k:4b`.
Referenced from `oh-my-opencode-slim.jsonc` and `oh-my-opencode-slim/oh-my-opencode-slim.json`.
It is **not** caused by this plugin — parking `spec-gate.ts` and re-running reproduces
the identical failure. `--model` override does not help; the dead model is resolved
during init, not only as the session model. Fix that reference, then run the live
sequence in "Verification".

**`--pure` is not a workaround.** It disables *all* external plugins including
project-level ones, so the gate does not load under it. A `--pure` run that edits a
file successfully proves nothing about the gate.

### Corrections to the original design notes below

Three claims in the first draft were wrong, all in your favour:

1. **Per-turn injection is not lost.** `experimental.chat.system.transform` gives
   mutable `output.system: string[]` — a *system prompt* injection point, stronger
   than Claude Code's `additionalContext`. Implemented.
2. **`permission.ask` exists**, with `output.status: "ask" | "deny" | "allow"`.
   Not used here (it only fires when a permission is actually asked; throwing in
   `tool.execute.before` covers auto-approved calls too) but it is a real surface.
3. **Commands are user-typed**, so a command file is closer to operator-only than
   assumed. The bash guard is still required, because nothing stops the agent
   shelling out — but the reasoning is "defence that does not depend on that
   assumption", not "commands are model-invocable".

### Defect found during install

**Never put a test file in `plugin/`.** opencode auto-loads every `.ts` there, so
`spec-gate.test.ts` executed its whole battery on every startup. Tests live in
`~/.config/opencode/spec-gate-tests/` instead. This cost a confusing false positive:
the load-probe marker was being written by the test's own calls, not by opencode.

---

## Original design notes

**Status when written: UNVALIDATED design**, derived from opencode's docs and issue
tracker. Superseded in part by the disposition above.

Source of the Claude Code original: `~/.claude/hooks/spec_{gate,state,paths}.py`,
`~/.claude/skills/spec-*/`, validated 2026-08-04 at 30/30 battery + 10-step live.

---

## The one finding that changes the design

`tool.execute.before` **does not intercept tool calls made by subagents** spawned
through the task tool — [opencode#5894](https://github.com/anomalyco/opencode/issues/5894),
filed explicitly as a security-policy bypass. A second report,
[#6396](https://github.com/sst/opencode/issues/6396), says agent-level `permission`
denies are ignored when the agent is invoked via the SDK.

For a spec gate this is not cosmetic. In Claude Code, hooks fire inside subagents
too, so the wall holds everywhere. In opencode, **the primary agent is walled and
subagents are not.** An orchestrator that delegates the edit to a worker walks
straight through.

Three honest responses, in order of preference:

1. **Deny the task/subagent tool itself** while a spec is unapproved. The gate then
   covers the hole by removing the route around it rather than by trying to guard
   the far side. Costs you delegation during the spec phases, which is the phase
   where you should not be delegating implementation anyway.
2. **Pair the plugin with agent-level `permission` config** so subagents are
   independently constrained. Weaker — see #6396.
3. **Accept it and say so.** The gate raises cost, does not close the hole.

Recommend (1). It is the only one that actually holds, and it happens to align with
the workflow: nothing should be implementing before `implement`.

---

## Mechanism mapping

| Claude Code | opencode | Fidelity |
|---|---|---|
| `PreToolUse` hook, `permissionDecision: "deny"` | `tool.execute.before`, **throw an Error** | Good. Thrown message surfaces to the model as the tool error |
| Matcher `^(Edit\|Write\|NotebookEdit\|MultiEdit)$` | Branch on `input.tool` in JS | Good, but **names differ** — see below |
| `UserPromptSubmit` → `additionalContext` | **No equivalent** | **Lost.** No per-turn deterministic injection point |
| `.claude/skills/<name>/SKILL.md` + `/name` | `.opencode/command/<name>.md` | Good |
| `disable-model-invocation: true` | **No equivalent** | **Lost.** See "The approval problem" |
| `settings.json` `hooks` block | `.opencode/plugins/*.ts`, auto-loaded | Good |
| Hooks fire inside subagents | They do not | **Broken.** See above |

### Tool names are lowercase and different

Do not port the matcher literally. opencode's mutating tools are `edit`, `write`,
`patch`. Note the trap from the plugin guides: the patch tool reports as
`apply_patch` and carries `output.args.patchText`, **not** `output.args.filePath` —
a gate keyed only on `filePath` silently lets every patch through. That is the same
class of error as a monitor that greps only for success: it looks like it is working
because it never fires.

---

## The approval problem

The Claude Code design rests on `disable-model-invocation: true`. That field is why
`/spec-approve` is a human act the model cannot perform, and it is what makes the
whole thing a gate rather than a suggestion. **opencode commands have no such flag** —
a command file is a prompt template, and nothing stops the agent from doing whatever
the template says by itself.

So the authority has to move out of the command and into the filesystem, guarded by
the same plugin:

- The plugin denies **`bash`** whenever the command line touches `state.json`
  (`spec_state.py approve`, `jq`, `sed`, `>` redirection, `python -c`), *unless* an
  environment marker set only by the operator's own shell is present.
- Approval becomes something you do **outside the agent** — you run
  `python spec_state.py approve requirements` in your own terminal, not through the
  agent's bash tool.

That is strictly more awkward than Claude Code's version, and it is the honest
price of the port. Do not paper over it: an approval command the agent can run is
not an approval gate, and shipping one would be worse than shipping nothing, because
you would believe you had a gate.

---

## The plugin

`~/.config/opencode/plugins/spec-gate.ts` (global) or `.opencode/plugins/spec-gate.ts`
(project). Auto-loaded at startup; load order is global config → project config →
global plugin dir → project plugin dir, all hooks running in sequence.

```ts
import type { Plugin } from "@opencode-ai/plugin"
import * as fs from "node:fs"
import * as path from "node:path"

// Mutating tools. Lowercase, and `apply_patch` carries patchText not filePath.
const MUTATING = new Set(["edit", "write", "patch", "apply_patch"])
// Delegation is denied while unapproved: subagent tool calls are NOT hooked
// (opencode#5894), so the only way to hold the wall is to remove the route.
const DELEGATING = new Set(["task", "agent"])

const PHASES = ["requirements", "design", "tasks", "implement"]
const EXEMPT = [/\/\.spec\//, /\/\.opencode\//, /\/\.git\//, /\.md$/, /\.txt$/]

function findSpecRoot(start: string): string | null {
  let cur = path.resolve(start)
  for (;;) {
    const c = path.join(cur, ".spec")
    if (fs.existsSync(c) && fs.statSync(c).isDirectory()) return c
    const up = path.dirname(cur)
    if (up === cur) return null
    cur = up
  }
}

function loadState(root: string, feature: string): any | null {
  try {
    const d = JSON.parse(fs.readFileSync(
      path.join(root, "specs", feature, "state.json"), "utf8"))
    return typeof d === "object" && !Array.isArray(d) ? d : null
  } catch { return null }
}

function resolveActive(root: string): string | null {
  try {
    const a = fs.readFileSync(path.join(root, "ACTIVE"), "utf8").trim()
    if (a && loadState(root, a)) return a
  } catch { /* fall through to inference */ }
  try {
    const ready = fs.readdirSync(path.join(root, "specs"))
      .filter(n => loadState(root, n)?.phase === "implement")
    return ready.length === 1 ? ready[0] : null   // ambiguity is never guessed
  } catch { return null }
}

function targetPath(tool: string, args: any): string {
  if (tool === "apply_patch" || tool === "patch") {
    // patchText names its files inline; extract or treat as unresolvable.
    const m = /^(?:\*\*\*\s+)?(?:Update|Add|Delete) File:\s*(.+)$/m
      .exec(args?.patchText ?? "")
    return m ? m[1].trim() : "<patch>"
  }
  return args?.filePath ?? args?.path ?? ""
}

export const SpecGate: Plugin = async ({ directory }) => {
  return {
    "tool.execute.before": async (input: any, output: any) => {
      const root = findSpecRoot(directory)
      if (!root) return                                  // repo not armed
      if (process.env.SPEC_GATE?.toLowerCase() === "off") return
      if (fs.existsSync(path.join(root, "BYPASS"))) return

      const feature = resolveActive(root)
      const state = feature ? loadState(root, feature) : null
      const phase = state?.phase
      const unlocked = phase === "implement"

      // Close the subagent hole by denying delegation until implement.
      if (DELEGATING.has(input.tool) && !unlocked) {
        throw new Error(
          `SPEC GATE: delegation is blocked while spec '${feature ?? "(none)"}' ` +
          `is in phase '${phase ?? "none"}'. Subagent tool calls are not ` +
          `intercepted by this hook (opencode#5894), so delegating here would ` +
          `bypass the gate. Finish and approve the spec phases first.`)
      }

      if (!MUTATING.has(input.tool)) return

      const p = targetPath(input.tool, output.args).replace(/\\/g, "/")
      // A patch whose target cannot be resolved must NOT be waved through.
      if (p !== "<patch>" && path.basename(p) !== "state.json"
          && EXEMPT.some(rx => rx.test(p))) return

      if (!feature) {
        throw new Error(
          `SPEC GATE: this repo is spec-driven (${root}) but no spec governs ` +
          `this edit. Open one with spec_state.py new <name>.`)
      }
      if (state === null) {
        throw new Error(`SPEC GATE: state.json for '${feature}' is unreadable.`)
      }
      // Confusion fails OPEN: state.json is itself unwritable here, so denying
      // on a malformed phase would deadlock the repo with no route back.
      if (!PHASES.includes(phase)) return

      if (!unlocked) {
        const done = Object.entries(state.approvals ?? {})
          .filter(([, v]) => v).map(([k]) => k).join(", ") || "nothing yet"
        throw new Error(
          `SPEC GATE: spec '${feature}' is in phase '${phase}', not 'implement'. ` +
          `Approved so far: ${done}. The OPERATOR must approve '${phase}' from ` +
          `their own terminal before source edits are allowed.`)
      }

      const scope: string[] = state.scope ?? []
      if (scope.length && !scope.some(g => new RegExp(
            "^" + g.replace(/[.+^${}()|[\]\\]/g, "\\$&")
                   .replace(/\*\*/g, " ").replace(/\*/g, "[^/]*")
                   .replace(/ /g, ".*") + "$").test(p.replace(/^.*?\/(?=src|lib)/, "")))) {
        throw new Error(
          `SPEC GATE: '${p}' is outside spec '${feature}' scope (${scope.join(", ")}).`)
      }
    },
  }
}
```

**Reuse `spec_state.py` and `spec_paths.py` unchanged.** They are plain Python with
no Claude Code dependency — the phase machine, atomic writes, and `status` output
port as-is. Only the *gate* is rewritten, because only the gate touches the harness.
Do not reimplement the state machine in TypeScript; two copies of the phase model
will drift, which is the exact reason `spec_paths.py` exists in the original.

---

## Commands

`.opencode/command/spec-new.md` (and `spec-next`, `spec-status`):

```markdown
---
description: Open a new spec and draft its requirements
agent: build
---

Run `python ~/.claude/hooks/spec_state.py new $ARGUMENTS`, then draft
`.spec/specs/<name>/requirements.md` in EARS notation. Stop there. Do not draft
design.md and do not touch source. Tell the operator to review and approve from
their own terminal.
```

**Do not create a `spec-approve` command.** There is no way to stop the agent from
invoking it, so its existence would be a lie about where the authority sits.
Approval lives in your shell.

---

## Config placement warning

opencode resolves config from **`~/.config/opencode/`**, not from a dev repo copy,
and the settings are spread across several files — `opencode.json` / `.jsonc`, the
npm bundle's own json, `skills/agents/*.toml`, `skills/codex-agents/*.toml`, and
`agents/*.md` frontmatter. **`.jsonc` is loaded in preference to `.json` when both
exist** — check the extension before editing, or you will edit a shadowed file and
believe the change landed.

---

## Verification — none of this has been run

Port the Python battery first; it is harness-independent and already covers the
phase logic. Then, for the plugin specifically:

1. **Prove the deny fires before proving the allow does.** A gate validated only on
   the happy path is not validated.
2. **`apply_patch` probe, explicitly.** Confirm a patch-tool edit to an out-of-scope
   file is denied. This is the most likely silent failure in the port: if the gate
   reads `filePath` on a patch it gets `undefined`, and every patch sails through
   while the battery still looks green.
3. **Subagent probe.** Ask the primary agent to delegate an edit to a subagent and
   confirm it is refused. If it is not, the delegation denial is not working and
   the gate is primary-agent-only — report that plainly rather than assuming #5894
   was fixed.
4. **Confirm the plugin actually loaded.** File contents and resolved config are not
   the same thing. Check `client.app.log()` output at startup, and run a real
   `opencode run` that attempts a blocked edit — a config check alone is necessary
   but not sufficient.
5. Regression: an unarmed repo must be completely untouched.

## What is lost relative to Claude Code

| Lost | Consequence |
|---|---|
| `disable-model-invocation` | Approval must move to your terminal; no in-agent approval command is safe |
| `UserPromptSubmit` injection | No per-turn phase reminder. Nearest substitute is a line in `AGENTS.md`, which is advisory |
| Hooks inside subagents | Closed only by denying delegation outright |
| `permissionDecision: "deny"` semantics | A thrown error reads as a tool failure rather than a policy decision; expect more retry behavior |

## Sources

- [opencode plugins](https://opencode.ai/docs/plugins/) — hook list, signature, load order, file locations
- [opencode tools](https://opencode.ai/docs/tools/) — tool names
- [opencode#5894](https://github.com/anomalyco/opencode/issues/5894) — subagent bypass
- [opencode#6396](https://github.com/sst/opencode/issues/6396) — SDK permission denies ignored
