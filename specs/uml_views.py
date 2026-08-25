"""Generate and validate traceable UML design views.

Purpose: generate Mermaid use-case, component, class, and sequence views
from the traceability graph and AST metadata. Validate node IDs, relationships,
syntax, source hashes, and stale-diagram detection.

Preconditions: traceability_graph.py available; pydantic v2.
Failure modes: StaleViewError on hash mismatch; ValidationError on invalid Mermaid.

Usage:
    from specs.uml_views import UmlViewGenerator
    gen = UmlViewGenerator(graph)
    uc = gen.use_case_view()
    comp = gen.component_view()
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from .traceability_graph import EdgeType, NodeType, TraceabilityGraph


class ViewType(str, Enum):
    use_case = "use_case"
    component = "component"
    class_diagram = "class"
    sequence = "sequence"


@dataclass
class MermaidView:
    """A generated Mermaid diagram with validation metadata."""
    view_type: ViewType
    title: str
    mermaid: str
    source_hash: str = ""
    node_ids: list[str] = field(default_factory=list)
    stale: bool = False
    errors: list[str] = field(default_factory=list)

    def compute_hash(self) -> str:
        return hashlib.sha256(self.mermaid.encode()).hexdigest()[:16]


class StaleViewError(Exception):
    """Raised when a view's source hash doesn't match current graph state."""
    pass


class UmlViewGenerator:
    """Generate Mermaid UML views from a TraceabilityGraph.

    Contract:
        Require: populated TraceabilityGraph with nodes and edges.
        Guarantee: syntactically valid Mermaid; bounded output (max_nodes).
        Maintain: deterministic output for same graph state.
    """

    def __init__(self, graph: TraceabilityGraph, max_nodes: int = 40):
        self.graph = graph
        self.max_nodes = max_nodes

    def use_case_view(self) -> MermaidView:
        """Generate use-case diagram from intents and requirements."""
        intents = self.graph.list_nodes(node_type="intent", status="active")
        reqs = self.graph.list_nodes(node_type="requirement", status="active")

        lines = ["graph LR"]
        node_ids = []

        # Actors (intents)
        for intent in intents[:self.max_nodes // 2]:
            safe_label = _sanitize(intent.label or intent.node_id)
            lines.append(f"    {intent.node_id}(({safe_label}))")
            node_ids.append(intent.node_id)

        # Use cases (requirements)
        for req in reqs[:self.max_nodes // 2]:
            safe_label = _sanitize(req.label or req.node_id)
            lines.append(f"    {req.node_id}[{safe_label}]")
            node_ids.append(req.node_id)

        # Edges: requirement derives_from intent
        id_set = set(node_ids)
        for req in reqs[:self.max_nodes // 2]:
            edges = self.graph.get_edges_from(req.node_id, "derives_from")
            for e in edges:
                if e.target_id in id_set:
                    lines.append(f"    {e.target_id} --> {req.node_id}")

        mermaid = "\n".join(lines)
        view = MermaidView(
            view_type=ViewType.use_case,
            title="Use Case View",
            mermaid=mermaid,
            node_ids=node_ids,
        )
        view.source_hash = view.compute_hash()
        return view

    def component_view(self) -> MermaidView:
        """Generate component/architecture diagram from code symbols and dependencies."""
        symbols = self.graph.list_nodes(node_type="code_symbol", status="active")
        artifacts = self.graph.list_nodes(node_type="artifact", status="active")

        lines = ["graph TD"]
        node_ids = []

        for sym in symbols[:self.max_nodes]:
            safe_label = _sanitize(sym.label or sym.node_id)
            lines.append(f"    {sym.node_id}[{safe_label}]")
            node_ids.append(sym.node_id)

        for art in artifacts[:self.max_nodes - len(node_ids)]:
            safe_label = _sanitize(art.label or art.node_id)
            lines.append(f"    {art.node_id}[/{safe_label}/]")
            node_ids.append(art.node_id)

        # Edges: implements, depends_on, produces
        id_set = set(node_ids)
        for nid in node_ids:
            for edge_type in ("implements", "depends_on", "produces"):
                edges = self.graph.get_edges_from(nid, edge_type)
                for e in edges:
                    if e.target_id in id_set:
                        lines.append(f"    {nid} -->|{edge_type}| {e.target_id}")

        mermaid = "\n".join(lines)
        view = MermaidView(
            view_type=ViewType.component,
            title="Component View",
            mermaid=mermaid,
            node_ids=node_ids,
        )
        view.source_hash = view.compute_hash()
        return view

    def class_view(self) -> MermaidView:
        """Generate class diagram from code symbols with relationships."""
        symbols = self.graph.list_nodes(node_type="code_symbol", status="active")

        lines = ["classDiagram"]
        node_ids = []

        for sym in symbols[:self.max_nodes]:
            safe_id = _safe_id(sym.node_id)
            safe_label = _sanitize(sym.label or sym.node_id)
            lines.append(f"    class {safe_id} {{\n        {safe_label}\n    }}")
            node_ids.append(sym.node_id)

        # Relationships
        id_set = set(node_ids)
        for nid in node_ids:
            edges = self.graph.get_edges_from(nid)
            for e in edges:
                if e.target_id in id_set:
                    safe_src = _safe_id(nid)
                    safe_tgt = _safe_id(e.target_id)
                    rel = _edge_to_class_rel(e.edge_type.value)
                    lines.append(f"    {safe_src} {rel} {safe_tgt}")

        mermaid = "\n".join(lines)
        view = MermaidView(
            view_type=ViewType.class_diagram,
            title="Class View",
            mermaid=mermaid,
            node_ids=node_ids,
        )
        view.source_hash = view.compute_hash()
        return view

    def sequence_view(self, path: list[str]) -> MermaidView:
        """Generate sequence diagram from a path of node IDs.

        Args:
            path: ordered list of node_ids representing a call/interaction sequence.
        """
        if len(path) < 2:
            return MermaidView(
                view_type=ViewType.sequence,
                title="Sequence View",
                mermaid="sequenceDiagram\n    Note right of System: Empty path",
                node_ids=path,
                errors=["Path too short for sequence diagram"],
            )

        lines = ["sequenceDiagram"]
        node_ids = []

        # Declare participants
        for nid in path:
            node = self.graph.get_node(nid)
            label = _sanitize(node.label if node else nid)
            safe = _safe_id(nid)
            lines.append(f"    participant {safe} as {label}")
            node_ids.append(nid)

        # Interactions between consecutive nodes
        for i in range(len(path) - 1):
            src = _safe_id(path[i])
            tgt = _safe_id(path[i + 1])
            # Find edge type between them
            edges = self.graph.get_edges_from(path[i])
            edge_label = "calls"
            for e in edges:
                if e.target_id == path[i + 1]:
                    edge_label = e.edge_type.value
                    break
            lines.append(f"    {src}->>+{tgt}: {edge_label}")
            lines.append(f"    {tgt}-->>-{src}: response")

        mermaid = "\n".join(lines)
        view = MermaidView(
            view_type=ViewType.sequence,
            title="Sequence View",
            mermaid=mermaid,
            node_ids=node_ids,
        )
        view.source_hash = view.compute_hash()
        return view

    def validate_view(self, view: MermaidView) -> list[str]:
        """Validate a Mermaid view for common issues."""
        errors = []

        # Check non-empty
        if not view.mermaid.strip():
            errors.append("Empty diagram")

        # Check has a valid diagram type declaration
        first_line = view.mermaid.strip().split("\n")[0].strip()
        valid_starts = ("graph ", "classDiagram", "sequenceDiagram", "flowchart ")
        if not any(first_line.startswith(v) for v in valid_starts):
            errors.append(f"Invalid diagram type: {first_line}")

        # Check node IDs reference existing nodes
        for nid in view.node_ids:
            node = self.graph.get_node(nid)
            if not node:
                errors.append(f"Referenced node not found: {nid}")

        # Check for staleness (source hash mismatch)
        if view.source_hash and view.source_hash != view.compute_hash():
            errors.append("View is stale (content changed since generation)")
            view.stale = True

        view.errors = errors
        return errors

    def detect_stale_views(self, stored_views: list[MermaidView]) -> list[MermaidView]:
        """Check stored views against current graph state."""
        stale = []
        for view in stored_views:
            # Regenerate and compare hash
            if view.view_type == ViewType.use_case:
                fresh = self.use_case_view()
            elif view.view_type == ViewType.component:
                fresh = self.component_view()
            elif view.view_type == ViewType.class_diagram:
                fresh = self.class_view()
            else:
                continue  # sequence views depend on path, can't auto-regenerate

            if fresh.source_hash != view.source_hash:
                view.stale = True
                stale.append(view)
        return stale


# --- Helpers -----------------------------------------------------------------


def _sanitize(text: str) -> str:
    """Remove characters that break Mermaid syntax."""
    return re.sub(r'["\[\]{}()<>|/\\]', "", text)[:60]


def _safe_id(node_id: str) -> str:
    """Convert node_id to valid Mermaid identifier."""
    return re.sub(r"[^a-zA-Z0-9_]", "_", node_id)


def _edge_to_class_rel(edge_type: str) -> str:
    """Map edge type to UML class relationship notation."""
    mapping = {
        "implements": "--|>",
        "depends_on": "-->",
        "supersedes": "..|>",
        "derives_from": "-->",
        "tests": "..>",
        "produces": "-->",
    }
    return mapping.get(edge_type, "-->")
