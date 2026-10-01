#!/usr/bin/env python3
"""ID-bearing store for the spec-driven gate: SQLite is the source of truth.

Thesis
------
Markdown cannot carry stable identity. A requirement is "the third bullet" until
someone inserts a second one, and then every reference to it is silently wrong.
Properties bind to requirements, tasks bind to requirements, gates bind to
properties -- none of that survives a store whose primary key is line position.

So the DB holds the records and the markdown becomes a *generated read-view*.
The direction is one-way on purpose: `render` writes markdown from the DB, and
`reconcile` reports when someone has edited the generated region by hand. It
refuses rather than overwriting, because silently discarding a human's edit
teaches people the tool eats their work, and then they stop using it.

Layout
------
    <spec_root>/spec.db                     one DB per spec root
    <spec_root>/specs/<feature>/requirements.md   generated region
    <spec_root>/specs/<feature>/tasks.md          generated region

Contract
--------
Require   - a `.spec/` root above cwd (`spec_paths.find_spec_root`).
Guarantee - every mutation routes through this CLI; ids are allocated, never
            reused, and never renumbered. `render` is idempotent.
Maintain  - the generated region is delimited and checksummed, so a hand edit is
            detectable rather than a merge conflict nobody notices.
Assert    - the DB is authoritative. Markdown is derived and disposable; deleting
            a generated region costs nothing because `render` rebuilds it.

Note on schema evolution: `CREATE TABLE IF NOT EXISTS` is a *no-op* against an
existing table, so a new column added to the DDL below never appears in a DB
created by an earlier version. Additive `ALTER TABLE` in `_migrate` is what
actually applies it. Add columns in both places or reads of the new column raise.
"""

from __future__ import annotations

import hashlib
import os
import re
import sqlite3
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from spec_paths import find_spec_root, specs_dir  # noqa: E402

DB_NAME = "spec.db"

BEGIN = "<!-- spec:begin -->"
END_RE = re.compile(r"<!--\s*spec:end(?:\s+sha256=([0-9a-f]{8,64}))?\s*-->")

STRENGTHS = {"MUST", "SHALL", "SHOULD", "MAY"}
PBT_VALUES = {"required", "n/a"}
GATE_VALUES = {"pass", "fail", "unrun"}

# Whitelists. Field names reach SQL as identifiers and cannot be parameterised,
# so `update` validates against these rather than interpolating user input.
FIELDS = {
    "requirements": {"feature", "text", "strength", "ears_form", "pbt", "pbt_reason"},
    "tasks": {"feature", "text", "done", "file_hint"},
    "properties": {
        "feature", "requirement_id", "task_id", "test_ref", "sut_symbol",
        "g1", "g2", "g3", "g4", "impl_hash", "checked_at",
    },
}
PREFIX = {"R": "requirements", "T": "tasks", "P": "properties"}

DDL = [
    """CREATE TABLE IF NOT EXISTS requirements (
           id TEXT PRIMARY KEY, feature TEXT NOT NULL, text TEXT NOT NULL,
           strength TEXT NOT NULL, ears_form TEXT, pbt TEXT, pbt_reason TEXT)""",
    """CREATE TABLE IF NOT EXISTS tasks (
           id TEXT PRIMARY KEY, feature TEXT NOT NULL, text TEXT NOT NULL,
           done INTEGER NOT NULL DEFAULT 0, file_hint TEXT)""",
    """CREATE TABLE IF NOT EXISTS properties (
           id TEXT PRIMARY KEY, feature TEXT NOT NULL,
           requirement_id TEXT, task_id TEXT, test_ref TEXT,
           sut_symbol TEXT NOT NULL,
           g1 TEXT NOT NULL DEFAULT 'unrun', g2 TEXT NOT NULL DEFAULT 'unrun',
           g3 TEXT NOT NULL DEFAULT 'unrun', g4 TEXT NOT NULL DEFAULT 'unrun',
           impl_hash TEXT, checked_at TEXT)""",
]

# Additive migrations: (table, column, DDL fragment). Applied when absent.
MIGRATIONS: list[tuple[str, str, str]] = []


# --------------------------------------------------------------------------- db


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def die(message: str) -> int:
    sys.stderr.write(message.rstrip() + "\n")
    return 1


def db_path(spec_root: str) -> str:
    return os.path.join(spec_root, DB_NAME)


def _migrate(conn: sqlite3.Connection) -> None:
    """Apply additive column migrations. See the module note on IF NOT EXISTS."""
    for table, column, fragment in MIGRATIONS:
        cols = {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
        if column not in cols:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {fragment}")


def connect(spec_root: str, create: bool = False) -> sqlite3.Connection | None:
    path = db_path(spec_root)
    if not create and not os.path.isfile(path):
        return None
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    for stmt in DDL:
        conn.execute(stmt)
    _migrate(conn)
    conn.commit()
    return conn


def next_id(conn: sqlite3.Connection, table: str, prefix: str) -> str:
    """Highest existing number plus one. Ids are never reused."""
    top = 0
    for row in conn.execute(f"SELECT id FROM {table}"):
        m = re.fullmatch(rf"{prefix}-(\d+)", str(row["id"]))
        if m:
            top = max(top, int(m.group(1)))
    return f"{prefix}-{top + 1}"


def require_root() -> str | None:
    root = find_spec_root(os.getcwd())
    if not root:
        sys.stderr.write(
            "No .spec/ directory found above the working directory. "
            "Run /spec-init first to make this repo spec-driven.\n"
        )
    return root


def require_db(spec_root: str) -> sqlite3.Connection | None:
    conn = connect(spec_root)
    if conn is None:
        sys.stderr.write(
            f"No {DB_NAME} in {spec_root}. Run 'spec_store.py init' first.\n"
        )
    return conn


def parse_kv(args: list[str]) -> dict[str, str]:
    """`--field=value` pairs. Rejects bare flags so typos are not silently lost."""
    out: dict[str, str] = {}
    for arg in args:
        if not arg.startswith("--") or "=" not in arg:
            raise ValueError(f"Expected --field=value, got '{arg}'")
        key, value = arg[2:].split("=", 1)
        out[key.replace("-", "_")] = value
    return out


# ----------------------------------------------------------------------- render


def _region_hash(body: str) -> str:
    return hashlib.sha256(body.encode("utf-8")).hexdigest()[:16]


def render_requirements(conn: sqlite3.Connection, feature: str) -> str:
    rows = conn.execute(
        "SELECT * FROM requirements WHERE feature = ? ORDER BY CAST(SUBSTR(id, 3) AS INTEGER)",
        (feature,),
    ).fetchall()
    if not rows:
        return "_No requirements recorded._"
    lines = []
    for r in rows:
        line = f"- **{r['id']}** [{r['strength']}] {r['text']}"
        if r["pbt"] == "n/a":
            reason = r["pbt_reason"] or "(no reason given -- G2 will flag this)"
            line += f"\n  - _pbt: n/a -- {reason}_"
        lines.append(line)
    return "\n".join(lines)


def render_tasks(conn: sqlite3.Connection, feature: str) -> str:
    rows = conn.execute(
        "SELECT * FROM tasks WHERE feature = ? ORDER BY CAST(SUBSTR(id, 3) AS INTEGER)",
        (feature,),
    ).fetchall()
    if not rows:
        return "_No tasks recorded._"
    lines = []
    for r in rows:
        box = "x" if r["done"] else " "
        line = f"- [{box}] **{r['id']}** {r['text']}"
        if r["file_hint"]:
            line += f"  `{r['file_hint']}`"
        lines.append(line)
    return "\n".join(lines)


def splice(existing: str, body: str) -> str:
    """Replace the generated region, preserving prose outside the markers."""
    block = f"{BEGIN}\n{body}\n<!-- spec:end sha256={_region_hash(body)} -->"
    if BEGIN in existing:
        head, rest = existing.split(BEGIN, 1)
        m = END_RE.search(rest)
        tail = rest[m.end():] if m else ""
        return head + block + tail
    sep = "" if not existing or existing.endswith("\n\n") else ("\n" if existing.endswith("\n") else "\n\n")
    return existing + sep + block + "\n"


def extract_region(text: str) -> tuple[str, str] | None:
    """Return (body, recorded_hash) for the generated region, or None."""
    if BEGIN not in text:
        return None
    rest = text.split(BEGIN, 1)[1]
    m = END_RE.search(rest)
    if not m:
        return None
    return rest[: m.start()].strip("\n"), (m.group(1) or "")


def write_atomic(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    os.replace(tmp, path)


def feature_files(spec_root: str, feature: str) -> dict[str, str]:
    base = os.path.join(specs_dir(spec_root), feature)
    return {
        "requirements.md": os.path.join(base, "requirements.md"),
        "tasks.md": os.path.join(base, "tasks.md"),
    }


def features_in_db(conn: sqlite3.Connection) -> list[str]:
    seen = set()
    for table in ("requirements", "tasks", "properties"):
        for row in conn.execute(f"SELECT DISTINCT feature FROM {table}"):
            seen.add(row["feature"])
    return sorted(seen)


def drift(conn: sqlite3.Connection, spec_root: str, feature: str) -> list[str]:
    """Report ways the markdown disagrees with the DB. Empty list means clean."""
    problems = []
    rendered = {
        "requirements.md": render_requirements(conn, feature),
        "tasks.md": render_tasks(conn, feature),
    }
    for name, path in feature_files(spec_root, feature).items():
        if not os.path.isfile(path):
            problems.append(f"{feature}/{name}: missing -- run 'render'")
            continue
        try:
            text = open(path, encoding="utf-8").read()
        except OSError as exc:
            problems.append(f"{feature}/{name}: unreadable ({exc})")
            continue
        region = extract_region(text)
        if region is None:
            problems.append(f"{feature}/{name}: no spec:begin/spec:end markers -- run 'render'")
            continue
        body, recorded = region
        if recorded and _region_hash(body) != recorded:
            problems.append(
                f"{feature}/{name}: generated region was hand-edited "
                f"(checksum {recorded} != {_region_hash(body)}). "
                f"Move the edit into the DB, or re-render with --force to discard it."
            )
        elif body != rendered[name]:
            problems.append(f"{feature}/{name}: stale -- DB has changed since last render")
    return problems


# ------------------------------------------------------------------- commands


def cmd_init() -> int:
    root = require_root()
    if not root:
        return 1
    fresh = not os.path.isfile(db_path(root))
    conn = connect(root, create=True)
    assert conn is not None
    conn.close()
    print(f"{'Created' if fresh else 'Verified'} {db_path(root)}")
    return 0


def cmd_add_req(args: list[str]) -> int:
    root = require_root()
    if not root:
        return 1
    conn = require_db(root)
    if conn is None:
        return 1
    try:
        kv = parse_kv(args)
    except ValueError as exc:
        return die(str(exc))

    missing = {"feature", "text", "strength"} - kv.keys()
    if missing:
        return die(f"add-req requires {', '.join(sorted(missing))}")
    strength = kv["strength"].upper()
    if strength not in STRENGTHS:
        return die(f"strength must be one of {'/'.join(sorted(STRENGTHS))}, got '{kv['strength']}'")
    pbt = kv.get("pbt", "required")
    if pbt not in PBT_VALUES:
        return die(f"pbt must be 'required' or 'n/a', got '{pbt}'")
    if pbt == "n/a" and not kv.get("pbt_reason", "").strip():
        return die("pbt=n/a requires --pbt-reason=... -- an unexplained exemption is how the gate becomes a liar")

    rid = next_id(conn, "requirements", "R")
    conn.execute(
        "INSERT INTO requirements (id, feature, text, strength, ears_form, pbt, pbt_reason)"
        " VALUES (?, ?, ?, ?, ?, ?, ?)",
        (rid, kv["feature"], kv["text"], strength, kv.get("ears_form"), pbt, kv.get("pbt_reason")),
    )
    conn.commit()
    print(f"{rid}  [{strength}] {kv['text']}")
    return 0


def cmd_add_task(args: list[str]) -> int:
    root = require_root()
    if not root:
        return 1
    conn = require_db(root)
    if conn is None:
        return 1
    try:
        kv = parse_kv(args)
    except ValueError as exc:
        return die(str(exc))

    missing = {"feature", "text"} - kv.keys()
    if missing:
        return die(f"add-task requires {', '.join(sorted(missing))}")
    tid = next_id(conn, "tasks", "T")
    conn.execute(
        "INSERT INTO tasks (id, feature, text, done, file_hint) VALUES (?, ?, ?, ?, ?)",
        (tid, kv["feature"], kv["text"], 0, kv.get("file_hint")),
    )
    conn.commit()
    print(f"{tid}  {kv['text']}")
    return 0


def cmd_add_prop(args: list[str]) -> int:
    root = require_root()
    if not root:
        return 1
    conn = require_db(root)
    if conn is None:
        return 1
    try:
        kv = parse_kv(args)
    except ValueError as exc:
        return die(str(exc))

    missing = {"feature", "sut_symbol"} - kv.keys()
    if missing:
        return die(f"add-prop requires {', '.join(sorted(missing))}")
    if not kv["sut_symbol"].strip():
        return die("sut_symbol cannot be empty -- G3 needs a seam to mutate")
    for ref, table in (("requirement_id", "requirements"), ("task_id", "tasks")):
        val = kv.get(ref)
        if val and not conn.execute(f"SELECT 1 FROM {table} WHERE id = ?", (val,)).fetchone():
            return die(f"{ref} '{val}' does not exist")

    pid = next_id(conn, "properties", "P")
    conn.execute(
        "INSERT INTO properties (id, feature, requirement_id, task_id, test_ref, sut_symbol)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        (pid, kv["feature"], kv.get("requirement_id"), kv.get("task_id"),
         kv.get("test_ref"), kv["sut_symbol"]),
    )
    conn.commit()
    print(f"{pid}  sut={kv['sut_symbol']}  gates unrun")
    return 0


def cmd_update(args: list[str]) -> int:
    if not args:
        return die("update requires an id: spec_store.py update R-2 --text=...")
    root = require_root()
    if not root:
        return 1
    conn = require_db(root)
    if conn is None:
        return 1

    rec_id, rest = args[0], args[1:]
    prefix = rec_id.split("-", 1)[0].upper()
    table = PREFIX.get(prefix)
    if not table:
        return die(f"Unknown id '{rec_id}'. Ids look like R-1, T-1, P-1.")
    if not conn.execute(f"SELECT 1 FROM {table} WHERE id = ?", (rec_id,)).fetchone():
        return die(f"{rec_id} not found")
    try:
        kv = parse_kv(rest)
    except ValueError as exc:
        return die(str(exc))
    if not kv:
        return die("update requires at least one --field=value")

    bad = kv.keys() - FIELDS[table]
    if bad:
        return die(
            f"Unknown field(s) for {table}: {', '.join(sorted(bad))}. "
            f"Allowed: {', '.join(sorted(FIELDS[table]))}"
        )
    for gate in ("g1", "g2", "g3", "g4"):
        if gate in kv and kv[gate] not in GATE_VALUES:
            return die(f"{gate} must be pass|fail|unrun, got '{kv[gate]}'")
    if "strength" in kv:
        kv["strength"] = kv["strength"].upper()
        if kv["strength"] not in STRENGTHS:
            return die(f"strength must be one of {'/'.join(sorted(STRENGTHS))}")
    if "pbt" in kv and kv["pbt"] not in PBT_VALUES:
        return die("pbt must be 'required' or 'n/a'")
    if "done" in kv:
        kv["done"] = "1" if kv["done"].lower() in {"1", "true", "yes", "done"} else "0"
    if table == "properties" and kv.keys() & {"g1", "g2", "g3", "g4"}:
        kv.setdefault("checked_at", now())

    assign = ", ".join(f"{k} = ?" for k in kv)          # keys whitelisted above
    conn.execute(f"UPDATE {table} SET {assign} WHERE id = ?", (*kv.values(), rec_id))
    conn.commit()
    print(f"{rec_id}  updated: {', '.join(sorted(kv))}")
    return 0


def cmd_render(args: list[str]) -> int:
    root = require_root()
    if not root:
        return 1
    conn = require_db(root)
    if conn is None:
        return 1

    force = "--force" in args
    wanted = [a for a in args if not a.startswith("--")]
    features = wanted or features_in_db(conn)
    if not features:
        print("Nothing to render: the store is empty.")
        return 0

    rc = 0
    for feature in features:
        problems = [p for p in drift(conn, root, feature) if "hand-edited" in p]
        if problems and not force:
            for p in problems:
                sys.stderr.write("REFUSED  " + p + "\n")
            rc = 1
            continue
        bodies = {
            "requirements.md": render_requirements(conn, feature),
            "tasks.md": render_tasks(conn, feature),
        }
        for name, path in feature_files(root, feature).items():
            existing = open(path, encoding="utf-8").read() if os.path.isfile(path) else ""
            write_atomic(path, splice(existing, bodies[name]))
            print(f"rendered  {feature}/{name}")
    return rc


def cmd_reconcile() -> int:
    root = require_root()
    if not root:
        return 1
    conn = require_db(root)
    if conn is None:
        return 1

    features = features_in_db(conn)
    if not features:
        print("Store is empty; nothing to reconcile.")
        return 0
    problems = []
    for feature in features:
        problems.extend(drift(conn, root, feature))
    if not problems:
        print(f"Clean: {len(features)} feature(s) match the store.")
        return 0
    for p in problems:
        print("DRIFT  " + p)
    return 1


def cmd_show(args: list[str]) -> int:
    root = require_root()
    if not root:
        return 1
    conn = require_db(root)
    if conn is None:
        return 1

    only = args[0] if args else None
    for feature in features_in_db(conn):
        if only and feature != only:
            continue
        print(f"\n=== {feature} ===")
        for row in conn.execute(
            "SELECT * FROM requirements WHERE feature = ?"
            " ORDER BY CAST(SUBSTR(id, 3) AS INTEGER)", (feature,)):
            flag = "" if row["pbt"] != "n/a" else "  (pbt n/a)"
            print(f"  {row['id']:<6} [{row['strength']:<6}] {row['text']}{flag}")
        for row in conn.execute(
            "SELECT * FROM tasks WHERE feature = ?"
            " ORDER BY CAST(SUBSTR(id, 3) AS INTEGER)", (feature,)):
            print(f"  {row['id']:<6} [{'x' if row['done'] else ' '}] {row['text']}")
        for row in conn.execute(
            "SELECT * FROM properties WHERE feature = ?"
            " ORDER BY CAST(SUBSTR(id, 3) AS INTEGER)", (feature,)):
            gates = " ".join(f"{g.upper()}:{row[g]}" for g in ("g1", "g2", "g3", "g4"))
            bind = row["requirement_id"] or row["task_id"] or "unbound"
            print(f"  {row['id']:<6} -> {bind:<6} sut={row['sut_symbol']}  {gates}")
    return 0


USAGE = ("Use: init | add-req | add-task | add-prop | update <id> --field=value "
         "| render [feature...] [--force] | reconcile | show [feature]")


def main(argv: list[str]) -> int:
    if not argv:
        return die(USAGE)
    command, args = argv[0], argv[1:]
    if command == "init":
        return cmd_init()
    if command == "add-req":
        return cmd_add_req(args)
    if command == "add-task":
        return cmd_add_task(args)
    if command == "add-prop":
        return cmd_add_prop(args)
    if command == "update":
        return cmd_update(args)
    if command == "render":
        return cmd_render(args)
    if command == "reconcile":
        return cmd_reconcile()
    if command == "show":
        return cmd_show(args)
    return die(f"Unknown command '{command}'. {USAGE}")


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass
    sys.exit(main(sys.argv[1:]))
