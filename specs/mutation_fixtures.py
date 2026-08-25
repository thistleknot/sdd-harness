"""Mutation fixtures for reachability and traceability gates.

Purpose: test graph garbage-collection semantics with concrete fixtures covering
reachable symbols, orphans, dynamic callbacks, pending/closed tasks, duplicates,
stale docstrings, stale UML hashes, missing edges, and unexpected actions.

Preconditions: traceability_graph.py available.
Failure modes: assertion failures in gate tests if fixtures don't produce expected diagnostics.

Usage:
    from specs.mutation_fixtures import build_fixture, FIXTURES
    graph, expected = build_fixture("direct_orphan")
    actual_orphans = graph.orphan_nodes()
    assert len(actual_orphans) == expected["orphan_count"]
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from .traceability_graph import TraceabilityGraph


@dataclass
class FixtureExpectation:
    """What a gate should diagnose for this fixture."""
    orphan_count: int = 0
    stale_count: int = 0
    missing_edge_count: int = 0
    blocking: bool = False
    diagnostics: list[str] = field(default_factory=list)


# --- Fixture Builders --------------------------------------------------------


def _fixture_reachable_production(g: TraceabilityGraph) -> FixtureExpectation:
    """A fully-connected production symbol — no issues expected."""
    g.add_node("requirement", "R-001", label="Auth login")
    g.add_node("code_symbol", "S-login", label="login()", source_hash="abc123")
    g.add_node("test", "T-001", label="test_login")
    g.add_edge("S-login", "R-001", "implements")
    g.add_edge("T-001", "S-login", "tests")
    return FixtureExpectation(orphan_count=0, stale_count=0)


def _fixture_direct_orphan(g: TraceabilityGraph) -> FixtureExpectation:
    """A code symbol with no edges — direct orphan."""
    g.add_node("requirement", "R-001", label="Auth")
    g.add_node("code_symbol", "S-login", label="login()")
    g.add_node("code_symbol", "S-orphan", label="dead_code()")
    g.add_edge("S-login", "R-001", "implements")
    # S-orphan has no edges
    return FixtureExpectation(
        orphan_count=1,
        diagnostics=["S-orphan is unreferenced"],
    )


def _fixture_dynamic_callback_root(g: TraceabilityGraph) -> FixtureExpectation:
    """A symbol registered as a dynamic callback — not orphan despite no static edges.

    Convention: metadata contains {"dynamic_root": true} to mark it as reachable.
    """
    g.add_node("code_symbol", "S-handler", label="on_event()",
               metadata={"dynamic_root": True})
    # No edges, but metadata marks it as a root
    return FixtureExpectation(
        orphan_count=0,  # gate should respect dynamic_root metadata
        diagnostics=["S-handler marked as dynamic root — not orphan"],
    )


def _fixture_pending_active_task(g: TraceabilityGraph) -> FixtureExpectation:
    """A symbol with a pending task — not orphan, task is active."""
    g.add_node("code_symbol", "S-wip", label="wip_feature()", status="pending")
    g.add_node("task", "T-042", label="Implement WIP", status="active")
    g.add_edge("T-042", "S-wip", "produces")
    return FixtureExpectation(
        orphan_count=0,
        diagnostics=["S-wip is pending with active task T-042"],
    )


def _fixture_pending_closed_task(g: TraceabilityGraph) -> FixtureExpectation:
    """A pending symbol whose task is done — should be flagged."""
    g.add_node("code_symbol", "S-stale", label="stale_feature()", status="pending")
    g.add_node("task", "T-099", label="Old task", status="deprecated")
    g.add_edge("T-099", "S-stale", "produces")
    return FixtureExpectation(
        orphan_count=0,  # has edges, not orphan
        stale_count=1,   # pending but task closed
        diagnostics=["S-stale is pending but task T-099 is deprecated"],
    )


def _fixture_duplicate_implementation(g: TraceabilityGraph) -> FixtureExpectation:
    """Two symbols implementing the same requirement — potential duplication."""
    g.add_node("requirement", "R-001", label="Login")
    g.add_node("code_symbol", "S-login-v1", label="login_v1()")
    g.add_node("code_symbol", "S-login-v2", label="login_v2()")
    g.add_edge("S-login-v1", "R-001", "implements")
    g.add_edge("S-login-v2", "R-001", "implements")
    return FixtureExpectation(
        orphan_count=0,
        diagnostics=["R-001 has multiple implementations: S-login-v1, S-login-v2"],
    )


def _fixture_stale_docstring_id(g: TraceabilityGraph) -> FixtureExpectation:
    """A symbol referencing a superseded requirement — stale provenance."""
    g.add_node("requirement", "R-OLD", label="Old req", status="active")
    g.update_node("R-OLD", status="superseded")
    g.add_node("requirement", "R-NEW", label="New req")
    g.add_edge("R-NEW", "R-OLD", "supersedes")
    g.add_node("code_symbol", "S-fn", label="some_fn()")
    g.add_edge("S-fn", "R-OLD", "implements")  # points to superseded!
    return FixtureExpectation(
        stale_count=1,
        diagnostics=["S-fn implements superseded R-OLD — should reference R-NEW"],
    )


def _fixture_stale_uml_source_hash(g: TraceabilityGraph) -> FixtureExpectation:
    """A diagram node whose source hash is outdated."""
    g.add_node("artifact", "UML-001", label="Component diagram", source_hash="old_hash")
    return FixtureExpectation(
        orphan_count=1,  # no edges → structurally an orphan
        stale_count=1,
        diagnostics=["UML-001 source_hash may be outdated (requires regeneration check)"],
    )


def _fixture_missing_requirement_to_test(g: TraceabilityGraph) -> FixtureExpectation:
    """A requirement with implementation but no test edge."""
    g.add_node("requirement", "R-001", label="Auth")
    g.add_node("code_symbol", "S-login", label="login()")
    g.add_edge("S-login", "R-001", "implements")
    # No test node or test edge
    return FixtureExpectation(
        missing_edge_count=1,
        diagnostics=["R-001 has implementation but no test coverage edge"],
    )


def _fixture_unexpected_behavioral_action(g: TraceabilityGraph) -> FixtureExpectation:
    """An anomaly node blocking a task — unexpected action detected."""
    g.add_node("task", "T-001", label="Deploy auth")
    g.add_node("anomaly", "ANOM-001", label="Unexpected deletion of auth.py")
    g.add_edge("ANOM-001", "T-001", "blocks")
    return FixtureExpectation(
        blocking=True,
        diagnostics=["ANOM-001 blocks T-001: unexpected deletion of auth.py"],
    )


# --- Registry ----------------------------------------------------------------


FIXTURES: dict[str, Callable[[TraceabilityGraph], FixtureExpectation]] = {
    "reachable_production": _fixture_reachable_production,
    "direct_orphan": _fixture_direct_orphan,
    "dynamic_callback_root": _fixture_dynamic_callback_root,
    "pending_active_task": _fixture_pending_active_task,
    "pending_closed_task": _fixture_pending_closed_task,
    "duplicate_implementation": _fixture_duplicate_implementation,
    "stale_docstring_id": _fixture_stale_docstring_id,
    "stale_uml_source_hash": _fixture_stale_uml_source_hash,
    "missing_requirement_to_test": _fixture_missing_requirement_to_test,
    "unexpected_behavioral_action": _fixture_unexpected_behavioral_action,
}


def build_fixture(name: str) -> tuple[TraceabilityGraph, FixtureExpectation]:
    """Build a named fixture and return (graph, expected_diagnostics).

    Raises KeyError if fixture name unknown.
    """
    if name not in FIXTURES:
        raise KeyError(f"Unknown fixture: {name}. Available: {list(FIXTURES.keys())}")
    g = TraceabilityGraph(":memory:")
    expected = FIXTURES[name](g)
    return g, expected


def run_all_fixtures() -> dict[str, tuple[TraceabilityGraph, FixtureExpectation]]:
    """Build all fixtures. Returns {name: (graph, expectation)}."""
    return {name: build_fixture(name) for name in FIXTURES}
