"""Tests for specs_db.py — CRUD operations and markdown rendering."""
import sqlite3
import tempfile
from pathlib import Path

import pytest

from specs_db import SpecsDB, _slugify


@pytest.fixture
def db(tmp_path):
    """Provide a fresh in-memory-like DB for each test."""
    db_path = tmp_path / "test_specs.db"
    s = SpecsDB(db_path)
    yield s
    s.close()


# ── slugify ─────────────────────────────────────────────────────────────────

def test_slugify_basic():
    assert _slugify("Hello World") == "hello-world"


def test_slugify_slashes():
    assert _slugify("path/to/thing") == "path-to-thing"


def test_slugify_truncates_at_80():
    long = "a" * 100
    assert len(_slugify(long)) == 80


# ── requirements CRUD ───────────────────────────────────────────────────────

def test_add_requirement(db):
    rid = db.add_requirement("Auth required", "All endpoints return 401 without token", "must")
    assert rid == 1
    row = db.conn.execute("SELECT * FROM requirements WHERE id=?", (rid,)).fetchone()
    assert row["title"] == "Auth required"
    assert row["priority"] == "must"
    assert row["status"] == "active"


def test_update_requirement(db):
    rid = db.add_requirement("Feature X", "Criteria Y", "should")
    db.update_requirement(rid, status="met")
    row = db.conn.execute("SELECT status FROM requirements WHERE id=?", (rid,)).fetchone()
    assert row["status"] == "met"


def test_update_requirement_ignores_invalid_fields(db):
    rid = db.add_requirement("Feature X", "Criteria Y", "should")
    db.update_requirement(rid, hacker="drop table")  # should be no-op
    row = db.conn.execute("SELECT * FROM requirements WHERE id=?", (rid,)).fetchone()
    assert row["title"] == "Feature X"


# ── tasks CRUD ──────────────────────────────────────────────────────────────

def test_add_task(db):
    tid = db.add_task("Build widget", "planned", details="Use React")
    assert tid == 1
    row = db.conn.execute("SELECT * FROM tasks WHERE id=?", (tid,)).fetchone()
    assert row["status"] == "planned"
    assert row["details"] == "Use React"


def test_update_task_status(db):
    tid = db.add_task("Build widget", "planned")
    db.update_task(tid, status="doing")
    row = db.conn.execute("SELECT status FROM tasks WHERE id=?", (tid,)).fetchone()
    assert row["status"] == "doing"


def test_list_tasks_filtered(db):
    db.add_task("A", "planned")
    db.add_task("B", "doing")
    db.add_task("C", "planned")
    results = db.list_tasks("planned")
    assert len(results) == 2
    assert all(r["status"] == "planned" for r in results)


def test_list_tasks_all(db):
    db.add_task("A", "planned")
    db.add_task("B", "doing")
    results = db.list_tasks()
    assert len(results) == 2


# ── decisions CRUD ──────────────────────────────────────────────────────────

def test_add_decision(db):
    did = db.add_decision("Use SQLite", "SQLite", "Zero-dep, WAL mode handles concurrency",
                          context="Need embedded DB", options="SQLite, DuckDB, JSON files")
    assert did == 1
    row = db.conn.execute("SELECT * FROM decisions WHERE id=?", (did,)).fetchone()
    assert row["chosen"] == "SQLite"
    assert row["context"] == "Need embedded DB"


# ── settings CRUD ───────────────────────────────────────────────────────────

def test_add_setting(db):
    sid = db.add_setting("learning_rate", "2e-4", citation="QLoRA paper Table 3")
    assert sid >= 1
    row = db.conn.execute("SELECT * FROM settings WHERE key='learning_rate'").fetchone()
    assert row["value"] == "2e-4"
    assert row["citation"] == "QLoRA paper Table 3"


def test_add_setting_upsert(db):
    db.add_setting("lr", "1e-4", "initial")
    db.add_setting("lr", "2e-4", "revised")
    rows = db.conn.execute("SELECT * FROM settings WHERE key='lr'").fetchall()
    assert len(rows) == 1
    assert rows[0]["value"] == "2e-4"


# ── canon CRUD ──────────────────────────────────────────────────────────────

def test_add_canon(db):
    cid = db.add_canon("LoRA rank-4 underperforms rank-16", "yes",
                       "3 runs, 0.8 vs 0.92 F1", tags="lora,rank")
    assert cid == 1
    row = db.conn.execute("SELECT * FROM canon WHERE id=?", (cid,)).fetchone()
    assert row["verdict"] == "yes"
    assert row["tags"] == "lora,rank"


# ── dispositions CRUD ───────────────────────────────────────────────────────

def test_add_disposition(db):
    did = db.add_disposition("full-param-rl", "Full Parameter RL Experiment",
                             "Tried full param, OOM at batch 32.", tags="rl,oom")
    assert did >= 1
    row = db.conn.execute("SELECT * FROM dispositions WHERE slug='full-param-rl'").fetchone()
    assert row["title"] == "Full Parameter RL Experiment"


def test_add_disposition_auto_slug(db):
    did = db.add_disposition("", "My Cool Experiment", "body text")
    row = db.conn.execute("SELECT * FROM dispositions WHERE id=?", (did,)).fetchone()
    assert row["slug"] == "my-cool-experiment"


# ── query ───────────────────────────────────────────────────────────────────

def test_query_by_type(db):
    db.add_task("TaskA", "planned")
    db.add_canon("ClaimB", "yes", "evidence")
    results = db.query_specs(type="tasks")
    assert len(results) == 1
    assert results[0]["title"] == "TaskA"


def test_query_by_text(db):
    db.add_task("Build LoRA", "planned")
    db.add_task("Fix bug", "doing")
    results = db.query_specs(query="lora")
    assert len(results) == 1
    assert "LoRA" in results[0]["title"]


# ── render ──────────────────────────────────────────────────────────────────

def test_render_all_creates_files(db, tmp_path):
    db.add_requirement("R1", "Criteria1", "must")
    db.add_task("T1", "doing", details="In progress")
    db.add_decision("D1", "Option A", "Reason A")
    db.add_setting("lr", "2e-4")
    db.add_canon("Claim1", "yes", "Proof1")
    db.add_disposition("exp-1", "Experiment 1", "Body here")

    out = tmp_path / "rendered"
    stats = db.render_all(out)

    assert (out / "requirements.md").exists()
    assert (out / "tasks.md").exists()
    assert (out / "design.md").exists()
    assert (out / "settings.md").exists()
    assert (out / "canon.md").exists()
    assert (out / "dispositions" / "exp-1.md").exists()
    assert stats["requirements.md"] == 1
    assert stats["tasks.md"] == 1


def test_render_tasks_content(db, tmp_path):
    db.add_task("Active task", "doing", details="Working on it")
    db.add_task("Planned task", "planned")
    out = tmp_path / "rendered"
    db.render_all(out)
    content = (out / "tasks.md").read_text(encoding="utf-8")
    assert "## DOING" in content
    assert "Active task" in content
    assert "## PLANNED" in content


def test_render_canon_verdict_first(db, tmp_path):
    db.add_canon("Sky is blue", "yes", "Looked up")
    out = tmp_path / "rendered"
    db.render_all(out)
    content = (out / "canon.md").read_text(encoding="utf-8")
    assert "**YES**" in content
    assert "Sky is blue" in content
