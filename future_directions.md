<!-- NO GOVERNING SPEC. Basis: operator instruction 2026-10-12 ("add in future_directions.md the use of apm and have pi and opencode listed as open questions"). -->
# Future directions

Directions considered and not adopted. Each carries what was observed, what is still unknown, and the cheapest test.

## Use APM to replace the MCP projection in adapter.py

APM is the Agent Package Manager (github.com/microsoft/apm). It reads one manifest and writes instructions, skills, agents, hooks and MCP servers into each client's config. Cloned for review at `.tmp/apm` (scratch, not tracked).

**Intent:** less custom code in `adapter.py`, with the shims kept.

**What it would replace.** The six MCP projection functions (`sync_claude_code`, `sync_opencode`, `sync_kiro`, `sync_pi`, `sync_codex`, `sync_github_copilot`), about 135 of 279 lines. `harness.json` would become `~/.apm/apm.yml` and `apm install -g` would fan it out. It adds a lockfile with content hashes and a drift check (`apm audit`).

**Evidence (observed in the clone, not run):**

```
install.md:59   -g, --global  Install to user scope (~/.apm/) ... deploys only to global-capable runtimes
adapters/client/*.py  supports_user_scope = True for: claude, codex, copilot, gemini, kiro,
                      windsurf, antigravity, hermes, intellij
```

**What stays custom:**
- `sync_vscode`: the VS Code client adapter writes only `.vscode/mcp.json` in the repo (`vscode.py:64`), never `Code\User`.
- `hooks/vscode_shim.py`: APM renames hook events but no map of VS Code tool names to Claude's was found in `src/` or `docs/`. The gates key on `Edit`, `Write` and `Bash`.
- The gates themselves (spec gate, file manifest, source-write guard). APM has no equivalent.

**Cheapest test:** translate a copy of `harness.json` to `apm.yml`, then run `apm install -g --dry-run`. It previews the writes without touching anything.

### Open questions

1. **opencode.** The APM adapter translates to OpenCode's schema correctly (`mcp` key, `command` as an array) but is project-only: `supports_user_scope = False` and the path is `<repo>/opencode.json` (`opencode.py:45,58`). Can a small subclass that points at `~/.config/opencode/opencode.json` reuse APM's translation, or should `sync_opencode` stay? Not tried. Aliasing opencode to the codex or claude adapter is ruled out: it would write the wrong schema.
2. **pi.** There is no pi target in the APM matrix. Today `sync_pi` only calls `sync_claude_code`, because pi reads `~/.claude.json`. If the claude target already writes that file, pi may need nothing of its own. Not confirmed.
3. **stdio servers with env.** All five servers are stdio or http with `env` values. Not confirmed that `apm.yml` expresses these, or that `apm install -g` preserves existing `~/.claude.json` entries.
4. **cursor and vscode user scope.** Both are `supports_user_scope = False` in APM. If either becomes a target, its user-level config stays ours.
