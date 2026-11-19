"""| Stage | Mechanism | Tag | Requirements |
|---|---|---|---|
| FIXTURE | Create temporary project, transcript and memory-index database | [mandatory] | R1-R2 |
| CAPTURE | Index transcript through the PreCompact integration | [mandatory] | R1 |
| VERIFY | Search and open under matching and foreign scopes | [contract] | R2 |

R1: WHEN a transcript and session context exist, its content shall persist as searchable session evidence.
R2: IF project or session differs, THEN the captured source shall not be retrievable.
CLOSED: Live operator memory is rejected as a test fixture because fixture isolation requires disposable SQLite.
Preconditions: memory-index source and test dependencies are installed.
Failure modes: capture, scope leakage, or source-open errors fail the test.
"""
import importlib.util
import sys
from pathlib import Path

import pytest


HOOK_PATH = Path(__file__).resolve().parents[1] / "hooks" / "pre_compact.py"
MEMORY_INDEX = Path.home() / ".mcp" / "memory-index"
sys.path.insert(0, str(MEMORY_INDEX))
import conversation_store as convstore  # noqa: E402

spec = importlib.util.spec_from_file_location("pre_compact_under_test", HOOK_PATH)
pre_compact = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pre_compact)


@pytest.fixture
def capture_env(tmp_path, monkeypatch):
    """Create isolated paths for one source-capture check.

    Require: pytest supplies a writable temporary directory.
    Guarantee: transcript and SQLite paths are isolated from operator data.
    Maintain: hook module uses the fixture database for the test duration.
    Assert: workspace exists before capture.
    """
    workspace = tmp_path / "alpha"
    workspace.mkdir()
    transcript = tmp_path / "session.jsonl"
    transcript.write_text('{"message":"EARLY_MARKER_DELTA"}\n', encoding="utf-8")
    db_path = tmp_path / "memory" / "conversations.sqlite3"
    monkeypatch.setattr(pre_compact, "MEMORY_DB", db_path)
    return workspace, transcript, db_path


def test_capture_is_searchable_and_openable_in_matching_scope(capture_env):
    """Verify exact source recovery for the matching project and session.

    Require: capture_env contains a readable transcript and temporary project.
    Guarantee: matching scoped search/open returns the early marker and source ref.
    Maintain: all reads use the disposable SQLite database.
    Assert: one authorized record is found.
    """
    workspace, transcript, db_path = capture_env
    assert pre_compact.index_transcript({
        "transcript_path": str(transcript), "cwd": str(workspace), "session_id": "session-a"
    }) == 1
    conn = convstore.connect(db_path)
    try:
        hits = convstore.search_records(conn, "EARLY_MARKER_DELTA", workspace_root=str(workspace),
                                        session_id="session-a", scope="session")
        assert len(hits) == 1
        opened = convstore.open_record(conn, hits[0]["memory_id"], workspace_root=str(workspace),
                                       session_id="session-a", scope="session")
        assert "EARLY_MARKER_DELTA" in opened["body"]
        assert opened["source_ref"].startswith(str(transcript))
    finally:
        conn.close()


def test_capture_rejects_wrong_session_and_equal_basename_project(capture_env, tmp_path):
    """Verify session and canonical workspace checks isolate matching basenames.

    Require: fixture project and foreign project have the same basename.
    Guarantee: wrong-session and foreign-project reads return no hits.
    Maintain: capture itself remains available to its owning scope.
    Assert: unauthorized result sets are empty.
    """
    workspace, transcript, db_path = capture_env
    foreign = tmp_path / "foreign" / "alpha"
    foreign.mkdir(parents=True)
    pre_compact.index_transcript({
        "transcript_path": str(transcript), "cwd": str(workspace), "session_id": "session-a"
    })
    conn = convstore.connect(db_path)
    try:
        for root, session in ((workspace, "session-b"), (foreign, "session-a")):
            assert convstore.search_records(conn, "EARLY_MARKER_DELTA", workspace_root=str(root),
                                            session_id=session, scope="session") == []
    finally:
        conn.close()


def test_capture_skips_missing_transcript(capture_env):
    """Verify missing source paths do not create records.

    Require: temporary workspace exists and the transcript path does not.
    Guarantee: capture returns zero without creating a source record.
    Maintain: the hook can still preserve its payload backup.
    Assert: no source path is opened.
    """
    workspace, _transcript, _db_path = capture_env
    assert pre_compact.index_transcript({
        "transcript_path": str(workspace / "missing.jsonl"), "cwd": str(workspace), "session_id": "session-a"
    }) == 0


def test_capture_splits_large_transcript_without_losing_bytes(capture_env):
    """Verify large transcript lines split at the record bound and reassemble exactly.

    Require: transcript exceeds two memory-index record bounds.
    Guarantee: raw stored chunks reassemble byte-for-byte and remain bounded.
    Maintain: source order is retained across chunks.
    Assert: each persisted chunk fits the declared maximum.
    """
    workspace, transcript, db_path = capture_env
    content = "marker " + ("chunkword " * 12000) + " END_MARKER\n"
    transcript.write_text(content, encoding="utf-8")
    assert pre_compact.index_transcript({
        "transcript_path": str(transcript), "cwd": str(workspace), "session_id": "session-large"
    }) == 3
    conn = convstore.connect(db_path)
    try:
        stored = "".join(row[0] for row in conn.execute(
            "SELECT content FROM volleys WHERE session_id=? ORDER BY seq", ("session-large",)
        ))
        assert stored == content
        assert max(len(row[0]) for row in conn.execute(
            "SELECT content FROM volleys WHERE session_id=?", ("session-large",)
        )) <= pre_compact.MAX_RECORD_CHARS
    finally:
        conn.close()
