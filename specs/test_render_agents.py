"""Tests for render_agents.py.

The module's whole reason to exist is a byte-exact identity transform: rendering
an unchanged schema over unchanged bodies must reproduce the source files
exactly, CRLF and all. So most of these tests assert on bytes, not on "looks
about right" -- a renderer that silently normalized line endings would rewrite
every agent file for zero semantic change and make --check meaningless.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import render_agents as ra


CRLF_SRC = (
    "---\r\n"
    "name: opus_planner\r\n"
    "description: plans the work\r\n"
    "model: stale-model\r\n"
    "reasoningEffort: low\r\n"
    'tools: ["Read"]\r\n'
    "---\r\n"
    "Body line one.\r\n"
    "\r\n"
    "Body line two.\r\n"
)


@pytest.fixture
def schema() -> dict:
    return {
        "stale_after_days": 90,
        "binding": {
            "claude": {
                "L1": "claude-opus-4",
                "L2": "claude-sonnet-4",
                "L3": "claude-haiku-4",
                "resolved": "2026-08-01",
                "effort_key": "reasoningEffort",
                "effort_map": {"high": "high", "medium": "medium", "low": "low"},
            }
        },
        "role": {
            "planner": {
                "name": "opus_planner",
                "tier": "L1",
                "reasoning": "high",
                "tools": ["Read", "Bash"],
            }
        },
    }


@pytest.fixture
def agents_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    d = tmp_path / "agents"
    d.mkdir()
    monkeypatch.setattr(ra, "SOURCE_AGENTS", d)
    return d


# --- exact I/O ---------------------------------------------------------------

def test_write_exact_does_not_translate_newlines(tmp_path: Path):
    p = tmp_path / "a.md"
    ra.write_exact(p, "one\r\ntwo\r\n")
    assert p.read_bytes() == b"one\r\ntwo\r\n"


def test_write_exact_leaves_lf_alone_on_windows(tmp_path: Path):
    p = tmp_path / "a.md"
    ra.write_exact(p, "one\ntwo\n")
    assert p.read_bytes() == b"one\ntwo\n"


def test_read_exact_preserves_crlf(tmp_path: Path):
    p = tmp_path / "a.md"
    p.write_bytes(b"one\r\ntwo\r\n")
    assert ra.read_exact(p) == "one\r\ntwo\r\n"


def test_read_exact_write_exact_round_trip_is_byte_identical(tmp_path: Path):
    src, dst = tmp_path / "s.md", tmp_path / "d.md"
    src.write_bytes(CRLF_SRC.encode("utf-8"))
    ra.write_exact(dst, ra.read_exact(src))
    assert dst.read_bytes() == src.read_bytes()


# --- newline handling --------------------------------------------------------

def test_detect_newline_crlf():
    assert ra.detect_newline("a\r\nb") == "\r\n"


def test_detect_newline_lf():
    assert ra.detect_newline("a\nb") == "\n"


def test_detect_newline_defaults_to_lf_when_no_newline():
    assert ra.detect_newline("a") == "\n"


def test_normalize_collapses_crlf_and_lone_cr():
    assert ra.normalize("a\r\nb\rc\nd") == "a\nb\nc\nd"


# --- frontmatter -------------------------------------------------------------

def test_split_frontmatter_returns_front_and_body():
    front, body = ra.split_frontmatter("---\nname: x\n---\nbody\n")
    assert front == "name: x"
    assert body == "body\n"


def test_split_frontmatter_keeps_body_trailing_newline():
    _, body = ra.split_frontmatter("---\nk: v\n---\nline\n\nlast\n")
    assert body == "line\n\nlast\n"


def test_split_frontmatter_keeps_body_without_trailing_newline():
    _, body = ra.split_frontmatter("---\nk: v\n---\nno trailing eol")
    assert body == "no trailing eol"


def test_split_frontmatter_closing_fence_at_eof_gives_empty_body():
    front, body = ra.split_frontmatter("---\nk: v\n---")
    assert (front, body) == ("k: v", "")


def test_split_frontmatter_rejects_unfenced_file():
    with pytest.raises(ra.RenderError, match="does not open"):
        ra.split_frontmatter("just a body\n")


def test_split_frontmatter_rejects_unclosed_fence():
    with pytest.raises(ra.RenderError, match="never closed"):
        ra.split_frontmatter("---\nk: v\nstill frontmatter\n")


def test_read_description_strips_key_and_whitespace():
    assert ra.read_description("name: x\ndescription:   plans stuff  \nmodel: m") == "plans stuff"


def test_read_description_raises_when_absent():
    with pytest.raises(ra.RenderError, match="no description:"):
        ra.read_description("name: x\nmodel: m")


# --- binding warnings --------------------------------------------------------

def test_binding_warnings_silent_when_fresh_and_bound(schema):
    import datetime as dt

    assert ra.binding_warnings(schema, "claude", today=dt.date(2026, 8, 15)) == []


def test_binding_warnings_flags_unbound_tiers(schema):
    import datetime as dt

    schema["binding"]["claude"]["L2"] = ""
    del schema["binding"]["claude"]["L3"]
    warns = ra.binding_warnings(schema, "claude", today=dt.date(2026, 8, 15))
    assert warns == ["claude: tiers L2, L3 are unbound (empty model id)"]


def test_binding_warnings_flags_missing_resolved_date(schema):
    import datetime as dt

    schema["binding"]["claude"]["resolved"] = ""
    warns = ra.binding_warnings(schema, "claude", today=dt.date(2026, 8, 15))
    assert warns == ["claude: binding has no resolved date"]


def test_binding_warnings_flags_stale_binding(schema):
    import datetime as dt

    warns = ra.binding_warnings(schema, "claude", today=dt.date(2026, 12, 1))
    assert len(warns) == 1
    assert warns[0].startswith("claude: binding resolved 2026-08-01 is 122d old (limit 90d)")


def test_binding_warnings_respects_custom_stale_limit(schema):
    import datetime as dt

    schema["stale_after_days"] = 200
    assert ra.binding_warnings(schema, "claude", today=dt.date(2026, 12, 1)) == []


def test_binding_warnings_at_exact_limit_is_not_stale(schema):
    import datetime as dt

    # 90 days after 2026-08-01; the check is age > limit, not >=.
    assert ra.binding_warnings(schema, "claude", today=dt.date(2026, 10, 30)) == []


# --- resolve -----------------------------------------------------------------

def test_resolve_maps_role_and_binding(schema):
    assert ra.resolve(schema, "claude", "planner") == {
        "name": "opus_planner",
        "tier": "L1",
        "model": "claude-opus-4",
        "effort_key": "reasoningEffort",
        "effort_value": "high",
        "tools": ["Read", "Bash"],
    }


def test_resolve_raises_on_unbound_tier(schema):
    schema["binding"]["claude"]["L1"] = ""
    with pytest.raises(ra.RenderError, match="no model bound to L1"):
        ra.resolve(schema, "claude", "planner")


def test_resolve_raises_on_missing_effort_mapping(schema):
    del schema["binding"]["claude"]["effort_map"]["high"]
    with pytest.raises(ra.RenderError, match="effort_map has no entry"):
        ra.resolve(schema, "claude", "planner")


# --- rendering ---------------------------------------------------------------

def test_render_claude_emits_exact_frontmatter(schema):
    res = ra.resolve(schema, "claude", "planner")
    out = ra.render_claude(res, "plans the work", "Body.\n")
    assert out == (
        "---\n"
        "name: opus_planner\n"
        "description: plans the work\n"
        "model: claude-opus-4\n"
        "reasoningEffort: high\n"
        'tools: ["Read", "Bash"]\n'
        "---\n"
        "Body.\n"
    )


def test_render_claude_quotes_every_tool(schema):
    res = ra.resolve(schema, "claude", "planner")
    out = ra.render_claude(res, "d", "")
    assert 'tools: ["Read", "Bash"]' in out


def test_render_all_preserves_crlf_from_source(schema, agents_dir):
    (agents_dir / "opus_planner.md").write_bytes(CRLF_SRC.encode("utf-8"))
    out = ra.render_all(schema, "claude")
    text = out["opus_planner"]
    assert "\n" not in text.replace("\r\n", "")
    assert text.endswith("Body line two.\r\n")
    assert "model: claude-opus-4\r\n" in text


def test_render_all_keeps_hand_written_description_and_body(schema, agents_dir):
    (agents_dir / "opus_planner.md").write_bytes(CRLF_SRC.encode("utf-8"))
    text = ra.render_all(schema, "claude")["opus_planner"]
    assert "description: plans the work\r\n" in text
    assert "Body line one.\r\n\r\nBody line two.\r\n" in text
    # policy fields come from the schema, not the stale source
    assert "stale-model" not in text


def test_render_all_rejects_unknown_harness(schema):
    with pytest.raises(ra.RenderError, match="no renderer for harness"):
        ra.render_all(schema, "codex")


def test_render_all_rejects_missing_source_body(schema, agents_dir):
    with pytest.raises(ra.RenderError, match="source body missing"):
        ra.render_all(schema, "claude")


# --- check / cli -------------------------------------------------------------

def test_check_reports_zero_drift_for_identical_file(schema, agents_dir, capsys):
    (agents_dir / "opus_planner.md").write_bytes(CRLF_SRC.encode("utf-8"))
    rendered = ra.render_all(schema, "claude")
    ra.write_exact(agents_dir / "opus_planner.md", rendered["opus_planner"])

    assert ra._check(schema, "claude", rendered) == 0
    assert "IDENTICAL" in capsys.readouterr().out


def test_check_counts_drift(schema, agents_dir, capsys):
    (agents_dir / "opus_planner.md").write_bytes(CRLF_SRC.encode("utf-8"))
    rendered = ra.render_all(schema, "claude")

    assert ra._check(schema, "claude", rendered) == 1
    assert "DRIFT" in capsys.readouterr().out


def test_main_out_writes_byte_exact_crlf(schema, agents_dir, tmp_path, monkeypatch):
    (agents_dir / "opus_planner.md").write_bytes(CRLF_SRC.encode("utf-8"))
    monkeypatch.setattr(ra, "load_schema", lambda *a, **k: schema)
    out = tmp_path / "out"

    rc = ra.main(["--harness", "claude", "--out", str(out)])

    assert rc == 0
    written = (out / "opus_planner.md").read_bytes()
    assert b"\r\n" in written
    assert written.count(b"\n") == written.count(b"\r\n")
    assert b"model: claude-opus-4\r\n" in written


def test_main_check_returns_one_on_drift(schema, agents_dir, monkeypatch):
    (agents_dir / "opus_planner.md").write_bytes(CRLF_SRC.encode("utf-8"))
    monkeypatch.setattr(ra, "load_schema", lambda *a, **k: schema)

    assert ra.main(["--harness", "claude", "--check"]) == 1


def test_main_check_returns_zero_once_rendered(schema, agents_dir, monkeypatch):
    (agents_dir / "opus_planner.md").write_bytes(CRLF_SRC.encode("utf-8"))
    monkeypatch.setattr(ra, "load_schema", lambda *a, **k: schema)
    ra.main(["--harness", "claude", "--out", str(agents_dir)])

    assert ra.main(["--harness", "claude", "--check"]) == 0


def test_main_render_error_exits_two(schema, agents_dir, monkeypatch, capsys):
    monkeypatch.setattr(ra, "load_schema", lambda *a, **k: schema)

    assert ra.main(["--harness", "claude", "--check"]) == 2
    assert "ERROR: source body missing" in capsys.readouterr().err


def test_main_requires_check_or_out(schema, agents_dir, monkeypatch):
    (agents_dir / "opus_planner.md").write_bytes(CRLF_SRC.encode("utf-8"))
    monkeypatch.setattr(ra, "load_schema", lambda *a, **k: schema)

    with pytest.raises(SystemExit):
        ra.main(["--harness", "claude"])
