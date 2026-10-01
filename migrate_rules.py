"""One-shot migration: split live instruction files into ~/.rules canonical units.

Deliberately dumb. It does not merge, rewrite, or summarise anything -- every
output byte is copied from a source file. The only judgement it encodes is
where a section starts, and that is purely structural (H1/H2 begin a new unit;
H3+ stay with their parent).

Canonical format is Kiro steering-style frontmatter, because manifest.toml
already commits to it (manifest.toml:156, quoted in full):

    artifact="instructions" harness="kiro" strategy="LINK"
    note = "Native frontmatter == our interlingua, so this is the one lossless
            cell. Unenforced."

That last word is load-bearing and was dropped from an earlier draft of this
docstring. Nothing checks the LINK cell's losslessness, so the manifest is
asserting an intent, not a verified property. Treat it accordingly.

The interlingua is also thinner than "interlingua" suggests: kiro's frontmatter
is a single key -- inclusion -- across 15 files, 6 of which have no frontmatter
at all. That may still be the right target; it is not a rich one.

Run from the repo root:  python migrate_rules.py [--apply]
Without --apply it reports what it would write and touches nothing.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

HOME = Path.home()
RULES_ROOT = HOME / ".rules"

# (key, path, first filename ordinal). Ordinals keep source order stable and
# leave gaps so units can be inserted later without renumbering everything.
SOURCES = [
    ("claude", HOME / ".claude" / "CLAUDE.md", 10),
    ("opencode", HOME / ".config" / "opencode" / "AGENTS.md", 500),
]

# The single topic collision in the corpus. CLAUDE.md's version is a
# substantive superset; opencode's is kept for provenance but not rendered.
# Resolving this is a human call -- see the report at the end of the run.
# Maps loser (source, title) -> winner (source, title). Filenames are resolved
# after planning, never hardcoded: ordinals shift whenever a source gains a
# heading, and a stale pointer here is a dangling reference nothing catches.
SUPERSEDED = {("opencode", "Validation"): ("claude", "6. Validation")}

HEADING = re.compile(r"^(#{1,6})\s+(.*)$")


def read_exact(path: Path) -> str:
    """Read without newline translation, so CRLF survives the round trip."""
    with path.open("r", encoding="utf-8", newline="") as fh:
        return fh.read()


def write_exact(path: Path, text: str) -> None:
    """Write without newline translation; `text` already carries its own."""
    with path.open("w", encoding="utf-8", newline="") as fh:
        fh.write(text)


def slugify(title: str) -> str:
    t = re.sub(r"^\d+\.\s*", "", title.strip().lower())
    t = re.sub(r"[^a-z0-9]+", "-", t)
    return t.strip("-") or "untitled"


def split_units(raw: str) -> list[dict]:
    """Split a document into units. A unit starts at an H1 or H2; H3+ nest.

    Headings inside fenced code blocks are text, not structure.
    """
    units: list[dict] = []
    cur: dict | None = None
    fence = False
    for line in raw.split("\n"):
        s = line.rstrip("\r")
        if s.lstrip().startswith("```"):
            fence = not fence
        m = None if fence else HEADING.match(s)
        if m and len(m.group(1)) <= 2:
            if cur:
                units.append(cur)
            cur = {"level": len(m.group(1)), "title": m.group(2).strip(), "body": []}
        elif cur is not None:
            cur["body"].append(s)
        # Content before the first heading is a document preamble; the sources
        # have none, and silently inventing a home for it would be a guess.
    if cur:
        units.append(cur)
    return units


def render_unit(src_key: str, src_path: Path, unit: dict, superseded_by: str | None) -> str:
    body = "\n".join(unit["body"]).strip("\n")
    fm = [
        "---",
        "inclusion: always" if not superseded_by else "inclusion: auto",
        f"source: {src_key}",
        f"source_file: {src_path.as_posix()}",
        f"source_title: {unit['title']}",
    ]
    if superseded_by:
        fm.append(f"superseded_by: {superseded_by}")
    fm.append("---")
    return "\n".join(fm) + "\n\n" + f"# {unit['title']}\n\n" + body + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true", help="write files; default is a dry run")
    args = ap.parse_args(argv)

    # Pass 1: assign filenames. No rendering yet -- a superseded_by pointer can
    # name a unit from any source, including one not yet walked.
    staged: list[tuple[str, Path, dict, str]] = []
    for src_key, src_path, start in SOURCES:
        if not src_path.exists():
            print(f"  SKIP   {src_path} (missing)")
            continue
        raw = read_exact(src_path)
        units = split_units(raw)
        print(f"  {src_key:9s} {len(units):3d} units  <- {src_path}")
        for i, unit in enumerate(units):
            name = f"{start + i * 10:03d}-{slugify(unit['title'])}.md"
            staged.append((src_key, src_path, unit, name))

    by_title = {(k, u["title"]): n for k, _, u, n in staged}

    # Pass 2: resolve pointers against real filenames and render.
    planned: list[tuple[Path, str]] = []
    superseded_hits: list[str] = []
    total_body_lines = 0
    for src_key, src_path, unit, name in staged:
        sup = None
        winner = SUPERSEDED.get((src_key, unit["title"]))
        if winner:
            sup = by_title.get(winner)
            if sup is None:
                print(f"\n  ERROR superseded_by target not found: {winner}")
                return 1
            superseded_hits.append(f"{src_key}:{unit['title']} -> {sup}")
        planned.append((RULES_ROOT / name, render_unit(src_key, src_path, unit, sup)))
        total_body_lines += len([b for b in unit["body"] if b.strip()])

    names = [p.name for p, _ in planned]
    dupes = {n for n in names if names.count(n) > 1}
    if dupes:
        print(f"\n  ERROR filename collisions: {sorted(dupes)}")
        return 1

    print(f"\n  {len(planned)} units, {total_body_lines} non-blank body lines -> {RULES_ROOT}")
    for s in superseded_hits:
        print(f"  superseded (not rendered): {s}")

    if not args.apply:
        print("\n  dry run; pass --apply to write")
        return 0

    RULES_ROOT.mkdir(parents=True, exist_ok=True)
    for path, text in planned:
        write_exact(path, text)
    print(f"  wrote {len(planned)} files")
    return 0


if __name__ == "__main__":
    sys.exit(main())
