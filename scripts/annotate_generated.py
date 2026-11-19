"""Annotate pyecoregen output with decision backlinks lost during generation.

| Stage | Mechanism | Tag | Refs |
|---|---|---|---|
| INGEST | Parse the source Ecore XML and select decision EAnnotations | [mandatory] | SDD generation contract |
| SCORE | Normalize and sort recognized decision identifiers | [mandatory] | SDD generation contract |
| SELECT | Find generated Python modules under the output root | [mandatory] | SDD generation contract |
| SERVE | Replace or prepend one stable generated-file marker | [mandatory] | SDD generation contract |

EARS guards:
- R1: Only annotations with source `decision` or prefix `decision:` supply backlinks.
- R2: WHEN no decision IDs exist, generated modules say `decisions: none`.
- R3: Repeated runs replace the marker and never stack duplicate headers.
- R4: Every target module must resolve inside the selected output directory.

CLOSED:
- Ecore EAnnotations alone are not a generated-code carrier: pyecoregen 0.5.1
  dropped them in the recorded lending sample, so the post-generation header is
  the selected carrier (`docs/playbooks/sdd-integration-samplerun-2026-11-07.md`).

Preconditions: The Ecore file and output directory exist; output contains at
least one generated Python module.
Failure modes: Missing inputs, malformed XML, path escape, or no modules aborts
the command instead of reporting a successful annotation pass.
"""
from __future__ import annotations

import argparse
import re
import xml.etree.ElementTree as ET
from pathlib import Path

DECISION_ID = re.compile(r"\b(?:D|ADR|CDR|EDR|IDR)-\d+\b")
GENERATED_HEADER = re.compile(rb"^# GENERATED FROM .* - DO NOT EDIT - decisions: .*\r?\n")


def decision_ids(ecore_path: Path) -> list[str]:
    """Collect recognized decision IDs from decision-scoped Ecore annotations.

    Args:
        ecore_path: Existing Ecore XML file.

    Returns:
        Unique decision IDs in lexical order.

    Require: The caller supplies a readable Ecore XML file.
    Guarantee: Requirement IDs and non-decision annotations are excluded.
    Maintain: The source Ecore bytes are never modified.
    Assert: Each returned ID matches the recognized decision identifier form.
    """
    root = ET.parse(ecore_path).getroot()
    found: set[str] = set()
    for annotation in root.iter():
        if annotation.tag.rsplit("}", 1)[-1] != "eAnnotations":
            continue
        source = annotation.get("source", "")
        if source != "decision" and not source.startswith("decision:"):
            continue
        found.update(DECISION_ID.findall(source))
        for detail in annotation:
            if detail.tag.rsplit("}", 1)[-1] == "details":
                found.update(DECISION_ID.findall(detail.get("key", "")))
                found.update(DECISION_ID.findall(detail.get("value", "")))
    return sorted(found)


def annotate_generated(ecore_path: Path, output_dir: Path) -> list[Path]:
    """Write one idempotent traceability header to every generated Python file.

    Args:
        ecore_path: Source Ecore model used by pyecoregen.
        output_dir: pyecoregen output root.

    Returns:
        Generated Python files updated, in stable path order.

    Require: Both inputs exist and output_dir contains generated Python files.
    Guarantee: Every module begins with one marker naming its Ecore source and
        sorted decision IDs, or `none` when the model cites no decisions.
    Maintain: Existing module content after its current marker is preserved.
    Assert: No target path escapes the resolved output directory.
    """
    root = output_dir.resolve(strict=True)
    ids = ",".join(decision_ids(ecore_path)) or "none"
    header = f"# GENERATED FROM {ecore_path.name} - DO NOT EDIT - decisions: {ids}\n".encode("utf-8")
    modules = sorted(output_dir.rglob("*.py"))
    if not modules:
        raise ValueError(f"No generated Python files found beneath {output_dir}")

    updates: list[tuple[Path, bytes]] = []
    for module in modules:
        target = module.resolve(strict=True)
        if target != root and root not in target.parents:
            raise ValueError(f"Generated module escapes output directory: {module}")
        content = module.read_bytes()
        body = GENERATED_HEADER.sub(b"", content, count=1)
        updates.append((module, header + body))

    for module, content in updates:
        module.write_bytes(content)
    return [module for module, _ in updates]


def main(argv: list[str] | None = None) -> int:
    """Annotate generated modules after a successful pyecoregen invocation.

    Args:
        argv: Optional command-line arguments.

    Returns:
        Zero after every generated module has been updated.

    Require: `--ecore` names the source model and `--output` names its output root.
    Guarantee: A success summary is printed only after writes finish.
    Maintain: The command changes generated modules only.
    Assert: Missing input paths and empty output are reported as command failures.
    """
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--ecore", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    if not args.ecore.is_file():
        parser.error(f"Ecore file does not exist: {args.ecore}")
    if not args.output.is_dir():
        parser.error(f"Output directory does not exist: {args.output}")
    modules = annotate_generated(args.ecore, args.output)
    print(f"Annotated {len(modules)} generated Python file(s) with decision IDs.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
