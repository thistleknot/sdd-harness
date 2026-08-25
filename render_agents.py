"""Render canonical agent definitions into harness-native form.

Reads tiers.toml (model policy) + the agent bodies, and emits frontmatter for
a chosen harness. The body prose is passed through untouched; only the
frontmatter is generated.

Why this exists
---------------
manifest.toml marks agents x claude as LINK, with the note "Markdown + YAML
frontmatter matches canonical form byte-for-byte." That is true, but it is true
by accident: the canonical source lives in claude/agents/ and carries
`model: claude-opus-5`, a vendor string. The formats match because the
canonical form IS the Claude form. Any second harness would have to either
inherit Claude's model ids or fork the files.

So agents x claude is not really LINK -- it is GENERATE that happens to be an
identity transform today. This module makes that explicit. Run with --check to
prove the identity still holds. One caveat, recorded in tiers.toml under
[binding.claude]: L3 and L2 bind to the same model id today, so the two tiers
are indistinguishable in rendered output.

Usage
-----
    python render_agents.py --harness claude --check      # diff, write nothing
    python render_agents.py --harness claude --out DIR    # render to DIR

Only claude has a renderer. codex, gemini and opencode carry bindings in
tiers.toml but no entry in RENDERERS, so --harness codex raises RenderError
until one is written.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import difflib
import sys
from pathlib import Path

try:  # 3.11+
    import tomllib
except ModuleNotFoundError:  # 3.10 pin, see manifest.toml [runtime]
    import tomli as tomllib

ROOT = Path(__file__).resolve().parent
TIERS = ROOT / "tiers.toml"
SOURCE_AGENTS = ROOT / "claude" / "agents"

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
            return line[len("description:"):].strip()
    raise RenderError("no description: key in frontmatter")


# --- schema ------------------------------------------------------------------

def load_schema(path: Path = TIERS) -> dict:
    with path.open("rb") as fh:
        return tomllib.load(fh)


def binding_warnings(schema: dict, harness: str, today: _dt.date | None = None) -> list[str]:
    """Stale / unbound checks. Warnings, never silent substitutions."""
    today = today or _dt.date.today()
    binding = schema["binding"][harness]
    warnings: list[str] = []

    unbound = sorted(t for t in ("L1", "L2", "L3") if not binding.get(t))
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
    """Role + harness -> the concrete values a renderer needs."""
    role = schema["role"][role_key]
    binding = schema["binding"][harness]
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


# --- rendering ---------------------------------------------------------------

def render_claude(resolved: dict, description: str, body: str) -> str:
    """Claude Code: YAML frontmatter, flat tools[] allowlist, string effort."""
    tools = ", ".join(f'"{t}"' for t in resolved["tools"])
    front = [
        f"name: {resolved['name']}",
        f"description: {description}",
        f"model: {resolved['model']}",
        f"{resolved['effort_key']}: {resolved['effort_value']}",
        f"tools: [{tools}]",
    ]
    return f"{FENCE}\n" + "\n".join(front) + f"\n{FENCE}\n" + body


RENDERERS = {"claude": render_claude}


def render_all(schema: dict, harness: str) -> dict[str, str]:
    """role name -> rendered file text, for every role in the schema."""
    if harness not in RENDERERS:
        raise RenderError(
            f"no renderer for harness {harness!r}; have {sorted(RENDERERS)}"
        )
    renderer = RENDERERS[harness]

    out: dict[str, str] = {}
    for role_key in schema["role"]:
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


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--harness", required=True)
    ap.add_argument("--check", action="store_true", help="diff against current, write nothing")
    ap.add_argument("--out", type=Path, help="directory to write rendered agents into")
    args = ap.parse_args(argv)

    schema = load_schema()

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

    if args.out:
        args.out.mkdir(parents=True, exist_ok=True)
        for name, text in sorted(rendered.items()):
            write_exact(args.out / f"{name}.md", text)
            print(f"  wrote {name}.md")
        return 0

    ap.error("one of --check or --out is required")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
