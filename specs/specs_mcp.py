"""specs_mcp.py — FastMCP server exposing the specs tracker as MCP tools.

Runs as a persistent HTTP service. CRUD tools write to specs.db,
then auto-render all markdown views after each mutation.

Usage:
    python specs_mcp.py [--port 8057]

Register in mcp.json:
    "specs": { "url": "http://127.0.0.1:8057/mcp", "disabled": false }
"""
from __future__ import annotations

import os
from pathlib import Path

from fastmcp import FastMCP

from specs_db import SpecsDB

HERE = Path(__file__).parent
DB_PATH = HERE / "specs.db"
RENDER_DIR = HERE  # render markdown into the same specs/ folder

db = SpecsDB(DB_PATH)

mcp = FastMCP(
    name="specs",
    instructions=(
        "Spec tracker for the harness project. SQLite is the source of truth; "
        "markdown files are rendered views. Use CRUD tools to add/update items, "
        "query tools to search, and render to force a full re-render."
    ),
)


def _auto_render() -> dict:
    """Re-render all markdown after any mutation."""
    return db.render_all(RENDER_DIR)


# ── Requirements ────────────────────────────────────────────────────────────

@mcp.tool
def add_requirement(title: str, criteria: str, priority: str = "normal") -> str:
    """Add an acceptance criterion.

    priority: must | should | could | normal
    """
    rid = db.add_requirement(title, criteria, priority)
    _auto_render()
    return f"Requirement #{rid} added: {title}"


@mcp.tool
def update_requirement(id: int, title: str = None, criteria: str = None,
                       priority: str = None, status: str = None) -> str:
    """Update a requirement. status: active | met | dropped"""
    db.update_requirement(id, title=title, criteria=criteria, priority=priority, status=status)
    _auto_render()
    return f"Requirement #{id} updated"


# ── Decisions ───────────────────────────────────────────────────────────────

@mcp.tool
def add_decision(title: str, chosen: str, rationale: str,
                 context: str = None, options: str = None) -> str:
    """Record an architecture decision."""
    did = db.add_decision(title, chosen, rationale, context, options)
    _auto_render()
    return f"Decision #{did} added: {title}"


# ── Tasks ───────────────────────────────────────────────────────────────────

@mcp.tool
def add_task(title: str, status: str = "planned", details: str = None,
             parent_id: int = None) -> str:
    """Add a plan item. status: planned | doing | done | blocked | deferred | deprecated"""
    tid = db.add_task(title, status, details, parent_id)
    _auto_render()
    return f"Task #{tid} added: {title} [{status}]"


@mcp.tool
def update_task(id: int, status: str = None, details: str = None,
                blocker: str = None) -> str:
    """Transition a task's state."""
    db.update_task(id, status=status, details=details, blocker=blocker)
    _auto_render()
    return f"Task #{id} updated"


@mcp.tool
def list_tasks(status: str = None) -> str:
    """List tasks, optionally filtered by status."""
    tasks = db.list_tasks(status)
    if not tasks:
        return "No tasks found"
    lines = []
    for t in tasks:
        line = f"#{t['id']} [{t['status']}] {t['title']}"
        if t.get("details"):
            line += f" — {t['details']}"
        if t.get("blocker"):
            line += f" (BLOCKED: {t['blocker']})"
        lines.append(line)
    return "\n".join(lines)


# ── Settings ────────────────────────────────────────────────────────────────

@mcp.tool
def add_setting(key: str, value: str, citation: str = None) -> str:
    """Record or update a hyperparameter anchor with optional provenance citation."""
    db.add_setting(key, value, citation)
    _auto_render()
    return f"Setting '{key}' = '{value}'"


# ── Canon ───────────────────────────────────────────────────────────────────

@mcp.tool
def add_canon(claim: str, verdict: str, evidence: str, tags: str = None) -> str:
    """Record a settled finding. verdict: yes | no | mixed | inconclusive"""
    cid = db.add_canon(claim, verdict, evidence, tags)
    _auto_render()
    return f"Canon #{cid} added: [{verdict.upper()}] {claim}"


# ── Dispositions ────────────────────────────────────────────────────────────

@mcp.tool
def add_disposition(slug: str, title: str, body: str, tags: str = None) -> str:
    """Record a detailed experiment writeup. slug is the filename (auto-generated if empty)."""
    did = db.add_disposition(slug, title, body, tags)
    _auto_render()
    return f"Disposition #{did} added: {title}"


# ── Query ───────────────────────────────────────────────────────────────────

@mcp.tool
def query_specs(type: str = None, status: str = None, query: str = None) -> str:
    """Search across all spec tables. Filter by type (requirements/decisions/tasks/settings/canon/dispositions), status, or free text."""
    results = db.query_specs(type, status, query)
    if not results:
        return "No results found"
    lines = []
    for r in results[:20]:  # cap output
        table = r.pop("_table", "?")
        title = r.get("title") or r.get("claim") or r.get("key") or "?"
        lines.append(f"[{table}] {title}")
    if len(results) > 20:
        lines.append(f"... and {len(results) - 20} more")
    return "\n".join(lines)


# ── Render ──────────────────────────────────────────────────────────────────

@mcp.tool
def render() -> str:
    """Force re-render all markdown from the DB."""
    stats = _auto_render()
    return f"Rendered: {stats}"


# ── Health ──────────────────────────────────────────────────────────────────

from starlette.requests import Request
from starlette.responses import JSONResponse


@mcp.custom_route("/health", methods=["GET"])
async def health(_: Request) -> JSONResponse:
    return JSONResponse({
        "status": "ok",
        "db": str(DB_PATH),
        "tables": ["requirements", "decisions", "tasks", "settings", "canon", "dispositions"],
    })


# ── Main ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Specs MCP server")
    parser.add_argument("--port", type=int, default=8057, help="HTTP port (default: 8057)")
    args = parser.parse_args()

    mcp.run(transport="streamable-http", host="127.0.0.1", port=args.port)
