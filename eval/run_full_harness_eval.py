"""Full-Harness Eval Runner: specs-on vs specs-off.

Tests whether structured spec-tracking via the specs MCP server improves
code coherence across 10 sequential edits with full MCP access.

Usage:
    python eval/run_full_harness_eval.py [--arm specs-on|specs-off|both] [--start N] [--end N]

Requires: opencode CLI, git, python 3.10+, all MCP servers running
"""

import argparse
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

EVAL_DIR = Path(__file__).parent
REPO_ROOT = EVAL_DIR.parent
SEED_DIR = EVAL_DIR / "seed"
PROMPTS_FILE = EVAL_DIR / "prompts.json"
RESULTS_DIR = EVAL_DIR / "results" / "full-harness"
CONFIGS_DIR = EVAL_DIR / "configs"
WORKTREE_BASE = EVAL_DIR / "worktrees"

TIMEOUT_SECONDS = 300  # 5 min per edit

OPENCODE_EXE = r"C:\Users\user\AppData\Roaming\npm\node_modules\opencode-ai\bin\opencode.exe"

# Arm configs
ARM_CONFIGS = {
    "specs-on": {
        "config": CONFIGS_DIR / "harness-a.json",
        "steering": CONFIGS_DIR / "steering-a.md",
        "specs_enabled": True,
    },
    "specs-off": {
        "config": CONFIGS_DIR / "harness-b.json",
        "steering": None,
        "specs_enabled": False,
    },
}


def load_prompts() -> list[str]:
    with open(PROMPTS_FILE) as f:
        return json.load(f)


def create_arm_repo(arm: str) -> Path:
    """Create a standalone git repo for the given arm, seeded with taskq/."""
    arm_path = WORKTREE_BASE / f"full-{arm}"
    if arm_path.exists():
        shutil.rmtree(arm_path, onerror=lambda fn, path, exc: (os.chmod(path, 0o777), fn(path)))

    arm_path.mkdir(parents=True, exist_ok=True)
    print(f"[{arm}] Creating arm repo at {arm_path}...")

    # Init git repo
    subprocess.run(["git", "init", "."], cwd=arm_path, capture_output=True, check=True)
    subprocess.run(["git", "config", "user.email", "eval@harness"], cwd=arm_path, capture_output=True)
    subprocess.run(["git", "config", "user.name", "eval"], cwd=arm_path, capture_output=True)

    # Copy seed content
    shutil.copytree(SEED_DIR / "taskq", arm_path / "taskq",
                    ignore=shutil.ignore_patterns("__pycache__"))

    # Place MCP config (opencode reads from .mcp.json or opencode.json in cwd)
    arm_cfg = ARM_CONFIGS[arm]
    config_data = json.loads(arm_cfg["config"].read_text(encoding="utf-8"))
    # Write as opencode.json so model + mcp config are both picked up
    (arm_path / "opencode.json").write_text(json.dumps(config_data, indent=2), encoding="utf-8")

    # Place steering doc for Arm A
    if arm_cfg["steering"]:
        steering_content = arm_cfg["steering"].read_text(encoding="utf-8")
        (arm_path / "AGENTS.md").write_text(steering_content, encoding="utf-8")

    # Initial commit
    subprocess.run(["git", "add", "-A"], cwd=arm_path, capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "-m", "seed: taskq module + harness config"],
        cwd=arm_path, capture_output=True, check=True
    )
    return arm_path


def run_edit(wt_path: Path, prompt: str, edit_num: int, arm: str) -> dict:
    """Run a single opencode edit and return metadata."""
    print(f"  [{arm}] Edit {edit_num}: {prompt[:60]}...")
    start = time.time()

    try:
        # No --pure: MCP is live
        cmd = [OPENCODE_EXE, "run", prompt]
        result = subprocess.run(
            cmd,
            cwd=wt_path,
            capture_output=True,
            text=True,
            timeout=TIMEOUT_SECONDS,
        )
        elapsed = time.time() - start
        success = result.returncode == 0
        output = result.stdout[-2000:] if result.stdout else ""
        error = result.stderr[-1000:] if result.stderr else ""
    except subprocess.TimeoutExpired:
        elapsed = TIMEOUT_SECONDS
        success = False
        output = ""
        error = "TIMEOUT"

    # Snapshot: commit all changes
    subprocess.run(["git", "add", "-A"], cwd=wt_path, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", f"edit-{edit_num:02d}: {prompt[:50]}", "--allow-empty"],
        cwd=wt_path, capture_output=True, text=True,
    )

    # Get commit hash
    hash_result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=wt_path, capture_output=True, text=True,
    )
    commit_hash = hash_result.stdout.strip()

    return {
        "edit": edit_num,
        "prompt": prompt,
        "success": success,
        "elapsed_seconds": round(elapsed, 1),
        "commit": commit_hash,
        "error": error if not success else None,
        "output_tail": output[-500:] if output else None,
    }


def start_eval_specs_server(arm_path: Path, port: int = 8058) -> subprocess.Popen:
    """Start an isolated specs MCP server for the eval on a different port."""
    # Copy specs_mcp.py and specs_db.py into the arm dir so it uses a local DB
    specs_src = Path.home() / ".harness" / "specs"
    shutil.copy2(specs_src / "specs_db.py", arm_path / "specs_db.py")
    shutil.copy2(specs_src / "specs_mcp.py", arm_path / "specs_mcp.py")

    proc = subprocess.Popen(
        [sys.executable, "specs_mcp.py", "--port", str(port)],
        cwd=arm_path,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    # Wait for it to be ready
    import urllib.request
    for _ in range(30):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=2)
            return proc
        except Exception:
            time.sleep(1)
    raise RuntimeError(f"Eval specs server on port {port} failed to start")


def stop_eval_specs_server(proc: subprocess.Popen):
    """Kill the isolated eval specs server."""
    if proc and proc.poll() is None:
        proc.terminate()
        proc.wait(timeout=5)


def dump_specs_db(arm_path: Path) -> dict:
    """Extract the eval-local specs.db contents for analysis."""
    specs_db = arm_path / "specs.db"
    if not specs_db.exists():
        return {"error": "specs.db not found in arm dir"}

    conn = sqlite3.connect(str(specs_db))
    conn.row_factory = sqlite3.Row
    dump = {}
    for table in ["requirements", "decisions", "tasks", "settings", "canon", "dispositions"]:
        try:
            rows = conn.execute(f"SELECT * FROM {table}").fetchall()
            dump[table] = [dict(r) for r in rows]
        except sqlite3.OperationalError:
            dump[table] = []
    conn.close()
    return dump


def run_arm(arm: str, prompts: list[str], start: int = 1, end: int = 10) -> list[dict]:
    """Run all edits for one arm."""
    wt_path = create_arm_repo(arm)
    results = []
    specs_proc = None

    print(f"\n{'='*60}")
    print(f"  ARM: {arm} (specs={'ON' if ARM_CONFIGS[arm]['specs_enabled'] else 'OFF'})")
    print(f"  Edits {start}-{end} of {len(prompts)}")
    print(f"{'='*60}\n")

    # For specs-on arm, start an isolated specs server on port 8058
    if ARM_CONFIGS[arm]["specs_enabled"]:
        print(f"  [{arm}] Starting isolated specs server on :8058...")
        specs_proc = start_eval_specs_server(wt_path, port=8058)
        # Patch the opencode.json to point at the eval-local port
        mcp_cfg = json.loads((wt_path / "opencode.json").read_text(encoding="utf-8"))
        mcp_cfg["mcp"]["specs"]["url"] = "http://127.0.0.1:8058/mcp"
        (wt_path / "opencode.json").write_text(json.dumps(mcp_cfg, indent=2), encoding="utf-8")
        print(f"  [{arm}] Eval specs server ready")

    try:
        for i in range(start - 1, min(end, len(prompts))):
            edit_result = run_edit(wt_path, prompts[i], i + 1, arm)
            results.append(edit_result)
            status = "OK" if edit_result["success"] else "FAIL"
            print(f"  [{arm}] Edit {i+1}: {status} ({edit_result['elapsed_seconds']}s)")
    finally:
        if specs_proc:
            stop_eval_specs_server(specs_proc)

    return results


def save_results(arm: str, results: list[dict], arm_path: Path):
    """Save results to JSON."""
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RESULTS_DIR / f"{arm}.json"

    payload = {"arm": arm, "edits": results}

    # For specs-on arm, also dump the specs DB state
    if ARM_CONFIGS[arm]["specs_enabled"]:
        payload["specs_db_dump"] = dump_specs_db(arm_path)

    with open(out_path, "w") as f:
        json.dump(payload, f, indent=2)
    print(f"\n  Results saved to {out_path}")


def pre_flight_check():
    """Verify all MCP servers are reachable before starting."""
    import urllib.request

    servers = {
        "retrieve-skills": "http://127.0.0.1:8765/health",
        "memory-index": "http://127.0.0.1:8055/health",
        "specs": "http://127.0.0.1:8057/health",
    }
    all_ok = True
    for name, url in servers.items():
        try:
            resp = urllib.request.urlopen(url, timeout=5)
            data = json.loads(resp.read())
            print(f"  [OK] {name}: {data.get('status', '?')}")
        except Exception as e:
            print(f"  [FAIL] {name}: {e}")
            all_ok = False

    if not all_ok:
        print("\n  ERROR: Not all MCP servers are running. Aborting.")
        sys.exit(1)

    # Verify opencode exists
    if not Path(OPENCODE_EXE).exists():
        print(f"  [FAIL] opencode not found at {OPENCODE_EXE}")
        sys.exit(1)
    print(f"  [OK] opencode: {OPENCODE_EXE}")


def main():
    parser = argparse.ArgumentParser(description="Full-Harness Eval: specs-on vs specs-off")
    parser.add_argument("--arm", choices=["specs-on", "specs-off", "both"],
                        default="both", help="Which arm to run")
    parser.add_argument("--start", type=int, default=1, help="First edit number (1-indexed)")
    parser.add_argument("--end", type=int, default=10, help="Last edit number (1-indexed)")
    parser.add_argument("--skip-preflight", action="store_true", help="Skip server health checks")
    args = parser.parse_args()

    print("=" * 60)
    print("  FULL-HARNESS EVAL: Specs MCP Impact")
    print("=" * 60)

    if not args.skip_preflight:
        print("\nPre-flight checks:")
        pre_flight_check()

    prompts = load_prompts()
    assert len(prompts) == 10, f"Expected 10 prompts, got {len(prompts)}"

    arms_to_run = []
    if args.arm in ("specs-on", "both"):
        arms_to_run.append("specs-on")
    if args.arm in ("specs-off", "both"):
        arms_to_run.append("specs-off")

    for arm_name in arms_to_run:
        results = run_arm(arm_name, prompts, args.start, args.end)
        arm_path = WORKTREE_BASE / f"full-{arm_name}"
        save_results(arm_name, results, arm_path)

    print("\n" + "=" * 60)
    print("  EVAL COMPLETE")
    print("  Run score.py on results/full-harness/ to analyze")
    print("=" * 60)


if __name__ == "__main__":
    main()
