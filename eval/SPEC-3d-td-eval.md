# 3D Tower Defense — Harness Comparative Eval

## Bounded six-arm rerun for Todo #4

- When this rerun starts, the evaluator shall create six isolated Git roots with the same SDL2 seed and the existing per-harness gate-on or gate-off instructions.
- When the evaluator dispatches an arm, it shall use the common `td-p1.md` workload with the CMake configure command adjusted for x64 MSVC already on PATH and the Ninja Multi-Config generator. The same prompt bytes shall reach all six arms.
- When two gate conditions run on the same harness, the evaluator shall use the same model and client settings for both. The batch shall use native code tools and project instructions, with external tool servers and delegation disabled where the client supports it. Cross-harness comparisons shall identify any provider or model differences.
- When OpenCode is used, the evaluator shall place `compaction.auto: false` in the arm-local `opencode.json` so the matched OpenCode arms share the same context behavior without changing user-level settings. The OpenCode probe shall be selectable by client and shall run alone before the full batch.
- Before dispatch, the evaluator shall record the prompt hash, gate-instruction hash per arm, client versions, configured model, and tool or extension settings. Each arm shall have its own project root and client state directory.
- When an arm instruction file is copied, the evaluator shall verify client discovery: Claude Code reads `CLAUDE.md`; Pi and OpenCode read `AGENTS.md`. If discovery cannot be evidenced, the affected comparison shall remain unscored.
- When the batch runs, the evaluator shall reserve time for independent verification within a single 15-minute wall clock limit. When an arm reaches the generation cutoff, the evaluator shall stop the arm's process tree and distinguish a timeout from a completed response.
- When generation ends, the evaluator shall count authored C or C++ source and header files and their physical lines, excluding build output, the SDL2 seed, and other vendored toolchains. It shall configure and build each available CMake project into a fresh directory, then test its executable for a live process and a visible window after five seconds.
- If an arm produces no buildable project or the check cannot run, the evaluator shall record the reason per arm. When the rerun ends, the evaluator shall save a single comparison with model, project instruction variant, runner exit, build and launch results, file and line counts, and supporting logs. The first response per arm is the unit of this comparison.

This bounded rerun scores the first response, independent CMake build, and five-second process/window launch only. It does not score pathfinding, combat, waves, win/loss, or the former 30-step progression protocol. Those broader gameplay results remain unverified.

The sections below document the earlier 30-step protocol and its original client setup. Todo #4 used the bounded configuration and exact versions recorded in `eval/results/3d-td/comparison.md`; do not use the historical model/provider table below as the current run manifest.

## Objective

Measure steps-to-working-game across 3 harnesses (pi, opencode, claude) on the same task: build a 3D tower defense game with a custom engine from scratch. No frameworks, no game engines. The harness that reaches the acceptance gate in fewer steps wins. Cap: 30 steps. If none reach it, lower the difficulty class.

## Harnesses Under Test — earlier 30-step configuration

| Harness | Provider | Model | Enforcement | Notes |
|---------|----------|-------|-------------|-------|
| pi | OpenRouter (litellm) | claude-sonnet-4 | native (inherits Claude hooks) | Has transcript persistence |
| opencode | OpenRouter | claude-sonnet-4 | advisory only | No hooks, no subagents |
| claude | Anthropic direct | claude-sonnet-5 | native | Full hooks + subagents |

All 3 get the same prompt, same MCP servers (specs, memory-index, retrieve-skills), same working directory structure. The only variable is the harness.

## What Counts as a "Step"

One step = one user prompt → harness response cycle that produces code changes. Clarification questions, planning-only responses, and tool-call-only responses that don't write files don't count. A step that writes code but fails to compile still counts.

## Acceptance Gate (the game works when ALL pass)

1. **Renders** — window opens, 3D scene visible (camera, lit ground plane, at least one 3D object)
2. **Pathfinding** — enemies spawn at point A, follow a 3D path to point B (not hardcoded waypoints — actual pathfinding)
3. **Tower placement** — mouse click raycasts into world, places a tower at the intersection point
4. **Combat** — towers detect enemies in range, fire projectiles, enemies lose HP, die at 0
5. **Waves** — at least 3 waves with increasing enemy count, pause between waves
6. **Win/Lose** — player loses lives when enemies reach the end, game over at 0 lives, victory after final wave

## Verification (automated where possible)

- Gate 1: process launches, no crash within 5 seconds, window handle exists
- Gate 2: enemy entity count increases then decreases over 30 seconds of runtime
- Gate 3: click event at screen center produces a new tower entity (check stdout/log)
- Gate 4: tower entity emits projectile entity, enemy HP decreases (check stdout/log)
- Gate 5: wave counter increments 3 times within 120 seconds of gameplay
- Gate 6: lives counter decrements OR victory state reached

Manual verification (visual): screenshot at 10s, 30s, 60s — confirms 3D rendering, not just a blank window.

## Constraints (same for all harnesses)

- Language: C++ (C++17 or later)
- Windowing: SDL2 (already installed at standard paths)
- Rendering: OpenGL 3.3+ core profile (raw, no wrappers)
- Math: GLM or hand-rolled (no engine math libs)
- No external game engines, no ECS frameworks, no physics engines
- Build system: CMake or single-file build script
- Must compile on Windows x64 with MSVC (VS 2026 Build Tools available)
- Total LOC cap: none (but sprawl is a negative signal — fewer files = better)

## Difficulty Ladder (if 30 steps isn't enough)

If no harness reaches the full gate in 30 steps, drop to the next tier:

| Tier | Gate | What's removed |
|------|------|----------------|
| A (full) | All 6 gates | Nothing |
| B | Gates 1-4 | No waves, no win/lose (just infinite spawning + combat) |
| C | Gates 1-2 | No towers, no combat (just rendering + pathfinding) |
| D | Gate 1 only | Just get a 3D scene on screen with SDL2+OpenGL |

Report which tier each harness achieved and at which step.

## Scoring

| Metric | Weight | How measured |
|--------|--------|--------------|
| Steps to Tier D (renders) | 1x | Step number when Gate 1 first passes |
| Steps to Tier C (pathfinding) | 2x | Step number when Gates 1-2 pass |
| Steps to Tier B (combat) | 3x | Step number when Gates 1-4 pass |
| Steps to Tier A (full game) | 5x | Step number when all 6 gates pass |
| Final LOC | 0.5x | Lower is better (normalized: best=1.0, worst=0.5) |
| Final file count | 0.5x | Lower is better (same normalization) |
| Compile errors per step | -0.5x | Total compilation failures across all steps |

Score = sum of (weight × (30 - step_at_tier) / 30) for each tier reached, minus penalties.

## Execution Protocol

1. Each harness gets a fresh git worktree (isolated, no cross-contamination)
2. Same initial prompt (verbatim, stored in `eval/prompts/3d-td.md`)
3. Human operator provides ONLY: the initial prompt, then "continue" or "the build failed with: <error>" or "gate N passed, continue"
4. Human NEVER provides implementation hints, architecture suggestions, or debugging help
5. Each step is logged: timestamp, prompt given, files changed, compile result, gates checked
6. Stop at 30 steps OR all 6 gates pass, whichever comes first

### Batch runner contract

- When `run_td_batch.ps1` launches OpenCode, it shall pass the complete prompt as one positional message argument; OpenCode does not consume this batch prompt from standard input.
- When the batch runner waits for an arm, it shall allow up to 30 minutes before terminating that arm and record the timeout using the same duration.
- When Claude Code or Pi is launched by the batch runner, the prompt shall remain on standard input.
- Given a multi-line prompt containing quotes, when OpenCode is launched, then the received message shall preserve the prompt text as one argument.
- When Pi routes an NVIDIA model alias through LiteLLM, Pi's model registry shall define that exact alias with reasoning disabled so it does not inherit incompatible metadata from another model.
- Given a Pi NVIDIA request, when LiteLLM forwards it, then the request shall not contain the unsupported `enable_thinking` parameter.

## Initial Prompt (given verbatim to each harness)

```
Build a 3D tower defense game from scratch. Requirements:

- C++ with SDL2 for windowing and OpenGL 3.3+ for rendering
- Custom engine (no Unity, Godot, or framework dependencies)
- Enemies spawn, pathfind through a 3D environment to an exit point
- Player clicks to place towers that shoot projectiles at enemies
- 3 waves of increasing difficulty, lives system, win/lose state
- Must compile on Windows with MSVC and run without crashing

Start building. I'll tell you if it compiles and what works.
```

## Output

Per-harness result file in `eval/results/3d-td/`:
- `{harness}-log.jsonl` — one JSON object per step (step_num, prompt, files_changed, compile_ok, gates_passed, notes)
- `{harness}-summary.md` — final score, tier reached, total steps, LOC, file count
- `{harness}-screenshots/` — visual captures at key moments

Final comparison: `eval/results/3d-td/comparison.md` — side-by-side matrix.

## What This Measures

1. **Architecture instinct** — does the harness produce a coherent file structure on step 1, or does it sprawl?
2. **Iteration speed** — how many steps wasted on compile errors vs. feature progress?
3. **Self-correction** — when something doesn't compile, does it fix efficiently or patch-on-patch?
4. **Scope control** — does it over-engineer (ECS framework before a triangle renders) or bottom-up (triangle → cube → scene → game)?
5. **Harness overhead** — does the SDD infrastructure (specs, hooks, steering) help or slow things down?

The SDD harness (pi, opencode) has access to specs MCP, memory-index, retrieve-skills. Claude Code has its own hooks and transcript. If the SDD infrastructure causes sprawl (the harness spends steps writing specs instead of code), that shows up as a higher step count. If it helps (the harness avoids dead ends because of prior decisions), that shows up as a lower step count.
