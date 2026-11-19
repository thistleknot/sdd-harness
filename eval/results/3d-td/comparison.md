# 3D tower-defense harness comparison

## Current run

- Run: `20261118T174113` (six fresh isolated roots).
- Total elapsed: 656.05 seconds, under the 15-minute limit.
- Game prompt SHA-256: `8931c9ef5c921aa13f22ca3c2e0567da88522bf42fb4506d30c98700d1b66894`.
- Toolchain: CMake 4.1.1, Ninja 1.11.1, MSVC 19.44.35228 x64.
- Client versions: Claude Code 2.1.327, Pi 0.80.2, OpenCode 1.19.5.
- Gate-on and gate-off used the same model and client settings within each harness. The model IDs differ between Claude and the NVIDIA-backed clients.
- Counts include authored C/C++ sources and headers; SDL2, generated, and build files are excluded.

| Harness | Gate | Model | Agent result | Files / LOC | Independent configure / build | Five-second launch |
|---|---|---|---|---:|---|---|
| Claude Code | on | `claude-sonnet-5-5` (Anthropic) | completed, 158.34 s | 5 / 478 | pass / pass | window, `td.exe` |
| Claude Code | off | `claude-sonnet-5-5` (Anthropic) | completed, 173.88 s | 8 / 525 | pass / pass | window, `td3d.exe` |
| Pi | on | `nvidia/nemotron-3.5-lightning-30b-a3b` (LiteLLM/NVIDIA) | timeout, 600.51 s | 0 / 0 | no project / not attempted | not attempted |
| Pi | off | `nvidia/nemotron-3.5-lightning-30b-a3b` (LiteLLM/NVIDIA) | timeout, 600.48 s | 16 / 1,438 | pass / fail: OpenGL types such as `GLuint` were undefined | not attempted |
| OpenCode | on | `nvidia/nemotron-3.5-lightning-30b-a3b` (LiteLLM/NVIDIA) | timeout, 597.84 s | 16 / 1,222 | pass / fail: compiler could not find `SDL.h` | not attempted |
| OpenCode | off | `nvidia/nemotron-3.5-lightning-30b-a3b` (LiteLLM/NVIDIA) | timeout, 597.78 s | 11 / 632 | pass / pass | window, `TowerDefense.exe` |

Each arm's result JSON, input manifest, agent trace, and applicable configure/build/launch logs are in the [run directory](20261118T174113/). The full structured result is [comparison.json](20261118T174113/comparison.json).

## Executables that opened a window

- Claude Code, gates on: `eval/results/3d-td/20261118T174113/claude-gates-on/independent-build/Release/td.exe`
- Claude Code, gates off: `eval/results/3d-td/20261118T174113/claude-gates-off/independent-build/Release/td3d.exe`
- OpenCode, gates off: `eval/results/3d-td/20261118T174113/opencode-gates-off/independent-build/Release/TowerDefense.exe`

The verifier started each executable, confirmed the process survived five seconds and had a nonzero window handle, then stopped it. This checks launch only; it does not establish that the scene rendered correctly or that game mechanics work.

## Interpretation and limits

- In this single run, Claude's gate-on arm compiled with fewer source files and fewer lines than its gate-off arm; both passed the launch check.
- OpenCode's gate-off arm compiled and launched. Its gate-on arm did not compile because the generated code included `SDL.h` while the seed's include path exposed `SDL2/SDL.h`.
- Pi's gate-off arm produced source but failed compilation because OpenGL type declarations were missing. Its gate-on arm spent the cutoff in a recursive search for GLU files and produced no CMake project.
- All four Pi/OpenCode agent calls reached the 10-minute cutoff after receiving the game task. A completed independent build can therefore coexist with an agent timeout.
- The cross-harness comparison is confounded by different models/providers. Each gate pair is matched within its harness, but one run per arm is descriptive evidence, not a repeatable quality estimate.
- Pathfinding, rendered 3D scene quality, tower placement, combat, waves, and win/loss behavior were not evaluated.

OpenCode's private resolved config recorded `compaction.auto: false` for both arms; the [OpenCode compaction docs](https://opencode.ai/docs/compaction/) define this as the automatic-compaction setting. The user's OpenCode configuration was not changed.
