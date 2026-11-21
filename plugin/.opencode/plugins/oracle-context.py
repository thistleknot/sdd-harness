"""Build a bounded static code outline for Oracle delegations.

Pipeline
| Stage | Mechanism | Tag | Refs |
| --- | --- | --- | --- |
| INPUT | Read one JSON request from standard input. | [mandatory] | R1 |
| RESOLVE | Confine pointers to the requested workspace. | [mandatory] | R2 |
| MAP | Parse bounded selected Python source with the standard-library AST parser. | [mandatory] | R3 |
| EVIDENCE | Read an already-captured, bounded workspace PyCallGraph DOT file. | [opt] | R4 |
| SERVE | Emit compact JSON pointers and outline lines to standard output. | [mandatory] | R5 |

EARS guards
- R1: When input is invalid, the program shall return valid JSON with empty results.
- R2: If a candidate path escapes the workspace or is inside an ignored directory,
  then the program shall omit it.
- R3: When a Python source file cannot be parsed, the program shall record a bounded
  syntax diagnostic and continue without executing or importing it.
- R4: When a recognized captured DOT graph is present, the program shall include only
  bounded observed edges; it shall not trace, execute, import, or deserialize project code.
- R5: When no usable pointer is supplied, the program shall inspect a bounded set of
  workspace Python files without traversing ignored or linked directories.

Closed
- Runtime tracing, imports, execution, and pickle deserialization are not started here.

Preconditions and failure modes
- Standard input is UTF-8 JSON with an absolute existing workspace root.
- The program returns an empty result for missing roots, malformed JSON, unreadable
  sources, and out-of-workspace paths.
"""
from __future__ import annotations

import ast
import json
import os
import re
import sys
from pathlib import Path


MAX_FILES = 12
MAX_DEFINITIONS_PER_FILE = 16
MAX_CALLS_PER_DEFINITION = 6
MAX_OUTLINE_LINES = 120
MAX_AUTO_DISCOVERY_DIRECTORIES = 128
MAX_SOURCE_BYTES = 512 * 1024
MAX_DOT_BYTES = 256 * 1024
MAX_OBSERVED_EDGES = 24
IGNORED_DIRECTORIES = {
    ".git",
    ".hg",
    ".svn",
    ".tmp",
    ".venv",
    "venv",
    "__pycache__",
    "node_modules",
    "site-packages",
    "dist",
    "build",
    "coverage",
    ".mypy_cache",
    ".pytest_cache",
    ".secrets",
    "secrets",
    ".env",
    "dotenv",
}
SECRET_FILE_NAMES = {".env", ".envrc", "id_rsa", "id_ed25519", "credentials.json"}
LINE_SUFFIX = re.compile(r":\d+(?::\d+)?$")
DOT_HEADER = re.compile(r"^\s*(?:strict\s+)?digraph\b[^\{]*\{", re.IGNORECASE)
DOT_EDGE = re.compile(
    r'^\s*(?:"(?P<left_quoted>[^"\\\r\n]{1,160})"|(?P<left_id>[A-Za-z_][\w.:-]{0,159}))'
    r'\s*->\s*(?:"(?P<right_quoted>[^"\\\r\n]{1,160})"|(?P<right_id>[A-Za-z_][\w.:-]{0,159}))'
)


def read_request() -> dict:
    """Read a single request from standard input.

    Require:
        Input contains one UTF-8 JSON object.
    Guarantee:
        Returns an empty object for malformed input.
    Maintain:
        Input is never executed or interpolated into a command.
    Assert:
        The returned value is a dictionary.
    """
    try:
        value = json.load(sys.stdin)
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def is_ignored(path: Path, root: Path) -> bool:
    """Return whether a workspace-relative path traverses ignored directories.

    Require:
        Both paths are resolved and path is confined to root.
    Guarantee:
        Ignores dependency, build, VCS, and cache directories.
    Maintain:
        The workspace root itself is never treated as ignored.
    Assert:
        Result depends only on relative path components.
    """
    return any(part.casefold() in IGNORED_DIRECTORIES for part in path.relative_to(root).parts[:-1])


def resolve_pointer(candidate: object, root: Path) -> Path | None:
    """Resolve one path or file-and-line pointer within the workspace.

    Require:
        Candidate is a string path, optionally ending in line and column digits.
    Guarantee:
        Returns only existing regular files beneath root.
    Maintain:
        Absolute paths outside root and ignored directories never enter the map.
    Assert:
        Returned paths are resolved descendants of root.
    """
    if not isinstance(candidate, str) or not candidate.strip():
        return None
    text = LINE_SUFFIX.sub("", candidate.strip().strip("`'\""))
    path = Path(text).expanduser()
    if not path.is_absolute():
        path = root / path
    try:
        resolved = path.resolve(strict=True)
        resolved.relative_to(root)
    except (OSError, ValueError):
        return None
    if (
        not resolved.is_file()
        or resolved.name.casefold() in SECRET_FILE_NAMES
        or is_ignored(resolved, root)
    ):
        return None
    return resolved


def candidate_files(root: Path, pointers: object) -> list[Path]:
    """Select relevant Python files followed by bounded workspace coverage.

    Require:
        Root exists and pointers is a list or absent.
    Guarantee:
        Pointer-selected Python files retain their supplied order before coverage.
    Maintain:
        At most MAX_FILES files are returned.
    Assert:
        Every returned file is a Python source beneath root.
    """
    selected: list[Path] = []
    raw_pointers = pointers if isinstance(pointers, list) else []
    for pointer in raw_pointers:
        path = resolve_pointer(pointer, root)
        if path and path.suffix == ".py" and path not in selected:
            selected.append(path)
    if len(selected) >= MAX_FILES:
        return selected[:MAX_FILES]
    discovered_directories = 0
    for current_text, directories, filenames in os.walk(root, topdown=True, followlinks=False):
        current = Path(current_text)
        directories[:] = sorted(
            directory
            for directory in directories
            if directory.casefold() not in IGNORED_DIRECTORIES
            and not (current / directory).is_symlink()
        )
        discovered_directories += 1
        if discovered_directories > MAX_AUTO_DISCOVERY_DIRECTORIES:
            break
        for filename in sorted(filenames):
            if not filename.endswith(".py"):
                continue
            path = current / filename
            if path.is_symlink() or path in selected:
                continue
            try:
                resolved = path.resolve(strict=True)
                resolved.relative_to(root)
            except (OSError, ValueError):
                continue
            if is_ignored(resolved, root):
                continue
            selected.append(resolved)
            if len(selected) == MAX_FILES:
                return selected
    return selected


def expression_name(node: ast.AST) -> str:
    """Render a bounded syntactic callee name without evaluating the expression.

    Require:
        Node is an AST expression.
    Guarantee:
        Returns an identifier-like display string.
    Maintain:
        Attribute access remains syntax only.
    Assert:
        The returned string contains no source execution result.
    """
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return f"{expression_name(node.value)}.{node.attr}"
    return "<dynamic>"


def signature(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    """Render a compact static function signature.

    Require:
        Node is a Python function definition.
    Guarantee:
        Includes positional, keyword-only, variadic arguments, and return syntax.
    Maintain:
        Default expressions are represented as ellipses.
    Assert:
        The signature does not import the defining module.
    """
    args = node.args
    parts = [arg.arg for arg in args.posonlyargs]
    if args.posonlyargs:
        parts.append("/")
    parts.extend(arg.arg for arg in args.args)
    if args.vararg:
        parts.append(f"*{args.vararg.arg}")
    elif args.kwonlyargs:
        parts.append("*")
    parts.extend(arg.arg for arg in args.kwonlyargs)
    if args.kwarg:
        parts.append(f"**{args.kwarg.arg}")
    returns = f" -> {ast.unparse(node.returns)}" if node.returns else ""
    prefix = "async " if isinstance(node, ast.AsyncFunctionDef) else ""
    return f"{prefix}{node.name}({', '.join(parts)}){returns}"


def definition_calls(node: ast.AST) -> list[str]:
    """Extract bounded syntactic call targets below one definition.

    Require:
        Node is a class or function body.
    Guarantee:
        Returns unique source-order callee names.
    Maintain:
        Nested class and function bodies are not attributed to their parent.
    Assert:
        No call target is resolved dynamically.
    """
    calls: list[str] = []

    class Calls(ast.NodeVisitor):
        def visit_FunctionDef(self, child: ast.FunctionDef) -> None:
            if child is not node:
                return
            self.generic_visit(child)

        def visit_AsyncFunctionDef(self, child: ast.AsyncFunctionDef) -> None:
            if child is not node:
                return
            self.generic_visit(child)

        def visit_ClassDef(self, child: ast.ClassDef) -> None:
            if child is not node:
                return
            self.generic_visit(child)

        def visit_Call(self, child: ast.Call) -> None:
            value = expression_name(child.func)
            if value not in calls and len(calls) < MAX_CALLS_PER_DEFINITION:
                calls.append(value)
            self.generic_visit(child)

    Calls().visit(node)
    return calls


def outline_file(path: Path, root: Path) -> tuple[list[str], list[str]]:
    """Summarize module definitions and direct syntactic calls with AST.

    Require:
        Path is a readable Python source under root.
    Guarantee:
        Emits at most MAX_DEFINITIONS_PER_FILE definition lines.
    Maintain:
        Source is parsed only. It is never imported, compiled, or executed.
    Assert:
        Every emitted pointer has a workspace-relative path and source line.
    """
    relative = path.relative_to(root).as_posix()
    try:
        if path.stat().st_size > MAX_SOURCE_BYTES:
            return [f"{relative}:1"], [f"{relative}:1 source skipped: exceeds byte limit"]
        source = path.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(source, filename=str(path))
    except (OSError, SyntaxError) as exc:
        line = getattr(exc, "lineno", 1) or 1
        return [f"{relative}:{line}"], [f"{relative}:{line} syntax unavailable: {type(exc).__name__}"]

    pointers = [f"{relative}:1"]
    outlines: list[str] = []
    definitions = 0
    imports = [
        alias.name
        for node in tree.body
        if isinstance(node, ast.Import)
        for alias in node.names
    ]
    imports.extend(
        f"{node.module or '.'}"
        for node in tree.body
        if isinstance(node, ast.ImportFrom)
    )
    if imports:
        outlines.append(f"{relative}:1 imports {', '.join(imports[:6])}")

    for node in tree.body:
        if definitions >= MAX_DEFINITIONS_PER_FILE:
            break
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            calls = definition_calls(node)
            suffix = f"; calls {', '.join(calls)}" if calls else ""
            pointers.append(f"{relative}:{node.lineno}")
            outlines.append(f"{relative}:{node.lineno} def {signature(node)}{suffix}")
            definitions += 1
        elif isinstance(node, ast.ClassDef):
            pointers.append(f"{relative}:{node.lineno}")
            outlines.append(f"{relative}:{node.lineno} class {node.name}")
            definitions += 1
            for child in node.body:
                if definitions >= MAX_DEFINITIONS_PER_FILE:
                    break
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    calls = definition_calls(child)
                    suffix = f"; calls {', '.join(calls)}" if calls else ""
                    pointers.append(f"{relative}:{child.lineno}")
                    outlines.append(f"{relative}:{child.lineno} {node.name}.{signature(child)}{suffix}")
                    definitions += 1
    return pointers, outlines


def observed_edges(root: Path) -> list[str]:
    """Read bounded observed call evidence from an already-captured DOT graph.

    Require:
        Graph is exactly ``pycallgraph.dot`` or ``.tmp/pycallgraph.dot`` under root.
    Guarantee:
        Returns only validated DOT edge labels, never runtime-generated evidence.
    Maintain:
        The graph is read as capped text; project code is never traced or deserialized.
    Assert:
        Every output line starts with ``observed edge``.
    """
    for relative in (Path(".tmp") / "pycallgraph.dot", Path("pycallgraph.dot")):
        path = root / relative
        try:
            if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_DOT_BYTES:
                continue
            payload = path.read_bytes()
        except OSError:
            continue
        try:
            text = payload.decode("utf-8")
        except UnicodeDecodeError:
            continue
        if not DOT_HEADER.match(text) or "\x00" in text:
            continue
        edges: list[str] = []
        for line in text.splitlines():
            match = DOT_EDGE.match(line)
            if not match:
                continue
            left = match.group("left_quoted") or match.group("left_id")
            right = match.group("right_quoted") or match.group("right_id")
            edge = f"observed edge {left} -> {right}"
            if edge not in edges:
                edges.append(edge)
            if len(edges) == MAX_OBSERVED_EDGES:
                break
        if edges:
            return edges
    return []


def build_response(request: dict) -> dict:
    """Construct a compact Oracle source map from a JSON request.

    Require:
        Request root is an absolute workspace directory.
    Guarantee:
        Emits only workspace-confined static source information.
    Maintain:
        Target project code remains unexecuted and unimported.
    Assert:
        Response conforms to pointers and outline string arrays.
    """
    raw_root = request.get("root")
    if not isinstance(raw_root, str):
        return {"pointers": [], "outline": []}
    try:
        root = Path(raw_root).expanduser().resolve(strict=True)
    except OSError:
        return {"pointers": [], "outline": []}
    if not root.is_dir():
        return {"pointers": [], "outline": []}

    pointers: list[str] = []
    outline: list[str] = []
    for path in candidate_files(root, request.get("pointers")):
        file_pointers, file_outline = outline_file(path, root)
        for pointer in file_pointers:
            if pointer not in pointers:
                pointers.append(pointer)
        outline.extend(file_outline)
        if len(outline) >= MAX_OUTLINE_LINES:
            break
    remaining = MAX_OUTLINE_LINES - len(outline)
    if remaining > 0:
        outline.extend(observed_edges(root)[:remaining])
    return {"pointers": pointers[:MAX_OUTLINE_LINES], "outline": outline[:MAX_OUTLINE_LINES]}


def main() -> None:
    """Write the static Oracle handoff source map as one JSON line."""
    json.dump(build_response(read_request()), sys.stdout, ensure_ascii=False, separators=(",", ":"))
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
