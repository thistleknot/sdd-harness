"""specs_db.py — SQLite source of truth for the harness spec tracker.

Owns: schema init, CRUD operations, and full markdown rendering.
The DB is the single source of truth; all .md files are derived views.

Usage:
    from specs_db import SpecsDB
    db = SpecsDB("specs.db")
    db.add_task("Implement LoRA probe", "planned", details="rank-4 test")
    db.render_all(".")  # writes requirements.md, tasks.md, etc.
"""
from __future__ import annotations

import sqlite3
import textwrap
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _slugify(text: str) -> str:
    return text.lower().replace(" ", "-").replace("/", "-")[:80]


class SpecsDB:
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.conn = sqlite3.connect(str(self.db_path), isolation_level="DEFERRED")
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA busy_timeout=5000")
        self._init_schema()

    def _init_schema(self):
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS requirements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                criteria TEXT NOT NULL,
                priority TEXT DEFAULT 'normal' CHECK(priority IN ('must','should','could','normal')),
                status TEXT DEFAULT 'active' CHECK(status IN ('active','met','dropped')),
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS decisions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                context TEXT,
                options TEXT,
                chosen TEXT NOT NULL,
                rationale TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                status TEXT DEFAULT 'planned' CHECK(status IN ('planned','doing','done','blocked','deferred','deprecated')),
                details TEXT,
                blocker TEXT,
                parent_id INTEGER REFERENCES tasks(id),
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS settings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                key TEXT NOT NULL UNIQUE,
                value TEXT NOT NULL,
                citation TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS canon (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                claim TEXT NOT NULL,
                verdict TEXT NOT NULL CHECK(verdict IN ('yes','no','mixed','inconclusive')),
                evidence TEXT NOT NULL,
                tags TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS dispositions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                slug TEXT NOT NULL UNIQUE,
                title TEXT NOT NULL,
                body TEXT NOT NULL,
                tags TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
        """)
        self.conn.commit()

    # ── CRUD: requirements ──────────────────────────────────────────────────

    def add_requirement(self, title: str, criteria: str, priority: str = "normal") -> int:
        now = _now()
        cur = self.conn.execute(
            "INSERT INTO requirements (title, criteria, priority, created_at, updated_at) VALUES (?,?,?,?,?)",
            (title, criteria, priority, now, now),
        )
        self.conn.commit()
        return cur.lastrowid

    def update_requirement(self, id: int, **kwargs) -> None:
        allowed = {"title", "criteria", "priority", "status"}
        fields = {k: v for k, v in kwargs.items() if k in allowed and v is not None}
        if not fields:
            return
        fields["updated_at"] = _now()
        sets = ", ".join(f"{k}=?" for k in fields)
        self.conn.execute(f"UPDATE requirements SET {sets} WHERE id=?", [*fields.values(), id])
        self.conn.commit()

    # ── CRUD: decisions ─────────────────────────────────────────────────────

    def add_decision(self, title: str, chosen: str, rationale: str,
                     context: str = None, options: str = None) -> int:
        now = _now()
        cur = self.conn.execute(
            "INSERT INTO decisions (title, context, options, chosen, rationale, created_at, updated_at) VALUES (?,?,?,?,?,?,?)",
            (title, context, options, chosen, rationale, now, now),
        )
        self.conn.commit()
        return cur.lastrowid

    # ── CRUD: tasks ─────────────────────────────────────────────────────────

    def add_task(self, title: str, status: str = "planned", details: str = None,
                 parent_id: int = None) -> int:
        now = _now()
        cur = self.conn.execute(
            "INSERT INTO tasks (title, status, details, parent_id, created_at, updated_at) VALUES (?,?,?,?,?,?)",
            (title, status, details, parent_id, now, now),
        )
        self.conn.commit()
        return cur.lastrowid

    def update_task(self, id: int, **kwargs) -> None:
        allowed = {"title", "status", "details", "blocker", "parent_id"}
        fields = {k: v for k, v in kwargs.items() if k in allowed and v is not None}
        if not fields:
            return
        fields["updated_at"] = _now()
        sets = ", ".join(f"{k}=?" for k in fields)
        self.conn.execute(f"UPDATE tasks SET {sets} WHERE id=?", [*fields.values(), id])
        self.conn.commit()

    def list_tasks(self, status: str = None) -> list[dict]:
        if status:
            rows = self.conn.execute("SELECT * FROM tasks WHERE status=? ORDER BY id", (status,)).fetchall()
        else:
            rows = self.conn.execute("SELECT * FROM tasks ORDER BY status, id").fetchall()
        return [dict(r) for r in rows]

    # ── CRUD: settings ──────────────────────────────────────────────────────

    def add_setting(self, key: str, value: str, citation: str = None) -> int:
        now = _now()
        cur = self.conn.execute(
            "INSERT OR REPLACE INTO settings (key, value, citation, created_at, updated_at) VALUES (?,?,?, COALESCE((SELECT created_at FROM settings WHERE key=?), ?), ?)",
            (key, value, citation, key, now, now),
        )
        self.conn.commit()
        return cur.lastrowid

    # ── CRUD: canon ─────────────────────────────────────────────────────────

    def add_canon(self, claim: str, verdict: str, evidence: str, tags: str = None) -> int:
        now = _now()
        cur = self.conn.execute(
            "INSERT INTO canon (claim, verdict, evidence, tags, created_at, updated_at) VALUES (?,?,?,?,?,?)",
            (claim, verdict, evidence, tags, now, now),
        )
        self.conn.commit()
        return cur.lastrowid

    # ── CRUD: dispositions ──────────────────────────────────────────────────

    def add_disposition(self, slug: str, title: str, body: str, tags: str = None) -> int:
        now = _now()
        slug = _slugify(slug) if slug else _slugify(title)
        cur = self.conn.execute(
            "INSERT OR REPLACE INTO dispositions (slug, title, body, tags, created_at, updated_at) VALUES (?,?,?,?, COALESCE((SELECT created_at FROM dispositions WHERE slug=?), ?), ?)",
            (slug, title, body, tags, slug, now, now),
        )
        self.conn.commit()
        return cur.lastrowid

    # ── Query ───────────────────────────────────────────────────────────────

    def query_specs(self, type: str = None, status: str = None, query: str = None) -> list[dict]:
        """Search across tables. Returns matching rows with their source table."""
        results = []
        tables = [type] if type else ["requirements", "decisions", "tasks", "settings", "canon", "dispositions"]

        for table in tables:
            try:
                rows = self.conn.execute(f"SELECT *, '{table}' as _table FROM {table}").fetchall()
                for r in rows:
                    d = dict(r)
                    if status and d.get("status") != status:
                        continue
                    if query and query.lower() not in str(d).lower():
                        continue
                    results.append(d)
            except sqlite3.OperationalError:
                continue
        return results

    # ── Render ──────────────────────────────────────────────────────────────

    def render_all(self, out_dir: str | Path) -> dict[str, int]:
        """Regenerate all markdown files. Returns {filename: row_count}."""
        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        stats = {}

        stats["requirements.md"] = self._render_requirements(out / "requirements.md")
        stats["design.md"] = self._render_decisions(out / "design.md")
        stats["tasks.md"] = self._render_tasks(out / "tasks.md")
        stats["settings.md"] = self._render_settings(out / "settings.md")
        stats["canon.md"] = self._render_canon(out / "canon.md")
        stats.update(self._render_dispositions(out / "dispositions"))

        return stats

    def _render_requirements(self, path: Path) -> int:
        rows = self.conn.execute("SELECT * FROM requirements ORDER BY priority, id").fetchall()
        lines = ["# Requirements\n"]
        for r in rows:
            status_mark = {"active": " ", "met": "x", "dropped": "-"}.get(r["status"], " ")
            lines.append(f"- [{status_mark}] **[{r['priority'].upper()}]** {r['title']}")
            lines.append(f"  - Criteria: {r['criteria']}")
            lines.append("")
        path.write_text("\n".join(lines), encoding="utf-8")
        return len(rows)

    def _render_decisions(self, path: Path) -> int:
        rows = self.conn.execute("SELECT * FROM decisions ORDER BY id").fetchall()
        lines = ["# Design Decisions\n"]
        for r in rows:
            lines.append(f"## {r['id']}. {r['title']}\n")
            if r["context"]:
                lines.append(f"**Context:** {r['context']}\n")
            if r["options"]:
                lines.append(f"**Options:** {r['options']}\n")
            lines.append(f"**Chosen:** {r['chosen']}\n")
            lines.append(f"**Rationale:** {r['rationale']}\n")
            lines.append("---\n")
        path.write_text("\n".join(lines), encoding="utf-8")
        return len(rows)

    def _render_tasks(self, path: Path) -> int:
        rows = self.conn.execute(
            "SELECT * FROM tasks ORDER BY CASE status "
            "WHEN 'doing' THEN 0 WHEN 'blocked' THEN 1 WHEN 'planned' THEN 2 "
            "WHEN 'deferred' THEN 3 WHEN 'done' THEN 4 WHEN 'deprecated' THEN 5 END, id"
        ).fetchall()
        lines = ["# Tasks\n"]

        current_status = None
        for r in rows:
            if r["status"] != current_status:
                current_status = r["status"]
                lines.append(f"## {current_status.upper()}\n")

            check = "x" if r["status"] == "done" else " "
            prefix = f"- [{check}] `#{r['id']}` {r['title']}"
            if r["parent_id"]:
                prefix = f"  {prefix}"  # indent children
            lines.append(prefix)

            if r["details"]:
                lines.append(f"    - {r['details']}")
            if r["blocker"]:
                lines.append(f"    - **BLOCKER:** {r['blocker']}")
            lines.append("")

        path.write_text("\n".join(lines), encoding="utf-8")
        return len(rows)

    def _render_settings(self, path: Path) -> int:
        rows = self.conn.execute("SELECT * FROM settings ORDER BY key").fetchall()
        lines = ["# Settings\n", "| Key | Value | Citation |", "|-----|-------|----------|"]
        for r in rows:
            citation = r["citation"] or ""
            lines.append(f"| `{r['key']}` | `{r['value']}` | {citation} |")
        lines.append("")
        path.write_text("\n".join(lines), encoding="utf-8")
        return len(rows)

    def _render_canon(self, path: Path) -> int:
        rows = self.conn.execute("SELECT * FROM canon ORDER BY id").fetchall()
        lines = ["# Canon (Settled Claims)\n"]
        for r in rows:
            verdict_icon = {"yes": "YES", "no": "NO", "mixed": "MIXED", "inconclusive": "???"}.get(r["verdict"], r["verdict"])
            lines.append(f"- **{verdict_icon}** — {r['claim']}")
            lines.append(f"  - Evidence: {r['evidence']}")
            if r["tags"]:
                lines.append(f"  - Tags: {r['tags']}")
            lines.append("")
        path.write_text("\n".join(lines), encoding="utf-8")
        return len(rows)

    def _render_dispositions(self, dir_path: Path) -> dict[str, int]:
        dir_path.mkdir(parents=True, exist_ok=True)
        rows = self.conn.execute("SELECT * FROM dispositions ORDER BY id").fetchall()

        # Clean stale files
        existing = {p.stem for p in dir_path.glob("*.md")}
        current_slugs = {r["slug"] for r in rows}
        for stale in existing - current_slugs:
            (dir_path / f"{stale}.md").unlink(missing_ok=True)

        for r in rows:
            lines = [
                f"# {r['title']}\n",
                f"**Slug:** `{r['slug']}`",
            ]
            if r["tags"]:
                lines.append(f"**Tags:** {r['tags']}")
            lines.append(f"**Created:** {r['created_at']}\n")
            lines.append("---\n")
            lines.append(r["body"])
            lines.append("")
            (dir_path / f"{r['slug']}.md").write_text("\n".join(lines), encoding="utf-8")

        return {f"dispositions/{r['slug']}.md": 1 for r in rows}

    def close(self):
        self.conn.close()
