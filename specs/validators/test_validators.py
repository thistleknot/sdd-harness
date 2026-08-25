"""Validator behavioral tests — one per validator, testing the contract not internals."""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from specs.policy_contracts import (
    LifecycleEvent,
    LifecycleEventType,
    PolicyRecord,
    PolicyPriority,
    VerdictStatus,
)
from specs.validators.security_validator import SecurityValidator
from specs.validators.self_review_validator import SelfReviewValidator
from specs.validators.convergence_validator import ConvergenceValidator
from specs.validators.sprawl_validator import SprawlValidator


@pytest.fixture
def rules():
    return [PolicyRecord(
        rule_id="req:8", title="Security", criteria="No secrets in code",
        priority=PolicyPriority.must, source_type="requirement", source_id=8,
        content_hash="x",
    )]


@pytest.fixture
def event():
    return LifecycleEvent(
        event_id="evt-1", event_type=LifecycleEventType.stop,
        harness_id="kiro", project_slug="harness", session_id="sess-1",
        payload={},
    )


# --- SecurityValidator -------------------------------------------------------


def test_security_blocks_secrets(rules, event):
    """Detects AWS keys, OpenAI keys, private keys; blocks on any."""
    event.payload = {"text": "aws_key = AKIAIOSFODNN7EXAMPLE", "path": "config.py"}
    event.event_type = LifecycleEventType.pre_tool_use
    v = SecurityValidator()
    verdicts = v.evaluate(event, rules, "snap1")
    assert verdicts[0].status == VerdictStatus.block


def test_security_allows_clean(rules, event):
    """Clean code with no secrets passes."""
    event.payload = {"text": "x = 42", "path": "math.py"}
    event.event_type = LifecycleEventType.pre_tool_use
    v = SecurityValidator()
    verdicts = v.evaluate(event, rules, "snap1")
    assert verdicts[0].status == VerdictStatus.allow


# --- SelfReviewValidator -----------------------------------------------------


def test_self_review_warns_stubs(rules, event):
    """NotImplementedError and TODO in code body triggers warn."""
    event.payload = {"changed_files": [{"path": "a.py", "content": "def f():\n    raise NotImplementedError\n"}]}
    v = SelfReviewValidator()
    verdicts = v.evaluate(event, rules, "snap1")
    assert verdicts[0].status == VerdictStatus.warn


def test_self_review_allows_complete(rules, event):
    """Clean implementation passes."""
    event.payload = {"changed_files": [{"path": "a.py", "content": "def f():\n    return 42\n"}]}
    v = SelfReviewValidator()
    verdicts = v.evaluate(event, rules, "snap1")
    assert verdicts[0].status == VerdictStatus.allow


# --- ConvergenceValidator ----------------------------------------------------


def test_convergence_blocks_uncovered_must(tmp_path, rules, event):
    """MUST rule with no task/test/file evidence → block."""
    db_path = tmp_path / "specs.db"
    conn = sqlite3.connect(str(db_path))
    conn.executescript("CREATE TABLE tasks (id INTEGER PRIMARY KEY, title TEXT, status TEXT, details TEXT, parent_id INTEGER, blocker TEXT, created_at TEXT, updated_at TEXT);")
    conn.commit()
    conn.close()
    event.payload = {"specs_db_path": str(db_path), "specs_dir": str(tmp_path)}
    v = ConvergenceValidator()
    verdicts = v.evaluate(event, rules, "snap1")
    assert verdicts[0].status == VerdictStatus.block


def test_convergence_allows_covered(tmp_path, rules, event):
    """Rule with done task + test reference → allow."""
    db_path = tmp_path / "specs.db"
    conn = sqlite3.connect(str(db_path))
    conn.executescript("CREATE TABLE tasks (id INTEGER PRIMARY KEY, title TEXT, status TEXT, details TEXT, parent_id INTEGER, blocker TEXT, created_at TEXT, updated_at TEXT);")
    conn.execute("INSERT INTO tasks (title, status, details) VALUES (?, ?, ?)", ("Done", "done", "req:8"))
    conn.commit()
    conn.close()
    (tmp_path / "test_x.py").write_text("# req:8\ndef test_it(): pass\n")
    event.payload = {"specs_db_path": str(db_path), "specs_dir": str(tmp_path)}
    v = ConvergenceValidator()
    verdicts = v.evaluate(event, rules, "snap1")
    assert verdicts[0].status == VerdictStatus.allow


# --- SprawlValidator ---------------------------------------------------------


def test_sprawl_warns_on_orphan(tmp_path, rules, event):
    """Unreferenced public symbol → warn."""
    (tmp_path / "orphan.py").write_text("def unreachable(): pass\n")
    event.payload = {"scan_dir": str(tmp_path)}
    v = SprawlValidator()
    verdicts = v.evaluate(event, rules, "snap1")
    assert verdicts[0].status == VerdictStatus.warn


def test_sprawl_allows_referenced(tmp_path, rules, event):
    """All public symbols referenced → allow."""
    (tmp_path / "mod.py").write_text("def helper(): pass\n")
    (tmp_path / "main.py").write_text("from mod import helper\nhelper()\ndef main(): pass\n")
    event.payload = {"scan_dir": str(tmp_path)}
    v = SprawlValidator()
    verdicts = v.evaluate(event, rules, "snap1")
    assert verdicts[0].status == VerdictStatus.allow
