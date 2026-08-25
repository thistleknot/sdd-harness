#!/usr/bin/env python3
"""
SDD Harness Plugin Installer

Detects installed harnesses and wires the SDD plugin into each one's native config.
Supports: Claude Code, OpenCode, Codex, Pi, Kiro.

Usage:
    python install.py              # auto-detect and install all
    python install.py --target claude opencode  # install specific targets
    python install.py --verify     # check health of all MCP services
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

HARNESS_ROOT = Path(__file__).parent.parent  # ~/.harness
PLUGIN_ROOT = Path(__file__).parent           # ~/.harness/plugin
HOME = Path.home()

MCP_SERVICES = {
    "specs": {"port": 8057, "url": "http://127.0.0.1:8057/mcp"},
    "memory-index": {"port": 8055, "url": "http://127.0.0.1:8055/mcp"},
    "retrieve-skills": {"port": 8765, "url": "http://127.0.0.1:8765/mcp"},
    "todo": {"port": 8056, "url": "http://127.0.0.1:8056/mcp"},
}


def check_port(port: int) -> bool:
    """Check if a service is listening on a port."""
    import socket
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=2):
            return True
    except (ConnectionRefusedError, TimeoutError, OSError):
        return False


def verify_services() -> dict:
    """Check all MCP services are healthy."""
    results = {}
    for name, info in MCP_SERVICES.items():
        healthy = check_port(info["port"])
        results[name] = {"port": info["port"], "healthy": healthy}
        status = "OK" if healthy else "DOWN"
        print(f"  {name} (:{info['port']}): {status}")
    return results


def detect_harnesses() -> list:
    """Detect which harnesses are installed."""
    found = []

    # Claude Code
    claude_dir = HOME / ".claude"
    if claude_dir.exists() and (claude_dir / "settings.json").exists():
        found.append("claude")

    # OpenCode
    opencode_cfg = HOME / ".config" / "opencode" / "opencode.json"
    opencode_cfg_win = HOME / ".config" / "opencode" / "opencode.json"
    if opencode_cfg.exists() or opencode_cfg_win.exists():
        found.append("opencode")
    # Also check if opencode binary exists
    if shutil.which("opencode"):
        if "opencode" not in found:
            found.append("opencode")

    # Codex
    codex_dir = HOME / ".codex"
    if codex_dir.exists():
        found.append("codex")
    if shutil.which("codex"):
        if "codex" not in found:
            found.append("codex")

    # Pi
    if shutil.which("pi"):
        found.append("pi")

    # Kiro
    kiro_dir = HOME / ".kiro"
    if kiro_dir.exists():
        found.append("kiro")

    return found


def install_claude():
    """Install plugin for Claude Code."""
    print("\n[Claude Code]")
    plugins_dir = HOME / ".claude" / "plugins" / "data" / "sdd-harness"
    plugins_dir.mkdir(parents=True, exist_ok=True)

    # Copy plugin structure
    src = PLUGIN_ROOT / ".claude-plugin"
    dst = plugins_dir / ".claude-plugin"
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)

    # Copy skills
    skills_src = PLUGIN_ROOT / "skills"
    skills_dst = plugins_dir / "skills"
    if skills_dst.exists():
        shutil.rmtree(skills_dst)
    shutil.copytree(skills_src, skills_dst)

    # Copy hooks
    hooks_src = PLUGIN_ROOT / "hooks"
    hooks_dst = plugins_dir / "hooks"
    if hooks_dst.exists():
        shutil.rmtree(hooks_dst)
    shutil.copytree(hooks_src, hooks_dst)

    # Also copy the shared hook scripts from harness root
    for hook_file in (HARNESS_ROOT / "hooks").glob("*.py"):
        shutil.copy2(hook_file, hooks_dst / hook_file.name)

    # Register in installed_plugins.json
    installed_path = HOME / ".claude" / "plugins" / "installed_plugins.json"
    if installed_path.exists():
        data = json.loads(installed_path.read_text())
    else:
        data = {"version": 2, "plugins": {}}

    data["plugins"]["sdd-harness@local"] = [{
        "scope": "user",
        "installPath": str(plugins_dir),
        "version": "0.1.0",
        "installedAt": __import__("datetime").datetime.now().isoformat() + "Z",
    }]
    installed_path.write_text(json.dumps(data, indent=2))

    # MCP servers: only add what's missing
    settings_path = HOME / ".claude" / "settings.json"
    if settings_path.exists():
        settings = json.loads(settings_path.read_text())
    else:
        settings = {}

    if "mcpServers" not in settings:
        settings["mcpServers"] = {}

    added = []
    for name, info in MCP_SERVICES.items():
        if name not in settings["mcpServers"]:
            settings["mcpServers"][name] = {"url": info["url"]}
            added.append(name)

    if added:
        settings_path.write_text(json.dumps(settings, indent=2))
        print(f"  MCP servers added: {added}")
    else:
        print(f"  MCP servers already present (skipped)")

    print(f"  Plugin: {plugins_dir}")


def install_opencode():
    """Install plugin for OpenCode."""
    print("\n[OpenCode]")
    config_dir = HOME / ".config" / "opencode"
    config_dir.mkdir(parents=True, exist_ok=True)

    # Copy the plugin JS
    plugins_dir = config_dir / "plugins"
    plugins_dir.mkdir(exist_ok=True)
    shutil.copy2(
        PLUGIN_ROOT / ".opencode" / "plugins" / "sdd-harness.js",
        plugins_dir / "sdd-harness.js"
    )

    # Update opencode.json to include the plugin
    config_file = config_dir / "opencode.json"
    if config_file.exists():
        config = json.loads(config_file.read_text())
    else:
        config = {}

    if "plugin" not in config:
        config["plugin"] = []

    plugin_path = str(plugins_dir / "sdd-harness.js")
    if plugin_path not in config["plugin"] and "sdd-harness" not in config["plugin"]:
        config["plugin"].append(plugin_path)

    # MCP servers: only add what's missing
    if "mcp" not in config:
        config["mcp"] = {}

    added = []
    for name, info in MCP_SERVICES.items():
        if name not in config["mcp"]:
            config["mcp"][name] = {"url": info["url"]}
            added.append(name)

    config_file.write_text(json.dumps(config, indent=2))
    if added:
        print(f"  MCP servers added: {added}")
    else:
        print(f"  MCP servers already present (skipped)")
    print(f"  Plugin: {plugin_path}")


def install_codex():
    """Install plugin for Codex."""
    print("\n[Codex]")
    # Codex uses .agents/plugins/ in the workspace or ~/.codex/plugins/
    codex_plugins = HOME / ".codex" / "plugins" / "sdd-harness"
    codex_plugins.mkdir(parents=True, exist_ok=True)

    # Copy plugin manifest
    shutil.copy2(
        PLUGIN_ROOT / ".codex-plugin" / "plugin.json",
        codex_plugins / "plugin.json"
    )

    # Copy skills
    skills_dst = codex_plugins / "skills"
    if skills_dst.exists():
        shutil.rmtree(skills_dst)
    shutil.copytree(PLUGIN_ROOT / "skills", skills_dst)

    print(f"  Installed to {codex_plugins}")


def install_pi():
    """Install plugin for Pi."""
    print("\n[Pi]")
    pi_ext_dir = HOME / ".pi" / "extensions"
    pi_ext_dir.mkdir(parents=True, exist_ok=True)

    shutil.copy2(
        PLUGIN_ROOT / ".pi" / "extensions" / "sdd-harness.ts",
        pi_ext_dir / "sdd-harness.ts"
    )
    print(f"  Extension: {pi_ext_dir / 'sdd-harness.ts'}")


def install_kiro():
    """Install plugin for Kiro."""
    print("\n[Kiro]")
    kiro_settings = HOME / ".kiro" / "settings" / "mcp.json"
    if kiro_settings.exists():
        config = json.loads(kiro_settings.read_text())
        existing = set(config.get("mcpServers", {}).keys())
        needed = set(MCP_SERVICES.keys())
        missing = needed - existing
        # Remove any sdd-* duplicates that point to the same ports
        dupes = [k for k in existing if k.startswith("sdd-")]
        if dupes:
            print(f"  Removing duplicates: {dupes}")
            for d in dupes:
                del config["mcpServers"][d]
            kiro_settings.write_text(json.dumps(config, indent=2))
        if missing:
            print(f"  MANUAL: Add to {kiro_settings}: {sorted(missing)}")
        else:
            print(f"  MCP servers already configured (no duplicates)")
    else:
        print(f"  WARNING: {kiro_settings} not found — create manually")

    # Copy steering files
    steering_dir = HOME / ".kiro" / "steering"
    steering_dir.mkdir(parents=True, exist_ok=True)

    sdd_steering = steering_dir / "sdd-harness.md"
    sdd_steering.write_text(
        "---\ninclusion: always\n---\n\n"
        "# SDD Harness\n\n"
        "You are operating under the SDD (Spec-Driven Development) harness.\n"
        "Available MCP tools: specs, memory-index, retrieve-skills, todo.\n\n"
        "At session start: search_memory, list_todos, retrieve_skills.\n"
        "After significant work: log_memory with lessons.\n"
        "Before implementation: verify spec phase via query_specs.\n"
    )
    print(f"  MCP servers: {kiro_settings}")
    print(f"  Steering: {sdd_steering}")


INSTALLERS = {
    "claude": install_claude,
    "opencode": install_opencode,
    "codex": install_codex,
    "pi": install_pi,
    "kiro": install_kiro,
}


def main():
    parser = argparse.ArgumentParser(description="SDD Harness Plugin Installer")
    parser.add_argument("--target", nargs="*", choices=list(INSTALLERS.keys()),
                        help="Specific harnesses to install (default: auto-detect)")
    parser.add_argument("--verify", action="store_true",
                        help="Verify MCP service health only")
    parser.add_argument("--all", action="store_true",
                        help="Install for all supported harnesses regardless of detection")
    args = parser.parse_args()

    print("=" * 60)
    print("  SDD Harness Plugin Installer")
    print("=" * 60)

    # Verify services
    print("\nMCP Services:")
    results = verify_services()
    down = [k for k, v in results.items() if not v["healthy"]]
    if down:
        print(f"\n  WARNING: {len(down)} service(s) down: {', '.join(down)}")
        print("  Start them before using the plugin.")

    if args.verify:
        return

    # Determine targets
    if args.all:
        targets = list(INSTALLERS.keys())
    elif args.target:
        targets = args.target
    else:
        targets = detect_harnesses()

    if not targets:
        print("\nNo harnesses detected. Use --target or --all.")
        return

    print(f"\nDetected harnesses: {', '.join(targets)}")
    print("\nInstalling...")

    for target in targets:
        INSTALLERS[target]()

    print("\n" + "=" * 60)
    print("  Done. Plugin installed for: " + ", ".join(targets))
    print("=" * 60)
    if down:
        print(f"\n  Next: start MCP services ({', '.join(down)})")
        print("  Then restart your agent sessions.")


if __name__ == "__main__":
    main()
