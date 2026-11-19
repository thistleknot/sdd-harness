"""| Stage | Mechanism | Tag | Requirements |
|---|---|---|---|
| FIXTURE | Provide Claude-shaped settings with transcript and ordinary hooks | [mandatory] | R1 |
| FILTER | Resolve eligible hooks for a VS Code event | [mandatory] | R1 |
| VERIFY | Ensure transcript-only PreCompact capture is skipped | [contract] | R1 |

R1: IF a VS Code event lacks the Claude JSONL transcript source, THEN transcript-dependent hooks shall not run.
CLOSED: Passing an empty or foreign transcript pointer to PreCompact is rejected because it cannot capture the active conversation.
Preconditions: pytest and the VS Code shim module are available.
Failure modes: running the transcript hook through the shim fails the assertion.
"""
import importlib.util
import json
from pathlib import Path


SHIM_PATH = Path(__file__).resolve().parents[1] / "hooks" / "vscode_shim.py"
spec = importlib.util.spec_from_file_location("vscode_shim_under_test", SHIM_PATH)
vscode_shim = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vscode_shim)


def test_vscode_skips_pre_compact_transcript_capture(tmp_path, monkeypatch):
    """Verify the VS Code shim omits the Claude-only transcript capture hook.

    Require: settings include one transcript-dependent and one ordinary hook.
    Guarantee: only the ordinary hook is eligible for VS Code execution.
    Maintain: event matcher processing remains unchanged.
    Assert: pre_compact.py is absent from the selected commands.
    """
    settings = tmp_path / "settings.json"
    settings.write_text(json.dumps({"hooks": {"PreCompact": [{"hooks": [
        {"type": "command", "command": "python C:/harness/hooks/pre_compact.py"},
        {"type": "command", "command": "python C:/claude/hooks/ordinary.py"},
    ]}]}}), encoding="utf-8")
    monkeypatch.setattr(vscode_shim, "SETTINGS", settings)
    hooks = vscode_shim.commands_for("PreCompact", None, None)
    assert [hook["command"] for hook in hooks] == ["python C:/claude/hooks/ordinary.py"]
