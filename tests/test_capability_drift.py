"""| Stage | Mechanism | Tag | Requirements |
|---|---|---|---|
| CHECK | Compare canonical and deliberately damaged capability matrices | [mandatory] | R1 |
| VERIFY | Reject missing targets, incorrect paths, duplicates, and false SKIP | [contract] | R2 |

R1: When report tests run, the system shall avoid config writes and native client startup.
R2: When a matrix omits supported targets or misstates destinations, the system shall report drift.
CLOSED: Merely checking declared cells cannot detect omitted adapters.
Preconditions: committed matrix and registry are present; pytest is installed.
Failure modes: missing or falsely accepted drift fails assertions.
"""
from __future__ import annotations

import json
from pathlib import Path
import re
import shutil

import pytest

import adapter
from scripts import capability_drift

ROOT = Path(__file__).resolve().parents[1]


def damaged_manifest(tmp_path, name, replacement):
    """Write an isolated registry with one MCP cell changed or removed.

    Require: name identifies a canonical MCP cell and replacement is TOML text.
    Guarantee: Canonical files remain unchanged while a negative case is isolated.
    Maintain: Other matrix cells are preserved byte-for-byte.
    Assert: Exactly one selected block is replaced.
    """
    text = (ROOT / "manifest.toml").read_text(encoding="utf-8")
    pattern = rf'(?ms)^\[\[cell\]\]\nartifact\s*=\s*"mcp"\nharness\s*=\s*"{re.escape(name)}"\n.*?(?=^\[\[cell\]\]|\Z)'
    text, count = re.subn(pattern, lambda match: replacement, text)
    assert count == 1
    (tmp_path / "manifest.toml").write_text(text, encoding="utf-8")
    shutil.copy(ROOT / "harness.json", tmp_path / "harness.json")


@pytest.fixture(autouse=True)
def native_metadata_without_client_startup(monkeypatch):
    """Keep report tests independent of the installed Hermes runtime.

    Require: All targets other than Hermes have static path metadata.
    Guarantee: No native client process is started by report unit tests.
    Maintain: The canonical Hermes destination remains independently tested by native acceptance.
    Assert: All other target contracts use the real adapter accessor.
    """
    original = adapter.mcp_projection_contract
    monkeypatch.setattr(adapter, "mcp_projection_contract", lambda name: {
        "strategy": "GENERATE", "target": str(Path.home() / "AppData" / "Local" / "hermes" / "config.yaml"),
        "key": "mcp_servers", "reason": "",
    } if name == "hermes" else original(name))


def test_capability_drift_report_covers_supported_and_explicit_skip_cells(capsys):
    """Expose MCP support and deliberate omission using canonical registries.

    Require: The current manifest includes generated MCP cells and a reasoned SKIP.
    Guarantee: The report shows both dispositions and validates registered servers.
    Maintain: The report performs no adapter sync or config writes.
    Assert: The live read-only report completes without discrepancies.
    """
    lines, issues = capability_drift.build_report(ROOT)

    assert any(line.startswith("GENERATE claude:") for line in lines)
    assert any(line.startswith("SKIP pi:") for line in lines)
    assert issues == []
    assert capability_drift.main(["--root", str(ROOT)]) == 0
    assert "PASS: 0 discrepancy(s)" in capsys.readouterr().out


def test_capability_drift_report_detects_missing_adapter_projection(tmp_path, monkeypatch):
    """Fail when a generated manifest cell has no registered adapter target.

    Require: The fixture copies the two registries without editing the source checkout.
    Guarantee: The missing adapter mapping is reported as drift.
    Maintain: No harness config is written.
    Assert: Removing Claude's projection produces a precise discrepancy.
    """
    shutil.copy(ROOT / "manifest.toml", tmp_path / "manifest.toml")
    shutil.copy(ROOT / "harness.json", tmp_path / "harness.json")
    monkeypatch.setattr(adapter, "TARGETS", {key: value for key, value in adapter.TARGETS.items() if key != "claude"})
    _, issues = capability_drift.build_report(tmp_path)
    assert any("claude: no adapter target registered" in issue for issue in issues)
    assert json.loads((tmp_path / "harness.json").read_text(encoding="utf-8"))["mcp_servers"]


def test_capability_drift_report_detects_invalid_server_transport(tmp_path):
    """Reject a registry entry that cannot be projected by adapter.py.

    Require: Temporary registry copies are independent of the live configuration.
    Guarantee: Unsupported transport values produce a discrepancy.
    Maintain: The report is read-only.
    Assert: A malformed server is named in the report.
    """
    shutil.copy(ROOT / "manifest.toml", tmp_path / "manifest.toml")
    config = json.loads((ROOT / "harness.json").read_text(encoding="utf-8"))
    config["mcp_servers"]["fixture-invalid"] = {"type": "socket"}
    (tmp_path / "harness.json").write_text(json.dumps(config), encoding="utf-8")

    _, issues = capability_drift.build_report(tmp_path)

    assert "server fixture-invalid: unsupported transport 'socket'" in issues


@pytest.mark.parametrize("name", ["codex", "copilot", "vscode", "hermes"])
def test_missing_adapter_cell_is_detected(tmp_path, name):
    """Require an omitted implemented target; guarantee inverse coverage catches it."""
    damaged_manifest(tmp_path, name, "")
    _, issues = capability_drift.build_report(tmp_path)
    assert f"{name}: missing MCP disposition" in issues


def test_wrong_native_destination_is_detected(tmp_path):
    """Require a plausible Claude path with the wrong scope; guarantee drift."""
    damaged_manifest(tmp_path, "claude", '[[cell]]\nartifact="mcp"\nharness="claude"\nstrategy="GENERATE"\ntarget="C:/wrong/.mcp.json"\n\n')
    _, issues = capability_drift.build_report(tmp_path)
    assert any("claude: destination differs from native adapter" in issue for issue in issues)


def test_duplicate_cell_and_false_skip_are_detected(tmp_path):
    """Require contradictory duplicate rows; guarantee both defects are surfaced."""
    replacement = '[[cell]]\nartifact="mcp"\nharness="hermes"\nstrategy="SKIP"\nreason="fixture"\n\n'
    damaged_manifest(tmp_path, "hermes", replacement + replacement)
    _, issues = capability_drift.build_report(tmp_path)
    assert "hermes: duplicate MCP dispositions (2)" in issues
    assert "hermes: SKIP contradicts its native MCP adapter" in issues
