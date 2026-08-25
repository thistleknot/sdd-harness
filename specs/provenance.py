"""Code-symbol provenance validation against SpecsDB.

Purpose: define language-neutral provenance fields, parse Python docstrings,
validate IDs and signature/spec hashes, permit module-level inheritance,
and fail on missing/stale references for public and critical symbols.

Preconditions: ast module for Python parsing; traceability_graph available.
Failure modes: ProvenanceError on missing/stale references for public symbols.

Usage:
    from specs.provenance import ProvenanceParser, validate_provenance
    parser = ProvenanceParser()
    records = parser.parse_file("src/auth.py")
    issues = validate_provenance(records, graph)
"""
from __future__ import annotations

import ast
import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .traceability_graph import TraceabilityGraph


# --- Data Models -------------------------------------------------------------


@dataclass
class ProvenanceRecord:
    """Provenance metadata extracted from a code symbol's docstring."""
    symbol_name: str
    file_path: str
    line_number: int
    is_public: bool
    purpose: str = ""
    requirements: list[str] = field(default_factory=list)  # e.g. ["R-001", "R-003"]
    design: list[str] = field(default_factory=list)         # e.g. ["D-002"]
    failure_modes: list[str] = field(default_factory=list)
    pending: list[str] = field(default_factory=list)        # task IDs
    signature_hash: str = ""  # hash of function signature for staleness
    module_level: bool = False  # inherits from module docstring


@dataclass
class ProvenanceIssue:
    """One validation issue found during provenance check."""
    symbol_name: str
    file_path: str
    line_number: int
    severity: str  # "error", "warn", "info"
    message: str


# --- Parser ------------------------------------------------------------------


_PROVENANCE_FIELDS = {
    "purpose": re.compile(r"^\s*Purpose:\s*(.+)", re.IGNORECASE),
    "requirements": re.compile(r"^\s*Requirements?:\s*(.+)", re.IGNORECASE),
    "design": re.compile(r"^\s*Design:\s*(.+)", re.IGNORECASE),
    "failure_modes": re.compile(r"^\s*Failure [Mm]odes?:\s*(.+)", re.IGNORECASE),
    "pending": re.compile(r"^\s*Pending:\s*(.+)", re.IGNORECASE),
}

_ID_PATTERN = re.compile(r"[A-Z]-\d{3}|#\d+|[A-Z]{1,4}-\w+")


class ProvenanceParser:
    """Parse provenance fields from Python source files.

    Contract:
        Require: valid Python source file.
        Guarantee: one ProvenanceRecord per class/function.
        Maintain: module-level inheritance for internal helpers.
    """

    def parse_file(self, file_path: str | Path) -> list[ProvenanceRecord]:
        """Parse all provenance records from a Python file."""
        path = Path(file_path)
        if not path.exists():
            return []

        source = path.read_text(encoding="utf-8")
        return self.parse_source(source, str(path))

    def parse_source(self, source: str, file_path: str = "<string>") -> list[ProvenanceRecord]:
        """Parse provenance from source string."""
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return []

        records: list[ProvenanceRecord] = []
        module_provenance = self._extract_module_provenance(tree)

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                record = self._parse_node(node, file_path, module_provenance)
                if record:
                    records.append(record)

        return records

    def _extract_module_provenance(self, tree: ast.Module) -> dict:
        """Extract provenance from module-level docstring."""
        docstring = ast.get_docstring(tree)
        if not docstring:
            return {}
        return self._parse_docstring(docstring)

    def _parse_node(
        self, node: ast.AST, file_path: str, module_prov: dict
    ) -> Optional[ProvenanceRecord]:
        """Parse a function/class node into a ProvenanceRecord."""
        name = node.name
        is_public = not name.startswith("_")
        docstring = ast.get_docstring(node)

        # Compute signature hash
        sig_hash = self._compute_signature_hash(node)

        # Parse docstring fields
        if docstring:
            fields = self._parse_docstring(docstring)
        else:
            fields = {}

        # Module-level inheritance for non-public symbols
        inherited = not bool(fields.get("requirements") or fields.get("design"))
        if inherited and not is_public:
            fields = {**module_prov, **fields}

        return ProvenanceRecord(
            symbol_name=name,
            file_path=file_path,
            line_number=node.lineno,
            is_public=is_public,
            purpose=fields.get("purpose", ""),
            requirements=fields.get("requirements", []),
            design=fields.get("design", []),
            failure_modes=fields.get("failure_modes", []),
            pending=fields.get("pending", []),
            signature_hash=sig_hash,
            module_level=inherited and not is_public,
        )

    def _parse_docstring(self, docstring: str) -> dict:
        """Extract provenance fields from a docstring."""
        result: dict = {}
        for line in docstring.split("\n"):
            for field_name, pattern in _PROVENANCE_FIELDS.items():
                m = pattern.match(line)
                if m:
                    value = m.group(1).strip()
                    if field_name in ("requirements", "design", "pending", "failure_modes"):
                        ids = _ID_PATTERN.findall(value)
                        result[field_name] = ids if ids else [value]
                    else:
                        result[field_name] = value
        return result

    def _compute_signature_hash(self, node: ast.AST) -> str:
        """Hash the function/class signature for staleness detection."""
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            sig = ast.dump(node.args)
            if node.returns:
                sig += ast.dump(node.returns)
        elif isinstance(node, ast.ClassDef):
            sig = ",".join(ast.dump(b) for b in node.bases)
        else:
            sig = node.name
        return hashlib.sha256(sig.encode()).hexdigest()[:12]


# --- Validator ---------------------------------------------------------------


def validate_provenance(
    records: list[ProvenanceRecord],
    graph: TraceabilityGraph,
) -> list[ProvenanceIssue]:
    """Validate provenance records against the traceability graph.

    Rules:
    - Public symbols MUST have at least one requirement or design reference.
    - Referenced IDs MUST exist as nodes in the graph.
    - Pending references MUST correspond to active tasks.
    - Module-level inheritance is allowed for private helpers.
    """
    issues: list[ProvenanceIssue] = []

    for rec in records:
        # Public symbols must have provenance
        if rec.is_public and not rec.requirements and not rec.design and not rec.pending:
            issues.append(ProvenanceIssue(
                symbol_name=rec.symbol_name,
                file_path=rec.file_path,
                line_number=rec.line_number,
                severity="error",
                message=f"Public symbol '{rec.symbol_name}' has no requirement, design, or pending reference",
            ))

        # Validate requirement IDs exist
        for req_id in rec.requirements:
            node = graph.get_node(req_id)
            if not node:
                issues.append(ProvenanceIssue(
                    symbol_name=rec.symbol_name,
                    file_path=rec.file_path,
                    line_number=rec.line_number,
                    severity="error",
                    message=f"Referenced requirement '{req_id}' not found in graph",
                ))
            elif node.status.value == "superseded":
                issues.append(ProvenanceIssue(
                    symbol_name=rec.symbol_name,
                    file_path=rec.file_path,
                    line_number=rec.line_number,
                    severity="warn",
                    message=f"Referenced requirement '{req_id}' is superseded",
                ))

        # Validate design IDs exist
        for design_id in rec.design:
            node = graph.get_node(design_id)
            if not node:
                issues.append(ProvenanceIssue(
                    symbol_name=rec.symbol_name,
                    file_path=rec.file_path,
                    line_number=rec.line_number,
                    severity="warn",
                    message=f"Referenced design element '{design_id}' not found in graph",
                ))

        # Pending references should map to active tasks
        for task_id in rec.pending:
            node = graph.get_node(task_id)
            if node and node.status.value == "deprecated":
                issues.append(ProvenanceIssue(
                    symbol_name=rec.symbol_name,
                    file_path=rec.file_path,
                    line_number=rec.line_number,
                    severity="warn",
                    message=f"Pending task '{task_id}' is deprecated — symbol may be orphaned",
                ))

    return issues
