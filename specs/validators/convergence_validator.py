"""Convergence validator: compare implementation evidence against spec criteria.

Replaces the checkbox-counting approach in hooks/convergence.py with actual
inspection of whether each MUST requirement has implementation evidence.

Trigger: PostTaskExec or Stop (after implementation work).
Fail mode: block if any MUST requirement has zero implementation evidence;
warn if SHOULD requirements are unmet.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ..policy_contracts import (
    EvidenceRef,
    LifecycleEvent,
    PolicyRecord,
    PolicyPriority,
    StructuredVerdict,
    VerdictStatus,
)


def check_task_coverage(db_path: str | Path, rule_id: str) -> dict:
    """Check if a requirement has at least one done task linked to it.

    Returns {has_coverage: bool, done_tasks: int, total_tasks: int, task_titles: [...]}
    """
    try:
        conn = sqlite3.connect(str(db_path), timeout=5)
        conn.row_factory = sqlite3.Row
        # Tasks whose details mention the requirement ID
        rows = conn.execute(
            "SELECT id, title, status, details FROM tasks WHERE details LIKE ?",
            (f"%{rule_id}%",),
        ).fetchall()
        conn.close()
    except Exception:
        return {"has_coverage": False, "done_tasks": 0, "total_tasks": 0, "task_titles": []}

    done = [r for r in rows if r["status"] == "done"]
    return {
        "has_coverage": len(done) > 0,
        "done_tasks": len(done),
        "total_tasks": len(rows),
        "task_titles": [r["title"] for r in rows],
    }


def check_test_coverage(specs_dir: Path, rule_id: str) -> dict:
    """Check if test files reference this rule_id in assertions or comments.

    Returns {has_tests: bool, test_files: [...], mention_count: int}
    """
    test_files = list(specs_dir.rglob("test_*.py"))
    mentions = []
    for tf in test_files:
        try:
            content = tf.read_text(encoding="utf-8", errors="replace")
            if rule_id in content:
                mentions.append(str(tf.relative_to(specs_dir)))
        except OSError:
            continue
    return {
        "has_tests": len(mentions) > 0,
        "test_files": mentions,
        "mention_count": len(mentions),
    }


def check_file_evidence(specs_dir: Path, rule_id: str) -> dict:
    """Check if any implementation file (.py, not test) references this rule.

    Returns {has_impl: bool, impl_files: [...]}
    """
    py_files = [
        p for p in specs_dir.rglob("*.py")
        if "test_" not in p.name and "__pycache__" not in str(p)
    ]
    mentions = []
    for pf in py_files:
        try:
            content = pf.read_text(encoding="utf-8", errors="replace")
            if rule_id in content:
                mentions.append(str(pf.relative_to(specs_dir)))
        except OSError:
            continue
    return {"has_impl": len(mentions) > 0, "impl_files": mentions}


class ConvergenceValidator:
    """Assess whether implementation evidence exists for each policy rule.

    Require: event payload has 'specs_db_path' and 'specs_dir' or they default
             to the standard harness locations.
    Guarantee: returns one verdict per rule with evidence of coverage or gap.
    Maintain: read-only — never modifies specs, tasks, or source files.

    Unlike the old convergence.py, this validator does NOT count checkboxes.
    It checks whether implementation artifacts (done tasks, test files,
    source references) exist for each requirement.
    """

    VALIDATOR_ID = "convergence"

    def evaluate(
        self, event: LifecycleEvent, rules: list[PolicyRecord], snapshot_hash: str,
    ) -> list[StructuredVerdict]:
        payload = event.payload
        specs_root = Path(__file__).resolve().parent.parent
        specs_db = Path(payload.get("specs_db_path") or specs_root / "specs.db")
        specs_dir = Path(payload.get("specs_dir") or specs_root)

        verdicts = []
        for r in rules:
            task_cov = check_task_coverage(specs_db, r.rule_id)
            test_cov = check_test_coverage(specs_dir, r.rule_id)
            file_cov = check_file_evidence(specs_dir, r.rule_id)

            has_any_evidence = task_cov["has_coverage"] or test_cov["has_tests"] or file_cov["has_impl"]

            evidence_refs = []
            if task_cov["has_coverage"]:
                evidence_refs.append(EvidenceRef(
                    ref_type="task", ref_id=r.rule_id,
                    description=f"{task_cov['done_tasks']} done task(s): {', '.join(task_cov['task_titles'][:3])}",
                ))
            if test_cov["has_tests"]:
                evidence_refs.append(EvidenceRef(
                    ref_type="test", ref_id=r.rule_id,
                    description=f"Referenced in {test_cov['mention_count']} test file(s)",
                ))
            if file_cov["has_impl"]:
                evidence_refs.append(EvidenceRef(
                    ref_type="file", ref_id=r.rule_id,
                    description=f"Referenced in: {', '.join(file_cov['impl_files'][:3])}",
                ))

            if has_any_evidence:
                verdicts.append(StructuredVerdict(
                    rule_id=r.rule_id, validator_id=self.VALIDATOR_ID,
                    status=VerdictStatus.allow,
                    evidence=evidence_refs,
                    message=f"Covered: {task_cov['done_tasks']} task(s), {test_cov['mention_count']} test ref(s)",
                ))
            else:
                # MUST rules block; SHOULD rules warn
                status = VerdictStatus.block if r.priority == PolicyPriority.must else VerdictStatus.warn
                verdicts.append(StructuredVerdict(
                    rule_id=r.rule_id, validator_id=self.VALIDATOR_ID,
                    status=status,
                    message=f"No implementation evidence for '{r.title}' — 0 done tasks, 0 test refs, 0 source refs",
                    remediation_task_ref=f"Implement or link evidence for {r.rule_id}",
                ))

        return verdicts
