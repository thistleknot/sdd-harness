"""| Stage | Mechanism | Tag | Requirements |
|---|---|---|---|
| LOAD | Import deployed specs MCP analyzer without starting its server | [mandatory] | R1 |
| EXERCISE | Check exact IDs, repeated IDs and task-local references | [mandatory] | R1-R2 |
| VERIFY | Assert coverage and orphan outputs | [contract] | R1-R2 |

R1: WHEN analyzer input contains requirement identifiers, only whole REQ-NNN tokens shall count.
R2: WHEN task references are evaluated, each reference shall remain within its declared task block.
CLOSED: Substring assertions are rejected because REQ-100 must not cover REQ-10.
Preconditions: deployed specs MCP and FastMCP dependencies are installed.
Failure modes: malformed analyzer JSON or incorrect coverage fails the test.
"""
import json
import sys
from pathlib import Path

import pytest


SPECS_SERVICE = Path.home() / ".mcp" / "specs"
sys.path.insert(0, str(SPECS_SERVICE))
import specs_mcp  # noqa: E402


@pytest.mark.parametrize(
    ("spec_text", "design_text", "tasks_text", "expected_design", "expected_tasks", "orphaned"),
    [
        ("REQ-10 REQ-100", "REQ-10", "T-1: exact REQ-10", 1, 1, []),
        ("REQ-10", "REQ-100", "T-1: REQ-100", 0, 0, ["T-1"]),
        ("REQ-10 REQ-20 REQ-10", "REQ-10", "T-1: REQ-10\nT-2: no requirement\nT-3: unrelated REQ-20", 1, 2, ["T-2"]),
        ("REQ-10", "REQ-10", "- Task #14: open\n  Requirement: REQ-10\n- Task #15: unrelated", 1, 1, ["Task #15"]),
        ("REQ-10", "REQ-10", "loose reference REQ-10 without a task heading", 1, 0, []),
    ],
)
def test_cross_analyze_exact_ids_and_task_blocks(
    spec_text, design_text, tasks_text, expected_design, expected_tasks, orphaned
):
    """Verify coverage follows exact tokens and local task references.

    Require: inputs cover exact/prefix IDs, repeated IDs, and recognized/unrecognized task blocks.
    Guarantee: only exact references in recognized task blocks count toward coverage.
    Maintain: deployed result JSON keys stay stable.
    Assert: design, task coverage and orphan task results match each fixture.
    """
    result = json.loads(specs_mcp.cross_analyze.fn(spec_text, design_text, tasks_text))
    assert int(result["design_coverage"].split("/")[0]) == expected_design
    assert int(result["task_coverage"].split("/")[0]) == expected_tasks
    assert result["orphaned_tasks"] == orphaned
