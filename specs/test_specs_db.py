"""SpecsDB integration: schema init, CRUD roundtrip, render pipeline."""
from pathlib import Path

import pytest

from specs.specs_db import SpecsDB, _slugify


@pytest.fixture
def db(tmp_path):
    s = SpecsDB(tmp_path / "test.db")
    yield s
    s.close()


def test_full_crud_roundtrip(db):
    """All 6 tables: insert → query → verify."""
    rid = db.add_requirement("Auth", "Must authenticate", "must")
    did = db.add_decision("Use JWT", "JWT", "Stateless")
    tid = db.add_task("Implement auth", "planned", details="Sprint 1")
    sid = db.add_setting("timeout", "30s")
    cid = db.add_canon("JWT works", "yes", "Tested 3x")
    db.add_disposition("exp-1", "First Experiment", "Body")

    assert rid >= 1 and did >= 1 and tid >= 1 and sid >= 1 and cid >= 1
    results = db.query_specs(type="requirements")
    assert len(results) == 1 and results[0]["priority"] == "must"


def test_update_lifecycle(db):
    """Requirements and tasks transition through statuses."""
    rid = db.add_requirement("Feature", "Criteria", "should")
    db.update_requirement(rid, status="met")

    tid = db.add_task("Build it", "planned")
    db.update_task(tid, status="doing")
    db.update_task(tid, status="done")

    tasks = db.list_tasks("done")
    assert len(tasks) == 1


def test_query_filters(db):
    """Query by type, status, and text search."""
    db.add_task("Build LoRA", "planned")
    db.add_task("Fix bug", "doing")
    db.add_canon("Claim", "yes", "proof")

    assert len(db.query_specs(type="tasks")) == 2
    assert len(db.query_specs(type="tasks", status="doing")) == 1
    assert len(db.query_specs(query="lora")) == 1


def test_render_all_produces_files(db, tmp_path):
    """Render pipeline creates all expected markdown files."""
    db.add_requirement("R1", "C1", "must")
    db.add_task("T1", "doing")
    db.add_decision("D1", "Choice", "Reason")
    db.add_setting("k", "v")
    db.add_canon("Claim", "yes", "Evidence")
    db.add_disposition("slug-1", "Title", "Body")

    out = tmp_path / "out"
    stats = db.render_all(out)

    assert (out / "requirements.md").exists()
    assert (out / "tasks.md").exists()
    assert (out / "design.md").exists()
    assert (out / "dispositions" / "slug-1.md").exists()
    assert stats["requirements.md"] == 1


def test_setting_upsert(db):
    """Settings with same key replace — no duplicates."""
    db.add_setting("lr", "1e-4")
    db.add_setting("lr", "2e-4")
    rows = db.conn.execute("SELECT * FROM settings WHERE key='lr'").fetchall()
    assert len(rows) == 1 and rows[0]["value"] == "2e-4"


# ── slugify (restored: dropped during the specs/ package migration) ──────────

def test_slugify_basic():
    assert _slugify("Hello World") == "hello-world"


def test_slugify_slashes():
    assert _slugify("path/to/thing") == "path-to-thing"


def test_slugify_truncates_at_80():
    long = "a" * 100
    assert len(_slugify(long)) == 80


# ── negative path (restored) ────────────────────────────────────────────────

def test_update_requirement_ignores_invalid_fields(db):
    """Unknown kwargs must not reach the SQL string — no injection, no-op."""
    rid = db.add_requirement("Feature X", "Criteria Y", "should")
    db.update_requirement(rid, hacker="drop table")  # should be a no-op
    row = db.conn.execute("SELECT * FROM requirements WHERE id=?", (rid,)).fetchone()
    assert row["title"] == "Feature X"
    assert row["criteria"] == "Criteria Y"
