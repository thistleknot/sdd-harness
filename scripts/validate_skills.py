"""Validate local skill package structure without changing the skill store.

| Stage | Mechanism | Contract | Req |
|---|---|---|---|
| DISCOVER | Find immediate child directories containing SKILL.md | [mandatory] | R58, R61 |
| PARSE | Read YAML frontmatter and check name/description | [mandatory] | R59 |
| REFERENCES | Resolve relative Markdown links from SKILL.md | [mandatory] | R59 |
| REPORT | Print findings and return a process status | [mandatory] | R60, R61 |

EARS guards:
- R1: The validator reads skill files and never modifies the supplied root.
- R2: Invalid frontmatter, mismatched directory names, and broken prose links are reported per skill; code examples are ignored.
- R3: The validator performs no model calls or network requests.
- R4: A missing or empty skill root returns failure.

CLOSED:
- Importing a plugin marketplace evaluator was rejected: the harness needs a small structural check first, and its skills remain owned by the separate ~/.skills store.
- LLM quality scoring was rejected for this gate: it would exceed the no-model contract and cannot replace file/reference integrity checks.

Preconditions: the root is readable; PyYAML is installed in the execution environment.
Failure modes: invalid root, missing SKILL.md metadata, malformed YAML, or unresolved local Markdown links produce a nonzero exit status.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from urllib.parse import urlsplit

import yaml


MARKDOWN_LINK = re.compile(r"!?\[[^\]]*\]\(([^)\s]+)(?:\s+[^)]*)?\)")


def validate_skill(skill_file: Path) -> list[str]:
    """Check one SKILL.md package's metadata and relative Markdown links.

    Args:
        skill_file: Path to the package's SKILL.md.

    Returns:
        Findings prefixed with the skill directory name; an empty list means valid.

    Raises:
        OSError: If the file cannot be read; callers should see the failure.

    Require: skill_file is named SKILL.md inside its owning skill directory.
    Guarantee: metadata and local Markdown targets are checked without writes.
    Maintain: Only relative file links are resolved; web URLs and anchors are ignored.
    Assert: Parsed frontmatter is a mapping with non-empty string name and description.
    """
    findings: list[str] = []
    text = skill_file.read_text(encoding="utf-8")
    lines = text.splitlines()
    label = skill_file.parent.name
    if not lines or lines[0].strip() != "---":
        return [f"{label}: missing opening YAML frontmatter fence"]

    try:
        closing = lines.index("---", 1)
    except ValueError:
        return [f"{label}: missing closing YAML frontmatter fence"]

    try:
        metadata = yaml.safe_load("\n".join(lines[1:closing]))
    except yaml.YAMLError as error:
        return [f"{label}: invalid YAML frontmatter: {error.problem or 'parse error'}"]
    if not isinstance(metadata, dict):
        return [f"{label}: frontmatter must be a YAML mapping"]

    name = metadata.get("name")
    description = metadata.get("description")
    if not isinstance(name, str) or not name.strip():
        findings.append(f"{label}: frontmatter name must be a non-empty string")
    elif name.strip() != label:
        findings.append(f"{label}: frontmatter name {name.strip()!r} does not match directory")
    if not isinstance(description, str) or not description.strip():
        findings.append(f"{label}: frontmatter description must be a non-empty string")

    prose_lines: list[str] = []
    fence: tuple[str, int] | None = None
    for line in text.splitlines():
        marker = re.match(r"^\s*(`{3,}|~{3,})", line)
        if fence is None and marker:
            run = marker.group(1)
            fence = (run[0], len(run))
            continue
        if fence is not None:
            if marker and marker.group(1)[0] == fence[0] and len(marker.group(1)) >= fence[1]:
                fence = None
            continue
        prose_lines.append(line)

    for match in MARKDOWN_LINK.finditer("\n".join(prose_lines)):
        target = match.group(1).strip().strip("<>")
        parsed = urlsplit(target)
        if parsed.scheme or target.startswith("//") or not parsed.path:
            continue
        destination = (skill_file.parent / parsed.path).resolve()
        if not destination.exists():
            findings.append(f"{label}: unresolved relative link {target!r}")

    return findings


def validate_root(root: Path) -> tuple[int, list[str]]:
    """Validate every immediate child skill package under a skill-store root.

    Args:
        root: Skill-store directory containing one directory per skill.

    Returns:
        A pair of discovered skill count and aggregated validation findings.

    Raises:
        OSError: If a discovered SKILL.md cannot be read.

    Require: root is an existing directory.
    Guarantee: Only immediate child directories with SKILL.md are scanned.
    Maintain: The skill store remains unchanged.
    Assert: An empty or missing root yields a finding and zero discovered skills.
    """
    if not root.is_dir():
        return 0, [f"skill root does not exist or is not a directory: {root}"]

    skill_files = sorted(root.glob("*/SKILL.md"))
    if not skill_files:
        return 0, [f"no immediate child SKILL.md files found under: {root}"]

    findings = [finding for skill_file in skill_files for finding in validate_skill(skill_file)]
    return len(skill_files), findings


def main(argv: list[str] | None = None) -> int:
    """Run the read-only skill package validator from the command line.

    Args:
        argv: Optional argument vector for tests; defaults to process arguments.

    Returns:
        Zero when all discovered skills pass, otherwise one.

    Require: --root names the skill-store directory to inspect.
    Guarantee: Findings are printed to stdout and invalid results return nonzero.
    Maintain: This command never writes to the skill store.
    Assert: No model, network, or mutation operation is invoked.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True, help="Skill store containing <name>/SKILL.md")
    args = parser.parse_args(argv)
    scanned, findings = validate_root(args.root)
    if findings:
        for finding in findings:
            print(f"FAIL {finding}")
        print(f"{scanned} skill(s) scanned; {len(findings)} finding(s)")
        return 1
    print(f"PASS {scanned} skill(s) scanned; no structural findings")
    return 0


if __name__ == "__main__":
    sys.exit(main())
