"""Report MCP capability alignment across manifest, registry, and adapters.

| Stage | Mechanism | Contract | Req |
|---|---|---|---|
| LOAD | Read manifest.toml and harness.json | [mandatory] | R66, R67 |
| RECONCILE | Compare MCP/skill cells, hooks, plugin artifacts, adapter targets, and registrations | [mandatory] | R66 |
| REPORT | Print supported/SKIP dispositions and discrepancies | [mandatory] | R67 |

EARS guards:
- R1: The report is read-only and does not emit harness configuration.
- R2: A SKIP cell is valid only when its adapter documents that no MCP projection is written.
- R3: Each generated MCP cell requires a target registered in adapter.TARGETS.
- R4: Every registered MCP server must have a supported adapter projection or an explicit SKIP disposition.
- R5: Skill targets, plugin entrypoints, and global hook adapters must resolve without reading credentials.
- R6: When the matrix is checked, the system shall reject missing or duplicate MCP cells for registered adapter targets.
- R7: When a generated MCP cell is checked, the system shall compare its destination with native adapter metadata.
- R8: When a declared harness has no implemented MCP adapter, the system shall require an explicit SKIP reason.

CLOSED:
- A second capability registry was rejected; manifest.toml remains the capability source and
  harness.json remains the MCP registration source.

Preconditions: Run from a checkout containing valid TOML and JSON registries.
Failure modes: Parse errors are raised; detected drift returns exit status 1.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
import os
from pathlib import Path

import adapter
from scripts.validate_skills import validate_skill

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10 runtime
    import tomli as tomllib


ROOT = Path(__file__).resolve().parent.parent


def build_report(root: Path = ROOT) -> tuple[list[str], list[str]]:
    """Compare the declared MCP matrix with registrations and adapter coverage.

    Args:
        root: Harness checkout containing manifest.toml and harness.json.

    Returns:
        A pair of report lines and discrepancy messages.

    Require: Both registry files are readable and structurally valid.
    Guarantee: The inspection reads files and adapter declarations only.
    Maintain: manifest.toml and harness.json remain their respective source registries.
    Assert: Every registered adapter and declared harness has exactly one MCP disposition.
    """
    with (root / "manifest.toml").open("rb") as stream:
        manifest = tomllib.load(stream)
    config = json.loads((root / "harness.json").read_text(encoding="utf-8"))
    cells = [cell for cell in manifest["cell"] if cell["artifact"] == "mcp"]
    skill_cells = [cell for cell in manifest["cell"] if cell["artifact"] == "skills"]
    servers = config.get("mcp_servers", {})
    hooks = config.get("global_hooks", {})
    lines = [f"Registered MCP servers: {len(servers)}"]
    issues: list[str] = []
    declared = manifest.get("harness", {})
    counts = Counter(cell["harness"] for cell in cells)
    for name in sorted(set(adapter.TARGETS) | set(declared)):
        if counts[name] == 0:
            issues.append(f"{name}: missing MCP disposition")
        elif counts[name] > 1:
            issues.append(f"{name}: duplicate MCP dispositions ({counts[name]})")

    for cell in cells:
        name = cell["harness"]
        strategy = cell["strategy"]
        target = adapter.TARGETS.get(name)
        if name not in declared:
            issues.append(f"{name}: MCP harness is not declared in manifest.toml")
        contract = adapter.mcp_projection_contract(name) if target is not None else None
        if strategy == "SKIP":
            reason = cell.get("reason", "").strip()
            if not reason:
                issues.append(f"{name}: SKIP has no reason")
            if contract and contract["strategy"] != "SKIP":
                issues.append(f"{name}: SKIP contradicts its native MCP adapter")
            lines.append(f"SKIP {name}: {reason or 'missing reason'}")
            continue

        if strategy not in {"LINK", "GENERATE"}:
            issues.append(f"{name}: unsupported strategy {strategy!r}")
        if not cell.get("target", "").strip():
            issues.append(f"{name}: generated MCP capability has no target")
        if target is None:
            issues.append(f"{name}: no adapter target registered")
        elif contract["strategy"] != strategy:
            issues.append(f"{name}: manifest strategy {strategy} differs from native {contract['strategy']}")
        elif os.path.normcase(os.path.normpath(str(Path(cell.get("target", "")).expanduser()))) != os.path.normcase(
                os.path.normpath(contract["target"])):
            issues.append(f"{name}: destination differs from native adapter: {contract['target']}")
        lines.append(f"{strategy} {name}: {cell.get('target', '(no target)')}")

    for server_name, server in sorted(servers.items()):
        kind = server.get("type")
        if kind == "http" and not server.get("url", "").startswith(("http://", "https://")):
            issues.append(f"server {server_name}: HTTP registration has no valid URL")
        elif kind == "stdio" and not server.get("command", "").strip():
            issues.append(f"server {server_name}: stdio registration has no command")
        elif kind not in {"http", "stdio"}:
            issues.append(f"server {server_name}: unsupported transport {kind!r}")

    for cell in skill_cells:
        name = cell["harness"]
        if cell["strategy"] == "SKIP":
            reason = cell.get("reason", "").strip()
            if not reason:
                issues.append(f"skills/{name}: SKIP has no reason")
            lines.append(f"SKIP skills/{name}: {reason or 'missing reason'}")
            continue
        target = Path(cell.get("target", "")).expanduser()
        if not target.exists():
            issues.append(f"skills/{name}: target does not exist: {target}")
        lines.append(f"{cell['strategy']} skills/{name}: {'present' if target.exists() else 'missing'} {target}")

    for harness_name, entries in sorted(hooks.items()):
        if harness_name not in manifest.get("harness", {}):
            issues.append(f"hooks/{harness_name}: harness is not declared in manifest.toml")
        if harness_name not in adapter.TARGETS:
            issues.append(f"hooks/{harness_name}: no adapter target is registered")
        for index, hook in enumerate(entries):
            if not hook.get("event") or not hook.get("command"):
                issues.append(f"hooks/{harness_name}[{index}]: event and command are required")
        lines.append(f"HOOKS {harness_name}: {len(entries)} configured")

    plugin_files = sorted((root / "plugin").rglob("*"))
    plugin_entries = [path for path in plugin_files if path.is_file() and path.suffix in {".json", ".js", ".ts"}]
    plugin_skills = sorted((root / "plugin" / "skills").glob("*/SKILL.md"))
    if not plugin_entries:
        issues.append("plugin: no manifest or native entrypoint artifacts found")
    for plugin_file in plugin_entries:
        if plugin_file.suffix == ".json":
            json.loads(plugin_file.read_text(encoding="utf-8"))
    for skill_file in plugin_skills:
        issues.extend(f"plugin/{finding}" for finding in validate_skill(skill_file))
    lines.append(f"PLUGIN: {len(plugin_entries)} native metadata/entrypoint files, {len(plugin_skills)} skill packages")

    generated_harnesses = {cell["harness"] for cell in cells if cell["strategy"] != "SKIP"}
    if servers and not generated_harnesses:
        issues.append("harness.json has servers but the manifest has no generated MCP projection")
    lines.append("REPORT_SCOPE: configuration declarations and artifacts; native connections are not tested")
    return lines, issues


def main(argv: list[str] | None = None) -> int:
    """Run the read-only MCP capability report.

    Args:
        argv: Optional CLI arguments for tests.

    Returns:
        Zero when no discrepancies are found, otherwise one.

    Require: The current checkout contains the two canonical registries.
    Guarantee: Output is diagnostic text; no files are changed.
    Maintain: The report does not call adapter sync functions.
    Assert: Any discrepancy produces a nonzero process status.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args(argv)
    lines, issues = build_report(args.root)
    for line in lines:
        print(line)
    for issue in issues:
        print(f"DRIFT {issue}")
    print(f"{'FAIL' if issues else 'PASS'}: {len(issues)} discrepancy(s)")
    return int(bool(issues))


if __name__ == "__main__":
    raise SystemExit(main())
