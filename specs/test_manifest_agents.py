"""Validate capability-matrix declarations and agent renderer projections.

| Stage | Mechanism | Contract | Req |
|---|---|---|---|
| LOAD | Read harness and artifact cells from manifest.toml | [mandatory] | R62, R63 |
| CHECK | Reject undeclared harnesses, duplicate cells, unknown strategies, and reasonless SKIP | [mandatory] | R62, R63 |
| PROJECT | Compare agent cells with tiers.toml and render_agents.py | [mandatory] | R54 |

EARS guards:
- R1: The manifest is the declared capability matrix; tests compare its values to renderers without writing configs.
- R2: SKIP requires a reason and each artifact/harness pair has exactly one strategy.

CLOSED:
- Undeclared harness cells were previously tolerated; measured mismatch on 2026-10-21 showed cells for Codex, Gemini, and Hermes without top-level declarations.

Preconditions: manifest.toml and tiers.toml are readable TOML files.
Failure modes: parse errors, duplicate/unknown cells, missing reasons, or renderer drift fail the suite.

Run from ~/.harness: python -m pytest specs/test_manifest_agents.py -q
"""
from __future__ import annotations

from pathlib import Path

import pytest

import harness_write as hw
import render_agents as ra

try:
    import tomllib
except ModuleNotFoundError:  # py310 pin
    import tomli as tomllib

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def cells() -> dict:
    """Load agent capability cells keyed by harness.

    Returns:
        Mapping from harness identifier to its manifest cell.

    Require: manifest.toml is valid TOML.
    Guarantee: Each returned cell describes the agent projection for one harness.
    Maintain: The manifest is read-only during test setup.
    Assert: TOML parsing succeeds before tests inspect cells.
    """
    with (ROOT / "manifest.toml").open("rb") as fh:
        data = tomllib.load(fh)
    return {c["harness"]: c for c in data["cell"] if c["artifact"] == "agents"}


@pytest.fixture(scope="module")
def schema() -> dict:
    """Load the canonical role/provider schema used by render_agents.py.

    Returns:
        Parsed tiers.toml data.

    Require: tiers.toml is valid and complete.
    Guarantee: Tests share the same schema the renderer consumes.
    Maintain: The fixture performs no writes.
    Assert: Renderer schema loading succeeds.
    """
    return ra.load_schema()


def test_every_harness_in_tiers_toml_has_exactly_one_agents_row_and_vice_versa(cells, schema):
    """Keep agent projections aligned with the active provider roster.

    Args:
        cells: Manifest agent cells.
        schema: Canonical renderer schema.

    Require: Each provider harness has one agent projection row.
    Guarantee: Missing and extra agent rows fail the test.
    Maintain: The check compares harness identifiers only.
    Assert: The two harness sets are equal.
    """
    assert set(cells) == set(schema["harness"])


def test_every_agents_row_is_generate_because_nothing_is_a_plain_link_any_more(cells):
    """Require rendered agent outputs because native formats differ.

    Args:
        cells: Manifest agent cells.

    Require: Every row describes a supported projection.
    Guarantee: No agent row claims byte-identical linking.
    Maintain: Only the strategy column is evaluated.
    Assert: Every strategy is GENERATE.
    """
    assert {c["strategy"] for c in cells.values()} == {"GENERATE"}


def test_rows_with_a_renderer_are_exactly_the_harnesses_that_speak_providers(cells, schema):
    """Ensure provider-capable harnesses have renderers and document-only harnesses have docs.

    Args:
        cells: Manifest agent cells.
        schema: Canonical renderer schema.

    Require: Provider capability and renderer registration agree.
    Guarantee: Document-only harnesses retain their output declaration.
    Maintain: Harnesses without providers do not receive generated agent files.
    Assert: Provider harnesses equal registered party renderers.
    """
    speaks = {h for h, v in schema["harness"].items() if v.get("providers")}
    assert speaks == set(ra.PARTY_RENDERERS)
    for h in set(cells) - speaks:
        assert "doc" in schema["harness"][h]                       # the rest are instruction documents


def test_each_rows_target_is_the_primary_path_the_renderer_writes(cells, schema, monkeypatch):
    """Compare manifest targets with canonical renderer destinations.

    Args:
        cells: Manifest agent cells.
        schema: Canonical renderer schema.
        monkeypatch: Pytest fixture that isolates the home directory.

    Require: Renderer targets are rooted in the configured harness destinations.
    Guarantee: Every agent cell target matches the renderer's expanded primary path.
    Maintain: No live config path is written.
    Assert: Every target comparison is byte-for-byte path-equal.
    """
    monkeypatch.setattr(hw.Path, "home", classmethod(lambda cls: Path("C:/Users/user")))
    for name, cell in cells.items():
        h = schema["harness"][name]
        key = "agent_dir" if h.get("providers") else "doc"
        expected = hw.expand(h[key], ROOT).as_posix()
        assert Path(cell["target"]).as_posix() == expected, (name, cell["target"], expected)


def test_a_row_that_says_unverified_matches_the_tiers_toml_verified_list(cells, schema):
    """Prevent stale verification labels from contradicting tiers.toml.

    Args:
        cells: Manifest agent cells.
        schema: Canonical renderer schema.

    Require: Verification status is owned by tiers.toml.
    Guarantee: Verified providers are not labeled UNVERIFIED in the manifest.
    Maintain: No live provider probe is run.
    Assert: Every row's note agrees with its schema verification flag.
    """
    for name, cell in cells.items():
        verified = bool(schema["harness"][name].get("verified"))
        says_unverified = "UNVERIFIED" in cell["note"]
        assert not (verified and says_unverified), (name, "verified in tiers.toml but the manifest note says UNVERIFIED")


def test_every_agents_row_documents_what_it_emits_and_the_codex_row_names_its_templates(cells):
    """Require each agent projection to describe its generated artifact.

    Args:
        cells: Manifest agent cells.

    Require: Generated outputs and provider templates are documented.
    Guarantee: Missing artifact descriptions fail the test.
    Maintain: Documentation is checked without rendering or writing outputs.
    Assert: Every row emits a named artifact.
    """
    for name, cell in cells.items():
        assert cell.get("emit"), name
    assert "profiles" in cells["codex"]["emit"] and "Templates: openai, ollama" in cells["codex"]["note"]


def test_every_cell_harness_has_a_top_level_declaration():
    """Reject artifact cells that refer to an undeclared harness.

    Require: manifest.toml uses one canonical identifier across its harness and cell tables.
    Guarantee: Missing harness declarations fail before any adapter projection is claimed.
    Maintain: This test reads the manifest only.
    Assert: Every cell harness is a key in manifest.harness.
    """
    with (ROOT / "manifest.toml").open("rb") as fh:
        data = tomllib.load(fh)

    cell_harnesses = {cell["harness"] for cell in data["cell"]}
    assert cell_harnesses <= set(data["harness"]), cell_harnesses - set(data["harness"])


def test_capability_cells_are_unique_and_use_known_strategies():
    """Require one supported projection decision for each artifact/harness pair.

    Require: Each matrix cell has artifact, harness, and strategy fields.
    Guarantee: Duplicate cells and unsupported strategy labels fail.
    Maintain: LINK, GENERATE, and SKIP remain the only strategy vocabulary.
    Assert: Artifact/harness keys are unique and strategies belong to the closed set.
    """
    with (ROOT / "manifest.toml").open("rb") as fh:
        cells = tomllib.load(fh)["cell"]

    pairs = [(cell["artifact"], cell["harness"]) for cell in cells]
    assert len(pairs) == len(set(pairs)), "duplicate artifact/harness cells"
    assert {cell["strategy"] for cell in cells} <= {"LINK", "GENERATE", "SKIP"}


def test_skipped_capabilities_include_a_reason():
    """Require an explicit disposition wherever a capability is unavailable.

    Require: SKIP cells represent deliberate absence rather than missing work.
    Guarantee: Every SKIP row explains the absence with a non-empty reason.
    Maintain: The test does not infer support from neighboring harnesses.
    Assert: No SKIP cell lacks a reason.
    """
    with (ROOT / "manifest.toml").open("rb") as fh:
        cells = tomllib.load(fh)["cell"]

    assert all(cell.get("reason", "").strip() for cell in cells if cell["strategy"] == "SKIP")
