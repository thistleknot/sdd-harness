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

            CREATE TABLE IF NOT EXISTS failures (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                approach TEXT NOT NULL,
                signature TEXT NOT NULL,
                context TEXT,
                error_class TEXT,
                evidence TEXT NOT NULL,
                falsifies TEXT,
                conditions TEXT,
                status TEXT DEFAULT 'dead' CHECK(status IN ('dead','conditional','revived')),
                observations INTEGER DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_failures_signature ON failures(signature);
            CREATE INDEX IF NOT EXISTS idx_failures_status ON failures(status);

            CREATE TABLE IF NOT EXISTS future_directions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                rationale TEXT NOT NULL,
                trigger TEXT,
                scope TEXT NOT NULL DEFAULT 'harness',
                status TEXT DEFAULT 'open' CHECK(status IN ('open','promoted','dropped')),
                promoted_to TEXT,
                tags TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_future_scope ON future_directions(scope);
            CREATE INDEX IF NOT EXISTS idx_future_status ON future_directions(status);
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

    # ── CRUD: failures ──────────────────────────────────────────────────────

    @staticmethod
    def _failure_signature(approach: str) -> str:
        """Compute a structural signature for an approach.

        Masks identifiers, numbers, and quoted strings (Tracely-inspired)
        so that the same approach phrased slightly differently still matches.
        """
        import hashlib
        import re
        text = approach.lower().strip()
        # Mask hex ids, UUIDs
        text = re.sub(r'\b[0-9a-f]{8,}\b', '<id>', text)
        # Mask numbers
        text = re.sub(r'\b\d+(\.\d+)?\b', '<n>', text)
        # Mask quoted strings
        text = re.sub(r"'[^']*'|\"[^\"]*\"", '<*>', text)
        # Collapse whitespace
        text = re.sub(r'\s+', ' ', text)
        return hashlib.sha256(text.encode()).hexdigest()[:16]

    def add_failure(self, approach: str, evidence: str, context: str = None,
                    error_class: str = None, falsifies: str = None,
                    conditions: str = None) -> int:
        """Record a failed approach with its structural signature.

        If an approach with the same signature already exists, increments
        observations instead of creating a duplicate.
        """
        now = _now()
        sig = self._failure_signature(approach)

        # Check for existing failure with same signature
        existing = self.conn.execute(
            "SELECT id, observations FROM failures WHERE signature=? AND status='dead'",
            (sig,)
        ).fetchone()

        if existing:
            self.conn.execute(
                "UPDATE failures SET observations=observations+1, evidence=?, updated_at=? WHERE id=?",
                (evidence, now, existing["id"])
            )
            self.conn.commit()
            return existing["id"]

        cur = self.conn.execute(
            "INSERT INTO failures (approach, signature, context, error_class, evidence, falsifies, conditions, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (approach, sig, context, error_class, evidence, falsifies, conditions, now, now),
        )
        self.conn.commit()
        return cur.lastrowid

    def check_failures(self, approach: str, threshold: float = 0.0) -> list[dict]:
        """Check if an approach matches any known dead-end failures.

        Uses exact signature match. Returns matching failures sorted by
        observations (most-observed first).
        """
        sig = self._failure_signature(approach)
        rows = self.conn.execute(
            "SELECT * FROM failures WHERE signature=? AND status='dead' ORDER BY observations DESC",
            (sig,)
        ).fetchall()
        return [dict(r) for r in rows]

    def list_failures(self, status: str = None, limit: int = 20) -> list[dict]:
        """List recorded failures, optionally filtered by status."""
        if status:
            rows = self.conn.execute(
                "SELECT * FROM failures WHERE status=? ORDER BY observations DESC, updated_at DESC LIMIT ?",
                (status, limit)
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM failures ORDER BY observations DESC, updated_at DESC LIMIT ?",
                (limit,)
            ).fetchall()
        return [dict(r) for r in rows]

    def revive_failure(self, id: int, reason: str) -> None:
        """Mark a failure as revived (conditions changed, approach viable again)."""
        now = _now()
        self.conn.execute(
            "UPDATE failures SET status='revived', conditions=?, updated_at=? WHERE id=?",
            (reason, now, id)
        )
        self.conn.commit()

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

    # ── CRUD: future directions ────────────────────────────────────────

    def add_future_direction(self, title: str, rationale: str, trigger: str = None,
                             scope: str = "harness", tags: str = None) -> int:
        """Record uncommitted work worth revisiting. Not a task — no owner, no ETA."""
        now = _now()
        cur = self.conn.execute(
            "INSERT INTO future_directions (title, rationale, trigger, scope, tags, created_at, updated_at) VALUES (?,?,?,?,?,?,?)",
            (title, rationale, trigger, scope, tags, now, now),
        )
        self.conn.commit()
        return cur.lastrowid

    def update_future_direction(self, id: int, **kwargs) -> None:
        """Transition a direction. status: open | promoted | dropped

        Promoting sets promoted_to — the task or requirement that now owns the work.
        """
        fields = {k: v for k, v in kwargs.items() if v is not None and k in
                  ("title", "rationale", "trigger", "scope", "status", "promoted_to", "tags")}
        if not fields:
            return
        sets = ", ".join(f"{k}=?" for k in fields)
        self.conn.execute(
            f"UPDATE future_directions SET {sets}, updated_at=? WHERE id=?",
            (*fields.values(), _now(), id),
        )
        self.conn.commit()

    # ── Query ───────────────────────────────────────────────────────────────

    def query_specs(self, type: str = None, status: str = None, query: str = None) -> list[dict]:
        """Search across tables. Returns matching rows with their source table."""
        results = []
        tables = [type] if type else ["requirements", "decisions", "tasks", "settings", "canon", "dispositions", "failures", "future_directions"]

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

    _GENERATED_BANNER = "<!-- GENERATED — DO NOT EDIT — source: specs/specs.db -->\n"

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
        stats["failures.md"] = self._render_failures(out / "failures.md")
        stats["future_directions.md"] = self._render_future_directions(out / "future_directions.md")
        stats.update(self._render_dispositions(out / "dispositions"))

        return stats

    def _render_requirements(self, path: Path) -> int:
        rows = self.conn.execute("SELECT * FROM requirements ORDER BY priority, id").fetchall()
        lines = [self._GENERATED_BANNER + "# Requirements\n"]
        for r in rows:
            status_mark = {"active": " ", "met": "x", "dropped": "-"}.get(r["status"], " ")
            lines.append(f"- [{status_mark}] **[{r['priority'].upper()}]** {r['title']}")
            lines.append(f"  - Criteria: {r['criteria']}")
            lines.append("")
        path.write_text("\n".join(lines), encoding="utf-8")
        return len(rows)

    def _render_decisions(self, path: Path) -> int:
        rows = self.conn.execute("SELECT * FROM decisions ORDER BY id").fetchall()
        lines = [self._GENERATED_BANNER + "# Design Decisions\n"]
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
        lines = [self._GENERATED_BANNER + "# Tasks\n"]

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
        lines = [self._GENERATED_BANNER + "# Settings\n", "| Key | Value | Citation |", "|-----|-------|----------|"]
        for r in rows:
            citation = r["citation"] or ""
            lines.append(f"| `{r['key']}` | `{r['value']}` | {citation} |")
        lines.append("")
        path.write_text("\n".join(lines), encoding="utf-8")
        return len(rows)

    def _render_canon(self, path: Path) -> int:
        rows = self.conn.execute("SELECT * FROM canon ORDER BY id").fetchall()
        lines = [self._GENERATED_BANNER + "# Canon (Settled Claims)\n"]
        for r in rows:
            verdict_icon = {"yes": "YES", "no": "NO", "mixed": "MIXED", "inconclusive": "???"}.get(r["verdict"], r["verdict"])
            lines.append(f"- **{verdict_icon}** — {r['claim']}")
            lines.append(f"  - Evidence: {r['evidence']}")
            if r["tags"]:
                lines.append(f"  - Tags: {r['tags']}")
            lines.append("")
        path.write_text("\n".join(lines), encoding="utf-8")
        return len(rows)

    def _render_failures(self, path: Path) -> int:
        rows = self.conn.execute(
            "SELECT * FROM failures ORDER BY status, observations DESC, updated_at DESC"
        ).fetchall()
        lines = [self._GENERATED_BANNER + "# Failure Registry (Dead Ends)\n"]
        lines.append("Approaches proven dead. Check before pursuing similar ideas.\n")

        current_status = None
        for r in rows:
            if r["status"] != current_status:
                current_status = r["status"]
                icon = {"dead": "DEAD", "conditional": "CONDITIONAL", "revived": "REVIVED"}
                lines.append(f"## {icon.get(current_status, current_status.upper())}\n")

            obs = f" (×{r['observations']})" if r['observations'] > 1 else ""
            lines.append(f"- **#{r['id']}**{obs} {r['approach']}")
            lines.append(f"  - Evidence: {r['evidence']}")
            if r["error_class"]:
                lines.append(f"  - Error class: {r['error_class']}")
            if r["falsifies"]:
                lines.append(f"  - Falsifies: {r['falsifies']}")
            if r["conditions"]:
                lines.append(f"  - Conditions: {r['conditions']}")
            lines.append(f"  - Signature: `{r['signature']}`")
            lines.append("")
        path.write_text("\n".join(lines), encoding="utf-8")
        return len(rows)

    def _render_future_directions(self, path: Path) -> int:
        rows = self.conn.execute(
            "SELECT * FROM future_directions ORDER BY status, scope, id"
        ).fetchall()
        lines = [self._GENERATED_BANNER + "# Future Directions (Uncommitted)\n"]
        lines.append(
            "Work that MIGHT be worth doing. Nobody owns these and none is scheduled — "
            "that is what separates a direction from a `planned` task in tasks.md.\n"
        )
        lines.append(
            "Each carries the **trigger** that would promote it. A direction with no "
            "trigger never gets revisited, because nothing tells you to look.\n"
        )

        current = None
        for r in rows:
            key = (r["status"], r["scope"])
            if key != current:
                current = key
                lines.append(f"## {r['status'].upper()} — {r['scope']}\n")

            lines.append(f"- **#{r['id']}** {r['title']}")
            lines.append(f"  - Why: {r['rationale']}")
            if r["trigger"]:
                lines.append(f"  - Revisit when: {r['trigger']}")
            else:
                lines.append("  - Revisit when: **NO TRIGGER — this is a wish, not a direction**")
            if r["promoted_to"]:
                lines.append(f"  - Promoted to: {r['promoted_to']}")
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
                self._GENERATED_BANNER + f"# {r['title']}\n",
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
