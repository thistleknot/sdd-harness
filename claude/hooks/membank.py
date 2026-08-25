#!/usr/bin/env python3
"""Memory read layer: inject the memory bank, plus ranked recall of memories.

Two modes, dispatched on the hook event in stdin:

- SessionStart  -> the memory-bank six-file layer (unchanged), then a recall block
                   of approved USER-scoped memories. There is no prompt yet, so
                   ranking is against the session's own project name.
- UserPromptSubmit -> the recall block ONLY, ranked against the actual prompt.
                   Re-emitting the whole bank on every turn would be the context
                   bloat this hook exists to avoid.

The split follows MKG's `inject_project_context.py`: user-scope facts belong at
session start, project-scope recall belongs where a query exists to rank against.

Every stored memory is injectable the moment it is written -- there is no approval
gate. Survival is decided downstream by retrieval: three retrievals promote a memory
to a skill, and anything never retrieved decays out. Recall is therefore also the
mechanism that curates, which is why injection counts hits.

Thesis
------
The memory-bank read protocol only works if it fires deterministically. A prose
instruction in CLAUDE.md is model-discretionary and gets skipped; a harness hook
does not. This script owns the READ side; CLAUDE.md owns the WRITE policy.

The recall half closes the loop that `log_event.py` (capture) and `mem dream`
(distillation) open: a memory nothing reads is a memory that was not worth
writing.

Why Python and not PowerShell
-----------------------------
Claude Code runs hook command strings through a POSIX-ish shell on this box.
That chain ate two dependencies in a row: Windows backslashes in the command
path were stripped (`C:\\Users\\...` -> `C:Usersuser...`, so the script was never
found), and `pwsh` resolves to a WindowsApps execution-alias stub that is
unreliable from non-interactive contexts. `python` is a real executable on PATH.
Invoke as: `python C:/Users/user/.claude/hooks/membank.py` (forward slashes).

Contract
--------
Require   - nothing. A missing memory bank is a valid state, not an error.
Guarantee - writes a bounded context block to stdout: MEMORY.md index, the
            global six-file layer, and the repo-local layer + last_session.md
            when cwd resolves to a git repo that has a bank under projects/.
Maintain  - total output stays under TOTAL; section ceilings sit below it to
            leave room for the unbudgeted headers. Ceilings are cumulative, so
            the global layer can never
            starve the repo layer (the more actionable half). Volatile logs are
            excerpted tail-first so the newest entries survive; stable docs
            head-first so the thesis survives. This hook must never re-create
            the context bloat it was written to replace.
Assert    - missing canonical files are named MISSING, never silently dropped.
            A non-repo cwd says so rather than implying a global-only bank is
            the whole picture.

Failure modes
-------------
- No memory-bank dir -> one NOTE line, exit 0. Never blocks a session.
- git absent / not a repo -> global layer only, stated explicitly.
- Repo has no bank -> foreign-repo guard message, no bank created.
- Any unexpected exception -> one NOTE line, exit 0. A broken hook must not
  break the session.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

MEM_TOOL_DIR = Path.home() / "Documents" / "dev" / "skills" / "memory-index"

# Frontmatter types that mark a discrete memory. Mirrors mem.ALLOWED_TYPES, kept
# literal here so this hook does not fail to inject when the tool dir is missing.
MEMORY_TYPES = {"user", "feedback", "project", "reference"}

# Memory-bank content contains non-cp1252 characters (>=, arrows, em dashes) and
# Windows consoles default to cp1252, which raises UnicodeEncodeError mid-write.
# Reconfigure before any output; errors='replace' so an exotic glyph degrades to
# '?' rather than aborting the whole injection.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, OSError):
    pass

# TOTAL is the real contract. Fixed headers and the foreign-repo guard print
# outside the budgeted path, so the section ceilings are set below TOTAL to leave
# room for them -- otherwise the script overruns the cap it advertises.
TOTAL = 6000
HEADER_RESERVE = 450
BUDGET = TOTAL - HEADER_RESERVE

CEIL_INDEX = 900
CEIL_GLOBAL = 3000
CEIL_REPO = BUDGET

# The recall block is budgeted OUTSIDE the bank budget above: it is a handful of
# short memories, and charging it against the bank would silently shrink the
# repo layer -- the more actionable half -- every time recall got a good hit.
RECALL_BUDGET = 1400
RECALL_LIMIT = 4
# Derived, not guessed. Measured against this corpus with nomic-embed-text
# (2026-07-29): 6 deliberately unrelated queries topped out at 0.552 similarity,
# while 3 on-topic queries bottomed out at 0.590 -- nomic compresses cosine into a
# narrow band, so an intuitive 0.45 floor matched nonsense. 0.57 is the midpoint of
# that measured gap. Small samples; re-measure if the corpus or embedder changes.
RECALL_MIN_SCORE = 0.57

CANON = [
    "projectbrief",
    "productContext",
    "activeContext",
    "systemPatterns",
    "techContext",
    "progress",
]
# Append-only logs: the newest entries are the load-bearing ones.
VOLATILE = {"activeContext", "progress", "last_session"}

_spent = 0
_ceiling = BUDGET


def emit(text: str) -> None:
    """Write to stdout, charged against the current section ceiling.

    Ceilings are cumulative caps on total spend, not independent pools -- a
    single shared pool let the global layer consume everything before the repo
    layer was reached.
    """
    global _spent
    if _spent >= _ceiling:
        return
    room = _ceiling - _spent
    if len(text) > room:
        text = text[:room] + "\n[...truncated at budget]"
    _spent += len(text)
    sys.stdout.write(text + "\n")


def excerpt(path: Path, max_chars: int, tail_biased: bool) -> str | None:
    """Bounded excerpt of one file, or None when the file is absent.

    None is distinct from '' so the caller can report MISSING rather than
    silently emitting an empty section.
    """
    if not path.is_file():
        return None
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return "(unreadable)"
    if not raw.strip():
        return "(empty)"
    raw = raw.rstrip()
    if len(raw) <= max_chars:
        return raw
    if tail_biased:
        return "[...earlier entries omitted]\n" + raw[-max_chars:].lstrip()
    return raw[:max_chars].rstrip() + "\n[...truncated]"


def emit_layer(directory: Path, names: list[str], label: str) -> None:
    """Emit one six-file layer, dividing remaining room across files still due."""
    emit(f"\n### {label}")
    remaining = len(names)
    for name in names:
        share = max(200, (_ceiling - _spent) // max(1, remaining))
        per_file = min(share, 900)
        body = excerpt(directory / f"{name}.md", per_file, name in VOLATILE)
        if body is None:
            emit(f"\n**{name}.md** - MISSING ({directory / (name + '.md')})")
        else:
            emit(f"\n**{name}.md**\n{body}")
        remaining -= 1


def git_root() -> str | None:
    """Repo root for cwd, or None when git is absent or cwd is not a repo."""
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    root = out.stdout.strip()
    return root if out.returncode == 0 and root else None


def emit_recall(query: str, session_id: str | None, context_wiped: bool) -> None:
    """Print already-reviewed memories ranked against `query`.

    Require   - Chroma and Ollama reachable; the memory index populated.
    Guarantee - at most RECALL_LIMIT memories, at most RECALL_BUDGET chars, each
                injected at most once per session. Prints nothing at all when
                there is no qualifying hit.
    Maintain  - already-promoted and aggregate docs are skipped; everything else in
                the store is fair game the moment it is written.
    Assert    - any failure in the retrieval stack degrades to silence, never to
                an error in the session's context.
    """
    if not query.strip():
        return
    if str(MEM_TOOL_DIR) not in sys.path:
        sys.path.insert(0, str(MEM_TOOL_DIR))
    try:
        import events_store as es
        import mem
    except Exception:
        return

    conn = None
    already: set[str] = set()
    try:
        conn = es.connect()
        if session_id:
            if context_wiped:
                es.clear_injections(conn, session_id)
            else:
                already = es.injected_names(conn, session_id)
    except Exception:
        conn = None

    try:
        col = mem.get_collection(mem.DEFAULT_MEM_DIR)
        if col.count() == 0:
            return
        qv = mem.embed([query], is_query=True)[0]
        # Over-fetch: status filtering, scope filtering, and per-session dedupe all
        # happen after retrieval, so the top-k must be wider than the display limit.
        res = col.query(query_embeddings=[qv], n_results=min(20, col.count()))
    except Exception:
        return
    finally:
        pass

    picked: list[tuple[str, str, str]] = []
    for mid, meta, dist, doc in zip(
        res["ids"][0], res["metadatas"][0], res["distances"][0], res["documents"][0]
    ):
        meta = meta or {}
        score = 1.0 - float(dist)
        if score < RECALL_MIN_SCORE:
            break  # distance-ordered, so nothing later qualifies either
        if meta.get("kind") != "doc":
            continue  # annealing-log bits have their own promotion path
        if meta.get("type") not in MEMORY_TYPES:
            # Aggregate living docs (activeContext, progress, AGENTS) have no
            # memory type. They are already injected wholesale above, so a chunk
            # of one here is duplication, and they sit near every query.
            continue
        # No scope filter: a real query is doing the filtering. Restricting to
        # project scope here would drop the hand-written legacy memories, which
        # are the most useful things in the store.
        name = str(meta.get("name") or mid)
        if name in already or any(name == p[0] for p in picked):
            continue
        picked.append((name, str(meta.get("description") or ""), doc))
        if len(picked) >= RECALL_LIMIT:
            break

    if not picked:
        return

    spent = 0
    print("\n### Recalled memories (ranked against this prompt)")
    shown = []
    for name, description, doc in picked:
        body = " ".join(doc.split())
        # The indexed document is description + body, so printing both repeats the
        # description verbatim in every entry.
        if description and body.startswith(description):
            body = body[len(description):].lstrip()
        room = RECALL_BUDGET - spent
        if room <= 120:
            break
        if len(body) > room:
            body = body[:room] + " […]"
        spent += len(body)
        print(f"\n**{name}** — {description}\n{body}")
        shown.append(name)

    if conn is not None and session_id and shown:
        es.record_injections(conn, session_id, shown)


def emit_user_memories(session_id: str | None, context_wiped: bool) -> None:
    """Print the most recently written approved USER-scope memories.

    Ordered by recency, NOT similarity. At SessionStart there is no prompt, and
    ranking against a synthetic stand-in query ("working in <repo>") scores below
    any honest relevance threshold -- which made this block silently never fire.
    With no query, recency is the only defensible ordering, which is the same
    choice MKG makes for its session-start observation recap.

    Reads markdown directly: no embedder, no vector store, so this half of recall
    still works when Ollama or Chroma is down.
    """
    if str(MEM_TOOL_DIR) not in sys.path:
        sys.path.insert(0, str(MEM_TOOL_DIR))
    try:
        import events_store as es
        import mem
    except Exception:
        return

    conn = None
    already: set[str] = set()
    try:
        conn = es.connect()
        if session_id:
            if context_wiped:
                es.clear_injections(conn, session_id)
            else:
                already = es.injected_names(conn, session_id)
    except Exception:
        conn = None

    entries = []
    try:
        for path in mem.memory_files(mem.DEFAULT_MEM_DIR):
            parsed = mem.parse_memory(path)
            meta = parsed.get("metadata") or {}
            if meta.get("type") not in MEMORY_TYPES:
                continue
            if (meta.get("scope") or "user") != "user":
                continue
            if parsed["name"] in already:
                continue
            entries.append((path.stat().st_mtime, parsed))
    except Exception:
        return
    if not entries:
        return
    entries.sort(key=lambda pair: -pair[0])

    spent, shown = 0, []
    print("\n### Recalled memories (durable facts about the user, newest first)")
    for _, parsed in entries[:RECALL_LIMIT]:
        body = " ".join(parsed["body"].split())
        room = RECALL_BUDGET - spent
        if room <= 120:
            break
        if len(body) > room:
            body = body[:room] + " […]"
        spent += len(body)
        print(f"\n**{parsed['name']}** — {parsed['description']}\n{body}")
        shown.append(parsed["name"])

    if conn is not None and session_id and shown:
        es.record_injections(conn, session_id, shown)


def capture_health_snapshot() -> dict | None:
    """Read capture health BEFORE anything else touches the store.

    Ordering matters: the recall paths call `events_store.connect`, which creates the
    store with a fresh schema if it is absent. Checking health after them would find
    a healthy empty file and report the wrong fault -- the read layer would have
    silently repaired the evidence of the problem.
    """
    if str(MEM_TOOL_DIR) not in sys.path:
        sys.path.insert(0, str(MEM_TOOL_DIR))
    try:
        import events_store as es
        return es.capture_health()
    except Exception:
        return None


def emit_loop_status(health: dict | None) -> None:
    """One line per problem with the memory loop. Silent when it is healthy.

    Capture fails silently by design (see `events_store.capture_health`), and
    distillation only runs when someone runs it. Both are states where nothing looks
    wrong and nothing is working, so both get polled once per session here rather than
    waited on.

    Guarantee - prints nothing when capture is live and distillation is current.
                Never raises; a diagnostic that breaks the session it diagnoses is
                worse than the silence it replaces.
    """
    if str(MEM_TOOL_DIR) not in sys.path:
        sys.path.insert(0, str(MEM_TOOL_DIR))
    try:
        import mem
    except Exception:
        return

    lines = []
    if health is not None and not health.get("ok"):
        if health.get("rebuildable"):
            # Missing or empty is a cache miss, not data loss: the events are
            # reconstructible from the Claude Code transcripts on disk.
            lines.append(
                f"- Event cache is cold: {health['reason']}. Call the "
                "`rebuild_event_cache` MCP tool; nothing is lost."
            )
        else:
            lines.append(
                f"- CAPTURE IS NOT RECORDING: {health['reason']}. New events are "
                "being dropped. Fix write access to ~/memory-bank/events.sqlite3 — "
                "past sessions are still rebuildable with `mem backfill`."
            )

    # Distillation staleness. There is deliberately no scheduler: the agent decides
    # when work is worth consolidating and calls the `distil_sessions` MCP tool
    # (memory-bank server). A scheduler would have to guess that moment, and needs a
    # registration step nobody performs. What a hook CAN do is make the absence
    # visible -- nothing fires on a non-event, so this reports it once per session.
    try:
        import events_store as es
        conn = es.connect()
        try:
            stamp = es.get_meta(conn, es.DREAM_ATTEMPT_KEY)
        finally:
            conn.close()
        if health and health.get("ok"):
            if not stamp:
                lines.append(
                    f"- {health.get('events', 0)} captured events have never been "
                    "distilled. Call the `distil_sessions` MCP tool (or "
                    "`mem dream --since 7d`) when this session's work is done."
                )
            else:
                from datetime import datetime, timezone
                last = datetime.fromisoformat(stamp)
                if last.tzinfo is None:
                    last = last.replace(tzinfo=timezone.utc)
                days = (datetime.now(timezone.utc) - last).days
                if days >= 2:
                    lines.append(
                        f"- Distillation last ran {days} days ago; captured events are "
                        "accumulating unread. Call the `distil_sessions` MCP tool "
                        "when this session's work is done."
                    )
    except Exception:
        pass

    try:
        conn = es.connect()
        try:
            size = (Path.home()/"memory-bank"/"events.sqlite3").stat().st_size
            if size > es.CAP_BYTES:
                lines.append(
                    f"- Event cache is {size/1024**3:.1f} GiB, over the "
                    f"{es.CAP_BYTES/1024**3:.0f} GiB cap. `distil_sessions` FIFO-prunes "
                    "on its next run; evicted sessions stay rebuildable via "
                    "`rebuild_event_cache`."
                )
        finally:
            conn.close()
    except Exception:
        pass

    if lines:
        print("\n### Memory loop status")
        for line in lines:
            print(line)


def read_payload() -> dict:
    """Hook payload from stdin, or {} when absent.

    SessionStart is also invoked with no stdin in some paths, so an empty read is
    a normal state, not a failure.
    """
    try:
        raw = sys.stdin.read()
    except Exception:
        return {}
    if not raw.strip():
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def main() -> int:
    global _ceiling

    payload = read_payload()
    hook_event = str(payload.get("hook_event_name") or "SessionStart")
    session_id = payload.get("session_id") or None
    # /clear and /compact wipe the transcript, so prior injections are no longer
    # in context and must not be suppressed as duplicates.
    context_wiped = payload.get("source") in {"clear", "compact"}

    # Sampled before any recall path can create or heal the store.
    health = capture_health_snapshot()

    if hook_event == "UserPromptSubmit":
        # Prompt-ranked project recall only. The bank was already injected at
        # session start; re-emitting it every turn is the bloat this avoids.
        emit_recall(str(payload.get("prompt") or ""), session_id, context_wiped)
        return 0

    root = Path(os.path.expanduser("~")) / "memory-bank"
    if not root.is_dir():
        print(f"NOTE: no memory bank at {root} - skipping memory-bank bootstrap.")
        return 0

    print("## Memory bank (SessionStart, read layer)")
    print("Write policy lives in CLAUDE.md. Full protocol: skill `memory-bank`.")

    _ceiling = CEIL_INDEX
    index = excerpt(root / "MEMORY.md", 1200, tail_biased=False)
    if index is not None:
        emit(f"\n### Topical index (MEMORY.md)\n{index}")

    _ceiling = CEIL_GLOBAL
    emit_layer(root, CANON, f"Global layer ({root})")

    _ceiling = CEIL_REPO
    repo = git_root()
    if repo is None:
        print("\n### Repo layer\nNot inside a git repository - global layer only.")
    else:
        name = Path(repo).name
        local = root / "projects" / name
        if local.is_dir():
            emit_layer(local, CANON + ["last_session"], f"Repo layer: {name} ({local})")
        else:
            # Foreign-repo guard: absence of a project dir is the signal NOT to
            # apply the skills-repo protocol here. Do not create one unprompted.
            print("\n### Repo layer")
            print(f"Repo `{name}` has no memory bank at {local}.")
            print(
                "Foreign-repo guard: use this workspace's own instructions. "
                "Do not create a bank unless asked."
            )

    if _spent >= BUDGET:
        print(f"\n[TRUNCATED at {BUDGET}-char budget - read files directly if more is needed.]")

    emit_user_memories(session_id, context_wiped)
    emit_loop_status(health)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # a broken hook must never break the session
        print(f"NOTE: memory-bank hook failed ({type(exc).__name__}: {exc}) - continuing.")
        sys.exit(0)
