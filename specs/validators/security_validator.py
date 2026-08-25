"""Security validator: detect credential exposure in file writes.

Ported from hooks/security_scan.py into the StructuredVerdict contract.
Trigger: PreToolUse (file write operations).
Fail mode: block on detected secrets; allow on clean scan or no content.
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

SECRET_PATTERNS = [
    (r'(?i)(api[_-]?key|apikey)\s*[=:]\s*["\']?[a-z0-9_\-]{20,}', "API key"),
    (r'sk-[a-zA-Z0-9]{20,}', "OpenAI secret key"),
    (r'sk-ant-[a-zA-Z0-9\-]{20,}', "Anthropic secret key"),
    (r'ghp_[a-zA-Z0-9]{36,}', "GitHub PAT"),
    (r'AKIA[0-9A-Z]{16}', "AWS access key ID"),
    (r'(?i)(secret[_-]?key|secretkey)\s*[=:]\s*["\']?[a-z0-9/+=]{20,}', "Secret key"),
    (r'(?i)(password|passwd|pwd)\s*[=:]\s*["\']?[^\s"\']{8,}', "Hardcoded password"),
    (r'-----BEGIN (RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----', "Private key"),
    (r'(?i)(mongodb|postgres|mysql|redis)://[^:]+:[^@]+@', "Connection string with password"),
    (r'hf_[a-zA-Z0-9]{20,}', "HuggingFace token"),
]

BLOCKED_FILES = [
    r'\.env$', r'\.env\.local$', r'credentials\.json$',
    r'service[_-]?account\.json$', r'id_rsa$', r'id_ed25519$', r'\.pem$',
]

ALLOWLIST = [
    r'sk-[\.x\*]{10,}', r'your[_-]?(api[_-]?key|token|secret)',
    r'<[A-Z_]+>', r'\$\{?[A-Z_]+\}?', r'env\.', r'os\.environ', r'process\.env',
]


def _is_allowlisted(line: str) -> bool:
    return any(re.search(p, line, re.IGNORECASE) for p in ALLOWLIST)


def scan_content(content: str, filepath: str) -> list[str]:
    """Scan for secrets. Returns finding descriptions."""
    findings = []
    for pattern in BLOCKED_FILES:
        if re.search(pattern, filepath, re.IGNORECASE):
            findings.append(f"BLOCKED FILE: {filepath}")
            return findings
    for i, line in enumerate(content.splitlines(), 1):
        if _is_allowlisted(line):
            continue
        for pattern, label in SECRET_PATTERNS:
            if re.search(pattern, line):
                findings.append(f"Line {i}: {label}")
                break
    return findings


class SecurityValidator:
    """Detect credential exposure in file writes.

    Require: event payload has content and file path from a write operation.
    Guarantee: returns one verdict per rule — block if secrets found, allow otherwise.
    """

    VALIDATOR_ID = "security-scan"

    def evaluate(
        self, event: LifecycleEvent, rules: list[PolicyRecord], snapshot_hash: str,
    ) -> list[StructuredVerdict]:
        payload = event.payload
        content = payload.get("content") or payload.get("new_string") or payload.get("newStr") or payload.get("text") or ""
        filepath = payload.get("file_path") or payload.get("path") or payload.get("targetFile") or ""

        if not content and not filepath:
            return [StructuredVerdict(
                rule_id=r.rule_id, validator_id=self.VALIDATOR_ID,
                status=VerdictStatus.allow, message="No content to scan",
            ) for r in rules]

        findings = scan_content(content, filepath)
        verdicts = []
        for r in rules:
            if findings:
                verdicts.append(StructuredVerdict(
                    rule_id=r.rule_id, validator_id=self.VALIDATOR_ID,
                    status=VerdictStatus.block,
                    subject_ids=[filepath] if filepath else [],
                    evidence=[EvidenceRef(ref_type="scan", ref_id=f, description=f) for f in findings[:5]],
                    message=f"Credential exposure: {len(findings)} finding(s)",
                ))
            else:
                verdicts.append(StructuredVerdict(
                    rule_id=r.rule_id, validator_id=self.VALIDATOR_ID,
                    status=VerdictStatus.allow, message="Clean",
                ))
        return verdicts
