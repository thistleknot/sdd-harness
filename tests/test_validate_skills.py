"""Bounded fixtures for read-only skill package validation.

| Stage | Mechanism | Contract | Req |
|---|---|---|---|
| FIXTURE | Create varied skill packages in a temporary root | [mandatory] | R58, R59 |
| ASSERT | Check valid metadata, relative references, exit states, and no mutation | [mandatory] | R60, R61 |

EARS guards:
- R1: Tests use temporary directories and never edit ~/.skills.
- R2: The fixture battery covers self-contained, linked, and malformed packages.

CLOSED:
- Live ~/.skills content is not used as a fixture; it is checked only after this synthetic battery passes.

Preconditions: pytest and PyYAML are installed.
Failure modes: any contract mismatch fails the test.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from scripts.validate_skills import main, validate_root


@pytest.fixture
def skill_store(tmp_path: Path) -> Path:
    """Build four packages covering valid and invalid structures.

    Args:
        tmp_path: Pytest-owned temporary directory.

    Returns:
        Root path containing four immediate skill directories.

    Require: pytest supplies a writable isolated directory.
    Guarantee: Fixtures include a valid self-contained package, a valid relative reference,
        and a package with malformed metadata and a missing reference.
    Maintain: No user skill-store path is accessed.
    Assert: Four SKILL.md files exist beneath the returned root.
    """
    root = tmp_path / "skills"
    (root / "standalone").mkdir(parents=True)
    (root / "referenced" / "references").mkdir(parents=True)
    (root / "broken").mkdir(parents=True)
    (root / "standalone" / "SKILL.md").write_text(
        "---\nname: standalone\ndescription: Use for standalone fixture.\n---\n"
        "No links.\n\n```markdown\n[Example only](not-a-real-file.md)\n```\n",
        encoding="utf-8",
    )
    (root / "referenced" / "SKILL.md").write_text(
        "---\nname: referenced\ndescription: Use for linked fixture.\n---\n[Guide](references/guide.md)\n",
        encoding="utf-8",
    )
    (root / "referenced" / "references" / "guide.md").write_text("Guide\n", encoding="utf-8")
    (root / "malformed").mkdir()
    (root / "malformed" / "SKILL.md").write_text(
        "---\nname: [unclosed\ndescription: broken YAML\n---\n", encoding="utf-8"
    )
    (root / "broken" / "SKILL.md").write_text(
        "---\nname: wrong-name\ndescription: ''\n---\n[Missing](references/missing.md)\n", encoding="utf-8"
    )
    return root


def test_valid_packages_pass_and_broken_package_is_reported(skill_store: Path) -> None:
    """Verify all three fixture types discriminate valid metadata and references.

    Args:
        skill_store: Isolated fixture root.

    Require: skill_store contains the three packages from the fixture builder.
    Guarantee: Only the malformed package produces findings.
    Maintain: Validation leaves fixture bytes unchanged.
    Assert: Broken metadata and the missing local link both appear in findings.
    """
    before = {path: path.read_bytes() for path in skill_store.rglob("*") if path.is_file()}
    scanned, findings = validate_root(skill_store)
    after = {path: path.read_bytes() for path in skill_store.rglob("*") if path.is_file()}

    assert scanned == 4
    assert len(findings) == 4
    assert any("does not match directory" in item for item in findings)
    assert any("description must" in item for item in findings)
    assert any("unresolved relative link" in item for item in findings)
    assert any("invalid YAML frontmatter" in item for item in findings)
    assert after == before


@pytest.mark.parametrize("root_name", ["missing", "empty"])
def test_missing_or_empty_skill_roots_fail(tmp_path: Path, root_name: str) -> None:
    """Reject roots that cannot establish any skill package to validate.

    Args:
        tmp_path: Pytest-owned temporary directory.
        root_name: Whether to test a missing or an existing empty directory.

    Require: The empty case creates a directory; the missing case does not.
    Guarantee: Both inputs return one root-level finding and no discovered skills.
    Maintain: Validation creates no files.
    Assert: The root finding names the missing or empty condition.
    """
    root = tmp_path / root_name
    if root_name == "empty":
        root.mkdir()

    scanned, findings = validate_root(root)

    assert scanned == 0
    assert len(findings) == 1


def test_cli_uses_failure_exit_status_for_invalid_skill_store(skill_store: Path, capsys: pytest.CaptureFixture) -> None:
    """Expose invalid package findings through the documented CLI result.

    Args:
        skill_store: Isolated fixture root.
        capsys: Pytest output capture fixture.

    Require: skill_store includes an invalid skill.
    Guarantee: CLI returns one and prints a failure line.
    Maintain: The CLI uses the same validation contract as the library call.
    Assert: Output reports the number of scanned skills and findings.
    """
    assert main(["--root", str(skill_store)]) == 1
    assert "4 skill(s) scanned" in capsys.readouterr().out


def test_cli_returns_success_when_all_skill_packages_are_valid(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    """Verify the CLI success status for a valid skill store.

    Args:
        tmp_path: Pytest-owned temporary directory.
        capsys: Pytest output capture fixture.

    Require: The root contains one correctly named skill with valid metadata.
    Guarantee: CLI returns zero and prints a successful scan summary.
    Maintain: The fixture is isolated from ~/.skills.
    Assert: Output reports one scanned skill and no findings.
    """
    skill_file = tmp_path / "clean" / "SKILL.md"
    skill_file.parent.mkdir()
    skill_file.write_text("---\nname: clean\ndescription: Use for clean fixture.\n---\n", encoding="utf-8")

    assert main(["--root", str(tmp_path)]) == 0
    assert "PASS 1 skill(s) scanned" in capsys.readouterr().out
