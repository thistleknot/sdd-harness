"""FastMCP server exposing global and workspace-scoped specification tools.

| Stage | Mechanism | Tag | Requirement |
|---|---|---|---|
| REGISTER | Register global and project-scoped tools before service startup | [mandatory] | R1 |
| STORE | Keep global CRUD on its configured DB; fix project DB at `<root>/.specs/reqs/requirements.db` | [mandatory] | R2 |
| INDEX | Register project artifact IDs and paths only after file containment checks | [mandatory] | R3 |
| RENDER | Auto-render global views after global mutations; project writes remain DB-only | [contract] | R4 |
| SERVE | Start streamable HTTP after tool registration | [mandatory] | R1 |

R1: WHEN the service starts, THEN every decorated tool MUST be registered before `mcp.run`.
R2: WHEN a project tool is called, its absolute existing workspace root MUST determine the database path; no arbitrary path or global DB is accepted.
R3: WHEN an artifact is indexed, its existing file MUST resolve inside that workspace's `.specs` tree.
R4: WHEN a project requirement is added, THEN no Markdown view is written into the workspace or global tracker.
R5: WHEN a project tool is advertised, THEN every input parameter MUST describe its meaning and accepted values.
R6: WHEN a project tool has a global counterpart, its description MUST state when to use each tool.

CLOSED: Project CRUD through global tools; evidence: their database is module-pinned and has no workspace parameter.
Preconditions: SpecsDB and FastMCP dependencies are installed; project root exists.
Failure modes: invalid roots and database/filesystem failures propagate; no project write falls back to the global DB.
"""
from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field

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

def _project_db(workspace_root: str) -> tuple[SpecsDB, Path]:
    """Open the registry fixed beneath one explicit project root.

    Require: workspace_root is an existing absolute directory supplied by the caller.
    Guarantee: the returned database is <root>/.specs/reqs/requirements.db.
    Failure modes: ValueError for invalid roots; filesystem and SQLite errors propagate.
    """
    root = Path(workspace_root)
    if not root.is_absolute() or not root.is_dir():
        raise ValueError("workspace_root must be an existing absolute directory")
    specs_root = (root / ".specs").resolve()
    reqs_root = specs_root / "reqs"
    reqs_root.mkdir(parents=True, exist_ok=True)
    db_path = (reqs_root / "requirements.db").resolve()
    if not db_path.is_relative_to(specs_root):
        raise ValueError("project registry path escapes .specs")
    return SpecsDB(db_path), db_path


@mcp.tool
def project_add_requirement(
    workspace_root: Annotated[str, Field(description="Absolute path to an existing project directory.")],
    title: Annotated[str, Field(description="Short, unique name for the requirement.")],
    criteria: Annotated[str, Field(description="Observable acceptance criteria for the requirement.")],
    priority: Annotated[Literal["must", "should", "could", "normal"], Field(description="Requirement priority.")] = "normal",
) -> str:
    """Add a requirement to the selected project's `.specs` SQLite registry. Use this for workspace-specific requirements; use global `add_requirement` only for the harness-wide registry.

    Args:
        workspace_root: Absolute path to an existing project directory.
        title: Short, unique name for the requirement.
        criteria: Observable acceptance criteria for the requirement.
        priority: Requirement priority: `must`, `should`, `could`, or `normal`.

    Returns:
        The assigned requirement ID and project registry path.

    Raises:
        ValueError: The project path is not absolute or does not exist.
        OSError: The project registry cannot be created or written.
    """
    project_db, db_path = _project_db(workspace_root)
    try:
        rid = project_db.add_requirement(title, criteria, priority)
        return f"Requirement #{rid} added to {db_path}: {title}"
    finally:
        project_db.close()


@mcp.tool
def project_query_requirements(
    workspace_root: Annotated[str, Field(description="Absolute path to an existing project directory.")],
    query: Annotated[str, Field(description="Optional text matched against requirement titles and criteria.")] = "",
) -> str:
    """Search requirements in one project's `.specs` SQLite registry. Use this when searching a project; global `query_specs` searches the harness registry.

    Args:
        workspace_root: Absolute path to an existing project directory.
        query: Optional text to match against requirement titles and criteria.

    Returns:
        Matching requirements with their IDs, statuses, titles, and criteria.

    Raises:
        ValueError: The project path is not absolute or does not exist.
        OSError: The project registry cannot be opened.
    """
    project_db, db_path = _project_db(workspace_root)
    try:
        rows = project_db.query_specs(type="requirements", query=query or None)
        if not rows:
            return f"No project requirements found in {db_path}"
        return "\n".join(f"#{row['id']} [{row['status']}] {row['title']}: {row['criteria']}" for row in rows)
    finally:
        project_db.close()


@mcp.tool
def project_register_artifact(
    workspace_root: Annotated[str, Field(description="Absolute path to an existing project directory.")],
    artifact_id: Annotated[str, Field(description="Stable ID used to reference this artifact in the registry.")],
    artifact_type: Annotated[str, Field(description="Artifact category, such as requirements or entity_model.")],
    relative_path: Annotated[str, Field(description="Project-relative path to an existing file under .specs.")],
) -> str:
    """Index an existing artifact contained in the project's `.specs` tree.

    Args:
        workspace_root: Absolute path to an existing project directory.
        artifact_id: Stable ID used to reference this artifact in the registry.
        artifact_type: Artifact category, such as `requirements` or `entity_model`.
        relative_path: Project-relative path to an existing file under `.specs`.

    Returns:
        Confirmation with the artifact ID and registered project-relative path.

    Raises:
        ValueError: The root is invalid or the artifact is missing or outside `.specs`.
        OSError: The project registry cannot be opened or written.
    """
    root = Path(workspace_root)
    if not root.is_absolute() or not root.is_dir():
        raise ValueError("workspace_root must be an existing absolute directory")
    specs_root = (root / ".specs").resolve()
    artifact = (root / relative_path).resolve()
    if not artifact.is_relative_to(specs_root) or not artifact.is_file():
        raise ValueError("artifact must be an existing file inside workspace .specs")
    project_db, db_path = _project_db(workspace_root)
    try:
        project_db.conn.execute("CREATE TABLE IF NOT EXISTS artifacts (artifact_id TEXT PRIMARY KEY, artifact_type TEXT NOT NULL, relative_path TEXT NOT NULL, updated_at TEXT NOT NULL)")
        project_db.conn.execute("INSERT INTO artifacts VALUES (?, ?, ?, datetime('now')) ON CONFLICT(artifact_id) DO UPDATE SET artifact_type=excluded.artifact_type, relative_path=excluded.relative_path, updated_at=excluded.updated_at", (artifact_id, artifact_type, str(artifact.relative_to(root))))
        project_db.conn.commit()
        return f"Artifact {artifact_id} indexed in {db_path}: {artifact.relative_to(root)}"
    finally:
        project_db.close()

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


# ── Failure Registry ────────────────────────────────────────────────────────

@mcp.tool
def add_failure(approach: str, evidence: str, context: str = None,
                error_class: str = None, falsifies: str = None,
                conditions: str = None) -> str:
    """Record a failed approach. Deduplicates by structural signature.

    approach: what was tried (the technique/method/library/pattern)
    evidence: what happened (error, outcome, measurements)
    context: under what conditions (optional — project, environment, constraints)
    error_class: category of failure (optional — e.g. 'type_error', 'perf_regression', 'incompatible')
    falsifies: what hypothesis this disproves (optional — ties to the hypothesis system)
    conditions: when this failure applies (optional — e.g. 'Windows only', 'Python <3.11')
    """
    fid = db.add_failure(approach, evidence, context, error_class, falsifies, conditions)
    _auto_render()
    return f"Failure #{fid} recorded: {approach}"


@mcp.tool
def check_failures(approach: str) -> str:
    """Check if an approach matches a known dead end. Use before starting work.

    Returns matching failures if the approach signature has been seen before.
    Empty result = no known blockers, proceed.
    """
    matches = db.check_failures(approach)
    if not matches:
        return "No known failures for this approach. Proceed."
    lines = ["KNOWN DEAD ENDS matching this approach:"]
    for f in matches:
        obs = f" (observed {f['observations']}x)" if f['observations'] > 1 else ""
        lines.append(f"\n#{f['id']}{obs}: {f['approach']}")
        lines.append(f"  Evidence: {f['evidence']}")
        if f["conditions"]:
            lines.append(f"  Conditions: {f['conditions']}")
        if f["falsifies"]:
            lines.append(f"  Falsifies: {f['falsifies']}")
    lines.append("\nDo NOT retry this approach unless conditions have changed.")
    return "\n".join(lines)


@mcp.tool
def list_failures(status: str = None) -> str:
    """List recorded failure signatures. status: dead | conditional | revived"""
    failures = db.list_failures(status)
    if not failures:
        return "No failures recorded"
    lines = []
    for f in failures:
        obs = f" (×{f['observations']})" if f['observations'] > 1 else ""
        lines.append(f"#{f['id']} [{f['status']}]{obs} {f['approach']}")
        if f.get("error_class"):
            lines.append(f"    error_class: {f['error_class']}")
    return "\n".join(lines)


@mcp.tool
def revive_failure(id: int, reason: str) -> str:
    """Mark a dead-end as revived (conditions changed, approach viable again)."""
    db.revive_failure(id, reason)
    _auto_render()
    return f"Failure #{id} revived: {reason}"


# ── Dispositions ────────────────────────────────────────────────────────────

@mcp.tool
def add_disposition(slug: str, title: str, body: str, tags: str = None) -> str:
    """Record a detailed experiment writeup. slug is the filename (auto-generated if empty)."""
    did = db.add_disposition(slug, title, body, tags)
    _auto_render()
    return f"Disposition #{did} added: {title}"


# ── Future directions ───────────────────────────────────────────────────────

@mcp.tool
def add_future_direction(title: str, rationale: str, trigger: str = None,
                         scope: str = "harness", tags: str = None) -> str:
    """Record uncommitted work worth revisiting later.

    NOT a task: a future direction has no owner and no ETA. If it has either, use
    add_task instead.

    trigger: the condition that would promote this to real work ("revisit when a
             second repo accumulates entries"). Without one it never gets revisited.
    scope:   'harness', or 'repo:<name>' for a direction belonging to another project.
    """
    fid = db.add_future_direction(title, rationale, trigger, scope, tags)
    warn = "" if trigger else "  WARNING: no trigger — this will never surface on its own."
    _auto_render()
    return f"Future direction #{fid} added: {title}{warn}"


@mcp.tool
def update_future_direction(id: int, title: str = None, rationale: str = None,
                            trigger: str = None, scope: str = None,
                            status: str = None, promoted_to: str = None,
                            tags: str = None) -> str:
    """Transition a future direction. status: open | promoted | dropped

    When promoting, pass promoted_to with the task or requirement that now owns it
    (e.g. 'task #59'). Directions are transitioned, never deleted.
    """
    db.update_future_direction(id, title=title, rationale=rationale, trigger=trigger,
                               scope=scope, status=status, promoted_to=promoted_to, tags=tags)
    _auto_render()
    return f"Future direction #{id} updated"


# ── Query ───────────────────────────────────────────────────────────────────

@mcp.tool
def query_specs(type: str = None, status: str = None, query: str = None) -> str:
    """Search across all spec tables. Filter by type (requirements/decisions/tasks/settings/canon/dispositions/failures/future_directions), status, or free text."""
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
        "tables": ["requirements", "decisions", "tasks", "settings", "canon", "dispositions", "failures"],
    })


# ── Main ────────────────────────────────────────────────────────────────────



# ── Tech Debt ───────────────────────────────────────────────────────────────

@mcp.tool
def add_tech_debt(title: str, severity: str = "warn", details: str = None) -> str:
    """Track a tech debt item. severity: info | warn | block"""
    tid = db.add_task(title, "planned", details=f"[TECH_DEBT:{severity}] {details or ''}")
    _auto_render()
    return f"Tech debt #{tid} added: {title} [{severity}]"


@mcp.tool
def list_tech_debt() -> str:
    """List all tech debt items (tasks tagged TECH_DEBT)."""
    tasks = db.list_tasks()
    debt = [t for t in tasks if "TECH_DEBT" in (t.get("details") or "")]
    if not debt:
        return "No tech debt tracked"
    lines = []
    for t in debt:
        lines.append(f"#{t['id']} [{t['status']}] {t['title']}")
    return "\n".join(lines)


# ── Hooks ───────────────────────────────────────────────────────────────────

import json


@mcp.tool
def list_hooks(workspace_root: str = None) -> str:
    """List all agent hooks in .kiro/hooks/."""
    hooks_dir = Path(workspace_root or HERE.parent) / ".kiro" / "hooks"
    if not hooks_dir.exists():
        return "No hooks directory found"
    hooks = []
    for f in hooks_dir.glob("*.json"):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            for h in data.get("hooks", []):
                hooks.append(f"{f.stem}: {h.get('name', '?')} [{h.get('trigger', '?')}]")
        except Exception:
            hooks.append(f"{f.stem}: (parse error)")
    return "\n".join(hooks) if hooks else "No hooks found"


@mcp.tool
def create_hook(hook_id: str, name: str, trigger: str, action_type: str,
                command: str = None, prompt: str = None, matcher: str = None) -> str:
    """Create a .kiro/hooks/<hook_id>.json file.

    trigger: PreToolUse | PostToolUse | SessionStart | Stop | PostFileSave | PostFileCreate | PostFileDelete | PostTaskExec
    action_type: command | agent
    """
    hooks_dir = Path(HERE.parent) / ".kiro" / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)
    hook_file = hooks_dir / f"{hook_id}.json"

    action = {"type": action_type}
    if action_type == "command" and command:
        action["command"] = command
    elif action_type == "agent" and prompt:
        action["prompt"] = prompt

    hook_def = {"name": name, "trigger": trigger, "action": action}
    if matcher:
        hook_def["matcher"] = matcher

    payload = {"version": "v1", "hooks": [hook_def]}
    hook_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return f"Hook created: {hook_file}"


# ── Steering ────────────────────────────────────────────────────────────────

@mcp.tool
def list_steering(workspace_root: str = None) -> str:
    """List all steering files in .kiro/steering/."""
    steer_dir = Path(workspace_root or HERE.parent) / ".kiro" / "steering"
    if not steer_dir.exists():
        return "No steering directory found"
    files = list(steer_dir.glob("*.md"))
    if not files:
        return "No steering files"
    return "\n".join(f"- {f.name} ({f.stat().st_size} bytes)" for f in sorted(files))


@mcp.tool
def read_steering(filename: str, workspace_root: str = None) -> str:
    """Read the content of a steering file."""
    steer_dir = Path(workspace_root or HERE.parent) / ".kiro" / "steering"
    path = steer_dir / filename
    if not path.exists():
        return f"Steering file not found: {filename}"
    return path.read_text(encoding="utf-8")


@mcp.tool
def write_steering(filename: str, content: str, workspace_root: str = None) -> str:
    """Create or update a steering file in .kiro/steering/."""
    steer_dir = Path(workspace_root or HERE.parent) / ".kiro" / "steering"
    steer_dir.mkdir(parents=True, exist_ok=True)
    path = steer_dir / filename
    path.write_text(content, encoding="utf-8")
    return f"Steering written: {path} ({len(content)} chars)"


# ── UML Views ───────────────────────────────────────────────────────────────

@mcp.tool
def generate_uml(view_type: str = "use_case") -> str:
    """Generate a Mermaid UML diagram from the traceability graph.

    view_type: use_case | component | class
    """
    try:
        from traceability_graph import TraceabilityGraph
        from uml_views import UmlViewGenerator
    except ImportError:
        return "Error: traceability_graph or uml_views not importable from specs dir"

    graph = TraceabilityGraph(str(DB_PATH))
    gen = UmlViewGenerator(graph)

    if view_type == "use_case":
        view = gen.use_case_view()
    elif view_type == "component":
        view = gen.component_view()
    elif view_type == "class":
        view = gen.class_view()
    else:
        graph.close()
        return f"Unknown view_type: {view_type}. Use: use_case, component, class"

    result = view.mermaid
    graph.close()
    return result


# ── Traceability Graph ──────────────────────────────────────────────────────

@mcp.tool
def graph_add_node(node_type: str, node_id: str, label: str = "",
                   source_hash: str = "") -> str:
    """Add a node to the traceability graph.

    node_type: intent | requirement | decision | task | code_symbol | test | evidence | anomaly | artifact
    """
    try:
        from traceability_graph import TraceabilityGraph
    except ImportError:
        return "Error: traceability_graph not importable"
    graph = TraceabilityGraph(str(DB_PATH))
    try:
        graph.add_node(node_type, node_id, label=label, source_hash=source_hash)
        graph.close()
        return f"Node added: {node_id} [{node_type}]"
    except Exception as e:
        graph.close()
        return f"Error: {e}"


@mcp.tool
def graph_add_edge(source_id: str, target_id: str, edge_type: str) -> str:
    """Add an edge to the traceability graph.

    edge_type: implements | tests | evidences | supersedes | depends_on | derives_from | produces | validates | blocks
    """
    try:
        from traceability_graph import TraceabilityGraph
    except ImportError:
        return "Error: traceability_graph not importable"
    graph = TraceabilityGraph(str(DB_PATH))
    try:
        graph.add_edge(source_id, target_id, edge_type)
        graph.close()
        return f"Edge added: {source_id} --{edge_type}--> {target_id}"
    except Exception as e:
        graph.close()
        return f"Error: {e}"


@mcp.tool
def graph_impact(node_id: str, max_depth: int = 3) -> str:
    """Query change-impact: what nodes are affected by a change to node_id."""
    try:
        from traceability_graph import TraceabilityGraph
    except ImportError:
        return "Error: traceability_graph not importable"
    graph = TraceabilityGraph(str(DB_PATH))
    result = graph.change_impact(node_id, max_depth)
    graph.close()
    if not result.affected_nodes:
        return f"No impact from {node_id} (isolated node)"
    return f"Impact from {node_id}: {len(result.affected_nodes)} affected nodes\n" + "\n".join(f"  - {n}" for n in result.affected_nodes)


@mcp.tool
def graph_stats() -> str:
    """Return traceability graph statistics."""
    try:
        from traceability_graph import TraceabilityGraph
    except ImportError:
        return "Error: traceability_graph not importable"
    graph = TraceabilityGraph(str(DB_PATH))
    s = graph.stats()
    graph.close()
    return f"Nodes: {s['total_nodes']}, Edges: {s['total_edges']}, By type: {s['nodes_by_type']}"

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Specs MCP server")
    parser.add_argument("--port", type=int, default=8057, help="HTTP port (default: 8057)")
    args = parser.parse_args()

    mcp.run(transport="streamable-http", host="127.0.0.1", port=args.port, stateless_http=True)
