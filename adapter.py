"""| Stage | Mechanism | Contract |
| INTEGRATE | Plan/apply/check selected canonical skill packages | [mandatory] R10-R12, R23-R28 |

Spec: docs/playbooks/memory-and-harness-integration.md R10-R12, R23-R28.
CLOSED: parallel registries or writers for the same feature.
Preconditions and failure modes: see the governing spec and incumbent contract below.

Cross-harness MCP projection from the ~/.harness registry.

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
R9: When target metadata is inspected, the system shall return the same native destination and disposition used by projection.
R10: When Hermes would change an existing configuration, the system shall verify a native configuration snapshot before writing.
R11: When Hermes projection repeats without semantic changes, the system shall perform no config write or backup.
R12: When Hermes projection runs, the system shall preserve unowned root settings, server controls, and environment keys.
R13: When a local server is projected to Hermes, the system shall allow the existing 240-second startup budget.
R14: If Hermes validation, snapshot verification, or readback fails, then the system shall report failure without claiming completion.
CLOSED: A separate OpenAI-only registry is rejected because ~/.harness is the shared
cross-harness source. Interactive `hermes mcp add` is rejected because it performs server
discovery and prompts; Hermes' `_save_mcp_server` is the native non-interactive writer. Scalar-only
`hermes config set` is rejected because it cannot create registry entries with argument arrays.
Pi MCP projection is rejected because the installed Pi integration is its retrieval extension,
not an MCP client.

R15: WHERE --client is supplied, skill sync MUST write only selected copy targets.
R16: WHERE --client is supplied, skill sync MUST validate only selected router targets.
R17: WHEN apply completes with selected router clients, skill sync MUST confirm selected skill membership in the shared index.
R18: WHEN skill sync refreshes the canonical retrieval index, it MUST report that visibility is shared across its clients.
R19: WHEN Codex is selected, skill sync MUST copy selected packages to `$HOME/.agents/skills` and verify every resource there; shared-index membership MUST NOT count as native installation.
R20: WHEN capability drift checks Codex skills, the declared transport MUST include native copy and MCP, with the native skill directory as its target.
Preconditions: the registry is valid JSON and harness_write.py is available beside this file.
Failure modes: malformed config or unsafe writes raise; target-specific parse failures do not overwrite.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from uuid import uuid4
import yaml

import harness_write
from scripts.validate_skills import validate_skill

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib

HARNESS_CONFIG = Path(__file__).parent / "harness.json"
HARNESS_AGENTS = Path(__file__).parent / "claude" / "AGENTS.md"
VSCODE_SHIM = Path(__file__).resolve().parent / "hooks" / "vscode_shim.py"
# SessionEnd has no VS Code equivalent; SubagentStart/Stop have no Claude-settings hooks to run.
VSCODE_HOOK_EVENTS = ("SessionStart", "UserPromptSubmit", "PreToolUse", "PostToolUse", "PreCompact", "Stop")
OPENCODE_LOCAL_TIMEOUT_MS = 240000
# OMO-slim was uninstalled 2026-11-08; it must never load from any opencode config.
RETIRED_OPENCODE_PLUGINS = frozenset({"oh-my-opencode-slim"})
HERMES_BRIDGE = Path(__file__).resolve().parent / "scripts" / "hermes_mcp.py"
BACKUP_RUN = Path.home() / '.harness/backups' / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f') + '-' + uuid4().hex[:8])
SKILL_COPY_TARGETS = {'claude': '.claude/skills', 'codex': '.agents/skills', 'copilot': '.copilot/skills',
                      'opencode': '.config/opencode/skills', 'hermes': '.hermes/skills', 'pi': '.pi/skills'}
SKILL_ROUTER_TARGETS = ('claude', 'codex', 'kiro', 'vscode')
SKILL_EXCLUDES = {'.git', '.venv', 'venv', '__pycache__', '.pytest_cache', '.benchmarks',
                  'node_modules', '.tmp', '.chroma', 'backups', '.ruff_cache'}
RETIRED_GRAPHIFY_HOOK_COMMANDS = frozenset({
    "C:/Users/user/.local/bin/graphify.EXE hook-guard search",
    "C:/Users/user/.local/bin/graphify.EXE hook-guard read",
    "C:/Users/user/.local/bin/graphify.EXE hook-check",
})


def load_harness() -> dict:
    return json.loads(HARNESS_CONFIG.read_text(encoding="utf-8"))


def hermes_command() -> list[str]:
    """Resolve the installed Hermes interpreter and native projection bridge.

    Require: Hermes is installed in a virtual environment on PATH.
    Guarantee: Returns argument-list execution without shell interpolation.
    Maintain: Only Hermes' environment imports its optional native dependencies.
    Assert: Missing interpreter or bridge fails before config access.
    """
    hermes = shutil.which("hermes")
    if not hermes:
        raise FileNotFoundError("Hermes executable was not found on PATH")
    python = Path(hermes).with_name("python.exe" if os.name == "nt" else "python")
    if not python.is_file() or not HERMES_BRIDGE.is_file():
        raise FileNotFoundError("Hermes interpreter or native harness bridge is missing")
    return [str(python), str(HERMES_BRIDGE)]


def mcp_projection_contract(name: str) -> dict:
    """Describe the native destination used by each existing MCP adapter.

    Args:
        name: Registered adapter target identifier.

    Returns:
        Strategy, target path, server key, and explicit SKIP reason.

    Require: name is a known native MCP client, including a temporarily unregistered one.
    Guarantee: Projection and capability reporting share native destination facts.
    Maintain: Hermes path discovery uses its native API without reading config values.
    Assert: Pi has an explicit SKIP; unknown targets raise KeyError.
    """
    home = Path.home()
    if name == "pi":
        return {"strategy": "SKIP", "target": None, "key": None,
                "reason": "Pi retains its installed retrieve-skills extension; no MCP config is written."}
    if name == "hermes":
        result = subprocess.run([*hermes_command(), "--config-path"], capture_output=True,
                                text=True, check=True, timeout=30)
        path, key = Path(json.loads(result.stdout)["path"]), "mcp_servers"
    else:
        path, key = {
            "claude": (home / ".claude.json", "mcpServers"),
            "opencode": (home / ".config" / "opencode" / "opencode.json", "mcp"),
            "kiro": (home / ".kiro" / "settings" / "mcp.json", "mcpServers"),
            "codex": (home / ".codex" / "config.toml", "mcp_servers"),
            "copilot": (home / ".copilot" / "mcp-config.json", "mcpServers"),
            "vscode": (vscode_user_dir() / "mcp.json", "servers"),
        }[name]
    return {"strategy": "GENERATE", "target": str(path), "key": key, "reason": ""}


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
    return bool(harness_write.apply(changes, BACKUP_RUN))


def ensure_global_hooks(path: Path, hooks: list[dict]) -> bool:
    """Append each declared hook to `path` (a Claude-format hooks JSON) unless already present.

    Require: `path` holds JSON(C) or is absent; each hook has event, command, optional matcher/timeout.
    Guarantee: every other hook in the file is untouched (deep_merge would replace the event's
        whole list); a hook is identified by (event, matcher, command), so reruns are no-ops.
        One trailing LF matches Codex's JSON merge writer and prevents alternating rewrites.
    Returns: True when the file was written.
    """
    import harness_write

    existing = harness_write.read_existing(path)
    data = harness_write.load_jsonc(existing) if existing else {}
    events = data.setdefault("hooks", {})
    for hook in hooks:
        groups = events.setdefault(hook["event"], [])
        if isinstance(groups, dict):
            groups = events[hook["event"]] = [groups]
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
    artifact = harness_write.Artifact(path=path, text=json.dumps(data, indent=2) + "\n", mode="file")
    return bool(harness_write.apply(harness_write.plan([artifact]), BACKUP_RUN))


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
    return bool(harness_write.apply(harness_write.plan([artifact]), BACKUP_RUN))


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
    claude_json = Path(mcp_projection_contract("claude")["target"])
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


def remove_retired_opencode_plugins() -> None:
    """Remove every retired plugin name from opencode's plugin lists.

    Require: the target config files hold JSON(C) or are absent.
    Guarantee: only the exact retired names are removed; other keys and plugins survive.
    Maintain: no-op when the file is missing or already clean.
    Assert: writes go through the safe harness writer.
    """
    import harness_write

    home = Path.home()
    for name in ("opencode.json", "tui.json"):
        path = home / ".config" / "opencode" / name
        existing = harness_write.read_existing(path)
        if not existing:
            continue
        data = harness_write.load_jsonc(existing)
        plugins = data.get("plugin")
        if not isinstance(plugins, list):
            continue
        kept = [p for p in plugins if not (isinstance(p, str) and p.split("/")[-1] in RETIRED_OPENCODE_PLUGINS)]
        if len(kept) == len(plugins):
            continue
        data["plugin"] = kept
        artifact = harness_write.Artifact(path=path, text=json.dumps(data, indent=2, ensure_ascii=False) + "\n", mode="file")
        changed = harness_write.apply(harness_write.plan([artifact]), BACKUP_RUN)
        print(f"  opencode: {'updated' if changed else 'unchanged'} {path} (retired plugins removed)")


def sync_opencode(config: dict) -> None:
    """Project the central registry into OpenCode's native MCP schema.

    Require: the registry uses `http` or `stdio` transport entries.
    Guarantee: remote HTTP and local command forms match OpenCode's schema; local tools receive
        enough catalog time for the measured cold start of their F: environments.
    Maintain: existing unmanaged root keys and MCP names survive the safe writer merge.
    Assert: the generated object is valid JSONC and preserves each server's transport.
    """
    remove_retired_opencode_plugins()
    oc_json = Path(mcp_projection_contract("opencode")["target"])
    if not oc_json.exists():
        print("  opencode: config not found, skipping")
        return

    # opencode uses JSONC; harness_write.load_jsonc handles // and /* */ comments and trailing commas
    # while respecting strings (the old line-start regex mangled '//' inside values).
    import harness_write

    text = oc_json.read_text(encoding="utf-8")
    try:
        harness_write.load_jsonc(text)
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
    kiro_json = Path(mcp_projection_contract("kiro")["target"])
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
    servers = {}
    for name, server in config["mcp_servers"].items():
        entry = {"enabled": True}
        if server["type"] == "http":
            entry["url"] = server["url"]
        else:
            entry["command"] = server["command"]
            entry["args"] = server.get("args", [])
            entry["connect_timeout"] = OPENCODE_LOCAL_TIMEOUT_MS / 1000
            if server.get("env"):
                entry["env"] = server["env"]
        servers[name] = entry

    result = subprocess.run(
        hermes_command(),
        input=json.dumps(servers),
        text=True,
        capture_output=True,
        check=True,
        env=os.environ.copy(),
        timeout=300,
    )
    summary = json.loads(result.stdout)
    if set(summary["configured"]) != set(servers):
        raise RuntimeError("Hermes projection summary omitted registry entries")
    print(f"  Hermes: configured {len(servers)} servers; changed {len(summary['changed'])}; "
          f"snapshot {'verified' if summary.get('snapshot') else 'not required'}")


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
    path = Path(mcp_projection_contract("codex")["target"])
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

    written = harness_write.apply(changes, BACKUP_RUN)
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
                                  BACKUP_RUN)
    print(f"  Codex hooks: {'updated' if written else 'unchanged'} {path}")


def sync_github_copilot(config: dict) -> None:
    """Merge GitHub Copilot CLI MCP config at the user-level path."""
    copilot_json = Path(mcp_projection_contract("copilot")["target"])

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
    vscode_json = Path(mcp_projection_contract("vscode")["target"])
    vscode_json.parent.mkdir(parents=True, exist_ok=True)
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
    core_text = (
        "---\napplyTo: '**'\n---\n\n"
        "<!-- Generated by ~/.harness/adapter.py from claude/AGENTS.md. Do not edit. -->\n"
        "<!-- Hooks run here through ~/.copilot/hooks/harness.json -> hooks/vscode_shim.py. -->\n"
        "<!-- Not ported: verify_gate and session_handoff (need Claude's transcript), SessionEnd. -->\n\n"
        + HARNESS_AGENTS.read_text(encoding="utf-8")
        + vscode_pointer_section()
    )
    harness_write.apply(harness_write.plan([harness_write.Artifact(core, core_text)]), BACKUP_RUN)
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
    harness_write.apply(harness_write.plan([harness_write.Artifact(hooks_json, json.dumps({"hooks": hooks}, indent=2))]), BACKUP_RUN)
    print(f"  VS Code: updated {hooks_json} ({len(hooks)} events via shim)")


def skill_package_files(package: Path) -> list[Path]:
    """Enumerate owned package resources, including binary assets but excluding runtime state.

    Require: package is a canonical skill directory.
    Guarantee: no symlink escape, credential file, model cache or runtime DB is copied.
    Maintain: stable order and byte identity.
    Assert: package identity is validated before projection.
    """
    root = package.resolve()
    result = []
    for path in sorted(package.rglob('*')):
        relative = path.relative_to(package)
        if not path.is_file() or any(part in SKILL_EXCLUDES for part in relative.parts):
            continue
        if path.suffix.lower() in {'.pyc', '.db', '.sqlite3', '.log', '.lock'} or path.name in {'.env', 'uv.lock', 'package-lock.json'}:
            continue
        if not path.resolve().is_relative_to(root):
            raise ValueError(f'skill resource escapes package: {relative}')
        if harness_write.denied(path):
            raise ValueError(f'protected configuration is not a skill resource: {relative}')
        result.append(path)
    return result


def skill_projection_contract(name: str, home: Path | None = None) -> dict:
    """Describe every skill delivery surface supported by a harness.

    Args:
        name: Supported native harness identifier.
        home: Optional user home used to resolve native destinations.

    Returns:
        Strategy, transport, and destination metadata shared with capability
        drift checks.

    Require: ``name`` identifies a supported native harness.
    Guarantee: Capability reporting includes each supported transport.
    Maintain: Claude does not receive the whole library as native skills.
    Assert: Unsupported harnesses remain explicit SKIP projections.
    """
    home = home or Path.home()
    if name in SKILL_COPY_TARGETS and name in SKILL_ROUTER_TARGETS:
        return {'strategy': 'GENERATE', 'transport': 'copy+mcp',
                'target': str(home / SKILL_COPY_TARGETS[name])}
    if name in SKILL_COPY_TARGETS:
        return {'strategy': 'GENERATE', 'transport': 'copy', 'target': str(home / SKILL_COPY_TARGETS[name])}
    if name in SKILL_ROUTER_TARGETS:
        return {'strategy': 'GENERATE', 'transport': 'mcp', 'target': mcp_projection_contract(name)['target']}
    return {'strategy': 'SKIP', 'transport': None, 'target': None, 'reason': 'No implemented skill projection for this harness.'}


def reconcile_skill_master(master: Path, *, apply: bool = False) -> dict:
    """Preserve unique/divergent legacy resources before canonical export.

    Require: caller explicitly chose reconciliation; canonical content wins collisions.
    Guarantee: unique resources are imported; conflicts are archived; unsafe packages are reported and skipped.
    Maintain: no deletions, LLM merges or whole-directory mirroring.
    Assert: every conflicting resource has a provenance report and backup.
    """
    home = Path.home()
    roots = [home / 'Documents/dev/skills', *[home / p for p in SKILL_COPY_TARGETS.values()], home / '.claude/skills']
    report = {'master': str(master), 'imported': [], 'preserved': [], 'skipped': []}
    for index, legacy in enumerate(roots):
        if not legacy.is_dir() or legacy.resolve() == master.resolve():
            continue
        for skill in sorted(legacy.glob('*/SKILL.md')):
            package = skill.parent
            try:
                resources = skill_package_files(package)
            except ValueError as exc:
                report['skipped'].append({'source': str(package), 'reason': str(exc)})
                continue
            for path in resources:
                relative = Path(package.name) / path.relative_to(package)
                destination = master / relative
                content = path.read_bytes()
                if not destination.exists():
                    report['imported'].append({'source': str(path), 'target': str(destination)})
                    if apply:
                        harness_write.write_bytes(destination, content, BACKUP_RUN / 'canonical')
                elif destination.read_bytes() != content:
                    archived = BACKUP_RUN / 'legacy' / str(index) / relative
                    report['preserved'].append({'source': str(path), 'backup': str(archived), 'sha256': hashlib.sha256(content).hexdigest()})
                    if apply:
                        harness_write.write_bytes(archived, content, BACKUP_RUN / 'legacy-backups')
    if apply:
        harness_write.write_bytes(BACKUP_RUN / 'reconciliation.json', json.dumps(report, indent=2).encode(), BACKUP_RUN / 'reports')
    return report


def _skill_router_issues(config: dict, master: Path, names: list[str], *, indexed: bool,
                         targets: tuple[str, ...] | None = None) -> list[str]:
    """Inspect selected named-skill router access without model calls or secret output.

    Args:
        config: Canonical harness registry.
        master: Canonical skill store.
        names: Selected skill directory names.
        indexed: Whether canonical index membership must be checked.
        targets: Router clients to inspect; defaults to every registered router client.

    Returns:
        Findings for missing, stale, disabled, or unindexed selected routes.

    Require: Native router destinations are registered.
    Guarantee: Only the selected router destinations are checked.
    Maintain: Checks are read-only and never trigger reindex.
    Assert: A file copy alone cannot establish router availability.
    """
    issues = []
    expected = config['mcp_servers']['retrieve-skills']['url']
    for target in targets if targets is not None else SKILL_ROUTER_TARGETS:
        contract = mcp_projection_contract(target)
        path = Path(contract['target'])
        if not path.is_file():
            issues.append(f'{target}: missing router configuration')
            continue
        raw = path.read_text(encoding='utf-8-sig')
        data = tomllib.loads(raw) if path.suffix == '.toml' else harness_write.load_jsonc(raw)
        server = data.get(contract['key'], {}).get('retrieve-skills', {})
        if server.get('url') != expected:
            issues.append(f'{target}: retrieve-skills URL differs from canonical registry')
        if server.get('disabled') is True or server.get('enabled') is False:
            issues.append(f'{target}: retrieve-skills is disabled')
    if indexed:
        db_path = master / 'retrieve-skills/index.db'
        if not db_path.is_file():
            return issues + ['retrieve-skills: index is missing']
        conn = sqlite3.connect(db_path.resolve().as_uri() + '?mode=ro', uri=True)
        try:
            for name in names:
                path = master / name / 'SKILL.md'
                front = yaml.safe_load(path.read_text(encoding='utf-8-sig').split('---', 2)[1])
                row = conn.execute('SELECT path,description FROM skills WHERE name=?', (name,)).fetchone()
                if not row or Path(row[0]).resolve() != path.resolve() or row[1].strip() != str(front['description']).strip():
                    issues.append(f'retrieve-skills: missing/stale canonical index entry for {name}')
        finally:
            conn.close()
    return issues


def sync_skills(config: dict, names: list[str], *, apply: bool = False, check: bool = False,
                reconcile: bool = False, master: Path | None = None,
                clients: list[str] | None = None) -> int:
    """Plan/apply/check selected canonical packages for selected harness clients.

    Args:
        config: Canonical harness registry.
        names: Canonical skill directory names to project.
        apply: Apply additive copies and refresh the shared skill index.
        check: Check selected projections and shared-index membership without writes.
        reconcile: Preserve/import legacy resources before export.
        master: Canonical skill-store path; defaults to the user's .skills directory.
        clients: Optional client subset; omitted preserves all-target behavior.

    Returns:
        Nonzero when selected router or projection checks find drift.

    Raises:
        ValueError: If modes, skill names, or client names are invalid.

    Require: Valid selected names; apply and check are mutually exclusive.
    Guarantee: Exact bytes, additive selected copies, and preserved unrelated resources.
    Maintain: Router clients share one canonical index; selection does not isolate its contents.
    Assert: Check/default plan never writes or reindexes.
    """
    if apply and check:
        raise ValueError('apply and check are mutually exclusive')
    master = master or Path.home() / '.skills'
    names = sorted(set(names))
    if not names or any(not re.fullmatch(r'[a-z0-9][a-z0-9_-]*', n) for n in names):
        raise ValueError('select valid canonical skill directory names')
    all_clients = set(SKILL_COPY_TARGETS) | set(SKILL_ROUTER_TARGETS)
    if clients is not None and (not clients or set(clients) - all_clients):
        raise ValueError('select one or more supported skill clients')
    selected_clients = all_clients if clients is None else set(clients)
    copy_targets = tuple(target for target in SKILL_COPY_TARGETS if target in selected_clients)
    router_targets = tuple(target for target in SKILL_ROUTER_TARGETS if target in selected_clients)
    if reconcile:
        report = reconcile_skill_master(master, apply=apply)
        print(f"Reconciliation: {len(report['imported'])} unique resources; {len(report['preserved'])} divergent resources preserved; {len(report['skipped'])} unsafe packages skipped")
    packages = []
    for name in names:
        package = master / name
        if not package.resolve().is_relative_to(master.resolve()):
            raise ValueError(f'canonical package escapes master: {name}')
        findings = validate_skill(package / 'SKILL.md')
        if findings:
            raise ValueError('\n'.join(findings))
        packages.append((name, package, skill_package_files(package)))
    issues = _skill_router_issues(config, master, names, indexed=check, targets=router_targets)
    copies = []
    for target in copy_targets:
        relative = SKILL_COPY_TARGETS[target]
        for name, package, files in packages:
            for source in files:
                destination = Path.home() / relative / name / source.relative_to(package)
                if not destination.exists() or destination.read_bytes() != source.read_bytes():
                    copies.append((target, source, destination))
    for target, source, destination in copies:
        print(f'{"DRIFT" if check else "WRITE" if apply else "PLAN"} {target}: {source.relative_to(master)}')
        if apply:
            harness_write.write_bytes(destination, source.read_bytes(), BACKUP_RUN)
    if apply:
        url = config['mcp_servers']['retrieve-skills']['url'].removesuffix('/mcp').rstrip('/')
        with urlopen(url + '/health', timeout=30) as response:
            health = json.load(response)
        if Path(health['store']).resolve() != master.resolve():
            raise ValueError('router is not configured to use the canonical skill master')
        with urlopen(Request(url + '/reindex', method='POST', data=b''), timeout=120) as response:
            json.load(response)
        issues.extend(_skill_router_issues(config, master, names, indexed=True, targets=router_targets))
    for issue in sorted(set(issues)):
        print('DRIFT ' + issue)
    selected_label = ','.join(sorted(selected_clients))
    print(f'Skills: {len(names)} selected; clients: {selected_label}; {len(copies)} changed resources; {len(set(issues))} router issues; shared index visibility is global')
    return int(bool(issues) or (check and bool(copies)))


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
OPT_IN_TARGETS = ("agents", "skills")


def main():
    parser = argparse.ArgumentParser(description="Sync harness config to all targets")
    parser.add_argument("--target", choices=[*TARGETS, *OPT_IN_TARGETS, "all"], default="all")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true", help="agents/skills: apply planned changes")
    mode.add_argument('--check', action='store_true', help='skills: report drift without writing')
    parser.add_argument('--skill', nargs='+', help='selected canonical skill packages')
    parser.add_argument('--reconcile', action='store_true', help='skills: preserve/import legacy packages before export')
    parser.add_argument('--client', nargs='+', choices=sorted(set(SKILL_COPY_TARGETS) | set(SKILL_ROUTER_TARGETS)), help='skills: limit projections and router checks to selected clients')
    args = parser.parse_args()
    if args.target != 'skills' and (args.skill or args.check or args.reconcile or args.client):
        parser.error('--skill, --check, --reconcile and --client belong to --target skills')

    config = load_harness()
    print(f"Loaded harness.json: {len(config['mcp_servers'])} MCP servers")

    targets = TARGETS

    if args.target == "all":
        for name, fn in targets.items():
            fn(config)
    elif args.target == "agents":
        sync_agents(config, apply=args.apply)
    elif args.target == 'skills':
        names = args.skill or config.get('skill_packages', {}).get('packages')
        if not names:
            parser.error('--target skills requires --skill NAME... or harness.json skill_packages')
        raise SystemExit(sync_skills(config, names, apply=args.apply, check=args.check, reconcile=args.reconcile, clients=args.client))
    else:
        targets[args.target](config)

    print("Done.")


if __name__ == "__main__":
    main()
