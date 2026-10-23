"""Tests for harness_write.py: safe merges into live config files.

Spec: C:/Users/user/.claude/plans/make-harness-render-and-install-the-party.md, section 4.
Run from ~/.harness: python -m pytest specs/test_harness_write.py -q
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import harness_write as hw


# ---- JSONC -----------------------------------------------------------------------------

def test_load_jsonc_handles_comments_trailing_commas_and_urls_in_strings():
    text = '''{
      // a line comment
      "url": "https://openrouter.ai/api/v1", /* block */
      "list": [1, 2,],
      "note": "keep // this and /* this */",
    }'''
    assert hw.load_jsonc(text) == {"url": "https://openrouter.ai/api/v1", "list": [1, 2],
                                   "note": "keep // this and /* this */"}


def test_load_jsonc_reports_bad_input_instead_of_guessing():
    with pytest.raises(hw.WriteError, match="cannot parse JSONC"):
        hw.load_jsonc("{not json}")
    with pytest.raises(hw.WriteError, match="unterminated"):
        hw.load_jsonc('{"a": 1 /* never closed')


def test_owned_prefix_replaces_our_keys_wholesale_and_leaves_everything_else_merged():
    base = {"variants": {"party_high": {"reasoning": {"effort": "high"}, "stale": 1}, "lean": {"x": 1}}, "other": {"a": 1}}
    patch = {"variants": {"party_high": {"reasoningEffort": "high"}}, "other": {"b": 2}}
    out = hw.deep_merge(base, patch, owned_prefix="party_")
    assert out["variants"]["party_high"] == {"reasoningEffort": "high"}        # the stale sub-keys are gone
    assert out["variants"]["lean"] == {"x": 1} and out["other"] == {"a": 1, "b": 2}
    assert hw.deep_merge(out, patch, owned_prefix="party_") == out             # idempotent
    merged_without = hw.deep_merge(base, patch)
    assert merged_without["variants"]["party_high"] == {"reasoning": {"effort": "high"}, "stale": 1,
                                                         "reasoningEffort": "high"}   # the defect the prefix fixes


def test_compute_passes_the_artifacts_owned_prefix_to_the_merge():
    existing = json.dumps({"v": {"party_x": {"old": 1}}})
    art = hw.Artifact(Path("c.json"), json.dumps({"v": {"party_x": {"new": 2}}}), "jsonmerge", owned_prefix="party_")
    assert json.loads(hw.compute(art, existing).after) == {"v": {"party_x": {"new": 2}}}
    no_prefix = hw.Artifact(Path("c.json"), art.text, "jsonmerge")
    assert json.loads(hw.compute(no_prefix, existing).after) == {"v": {"party_x": {"old": 1, "new": 2}}}


def test_deep_merge_merges_dicts_replaces_scalars_and_lists_and_mutates_nothing():
    base = {"a": {"x": 1, "y": [1]}, "keep": True}
    patch = {"a": {"y": [2, 3], "z": 4}}
    assert hw.deep_merge(base, patch) == {"a": {"x": 1, "y": [2, 3], "z": 4}, "keep": True}
    assert base == {"a": {"x": 1, "y": [1]}, "keep": True} and patch == {"a": {"y": [2, 3], "z": 4}}


# ---- jsonmerge -------------------------------------------------------------------------

def test_merge_json_is_idempotent_and_preserves_everything_it_does_not_own():
    existing = '{\n  "model": "m",\n  "provider": {"openrouter": {"apiKey": "{env:OR}", "models": {}}}\n}\n'
    patch = json.dumps({"provider": {"openrouter": {"models": {"x": {"variants": {"party_high": {"reasoning": {"effort": "high"}}}}}}}})
    once, w1 = hw.merge_json(existing, patch)
    twice, _ = hw.merge_json(once, patch)
    data = json.loads(once)
    assert once == twice and w1 == []
    assert data["model"] == "m" and data["provider"]["openrouter"]["apiKey"] == "{env:OR}"
    assert data["provider"]["openrouter"]["models"]["x"]["variants"]["party_high"]["reasoning"]["effort"] == "high"


def test_merge_json_warns_when_it_must_drop_comments_and_keeps_crlf():
    existing = '{\r\n  // hello\r\n  "a": 1\r\n}\r\n'
    out, warnings = hw.merge_json(existing, '{"b": 2}')
    assert warnings == ["the existing file has comments; they are dropped on write"]
    assert "\r\n" in out and "\n" not in out.replace("\r\n", "")
    assert json.loads(out) == {"a": 1, "b": 2}


def test_merge_json_into_a_missing_file_creates_it():
    out, warnings = hw.merge_json(None, '{"a": {"b": 1}}')
    assert json.loads(out) == {"a": {"b": 1}} and warnings == []


@pytest.mark.parametrize("key", ["apiKey", "api_key", "OPENROUTER_TOKEN", "client_secret", "password", "Authorization_bearer"])
def test_secret_looking_keys_are_refused_at_any_depth(key):
    with pytest.raises(hw.WriteError, match="looks like a secret"):
        hw.merge_json("{}", json.dumps({"a": {"b": [{key: "x"}]}}))


def test_ordinary_model_ids_and_reasoning_keys_are_not_mistaken_for_secrets():
    patch = {"openai/gpt-5.6-sol": {"variants": {"party_high": {"reasoning": {"effort": "high", "enabled": True}}}},
             "anthropic/claude-sonnet-5.5": {}, "deepseek/deepseek-v4-pro": {}}
    hw.assert_no_secret_keys(patch)


# ---- marker blocks ---------------------------------------------------------------------

def test_merge_block_appends_then_replaces_in_place_and_is_idempotent():
    base = 'model = "gpt-5.4"\n\n[profiles.local]\nmodel = "q"\n'
    once = hw.merge_block(base, '[profiles.party_a]\nmodel = "x"', hw.TOML_BEGIN, hw.TOML_END)
    assert once.startswith(base.rstrip("\n")) and hw.TOML_BEGIN in once and once.endswith(hw.TOML_END + "\n")
    changed = hw.merge_block(once, '[profiles.party_b]\nmodel = "y"', hw.TOML_BEGIN, hw.TOML_END)
    assert "party_b" in changed and "party_a" not in changed and changed.count(hw.TOML_BEGIN) == 1
    assert changed.startswith(base.rstrip("\n"))                      # everything outside the block survives
    assert hw.merge_block(changed, '[profiles.party_b]\nmodel = "y"', hw.TOML_BEGIN, hw.TOML_END) == changed


def test_merge_block_keeps_text_after_the_block_and_crlf():
    base = f'a = 1\r\n{hw.TOML_BEGIN}\r\nold\r\n{hw.TOML_END}\r\n[after]\r\nb = 2\r\n'
    out = hw.merge_block(base, "new = 1", hw.TOML_BEGIN, hw.TOML_END)
    assert out == f'a = 1\r\n{hw.TOML_BEGIN}\r\nnew = 1\r\n{hw.TOML_END}\r\n[after]\r\nb = 2\r\n'


def test_merge_block_refuses_a_half_marked_file():
    with pytest.raises(hw.WriteError, match="only one of the harness party markers"):
        hw.merge_block(f"x\n{hw.TOML_BEGIN}\ny\n", "z", hw.TOML_BEGIN, hw.TOML_END)


def test_merge_block_into_an_empty_or_missing_file():
    assert hw.merge_block(None, "x", hw.MD_BEGIN, hw.MD_END) == f"{hw.MD_BEGIN}\nx\n{hw.MD_END}\n"
    assert hw.merge_block("", "x", hw.MD_BEGIN, hw.MD_END) == f"{hw.MD_BEGIN}\nx\n{hw.MD_END}\n"


# ---- top-level toml keys ---------------------------------------------------------------

def test_set_toplevel_toml_keys_edits_in_place_adds_missing_and_never_touches_tables():
    base = 'model = "gpt-5.4"\nmodel_reasoning_effort = "xhigh"\n\n[profiles.local]\nmodel = "q"\nmodel_reasoning_effort = "medium"\n'
    out = hw.set_toplevel_toml_keys(base, {"model_reasoning_effort": '"medium"', "model_provider": '"p"'})
    assert out.splitlines()[:3] == ['model = "gpt-5.4"', 'model_reasoning_effort = "medium"', 'model_provider = "p"']
    assert out.endswith('[profiles.local]\nmodel = "q"\nmodel_reasoning_effort = "medium"\n')
    assert hw.set_toplevel_toml_keys(out, {"model_reasoning_effort": '"medium"'}) == out


# ---- compute / plan / apply ------------------------------------------------------------

def test_denylisted_files_are_never_opened_or_written(tmp_path):
    for name in ("oh-my-opencode-slim.json", "litellm_config.yaml"):
        with pytest.raises(hw.WriteError, match="refusing to touch"):
            hw.compute(hw.Artifact(tmp_path / name, "{}", "file"), None)
    hermes = tmp_path / "hermes" / "config.yaml"
    with pytest.raises(hw.WriteError, match="api_key"):
        hw.compute(hw.Artifact(hermes, "x", "file"), None)


@pytest.mark.parametrize("relative", ["hermes/config.yaml", "litellm_config.yaml", "oh-my-opencode-slim.json"])
def test_denylist_rejects_before_exists_or_open(tmp_path, monkeypatch, relative):
    """Prove the public reader and planner reject sensitive destinations before I/O.

    Require: Every fixture path matches the existing deny policy.
    Guarantee: Neither existence checks nor file opens are attempted.
    Maintain: The test cannot read actual credentials.
    Assert: Both public entrypoints fail with WriteError rather than the I/O sentinel.
    """
    path = tmp_path / relative

    def forbidden_io(*args, **kwargs):
        raise AssertionError("filesystem access preceded denylist validation")

    monkeypatch.setattr(Path, "exists", forbidden_io)
    monkeypatch.setattr(Path, "open", forbidden_io)
    with pytest.raises(hw.WriteError, match="refusing to touch"):
        hw.read_existing(path)
    with pytest.raises(hw.WriteError, match="refusing to touch"):
        hw.plan([hw.Artifact(path, "{}")])


def test_plan_preflights_entire_batch_before_reading_allowed_paths(tmp_path, monkeypatch):
    """Keep a later forbidden artifact from causing earlier reads.

    Require: The batch contains an allowed file before a denylisted file.
    Guarantee: The entire batch is rejected without opening either file.
    Maintain: No filesystem content is required for the test.
    Assert: The reader is never reached.
    """
    monkeypatch.setattr(hw, "read_existing", lambda path: pytest.fail("reader reached before preflight"))
    with pytest.raises(hw.WriteError, match="refusing to touch"):
        hw.plan([hw.Artifact(tmp_path / "allowed.json", "{}"),
                 hw.Artifact(tmp_path / "hermes" / "config.yaml", "{}")])


def test_toml_blocks_with_secret_keys_are_refused():
    with pytest.raises(hw.WriteError, match="looks like a secret"):
        hw.compute(hw.Artifact(Path("c.toml"), 'model = "x"\napi_key = "k"', "tomlblock"), None)


def test_unknown_mode_is_an_error():
    with pytest.raises(hw.WriteError, match="unknown artifact mode"):
        hw.compute(hw.Artifact(Path("x"), "t", "nope"), None)


def test_plan_reports_new_change_identical_and_writes_nothing(tmp_path):
    existing = tmp_path / "a.md"
    existing.write_bytes(b"old\n")           # exact bytes: write_text would turn \n into \r\n on Windows
    same = tmp_path / "same.md"
    same.write_bytes(b"s\n")
    arts = [hw.Artifact(tmp_path / "new.md", "n\n"), hw.Artifact(existing, "new\n"), hw.Artifact(same, "s\n")]
    changes = hw.plan(arts)
    assert [c.status for c in changes] == ["NEW", "CHANGE", "IDENTICAL"]
    assert "-old" in changes[1].diff() and "+new" in changes[1].diff()
    assert not (tmp_path / "new.md").exists() and existing.read_bytes() == b"old\n"


def test_apply_backs_up_what_it_replaces_writes_atomically_and_skips_identical(tmp_path):
    target = tmp_path / "cfg" / "opencode.json"
    target.parent.mkdir()
    target.write_bytes(b'{"keep": 1}\n')
    new_file = tmp_path / "agents" / "x.md"
    arts = [hw.Artifact(target, '{"added": 2}', "jsonmerge"), hw.Artifact(new_file, "body\n")]
    backups = tmp_path / "backups"
    written = hw.apply(hw.plan(arts), backups)
    assert set(written) == {target, new_file}
    assert json.loads(target.read_text(encoding="utf-8")) == {"keep": 1, "added": 2}
    saved = list(backups.iterdir())
    assert len(saved) == 1 and saved[0].read_bytes() == b'{"keep": 1}\n'                 # only the replaced file
    assert not [p for p in target.parent.iterdir() if p.name.endswith(".tmp")]
    assert hw.apply(hw.plan(arts), backups) == []                                        # second run: nothing to do


def test_apply_refuses_a_denylisted_path_even_if_a_change_was_built_by_hand(tmp_path):
    bad = hw.Change(hw.Artifact(tmp_path / "litellm_config.yaml", "x"), None, "x")
    with pytest.raises(hw.WriteError, match="refusing to touch"):
        hw.apply([bad], tmp_path / "b")


def test_custom_markers_and_default_markers_do_not_touch_each_other(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text("keep = 1\n", encoding="utf-8")
    party = hw.Artifact(p, "party = 1", mode="tomlblock")
    mcp = hw.Artifact(p, "[mcp_servers.a]\nurl = \"u\"", mode="tomlblock", begin="# >>> mcp", end="# <<< mcp")
    hw.apply(hw.plan([party]), tmp_path / "b")
    hw.apply(hw.plan([mcp]), tmp_path / "b")
    both = p.read_text(encoding="utf-8")
    assert "party = 1" in both and "[mcp_servers.a]" in both and both.startswith("keep = 1\n")
    hw.apply(hw.plan([hw.Artifact(p, "party = 2", mode="tomlblock")]), tmp_path / "b")
    after_party = p.read_text(encoding="utf-8")
    assert "party = 2" in after_party and "party = 1" not in after_party and "[mcp_servers.a]" in after_party
    hw.apply(hw.plan([hw.Artifact(p, "[mcp_servers.b]", mode="tomlblock", begin="# >>> mcp", end="# <<< mcp")]),
             tmp_path / "b")
    final = p.read_text(encoding="utf-8")
    assert "[mcp_servers.b]" in final and "[mcp_servers.a]" not in final and "party = 2" in final


def test_expand_handles_home_absolute_and_root_relative(tmp_path, monkeypatch):
    monkeypatch.setattr(hw.Path, "home", classmethod(lambda cls: tmp_path / "home"))
    root = tmp_path / "root"
    assert hw.expand("~/.codex/config.toml", root) == tmp_path / "home" / ".codex" / "config.toml"
    assert hw.expand("claude/agents", root) == root / "claude" / "agents"
    assert hw.expand(str(tmp_path / "abs"), root) == tmp_path / "abs"
