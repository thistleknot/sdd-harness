"""Tests for the party renderers in render_agents.py (claude, codex, opencode, pi, docs, CLI).

Spec: C:/Users/user/.claude/plans/make-harness-render-and-install-the-party.md, sections 3-5.
Real tiers.toml and the real agent bodies are read; every write goes to a tmp home/root.
Run from ~/.harness: python -m pytest specs/test_render_party.py -q
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

import harness_write as hw
import render_agents as ra

try:
    import tomllib
except ModuleNotFoundError:  # py310 pin
    import tomli as tomllib


@pytest.fixture
def schema() -> dict:
    return ra.load_schema()


@pytest.fixture
def home(tmp_path, monkeypatch) -> Path:
    """Home and harness root both point into tmp_path, so nothing real is written."""
    monkeypatch.setattr(hw.Path, "home", classmethod(lambda cls: tmp_path / "home"))
    monkeypatch.setattr(ra, "ROOT", tmp_path / "root")
    return tmp_path / "home"


def by_name(arts) -> dict:
    return {a.path.name: a for a in arts}


def body_of(name: str) -> str:
    return ra._source(name)[1]


def frontmatter(text: str) -> dict:
    assert text.startswith("---\n")
    block, _, _ = text[4:].partition("\n---\n")
    return yaml.safe_load(block)


# ---- claude ----------------------------------------------------------------------------

def test_claude_party_artifacts_equal_the_legacy_render_byte_for_byte(schema, home):
    arts = by_name(ra.render_party(schema, "claude").artifacts)
    legacy = ra.render_all(schema, "claude")
    assert {n[:-3] for n in arts} == set(legacy) == {"reader", "doer", "oracle"}
    for name, text in legacy.items():
        assert arts[f"{name}.md"].text == text and arts[f"{name}.md"].mode == "file"
    assert arts["doer.md"].path.parent == ra.ROOT / "claude" / "agents"


def test_a_window_that_squashes_the_oracle_into_the_leader_drops_its_agent_file(schema, home):
    out = ra.render_party(schema, "claude", window=(0, 2))
    assert sorted(by_name(out.artifacts)) == ["doer.md", "reader.md"]
    assert any("oracle squashed into leader" in n for n in out.notes)


def test_leader_flag_sets_claude_session_defaults_only_when_asked(schema, home):
    assert [a for a in ra.render_party(schema, "claude").artifacts if a.mode == "jsonmerge"] == []
    arts = ra.render_party(schema, "claude", leader=True).artifacts
    patch = json.loads(next(a for a in arts if a.mode == "jsonmerge").text)
    assert patch == {"model": "claude-sonnet-5-5", "effortLevel": "medium"}


def test_yaml_scalar_quotes_only_what_strict_yaml_would_reject():
    assert ra.yaml_scalar("plain prose with (parens), commas and a/b") == "plain prose with (parens), commas and a/b"
    for text in ("One of a team: fills the bodies", "ends with colon:", "has a #comment", " padded", "", "- dash", "[x] y",
                 "'quoted'"):
        out = ra.yaml_scalar(text)
        assert out.startswith('"') and yaml.safe_load("d: " + out)["d"] == text, text


def test_a_quoted_description_reads_back_as_plain_text_and_re_renders_identically():
    desc = "Fighter (doer, coder). One of a team: fills the bodies; the Leader's call: escalate."
    line = f"name: x\ndescription: {ra.yaml_scalar(desc)}\nmodel: m"
    assert ra.read_description(line) == desc
    resolved = {"name": "x", "model": "m", "effort_key": "effort", "effort_value": "low", "tools": ["Read"]}
    text = ra.render_claude(resolved, desc, "body\n")
    assert yaml.safe_load(text[4:].partition("\n---\n")[0])["description"] == desc
    assert ra.read_description(ra.split_frontmatter(text)[0]) == desc


def test_every_generated_claude_agent_is_strict_yaml_and_matches_its_vault_file(schema, home):
    rendered = ra.render_all(schema, "claude")
    for name, text in rendered.items():
        fm = yaml.safe_load(ra.split_frontmatter(ra.normalize(text))[0])      # the check Claude Code's loader needs
        assert fm["name"] == name and fm["tools"] and fm["model"], name
        assert text == ra.read_exact(ra.SOURCE_AGENTS / f"{name}.md"), f"{name}: vault file drifted from the render"


# ---- codex -----------------------------------------------------------------------------

def test_codex_agent_files_are_valid_toml_with_the_documented_keys(schema, home):
    arts = by_name(ra.render_party(schema, "codex", "openai").artifacts)
    for role, model, effort, sandbox in [("reader", "gpt-5.4-mini", "low", "read-only"),
                                         ("doer", "gpt-5.4-mini", "low", "workspace-write"),
                                         ("oracle", "gpt-6.1-sol", "high", "workspace-write")]:
        text = arts[f"{role}-openai.toml"].text
        data = tomllib.loads(text)
        assert set(data) == {"name", "description", "model", "model_reasoning_effort", "sandbox_mode",
                             "developer_instructions"}
        assert (data["name"], data["model"], data["model_reasoning_effort"], data["sandbox_mode"]) == (
            f"{role}-openai", model, effort, sandbox)
        assert data["developer_instructions"] == body_of(role)
        assert "UNVERIFIED" in text.splitlines()[0]
    assert "enforced by the prompt, not the sandbox" in arts["oracle-openai.toml"].text
    assert "enforced by the prompt" not in arts["doer-openai.toml"].text


@pytest.mark.parametrize("body", ["plain\n", "has ''' triple single\n", 'back\\slash and """ triple double\n'])
def test_toml_multiline_round_trips_awkward_bodies(body):
    assert tomllib.loads("x = " + ra._toml_multiline(body))["x"] == body


def test_codex_profile_block_keeps_an_existing_config_valid_and_is_idempotent(schema, home):
    out = ra.render_party(schema, "codex", "openai")
    block = next(a for a in out.artifacts if a.mode == "tomlblock")
    existing = ('model = "gpt-5.4"\nmodel_reasoning_effort = "xhigh"\n\n[projects.\'C:\\Users\\user\\dev\']\n'
                'trust_level = "trusted"\n\n[profiles.local]\nmodel = "q"\n')
    ch = hw.compute(block, existing)
    data = tomllib.loads(ch.after)
    assert data["model_reasoning_effort"] == "xhigh" and data["profiles"]["local"] == {"model": "q"}
    p = data["profiles"]["party_oracle_openai"]
    assert p == {"model": "gpt-6.1-sol", "model_provider": "copilot-proxy", "model_reasoning_effort": "high"}
    assert set(k for k in data["profiles"] if k.startswith("party_")) == {
        "party_leader_openai", "party_reader_openai", "party_doer_openai", "party_oracle_openai"}
    assert hw.compute(block, ch.after).status == "IDENTICAL"


def test_codex_two_provider_templates_share_one_config_block(schema, home):
    arts = ra.render_party(schema, "codex").artifacts
    blocks = [a for a in arts if a.mode == "tomlblock"]
    assert len(blocks) == 1
    data = tomllib.loads(blocks[0].text)["profiles"]
    assert "party_leader_openai" in data and "party_leader_ollama" in data
    assert data["party_doer_ollama"]["model"] == "qwen3.5-oc:2b"
    assert len([a for a in arts if a.mode == "file"]) == 6                       # 3 agents x 2 providers


def test_codex_leader_keys_need_the_flag_and_a_single_provider(schema, home):
    assert not any(a.mode == "tomlkeys" for a in ra.render_party(schema, "codex", "openai").artifacts)
    arts = ra.render_party(schema, "codex", "openai", leader=True).artifacts
    keys = json.loads(next(a for a in arts if a.mode == "tomlkeys").text)
    assert keys == {"model": '"gpt-5.4"', "model_reasoning_effort": '"medium"', "model_provider": '"copilot-proxy"'}
    with pytest.raises(ra.RenderError, match="needs a single --provider"):
        ra.render_party(schema, "codex", leader=True)


# ---- opencode --------------------------------------------------------------------------

def test_opencode_openrouter_agents_carry_model_variant_and_permissions(schema, home):
    arts = by_name(ra.render_party(schema, "opencode", "openrouter").artifacts)
    doer = frontmatter(arts["doer-openrouter.md"].text)
    assert (doer["name"], doer["mode"], doer["model"], doer["variant"]) == (
        "doer-openrouter", "subagent", "openrouter/anthropic/claude-haiku-5.5", "party_low")
    assert doer["permission"]["bash"] == doer["permission"]["edit"] == "allow"
    reader = frontmatter(arts["reader-openrouter.md"].text)
    assert reader["permission"] == {"read": "allow", "grep": "allow", "glob": "allow", "list": "allow",
                                    "bash": "deny", "edit": "deny", "webfetch": "deny", "subtask": "deny"}
    oracle = frontmatter(arts["oracle-openrouter.md"].text)
    assert oracle["model"] == "openrouter/openai/gpt-5.6-sol" and oracle["variant"] == "party_high"
    assert oracle["permission"]["edit"] == "allow"                                # Write maps to edit
    assert arts["doer-openrouter.md"].text.endswith(body_of("doer"))


def test_opencode_variants_merge_into_the_existing_config_without_touching_the_rest(schema, home):
    arts = ra.render_party(schema, "opencode", "openrouter").artifacts
    patch = next(a for a in arts if a.mode == "jsonmerge")
    existing = ('{\n  // keep\n  "model": "openrouter/deepseek/deepseek-v4-flash",\n  "provider": {"openrouter": {'
                '"options": {"apiKey": "{env:OPENROUTER_API_KEY}"}, "models": {"deepseek/deepseek-v4-flash": {"name": "x"}}}}\n}\n')
    ch = hw.compute(patch, existing)
    data = json.loads(ch.after)
    models = data["provider"]["openrouter"]["models"]
    assert data["model"] == "openrouter/deepseek/deepseek-v4-flash"
    assert data["provider"]["openrouter"]["options"]["apiKey"] == "{env:OPENROUTER_API_KEY}"
    assert models["deepseek/deepseek-v4-flash"] == {"name": "x"}
    assert models["openai/gpt-5.6-sol"]["variants"]["party_high"] == {"reasoningEffort": "high"}   # observed live 2026-10-08
    assert models["anthropic/claude-haiku-5.5"]["variants"]["party_low"] == {"reasoning": {"effort": "low", "enabled": True}}
    assert set(models["anthropic/claude-sonnet-5.5"]["variants"]) == {"party_medium"}
    assert ch.warnings == ["the existing file has comments; they are dropped on write"]
    assert hw.compute(patch, ch.after).status == "IDENTICAL"


def test_openai_models_take_the_flat_reasoning_effort_and_other_vendors_the_nested_object():
    assert ra._opencode_variant("openai/gpt-5.6-sol", "high") == {"reasoningEffort": "high"}
    assert ra._opencode_variant("anthropic/claude-haiku-5.5", "low") == {"reasoning": {"effort": "low", "enabled": True}}
    assert ra._opencode_variant("deepseek/deepseek-v4-pro", "medium") == {"reasoning": {"effort": "medium", "enabled": True}}


def test_opencode_variants_replace_stale_party_keys_but_keep_the_operators_own_variants(schema, home):
    patch = next(a for a in ra.render_party(schema, "opencode", "openrouter").artifacts if a.mode == "jsonmerge")
    assert patch.owned_prefix == "party_"
    existing = json.dumps({"provider": {"openrouter": {"models": {"openai/gpt-5.6-sol": {
        "name": "mine", "variants": {"party_high": {"reasoning": {"effort": "high", "enabled": True}},
                                     "lean": {"reasoningEffort": "low"}}}}}}})
    sol = json.loads(hw.compute(patch, existing).after)["provider"]["openrouter"]["models"]["openai/gpt-5.6-sol"]
    assert sol["variants"]["party_high"] == {"reasoningEffort": "high"}           # no stale nested reasoning beside it
    assert sol["variants"]["lean"] == {"reasoningEffort": "low"}                  # the operator's own variant survives
    assert sol["name"] == "openai/gpt-5.6-sol"                                    # the patch owns the name it sets


def test_combine_keeps_the_owned_prefix_when_two_templates_merge_into_one_config(tmp_path):
    p = tmp_path / "o.json"
    a = hw.Artifact(p, '{"a": 1}', "jsonmerge", owned_prefix="party_")
    b = hw.Artifact(p, '{"b": 2}', "jsonmerge")
    assert ra.combine([a, b])[0].owned_prefix == "party_"


def test_opencode_ollama_template_has_no_variant_and_says_effort_is_advisory(schema, home):
    out = ra.render_party(schema, "opencode", "ollama")
    arts = by_name(out.artifacts)
    fm = frontmatter(arts["doer-ollama.md"].text)
    assert fm["model"] == "ollama/qwen3.5-oc:2b" and "variant" not in fm
    assert not any(a.mode == "jsonmerge" for a in out.artifacts)
    assert any("effort is not expressible for ollama" in n for n in out.notes)


def test_opencode_renders_both_provider_templates_as_separate_files(schema, home):
    names = sorted(by_name(ra.render_party(schema, "opencode").artifacts))
    assert [n for n in names if n.endswith(".md")] == sorted(
        f"{r}-{p}.md" for p in ("openrouter", "ollama") for r in ("reader", "doer", "oracle"))


# ---- pi --------------------------------------------------------------------------------

def _pi_models(home: Path, provider: str, ids: list) -> None:
    path = home / ".pi" / "agent" / "models.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"providers": {provider: {"models": [{"id": i} for i in ids]}}}), encoding="utf-8")


def test_pi_agents_use_thinking_and_a_tools_allowlist(schema, home):
    _pi_models(home, "ollama", ["qwen3.5-oc:2b", "qwopus-coding-thinking-256k:9b"])
    out = ra.render_party(schema, "pi", "ollama")
    arts = by_name(out.artifacts)
    reader, doer, oracle = (frontmatter(arts[f"{r}-ollama.md"].text) for r in ("reader", "doer", "oracle"))
    tools = lambda fm: set(fm["tools"].split(", "))          # order follows the role's tool list; pi ignores it
    assert tools(reader) == {"read", "grep", "find", "ls"} and reader["thinking"] == "low"
    assert reader["model"] == "ollama/qwen3.5-oc:2b"
    assert tools(doer) == {"read", "grep", "find", "ls", "bash", "edit", "write"} and doer["thinking"] == "low"
    assert tools(oracle) == {"read", "bash", "grep", "find", "ls", "write"} and oracle["thinking"] == "high"
    assert "edit" not in tools(oracle)
    assert (doer["systemPromptMode"], doer["defaultContext"], doer["inheritSkills"]) == ("replace", "fork", False)
    assert not [n for n in out.notes if n.startswith("SKIP")]


def test_pi_skips_roles_whose_models_are_missing_from_models_json(schema, home):
    _pi_models(home, "ollama", ["qwopus-coding-thinking-256k:9b"])                 # the L0 model is missing
    out = ra.render_party(schema, "pi", "ollama")
    assert sorted(by_name(out.artifacts)) == ["oracle-ollama.md"]
    assert any("SKIP pi/ollama reader" in n and "not in pi's models.json" in n for n in out.notes)
    assert any("SKIP pi/ollama doer" in n and "not in pi's models.json" in n for n in out.notes)


def test_pi_without_a_models_file_renders_nothing_and_says_why(schema, home):
    out = ra.render_party(schema, "pi", "openrouter")
    assert out.artifacts == [] and sum(n.startswith("pi/openrouter: SKIP") for n in out.notes) == 3


def test_pi_leader_settings_need_the_flag_and_a_known_model(schema, home):
    _pi_models(home, "ollama", ["qwen3.5-oc:2b", "qwopus-coding-thinking-256k:9b"])
    assert not any(a.mode == "jsonmerge" for a in ra.render_party(schema, "pi", "ollama").artifacts)
    arts = ra.render_party(schema, "pi", "ollama", leader=True).artifacts
    patch = json.loads(next(a for a in arts if a.mode == "jsonmerge").text)
    assert patch == {"defaultProvider": "ollama", "defaultModel": "qwopus-coding-thinking-256k:9b",
                     "defaultThinkingLevel": "medium"}


# ---- instruction documents -------------------------------------------------------------

@pytest.mark.parametrize("harness,suffix", [("kiro", ".kiro/steering/party.md"), ("gemini", ".gemini/GEMINI.md"),
                                            ("hermes", "AppData/Local/hermes/SOUL.md")])
def test_instruction_documents_carry_the_roster_the_models_and_the_rules(schema, home, harness, suffix):
    (art,) = ra.render_party(schema, harness).artifacts
    assert art.mode == "mdblock" and art.path.as_posix().endswith(suffix)
    assert "| leader | L1 | medium -> high | the session |" in art.text
    assert "| anthropic | claude-haiku-5-5 | claude-sonnet-5-5 | claude-sonnet-5-5 |" in art.text
    assert "Orchestration routing: a party on an accordion" in art.text and "UNVERIFIED" in art.text


def test_a_hermes_soul_file_keeps_everything_outside_the_block(schema, home):
    (art,) = ra.render_party(schema, "hermes").artifacts
    soul = "# Identity\n\nI am a careful assistant.\n"
    ch = hw.compute(art, soul)
    assert ch.after.startswith(soul.rstrip("\n")) and ch.after.count(hw.MD_BEGIN) == 1
    assert hw.compute(art, ch.after).status == "IDENTICAL"


# ---- errors, combine, guards -----------------------------------------------------------

def test_unknown_harness_and_a_harness_with_neither_providers_nor_doc_are_errors(schema, home):
    with pytest.raises(ra.RenderError, match="unknown harness"):
        ra.render_party(schema, "nope")
    schema["harness"]["bare"] = {"providers": []}
    with pytest.raises(ra.RenderError, match="neither providers nor a doc"):
        ra.render_party(schema, "bare")
    with pytest.raises(ra.RenderError, match="cannot speak provider"):
        ra.render_party(schema, "claude", "openrouter")


def test_combine_merges_blocks_and_json_and_rejects_collisions(tmp_path):
    p = tmp_path / "x"
    a, b = hw.Artifact(p, '{"a": {"x": 1}}', "jsonmerge"), hw.Artifact(p, '{"a": {"y": 2}}', "jsonmerge")
    assert json.loads(ra.combine([a, b])[0].text) == {"a": {"x": 1, "y": 2}}
    t = ra.combine([hw.Artifact(p, "one\n", "tomlblock"), hw.Artifact(p, "two\n", "tomlblock")])
    assert t[0].text == "one\n\ntwo"
    with pytest.raises(ra.RenderError, match="same file"):
        ra.combine([hw.Artifact(p, "1"), hw.Artifact(p, "2")])
    with pytest.raises(ra.RenderError, match="set model differently"):
        ra.combine([hw.Artifact(p, '{"model": "1"}', "tomlkeys"), hw.Artifact(p, '{"model": "2"}', "tomlkeys")])


def test_every_harness_renders_and_none_of_it_trips_the_secret_or_denylist_guards(schema, home):
    _pi_models(home, "ollama", ["qwen3.5-oc:2b", "qwopus-coding-thinking-256k:9b"])
    for name in schema["harness"]:
        providers = schema["harness"][name].get("providers", [])
        for prov in providers or [None]:
            out = ra.render_party(schema, name, prov, leader=bool(providers))
            for art in out.artifacts:
                hw.compute(art, None)                       # raises on a secret-looking key or a denylisted path


# ---- cli -------------------------------------------------------------------------------

def test_plan_writes_nothing_and_apply_writes_with_backups_then_check_passes(schema, home, tmp_path, capsys):
    cfg = home / ".codex" / "config.toml"
    cfg.parent.mkdir(parents=True)
    cfg.write_bytes(b'model = "gpt-5.4"\n')
    argv = ["--harness", "codex", "--provider", "openai"]
    assert ra.main(argv + ["--plan"]) == 0
    assert cfg.read_bytes() == b'model = "gpt-5.4"\n' and not (home / ".skills").exists()
    assert ra.main(argv + ["--check"]) == 1                                         # drift: nothing applied yet

    assert ra.main(argv + ["--apply"]) == 0
    assert hw.TOML_BEGIN in cfg.read_text(encoding="utf-8")
    assert tomllib.loads(cfg.read_text(encoding="utf-8"))["model"] == "gpt-5.4"
    assert (home / ".skills" / "codex-agents" / "oracle-openai.toml").exists()
    backups = list((ra.ROOT / "backups").iterdir())
    assert len(backups) == 1 and next(backups[0].iterdir()).read_bytes() == b'model = "gpt-5.4"\n'

    assert ra.main(argv + ["--check"]) == 0                                         # idempotent
    capsys.readouterr()
    assert ra.main(argv + ["--apply"]) == 0 and "nothing to write" in capsys.readouterr().out


def test_cli_requires_an_action_and_reports_errors_with_exit_two(schema, home, capsys):
    with pytest.raises(SystemExit):
        ra.main(["--harness", "codex"])
    assert ra.main(["--harness", "nope", "--plan"]) == 2
    assert "unknown harness" in capsys.readouterr().err
    assert ra.main(["--harness", "codex", "--provider", "ollama", "--window", "0:9", "--plan"]) == 2
    assert "outside the 4-step dial" in capsys.readouterr().err


def test_open_ended_windows_resolve_per_provider(schema, home, capsys):
    assert ra.main(["--harness", "codex", "--window", "1:", "--plan"]) == 0          # 1: means 1..last of each dial
    out = capsys.readouterr()
    assert "window 1:5" in out.out and "window 1:3" in out.out
