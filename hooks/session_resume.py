"""| Stage | Mechanism | Contract |
| IDENTIFY | Resolve full project identity from caller workspace | [mandatory] R1 |
| RESUME | Select the newest readable local or exact-identity handoff | [mandatory] R9 |
Spec: docs/playbooks/memory-and-harness-integration.md.
CLOSED: latest-global and basename-only handoff fallback.
Preconditions: caller workspace is available; missing archives are a no-op.
Failures: optional hook capture/parsing/IO fails open without cross-project fallback.
"""
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import sys as _ks
_ks.path.insert(0, str(Path(__file__).parent))
from _common import disabled

sys.path.insert(0, str(Path.home() / '.skills' / 'memory-index'))
from conversation_store import project_identity

MEMORY_DIR = Path(os.path.expanduser("~/memory-bank"))


def find_prompt_md(workspace_root: str | None = None) -> Path | None:
    """Select the newest readable, identity-matched prompt for this workspace.

    Require: caller workspace (or interactive CWD) resolves to project identity.
    Guarantee: newest eligible local or exact-identity archive wins; ties sort by
        normalized absolute path.
    Maintain: global recency and repository basenames never authorize archives.
    Assert: unreadable, foreign, and closed archive candidates are not selected.
    """
    workspace = Path(workspace_root or Path.cwd()).resolve()
    identity = project_identity(str(workspace))
    local_candidates = {workspace / 'prompt.md'}
    repo = subprocess.run(
        ['git', '-C', str(workspace), 'rev-parse', '--show-toplevel'],
        capture_output=True,
        text=True,
        timeout=5,
    )
    if repo.returncode == 0:
        local_candidates.add(Path(repo.stdout.strip()) / 'prompt.md')

    candidates: dict[str, tuple[int, Path]] = {}
    for candidate in local_candidates:
        if not candidate.is_file():
            continue
        try:
            candidate.read_text(encoding='utf-8')
            resolved = candidate.resolve()
            candidates[os.path.normcase(str(resolved))] = (
                resolved.stat().st_mtime_ns,
                resolved,
            )
        except (OSError, UnicodeError):
            continue

    key = hashlib.sha256(identity.encode()).hexdigest()[:24]
    directory = MEMORY_DIR / 'handoffs' / 'projects' / key
    for candidate in directory.glob('prompt-*.md'):
        try:
            content = candidate.read_text(encoding='utf-8')
            if content.splitlines()[0] != f'Project-URI: {identity}':
                continue
            resolved = candidate.resolve()
            candidates[os.path.normcase(str(resolved))] = (
                resolved.stat().st_mtime_ns,
                resolved,
            )
        except (OSError, UnicodeError, IndexError):
            continue
    if not candidates:
        return None
    return min(
        candidates.values(),
        key=lambda item: (-item[0], os.path.normcase(str(item[1]))),
    )[1]


def main():
    """Resume only context selected for the caller's project.

    Require: valid hook payload and resolvable workspace identity.
    Guarantee: selected context is emitted or the optional hook fails open.
    Maintain: no global or cross-project archive fallback.
    Assert: malformed input or inaccessible context never blocks session start.
    """
    if disabled():
        return 0
    try:
        raw = sys.stdin.read() if not sys.stdin.isatty() else ''
        payload = json.loads(raw) if raw.strip() else {}
        prompt_path = find_prompt_md(payload.get('workspace') or payload.get('cwd'))
        if prompt_path:
            print(prompt_path.read_text(encoding='utf-8')[:6000])
    except (ValueError, OSError, subprocess.SubprocessError):
        return 0  # Optional continuity must never block a session start.
    return 0


if __name__ == "__main__":
    sys.exit(main())
