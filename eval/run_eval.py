"""10-Edit Coherence Eval Runner.

Creates two git worktrees from the seed, runs 10 sequential opencode edits
in each (one with hooks on, one with hooks off), and snapshots after each edit.

Usage:
    python eval/run_eval.py [--arm hooks-on|hooks-off|both] [--start N] [--end N]

Requires: opencode CLI, git, python 3.10+
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

EVAL_DIR = Path(__file__).parent
REPO_ROOT = EVAL_DIR.parent
SEED_DIR = EVAL_DIR / "seed"
PROMPTS_FILE = EVAL_DIR / "prompts.json"
RESULTS_DIR = EVAL_DIR / "results"

# Worktree locations
WORKTREE_BASE = EVAL_DIR / "worktrees"

TIMEOUT_SECONDS = 300  # 5 min per edit

# Direct path to opencode binary (bypasses .ps1 wrapper)
OPENCODE_EXE = r"C:\Users\user\AppData\Roaming\npm\node_modules\opencode-ai\bin\opencode.exe"


def load_prompts() -> list[str]:
    with open(PROMPTS_FILE) as f:
        return json.load(f)


def create_arm_repo(arm: str) -> Path:
    """Create a standalone git repo for the given arm, seeded with taskq/."""
    arm_path = WORKTREE_BASE / arm
    if arm_path.exists():
        print(f"[{arm}] Removing existing arm repo...")
        # Git objects are read-only on Windows; force-remove
        subprocess.run(["cmd", "/c", "rmdir", "/s", "/q", str(arm_path)],
                       capture_output=True)

    arm_path.mkdir(parents=True)
    print(f"[{arm}] Creating arm repo at {arm_path}...")

    # Init git repo
    subprocess.run(["git", "init", "."], cwd=arm_path, capture_output=True, check=True)
    subprocess.run(["git", "config", "user.email", "eval@harness"], cwd=arm_path, capture_output=True)
    subprocess.run(["git", "config", "user.name", "eval"], cwd=arm_path, capture_output=True)

    # Copy seed content
    shutil.copytree(SEED_DIR / "taskq", arm_path / "taskq",
                    ignore=shutil.ignore_patterns("__pycache__"))

    # Initial commit
    subprocess.run(["git", "add", "-A"], cwd=arm_path, capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "-m", "seed: taskq module"],
        cwd=arm_path, capture_output=True, check=True
    )
    return arm_path


def run_edit(wt_path: Path, prompt: str, edit_num: int, arm: str, hooks_enabled: bool) -> dict:
    """Run a single opencode edit and return metadata."""
    env = os.environ.copy()
    env["HARNESS_HOOKS_ENABLED"] = "1" if hooks_enabled else "0"

    print(f"  [{arm}] Edit {edit_num}: {prompt[:60]}...")
    start = time.time()

    try:
        cmd = [OPENCODE_EXE, "run", prompt, "--pure"]
        result = subprocess.run(
            cmd,
            cwd=wt_path,
            env=env,
            capture_output=True,
            text=True,
            timeout=TIMEOUT_SECONDS
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
    commit_result = subprocess.run(
        ["git", "commit", "-m", f"edit-{edit_num:02d}: {prompt[:50]}", "--allow-empty"],
        cwd=wt_path, capture_output=True, text=True
    )

    # Get commit hash
    hash_result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=wt_path, capture_output=True, text=True
    )
    commit_hash = hash_result.stdout.strip()

    return {
        "edit": edit_num,
        "prompt": prompt,
        "success": success,
        "elapsed_seconds": round(elapsed, 1),
        "commit": commit_hash,
        "error": error if not success else None,
        "output_tail": output[-500:] if output else None
    }


def run_arm(arm: str, hooks_enabled: bool, prompts: list[str],
            start: int = 1, end: int = 10) -> list[dict]:
    """Run all edits for one arm."""
    wt_path = create_arm_repo(arm)
    results = []

    print(f"\n{'='*60}")
    print(f"  ARM: {arm} (hooks={'ON' if hooks_enabled else 'OFF'})")
    print(f"  Edits {start}-{end} of {len(prompts)}")
    print(f"{'='*60}\n")

    for i in range(start - 1, min(end, len(prompts))):
        edit_result = run_edit(wt_path, prompts[i], i + 1, arm, hooks_enabled)
        results.append(edit_result)
        status = "OK" if edit_result["success"] else "FAIL"
        print(f"  [{arm}] Edit {i+1}: {status} ({edit_result['elapsed_seconds']}s)")

    return results


def save_results(arm: str, results: list[dict]):
    """Save results to JSON."""
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RESULTS_DIR / f"{arm}.json"
    with open(out_path, "w") as f:
        json.dump({"arm": arm, "edits": results}, f, indent=2)
    print(f"\n  Results saved to {out_path}")


def main():
    parser = argparse.ArgumentParser(description="10-Edit Coherence Eval Runner")
    parser.add_argument("--arm", choices=["hooks-on", "hooks-off", "both"],
                        default="both", help="Which arm to run")
    parser.add_argument("--start", type=int, default=1, help="First edit number (1-indexed)")
    parser.add_argument("--end", type=int, default=10, help="Last edit number (1-indexed)")
    args = parser.parse_args()

    prompts = load_prompts()
    assert len(prompts) == 10, f"Expected 10 prompts, got {len(prompts)}"

    arms_to_run = []
    if args.arm in ("hooks-on", "both"):
        arms_to_run.append(("hooks-on", True))
    if args.arm in ("hooks-off", "both"):
        arms_to_run.append(("hooks-off", False))

    for arm_name, hooks_enabled in arms_to_run:
        results = run_arm(arm_name, hooks_enabled, prompts, args.start, args.end)
        save_results(arm_name, results)

    print("\n" + "="*60)
    print("  EVAL COMPLETE")
    print("  Run score.py to analyze results")
    print("="*60)


if __name__ == "__main__":
    main()
