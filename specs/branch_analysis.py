"""Branch efficiency and routing-hop locality analysis.

Purpose: extend traceability graph analysis with control-flow and call-path
metrics: conditional nesting, cyclomatic/cognitive complexity, branch fan-out,
routing-only hops, class/module boundary crossings, cycles, and root-to-outcome
path length. Classify nodes as domain work vs routing.

Preconditions: traceability_graph.py available; ast module for Python.
Failure modes: ValueError on invalid AST; cycles detected but not fatal.

Usage:
    from specs.branch_analysis import BranchAnalyzer, analyze_file
    analyzer = BranchAnalyzer()
    metrics = analyzer.analyze_source(source_code)
    graph_metrics = analyze_graph_paths(graph)
"""
from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .traceability_graph import TraceabilityGraph


# --- Metrics Models ----------------------------------------------------------


@dataclass
class FunctionMetrics:
    """Metrics for a single function/method."""
    name: str
    file_path: str
    line: int
    cyclomatic_complexity: int = 1
    cognitive_complexity: int = 0
    nesting_depth: int = 0
    branch_fan_out: int = 0
    is_routing_only: bool = False
    boundary_crossings: int = 0


@dataclass
class PathMetrics:
    """Metrics for a graph path analysis."""
    path: list[str] = field(default_factory=list)
    length: int = 0
    routing_hops: int = 0
    domain_hops: int = 0
    boundary_crossings: int = 0
    has_cycle: bool = False
    classification: str = ""  # "efficient", "routing-heavy", "ping-pong"


@dataclass
class FileMetrics:
    """Aggregated metrics for a file."""
    file_path: str
    functions: list[FunctionMetrics] = field(default_factory=list)
    max_complexity: int = 0
    avg_complexity: float = 0
    routing_ratio: float = 0  # fraction of functions that are routing-only
    total_fan_out: int = 0


# --- AST-Based Analysis ------------------------------------------------------


class BranchAnalyzer:
    """Analyze Python source for branch efficiency metrics.

    Contract:
        Require: valid Python source.
        Guarantee: one FunctionMetrics per function/method.
        Maintain: deterministic output for same source.
    """

    def analyze_file(self, file_path: str | Path) -> FileMetrics:
        """Analyze a Python file."""
        path = Path(file_path)
        if not path.exists():
            return FileMetrics(file_path=str(path))
        source = path.read_text(encoding="utf-8")
        return self.analyze_source(source, str(path))

    def analyze_source(self, source: str, file_path: str = "<string>") -> FileMetrics:
        """Analyze source code string."""
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return FileMetrics(file_path=file_path)

        functions: list[FunctionMetrics] = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                metrics = self._analyze_function(node, file_path)
                functions.append(metrics)

        # Aggregate
        complexities = [f.cyclomatic_complexity for f in functions]
        routing_count = sum(1 for f in functions if f.is_routing_only)

        return FileMetrics(
            file_path=file_path,
            functions=functions,
            max_complexity=max(complexities) if complexities else 0,
            avg_complexity=sum(complexities) / len(complexities) if complexities else 0,
            routing_ratio=routing_count / len(functions) if functions else 0,
            total_fan_out=sum(f.branch_fan_out for f in functions),
        )

    def _analyze_function(self, node: ast.FunctionDef, file_path: str) -> FunctionMetrics:
        """Compute metrics for a single function."""
        cc = self._cyclomatic_complexity(node)
        cognitive = self._cognitive_complexity(node)
        nesting = self._max_nesting(node)
        fan_out = self._branch_fan_out(node)
        is_routing = self._is_routing_only(node)

        return FunctionMetrics(
            name=node.name,
            file_path=file_path,
            line=node.lineno,
            cyclomatic_complexity=cc,
            cognitive_complexity=cognitive,
            nesting_depth=nesting,
            branch_fan_out=fan_out,
            is_routing_only=is_routing,
        )

    def _cyclomatic_complexity(self, node: ast.AST) -> int:
        """Count decision points (if, for, while, except, and, or, ternary)."""
        cc = 1  # base path
        for child in ast.walk(node):
            if isinstance(child, (ast.If, ast.IfExp)):
                cc += 1
            elif isinstance(child, (ast.For, ast.AsyncFor, ast.While)):
                cc += 1
            elif isinstance(child, ast.ExceptHandler):
                cc += 1
            elif isinstance(child, ast.BoolOp):
                cc += len(child.values) - 1
            elif isinstance(child, ast.Assert):
                cc += 1
        return cc

    def _cognitive_complexity(self, node: ast.AST, depth: int = 0) -> int:
        """Cognitive complexity: nesting adds weight to decisions."""
        total = 0
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.If, ast.IfExp)):
                total += 1 + depth
                total += self._cognitive_complexity(child, depth + 1)
            elif isinstance(child, (ast.For, ast.AsyncFor, ast.While)):
                total += 1 + depth
                total += self._cognitive_complexity(child, depth + 1)
            elif isinstance(child, ast.ExceptHandler):
                total += 1 + depth
                total += self._cognitive_complexity(child, depth + 1)
            elif isinstance(child, ast.BoolOp):
                total += len(child.values) - 1
            else:
                total += self._cognitive_complexity(child, depth)
        return total

    def _max_nesting(self, node: ast.AST, depth: int = 0) -> int:
        """Find maximum nesting depth of control structures."""
        max_d = depth
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.If, ast.For, ast.AsyncFor, ast.While,
                                  ast.With, ast.AsyncWith, ast.Try)):
                child_depth = self._max_nesting(child, depth + 1)
                max_d = max(max_d, child_depth)
            else:
                child_depth = self._max_nesting(child, depth)
                max_d = max(max_d, child_depth)
        return max_d

    def _branch_fan_out(self, node: ast.AST) -> int:
        """Count distinct call targets (function calls in this function)."""
        calls = set()
        for child in ast.walk(node):
            if isinstance(child, ast.Call):
                if isinstance(child.func, ast.Name):
                    calls.add(child.func.id)
                elif isinstance(child.func, ast.Attribute):
                    calls.add(child.func.attr)
        return len(calls)

    def _is_routing_only(self, node: ast.FunctionDef) -> bool:
        """Heuristic: function is routing-only if it just dispatches/delegates.

        A routing function has no domain logic — only calls and returns.
        Heuristic: body is ≤3 statements AND all are calls, returns, or assignments
        to the result of a call.
        """
        body = node.body
        # Skip docstring
        if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
            body = body[1:]

        if len(body) > 3:
            return False

        for stmt in body:
            if isinstance(stmt, ast.Return):
                continue
            elif isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call):
                continue
            elif isinstance(stmt, ast.Assign) and isinstance(stmt.value, ast.Call):
                continue
            else:
                return False
        return True


# --- Graph Path Analysis -----------------------------------------------------


def analyze_graph_paths(
    graph: TraceabilityGraph,
    max_path_length: int = 7,
) -> list[PathMetrics]:
    """Analyze all root-to-leaf paths in the graph for routing efficiency.

    Roots: nodes with no incoming edges.
    Leaves: nodes with no outgoing edges.
    """
    # Find roots (no incoming edges)
    all_nodes = graph.list_nodes(status="active")
    roots = []
    leaves = []
    for node in all_nodes:
        incoming = graph.get_edges_to(node.node_id)
        outgoing = graph.get_edges_from(node.node_id)
        if not incoming:
            roots.append(node.node_id)
        if not outgoing:
            leaves.append(node.node_id)

    paths: list[PathMetrics] = []
    for root in roots:
        for leaf in leaves:
            if root == leaf:
                continue
            path = graph.find_path(root, leaf, max_depth=max_path_length)
            if path:
                metrics = _classify_path(graph, path)
                paths.append(metrics)

    return paths


def detect_cycles(graph: TraceabilityGraph) -> list[list[str]]:
    """Detect cycles in the graph using DFS."""
    all_nodes = graph.list_nodes(status="active")
    visited: set[str] = set()
    in_stack: set[str] = set()
    cycles: list[list[str]] = []

    def dfs(node_id: str, path: list[str]):
        if node_id in in_stack:
            # Found a cycle
            cycle_start = path.index(node_id)
            cycles.append(path[cycle_start:] + [node_id])
            return
        if node_id in visited:
            return

        visited.add(node_id)
        in_stack.add(node_id)
        path.append(node_id)

        for edge in graph.get_edges_from(node_id):
            dfs(edge.target_id, path[:])

        in_stack.discard(node_id)

    for node in all_nodes:
        if node.node_id not in visited:
            dfs(node.node_id, [])

    return cycles


def _classify_path(graph: TraceabilityGraph, path: list[str]) -> PathMetrics:
    """Classify a path by routing efficiency."""
    routing_hops = 0
    domain_hops = 0
    boundary_crossings = 0

    prev_type = None
    for nid in path:
        node = graph.get_node(nid)
        if not node:
            continue

        node_type = node.node_type.value
        is_routing = node.metadata.get("routing_only", False)

        if is_routing:
            routing_hops += 1
        else:
            domain_hops += 1

        # Boundary crossing: different node types in sequence
        if prev_type and prev_type != node_type:
            boundary_crossings += 1
        prev_type = node_type

    # Classification
    total = routing_hops + domain_hops
    if total == 0:
        classification = "empty"
    elif routing_hops > domain_hops:
        classification = "routing-heavy"
    elif _has_ping_pong(path, graph):
        classification = "ping-pong"
    else:
        classification = "efficient"

    return PathMetrics(
        path=path,
        length=len(path),
        routing_hops=routing_hops,
        domain_hops=domain_hops,
        boundary_crossings=boundary_crossings,
        classification=classification,
    )


def _has_ping_pong(path: list[str], graph: TraceabilityGraph) -> bool:
    """Detect A→B→A pattern in a path (ping-pong)."""
    if len(path) < 3:
        return False
    types = []
    for nid in path:
        node = graph.get_node(nid)
        types.append(node.node_type.value if node else "")
    # Check for type oscillation
    for i in range(len(types) - 2):
        if types[i] == types[i + 2] and types[i] != types[i + 1]:
            return True
    return False
