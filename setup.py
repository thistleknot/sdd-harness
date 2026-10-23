"""Install shared skills and provision registered MCP runtime environments.

Pipeline:
| Stage | Mechanism | Tag | Requirements |
|---|---|---|---|
| SKILLS | Seed the canonical shared skill store without overwriting existing skills | [opt] | R1 |
| ENVIRONMENTS | Lock and sync each Python MCP project into its isolated F: environment | [mandatory] | R2 |
| TOOLS | Install the registered uv MCP tool into the configured F: tool directory | [mandatory] | R2 |
| PROJECTIONS | Delegate native client configs to adapter.py and harness_write.py | [mandatory] | R3 |

R1: WHEN skill setup runs, existing user-owned skill directories MUST remain intact.
R2: Python MCP dependencies MUST come from each committed uv.lock into runtime.mcp.environments_dir;
the cache and uv tool directory MUST use their manifest-defined F: locations.
R3: WHEN client MCP config is written, setup MUST delegate to the central registry adapter.
R4: Non-MCP Python consumers MUST retain the general runtime.python selection.
R5: When setup discovers an installed MCP adapter target, the system shall offer that target through the existing setup interface.

CLOSED: Global py310 pip installation is rejected because it mixes MCP dependencies
with hooks and unrelated servers. Pi MCP projection is rejected because its installed
integration is the retrieval extension.

Preconditions: uv and the manifest-selected CPython base interpreter are installed.
Failure modes: lock, sync, or client projection errors propagate before service cutover.
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

# ─── Paths ───────────────────────────────────────────────────────────────────

HARNESS_ROOT = Path(__file__).parent
SKILL_STORE = Path.home() / ".skills"
RETRIEVE_SKILLS_SRC = None  # discovered at runtime

# Harness detection
HARNESSES = {
    "claude": {
        "root": Path.home() / ".claude",
        "detect": "settings.json",
    },
    "opencode": {
        "root": Path.home() / ".config" / "opencode",
        "detect": "opencode.json",
    },
    "kiro": {
        "root": Path.home() / ".kiro",
        "detect": "steering",
    },
    "pi": {
        "root": Path.home() / ".pi",
        "detect": "agent",
    },
    "codex": {
        "root": Path.home() / ".codex",
        "detect": "config.toml",
    },
    "copilot": {
        "root": Path.home() / ".copilot",
        "detect": "mcp-config.json",
    },
    "vscode": {
        "root": Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / "Code" / "User",
        "detect": "mcp.json",
    },
    "hermes": {
        "root": Path(os.environ.get("HERMES_HOME", Path.home() / "AppData" / "Local" / "hermes")),
        "detect": "config.yaml",
    },
}

# Core skills that ship with this harness (relative to HARNESS_ROOT or discoverable)
# These are the skills that make the harness function as a Python-centric agentic dev environment
CORE_SKILLS = [
    # --- Infrastructure (MCP servers + retrieval) ---
    "retrieve-skills",  # the retrieval SKILL.md (not the server itself)
    "todo",
    "memory-index",
    "memory-bank",
    # --- Spec lifecycle ---
    "spec",
    "spec-init",
    "spec-new",
    "spec-next",
    "spec-approve",
    "spec-status",
    # --- Debugging & isolation ---
    "debugging",
    "subtractive-debugging",
    "evidence-first-exploration",
    "diagnostic-scanner",
    "pipeline-input-review",
    # --- Code quality & patterns ---
    "code",
    "architecture",
    "design-patterns",
    "simplify",
    "security-review",
    "validation",
    "tdd-agent",
    "llm-pipeline-layer-tdd",
    "checklist",
    # --- Reasoning & research ---
    "reasoning",
    "hypothesis-forge",
    "agentic-orchestration",
    # --- Workflow & continuity ---
    "git-workflow",
    "lessons-learned",
    "consolidation",
    "failed-feature-iteration",
    "context-compaction",
    # --- Robustness & observability ---
    "build-observability",
    "timeout-guard",
    "ewma-eta-watchdog",
    "prompt-optimization",
]


def find_python() -> str:
    """Find the Python interpreter to use."""
    # Prefer the harness runtime if specified
    try:
        import tomli as tomllib
    except ImportError:
        try:
            import tomllib
        except ImportError:
            tomllib = None

    if tomllib:
        manifest = HARNESS_ROOT / "manifest.toml"
        if manifest.exists():
            data = tomllib.loads(manifest.read_text(encoding="utf-8"))
            rt = data.get("runtime", {}).get("python")
            if rt and Path(rt).exists():
                return rt

    return sys.executable


def mcp_runtime() -> dict:
    """Load the manifest-owned paths and project map for registered MCP environments.

    Require: manifest.toml contains [runtime.mcp] and the named projects.
    Guarantee: returns resolved paths rooted at HARNESS_ROOT for each project.
    Maintain: the general runtime.python remains independent of MCP environments.
    Assert: every project path has a pyproject.toml and uv.lock before provisioning.
    """
    try:
        import tomllib
    except ImportError:
        import tomli as tomllib

    manifest = tomllib.loads((HARNESS_ROOT / "manifest.toml").read_text(encoding="utf-8"))
    runtime = manifest["runtime"]["mcp"]
    projects = {name: HARNESS_ROOT / path for name, path in runtime["projects"].items()}
    return {**runtime, "projects": projects, "tools": runtime.get("tools", {})}


def provision_mcp_environments() -> dict[str, str]:
    """Sync every registered Python MCP lock and the graphify uv tool onto F:.

    Require: all mapped projects have valid pyproject.toml and uv.lock files.
    Guarantee: each project uses its own F: environment; uv cache and tool directory use F:.
    Maintain: server source/data paths and non-MCP Python environment are unchanged.
    Assert: every `uv sync --locked` and tool installation exits successfully.

    Returns:
        A mapping from project/tool name to its installed interpreter or executable.
    """
    runtime = mcp_runtime()
    python = Path(runtime["python"])
    env_root = Path(runtime["environments_dir"])
    cache_dir = Path(runtime["cache_dir"])
    tool_dir = Path(runtime["tool_dir"])
    if not python.is_file():
        raise FileNotFoundError(f"MCP base interpreter is missing: {python}")
    installed = {}
    tool_bin = tool_dir / "bin"
    env = {
        **os.environ,
        "UV_CACHE_DIR": str(cache_dir),
        "UV_HTTP_TIMEOUT": "120",
        "UV_TOOL_DIR": str(tool_dir),
        "UV_TOOL_BIN_DIR": str(tool_bin),
    }
    for name, project in runtime["projects"].items():
        lock = project / "uv.lock"
        if not (project / "pyproject.toml").is_file() or not lock.is_file():
            raise FileNotFoundError(f"MCP project {name} needs pyproject.toml and uv.lock: {project}")
        environment = env_root / name
        project_env = {**env, "UV_PROJECT_ENVIRONMENT": str(environment)}
        subprocess.run(
            ["uv", "sync", "--project", str(project), "--locked", "--python", str(python),
             "--cache-dir", str(cache_dir)],
            check=True, env=project_env,
        )
        interpreter = environment / "Scripts" / "python.exe"
        if not interpreter.is_file():
            raise FileNotFoundError(f"uv did not create the MCP interpreter: {interpreter}")
        installed[name] = str(interpreter)

    for name, requirement in runtime["tools"].items():
        subprocess.run(
            ["uv", "tool", "install", "--python", str(python),
             "--cache-dir", str(cache_dir), requirement],
            check=True, env=env,
        )
        installed[name] = str(tool_bin / f"{name}.exe")
    return installed


def find_retrieve_skills_server() -> Path | None:
    """Locate the retrieve-skills server directory."""
    candidates = [
        HARNESS_ROOT / "retrieve-skills",
        Path.home() / ".claude" / "skills" / "retrieve-skills",
        SKILL_STORE / "retrieve-skills",
    ]
    for c in candidates:
        if (c / "server.py").exists():
            return c
    return None


def detect_harnesses() -> dict[str, dict]:
    """Return dict of harness_name -> config for harnesses that exist on disk."""
    found = {}
    for name, cfg in HARNESSES.items():
        root = cfg["root"]
        detect = cfg["detect"]
        if root.exists() and (root / detect).exists():
            found[name] = cfg
    return found


def copy_core_skills(source_store: Path | None = None) -> int:
    """Copy core skills to ~/.skills. Returns count of skills installed."""
    SKILL_STORE.mkdir(parents=True, exist_ok=True)

    # Find source skills — check multiple locations
    sources = [
        source_store,
        Path.home() / ".claude" / "skills" / ".skills",
        Path.home() / "Documents" / "dev" / "skills",
        HARNESS_ROOT / "skills",
    ]

    source = None
    for s in sources:
        if s and s.exists() and any(s.iterdir()):
            source = s
            break

    if source is None:
        print("  WARNING: No source skill store found. Skipping skill copy.")
        print("  Expected locations:")
        for s in sources:
            if s:
                print(f"    {s}")
        return 0

    installed = 0
    for skill_name in CORE_SKILLS:
        src = source / skill_name
        dst = SKILL_STORE / skill_name
        if not src.exists():
            continue
        if dst.exists():
            # Don't overwrite — user may have customized
            installed += 1
            continue
        if (src / "SKILL.md").exists() or skill_name == "memory-index":
            shutil.copytree(src, dst, dirs_exist_ok=True)
            installed += 1
            print(f"    + {skill_name}")

    # Write README if not present
    readme = SKILL_STORE / "README.md"
    if not readme.exists():
        readme.write_text(
            "# ~/.skills — Shared Skill Store\n\n"
            "Skills here are indexed by the retrieve-skills MCP server and injected\n"
            "into any harness session when semantically relevant.\n\n"
            "## Adding Skills\n\n"
            "1. Create a folder: `~/.skills/my-skill/`\n"
            "2. Add a `SKILL.md` with YAML frontmatter (`name` + `description` required)\n"
            "3. Reindex: `curl -X POST http://127.0.0.1:8765/reindex`\n\n"
            "The `description` field is the retrieval unit — write it to match the\n"
            "prompts that should trigger this skill.\n",
            encoding="utf-8",
        )

    return installed


def install_retrieve_skills(server_dir: Path) -> bool:
    """Index the shared skill store using the isolated retrieve-skills environment."""
    print("\n  Installing retrieve-skills dependencies...")
    interpreter = Path(mcp_runtime()["environments_dir"]) / "retrieve-skills" / "Scripts" / "python.exe"
    if not interpreter.is_file():
        print(f"    retrieve-skills environment is not provisioned: {interpreter}")
        return False

    print("  Indexing skill store...")
    indexer = server_dir / "indexer.py"
    if indexer.exists():
        result = subprocess.run(
            [str(interpreter), str(indexer)],
            capture_output=True, text=True,
            env={**os.environ, "SKILL_STORE": str(SKILL_STORE)},
        )
        if result.returncode == 0:
            print(f"    Indexed: {result.stdout.strip()[:100]}")
        else:
            print(f"    WARNING: indexer failed: {result.stderr[:200]}")
            return False

    return True


def prompt_yes_no(question: str, default: bool = True) -> bool:
    """Interactive yes/no prompt."""
    suffix = " [Y/n] " if default else " [y/N] "
    try:
        answer = input(question + suffix).strip().lower()
    except (EOFError, KeyboardInterrupt):
        return default
    if not answer:
        return default
    return answer in ("y", "yes")


def main():
    parser = argparse.ArgumentParser(
        description="SDD Harness Setup — install skills and wire MCP servers to all harnesses"
    )
    parser.add_argument("--all", action="store_true",
                        help="Install everything non-interactively (no prompts)")
    parser.add_argument("--skip-optional", action="store_true",
                        help="Deprecated compatibility flag; harness.json controls MCP registration.")
    parser.add_argument("--target", choices=["claude", "opencode", "kiro", "pi", "codex", "copilot", "vscode", "all"],
                        default="all", help="Sync to a specific harness only")
    parser.add_argument("--provision-mcp-only", action="store_true",
                        help="Lock/sync registered MCP environments without copying skills")
    parser.add_argument("--skill-source", type=Path, default=None,
                        help="Path to source skill store to copy from")
    args = parser.parse_args()

    if args.provision_mcp_only:
        provision_mcp_environments()
        return

    print("=" * 60)
    print("  SDD Harness Setup")
    print("=" * 60)

    # ─── Step 1: Copy core skills to ~/.skills ────────────────────────────────
    print(f"\n[1/4] Installing core skills to {SKILL_STORE}")
    count = copy_core_skills(args.skill_source)
    print(f"  {count} skills in store")

    # ─── Step 2: Find and install retrieve-skills ─────────────────────────────
    print("\n[2/4] Setting up retrieve-skills server")
    provision_mcp_environments()
    server_dir = find_retrieve_skills_server()
    if server_dir:
        print(f"  Found at: {server_dir}")
        install_retrieve_skills(server_dir)
    else:
        print("  WARNING: retrieve-skills server not found.")
        print("  Expected at: ~/.harness/retrieve-skills/ or ~/.claude/skills/retrieve-skills/")
        print("  Skill retrieval will not work until this is installed.")

    # ─── Step 3: Detect targets and project the central registry ───────────────
    print("\n[3/3] Detecting and syncing the central MCP registry")
    found = detect_harnesses()

    if not found:
        print("  No harnesses detected. Install Claude Code, opencode, or Kiro first.")
        return

    print(f"  Detected: {', '.join(found.keys())}")

    import adapter

    for harness_name, cfg in found.items():
        if args.target != "all" and harness_name != args.target:
            continue
        adapter.TARGETS[harness_name](adapter.load_harness())

    # ─── Summary ──────────────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("  Setup complete!")
    print("=" * 60)
    print(f"\n  Skill store: {SKILL_STORE}")
    print(f"  Add new skills: create {SKILL_STORE}/<name>/SKILL.md")
    print("  MCP registrations come from ~/.harness/harness.json.")
    print()

    if server_dir:
        print("  HTTP MCP services remain managed by their configured supervisors.")
        print(f"  retrieve-skills source: {server_dir}")

    print("  Verify everything:")
    print("    (Invoke-WebRequest http://127.0.0.1:8765/health -UseBasicParsing).Content")
    print("    (Invoke-WebRequest http://127.0.0.1:8055/health -UseBasicParsing).Content")


if __name__ == "__main__":
    main()
