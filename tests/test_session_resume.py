"""| Stage | Mechanism | Contract |
| FIXTURE | Isolate workspace identity and archive directory | [mandatory] REQ-68,TASK-91 |
| SELECT | Check newest matching local/archive handoff selection | [mandatory] REQ-68 |
| REJECT | Exclude foreign, closed, unreadable, or empty candidates | [mandatory] REQ-68 |

Spec: docs/playbooks/memory-and-harness-integration.md R9.
CLOSED: latest-global and basename-only archive selection.
Preconditions: temporary filesystem and pytest tmp_path are available.
Failure modes: selection mismatch fails the test at the observed path.
"""
from __future__ import annotations

import hashlib
import os
import time
from pathlib import Path

from hooks import session_resume


PROJECT_IDENTITY = "file:///tmp/resume-fixture"


def _make_archive(memory_root: Path, name: str, content: str) -> Path:
    """Create a generated handoff under the identity-keyed archive directory.

    Require: caller supplies an isolated memory root and a unique filename.
    Guarantee: returned path contains the supplied content.
    Maintain: archive location derives from the same identity hash as the reader.
    Assert: resulting path is a regular file.
    """
    project_key = hashlib.sha256(PROJECT_IDENTITY.encode()).hexdigest()[:24]
    archive_dir = memory_root / "handoffs" / "projects" / project_key
    archive_dir.mkdir(parents=True, exist_ok=True)
    archive = archive_dir / name
    archive.write_text(content, encoding="utf-8")
    return archive


def _set_mtime(path: Path, timestamp_ns: int) -> None:
    """Set both file timestamps for a deterministic resume-order fixture.

    Require: path exists and timestamp_ns is a valid filesystem timestamp.
    Guarantee: path modification time equals timestamp_ns.
    Maintain: fixtures compare filesystem metadata without wall-clock sleeps.
    Assert: stat reports the requested nanosecond modification time.
    """
    os.utime(path, ns=(timestamp_ns, timestamp_ns))
    assert path.stat().st_mtime_ns == timestamp_ns


def test_newer_matching_archive_wins_over_older_local_prompt(tmp_path, monkeypatch):
    """Verify newer project archives outrank older local prompts.

    Require: workspace prompt and matching archive have different timestamps.
    Guarantee: the newer exact-identity archive is selected.
    Maintain: fixture files stay within the isolated temporary directory.
    Assert: selected path equals the matching archive.
    """
    workspace = tmp_path / "repo"
    workspace.mkdir()
    local_prompt = workspace / "prompt.md"
    local_prompt.write_text("old local prompt", encoding="utf-8")
    memory_root = tmp_path / "memory"
    archive = _make_archive(
        memory_root,
        "prompt-newer.md",
        f"Project-URI: {PROJECT_IDENTITY}\nnew handoff",
    )
    now = time.time_ns()
    _set_mtime(local_prompt, now - 2_000_000_000)
    _set_mtime(archive, now - 1_000_000_000)
    monkeypatch.setattr(session_resume, "MEMORY_DIR", memory_root)
    monkeypatch.setattr(session_resume, "project_identity", lambda _: PROJECT_IDENTITY)

    assert session_resume.find_prompt_md(str(workspace)) == archive


def test_newer_local_prompt_wins_over_older_matching_archive(tmp_path, monkeypatch):
    """Verify a later operator prompt outranks an older generated handoff.

    Require: workspace prompt and matching archive have different timestamps.
    Guarantee: the newer local prompt is selected.
    Maintain: fixture files stay within the isolated temporary directory.
    Assert: selected path equals the local prompt.
    """
    workspace = tmp_path / "repo"
    workspace.mkdir()
    local_prompt = workspace / "prompt.md"
    local_prompt.write_text("new local prompt", encoding="utf-8")
    memory_root = tmp_path / "memory"
    archive = _make_archive(
        memory_root,
        "prompt-older.md",
        f"Project-URI: {PROJECT_IDENTITY}\nold handoff",
    )
    now = time.time_ns()
    _set_mtime(archive, now - 2_000_000_000)
    _set_mtime(local_prompt, now - 1_000_000_000)
    monkeypatch.setattr(session_resume, "MEMORY_DIR", memory_root)
    monkeypatch.setattr(session_resume, "project_identity", lambda _: PROJECT_IDENTITY)

    assert session_resume.find_prompt_md(str(workspace)) == local_prompt


def test_equal_mtime_uses_normalized_path_order(tmp_path, monkeypatch):
    """Verify equal timestamps use a stable normalized path tie-break.

    Require: local prompt and matching archive share a timestamp.
    Guarantee: the lexicographically first normalized path is selected.
    Maintain: fixture paths and identity remain fixed during selection.
    Assert: selected path equals the archive path that sorts first.
    """
    workspace = tmp_path / "z-repo"
    workspace.mkdir()
    local_prompt = workspace / "prompt.md"
    local_prompt.write_text("local prompt", encoding="utf-8")
    memory_root = tmp_path / "a-memory"
    archive = _make_archive(
        memory_root,
        "prompt-tied.md",
        f"Project-URI: {PROJECT_IDENTITY}\ntied handoff",
    )
    tied_time = time.time_ns() - 1_000_000_000
    _set_mtime(local_prompt, tied_time)
    _set_mtime(archive, tied_time)
    monkeypatch.setattr(session_resume, "MEMORY_DIR", memory_root)
    monkeypatch.setattr(session_resume, "project_identity", lambda _: PROJECT_IDENTITY)

    assert session_resume.find_prompt_md(str(workspace)) == archive


def test_foreign_closed_unreadable_and_empty_archives_are_ignored(tmp_path, monkeypatch):
    """Verify invalid project archives cannot become resume context.

    Require: archive directory contains foreign, closed, unreadable, and empty files.
    Guarantee: no invalid archive is returned as a candidate.
    Maintain: the test simulates unreadability without changing machine permissions.
    Assert: selection returns None when no valid local prompt exists.
    """
    workspace = tmp_path / "repo"
    workspace.mkdir()
    memory_root = tmp_path / "memory"
    foreign = _make_archive(
        memory_root,
        "prompt-foreign.md",
        "Project-URI: file:///tmp/other-project\nforeign",
    )
    _make_archive(
        memory_root,
        "closed-20260101.md",
        f"Project-URI: {PROJECT_IDENTITY}\nclosed",
    )
    unreadable = _make_archive(
        memory_root,
        "prompt-unreadable.md",
        f"Project-URI: {PROJECT_IDENTITY}\nunreadable",
    )
    _make_archive(memory_root, "prompt-empty.md", "")
    original_read_text = Path.read_text

    def read_text(candidate, *args, **kwargs):
        """Simulate one unreadable matching archive while preserving other reads."""
        if candidate == unreadable:
            raise OSError("fixture unreadable archive")
        return original_read_text(candidate, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", read_text)
    monkeypatch.setattr(session_resume, "MEMORY_DIR", memory_root)
    monkeypatch.setattr(session_resume, "project_identity", lambda _: PROJECT_IDENTITY)

    assert foreign.is_file()
    assert session_resume.find_prompt_md(str(workspace)) is None
