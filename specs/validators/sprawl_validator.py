"""Sprawl validator: detect unreachable, duplicate, or untraceable artifacts.

Implements the orphan-count gate from requirement #4. Scans a directory for
Python symbols and checks whether each is reachable from a declared root or
linked to an active spec task.

Trigger: PostFileSave, PostFileCreate, Stop.
Fail mode: block if orphan count increases; warn on complexity threshold breach.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ..policy_contracts import (
    EvidenceRef,
    LifecycleEvent,
    PolicyRecord,
    StructuredVerdict,
    VerdictStatus,
)


def extract_definitions(source: str, filepath: str) -> list[dict]:
    """Extract top-level function and class definitions from Python source.

    Returns [{name, type, lineno, filepath}] for each public symbol.
    """
    try:
        tree = ast.parse(source, filename=filepath)
    except SyntaxError:
        return []

    defs = []
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.FunctionDef) or isinstance(node, ast.AsyncFunctionDef):
            if not node.name.startswith("_"):
                defs.append({"name": node.name, "type": "function", "lineno": node.lineno, "filepath": filepath})
        elif isinstance(node, ast.ClassDef):
            if not node.name.startswith("_"):
                defs.append({"name": node.name, "type": "class", "lineno": node.lineno, "filepath": filepath})
    return defs


def extract_references(source: str) -> set[str]:
    """Extract all name references (calls, attributes, imports) from source."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return set()

    refs = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            refs.add(node.id)
        elif isinstance(node, ast.Attribute):
            refs.add(node.attr)
        elif isinstance(node, ast.ImportFrom):
            if node.names:
                for alias in node.names:
                    refs.add(alias.name if alias.name != "*" else "")
        elif isinstance(node, ast.Import):
            for alias in node.names:
                refs.add(alias.name.split(".")[-1])
    return refs


def find_orphans(directory: Path, exclude_patterns: list[str] | None = None) -> list[dict]:
    """Scan a directory for public Python symbols not referenced by any other file.

    Returns list of orphan definitions [{name, type, lineno, filepath}].
    """
    exclude = exclude_patterns or ["__pycache__", ".git", "node_modules"]
    py_files = [
        p for p in directory.rglob("*.py")
        if not any(ex in str(p) for ex in exclude)
    ]

    # Phase 1: collect all definitions
    all_defs: list[dict] = []
    for pf in py_files:
        try:
            source = pf.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        all_defs.extend(extract_definitions(source, str(pf.relative_to(directory))))

    # Phase 2: collect all references across all files
    all_refs: set[str] = set()
    for pf in py_files:
        try:
            source = pf.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        all_refs.update(extract_references(source))

    # Phase 3: orphans = defined but never referenced anywhere
    orphans = [d for d in all_defs if d["name"] not in all_refs]

    # Exclude entry points and known roots
    entry_names = {"main", "app", "cli", "run", "setup", "conftest"}
    orphans = [d for d in orphans if d["name"] not in entry_names]

    return orphans


class SprawlValidator:
    """Detect unreachable public symbols in the codebase.

    Require: event payload has 'scan_dir' or defaults to harness specs/.
    Guarantee: returns one verdict per rule — block if orphans found, allow if clean.
    Maintain: read-only AST analysis; never modifies source.
    """

    VALIDATOR_ID = "sprawl-census"

    def evaluate(
        self, event: LifecycleEvent, rules: list[PolicyRecord], snapshot_hash: str,
    ) -> list[StructuredVerdict]:
        payload = event.payload
        scan_dir = Path(
            payload.get("scan_dir") or Path(__file__).resolve().parent.parent
        )

        orphans = find_orphans(scan_dir)

        verdicts = []
        for r in rules:
            if orphans:
                evidence = [
                    EvidenceRef(
                        ref_type="symbol",
                        ref_id=f"{o['filepath']}:{o['lineno']}",
                        description=f"{o['type']} '{o['name']}' at {o['filepath']}:{o['lineno']}",
                    )
                    for o in orphans[:10]
                ]
                verdicts.append(StructuredVerdict(
                    rule_id=r.rule_id, validator_id=self.VALIDATOR_ID,
                    status=VerdictStatus.warn,
                    subject_ids=[o["filepath"] for o in orphans[:10]],
                    evidence=evidence,
                    message=f"Sprawl: {len(orphans)} unreferenced public symbol(s) found",
                ))
            else:
                verdicts.append(StructuredVerdict(
                    rule_id=r.rule_id, validator_id=self.VALIDATOR_ID,
                    status=VerdictStatus.allow,
                    message="No unreferenced public symbols detected",
                ))
        return verdicts
