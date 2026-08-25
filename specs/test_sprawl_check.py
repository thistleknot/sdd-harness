"""Test suite sprawl check — run as a meta-test.

Flags when the test suite is growing faster than the production code,
duplicating intent across files, or accumulating per-function bandaids
instead of holistic behavioral tests.

Thresholds (from steering: feature-lifecycle.md):
- Max ~30 canonical tests per module (not per function)
- Test-to-production-function ratio should stay < 3:1
- No test file should exceed 40 tests (split or generalize)
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

SPECS_DIR = Path(__file__).parent
MAX_TESTS_PER_FILE = 40
MAX_TEST_TO_PROD_RATIO = 3.0
MAX_TOTAL_TESTS = 300  # alarm threshold — rethink if we hit this


def _count_test_functions(path: Path) -> int:
    """Count test functions/methods in a file."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError:
        return 0
    count = 0
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name.startswith("test_"):
                count += 1
    return count


def _count_production_functions(path: Path) -> int:
    """Count public functions/methods in a production file."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError:
        return 0
    count = 0
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if not node.name.startswith("_") and not node.name.startswith("test_"):
                count += 1
    return count


def _get_test_files() -> list[Path]:
    return sorted(SPECS_DIR.rglob("test_*.py"))


def _get_prod_files() -> list[Path]:
    return [
        p for p in sorted(SPECS_DIR.rglob("*.py"))
        if not p.name.startswith("test_") and p.name != "__init__.py"
    ]


class TestSprawlCheck:
    def test_no_file_exceeds_max_tests(self):
        """Each test file should stay under MAX_TESTS_PER_FILE."""
        violations = []
        for path in _get_test_files():
            count = _count_test_functions(path)
            if count > MAX_TESTS_PER_FILE:
                violations.append(f"{path.name}: {count} tests (max {MAX_TESTS_PER_FILE})")
        assert violations == [], f"Test files exceed limit:\n" + "\n".join(violations)

    def test_total_tests_under_alarm(self):
        """Total test count should stay under alarm threshold."""
        total = sum(_count_test_functions(p) for p in _get_test_files())
        assert total <= MAX_TOTAL_TESTS, (
            f"Total tests: {total} exceeds alarm threshold {MAX_TOTAL_TESTS}. "
            f"Generalize or collapse duplicate-intent tests."
        )

    def test_ratio_within_bounds(self):
        """Test-to-production-function ratio shouldn't explode."""
        total_tests = sum(_count_test_functions(p) for p in _get_test_files())
        total_prod = sum(_count_production_functions(p) for p in _get_prod_files())
        if total_prod == 0:
            return
        ratio = total_tests / total_prod
        assert ratio <= MAX_TEST_TO_PROD_RATIO, (
            f"Test:prod ratio is {ratio:.1f}:1 (max {MAX_TEST_TO_PROD_RATIO}:1). "
            f"{total_tests} tests / {total_prod} production functions."
        )

    def test_report_current_stats(self):
        """Not a gate — just prints current stats for visibility."""
        test_files = _get_test_files()
        prod_files = _get_prod_files()
        total_tests = sum(_count_test_functions(p) for p in test_files)
        total_prod = sum(_count_production_functions(p) for p in prod_files)
        ratio = total_tests / total_prod if total_prod else 0

        print(f"\n--- Test Sprawl Report ---")
        print(f"Test files: {len(test_files)}")
        print(f"Prod files: {len(prod_files)}")
        print(f"Total tests: {total_tests}")
        print(f"Total prod functions: {total_prod}")
        print(f"Ratio: {ratio:.1f}:1")
        print(f"Largest test file: ", end="")
        if test_files:
            largest = max(test_files, key=_count_test_functions)
            print(f"{largest.name} ({_count_test_functions(largest)} tests)")
        print(f"--------------------------")
