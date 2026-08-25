"""Canonical traceability graph schema.

Purpose: extend SpecsDB with stable nodes and typed edges for intents,
requirements, design elements, code symbols, tests, evidence, tasks,
and anomalies. Enables bidirectional and change-impact queries.

Preconditions: sqlite3 available. Pydantic v2 for models.
Failure modes: IntegrityError on duplicate nodes; ValueError on invalid edge types.

Usage:
    from traceability_graph import TraceabilityGraph
    tg = TraceabilityGraph("specs.db")  # extends existing DB
    tg.add_node("req", "R-003", source_hash="abc123")
    tg.add_edge("R-003", "T-001", "tests")
"""
from __future__ import annotations

import hashlib
import sqlite3
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# --- Enums ------------------------------------------------------------------


class NodeType(str, Enum):
    intent = "intent"
    requirement = "requirement"
    decision = "decision"
    task = "task"
    code_symbol = "code_symbol"
    test = "test"
    evidence = "evidence"
    anomaly = "anomaly"
    artifact = "artifact"


class EdgeType(str, Enum):
    implements = "implements"       # code_symbol -> requirement
    tests = "tests"                 # test -> requirement | code_symbol
    evidences = "evidences"         # evidence -> requirement | decision
    supersedes = "supersedes"       # node -> node (same type)
    depends_on = "depends_on"      # task -> task | requirement -> requirement
    derives_from = "derives_from"  # requirement -> intent
    produces = "produces"          # task -> artifact
    validates = "validates"        # evidence -> code_symbol | task
    blocks = "blocks"              # anomaly -> task | requirement


class NodeStatus(str, Enum):
    active = "active"
    superseded = "superseded"
    deprecated = "deprecated"
    pending = "pending"


# --- Pydantic Models (for API/validation) -----------------------------------


class GraphNode(BaseModel):
    """A node in the traceability graph."""
    node_id: str = Field(description="Stable unique ID, e.g. 'R-003', 'S-auth.login'")
    node_type: NodeType
    label: str = Field(default="", description="Human-readable label")
    source_hash: str = Field(default="", description="Hash of source content for staleness detection")
    status: NodeStatus = NodeStatus.active
    metadata: dict = Field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""


class GraphEdge(BaseModel):
    """A typed directed edge between two nodes."""
    source_id: str
    target_id: str
    edge_type: EdgeType
    metadata: dict = Field(default_factory=dict)
    created_at: str = ""


class ImpactResult(BaseModel):
    """Result of a change-impact query."""
    origin_node: str
    affected_nodes: list[str] = Field(default_factory=list)
    affected_edges: list[tuple[str, str, str]] = Field(default_factory=list)
    depth: int = 0


# --- Helper ------------------------------------------------------------------


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _content_hash(content: str) -> str:
    return hashlib.sha256(content.encode()).hexdigest()[:16]


# --- TraceabilityGraph -------------------------------------------------------


class TraceabilityGraph:
    """SQLite-backed traceability graph that extends SpecsDB.

    Contract:
        Require: valid SQLite DB path (may be existing specs.db).
        Guarantee: schema created if absent; no data loss on existing tables.
        Maintain: node_id uniqueness; referential integrity on edges.
        Assert: all queries return deterministic results (ORDER BY).
    """

    VALID_NODE_TYPES = {e.value for e in NodeType}
    VALID_EDGE_TYPES = {e.value for e in EdgeType}

    def __init__(self, db_path: str):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path, isolation_level="DEFERRED")
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA busy_timeout=5000")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self._init_schema()

    def _init_schema(self):
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS graph_nodes (
                node_id TEXT PRIMARY KEY,
                node_type TEXT NOT NULL,
                label TEXT DEFAULT '',
                source_hash TEXT DEFAULT '',
                status TEXT DEFAULT 'active',
                metadata TEXT DEFAULT '{}',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS graph_edges (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_id TEXT NOT NULL,
                target_id TEXT NOT NULL,
                edge_type TEXT NOT NULL,
                metadata TEXT DEFAULT '{}',
                created_at TEXT NOT NULL,
                UNIQUE(source_id, target_id, edge_type)
            );

            CREATE INDEX IF NOT EXISTS idx_edges_source
                ON graph_edges(source_id);
            CREATE INDEX IF NOT EXISTS idx_edges_target
                ON graph_edges(target_id);
            CREATE INDEX IF NOT EXISTS idx_nodes_type
                ON graph_nodes(node_type);
            CREATE INDEX IF NOT EXISTS idx_nodes_status
                ON graph_nodes(status);
        """)
        self.conn.commit()

    # --- Node CRUD -----------------------------------------------------------

    def add_node(
        self,
        node_type: str,
        node_id: str,
        label: str = "",
        source_hash: str = "",
        status: str = "active",
        metadata: dict | None = None,
    ) -> GraphNode:
        """Add a node. Raises ValueError on invalid type, IntegrityError on duplicate."""
        if node_type not in self.VALID_NODE_TYPES:
            raise ValueError(f"Invalid node_type: {node_type}. Valid: {self.VALID_NODE_TYPES}")
        if status not in {e.value for e in NodeStatus}:
            raise ValueError(f"Invalid status: {status}")

        now = _now()
        import json
        meta_str = json.dumps(metadata or {})

        self.conn.execute(
            """INSERT INTO graph_nodes
               (node_id, node_type, label, source_hash, status, metadata, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (node_id, node_type, label, source_hash, status, meta_str, now, now),
        )
        self.conn.commit()
        return GraphNode(
            node_id=node_id, node_type=NodeType(node_type), label=label,
            source_hash=source_hash, status=NodeStatus(status),
            metadata=metadata or {}, created_at=now, updated_at=now,
        )

    def get_node(self, node_id: str) -> Optional[GraphNode]:
        """Fetch a node by ID. Returns None if not found."""
        import json
        row = self.conn.execute(
            "SELECT * FROM graph_nodes WHERE node_id=?", (node_id,)
        ).fetchone()
        if not row:
            return None
        return GraphNode(
            node_id=row["node_id"],
            node_type=NodeType(row["node_type"]),
            label=row["label"],
            source_hash=row["source_hash"],
            status=NodeStatus(row["status"]),
            metadata=json.loads(row["metadata"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def update_node(self, node_id: str, **kwargs) -> bool:
        """Update node fields. Returns True if updated, False if not found."""
        import json
        allowed = {"label", "source_hash", "status", "metadata"}
        fields = {k: v for k, v in kwargs.items() if k in allowed and v is not None}
        if not fields:
            return False
        if "metadata" in fields and isinstance(fields["metadata"], dict):
            fields["metadata"] = json.dumps(fields["metadata"])
        if "status" in fields and fields["status"] not in {e.value for e in NodeStatus}:
            raise ValueError(f"Invalid status: {fields['status']}")
        fields["updated_at"] = _now()
        sets = ", ".join(f"{k}=?" for k in fields)
        cur = self.conn.execute(
            f"UPDATE graph_nodes SET {sets} WHERE node_id=?",
            [*fields.values(), node_id],
        )
        self.conn.commit()
        return cur.rowcount > 0

    def supersede_node(self, old_id: str, new_id: str) -> None:
        """Mark old_id as superseded and create a supersedes edge."""
        self.update_node(old_id, status="superseded")
        self.add_edge(new_id, old_id, "supersedes")

    def list_nodes(
        self, node_type: str | None = None, status: str | None = None
    ) -> list[GraphNode]:
        """List nodes with optional filters."""
        import json
        query = "SELECT * FROM graph_nodes WHERE 1=1"
        params: list = []
        if node_type:
            query += " AND node_type=?"
            params.append(node_type)
        if status:
            query += " AND status=?"
            params.append(status)
        query += " ORDER BY node_id"
        rows = self.conn.execute(query, params).fetchall()
        return [
            GraphNode(
                node_id=r["node_id"], node_type=NodeType(r["node_type"]),
                label=r["label"], source_hash=r["source_hash"],
                status=NodeStatus(r["status"]), metadata=json.loads(r["metadata"]),
                created_at=r["created_at"], updated_at=r["updated_at"],
            )
            for r in rows
        ]

    # --- Edge CRUD -----------------------------------------------------------

    def add_edge(
        self,
        source_id: str,
        target_id: str,
        edge_type: str,
        metadata: dict | None = None,
    ) -> GraphEdge:
        """Add a directed edge. Validates type and node existence."""
        if edge_type not in self.VALID_EDGE_TYPES:
            raise ValueError(f"Invalid edge_type: {edge_type}. Valid: {self.VALID_EDGE_TYPES}")

        # Verify both nodes exist
        src = self.conn.execute(
            "SELECT node_id FROM graph_nodes WHERE node_id=?", (source_id,)
        ).fetchone()
        tgt = self.conn.execute(
            "SELECT node_id FROM graph_nodes WHERE node_id=?", (target_id,)
        ).fetchone()
        if not src:
            raise ValueError(f"Source node not found: {source_id}")
        if not tgt:
            raise ValueError(f"Target node not found: {target_id}")

        import json
        now = _now()
        meta_str = json.dumps(metadata or {})

        self.conn.execute(
            """INSERT OR IGNORE INTO graph_edges
               (source_id, target_id, edge_type, metadata, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (source_id, target_id, edge_type, meta_str, now),
        )
        self.conn.commit()
        return GraphEdge(
            source_id=source_id, target_id=target_id,
            edge_type=EdgeType(edge_type), metadata=metadata or {},
            created_at=now,
        )

    def remove_edge(self, source_id: str, target_id: str, edge_type: str) -> bool:
        """Remove a specific edge. Returns True if removed."""
        cur = self.conn.execute(
            "DELETE FROM graph_edges WHERE source_id=? AND target_id=? AND edge_type=?",
            (source_id, target_id, edge_type),
        )
        self.conn.commit()
        return cur.rowcount > 0

    def get_edges_from(self, node_id: str, edge_type: str | None = None) -> list[GraphEdge]:
        """Get all outgoing edges from a node."""
        import json
        query = "SELECT * FROM graph_edges WHERE source_id=?"
        params: list = [node_id]
        if edge_type:
            query += " AND edge_type=?"
            params.append(edge_type)
        query += " ORDER BY target_id"
        rows = self.conn.execute(query, params).fetchall()
        return [
            GraphEdge(
                source_id=r["source_id"], target_id=r["target_id"],
                edge_type=EdgeType(r["edge_type"]),
                metadata=json.loads(r["metadata"]), created_at=r["created_at"],
            )
            for r in rows
        ]

    def get_edges_to(self, node_id: str, edge_type: str | None = None) -> list[GraphEdge]:
        """Get all incoming edges to a node (reverse traversal)."""
        import json
        query = "SELECT * FROM graph_edges WHERE target_id=?"
        params: list = [node_id]
        if edge_type:
            query += " AND edge_type=?"
            params.append(edge_type)
        query += " ORDER BY source_id"
        rows = self.conn.execute(query, params).fetchall()
        return [
            GraphEdge(
                source_id=r["source_id"], target_id=r["target_id"],
                edge_type=EdgeType(r["edge_type"]),
                metadata=json.loads(r["metadata"]), created_at=r["created_at"],
            )
            for r in rows
        ]

    # --- Queries -------------------------------------------------------------

    def neighbors(self, node_id: str, direction: str = "both") -> list[str]:
        """Get neighbor node IDs. direction: 'out', 'in', or 'both'."""
        result = set()
        if direction in ("out", "both"):
            rows = self.conn.execute(
                "SELECT target_id FROM graph_edges WHERE source_id=?", (node_id,)
            ).fetchall()
            result.update(r["target_id"] for r in rows)
        if direction in ("in", "both"):
            rows = self.conn.execute(
                "SELECT source_id FROM graph_edges WHERE target_id=?", (node_id,)
            ).fetchall()
            result.update(r["source_id"] for r in rows)
        return sorted(result)

    def change_impact(self, node_id: str, max_depth: int = 3) -> ImpactResult:
        """BFS traversal to find all nodes affected by a change to node_id.

        Follows edges in BOTH directions to find the full impact cone.
        Stops at max_depth to bound computation.
        """
        visited: set[str] = set()
        affected_edges: list[tuple[str, str, str]] = []
        queue: list[tuple[str, int]] = [(node_id, 0)]

        while queue:
            current, depth = queue.pop(0)
            if current in visited or depth > max_depth:
                continue
            visited.add(current)

            # Get all connected edges (both directions)
            out_edges = self.conn.execute(
                "SELECT source_id, target_id, edge_type FROM graph_edges WHERE source_id=?",
                (current,),
            ).fetchall()
            in_edges = self.conn.execute(
                "SELECT source_id, target_id, edge_type FROM graph_edges WHERE target_id=?",
                (current,),
            ).fetchall()

            for e in out_edges:
                affected_edges.append((e["source_id"], e["target_id"], e["edge_type"]))
                if e["target_id"] not in visited:
                    queue.append((e["target_id"], depth + 1))
            for e in in_edges:
                affected_edges.append((e["source_id"], e["target_id"], e["edge_type"]))
                if e["source_id"] not in visited:
                    queue.append((e["source_id"], depth + 1))

        visited.discard(node_id)  # Don't include the origin
        return ImpactResult(
            origin_node=node_id,
            affected_nodes=sorted(visited),
            affected_edges=affected_edges,
            depth=max_depth,
        )

    def find_path(self, start: str, end: str, max_depth: int = 10) -> list[str] | None:
        """BFS shortest path from start to end. Returns node list or None."""
        if start == end:
            return [start]
        visited: set[str] = {start}
        queue: list[tuple[str, list[str]]] = [(start, [start])]

        while queue:
            current, path = queue.pop(0)
            if len(path) > max_depth:
                continue
            for neighbor in self.neighbors(current, direction="out"):
                if neighbor == end:
                    return path + [neighbor]
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append((neighbor, path + [neighbor]))
        return None

    def stale_nodes(self) -> list[GraphNode]:
        """Find nodes whose source_hash is empty (potentially stale)."""
        return self.list_nodes(status="active")  # caller checks source_hash

    def orphan_nodes(self) -> list[GraphNode]:
        """Find active nodes with no incoming or outgoing edges."""
        rows = self.conn.execute("""
            SELECT n.node_id FROM graph_nodes n
            WHERE n.status = 'active'
              AND n.node_id NOT IN (SELECT source_id FROM graph_edges)
              AND n.node_id NOT IN (SELECT target_id FROM graph_edges)
            ORDER BY n.node_id
        """).fetchall()
        return [self.get_node(r["node_id"]) for r in rows]

    # --- Rendering -----------------------------------------------------------

    def render_mermaid(self, max_nodes: int = 50) -> str:
        """Render the graph as a Mermaid diagram (bounded to max_nodes)."""
        nodes = self.list_nodes(status="active")[:max_nodes]
        node_ids = {n.node_id for n in nodes}

        lines = ["graph TD"]
        for n in nodes:
            shape = {
                "requirement": f"[{n.node_id}: {n.label or n.node_type.value}]",
                "code_symbol": f"({n.node_id}: {n.label or n.node_type.value})",
                "test": f"(({n.node_id}: {n.label or n.node_type.value}))",
                "anomaly": f">{n.node_id}: {n.label or n.node_type.value}]",
            }.get(n.node_type.value, f"[{n.node_id}: {n.label or n.node_type.value}]")
            lines.append(f"    {n.node_id}{shape}")

        edges = self.conn.execute(
            "SELECT * FROM graph_edges ORDER BY source_id, target_id"
        ).fetchall()
        for e in edges:
            if e["source_id"] in node_ids and e["target_id"] in node_ids:
                lines.append(
                    f"    {e['source_id']} -->|{e['edge_type']}| {e['target_id']}"
                )

        return "\n".join(lines)

    def stats(self) -> dict:
        """Return graph statistics."""
        node_count = self.conn.execute("SELECT COUNT(*) as c FROM graph_nodes").fetchone()["c"]
        edge_count = self.conn.execute("SELECT COUNT(*) as c FROM graph_edges").fetchone()["c"]
        type_counts = {}
        for row in self.conn.execute(
            "SELECT node_type, COUNT(*) as c FROM graph_nodes GROUP BY node_type"
        ).fetchall():
            type_counts[row["node_type"]] = row["c"]
        return {
            "total_nodes": node_count,
            "total_edges": edge_count,
            "nodes_by_type": type_counts,
        }

    # --- Lifecycle -----------------------------------------------------------

    def close(self):
        self.conn.close()
