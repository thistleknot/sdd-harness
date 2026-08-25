"""Self-review validator: detect incomplete implementations in recent changes.

Ported from hooks/self_review.py into the StructuredVerdict contract.
Trigger: Stop (before declaring done).
Fail mode: warn on incomplete patterns found; allow on clean scan.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ..policy_contracts import (
    EvidenceRef,
    LifecycleEvent,
    PolicyRecord,
    StructuredVerdict,
    VerdictStatus,
)

INCOMPLETE_PATTERNS = [
    re.compile(r"\bTODO\b"),
    re.compile(r"\bFIXME\b"),
    re.compile(r"\bHACK\b"),
    re.compile(r"\bXXX\b"),
    re.compile(r"\bplaceholder\b", re.IGNORECASE),
    re.compile(r"\bnot implemented\b", re.IGNORECASE),
    re.compile(r"\bmock implementation\b", re.IGNORECASE),
    re.compile(r"^\s*pass\s+#"),
    re.compile(r"\braise NotImplementedError\b"),
    re.compile(r"^\s*\.\.\.\s*$"),
]


def scan_lines(content: str, filepath: str) -> list[str]:
    """Scan content for incomplete-work patterns. Returns finding strings."""
    findings = []
    in_docstring = False
    for i, line in enumerate(content.splitlines(), 1):
        stripped = line.strip()
        if '"""' in stripped or "'''" in stripped:
            count = stripped.count('"""') + stripped.count("'''")
            if count % 2 == 1:
                in_docstring = not in_docstring
            continue
        if in_docstring:
            continue
        if stripped.startswith("#"):
            continue
        for pattern in INCOMPLETE_PATTERNS:
            if pattern.search(line):
                findings.append(f"{filepath}:{i} {stripped[:80]}")
                break
    return findings


class SelfReviewValidator:
    """Detect incomplete stubs in changed files before declaring done.

    Require: event payload has 'changed_files' list with content or paths.
    Guarantee: returns one verdict per rule — warn if stubs found, allow otherwise.
    """

    VALIDATOR_ID = "self-review"

    def evaluate(
        self, event: LifecycleEvent, rules: list[PolicyRecord], snapshot_hash: str,
    ) -> list[StructuredVerdict]:
        payload = event.payload
        changed_files: list[dict] = payload.get("changed_files", [])

        # If no file list provided, try single-file payload
        if not changed_files:
            content = payload.get("content") or payload.get("text") or ""
            filepath = payload.get("file_path") or payload.get("path") or ""
            if content and filepath:
                changed_files = [{"path": filepath, "content": content}]

        all_findings: list[str] = []
        for f in changed_files:
            path = f.get("path", "")
            content = f.get("content", "")
            if not content and path:
                try:
                    content = Path(path).read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
            if content:
                all_findings.extend(scan_lines(content, path))

        verdicts = []
        for r in rules:
            if all_findings:
                verdicts.append(StructuredVerdict(
                    rule_id=r.rule_id, validator_id=self.VALIDATOR_ID,
                    status=VerdictStatus.warn,
                    subject_ids=[f.get("path", "") for f in changed_files[:10]],
                    evidence=[EvidenceRef(ref_type="scan", ref_id=f, description=f) for f in all_findings[:10]],
                    message=f"Incomplete work: {len(all_findings)} pattern(s) found",
                ))
            else:
                verdicts.append(StructuredVerdict(
                    rule_id=r.rule_id, validator_id=self.VALIDATOR_ID,
                    status=VerdictStatus.allow, message="No incomplete patterns",
                ))
        return verdicts
