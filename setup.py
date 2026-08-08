"""SDD Harness Setup — one-command installer for all detected harnesses.

Usage:
    python setup.py                    # interactive (prompts for optional MCPs)
    python setup.py --all              # install everything non-interactively
    python setup.py --skip-optional    # core only (retrieve-skills), no todo/memory-index
    python setup.py --target claude    # sync to one harness only

What it does:
    1. Copies core skills from this repo to ~/.skills (the shared skill store)
    2. Installs retrieve-skills server + indexes the store
    3. Detects which harnesses are present (Claude Code, opencode, Kiro, pi)
    4. Syncs MCP server registrations to all detected harnesses
    5. Optionally wires todo and memory-index MCP servers

Prerequisites:
    - Python 3.10+ with pip
    - For retrieve-skills: sentence-transformers, fastmcp, numpy, pyyaml
    - For memory-index: chromadb, ollama (python), pyyaml, fastmcp
    - For todo: fastmcp
"""
from __future__ import annotations

import argparse
import json
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
        "mcp_file": Path.home() / ".claude.json",
        "mcp_key": "mcpServers",
    },
    "opencode": {
        "root": Path.home() / ".config" / "opencode",
        "detect": "opencode.json",
        "mcp_file": Path.home() / ".config" / "opencode" / "opencode.json",
        "mcp_key": "mcp",
    },
    "kiro": {
        "root": Path.home() / ".kiro",
        "detect": "steering",
        "mcp_file": Path.home() / ".kiro" / "settings" / "mcp.json",
        "mcp_key": "mcpServers",
    },
    "pi": {
        "root": Path.home() / ".pi",
        "detect": "agent",
        "mcp_file": None,  # pi uses npm packages, not mcp.json
        "mcp_key": None,
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
        Path(r"C:\Users\user\Documents\dev\skills"),
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


def build_mcp_entry(name: str, server_path: Path, harness: str) -> dict:
    """Build an MCP server entry in the native format for a harness."""
    python = find_python()

    if name == "retrieve-skills":
        # HTTP transport — same for all harnesses
        entry = {"url": "http://127.0.0.1:8765/mcp"}
        if harness == "kiro":
            entry["disabled"] = False
        elif harness == "opencode":
            entry = {"type": "streamable-http", "url": "http://127.0.0.1:8765/mcp", "enabled": True}
        return entry

    elif name == "memory-index":
        entry = {"url": "http://127.0.0.1:8055/mcp"}
        if harness == "kiro":
            entry["disabled"] = False
        elif harness == "opencode":
            entry = {"type": "streamable-http", "url": "http://127.0.0.1:8055/mcp", "enabled": True}
        return entry

    elif name == "todo":
        # stdio transport
        script = str(server_path / "todo_mcp.py")
        if harness == "kiro":
            return {"command": python, "args": [script], "disabled": False}
        elif harness == "opencode":
            return {"type": "local", "command": [python, script], "enabled": True}
        else:  # claude
            return {"type": "stdio", "command": python, "args": [script]}

    return {}


def sync_harness_mcp(harness_name: str, cfg: dict, servers: dict[str, dict]) -> None:
    """Write MCP entries to a harness's config file."""
    mcp_file = cfg.get("mcp_file")
    mcp_key = cfg.get("mcp_key")

    if not mcp_file or not mcp_key:
        print(f"    {harness_name}: no MCP config path (skipped)")
        return

    mcp_file = Path(mcp_file)
    mcp_file.parent.mkdir(parents=True, exist_ok=True)

    # Read existing config
    data = {}
    if mcp_file.exists():
        try:
            import re
            text = mcp_file.read_text(encoding="utf-8")
            # Strip JSONC comments for opencode
            if harness_name == "opencode":
                text = re.sub(r"//[^\n]*", "", text)
                text = re.sub(r"[\x00-\x1f]", " ", text)
                text = re.sub(r",\s*([}\]])", r"\1", text)
            data = json.loads(text) if text.strip() else {}
        except (json.JSONDecodeError, OSError):
            data = {}

    # Merge servers
    existing = data.get(mcp_key, {})
    existing.update(servers)
    data[mcp_key] = existing

    mcp_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
    print(f"    {harness_name}: {mcp_file} ({len(servers)} servers)")


def install_retrieve_skills(server_dir: Path) -> bool:
    """Install dependencies and index the skill store."""
    print("\n  Installing retrieve-skills dependencies...")
    python = find_python()
    req = server_dir / "requirements.txt"
    if req.exists():
        result = subprocess.run(
            [python, "-m", "pip", "install", "-r", str(req), "-q"],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            print(f"    WARNING: pip install failed: {result.stderr[:200]}")
            return False

    print("  Indexing skill store...")
    indexer = server_dir / "indexer.py"
    if indexer.exists():
        result = subprocess.run(
            [python, str(indexer)],
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
                        help="Core only (retrieve-skills). Skip todo and memory-index.")
    parser.add_argument("--target", choices=["claude", "opencode", "kiro", "pi", "all"],
                        default="all", help="Sync to a specific harness only")
    parser.add_argument("--skill-source", type=Path, default=None,
                        help="Path to source skill store to copy from")
    args = parser.parse_args()

    interactive = not args.all and not args.skip_optional
    install_todo = args.all
    install_memory = args.all

    print("=" * 60)
    print("  SDD Harness Setup")
    print("=" * 60)

    # ─── Step 1: Copy core skills to ~/.skills ────────────────────────────────
    print(f"\n[1/4] Installing core skills to {SKILL_STORE}")
    count = copy_core_skills(args.skill_source)
    print(f"  {count} skills in store")

    # ─── Step 2: Find and install retrieve-skills ─────────────────────────────
    print("\n[2/4] Setting up retrieve-skills server")
    server_dir = find_retrieve_skills_server()
    if server_dir:
        print(f"  Found at: {server_dir}")
        install_retrieve_skills(server_dir)
    else:
        print("  WARNING: retrieve-skills server not found.")
        print("  Expected at: ~/.harness/retrieve-skills/ or ~/.claude/skills/retrieve-skills/")
        print("  Skill retrieval will not work until this is installed.")

    # ─── Step 3: Optional MCP servers ─────────────────────────────────────────
    print("\n[3/4] Optional MCP servers")

    if interactive:
        install_todo = prompt_yes_no("  Wire todo MCP server (persistent task tracking)?")
        install_memory = prompt_yes_no("  Wire memory-index MCP server (semantic memory)?")
    elif not args.skip_optional:
        install_todo = True
        install_memory = True

    if install_todo:
        todo_path = SKILL_STORE / "todo"
        if (todo_path / "todo_mcp.py").exists():
            print(f"    todo: {todo_path / 'todo_mcp.py'}")
        else:
            print("    todo: todo_mcp.py not found in skill store")
            install_todo = False

    if install_memory:
        mem_path = SKILL_STORE / "memory-index"
        if (mem_path / "mem_server.py").exists():
            print(f"    memory-index: {mem_path / 'mem_server.py'}")
        else:
            print("    memory-index: mem_server.py not found in skill store")
            install_memory = False

    # ─── Step 4: Detect harnesses and sync ────────────────────────────────────
    print("\n[4/4] Detecting and syncing harnesses")
    found = detect_harnesses()

    if not found:
        print("  No harnesses detected. Install Claude Code, opencode, or Kiro first.")
        return

    print(f"  Detected: {', '.join(found.keys())}")

    for harness_name, cfg in found.items():
        if args.target != "all" and harness_name != args.target:
            continue

        servers = {}

        # retrieve-skills (always — it's the core)
        if server_dir:
            servers["retrieve-skills"] = build_mcp_entry(
                "retrieve-skills", server_dir, harness_name
            )

        # optional: todo
        if install_todo:
            servers["todo"] = build_mcp_entry(
                "todo", SKILL_STORE / "todo", harness_name
            )

        # optional: memory-index
        if install_memory:
            servers["memory-index"] = build_mcp_entry(
                "memory-index", SKILL_STORE / "memory-index", harness_name
            )

        if servers:
            sync_harness_mcp(harness_name, cfg, servers)

    # ─── Summary ──────────────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("  Setup complete!")
    print("=" * 60)
    print(f"\n  Skill store: {SKILL_STORE}")
    print(f"  Add new skills: create {SKILL_STORE}/<name>/SKILL.md")
    print(f"  Reindex after changes: curl -X POST http://127.0.0.1:8765/reindex")
    print()

    if server_dir:
        print("  To start the retrieve-skills server:")
        print(f"    cd {server_dir}")
        if os.name == "nt":
            print(f"    Start-Process -FilePath python -ArgumentList server.py -WindowStyle Hidden")
        else:
            print(f"    nohup python server.py &")
        print()

    if install_memory:
        print("  To start the memory-index server:")
        mem_server = SKILL_STORE / "memory-index" / "mem_server.py"
        if os.name == "nt":
            print(f"    Start-Process -FilePath python -ArgumentList \"{mem_server}\" -WindowStyle Hidden")
        else:
            print(f"    nohup python {mem_server} &")
        print()

    if install_todo:
        print("  Todo server runs via stdio (started per-session by the harness).")
        print()

    print("  Verify everything:")
    print("    (Invoke-WebRequest http://127.0.0.1:8765/health -UseBasicParsing).Content")
    if install_memory:
        print("    (Invoke-WebRequest http://127.0.0.1:8055/health -UseBasicParsing).Content")


if __name__ == "__main__":
    main()
