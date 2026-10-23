"""board.py — SQLite store behind the agentic-kanban feature board.

Spec: specs.db REQ #40 (story lifecycle and dependency rule), REQ #43 (server shape and
project keying).
Task: specs.db task #65; plan.md T2. Plan import and render: REQ #45, task #72 (plan.md T4b).

This module is the only writer of ``board.db``. It owns the state machine and the dependency
rule and runs no git commands, no network and no LLM calls. Worktree side effects belong to
``worktrees.py``; the MCP server (``board_mcp.py``) sequences the two.

States: todo, in-progress, in-review, done, cancelled.
Actions and the transition each performs:

    claim   todo         -> in-progress   (every dependency must be done)
    submit  in-progress  -> in-review     (verification output must be non-empty)
    accept  in-review    -> done          (caller session != assigning session)
    reject  in-review    -> in-progress   (caller session != assigning session; note required)
    cancel  todo|in-progress|in-review -> cancelled   (not from done or cancelled)

Every project's rows carry ``project_key``; no function reads or writes a row whose key
differs from the one passed in.
"""
from __future__ import annotations

import json
import re
import sqlite3
import subprocess
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_DB = Path.home() / ".harness" / "board" / "board.db"
STATES = ("todo", "in-progress", "in-review", "done", "cancelled")
ACTIONS = ("claim", "submit", "accept", "reject", "cancel")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS feature(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_key TEXT NOT NULL,
    title TEXT NOT NULL,
    request_text TEXT NOT NULL,
    created_at TEXT NOT NULL,
    preamble TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS story(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    feature_id INTEGER NOT NULL REFERENCES feature(id),
    project_key TEXT NOT NULL,
    slug TEXT NOT NULL,
    title TEXT NOT NULL,
    acceptance_checks TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'todo',
    assignee_session TEXT,
    reviewer_session TEXT,
    branch TEXT,
    worktree_path TEXT,
    review_note TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    layer_heading TEXT NOT NULL DEFAULT '',
    body TEXT NOT NULL DEFAULT '',
    UNIQUE(project_key, slug)
);
CREATE TABLE IF NOT EXISTS story_dependency(
    story_id INTEGER NOT NULL REFERENCES story(id),
    depends_on_story_id INTEGER NOT NULL REFERENCES story(id),
    PRIMARY KEY(story_id, depends_on_story_id)
);
CREATE TABLE IF NOT EXISTS event(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    story_id INTEGER NOT NULL REFERENCES story(id),
    project_key TEXT NOT NULL,
    kind TEXT NOT NULL,
    session TEXT,
    at TEXT NOT NULL,
    detail TEXT
);
"""


class BoardError(Exception):
    """A rule of the board was violated.

    The message states what was refused and names the allowed next action, so the
    calling model can recover without guessing.
    """


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def project_key(project_root: str) -> str:
    """Return the board key for the repository containing ``project_root``.

    Args:
        project_root: Any directory inside a git repository, including a story's worktree.

    Returns:
        The absolute path printed by ``git rev-parse --git-common-dir``, resolved and with
        forward slashes, so the main checkout and every worktree map to the same key.

    Raises:
        BoardError: ``project_root`` is not inside a git repository.
    """
    root = Path(project_root)
    if not root.is_dir():
        raise BoardError(f"{project_root!r} is not a directory; pass a directory inside a git repository.")
    proc = subprocess.run(
        ["git", "rev-parse", "--git-common-dir"],
        cwd=str(root), capture_output=True, text=True, stdin=subprocess.DEVNULL,
    )
    if proc.returncode != 0 or not proc.stdout.strip():
        raise BoardError(f"{project_root!r} is not inside a git repository; run from a git checkout.")
    return (root / proc.stdout.strip()).resolve().as_posix()


def connect(db_path: str | Path | None = None) -> sqlite3.Connection:
    """Open the board database, creating the file, parent directory and schema if absent.

    Args:
        db_path: Database file; ``DEFAULT_DB`` when None.

    Returns:
        A connection in WAL mode with a busy timeout of at least 5000 ms, foreign keys on and
        ``sqlite3.Row`` rows, so several sessions can write the same file.

    Schema (all tables carry ``project_key`` except ``story_dependency``):
        feature(id, project_key, title, request_text, created_at)
        story(id, feature_id, project_key, slug, title, acceptance_checks, status,
              assignee_session, reviewer_session, branch, worktree_path, review_note,
              created_at, updated_at)
        story_dependency(story_id, depends_on_story_id)
        event(id, story_id, project_key, kind, session, at, detail)
    ``acceptance_checks`` is a JSON list of strings. ``slug`` is unique per project.
    """
    path = Path(db_path) if db_path is not None else DEFAULT_DB
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=30, isolation_level=None)
    conn.execute("PRAGMA busy_timeout = 30000")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    return conn


def _begin(conn: sqlite3.Connection) -> None:
    conn.execute("BEGIN IMMEDIATE")


def create_feature(conn: sqlite3.Connection, key: str, title: str, request_text: str) -> dict:
    """Insert a feature and return its row as a dict.

    Raises:
        BoardError: ``title`` is empty.
    """
    if not title or not title.strip():
        raise BoardError("Feature title is empty; provide a non-empty title.")
    cur = conn.execute(
        "INSERT INTO feature(project_key, title, request_text, created_at) VALUES(?,?,?,?)",
        (key, title, request_text, _now()),
    )
    return dict(conn.execute("SELECT * FROM feature WHERE id=?", (cur.lastrowid,)).fetchone())


def _slugify(title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:40].strip("-")
    return slug or "story"


def _deps(conn: sqlite3.Connection, story_id: int) -> list[int]:
    rows = conn.execute(
        "SELECT depends_on_story_id FROM story_dependency WHERE story_id=? ORDER BY depends_on_story_id",
        (story_id,),
    ).fetchall()
    return [r[0] for r in rows]


def _ready(conn: sqlite3.Connection, story_id: int) -> bool:
    row = conn.execute(
        "SELECT COUNT(*) FROM story_dependency d JOIN story s ON s.id=d.depends_on_story_id "
        "WHERE d.story_id=? AND s.status!='done'",
        (story_id,),
    ).fetchone()
    return row[0] == 0


def _story_dict(conn: sqlite3.Connection, row: sqlite3.Row) -> dict:
    d = dict(row)
    d["acceptance_checks"] = json.loads(d["acceptance_checks"])
    d["depends_on"] = _deps(conn, d["id"])
    d["next_action"] = next_action(d, _ready(conn, d["id"]))
    return d


def add_story(
    conn: sqlite3.Connection,
    key: str,
    feature_id: int,
    title: str,
    acceptance_checks: list[str],
    depends_on: list[int],
) -> dict:
    """Insert a story in ``todo`` and return its row, with ``next_action`` set.

    ``slug`` is the kebab-case title (lowercase, non-alphanumerics to single hyphens, at most
    40 characters), made unique within the project by a numeric suffix.

    Raises:
        BoardError: the feature does not exist in this project; ``acceptance_checks`` is
            empty; a dependency does not exist in this project; the dependency would create a
            cycle.
    """
    if not acceptance_checks:
        raise BoardError("acceptance_checks is empty; provide at least one check.")
    _begin(conn)
    try:
        if conn.execute(
            "SELECT 1 FROM feature WHERE id=? AND project_key=?", (feature_id, key)
        ).fetchone() is None:
            raise BoardError(f"Feature {feature_id} does not exist in this project; call create_feature first.")
        deps = sorted(set(depends_on))
        for dep in deps:
            if conn.execute(
                "SELECT 1 FROM story WHERE id=? AND project_key=?", (dep, key)
            ).fetchone() is None:
                raise BoardError(f"Dependency story {dep} does not exist in this project; depend only on existing stories.")
        base = _slugify(title)
        slug, n = base, 1
        while conn.execute(
            "SELECT 1 FROM story WHERE project_key=? AND slug=?", (key, slug)
        ).fetchone():
            n += 1
            slug = f"{base}-{n}"
        now = _now()
        cur = conn.execute(
            "INSERT INTO story(feature_id, project_key, slug, title, acceptance_checks, status, "
            "created_at, updated_at) VALUES(?,?,?,?,?,'todo',?,?)",
            (feature_id, key, slug, title, json.dumps(list(acceptance_checks)), now, now),
        )
        sid = cur.lastrowid
        for dep in deps:
            conn.execute(
                "INSERT INTO story_dependency(story_id, depends_on_story_id) VALUES(?,?)", (sid, dep)
            )
        conn.execute(
            "INSERT INTO event(story_id, project_key, kind, session, at, detail) VALUES(?,?,?,?,?,?)",
            (sid, key, "created", None, now, None),
        )
        conn.execute("COMMIT")
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    return get_story(conn, key, sid)


def get_story(conn: sqlite3.Connection, key: str, story_id: int) -> dict:
    """Return one story with ``depends_on`` (list of ids) and ``next_action``.

    Raises:
        BoardError: no such story in this project.
    """
    row = conn.execute(
        "SELECT * FROM story WHERE id=? AND project_key=?", (story_id, key)
    ).fetchone()
    if row is None:
        raise BoardError(f"Story {story_id} does not exist in this project; call list_stories to see valid ids.")
    return _story_dict(conn, row)


def list_stories(conn: sqlite3.Connection, key: str, feature_id: int | None = None) -> list[dict]:
    """Return the project's stories, optionally of one feature, ordered by id."""
    if feature_id is None:
        rows = conn.execute(
            "SELECT * FROM story WHERE project_key=? ORDER BY id", (key,)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM story WHERE project_key=? AND feature_id=? ORDER BY id", (key, feature_id)
        ).fetchall()
    return [_story_dict(conn, r) for r in rows]


def feature_status(conn: sqlite3.Connection, key: str, feature_id: int) -> str:
    """Derive a feature's status from its stories; it is never stored.

    Returns:
        ``empty`` with no stories; ``done`` when every story is done or cancelled and at least
        one is done; ``cancelled`` when every story is cancelled; ``in-progress`` when any
        story is in-progress or in-review; otherwise ``todo``.
    """
    statuses = [
        r[0]
        for r in conn.execute(
            "SELECT status FROM story WHERE project_key=? AND feature_id=?", (key, feature_id)
        ).fetchall()
    ]
    if not statuses:
        return "empty"
    if all(s == "cancelled" for s in statuses):
        return "cancelled"
    if all(s in ("done", "cancelled") for s in statuses):
        return "done"
    if any(s in ("in-progress", "in-review") for s in statuses):
        return "in-progress"
    return "todo"


def next_action(story: dict, ready: bool) -> str:
    """Name what may happen to ``story`` next, as one sentence for the calling model.

    Args:
        story: A story row dict.
        ready: True when every dependency is done.
    """
    status = story["status"]
    if status == "todo":
        if ready:
            return "Claim this story with claim, or cancel it with cancel."
        return "Blocked: a dependency is not done yet; wait until every dependency is done, or cancel it with cancel."
    if status == "in-progress":
        return "The assigning session may submit it with verification output, or anyone may cancel it with cancel."
    if status == "in-review":
        return "A different session than the assigning one must accept or reject it (reject needs a note); cancel is also allowed."
    if status == "done":
        return "No action allowed: the story is done."
    return "No action allowed: the story is cancelled."


def check_transition(
    conn: sqlite3.Connection, key: str, story_id: int, action: str, session: str
) -> None:
    """Raise ``BoardError`` unless ``action`` is legal now; change nothing.

    The MCP server calls this before any worktree side effect so a refused action leaves git
    untouched. Rules are those in the module docstring, plus: ``submit`` requires ``session``
    to equal the assigning session; ``session`` must be non-empty.
    """
    if action not in ACTIONS and action != "lesson":
        raise BoardError(f"Unknown action {action!r}; allowed actions are {', '.join(ACTIONS)}.")
    if not session or not session.strip():
        raise BoardError("session is empty; provide the calling session id.")
    story = get_story(conn, key, story_id)
    status = story["status"]
    allowed = story["next_action"]
    if action == "claim":
        if status != "todo":
            raise BoardError(f"Cannot claim a story that is {status}. {allowed}")
        if not _ready(conn, story_id):
            raise BoardError(f"Cannot claim: a dependency is not done. {allowed}")
    elif action == "submit":
        if status != "in-progress":
            raise BoardError(f"Cannot submit a story that is {status}. {allowed}")
        if session != story["assignee_session"]:
            raise BoardError(f"Only the assigning session may submit. {allowed}")
    elif action in ("accept", "reject"):
        if status != "in-review":
            raise BoardError(f"Cannot {action} a story that is {status}. {allowed}")
        if session == story["assignee_session"]:
            raise BoardError(f"The assigning session cannot {action} its own story; ask a different session to review. {allowed}")
    elif action == "cancel":
        if status in ("done", "cancelled"):
            raise BoardError(f"Cannot cancel a story that is {status}. {allowed}")
    elif action == "lesson":
        if status == "cancelled":
            raise BoardError(f"Cannot add a lesson to a story that is cancelled. {allowed}")


def _update(conn: sqlite3.Connection, key: str, story_id: int, action: str, session: str,
            fields: dict, kind: str, detail: str | None) -> dict:
    _begin(conn)
    try:
        check_transition(conn, key, story_id, action, session)
        now = _now()
        current = get_story(conn, key, story_id) if any(callable(v) for v in fields.values()) else None
        fields = {k: (v(current) if callable(v) else v) for k, v in fields.items()}
        fields["updated_at"] = now
        sets = ", ".join(f"{k}=?" for k in fields)
        conn.execute(
            f"UPDATE story SET {sets} WHERE id=? AND project_key=?",
            (*fields.values(), story_id, key),
        )
        conn.execute(
            "INSERT INTO event(story_id, project_key, kind, session, at, detail) VALUES(?,?,?,?,?,?)",
            (story_id, key, kind, session, now, detail),
        )
        conn.execute("COMMIT")
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    return get_story(conn, key, story_id)


def claim_story(
    conn: sqlite3.Connection, key: str, story_id: int, session: str, branch: str, worktree_path: str
) -> dict:
    """Move a story to in-progress, recording assignee, branch and worktree path."""
    return _update(
        conn, key, story_id, "claim", session,
        {"status": "in-progress", "assignee_session": session, "branch": branch,
         "worktree_path": worktree_path},
        "claimed", branch,
    )


def submit_story(
    conn: sqlite3.Connection, key: str, story_id: int, session: str, verification_output: str
) -> dict:
    """Move a story to in-review and append an event holding ``verification_output``.

    Raises:
        BoardError: ``verification_output`` is empty or whitespace.
    """
    if not verification_output or not verification_output.strip():
        raise BoardError("verification_output is empty; run the verify command and pass its output.")
    return _update(
        conn, key, story_id, "submit", session, {"status": "in-review"},
        "submitted", verification_output,
    )


def accept_story(conn: sqlite3.Connection, key: str, story_id: int, session: str) -> dict:
    """Move a story to done and record ``session`` as reviewer.

    Raises:
        BoardError: ``session`` equals the assigning session.
    """
    return _update(
        conn, key, story_id, "accept", session,
        {"status": "done", "reviewer_session": session}, "accepted", None,
    )


def reject_story(
    conn: sqlite3.Connection, key: str, story_id: int, session: str, note: str
) -> dict:
    """Move a story back to in-progress, storing ``note`` as ``review_note``.

    Raises:
        BoardError: ``note`` is empty; ``session`` equals the assigning session.
    """
    if not note or not note.strip():
        raise BoardError("note is empty; state what must change, then call reject again.")
    return _update(
        conn, key, story_id, "reject", session,
        {"status": "in-progress", "reviewer_session": session, "review_note": note},
        "rejected", note,
    )


def cancel_story(
    conn: sqlite3.Connection, key: str, story_id: int, session: str, reason: str
) -> dict:
    """Move a story to cancelled and append an event holding ``reason``."""
    return _update(
        conn, key, story_id, "cancel", session, {"status": "cancelled"}, "cancelled", reason,
    )


def add_lesson(conn: sqlite3.Connection, key: str, story_id: int, session: str, text: str) -> dict:
    """Append ``  _Lessons:_ <text>`` to a story's stored ``body``.

    Spec: specs.db REQ #45. Task: specs.db task #72.

    This is how a lesson reaches a generated plan.md that no agent may edit by hand. Allowed
    in any status except cancelled. Appends an event of kind ``lesson`` holding ``text`` and
    returns the story row with ``next_action``.

    Raises:
        BoardError: ``text`` is empty or whitespace; no such story in this project; the story
            is cancelled.
    """
    if not text or not text.strip():
        raise BoardError("text is empty; state the lesson, then call add_lesson again.")
    line = f"  _Lessons:_ {text}"
    # A callable is evaluated by _update inside its write transaction, so two sessions
    # appending at once each see the other's line instead of overwriting it.
    return _update(
        conn, key, story_id, "lesson", session,
        {"body": lambda story: f"{story['body']}\n{line}" if story["body"] else line},
        "lesson", text,
    )


def import_plan(
    conn: sqlite3.Connection, key: str, plan_text: str, feature_title: str, session: str
) -> dict:
    """Import a plan.md-format file once, as one feature with one story per task.

    Spec: specs.db REQ #45. Task: specs.db task #72.

    Plan format: ``## Layer <n> - parallel|sequential`` headings; under each,
    ``- [OPEN|WIP|DONE|BLOCKED] T<n> <title>`` task lines followed by indented ``_Files:_``,
    ``_Verify:_``, ``_Lessons:_`` and ``_Blocked:_`` lines.

    Lossless storage (REQ #45, amended): besides the parsed fields, store verbatim (a) the
    text before the first layer heading as the feature's ``preamble``, (b) each task's layer
    heading line as the story's ``layer_heading``, and (c) every line under the task line, up
    to the next task or layer heading, as the story's ``body`` (newline-joined, no trailing
    blank lines). New columns: ``feature.preamble``, ``story.layer_heading``, ``story.body``,
    all TEXT NOT NULL DEFAULT ''. A story added later through ``add_story`` has an empty
    ``layer_heading`` and body.

    Mapping: OPEN -> todo; WIP -> in-progress; DONE -> done; BLOCKED -> todo with the
    ``_Blocked:_`` text stored as ``review_note``. Acceptance checks are the task's
    ``_Verify:_`` text, then ``Files: <list>``. Dependencies follow the layer barrier: every
    task depends on every task of the previous layer, and in a sequential layer also on the
    task listed just before it. Imported stories carry no assignee, branch or worktree; one
    ``imported`` event per story records ``session``.

    Returns:
        ``{"feature_id": int, "stories": {"T<n>": story_id, ...}}``.

    Raises:
        BoardError: ``feature_title`` already exists in this project; no tasks were found;
            two tasks share an id.
    """
    layer_re = re.compile(r"^##\s+Layer\s+\d+\s*-\s*(\w+)")
    task_re = re.compile(r"^- \[(OPEN|WIP|DONE|BLOCKED)\]\s+(\S+)\s*(.*)$")
    field_re = re.compile(r"^\s+_(Files|Verify|Blocked):_\s*(.*)$")
    layers: list[list[dict]] = []
    ltypes: list[str] = []
    cur = None
    heading = ""
    preamble: list[str] = []
    for line in plan_text.splitlines():
        m = layer_re.match(line)
        if m:
            layers.append([])
            ltypes.append(m.group(1).lower())
            heading = line
            cur = None
            continue
        m = task_re.match(line)
        if m:
            if not layers:
                layers.append([])
                ltypes.append("parallel")
            status, tid, rest = m.groups()
            cur = {"status": status, "tid": tid, "title": f"{tid} {rest}".strip(),
                   "Files": "", "Verify": "", "Blocked": "", "heading": heading, "body": []}
            layers[-1].append(cur)
            continue
        if cur is None:
            if not layers:
                preamble.append(line)
            continue
        cur["body"].append(line)
        m = field_re.match(line)
        if m:
            cur[m.group(1)] = m.group(2).strip()
    while preamble and not preamble[-1].strip():
        preamble.pop()
    tasks = [t for layer in layers for t in layer]
    for t in tasks:
        while t["body"] and not t["body"][-1].strip():
            t["body"].pop()
    if not tasks:
        raise BoardError("No tasks found in the plan text; expected '- [OPEN|WIP|DONE|BLOCKED] T<n> <title>' lines.")
    seen: set[str] = set()
    for t in tasks:
        if t["tid"] in seen:
            raise BoardError(f"Task id {t['tid']} appears twice in the plan; make task ids unique.")
        seen.add(t["tid"])
    if conn.execute(
        "SELECT 1 FROM feature WHERE project_key=? AND title=?", (key, feature_title)
    ).fetchone():
        raise BoardError(f"Feature {feature_title!r} already exists in this project; a plan is imported once.")
    feature = create_feature(conn, key, feature_title, f"Imported from plan: {feature_title}")
    conn.execute("UPDATE feature SET preamble=? WHERE id=?", ("\n".join(preamble), feature["id"]))
    ids: dict[str, int] = {}
    prev_ids: list[int] = []
    for layer, ltype in zip(layers, ltypes):
        if not layer:
            continue
        this_ids: list[int] = []
        for t in layer:
            deps = list(prev_ids)
            if ltype == "sequential" and this_ids:
                deps.append(this_ids[-1])
            checks = []
            if t["Verify"]:
                checks.append(t["Verify"])
            if t["Files"]:
                checks.append(f"Files: {t['Files']}")
            if not checks:
                checks = ["No verify command recorded in the plan."]
            story = add_story(conn, key, feature["id"], t["title"], checks, deps)
            sid = story["id"]
            fields: dict = {"layer_heading": t["heading"], "body": "\n".join(t["body"])}
            if t["status"] == "WIP":
                fields["status"] = "in-progress"
            elif t["status"] == "DONE":
                fields["status"] = "done"
            elif t["status"] == "BLOCKED" and t["Blocked"]:
                fields["review_note"] = t["Blocked"]
            now = _now()
            if fields:
                sets = ", ".join(f"{k}=?" for k in fields)
                conn.execute(
                    f"UPDATE story SET {sets} WHERE id=? AND project_key=?", (*fields.values(), sid, key)
                )
            conn.execute(
                "INSERT INTO event(story_id, project_key, kind, session, at, detail) VALUES(?,?,?,?,?,?)",
                (sid, key, "imported", session, now, t["status"]),
            )
            ids[t["tid"]] = sid
            this_ids.append(sid)
        prev_ids = this_ids
    return {"feature_id": feature["id"], "stories": ids}


def render_plan(conn: sqlite3.Connection, key: str, feature_id: int) -> str:
    """Render a feature to plan.md-format markdown.

    Output is the stored ``preamble``, then for each story in id order the story's
    ``layer_heading`` line when it differs from the previous story's (a blank line before
    each heading), then ``- [STATUS] <title>`` and the stored ``body`` lines. Stories with an
    empty ``layer_heading`` (added on the board) are grouped last under
    ``## Layer <n> - added on the board``. Status maps: todo -> OPEN, in-progress and
    in-review -> WIP, done -> DONE, cancelled -> BLOCKED. A story's own ``review_note`` is
    shown as a ``_Blocked:_`` body line only if its body has none. The file ends with exactly
    one newline.

    Guarantees: rendering a freshly imported plan reproduces the imported text byte for byte
    (for a plan whose layers are separated by single blank lines and whose file ends in one
    newline); after one story's status changes, only that story's status tag differs; two
    renders with no board change are byte-identical.

    Raises:
        BoardError: no such feature in this project.
    """
    feat = conn.execute(
        "SELECT * FROM feature WHERE id=? AND project_key=?", (feature_id, key)
    ).fetchone()
    if feat is None:
        raise BoardError(f"Feature {feature_id} does not exist in this project; call list_stories to see valid ids.")
    stories = list_stories(conn, key, feature_id)
    imported = [s for s in stories if s["layer_heading"]]
    added = [s for s in stories if not s["layer_heading"]]
    headings = [s["layer_heading"] for s in imported]
    n_layers = sum(1 for i, h in enumerate(headings) if i == 0 or h != headings[i - 1])
    tid_re = re.compile(r"^(T\w*)\s+(.*)$")
    out = feat["preamble"].split("\n") if feat["preamble"] else []
    prev_heading = None
    for s in imported + added:
        heading = s["layer_heading"]
        if not heading:
            heading = f"## Layer {n_layers + 1} - added on the board"
        if heading != prev_heading:
            if out:
                out.append("")
            out.append(heading)
            prev_heading = heading
        title = s["title"] if tid_re.match(s["title"]) else f"T{s['id']} {s['title']}"
        body = s["body"].split("\n") if s["body"] else []
        note = s["review_note"] if s["status"] == "todo" and s["review_note"] else None
        if s["status"] == "cancelled":
            row = conn.execute(
                "SELECT detail FROM event WHERE story_id=? AND project_key=? AND kind='cancelled' "
                "ORDER BY id DESC LIMIT 1", (s["id"], key),
            ).fetchone()
            note = (row["detail"] if row and row["detail"] else "cancelled")
        tag = {"todo": "OPEN", "in-progress": "WIP", "in-review": "WIP", "done": "DONE",
               "cancelled": "BLOCKED"}[s["status"]]
        if note:
            tag = "BLOCKED"
        out.append(f"- [{tag}] {title}")
        if not s["layer_heading"]:
            checks = s["acceptance_checks"]
            files = next((c[len("Files: "):] for c in checks if c.startswith("Files: ")), None)
            verify = next((c for c in checks if not c.startswith("Files: ")), None)
            if files:
                out.append(f"  _Files:_ {files}")
            if verify:
                out.append(f"  _Verify:_ {verify}")
        out.extend(body)
        if note and not any("_Blocked:_" in line for line in body):
            out.append(f"  _Blocked:_ {' '.join(note.split())}")
    return "\n".join(out) + "\n"
