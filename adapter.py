"""Cross-harness MCP projection from the ~/.harness registry.

Pipeline:
| Stage | Mechanism | Tag | Requirements |
|---|---|---|---|
| LOAD | Read harness.json as the canonical server registry | [mandatory] | R1 |
| PROJECT | Render each registered server in the native client schema, including Hermes via its native writer | [mandatory] | R1, R2, R7 |
| CLEAN | Remove only the exact retired C: Graphify hook commands before projecting current hooks | [mandatory] | R8 |
| WRITE | Merge through harness_write so backups and atomic writes apply | [mandatory] | R3 |
| VERIFY | Native clients load their registered servers and unmanaged entries survive | [contract] | R4 |

R1: WHEN a target sync runs, it MUST project only the central harness registry.
R2: Each target MUST use its user-level native configuration path and schema.
R3: Existing configuration MUST be backed up before any changed bytes are written.
R4: WHEN a target supports MCP, sync MUST preserve unmanaged entries and be repeatable.
R5: WHERE a client has no MCP transport, its existing supported integration MUST remain intact.
R6: WHEN a local server is projected to OpenCode, its documented per-server tool-fetch timeout MUST
allow the measured cold-start window for isolated F: Python environments.
R7: When Hermes sync runs, the system shall project every registry entry through Hermes' own
non-interactive MCP config writer and preserve unrelated Hermes settings and MCP entries.
R8: When native hook projections are synchronized, the system shall remove only the exact retired
C:/Users/user/.local/bin/graphify.EXE hook commands and preserve every unrelated hook.
CLOSED: A separate OpenAI-only registry is rejected because ~/.harness is the shared
cross-harness source. Interactive `hermes mcp add` is rejected because it performs server
discovery and prompts; Hermes' `_save_mcp_server` is the native non-interactive writer. Scalar-only
`hermes config set` is rejected because it cannot create registry entries with argument arrays.
Pi MCP projection is rejected because the installed Pi integration is its retrieval extension,
not an MCP client.

Preconditions: the registry is valid JSON and harness_write.py is available beside this file.
Failure modes: malformed config or unsafe writes raise; target-specific parse failures do not overwrite.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

HARNESS_CONFIG = Path(__file__).parent / "harness.json"
HARNESS_AGENTS = Path(__file__).parent / "claude" / "AGENTS.md"
VSCODE_SHIM = Path(__file__).resolve().parent / "hooks" / "vscode_shim.py"
# SessionEnd has no VS Code equivalent; SubagentStart/Stop have no Claude-settings hooks to run.
VSCODE_HOOK_EVENTS = ("SessionStart", "UserPromptSubmit", "PreToolUse", "PostToolUse", "PreCompact", "Stop")
OPENCODE_LOCAL_TIMEOUT_MS = 240000
RETIRED_GRAPHIFY_HOOK_COMMANDS = frozenset({
    "C:/Users/user/.local/bin/graphify.EXE hook-guard search",
    "C:/Users/user/.local/bin/graphify.EXE hook-guard read",
    "C:/Users/user/.local/bin/graphify.EXE hook-check",
})


def load_harness() -> dict:
    return json.loads(HARNESS_CONFIG.read_text(encoding="utf-8"))


def write_server_projection(path: Path, key: str, servers: dict, *, jsonc: bool = False) -> bool:
    """Merge registered servers into a native config and write through the harness backup path.

    Require: `servers` contains only this adapter's registered MCP names.
    Guarantee: unrelated root keys and unregistered servers survive; changed files are backed up.
    Maintain: target-owned server entries are replaced as complete values on every run.
    Assert: the result remains valid JSON before handing it to the safe atomic writer.
    """
    import harness_write

    existing = harness_write.read_existing(path)
    data = harness_write.load_jsonc(existing) if existing else {}
    current = data.get(key, {})
    if not isinstance(current, dict):
        raise harness_write.WriteError(f"{path}: expected an object at {key!r}")
    data[key] = {**current, **servers}
    rendered = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    artifact = harness_write.Artifact(path=path, text=rendered, mode="file")
    changes = harness_write.plan([artifact])
    return bool(harness_write.apply(changes, Path.home() / ".harness" / "backups"))


def ensure_global_hooks(path: Path, hooks: list[dict]) -> bool:
    """Append each declared hook to `path` (a Claude-format hooks JSON) unless already present.

    Require: `path` holds JSON(C) or is absent; each hook has event, command, optional matcher/timeout.
    Guarantee: every other hook in the file is untouched (deep_merge would replace the event's
        whole list); a hook is identified by (event, matcher, command), so reruns are no-ops.
    Returns: True when the file was written.
    """
    import harness_write

    existing = harness_write.read_existing(path)
    data = harness_write.load_jsonc(existing) if existing else {}
    events = data.setdefault("hooks", {})
    for hook in hooks:
        groups = events.setdefault(hook["event"], [])
        matcher = hook.get("matcher")
        if any(g.get("matcher") == matcher and h.get("command") == hook["command"]
               for g in groups for h in g.get("hooks", [])):
            continue
        entry = {"type": "command", "command": hook["command"]}
        if "timeout" in hook:
            entry["timeout"] = hook["timeout"]
        group = {"hooks": [entry]}
        if matcher:
            group = {"matcher": matcher, **group}
        groups.append(group)
    artifact = harness_write.Artifact(path=path, text=json.dumps(data, indent=2), mode="file")
    return bool(harness_write.apply(harness_write.plan([artifact]), Path.home() / ".harness" / "backups"))


def remove_retired_graphify_hooks(path: Path) -> bool:
    """Remove only the known retired C: Graphify hook commands from one hook file.

    Require: `path` is a native JSON(C) hook file or does not exist.
    Guarantee: exact retired commands are removed; all other hook entries and settings survive.
    Maintain: event order and mixed hook groups remain unchanged.
    Assert: the safe writer is called only when an exact command was removed.
    """
    import harness_write

    existing = harness_write.read_existing(path)
    if not existing:
        return False
    data = harness_write.load_jsonc(existing)
    events = data.get("hooks", {})
    changed = False
    for event, groups in list(events.items()):
        single_group = isinstance(groups, dict)
        if single_group:
            groups = [groups]
        elif not isinstance(groups, list):
            continue
        kept_groups = []
        for group in groups:
            if not isinstance(group, dict):
                kept_groups.append(group)
                continue
            hooks = group.get("hooks", [])
            if not isinstance(hooks, list):
                kept_groups.append(group)
                continue
            kept_hooks = [hook for hook in hooks if not isinstance(hook, dict)
                          or hook.get("command") not in RETIRED_GRAPHIFY_HOOK_COMMANDS]
            group_changed = len(kept_hooks) != len(hooks)
            changed = changed or group_changed
            if kept_hooks or not group_changed:
                group["hooks"] = kept_hooks
                kept_groups.append(group)
        if kept_groups:
            events[event] = kept_groups[0] if single_group and len(kept_groups) == 1 else kept_groups
        else:
            del events[event]
    if not changed:
        return False
    artifact = harness_write.Artifact(path=path, text=json.dumps(data, indent=2), mode="file")
    return bool(harness_write.apply(harness_write.plan([artifact]), Path.home() / ".harness" / "backups"))


def sync_global_hooks(config: dict, harness: str) -> None:
    """Install config["global_hooks"][harness] into that harness's hooks file(s).

    claude: the live ~/.claude/settings.json AND the vault copy (the vault is the source that
    sync-to-claude.ps1 pushes, so a hook only in the live file would be pushed away).
    codex: ~/.codex/hooks.json.
    """
    hooks = config.get("global_hooks", {}).get(harness, [])
    if not hooks:
        return
    home = Path.home()
    paths = {"claude": [home / ".claude" / "settings.json", home / ".harness" / "claude" / "settings.json"],
             "codex": [home / ".codex" / "hooks.json"]}[harness]
    for path in paths:
        removed = remove_retired_graphify_hooks(path)
        state = "updated" if ensure_global_hooks(path, hooks) else "unchanged"
        if removed and state == "unchanged":
            state = "cleaned"
        print(f"  {harness} global hooks: {state} {path} ({len(hooks)} declared)")


def sync_claude_code(config: dict) -> None:
    """Update ~/.claude.json with MCP servers from harness config."""
    claude_json = Path.home() / ".claude.json"
    servers = {}
    for name, srv in config["mcp_servers"].items():
        if srv["type"] == "http":
            servers[name] = {"type": "http", "url": srv["url"]}
        else:
            entry = {"type": "stdio", "command": srv["command"], "args": srv.get("args", [])}
            if srv.get("env"):
                entry["env"] = srv["env"]
            servers[name] = entry

    changed = write_server_projection(claude_json, "mcpServers", servers)
    print(f"  Claude Code: {'updated' if changed else 'unchanged'} {claude_json} ({len(servers)} servers)")
    sync_global_hooks(config, "claude")


def sync_opencode(config: dict) -> None:
    """Project the central registry into OpenCode's native MCP schema.

    Require: the registry uses `http` or `stdio` transport entries.
    Guarantee: remote HTTP and local command forms match OpenCode's schema; local tools receive
        enough catalog time for the measured cold start of their F: environments.
    Maintain: existing unmanaged root keys and MCP names survive the safe writer merge.
    Assert: the generated object is valid JSONC and preserves each server's transport.
    """
    oc_json = Path.home() / ".config" / "opencode" / "opencode.json"
    if not oc_json.exists():
        print("  opencode: config not found, skipping")
        return

    # opencode uses JSONC; harness_write.load_jsonc handles // and /* */ comments and trailing commas
    # while respecting strings (the old line-start regex mangled '//' inside values).
    import harness_write

    text = oc_json.read_text(encoding="utf-8")
    try:
        data = harness_write.load_jsonc(text)
    except harness_write.WriteError:
        print("  opencode: failed to parse config, skipping")
        return

    mcp = {}
    for name, srv in config["mcp_servers"].items():
        if srv["type"] == "http":
            mcp[name] = {"type": "remote", "url": srv["url"], "enabled": True}
        else:
            entry = {"type": "local", "command": [srv["command"]] + srv.get("args", []), "enabled": True}
            entry["timeout"] = OPENCODE_LOCAL_TIMEOUT_MS
            if srv.get("env"):
                entry["environment"] = srv["env"]
            mcp[name] = entry

    changed = write_server_projection(oc_json, "mcp", mcp, jsonc=True)
    print(f"  opencode: {'updated' if changed else 'unchanged'} {oc_json} ({len(mcp)} servers)")


def sync_kiro(config: dict) -> None:
    """Update ~/.kiro/settings/mcp.json."""
    kiro_json = Path.home() / ".kiro" / "settings" / "mcp.json"
    kiro_json.parent.mkdir(parents=True, exist_ok=True)

    servers = {}
    for name, srv in config["mcp_servers"].items():
        if srv["type"] == "http":
            servers[name] = {"url": srv["url"], "disabled": False}
        else:
            entry = {"command": srv["command"], "args": srv.get("args", []), "disabled": False}
            if srv.get("env"):
                entry["env"] = srv["env"]
            servers[name] = entry

    changed = write_server_projection(kiro_json, "mcpServers", servers)
    print(f"  Kiro: {'updated' if changed else 'unchanged'} {kiro_json} ({len(servers)} servers)")


def sync_pi(config: dict) -> None:
    """Keep Pi's installed retrieval extension; Pi does not load these MCP entries."""
    print("  pi: retained the existing retrieve-skills extension (no MCP config written)")


def sync_hermes(config: dict) -> None:
    """Project registry servers through Hermes' native MCP config writer.

    Require: `hermes` is installed in a virtual environment with its sibling Python executable.
    Guarantee: managed entries match harness.json and Hermes preserves unrelated config values.
    Maintain: Hermes owns serialization and validation; harness_write never opens credential files.
    Assert: every registry entry is accepted by Hermes or the subprocess fails visibly.
    """
    hermes = shutil.which("hermes")
    if not hermes:
        raise FileNotFoundError("Hermes executable was not found on PATH")
    python = Path(hermes).with_name("python.exe")
    if not python.is_file():
        raise FileNotFoundError(f"Hermes virtual-environment Python was not found: {python}")

    servers = {}
    for name, server in config["mcp_servers"].items():
        entry = {"enabled": True}
        if server["type"] == "http":
            entry["url"] = server["url"]
        else:
            entry["command"] = server["command"]
            entry["args"] = server.get("args", [])
            if server.get("env"):
                entry["env"] = server["env"]
        servers[name] = entry

    writer = (
        "import json, sys\n"
        "from hermes_cli.mcp_config import _save_mcp_server\n"
        "payload = json.load(sys.stdin)\n"
        "failed = [name for name, config in payload.items() if not _save_mcp_server(name, config)]\n"
        "if failed:\n"
        "    print(json.dumps({'rejected': failed}))\n"
        "    raise SystemExit(1)\n"
        "print(json.dumps({'saved': list(payload)}))\n"
    )
    result = subprocess.run(
        [str(python), "-c", writer],
        input=json.dumps(servers),
        text=True,
        capture_output=True,
        check=True,
        env=os.environ.copy(),
    )
    print(f"  Hermes: projected {len(servers)} servers through Hermes config writer")
    if result.stdout.strip():
        print(f"  Hermes writer: {result.stdout.strip()}")


MCP_TOML_BEGIN = "# >>> harness mcp servers (generated by ~/.harness; edit harness.json, not this block) >>>"
MCP_TOML_END = "# <<< harness mcp servers <<<"


def codex_mcp_block(config: dict) -> str:
    """Render every server in config["mcp_servers"] as a Codex [mcp_servers.<name>] TOML table."""
    lines = []
    for name, srv in config["mcp_servers"].items():
        lines.append(f"[mcp_servers.{name}]")
        if srv["type"] == "http":
            lines.append(f"url = {json.dumps(srv['url'])}")
        else:
            lines.append(f"command = {json.dumps(srv['command'])}")
            lines.append(f"args = {json.dumps(srv.get('args', []))}")
            if srv.get("env"):
                lines.append(f"[mcp_servers.{name}.env]")
                for k, v in srv["env"].items():
                    lines.append(f"{json.dumps(k)} = {json.dumps(str(v))}")
        lines.append("")
    return "\n".join(lines)


def sync_codex(config: dict) -> None:
    """Write Codex CLI MCP config.

    Codex uses AGENTS.md for steering (same as the skills repo root).
    Codex reads MCP servers from [mcp_servers.<name>] tables in ~/.codex/config.toml,
    not from mcp.json. The harness servers live in one marker-delimited block of that
    file; everything outside the block is untouched.

    Raises:
        RuntimeError: config.toml already defines [mcp_servers.<name>] outside the block
            for a harness server (a duplicate table makes Codex fail to load its config).
    """
    import re

    import harness_write

    block = codex_mcp_block(config)
    path = Path.home() / ".codex" / "config.toml"
    artifact = harness_write.Artifact(path=path, text=block, mode="tomlblock",
                                      begin=MCP_TOML_BEGIN, end=MCP_TOML_END)
    changes = harness_write.plan([artifact])

    outside = changes[0].before or ""
    if MCP_TOML_BEGIN in outside and MCP_TOML_END in outside:
        a = outside.index(MCP_TOML_BEGIN)
        b = outside.index(MCP_TOML_END, a) + len(MCP_TOML_END)
        outside = outside[:a] + outside[b:]
    for name in config["mcp_servers"]:
        if re.search(rf"^\s*\[mcp_servers\.{re.escape(name)}(\.[^\]]*)?\]", outside, re.M):
            raise RuntimeError(
                f"{path} already defines [mcp_servers.{name}] outside the generated block; "
                "remove it or the duplicate table breaks Codex config loading"
            )

    written = harness_write.apply(changes, Path.home() / ".harness" / "backups")
    state = "updated" if written else "unchanged"
    print(f"  Codex: {state} {path} ({len(config['mcp_servers'])} servers)")


CODEX_FEATURE_COMMAND = ("c:/users/user/py310/Scripts/python.exe "
                         "C:/Users/user/.claude/hooks/playbook.py --feature")


def sync_codex_hooks(config: dict) -> None:
    """Make ~/.codex/hooks.json carry our UserPromptSubmit `feature:` hook.

    Other events and hooks in the file are preserved (jsonmerge).

    Raises:
        RuntimeError: the file already has a UserPromptSubmit entry that is not ours.
    """
    import harness_write

    path = Path.home() / ".codex" / "hooks.json"
    entry = {"hooks": [{"type": "command", "command": CODEX_FEATURE_COMMAND, "timeout": 30}]}
    existing = harness_write.read_existing(path)
    if existing:
        data = harness_write.load_jsonc(existing)
        for group in (data.get("hooks") or {}).get("UserPromptSubmit") or []:
            for h in group.get("hooks") or []:
                if h.get("command") != CODEX_FEATURE_COMMAND:
                    raise RuntimeError(
                        f"{path} already has a UserPromptSubmit hook not ours "
                        f"({h.get('command')!r}); remove it or merge by hand")
    patch = json.dumps({"hooks": {"UserPromptSubmit": [entry]}})
    artifact = harness_write.Artifact(path=path, text=patch, mode="jsonmerge")
    written = harness_write.apply(harness_write.plan([artifact]),
                                  Path.home() / ".harness" / "backups")
    print(f"  Codex hooks: {'updated' if written else 'unchanged'} {path}")


def sync_github_copilot(config: dict) -> None:
    """Merge GitHub Copilot CLI MCP config at the user-level path."""
    copilot_json = Path.home() / ".copilot" / "mcp-config.json"

    servers = {}
    for name, srv in config["mcp_servers"].items():
        if srv["type"] == "http":
            servers[name] = {"type": "http", "url": srv["url"]}
        else:
            entry = {"type": "stdio", "command": srv["command"], "args": srv.get("args", [])}
            if srv.get("env"):
                entry["env"] = srv["env"]
            servers[name] = entry

    changed = write_server_projection(copilot_json, "mcpServers", servers)
    print(f"  GitHub Copilot: {'updated' if changed else 'unchanged'} {copilot_json} ({len(servers)} servers)")


def vscode_user_dir() -> Path:
    """VS Code user-profile directory (holds the user-level mcp.json)."""
    if sys.platform == "win32":
        return Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / "Code" / "User"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Code" / "User"
    return Path.home() / ".config" / "Code" / "User"


def vscode_pointer_section() -> str:
    """Absolute paths of the files the core text refers to; VS Code does not follow @-imports."""
    home = Path.home()
    rules = sorted((home / ".claude" / "rules").glob("*.md"))
    lines = [
        "\n\n## Where the rest lives\n\n",
        "This file is the compact core. Read these on demand with your file tools:\n\n",
        f"- Constitution (gates, Articles I-XV): `{home / '.harness' / 'constitution.md'}`\n",
        f"- Glossary (overloaded terms): `{home / '.skills' / 'GLOSSARY.md'}`\n",
    ]
    lines += [f"- Rule `{p.stem}`: `{p}`\n" for p in rules]
    return "".join(lines)


def sync_vscode(config: dict) -> None:
    """Merge harness MCP servers into VS Code's user mcp.json.

    VS Code uses the top-level key "servers" (not "mcpServers"). Servers and
    "inputs" the harness does not manage are preserved. Also writes the
    operating core to prompts/harness-core.instructions.md, the only prompts
    file this function touches.
    """
    vscode_json = vscode_user_dir() / "mcp.json"
    vscode_json.parent.mkdir(parents=True, exist_ok=True)
    data = json.loads(vscode_json.read_text(encoding="utf-8")) if vscode_json.exists() else {}

    servers = {}
    for name, srv in config["mcp_servers"].items():
        if srv["type"] == "http":
            servers[name] = {"type": "http", "url": srv["url"]}
        else:
            entry = {"type": "stdio", "command": srv["command"], "args": srv.get("args", [])}
            if srv.get("env"):
                entry["env"] = srv["env"]
            servers[name] = entry

    changed = write_server_projection(vscode_json, "servers", servers)
    print(f"  VS Code: {'updated' if changed else 'unchanged'} {vscode_json} ({len(servers)} servers)")

    prompts_dir = vscode_json.parent / "prompts"
    prompts_dir.mkdir(exist_ok=True)
    core = prompts_dir / "harness-core.instructions.md"
    core.write_text(
        "---\napplyTo: '**'\n---\n\n"
        "<!-- Generated by ~/.harness/adapter.py from claude/AGENTS.md. Do not edit. -->\n"
        "<!-- Hooks run here through ~/.copilot/hooks/harness.json -> hooks/vscode_shim.py. -->\n"
        "<!-- Not ported: verify_gate and session_handoff (need Claude's transcript), SessionEnd. -->\n\n"
        + HARNESS_AGENTS.read_text(encoding="utf-8")
        + vscode_pointer_section(),
        encoding="utf-8",
    )
    print(f"  VS Code: updated {core}")
    sync_vscode_hooks()


def sync_vscode_hooks() -> None:
    """Point every VS Code hook event at hooks/vscode_shim.py (native format).

    VS Code ignores matchers in Claude-format files, so ~/.claude/settings.json
    is NOT read directly (chat.useClaudeHooks stays off); the shim reads it and
    re-applies the matchers itself.
    """
    hooks_json = Path.home() / ".copilot" / "hooks" / "harness.json"
    hooks_json.parent.mkdir(parents=True, exist_ok=True)
    hooks = {
        event: [{
            "type": "command",
            "command": f'"{sys.executable}" "{VSCODE_SHIM}" {event}',
            "timeout": 120,
        }]
        for event in VSCODE_HOOK_EVENTS
    }
    hooks_json.write_text(json.dumps({"hooks": hooks}, indent=2), encoding="utf-8")
    print(f"  VS Code: updated {hooks_json} ({len(hooks)} events via shim)")


def sync_agents(config: dict, apply: bool = False) -> int:
    """Render the party (tiers.toml) into every harness's agent settings.

    Opt-in, not part of `--target all`: it edits agent definitions and session-adjacent
    config. Without `apply` it only prints the diffs (render_agents.py --plan).
    """
    import render_agents

    argv = ["--harness", "all", "--apply" if apply else "--plan"]
    return render_agents.main(argv)


TARGETS = {
    "claude": sync_claude_code,
    "opencode": sync_opencode,
    "kiro": sync_kiro,
    "pi": sync_pi,
    "hermes": sync_hermes,
    "codex": lambda config: (sync_codex(config), sync_codex_hooks(config), sync_global_hooks(config, "codex")),
    "copilot": sync_github_copilot,
    "vscode": sync_vscode,
}
OPT_IN_TARGETS = ("agents",)


def main():
    parser = argparse.ArgumentParser(description="Sync harness config to all targets")
    parser.add_argument("--target", choices=[*TARGETS, *OPT_IN_TARGETS, "all"], default="all")
    parser.add_argument("--apply", action="store_true", help="agents target only: write, instead of showing diffs")
    args = parser.parse_args()

    config = load_harness()
    print(f"Loaded harness.json: {len(config['mcp_servers'])} MCP servers")

    targets = TARGETS

    if args.target == "all":
        for name, fn in targets.items():
            fn(config)
    elif args.target == "agents":
        sync_agents(config, apply=args.apply)
    else:
        targets[args.target](config)

    print("Done.")


if __name__ == "__main__":
    main()
