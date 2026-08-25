"""Phase 5 integration: traceability graph → UML views → provenance → branch analysis.

Proves: graph populated → UML views generate valid Mermaid → provenance parser
validates symbols against graph → branch analyzer classifies paths → mutation
fixtures produce expected diagnostics.
"""
import pytest

from specs.branch_analysis import BranchAnalyzer, analyze_graph_paths, detect_cycles
from specs.mutation_fixtures import build_fixture, FIXTURES
from specs.provenance import ProvenanceParser, validate_provenance
from specs.traceability_graph import TraceabilityGraph
from specs.uml_views import UmlViewGenerator, ViewType


@pytest.fixture
def populated_graph():
    """A realistic graph with multiple node types and edges."""
    g = TraceabilityGraph(":memory:")
    # Intent → Requirement → Code → Test chain
    g.add_node("intent", "I-001", label="User auth")
    g.add_node("requirement", "R-001", label="Login endpoint")
    g.add_node("requirement", "R-002", label="Token refresh")
    g.add_node("code_symbol", "S-login", label="login()", source_hash="aaa")
    g.add_node("code_symbol", "S-refresh", label="refresh()", source_hash="bbb")
    g.add_node("test", "T-001", label="test_login")
    g.add_node("test", "T-002", label="test_refresh")
    g.add_node("artifact", "A-001", label="auth.py")

    g.add_edge("R-001", "I-001", "derives_from")
    g.add_edge("R-002", "I-001", "derives_from")
    g.add_edge("S-login", "R-001", "implements")
    g.add_edge("S-refresh", "R-002", "implements")
    g.add_edge("T-001", "S-login", "tests")
    g.add_edge("T-002", "S-refresh", "tests")
    g.add_edge("S-login", "S-refresh", "depends_on")
    yield g
    g.close()


class TestPhase5Integration:
    def test_graph_to_uml_roundtrip(self, populated_graph):
        """Graph → UML views → validation passes (no stale, no missing nodes)."""
        gen = UmlViewGenerator(populated_graph)

        uc = gen.use_case_view()
        assert uc.view_type == ViewType.use_case
        assert gen.validate_view(uc) == []

        comp = gen.component_view()
        assert "S-login" in comp.mermaid
        assert gen.validate_view(comp) == []

        cls = gen.class_view()
        assert cls.mermaid.startswith("classDiagram")
        assert gen.validate_view(cls) == []

    def test_graph_to_provenance_validation(self, populated_graph):
        """Source with valid provenance → no issues against graph."""
        source = '''
def login(username: str) -> bool:
    """Authenticate user.

    Purpose: Validate credentials
    Requirements: R-001
    """
    pass
'''
        parser = ProvenanceParser()
        records = parser.parse_source(source)
        issues = validate_provenance(records, populated_graph)
        assert issues == []

    def test_provenance_catches_missing_ref(self, populated_graph):
        """Source referencing nonexistent requirement → error."""
        source = '''
def orphan():
    """Bad ref.

    Requirements: R-999
    """
    pass
'''
        parser = ProvenanceParser()
        records = parser.parse_source(source)
        issues = validate_provenance(records, populated_graph)
        assert len(issues) == 1
        assert "not found" in issues[0].message

    def test_graph_path_analysis(self, populated_graph):
        """Graph paths classified correctly — no cycles in clean graph."""
        cycles = detect_cycles(populated_graph)
        assert cycles == []

        paths = analyze_graph_paths(populated_graph)
        assert len(paths) > 0
        # All paths in this clean graph should be efficient
        assert all(p.classification == "efficient" for p in paths)

    def test_branch_analyzer_on_real_source(self):
        """Branch analyzer produces meaningful metrics on nontrivial code."""
        source = '''
def complex(items):
    for item in items:
        if item > 0:
            if item % 2 == 0:
                return item
        elif item == 0:
            continue
    return None
'''
        analyzer = BranchAnalyzer()
        metrics = analyzer.analyze_source(source)
        fn = metrics.functions[0]
        assert fn.cyclomatic_complexity >= 4
        assert fn.nesting_depth >= 2
        assert fn.is_routing_only is False

    def test_mutation_fixtures_self_consistent(self):
        """Every fixture produces a graph matching its own expectations."""
        for name in FIXTURES:
            graph, expected = build_fixture(name)
            orphans = graph.orphan_nodes()
            # Filter dynamic roots (metadata convention)
            real_orphans = [
                o for o in orphans
                if not o.metadata.get("dynamic_root")
            ]
            assert len(real_orphans) == expected.orphan_count, (
                f"Fixture '{name}': expected {expected.orphan_count} orphans, got {len(real_orphans)}"
            )
            graph.close()
