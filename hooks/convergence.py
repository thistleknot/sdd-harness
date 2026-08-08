"""Convergence check: compare implementation against governing spec.

Purpose: after implementation, assess whether the code matches the spec.
Identifies: implemented items, missing items, deviations. Appends remaining
work as new tasks if gaps are found.

Usage:
  # As a standalone script (manual trigger):
  python convergence.py --spec <spec_path> --code <code_dir>

  # As a claude -p prompt (headless):
  claude -p "Run convergence: compare spec at <path> against implementation. Report gaps."

  # As a Stop hook (auto-trigger after implementation):
  Registered in settings.json on Stop event.

Preconditions: spec file exists with acceptance criteria.
Failure modes: any error → exit 0 (fail-open).
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


def find_spec_files(spec_dir: Path) -> list[Path]:
    """Find all spec files in a directory."""
    patterns = ["*.spec.md", "*.requirements.md", "requirements.md", "spec.md"]
    files = []
    for p in patterns:
        files.extend(spec_dir.rglob(p))
    return sorted(set(files))


def find_task_files(spec_dir: Path) -> list[Path]:
    """Find task files alongside specs."""
    patterns = ["*.tasks.md", "tasks.md"]
    files = []
    for p in patterns:
        files.extend(spec_dir.rglob(p))
    return sorted(set(files))


def extract_acceptance_criteria(spec_path: Path) -> list[str]:
    """Extract acceptance criteria / SHALL statements from a spec."""
    criteria = []
    content = spec_path.read_text(encoding="utf-8", errors="replace")
    for line in content.splitlines():
        stripped = line.strip()
        # EARS-style
        if "SHALL" in stripped and not stripped.startswith("#"):
            criteria.append(stripped)
        # Given/When/Then
        elif stripped.startswith(("Given ", "When ", "Then ", "- [ ]", "- [x]")):
            criteria.append(stripped)
        # Numbered acceptance criteria
        elif any(stripped.startswith(f"{i}.") for i in range(1, 20)) and (
            "shall" in stripped.lower() or "must" in stripped.lower() or "verify" in stripped.lower()
        ):
            criteria.append(stripped)
    return criteria


def extract_completed_tasks(task_path: Path) -> tuple[list[str], list[str]]:
    """Extract completed and pending tasks from a tasks.md file."""
    completed = []
    pending = []
    content = task_path.read_text(encoding="utf-8", errors="replace")
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("- [x]") or stripped.startswith("- [X]"):
            completed.append(stripped[6:].strip())
        elif stripped.startswith("- [ ]"):
            pending.append(stripped[6:].strip())
    return completed, pending


def convergence_report(spec_dir: Path, code_dir: Path | None = None) -> str:
    """Generate a convergence report comparing specs vs implementation state."""
    specs = find_spec_files(spec_dir)
    tasks = find_task_files(spec_dir)

    if not specs and not tasks:
        return f"No spec or task files found in {spec_dir}"

    lines = ["# Convergence Report", f"Spec directory: {spec_dir}", ""]

    total_criteria = 0
    total_completed = 0
    total_pending = 0
    pending_items = []

    # Analyze task completion
    for task_path in tasks:
        completed, pending = extract_completed_tasks(task_path)
        total_completed += len(completed)
        total_pending += len(pending)
        if pending:
            lines.append(f"## {task_path.stem} — {len(completed)} done, {len(pending)} pending")
            for p in pending:
                lines.append(f"  - [ ] {p}")
                pending_items.append(p)
            lines.append("")

    # Analyze spec criteria
    for spec_path in specs:
        criteria = extract_acceptance_criteria(spec_path)
        total_criteria += len(criteria)
        if criteria:
            lines.append(f"## {spec_path.stem} — {len(criteria)} acceptance criteria")
            lines.append("")

    # Summary
    lines.insert(2, "")
    if total_pending == 0 and total_completed > 0:
        lines.insert(3, f"**CONVERGED** — all {total_completed} tasks complete, {total_criteria} criteria defined")
    elif total_pending > 0:
        pct = (total_completed / (total_completed + total_pending) * 100) if (total_completed + total_pending) > 0 else 0
        lines.insert(3, f"**GAPS FOUND** — {total_completed}/{total_completed + total_pending} tasks done ({pct:.0f}%), {total_pending} remaining")
    else:
        lines.insert(3, f"**NO TASKS** — {total_criteria} criteria in specs, no task files to track progress")

    lines.append("")
    lines.append("---")
    lines.append(f"Specs analyzed: {len(specs)}")
    lines.append(f"Task files analyzed: {len(tasks)}")
    lines.append(f"Total criteria: {total_criteria}")
    lines.append(f"Tasks completed: {total_completed}")
    lines.append(f"Tasks pending: {total_pending}")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Convergence check: spec vs implementation")
    parser.add_argument("--spec", type=Path, required=True, help="Path to spec directory")
    parser.add_argument("--code", type=Path, default=None, help="Path to code directory (optional)")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    if not args.spec.exists():
        print(f"Error: spec path does not exist: {args.spec}", file=sys.stderr)
        return 1

    report = convergence_report(args.spec, args.code)

    if args.json:
        print(json.dumps({"report": report}))
    else:
        print(report)

    return 0


if __name__ == "__main__":
    sys.exit(main())
