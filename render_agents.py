"""Render the party into every harness's native agent settings.

Spec: C:/Users/user/.claude/plans/make-harness-render-and-install-the-party.md
      (operator instruction 2026-10-08: ~/.harness holds agent settings across harness
      platforms; models are a wrapper layer restricted by provider, so each provider is its
      own template and a harness renders every template it can speak).
Task: plan layers 2-3.

Reads tiers.toml (roles, provider bindings, harness table) + the agent bodies in
claude/agents/*.md, resolves the party against a provider's dial (party.py), and emits
harness-native artifacts (harness_write.py applies them safely).

Two paths live here:

  LEGACY (claude only, byte-exact):  --harness claude --check | --out DIR
      Renders claude/agents/*.md from tiers.toml and proves the identity transform.
  PARTY (every harness):  --harness NAME|all [--provider P|all] [--window lo:hi]
                          [--leader] (--plan | --check | --apply)
      claude    agents/*.md in the vault (sync-to-claude.ps1 copies them to ~/.claude)
      codex     agent TOMLs + [profiles.party_*] in config.toml (marker block)
      opencode  agents/<role>-<provider>.md + effort variants merged into opencode.json
      pi        ~/.pi/agent/agents/<role>-<provider>.md (refuses a model not in models.json)
      kiro, gemini, hermes   one instruction document each: their native agent formats
                             are unverified on this machine

Nothing is written without --apply; --apply backs up first. --leader additionally sets the
session defaults (the Leader's own model and effort) and needs a single --provider.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import difflib
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

try:  # 3.11+
    import tomllib
except ModuleNotFoundError:  # 3.10 pin, see manifest.toml [runtime]
    import tomli as tomllib

import harness_write as hw
from harness_write import Artifact
from party import Party, PartyError, RoleSetting, parse_open_window, report, resolve_party

ROOT = Path(__file__).resolve().parent
TIERS = ROOT / "tiers.toml"
SOURCE_AGENTS = ROOT / "claude" / "agents"
RULES = ROOT / "claude" / "rules" / "orchestration.md"

FENCE = "---"


class RenderError(RuntimeError):
    """Raised when the schema cannot produce a usable agent definition."""


# --- source parsing ----------------------------------------------------------

def read_exact(path: Path) -> str:
    """Read without newline translation, so CRLF survives the round trip."""
    with path.open("r", encoding="utf-8", newline="") as fh:
        return fh.read()


def write_exact(path: Path, text: str) -> None:
    """Write without newline translation; `text` already carries its own."""
    with path.open("w", encoding="utf-8", newline="") as fh:
        fh.write(text)


def detect_newline(raw: str) -> str:
    """Newline style of the source, so the render can put it back.

    The agent files are CRLF. A renderer that quietly emits LF would rewrite
    every line of every file for zero semantic change, and --check could never
    prove the identity transform it exists to prove.
    """
    return "\r\n" if "\r\n" in raw else "\n"


def normalize(raw: str) -> str:
    return raw.replace("\r\n", "\n").replace("\r", "\n")


def split_frontmatter(text: str) -> tuple[str, str]:
    """Return (frontmatter_block, body). Frontmatter excludes the --- fences.

    Expects LF-normalized text. The body is returned byte-exact including its
    trailing newline -- slicing, not splitlines()/join(), because the round trip
    through a line list silently eats the final newline.

    Raises RenderError if the file is not fenced, rather than guessing -- a
    silently body-only agent would render as an empty definition.
    """
    opening = FENCE + "\n"
    if not text.startswith(opening):
        raise RenderError("file does not open with a --- frontmatter fence")
    rest = text[len(opening):]

    marker = "\n" + FENCE + "\n"
    idx = rest.find(marker)
    if idx != -1:
        return rest[:idx], rest[idx + len(marker):]

    # closing fence sitting at EOF with no trailing newline
    tail = "\n" + FENCE
    if rest.endswith(tail):
        return rest[: -len(tail)], ""

    raise RenderError("frontmatter fence is never closed")


def read_description(frontmatter: str) -> str:
    """Pull the description line out of existing frontmatter.

    Descriptions are hand-written routing prose, not policy, so they survive
    rendering. Multi-line YAML is not supported here because none of the
    current agents use it; we raise instead of silently truncating.
    """
    for line in frontmatter.splitlines():
        if line.startswith("description:"):
            value = line[len("description:"):].strip()
            if len(value) >= 2 and value[0] == value[-1] == '"':
                try:
                    return json.loads(value)           # a quoted description is read back as plain text
                except json.JSONDecodeError:
                    pass
            return value
    raise RenderError("no description: key in frontmatter")


def yaml_scalar(text: str) -> str:
    """A YAML-safe one-line scalar: plain when that is valid, double-quoted when it is not.

    OBSERVED 2026-10-08: Claude Code did not register an agent whose unquoted description held
    ': ' (strict YAML rejects it: 'mapping values are not allowed here'), while a plain one
    loaded. Quoting only when needed keeps already-valid files byte-identical.
    """
    needs = (": " in text or " #" in text or text != text.strip() or text == ""
             or text[0] in "'\"[]{}&*!|>%@`,#?-" or text.endswith(":"))
    return json.dumps(text, ensure_ascii=False) if needs else text


# --- schema ------------------------------------------------------------------

def load_schema(path: Path = TIERS) -> dict:
    with path.open("rb") as fh:
        return tomllib.load(fh)


def _binding(schema: dict, name: str) -> tuple[str, dict]:
    """A provider key, or a harness name that maps to its first provider."""
    bindings = schema["binding"]
    if name in bindings:
        return name, bindings[name]
    speaks = schema.get("harness", {}).get(name, {}).get("providers") or []
    if speaks and speaks[0] in bindings:
        return speaks[0], bindings[speaks[0]]
    raise RenderError(f"no binding for {name!r}; providers: {sorted(bindings)}")


def binding_warnings(schema: dict, harness: str, today: _dt.date | None = None) -> list[str]:
    """Stale / unbound checks. Warnings, never silent substitutions."""
    today = today or _dt.date.today()
    _, binding = _binding(schema, harness)
    warnings: list[str] = []

    tiers = sorted(schema.get("tier") or ("L1", "L2", "L3"))
    unbound = [t for t in tiers if not binding.get(t)]
    if unbound:
        warnings.append(f"{harness}: tiers {', '.join(unbound)} are unbound (empty model id)")

    resolved = binding.get("resolved", "")
    if not resolved:
        warnings.append(f"{harness}: binding has no resolved date")
    else:
        age = (today - _dt.date.fromisoformat(resolved)).days
        limit = schema.get("stale_after_days", 90)
        if age > limit:
            warnings.append(
                f"{harness}: binding resolved {resolved} is {age}d old (limit {limit}d) -- "
                "re-confirm model ids before trusting this render"
            )
    return warnings


def resolve(schema: dict, harness: str, role_key: str) -> dict:
    """Role + harness -> the concrete values a renderer needs (legacy claude path)."""
    role = schema["role"][role_key]
    _, binding = _binding(schema, harness)
    tier = role["tier"]

    model = binding.get(tier, "")
    if not model:
        raise RenderError(f"{harness} has no model bound to {tier} (needed by role {role_key})")

    reasoning = role["reasoning"]
    effort_map = binding["effort_map"]
    if reasoning not in effort_map:
        raise RenderError(f"{harness} effort_map has no entry for reasoning={reasoning!r}")

    return {
        "name": role["name"],
        "tier": tier,
        "model": model,
        "effort_key": binding["effort_key"],
        "effort_value": effort_map[reasoning],
        "tools": role["tools"],
    }


# --- legacy claude rendering (byte-exact) ------------------------------------

def render_claude(resolved: dict, description: str, body: str) -> str:
    """Claude Code: YAML frontmatter, flat tools[] allowlist, string effort."""
    tools = ", ".join(f'"{t}"' for t in resolved["tools"])
    front = [
        f"name: {resolved['name']}",
        f"description: {yaml_scalar(description)}",
        f"model: {resolved['model']}",
        f"{resolved['effort_key']}: {resolved['effort_value']}",
        f"tools: [{tools}]",
    ]
    return f"{FENCE}\n" + "\n".join(front) + f"\n{FENCE}\n" + body


RENDERERS = {"claude": render_claude}


def render_all(schema: dict, harness: str) -> dict[str, str]:
    """role name -> rendered file text, for every agent role in the schema."""
    if harness not in RENDERERS:
        raise RenderError(
            f"no renderer for harness {harness!r}; have {sorted(RENDERERS)}"
        )
    renderer = RENDERERS[harness]

    out: dict[str, str] = {}
    for role_key, role in schema["role"].items():
        if role.get("kind", "agent") != "agent":
            continue  # the Leader is the session, not an agent file
        res = resolve(schema, harness, role_key)
        src = SOURCE_AGENTS / f"{res['name']}.md"
        if not src.exists():
            raise RenderError(f"source body missing: {src}")
        raw = read_exact(src)
        eol = detect_newline(raw)
        front, body = split_frontmatter(normalize(raw))
        rendered = renderer(res, read_description(front), body)
        out[res["name"]] = rendered.replace("\n", eol)
    return out


# --- party rendering ---------------------------------------------------------

PI_TOOLS = {"Read": ["read"], "Grep": ["grep"], "Glob": ["find", "ls"], "Bash": ["bash"],
            "Edit": ["edit"], "Write": ["write"]}
OPENCODE_PERMS = {"Read": ["read"], "Grep": ["grep"], "Glob": ["glob", "list"], "Bash": ["bash"],
                  "Edit": ["edit"], "Write": ["edit"]}
ALL_OPENCODE_PERMS = ("read", "grep", "glob", "list", "bash", "edit", "webfetch", "subtask")
VARIANT_PROVIDERS = {"openrouter"}  # providers whose models take a reasoning variant in opencode.json


@dataclass
class Rendered:
    artifacts: list
    notes: list


def _source(name: str) -> tuple[str, str, str]:
    """(description, body, eol) of an agent's source file."""
    src = SOURCE_AGENTS / f"{name}.md"
    if not src.exists():
        raise RenderError(f"source body missing: {src}")
    raw = read_exact(src)
    front, body = split_frontmatter(normalize(raw))
    return read_description(front), body, detect_newline(raw)


def _model_id(schema: dict, harness: str, provider: str, model: str) -> str:
    fmt = schema["harness"][harness].get("model_fmt", "{id}")
    return fmt.format(provider=provider, id=model)


def _stem(schema: dict, harness: str, party: Party, role: RoleSetting) -> str:
    multi = len(schema["harness"][harness].get("providers", [])) > 1
    return f"{role.name}-{party.provider}" if multi else role.name


def _header(schema: dict, harness: str, provider: str, comment: str = "# ") -> str:
    verified = provider in schema["harness"][harness].get("verified", [])
    status = "verified live" if verified else "UNVERIFIED (no live probe recorded in tiers.toml)"
    return (f"{comment}generated by ~/.harness render_agents.py from tiers.toml -- do not edit; "
            f"{harness}/{provider}: {status}")


def _toml_str(s: str) -> str:
    return json.dumps(s, ensure_ascii=False)


def _yaml_str(s: str) -> str:
    """A double-quoted YAML scalar. Descriptions contain ': ', which a strict YAML parser rejects bare."""
    return json.dumps(s, ensure_ascii=False)


def _toml_multiline(body: str) -> str:
    if "'''" not in body:
        return "'''\n" + body + "'''"
    return '"""\n' + body.replace("\\", "\\\\").replace('"""', '\\"\\"\\"') + '"""'


def _sandbox(tools) -> str:
    return "workspace-write" if {"Edit", "Write"} & set(tools) else "read-only"


def _expand(schema: dict, harness: str, key: str) -> Path:
    spec = schema["harness"][harness].get(key)
    if not spec:
        raise RenderError(f"harness {harness!r} declares no {key!r} in tiers.toml")
    return hw.expand(spec, ROOT)


def party_claude(schema: dict, party: Party, leader: bool) -> Rendered:
    agent_dir = _expand(schema, "claude", "agent_dir")
    arts = []
    for r in party.agent_roles():
        description, body, eol = _source(r.name)
        resolved = {"name": r.name, "model": r.model, "effort_key": r.effort_key,
                    "effort_value": r.effort_value, "tools": list(r.tools)}
        text = render_claude(resolved, description, body).replace("\n", eol)
        arts.append(Artifact(agent_dir / f"{r.name}.md", text, "file"))
    if leader and party.leader():
        ld = party.leader()
        arts.append(Artifact(_expand(schema, "claude", "settings"),
                             json.dumps({"model": ld.model, "effortLevel": ld.effort_value}), "jsonmerge"))
    return Rendered(arts, list(party.warnings))


def party_codex(schema: dict, party: Party, leader: bool) -> Rendered:
    h = schema["harness"]["codex"]
    agent_dir, config = _expand(schema, "codex", "agent_dir"), _expand(schema, "codex", "config")
    provider_ref = h.get("provider_refs", {}).get(party.provider, party.provider)
    arts, profiles = [], []
    head = _header(schema, "codex", party.provider)
    for r in party.roles:
        if r.kind == "agent" and r.squashed_into is None:
            description, body, _ = _source(r.name)
            stem = _stem(schema, "codex", party, r)
            notes = ""
            if "Write" in r.tools and "Edit" not in r.tools:
                notes = "# the sandbox allows writes, so 'specs only, never code bodies' is enforced by the prompt, not the sandbox\n"
            text = (f"{head}\n{notes}name = {_toml_str(stem)}\ndescription = {_toml_str(description)}\n"
                    f"model = {_toml_str(_model_id(schema, 'codex', party.provider, r.model))}\n"
                    f"{r.effort_key} = {_toml_str(r.effort_value)}\n"
                    f"sandbox_mode = {_toml_str(_sandbox(r.tools))}\n"
                    f"developer_instructions = {_toml_multiline(body)}\n")
            arts.append(Artifact(agent_dir / f"{stem}.toml", text, "file"))
        if r.squashed_into is None:
            profiles.append(f"[profiles.party_{r.role}_{party.provider}]\n"
                            f"model = {_toml_str(_model_id(schema, 'codex', party.provider, r.model))}\n"
                            f"model_provider = {_toml_str(provider_ref)}\n"
                            f"{r.effort_key} = {_toml_str(r.effort_value)}")
    arts.append(Artifact(config, "\n\n".join(profiles), "tomlblock"))
    if leader and party.leader():
        ld = party.leader()
        arts.append(Artifact(config, json.dumps({
            "model": _toml_str(_model_id(schema, "codex", party.provider, ld.model)),
            ld.effort_key: _toml_str(ld.effort_value),
            "model_provider": _toml_str(provider_ref)}), "tomlkeys"))
    return Rendered(arts, list(party.warnings))


def _opencode_frontmatter(schema: dict, party: Party, r: RoleSetting, description: str, stem: str) -> str:
    perms = {p: "deny" for p in ALL_OPENCODE_PERMS}
    for tool in r.tools:
        for p in OPENCODE_PERMS.get(tool, []):
            perms[p] = "allow"
    lines = [FENCE, _header(schema, "opencode", party.provider), f"name: {stem}", f"description: {_yaml_str(description)}",
             "mode: subagent", f"model: {_model_id(schema, 'opencode', party.provider, r.model)}"]
    if party.provider in VARIANT_PROVIDERS:
        lines.append(f"variant: party_{r.effort}")
    lines.append("permission:")
    lines += [f"  {p}: {perms[p]}" for p in ALL_OPENCODE_PERMS]
    lines.append(FENCE)
    return "\n".join(lines) + "\n"


def _opencode_variant(model: str, effort_value: str) -> dict:
    """The reasoning knob opencode accepts for this model.

    OBSERVED 2026-10-08 (opencode 1.17.11 + OpenRouter): opencode already sends a flat
    `reasoning_effort` for openai/* models, so the nested `reasoning` object collides with it
    ('"reasoning_effort" and "reasoning.effort" are both provided with conflicting values').
    openai/* therefore takes the flat `reasoningEffort`; other vendors (anthropic/*, ...) took
    the nested form (anthropic/claude-haiku-5.5 answered PONG with it).
    """
    if model.startswith("openai/"):
        return {"reasoningEffort": effort_value}
    return {"reasoning": {"effort": effort_value, "enabled": True}}


def party_opencode(schema: dict, party: Party, leader: bool) -> Rendered:
    agent_dir, config = _expand(schema, "opencode", "agent_dir"), _expand(schema, "opencode", "config")
    arts, notes = [], list(party.warnings)
    for r in party.agent_roles():
        description, body, _ = _source(r.name)
        stem = _stem(schema, "opencode", party, r)
        arts.append(Artifact(agent_dir / f"{stem}.md", _opencode_frontmatter(schema, party, r, description, stem) + body, "file"))
    if party.provider in VARIANT_PROVIDERS:
        models: dict = {}
        for r in party.roles:
            if r.squashed_into is None:
                models.setdefault(r.model, {"name": r.model, "variants": {}})["variants"][f"party_{r.effort}"] = \
                    _opencode_variant(r.model, r.effort_value)
        arts.append(Artifact(config, json.dumps({"provider": {party.provider: {"models": models}}}), "jsonmerge",
                             owned_prefix="party_"))
    else:
        notes.append(f"opencode: effort is not expressible for {party.provider} models (no reasoning variant known); "
                     "the model is set, the effort is advisory")
    if leader and party.leader():
        ld = party.leader()
        arts.append(Artifact(config, json.dumps({"model": _model_id(schema, "opencode", party.provider, ld.model)}), "jsonmerge"))
    return Rendered(arts, notes)


def _pi_known_models(schema: dict, provider: str) -> set | None:
    path = _expand(schema, "pi", "models")
    existing = hw.read_existing(path)
    if existing is None:
        return None
    try:
        data = hw.load_jsonc(existing)
    except hw.WriteError:
        return None
    models = data.get("providers", {}).get(provider, {}).get("models", [])
    return {m.get("id") for m in models if isinstance(m, dict)}


def party_pi(schema: dict, party: Party, leader: bool) -> Rendered:
    agent_dir = _expand(schema, "pi", "agent_dir")
    known = _pi_known_models(schema, party.provider)
    arts, notes = [], list(party.warnings)
    for r in party.agent_roles():
        if known is None or r.model not in known:
            notes.append(f"SKIP pi/{party.provider} {r.name}: model {r.model!r} is not in pi's models.json "
                         f"(providers.{party.provider}.models); add it there first")
            continue
        description, body, _ = _source(r.name)
        stem = _stem(schema, "pi", party, r)
        tools = []
        for t in r.tools:
            tools += [x for x in PI_TOOLS.get(t, []) if x not in tools]
        front = [FENCE, _header(schema, "pi", party.provider), f"name: {stem}", f"description: {_yaml_str(description)}",
                 f"model: {_model_id(schema, 'pi', party.provider, r.model)}", f"{r.effort_key}: {r.effort_value}",
                 "systemPromptMode: replace", "inheritProjectContext: true", "inheritSkills: false",
                 f"tools: {', '.join(tools)}", "defaultContext: fork", FENCE]
        arts.append(Artifact(agent_dir / f"{stem}.md", "\n".join(front) + "\n" + body, "file"))
    if leader and party.leader() and known is not None and party.leader().model in known:
        ld = party.leader()
        arts.append(Artifact(_expand(schema, "pi", "settings"), json.dumps({
            "defaultProvider": party.provider, "defaultModel": ld.model, "defaultThinkingLevel": ld.effort_value}), "jsonmerge"))
    return Rendered(arts, notes)


def party_doc(schema: dict, harness: str) -> Rendered:
    """Instruction document for a harness whose native agent format is unverified here."""
    path = _expand(schema, harness, "doc")
    lines = ["# Party (generated)", "",
             f"Generated by ~/.harness for {harness}. Its native agent format is UNVERIFIED on this machine, so this is an "
             "instruction document, not an agent definition. Edit tiers.toml and claude/rules/orchestration.md, not this block.",
             "", "## Roles", "", "| Role | Tier | Effort floor -> ceiling | Tools |", "|---|---|---|---|"]
    for key, role in schema["role"].items():
        lines.append(f"| {key} | {role['tier']} | {role['reasoning']} -> {role.get('ceiling', role['reasoning'])} | "
                     f"{', '.join(role.get('tools', [])) or 'the session'} |")
    lines += ["", "## Models by provider", "", "| Provider | light (L0) | mid (L1) | heavy (L3) |", "|---|---|---|---|"]
    for name, b in schema["binding"].items():
        lines.append(f"| {name} | {b.get('L0') or '-'} | {b.get('L1') or '-'} | {b.get('L3') or '-'} |")
    rules = normalize(read_exact(RULES)) if RULES.exists() else ""
    return Rendered([Artifact(path, "\n".join(lines) + "\n\n" + rules.strip("\n") + "\n", "mdblock")], [])


PARTY_RENDERERS = {"claude": party_claude, "codex": party_codex, "opencode": party_opencode, "pi": party_pi}


def combine(artifacts: list) -> list:
    """Merge artifacts that target the same file+mode (two provider templates share one config)."""
    groups: dict = {}
    for a in artifacts:
        groups.setdefault((a.path, a.mode), []).append(a)
    out = []
    for (path, mode), group in groups.items():
        if len(group) == 1:
            out.append(group[0])
        elif mode == "file":
            raise RenderError(f"two templates would write the same file {path}")
        elif mode == "jsonmerge":
            merged: dict = {}
            for a in group:
                merged = hw.deep_merge(merged, json.loads(a.text))
            out.append(Artifact(path, json.dumps(merged), mode, owned_prefix=next((a.owned_prefix for a in group if a.owned_prefix), "")))
        elif mode in ("tomlblock", "mdblock"):
            out.append(Artifact(path, "\n\n".join(a.text.strip("\n") for a in group), mode))
        else:
            keys: dict = {}
            for a in group:
                for k, v in json.loads(a.text).items():
                    if k in keys and keys[k] != v:
                        raise RenderError(f"two templates set {k} differently in {path}")
                    keys[k] = v
            out.append(Artifact(path, json.dumps(keys), mode))
    return out


def render_party(schema: dict, harness: str, provider: str | None = None, window: tuple | None = None,
                 leader: bool = False) -> Rendered:
    """All artifacts for one harness: every provider template it speaks, or just `provider`."""
    h = schema.get("harness", {}).get(harness)
    if h is None:
        raise RenderError(f"unknown harness {harness!r}; have {sorted(schema.get('harness', {}))}")
    speaks = h.get("providers", [])
    if not speaks:
        if "doc" not in h:
            raise RenderError(f"harness {harness!r} declares neither providers nor a doc")
        return party_doc(schema, harness)
    if harness not in PARTY_RENDERERS:
        raise RenderError(f"no renderer for harness {harness!r}; have {sorted(PARTY_RENDERERS)}")
    chosen = list(speaks) if provider in (None, "all") else [provider]
    if leader and len(chosen) != 1:
        raise RenderError("--leader sets one set of session defaults, so it needs a single --provider")
    arts, notes = [], []
    for prov in chosen:
        try:
            party = resolve_party(schema, harness, prov, window)
        except PartyError as exc:
            raise RenderError(str(exc)) from exc
        out = PARTY_RENDERERS[harness](schema, party, leader)
        arts += out.artifacts
        notes += [f"{harness}/{prov}: {n}" for n in out.notes]
        notes.append(report(party))
    return Rendered(combine(arts), notes)


# --- cli ---------------------------------------------------------------------

def _check(schema: dict, harness: str, rendered: dict[str, str]) -> int:
    drift = 0
    for name, text in sorted(rendered.items()):
        current_path = SOURCE_AGENTS / f"{name}.md"
        current = read_exact(current_path)
        if current == text:
            print(f"  IDENTICAL  {name}.md")
            continue
        drift += 1
        print(f"  DRIFT      {name}.md")
        diff = difflib.unified_diff(
            current.splitlines(keepends=True),
            text.splitlines(keepends=True),
            fromfile=f"current/{name}.md",
            tofile=f"rendered/{name}.md",
            n=1,
        )
        for line in diff:
            if line.startswith(("+++", "---", "@@", "+", "-")):
                print("    " + line.rstrip("\n"))
    return drift


def _legacy(args, schema: dict) -> int:
    for w in binding_warnings(schema, args.harness):
        print(f"WARNING: {w}", file=sys.stderr)

    try:
        rendered = render_all(schema, args.harness)
    except RenderError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    if args.check:
        drift = _check(schema, args.harness, rendered)
        print(f"\n{len(rendered)} agent(s), {drift} drifted")
        return 1 if drift else 0

    args.out.mkdir(parents=True, exist_ok=True)
    for name, text in sorted(rendered.items()):
        write_exact(args.out / f"{name}.md", text)
        print(f"  wrote {name}.md")
    return 0


def _party(args, schema: dict) -> int:
    names = sorted(schema.get("harness", {})) if args.harness == "all" else [args.harness]
    window = parse_open_window(args.window)
    drift = 0
    for name in names:
        try:
            out = render_party(schema, name, args.provider, window, args.leader)
            changes = hw.plan(out.artifacts)
        except (RenderError, hw.WriteError) as exc:
            print(f"ERROR: {name}: {exc}", file=sys.stderr)
            return 2
        print(f"== {name}: {len(changes)} artifact(s)")
        for note in out.notes:
            print(f"   {note}", file=sys.stderr if note.startswith(("SKIP", f"{name}/")) else sys.stdout)
        for ch in changes:
            for w in ch.warnings:
                print(f"   WARNING {ch.artifact.path}: {w}", file=sys.stderr)
            print(f"  {ch.status:9} {ch.artifact.path}")
            if ch.status != "IDENTICAL":
                drift += 1
                if args.plan:
                    print("".join("    " + ln for ln in ch.diff().splitlines(keepends=True)))
        if args.apply:
            backup = ROOT / "backups" / _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
            written = hw.apply(changes, backup)
            print(f"   wrote {len(written)} file(s); backups of replaced files in {backup}" if written
                  else "   nothing to write")
    return 1 if (args.check and drift) else 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--harness", required=True, help="claude, codex, opencode, pi, kiro, gemini, hermes, or all")
    ap.add_argument("--provider", help="one provider template, or all (default: every one the harness speaks)")
    ap.add_argument("--window", help="clamp the dial to lo:hi step indices, e.g. 0:2")
    ap.add_argument("--leader", action="store_true", help="also set the session defaults (the Leader); needs one --provider")
    ap.add_argument("--plan", action="store_true", help="show what would change (diffs), write nothing")
    ap.add_argument("--check", action="store_true", help="diff against current, write nothing; exit 1 on drift")
    ap.add_argument("--apply", action="store_true", help="write the artifacts, backing up what is replaced")
    ap.add_argument("--out", type=Path, help="legacy claude only: directory to write rendered agents into")
    args = ap.parse_args(argv)

    if not (args.check or args.out or args.plan or args.apply):
        ap.error("one of --plan, --check, --apply or --out is required")

    schema = load_schema()
    legacy = (args.harness == "claude" and (args.check or args.out) and not (
        args.provider or args.window or args.leader or args.plan or args.apply))
    return _legacy(args, schema) if legacy else _party(args, schema)


if __name__ == "__main__":
    raise SystemExit(main())
