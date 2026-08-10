"""Scorer for the 10-Edit Coherence Eval.

Checks out each edit snapshot and runs metrics against the taskq/ module.

Usage:
    python eval/score.py [--arm hooks-on|hooks-off|both]

Metrics:
    - LOC (informational)
    - Dead code (vulture)
    - Lint issues (ruff)
    - Test pass rate (pytest)
    - Duplication (custom AST)
    - Import coherence (custom)

Output: eval/results/<arm>_scores.json + summary table to stdout.
"""

import ast
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

EVAL_DIR = Path(__file__).parent
RESULTS_DIR = EVAL_DIR / "results"
WORKTREE_BASE = EVAL_DIR / "worktrees"

# Use py310 where ruff/vulture/pytest are installed
PYTHON = r"C:\Users\user\py310\Scripts\python.exe"


def get_python_files(root: Path) -> list[Path]:
    """Get all .py files under root, excluding __pycache__."""
    return [p for p in root.rglob("*.py") if "__pycache__" not in str(p)]


def metric_loc(taskq_dir: Path) -> dict:
    """Count total lines of code."""
    files = get_python_files(taskq_dir)
    total = sum(len(f.read_text(encoding="utf-8").splitlines()) for f in files)
    return {"loc": total, "files": len(files)}


def metric_dead_code(taskq_dir: Path) -> dict:
    """Run vulture for unused code detection."""
    try:
        result = subprocess.run(
            [PYTHON, "-m", "vulture", str(taskq_dir), "--min-confidence", "80"],
            capture_output=True, text=True, timeout=30
        )
        lines = [l for l in result.stdout.strip().splitlines() if l.strip()]
        return {"dead_code_items": len(lines), "details": lines[:10]}
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return {"dead_code_items": -1, "details": ["vulture not available"]}


def metric_lint(taskq_dir: Path) -> dict:
    """Run ruff for lint issues."""
    try:
        result = subprocess.run(
            [PYTHON, "-m", "ruff", "check", str(taskq_dir), "--output-format", "json"],
            capture_output=True, text=True, timeout=30
        )
        issues = json.loads(result.stdout) if result.stdout.strip() else []
        by_code = Counter(i.get("code", "unknown") for i in issues)
        return {"lint_issues": len(issues), "by_code": dict(by_code)}
    except (subprocess.TimeoutExpired, FileNotFoundError, json.JSONDecodeError):
        return {"lint_issues": -1, "by_code": {}}


def metric_tests(taskq_dir: Path) -> dict:
    """Run pytest and count pass/fail."""
    test_dir = taskq_dir / "tests"
    if not test_dir.exists():
        return {"passed": 0, "failed": 0, "errors": 0, "total": 0, "pass_rate": 0.0}

    try:
        result = subprocess.run(
            [PYTHON, "-m", "pytest", str(test_dir), "--tb=no", "-q", "--no-header"],
            capture_output=True, text=True, timeout=60,
            cwd=taskq_dir.parent  # run from worktree root so imports resolve
        )
        output = result.stdout + result.stderr
        # Parse pytest summary line like "3 passed, 1 failed in 0.5s"
        passed = failed = errors = 0
        for line in output.splitlines():
            if "passed" in line or "failed" in line or "error" in line:
                import re
                m_pass = re.search(r"(\d+) passed", line)
                m_fail = re.search(r"(\d+) failed", line)
                m_err = re.search(r"(\d+) error", line)
                if m_pass:
                    passed = int(m_pass.group(1))
                if m_fail:
                    failed = int(m_fail.group(1))
                if m_err:
                    errors = int(m_err.group(1))
        total = passed + failed + errors
        rate = passed / total if total > 0 else 0.0
        return {"passed": passed, "failed": failed, "errors": errors,
                "total": total, "pass_rate": round(rate, 3)}
    except subprocess.TimeoutExpired:
        return {"passed": 0, "failed": 0, "errors": 0, "total": 0, "pass_rate": 0.0}


def metric_duplication(taskq_dir: Path) -> dict:
    """Simple AST-based duplication: count identical function bodies."""
    files = get_python_files(taskq_dir)
    body_hashes = []
    for f in files:
        try:
            tree = ast.parse(f.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                body_str = ast.dump(ast.Module(body=node.body, type_ignores=[]))
                body_hashes.append(body_str)

    counts = Counter(body_hashes)
    duplicates = sum(c - 1 for c in counts.values() if c > 1)
    return {"duplicate_function_bodies": duplicates, "total_functions": len(body_hashes)}


def metric_imports(taskq_dir: Path) -> dict:
    """Check for circular imports and orphan modules."""
    files = get_python_files(taskq_dir)
    modules = {}
    imports_graph = {}

    for f in files:
        rel = f.relative_to(taskq_dir)
        mod_name = str(rel).replace("\\", "/").replace("/", ".").removesuffix(".py")
        if mod_name.endswith(".__init__"):
            mod_name = mod_name.removesuffix(".__init__")
        modules[mod_name] = f

        try:
            tree = ast.parse(f.read_text(encoding="utf-8"))
        except SyntaxError:
            continue

        deps = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                if node.level > 0:  # relative import
                    deps.add(node.module)
        imports_graph[mod_name] = deps

    # Detect cycles (simple DFS)
    visited = set()
    in_stack = set()
    cycles = []

    def dfs(mod, path):
        if mod in in_stack:
            cycles.append(path + [mod])
            return
        if mod in visited:
            return
        visited.add(mod)
        in_stack.add(mod)
        for dep in imports_graph.get(mod, []):
            dfs(dep, path + [mod])
        in_stack.discard(mod)

    for m in imports_graph:
        dfs(m, [])

    # Orphans: modules not imported by anything
    all_imported = set()
    for deps in imports_graph.values():
        all_imported.update(deps)

    non_init = {m for m in modules if not m.endswith("__init__") and "tests" not in m}
    orphans = [m for m in non_init if m.split(".")[-1] not in all_imported
               and m != "taskq" and "__main__" not in m]

    return {"circular_imports": len(cycles), "orphan_modules": orphans}


def compute_composite(metrics: dict) -> float:
    """Compute weighted composite score 0-1 (higher = better)."""
    scores = {}

    # Dead code: 0 items = 1.0, each item costs 0.1, floor at 0
    dc = metrics.get("dead_code", {}).get("dead_code_items", 0)
    scores["dead_code"] = max(0.0, 1.0 - dc * 0.1) if dc >= 0 else 0.5

    # Lint: 0 issues = 1.0, each issue costs 0.05, floor at 0
    lint = metrics.get("lint", {}).get("lint_issues", 0)
    scores["lint"] = max(0.0, 1.0 - lint * 0.05) if lint >= 0 else 0.5

    # Tests: pass_rate directly
    scores["tests"] = metrics.get("tests", {}).get("pass_rate", 0.0)

    # Duplication: 0 dupes = 1.0, each costs 0.15
    dupes = metrics.get("duplication", {}).get("duplicate_function_bodies", 0)
    scores["duplication"] = max(0.0, 1.0 - dupes * 0.15)

    # Imports: 0 cycles + 0 orphans = 1.0
    imp = metrics.get("imports", {})
    cycles = imp.get("circular_imports", 0)
    orphans = len(imp.get("orphan_modules", []))
    scores["imports"] = max(0.0, 1.0 - (cycles * 0.3 + orphans * 0.1))

    # Weighted composite
    weights = {"dead_code": 0.2, "lint": 0.1, "tests": 0.3,
               "duplication": 0.2, "imports": 0.2}
    composite = sum(scores[k] * weights[k] for k in weights)
    return round(composite, 3)


def score_snapshot(wt_path: Path, commit: str) -> dict:
    """Checkout a commit and score it."""
    subprocess.run(["git", "checkout", commit], cwd=wt_path,
                   capture_output=True, check=True)

    taskq_dir = wt_path / "taskq"
    if not taskq_dir.exists():
        return {"error": "taskq/ not found", "composite": 0.0}

    metrics = {
        "loc": metric_loc(taskq_dir),
        "dead_code": metric_dead_code(taskq_dir),
        "lint": metric_lint(taskq_dir),
        "tests": metric_tests(taskq_dir),
        "duplication": metric_duplication(taskq_dir),
        "imports": metric_imports(taskq_dir),
    }
    metrics["composite"] = compute_composite(metrics)
    return metrics


def score_arm(arm: str) -> list[dict]:
    """Score all edits for an arm."""
    results_file = RESULTS_DIR / f"{arm}.json"
    if not results_file.exists():
        print(f"[{arm}] No results file found at {results_file}")
        return []

    with open(results_file) as f:
        data = json.load(f)

    wt_path = WORKTREE_BASE / arm
    if not wt_path.exists():
        print(f"[{arm}] Arm repo not found at {wt_path}")
        return []

    scores = []
    for edit in data["edits"]:
        commit = edit["commit"]
        print(f"  [{arm}] Scoring edit {edit['edit']} ({commit[:7]})...")
        metrics = score_snapshot(wt_path, commit)
        scores.append({"edit": edit["edit"], "commit": commit, "metrics": metrics})

    # Return to latest commit
    subprocess.run(["git", "checkout", "-"], cwd=wt_path, capture_output=True)

    return scores


def print_comparison(all_scores: dict):
    """Print side-by-side comparison table."""
    print(f"\n{'='*70}")
    print(f"  COMPOSITE SCORES (higher = better)")
    print(f"{'='*70}")
    print(f"  {'Edit':<6}", end="")
    for arm in all_scores:
        print(f"  {arm:<12}", end="")
    print()
    print(f"  {'-'*6}", end="")
    for _ in all_scores:
        print(f"  {'-'*12}", end="")
    print()

    max_edits = max(len(s) for s in all_scores.values()) if all_scores else 0
    for i in range(max_edits):
        print(f"  {i+1:<6}", end="")
        for arm, scores in all_scores.items():
            if i < len(scores):
                c = scores[i]["metrics"].get("composite", 0)
                print(f"  {c:<12.3f}", end="")
            else:
                print(f"  {'---':<12}", end="")
        print()

    # Final summary
    print(f"\n  {'FINAL':<6}", end="")
    for arm, scores in all_scores.items():
        if scores:
            final = scores[-1]["metrics"].get("composite", 0)
            print(f"  {final:<12.3f}", end="")
    print("\n")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Score eval snapshots")
    parser.add_argument("--arm", choices=["hooks-on", "hooks-off", "both"],
                        default="both")
    args = parser.parse_args()

    arms = []
    if args.arm in ("hooks-on", "both"):
        arms.append("hooks-on")
    if args.arm in ("hooks-off", "both"):
        arms.append("hooks-off")

    all_scores = {}
    for arm in arms:
        print(f"\nScoring arm: {arm}")
        scores = score_arm(arm)
        all_scores[arm] = scores

        # Save
        RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        out_path = RESULTS_DIR / f"{arm}_scores.json"
        with open(out_path, "w") as f:
            json.dump({"arm": arm, "scores": scores}, f, indent=2)
        print(f"  Saved to {out_path}")

    print_comparison(all_scores)


if __name__ == "__main__":
    main()
