"""PreToolUse hook: security scan — blocks credential exposure in file writes.

Purpose: catch hardcoded secrets, API keys, passwords, tokens, and private keys
before they're written to disk. Exit code 2 = BLOCK the write.

Preconditions: registered on PreToolUse with matcher ^(Write|Edit|MultiEdit)$
Failure modes: any error → exit 0 (fail-open, never block on scanner crash).
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
import sys as _ks
_ks.path.insert(0, str(Path(__file__).parent))
from _common import disabled

# Patterns that indicate credential exposure
SECRET_PATTERNS = [
    # API keys with common prefixes
    (r'(?i)(api[_-]?key|apikey)\s*[=:]\s*["\']?[a-z0-9_\-]{20,}', "API key"),
    (r'sk-[a-zA-Z0-9]{20,}', "OpenAI secret key"),
    (r'sk-ant-[a-zA-Z0-9\-]{20,}', "Anthropic secret key"),
    (r'ghp_[a-zA-Z0-9]{36,}', "GitHub personal access token"),
    (r'gho_[a-zA-Z0-9]{36,}', "GitHub OAuth token"),
    (r'github_pat_[a-zA-Z0-9_]{20,}', "GitHub fine-grained PAT"),
    (r'xoxb-[0-9]{10,}-[0-9]{10,}-[a-zA-Z0-9]{24,}', "Slack bot token"),
    (r'xoxp-[0-9]{10,}-[0-9]{10,}-[a-zA-Z0-9]{24,}', "Slack user token"),
    (r'AKIA[0-9A-Z]{16}', "AWS access key ID"),
    (r'(?i)(secret[_-]?key|secretkey)\s*[=:]\s*["\']?[a-z0-9/+=]{20,}', "Secret key"),
    (r'(?i)(password|passwd|pwd)\s*[=:]\s*["\']?[^\s"\']{8,}', "Hardcoded password"),
    (r'(?i)(token)\s*[=:]\s*["\']?[a-z0-9_\-\.]{20,}', "Token value"),
    # Private keys
    (r'-----BEGIN (RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----', "Private key"),
    (r'-----BEGIN PGP PRIVATE KEY BLOCK-----', "PGP private key"),
    # Connection strings with credentials
    (r'(?i)(mongodb|postgres|mysql|redis)://[^:]+:[^@]+@', "Connection string with password"),
    # Jina/HuggingFace
    (r'jina_[a-zA-Z0-9_\-]{20,}', "Jina API key"),
    (r'hf_[a-zA-Z0-9]{20,}', "HuggingFace token"),
]

# Files that should never be written
BLOCKED_FILES = [
    r'\.env$',
    r'\.env\.local$',
    r'\.env\.production$',
    r'credentials\.json$',
    r'service[_-]?account\.json$',
    r'id_rsa$',
    r'id_ed25519$',
    r'\.pem$',
]

# Allowlist: patterns that look like secrets but aren't (placeholders, examples)
ALLOWLIST = [
    r'sk-[\.x\*]{10,}',  # masked keys like sk-xxxx...
    r'your[_-]?(api[_-]?key|token|secret)',  # placeholder instructions
    r'<[A-Z_]+>',  # template placeholders like <API_KEY>
    r'\$\{?[A-Z_]+\}?',  # env var references like $API_KEY or ${API_KEY}
    r'env\.',  # env.VARIABLE references
    r'os\.environ',  # code reading env vars (not exposing them)
    r'process\.env',  # Node.js env var access
]


def is_allowlisted(line: str) -> bool:
    """Check if a line matches allowlist patterns (not a real secret)."""
    for pattern in ALLOWLIST:
        if re.search(pattern, line, re.IGNORECASE):
            return True
    return False


def scan_content(content: str, filepath: str) -> list[str]:
    """Scan content for secrets. Returns list of findings."""
    findings = []

    # Check if file path itself is blocked
    for pattern in BLOCKED_FILES:
        if re.search(pattern, filepath, re.IGNORECASE):
            findings.append(f"BLOCKED FILE: {filepath} — this file type should never be written by agents")
            return findings  # immediate block

    # Scan content line by line
    for i, line in enumerate(content.splitlines(), 1):
        if is_allowlisted(line):
            continue
        for pattern, label in SECRET_PATTERNS:
            if re.search(pattern, line):
                findings.append(f"  Line {i}: {label} — {line.strip()[:80]}")
                break  # one finding per line is enough

    return findings


def main():
    if disabled():
        return 0
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
    except Exception:
        return 0  # fail-open on bad input

    # Extract the content being written
    tool_input = payload.get("tool_input", {})
    content = tool_input.get("content", "") or tool_input.get("new_string", "") or tool_input.get("newStr", "")
    filepath = tool_input.get("file_path", "") or tool_input.get("path", "") or tool_input.get("targetFile", "")

    if not content and not filepath:
        return 0  # no content to scan

    findings = scan_content(content, filepath)

    if findings:
        # EXIT CODE 2 = BLOCK
        msg = f"BLOCKED — credential exposure detected in {filepath}:\n" + "\n".join(findings[:5])
        if len(findings) > 5:
            msg += f"\n  ... and {len(findings) - 5} more"
        msg += "\n\nUse environment variables or a secrets manager instead of hardcoding."
        print(msg, file=sys.stderr)
        return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())
