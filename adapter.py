"""Cross-harness adapter: reads ~/.harness/harness.json, writes per-harness configs.

Usage: python adapter.py [--target claude|opencode|kiro|all]

Ensures all harnesses share the same MCP server registrations and model routing.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

HARNESS_CONFIG = Path(__file__).parent / "harness.json"


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


def main():
    parser = argparse.ArgumentParser(description="Sync harness config to all targets")
    parser.add_argument("--target", choices=["claude", "opencode", "kiro", "all"], default="all")
    args = parser.parse_args()

    config = load_harness()
    print(f"Loaded harness.json: {len(config['mcp_servers'])} MCP servers")

    targets = {
        "claude": sync_claude_code,
        "opencode": sync_opencode,
        "kiro": sync_kiro,
    }

    if args.target == "all":
        for name, fn in targets.items():
            fn(config)
    else:
        targets[args.target](config)

    print("Done.")


if __name__ == "__main__":
    main()
