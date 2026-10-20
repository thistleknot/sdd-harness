"""Cross-harness adapter: reads ~/.harness/harness.json, writes per-harness configs.

Usage: python adapter.py [--target claude|opencode|kiro|pi|codex|copilot|vscode|all]

Ensures all harnesses share the same MCP server registrations and model routing.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

HARNESS_CONFIG = Path(__file__).parent / "harness.json"
HARNESS_AGENTS = Path(__file__).parent / "claude" / "AGENTS.md"
VSCODE_SHIM = Path(__file__).resolve().parent / "hooks" / "vscode_shim.py"
# SessionEnd has no VS Code equivalent; SubagentStart/Stop have no Claude-settings hooks to run.
VSCODE_HOOK_EVENTS = ("SessionStart", "UserPromptSubmit", "PreToolUse", "PostToolUse", "PreCompact", "Stop")


def load_harness() -> dict:
    return json.loads(HARNESS_CONFIG.read_text(encoding="utf-8"))


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
        state = "updated" if ensure_global_hooks(path, hooks) else "unchanged"
        print(f"  {harness} global hooks: {state} {path} ({len(hooks)} declared)")


def sync_claude_code(config: dict) -> None:
    """Update ~/.claude.json with MCP servers from harness config."""
    claude_json = Path.home() / ".claude.json"
    if claude_json.exists():
        data = json.loads(claude_json.read_text(encoding="utf-8"))
    else:
        data = {}

    servers = {}
    for name, srv in config["mcp_servers"].items():
        if srv["type"] == "http":
            servers[name] = {"type": "http", "url": srv["url"]}
        else:
            entry = {"type": "stdio", "command": srv["command"], "args": srv.get("args", [])}
            if srv.get("env"):
                entry["env"] = srv["env"]
            servers[name] = entry

    data["mcpServers"] = {**data.get("mcpServers", {}), **servers}
    claude_json.write_text(json.dumps(data, indent=2), encoding="utf-8")
    print(f"  Claude Code: updated {claude_json} ({len(servers)} servers)")
    sync_global_hooks(config, "claude")


def sync_opencode(config: dict) -> None:
    """Update ~/.config/opencode/opencode.json MCP block."""
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
            mcp[name] = {"type": "streamable-http", "url": srv["url"], "enabled": True}
        else:
            entry = {"type": "local", "command": [srv["command"]] + srv.get("args", []), "enabled": True}
            if srv.get("env"):
                entry["env"] = srv["env"]
            mcp[name] = entry

    data["mcp"] = mcp
    # Write back (without comments — they'll be lost, but config is functional)
    oc_json.write_text(json.dumps(data, indent=2), encoding="utf-8")
    print(f"  opencode: updated {oc_json} ({len(mcp)} servers)")


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

    output = {"mcpServers": servers}
    kiro_json.write_text(json.dumps(output, indent=2), encoding="utf-8")
    print(f"  Kiro: updated {kiro_json} ({len(servers)} servers)")


def sync_pi(config: dict) -> None:
    """Pi inherits Claude Code's MCP config — sync is identical to claude."""
    # Pi uses the same ~/.claude.json as Claude Code (shared user scope)
    # Only difference: pi routes through litellm. MCP registration is the same.
    sync_claude_code(config)
    print("  pi: shares Claude Code MCP config (no separate file)")


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
    """Write GitHub Copilot MCP config to .copilot/mcp.json in workspace."""
    # Copilot MCP lives in the workspace, not user home
    copilot_dir = Path.cwd() / ".copilot"
    copilot_dir.mkdir(parents=True, exist_ok=True)
    copilot_json = copilot_dir / "mcp.json"

    servers = {}
    for name, srv in config["mcp_servers"].items():
        if srv["type"] == "http":
            servers[name] = {"type": "http", "url": srv["url"]}
        else:
            entry = {"type": "stdio", "command": srv["command"], "args": srv.get("args", [])}
            if srv.get("env"):
                entry["env"] = srv["env"]
            servers[name] = entry

    output = {"mcpServers": servers}
    copilot_json.write_text(json.dumps(output, indent=2), encoding="utf-8")
    print(f"  GitHub Copilot: updated {copilot_json} ({len(servers)} servers)")


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

    data["servers"] = {**data.get("servers", {}), **servers}
    vscode_json.write_text(json.dumps(data, indent=2), encoding="utf-8")
    print(f"  VS Code: updated {vscode_json} ({len(servers)} servers)")

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
