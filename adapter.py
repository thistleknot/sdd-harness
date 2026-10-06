"""Cross-harness adapter: reads ~/.harness/harness.json, writes per-harness configs.

Usage: python adapter.py [--target claude|opencode|kiro|pi|codex|copilot|vscode|all]

Ensures all harnesses share the same MCP server registrations and model routing.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

HARNESS_CONFIG = Path(__file__).parent / "harness.json"
HARNESS_AGENTS = Path(__file__).parent / "claude" / "AGENTS.md"


def load_harness() -> dict:
    return json.loads(HARNESS_CONFIG.read_text(encoding="utf-8"))


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


def sync_opencode(config: dict) -> None:
    """Update ~/.config/opencode/opencode.json MCP block."""
    oc_json = Path.home() / ".config" / "opencode" / "opencode.json"
    if not oc_json.exists():
        print("  opencode: config not found, skipping")
        return

    # opencode uses JSONC — strip comments and control chars before parsing
    text = oc_json.read_text(encoding="utf-8")
    # Strip single-line comments, but not // inside strings
    # Strategy: only strip // that appears at the start of a line (optionally indented)
    clean = re.sub(r"^\s*//[^\n]*", "", text, flags=re.MULTILINE)
    clean = re.sub(r"[\x00-\x1f]", " ", clean)  # strip control chars
    clean = re.sub(r",\s*([}\]])", r"\1", clean)  # strip trailing commas
    try:
        data = json.loads(clean)
    except json.JSONDecodeError:
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


def sync_codex(config: dict) -> None:
    """Write Codex CLI MCP config.

    Codex uses AGENTS.md for steering (same as the skills repo root).
    MCP config location is TBD; for now write to ~/.codex/mcp.json.
    """
    codex_dir = Path.home() / ".codex"
    codex_dir.mkdir(parents=True, exist_ok=True)
    codex_json = codex_dir / "mcp.json"

    servers = {}
    for name, srv in config["mcp_servers"].items():
        if srv["type"] == "http":
            servers[name] = {"url": srv["url"]}
        else:
            entry = {"command": srv["command"], "args": srv.get("args", [])}
            if srv.get("env"):
                entry["env"] = srv["env"]
            servers[name] = entry

    output = {"mcpServers": servers}
    codex_json.write_text(json.dumps(output, indent=2), encoding="utf-8")
    print(f"  Codex: updated {codex_json} ({len(servers)} servers)")


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
        "<!-- Advisory only in VS Code: the Claude Code hooks named below do not run here. -->\n\n"
        + HARNESS_AGENTS.read_text(encoding="utf-8")
        + vscode_pointer_section(),
        encoding="utf-8",
    )
    print(f"  VS Code: updated {core}")


TARGETS = {
    "claude": sync_claude_code,
    "opencode": sync_opencode,
    "kiro": sync_kiro,
    "pi": sync_pi,
    "codex": sync_codex,
    "copilot": sync_github_copilot,
    "vscode": sync_vscode,
}


def main():
    parser = argparse.ArgumentParser(description="Sync harness config to all targets")
    parser.add_argument("--target", choices=[*TARGETS, "all"], default="all")
    args = parser.parse_args()

    config = load_harness()
    print(f"Loaded harness.json: {len(config['mcp_servers'])} MCP servers")

    targets = TARGETS

    if args.target == "all":
        for name, fn in targets.items():
            fn(config)
    else:
        targets[args.target](config)

    print("Done.")


if __name__ == "__main__":
    main()
