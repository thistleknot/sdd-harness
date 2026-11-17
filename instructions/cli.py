"""Operate the SQLite-backed prompt rule registry.

Pipeline:
| Stage | Mechanism | Tag | Requirements |
|---|---|---|---|
| IMPORT | Capture named Markdown sources into the local SQLite registry | [mandatory] | Requirement #4 |
| INSPECT | List nested sections/rules with stable node IDs | [mandatory] | Requirement #4 |
| PREVIEW | Show the generated Markdown diff before delivery | [mandatory] | Requirement #4 |
| INSERT / MOVE | Show the whole-document diff, then apply validated tree and emission changes | [mandatory] | Requirement #4 |
| BACKUP | Copy the SQLite database with SQLite's online backup API | [mandatory] | Requirement #4 |
| REVIEW EXPORT | Serialize complete ordered registry state as deterministic JSON text | [mandatory] | Requirement #4 |

R1: Mutation commands MUST require the caller's expected revision.
R2: Restore MUST verify registry integrity and every document's rendered digest.

CLOSED: Implicit source selection is rejected because three live AGENTS.md copies differ.
Preconditions: use absolute input, database, and backup paths.
Failure modes: stale revision, source drift, corrupt snapshot, or failed render exits nonzero.
"""

from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import sqlite3
import sys
from pathlib import Path

from instructions.rules import RuleStore


def _store(path: str) -> RuleStore:
    """Open the explicitly selected database."""
    return RuleStore(Path(path))


def _diff(before: bytes, after: bytes) -> str:
    """Return a readable UTF-8 unified diff."""
    return "".join(difflib.unified_diff(
        before.decode("utf-8").splitlines(keepends=True),
        after.decode("utf-8").splitlines(keepends=True),
        fromfile="current",
        tofile="proposed",
    ))


def _outline(store: RuleStore, document_id: str, limit: int) -> None:
    """Print the imported outline in source order without recursive traversal.

    Require: document is imported.
    Guarantee: every record appears once with its stable ID and heading depth.
    Maintain: printed order matches the rendered Markdown byte order.
    """
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    with store.connect() as db:
        rows=db.execute(
            "SELECT node_id,parent_id,ordinal,emission,kind,payload FROM nodes WHERE document_id=? AND emission>=0 ORDER BY emission",
            (document_id,),
        ).fetchall()
    section_depth: dict[int,int] = {}
    for row in rows[:limit]:
        depth=0
        parent=row["parent_id"]
        while parent is not None:
            with store.connect() as db:
                parent_row=db.execute("SELECT parent_id,kind,payload FROM nodes WHERE node_id=?",(parent,)).fetchone()
            if parent_row is None:
                raise RuntimeError(f"orphan node {row['node_id']}")
            if parent_row["kind"]=="section":
                depth+=1
            parent=parent_row["parent_id"]
        text=bytes(row["payload"]).decode("utf-8").rstrip()
        print(f"{'  '*max(0,depth-1)}{row['node_id']} [{row['kind']}] {text}")


def main(argv: list[str] | None = None) -> int:
    """Run one explicit registry operation.

    Require: argv identifies a command and its database.
    Guarantee: operations print stable IDs, hashes, or a review diff.
    Maintain: SQLite remains the editing source; exported Markdown is a view.
    Assert: edit revisions and source baselines are checked by RuleStore.
    """
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db",required=True,help="absolute SQLite database path")
    sub=parser.add_subparsers(dest="command",required=True)
    imp=sub.add_parser("import");imp.add_argument("document_id");imp.add_argument("source")
    outline=sub.add_parser("outline");outline.add_argument("document_id")
    outline.add_argument("--limit",type=int,default=100)
    render=sub.add_parser("render");render.add_argument("document_id");render.add_argument("--out")
    edit=sub.add_parser("edit");edit.add_argument("document_id");edit.add_argument("node_id",type=int);edit.add_argument("text");edit.add_argument("--revision",type=int,required=True)
    insert=sub.add_parser("insert");insert.add_argument("document_id");insert.add_argument("parent_id",type=int);insert.add_argument("ordinal",type=int);insert.add_argument("emission",type=int);insert.add_argument("text");insert.add_argument("--revision",type=int,required=True)
    move=sub.add_parser("move");move.add_argument("document_id");move.add_argument("node_id",type=int);move.add_argument("parent_id",type=int);move.add_argument("ordinal",type=int);move.add_argument("--revision",type=int,required=True)
    split=sub.add_parser("split");split.add_argument("document_id");split.add_argument("node_id",type=int);split.add_argument("spans_json");split.add_argument("--revision",type=int,required=True)
    backup=sub.add_parser("backup");backup.add_argument("destination")
    restore=sub.add_parser("verify-backup");restore.add_argument("snapshot")
    export=sub.add_parser("export-review");export.add_argument("destination")
    restore_review=sub.add_parser("restore-review");restore_review.add_argument("source")
    publish=sub.add_parser("publish");publish.add_argument("document_id");publish.add_argument("target");publish.add_argument("backup_root");publish.add_argument("--expected-sha256");publish.add_argument("--apply",action="store_true")
    mapping=sub.add_parser("map-target");mapping.add_argument("document_id");mapping.add_argument("target");mapping.add_argument("baseline_sha256")
    args=parser.parse_args(argv)
    store=_store(args.db)
    if args.command=="import":
        print(store.import_markdown(args.document_id,Path(args.source)))
    elif args.command=="outline":
        _outline(store,args.document_id,args.limit)
    elif args.command=="render":
        raw=store.render(args.document_id)
        if args.out:Path(args.out).write_bytes(raw)
        else:sys.stdout.buffer.write(raw)
    elif args.command=="edit":
        with store.connect() as db:
            row=db.execute("SELECT revision FROM documents WHERE document_id=?",(args.document_id,)).fetchone()
            node=db.execute("SELECT payload FROM nodes WHERE node_id=? AND document_id=?",(args.node_id,args.document_id)).fetchone()
        if row is None or node is None:raise KeyError("unknown document or node")
        proposed=args.text.encode("utf-8")
        before=store.render(args.document_id)
        after=store.preview_replace(args.document_id,args.node_id,proposed)
        print(_diff(before,after))
        print(f"revision={store.replace_node(args.document_id,args.node_id,proposed,args.revision)}")
    elif args.command=="split":
        spans=json.loads(args.spans_json)
        if not isinstance(spans,list) or not all(isinstance(span,str) for span in spans):
            raise ValueError("spans_json must be a JSON array of strings")
        ids=store.split_rule(args.document_id,args.node_id,[span.encode("utf-8") for span in spans],args.revision)
        print(json.dumps(ids))
    elif args.command=="insert":
        payload=args.text.encode("utf-8")
        before=store.render(args.document_id)
        after=store.preview_insert(args.document_id,args.parent_id,args.ordinal,args.emission,payload)
        print(_diff(before,after))
        print(f"node_id={store.insert_child(args.document_id,args.parent_id,args.ordinal,args.emission,payload,args.revision)}")
    elif args.command=="move":
        before=store.render(args.document_id)
        after=store.preview_move(args.document_id,args.node_id,args.parent_id,args.ordinal)
        print(_diff(before,after))
        print(f"revision={store.move_node(args.document_id,args.node_id,args.parent_id,args.ordinal,args.revision)}")
    elif args.command=="backup":
        destination=Path(args.destination)
        destination.parent.mkdir(parents=True,exist_ok=True)
        with store.connect() as source,sqlite3.connect(destination) as target:
            source.backup(target)
        print(hashlib.sha256(destination.read_bytes()).hexdigest())
    elif args.command=="verify-backup":
        snapshot=Path(args.snapshot)
        restored=RuleStore(snapshot)
        with sqlite3.connect(snapshot) as db:
            integrity=db.execute("PRAGMA integrity_check").fetchone()[0]
            docs=db.execute("SELECT document_id,render_sha256 FROM documents ORDER BY document_id").fetchall()
        if integrity!="ok":raise RuntimeError(f"snapshot integrity failed: {integrity}")
        for document_id,digest in docs:
            if hashlib.sha256(restored.render(document_id)).hexdigest()!=digest:
                raise RuntimeError(f"snapshot render hash mismatch: {document_id}")
        print(f"verified {len(docs)} documents")
    elif args.command=="export-review":
        destination=Path(args.destination)
        destination.parent.mkdir(parents=True,exist_ok=True)
        destination.write_text(store.export_review(),encoding="utf-8",newline="\n")
        print(hashlib.sha256(destination.read_bytes()).hexdigest())
    elif args.command=="restore-review":
        print(f"restored {store.restore_review(Path(args.source))} documents")
    elif args.command=="publish":
        target=Path(args.target)
        current=target.read_bytes() if target.exists() else b""
        proposed=store.render(args.document_id)
        print(_diff(current,proposed),end="")
        if not args.apply:
            print(store.publish(args.document_id,Path(args.target),args.expected_sha256,Path(args.backup_root),True))
        else:
            print(store.publish(args.document_id,Path(args.target),args.expected_sha256,Path(args.backup_root),False))
    elif args.command=="map-target":
        store.map_target(args.document_id,Path(args.target),args.baseline_sha256)
        print("mapped")
    return 0


if __name__=="__main__":
    raise SystemExit(main())
