"""Store, edit, and render nested Markdown requirements in SQLite.

Pipeline:
| Stage | Mechanism | Tag | Requirements |
|---|---|---|---|
| IMPORT | Capture each file as a source-hashed, globally ordered node stream | [mandatory] | Requirement #4 |
| EDIT | Replace nodes or insert ordered children under optimistic revisions | [mandatory] | Requirement #4 |
| PREVIEW | Render proposed replacement, insertion, or sibling movement without committing | [mandatory] | Requirement #4 |
| RENDER | Join node bytes by document emission order, independent of tree nesting | [mandatory] | Requirement #4 |
| RESTORE | Snapshot SQLite and verify the restored rule IDs and render hashes | [mandatory] | Requirement #4 |
| PUBLISH | Check registered destination baseline then write atomically through harness_write | [mandatory] | Requirement #4 |

R1: If any captured source changes after import, edits and publication MUST fail until that source is reimported or explicitly reconciled.
R2: Each document MUST have one root. Every non-root node has one parent, nonnegative sibling ordinal, stable ID, and only renderable byte-owner nodes occupy a unique emission slot.
R3: Rendering MUST concatenate exact byte-owner payloads by explicit emissions rows, never by sibling traversal.
R4: An imported paragraph is one editable rule. Splitting it requires an explicit edit into ordered byte spans and child nodes.
R5: Every committed edit and audit receipt MUST share one transaction.
R6: A publication MUST check the target's last recorded digest, and exact readback MUST match the rendered bytes.

CLOSED: Markdown parse-and-reserialize is rejected because it can normalize source whitespace. Tree-only rendering is rejected because nested headings reorder bytes. The global emission sequence is authoritative.
Preconditions: Import source is UTF-8 Markdown. SQLite path and every destination are explicit.
Failure modes: stale source/revision/target, invalid parent graph, duplicate order, invalid UTF-8, snapshot mismatch, or failed atomic write aborts the operation.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from pathlib import Path

SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS documents (
    document_id TEXT PRIMARY KEY,
    source_path TEXT NOT NULL,
    source_sha256 TEXT NOT NULL,
    render_sha256 TEXT NOT NULL DEFAULT '',
    revision INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS nodes (
    node_id INTEGER PRIMARY KEY,
    document_id TEXT NOT NULL REFERENCES documents(document_id) ON DELETE CASCADE,
    parent_id INTEGER REFERENCES nodes(node_id) ON DELETE CASCADE,
    ordinal INTEGER NOT NULL,
    emission INTEGER NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('document','section','rule','literal','span')),
    payload BLOB NOT NULL,
    renderable INTEGER NOT NULL DEFAULT 1 CHECK(renderable IN (0,1)),
    UNIQUE(document_id,parent_id,ordinal),
    CHECK ((kind='document' AND parent_id IS NULL) OR
           (kind<>'document' AND parent_id IS NOT NULL))
);
CREATE TABLE IF NOT EXISTS emissions (
    document_id TEXT NOT NULL REFERENCES documents(document_id) ON DELETE CASCADE,
    emission INTEGER NOT NULL,
    node_id INTEGER NOT NULL REFERENCES nodes(node_id) ON DELETE CASCADE,
    PRIMARY KEY(document_id,emission),
    UNIQUE(document_id,node_id)
);
CREATE TABLE IF NOT EXISTS changes (
    change_id INTEGER PRIMARY KEY,
    document_id TEXT NOT NULL REFERENCES documents(document_id) ON DELETE CASCADE,
    revision INTEGER NOT NULL,
    node_id INTEGER NOT NULL REFERENCES nodes(node_id),
    operation TEXT NOT NULL,
    before_sha256 TEXT NOT NULL,
    after_sha256 TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(document_id,revision)
);
CREATE TABLE IF NOT EXISTS targets (
    document_id TEXT NOT NULL REFERENCES documents(document_id) ON DELETE CASCADE,
    target_path TEXT NOT NULL,
    expected_sha256 TEXT NOT NULL,
    rendered_sha256 TEXT NOT NULL,
    PRIMARY KEY(document_id,target_path)
);
CREATE TABLE IF NOT EXISTS target_history (
    publication_id INTEGER PRIMARY KEY,
    document_id TEXT NOT NULL REFERENCES documents(document_id) ON DELETE CASCADE,
    target_path TEXT NOT NULL,
    before_sha256 TEXT NOT NULL,
    rendered_sha256 TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


class RuleStore:
    """Persist and render instruction sources in explicit byte order.

    Require: path names an accessible SQLite registry.
    Guarantee: rendering follows globally unique node emission ordinals.
    Maintain: one parent per node and unique sibling and emission ordering.
    Assert: every semantic node edit matches the expected document revision.
    Failure modes: SQLite integrity errors and stale edits propagate.
    """

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript(SCHEMA)
            document_columns={row["name"] for row in db.execute("PRAGMA table_info(documents)")}
            if "render_sha256" not in document_columns:
                db.execute("ALTER TABLE documents ADD COLUMN render_sha256 TEXT NOT NULL DEFAULT ''")
            db.execute(
                """INSERT OR IGNORE INTO emissions(document_id,emission,node_id)
                   SELECT document_id,emission,node_id FROM nodes
                   WHERE emission>=0 AND renderable=1 ORDER BY emission"""
            )
            docs=db.execute("SELECT document_id FROM documents WHERE render_sha256='' ").fetchall()
            for row in docs:
                self._refresh_render_digest(db,row["document_id"])
            db.commit()

    @staticmethod
    def _refresh_render_digest(db: sqlite3.Connection, document_id: str) -> str:
        """Store the current emitted hash in the active transaction.

        Require: emissions rows and their byte owners reflect the proposed state.
        Guarantee: documents.render_sha256 equals the exact current render.
        Assert: every emission resolves to one renderable node.
        """
        rows=db.execute("SELECT n.payload FROM emissions e JOIN nodes n USING(node_id) WHERE e.document_id=? ORDER BY e.emission",
                        (document_id,)).fetchall()
        digest=hashlib.sha256(b"".join(bytes(row["payload"]) for row in rows)).hexdigest()
        db.execute("UPDATE documents SET render_sha256=? WHERE document_id=?",(digest,document_id))
        return digest

    def connect(self) -> sqlite3.Connection:
        """Open a foreign-key-enforcing connection.

        Require: registry path is readable and writable.
        Guarantee: row-addressable SQLite connection with busy timeout.
        """
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA busy_timeout=5000")
        return db

    def import_markdown(self, document_id: str, source: Path) -> str:
        """Import an exact source file and retain a nested logical outline.

        Require: nonempty stable document ID and UTF-8 Markdown source.
        Guarantee: output bytes and SHA-256 equal the imported source.
        Maintain: per-source node emission ordinals preserve every byte's order.
        """
        if not document_id.strip():
            raise ValueError("document_id must be nonempty")
        source = Path(source).resolve(strict=True)
        raw = source.read_bytes()
        raw.decode("utf-8")
        digest = hashlib.sha256(raw).hexdigest()
        with self.connect() as db:
            with db:
                db.execute(
                    """INSERT INTO documents(document_id,source_path,source_sha256,render_sha256,revision)
                       VALUES(?,?,?, ?,1)
                       ON CONFLICT(document_id) DO UPDATE SET source_path=excluded.source_path,
                       source_sha256=excluded.source_sha256,render_sha256=excluded.render_sha256,
                       revision=documents.revision+1""",
                    (document_id,str(source),digest,digest),
                )
                db.execute("DELETE FROM nodes WHERE document_id=?",(document_id,))
                root=db.execute(
                    """INSERT INTO nodes(document_id,parent_id,ordinal,emission,kind,payload)
                   VALUES(?,NULL,0,-1,'document',?) RETURNING node_id""",
                    (document_id,b""),
                ).fetchone()["node_id"]
                stack: dict[int,int]={0:root}
                sibling_counts: dict[int,int]={root:0}
                for emission,line in enumerate(raw.splitlines(keepends=True)):
                    heading=re.match(rb"^(#{1,6})[ \t]+",line)
                    if heading:
                        depth=len(heading.group(1))
                        for old_depth in tuple(stack):
                            if old_depth>=depth and old_depth:
                                del stack[old_depth]
                        parent=stack[max(d for d in stack if d<depth)]
                        kind="section"
                    else:
                        parent=stack[max(stack)]
                        kind="rule" if re.match(rb"^\s*(?:[-*+] |\d+[.)] )",line) else "literal"
                    ordinal=sibling_counts.get(parent,0)
                    node=db.execute(
                        """INSERT INTO nodes(document_id,parent_id,ordinal,emission,kind,payload)
                           VALUES(?,?,?,?,?,?) RETURNING node_id""",
                        (document_id,parent,ordinal,emission,kind,line),
                    ).fetchone()["node_id"]
                    sibling_counts[parent]=ordinal+1
                    db.execute("INSERT INTO emissions(document_id,emission,node_id) VALUES(?,?,?)",
                               (document_id,emission,node))
                    if kind=="section":
                        stack[depth]=node
                        sibling_counts[node]=0
        if self.render(document_id)!=raw:
            raise AssertionError("import renderer failed exact source readback")
        return digest

    def render(self, document_id: str) -> bytes:
        """Render a document by its explicit source order.

        Require: document exists and has source nodes.
        Guarantee: concatenated output follows emission ordinals.
        Assert: output hash can be compared to the registered source hash.
        """
        with self.connect() as db:
            rows=db.execute(
                """SELECT n.payload FROM emissions e JOIN nodes n USING(node_id)
                   WHERE e.document_id=? AND n.renderable=1 ORDER BY e.emission""",(document_id,)
            ).fetchall()
        if not rows:
            raise KeyError(f"unknown or empty document {document_id!r}")
        return b"".join(bytes(row["payload"]) for row in rows)

    def preview_replace(self, document_id: str, node_id: int, payload: bytes) -> bytes:
        """Render the whole proposed document without changing the registry.

        Require: node belongs to the document and payload is UTF-8.
        Guarantee: result equals current emitted bytes with only that node replaced.
        Assert: a non-renderable span cannot be edited as a source fragment.
        """
        payload.decode("utf-8")
        with self.connect() as db:
            rows=db.execute(
                "SELECT n.node_id,n.payload FROM emissions e JOIN nodes n USING(node_id) WHERE e.document_id=? AND n.renderable=1 ORDER BY e.emission",
                (document_id,),
            ).fetchall()
        if not any(row["node_id"]==node_id for row in rows):
            raise KeyError(f"renderable node {node_id} not in {document_id}")
        return b"".join(payload if row["node_id"]==node_id else bytes(row["payload"]) for row in rows)

    def preview_insert(self, document_id: str, parent_id: int, ordinal: int, emission: int,
                       payload: bytes) -> bytes:
        """Render an emitted child insertion without changing registry state.

        Require: parent exists, positions are nonnegative and emission is unused.
        Guarantee: output inserts exact UTF-8 payload at the requested document position.
        Assert: current document emissions are unique and complete.
        Failure modes: unknown parent or occupied position raises.
        """
        payload.decode("utf-8")
        if ordinal<0 or emission<0:
            raise ValueError("ordinal and emission must be nonnegative")
        with self.connect() as db:
            if db.execute("SELECT 1 FROM nodes WHERE document_id=? AND node_id=?",(document_id,parent_id)).fetchone() is None:
                raise KeyError(f"parent {parent_id} not in {document_id}")
            rows=db.execute("SELECT e.emission,n.node_id,n.payload FROM emissions e JOIN nodes n USING(node_id) WHERE e.document_id=? ORDER BY e.emission",
                            (document_id,)).fetchall()
        if any(row["emission"]==emission for row in rows):
            raise ValueError("emission position is occupied")
        output=[(row["emission"],bytes(row["payload"])) for row in rows]
        output.append((emission,payload))
        return b"".join(part for _,part in sorted(output,key=lambda item:item[0]))

    def preview_move(self, document_id: str, node_id: int, parent_id: int, ordinal: int) -> bytes:
        """Render a sibling reorder without changing registry state.

        Require: node and parent exist and node already belongs to that parent.
        Guarantee: emitted fragments reorder within their existing document slots.
        Assert: destination ordinal is nonnegative and sibling emissions are renderable.
        Failure modes: cross-parent move, unknown IDs, or non-emitting sibling raises.
        """
        if ordinal<0:
            raise ValueError("ordinal must be nonnegative")
        with self.connect() as db:
            node=db.execute("SELECT parent_id FROM nodes WHERE document_id=? AND node_id=?",
                            (document_id,node_id)).fetchone()
            parent=db.execute("SELECT 1 FROM nodes WHERE document_id=? AND node_id=?",
                              (document_id,parent_id)).fetchone()
            if node is None or parent is None:
                raise KeyError("node and parent must belong to the document")
            if node["parent_id"]!=parent_id:
                raise ValueError("cross-parent movement requires an explicit layout operation")
            siblings=db.execute("SELECT node_id FROM nodes WHERE parent_id=? ORDER BY ordinal,node_id",
                               (parent_id,)).fetchall()
            emission_rows=db.execute("SELECT e.emission,n.node_id,n.payload FROM emissions e JOIN nodes n USING(node_id) WHERE e.document_id=? ORDER BY e.emission",
                                    (document_id,)).fetchall()
        order=[row["node_id"] for row in siblings]
        order.remove(node_id)
        order.insert(min(ordinal,len(order)),node_id)
        sibling_ids=set(order)
        slots=[row["emission"] for row in emission_rows if row["node_id"] in sibling_ids]
        if len(slots)!=len(order):
            raise RuntimeError("sibling set has non-emitting structural nodes")
        replacement=iter(zip(sorted(slots),order))
        payloads={row["node_id"]:bytes(row["payload"]) for row in emission_rows}
        slot_to_node={slot:node for slot,node in replacement}
        return b"".join(payloads[slot_to_node[row["emission"]]] if row["emission"] in slot_to_node
                         else bytes(row["payload"]) for row in emission_rows)

    def replace_node(self, document_id: str, node_id: int, payload: bytes, expected_revision: int) -> int:
        """Replace one node and record a digest receipt atomically.

        Require: payload is UTF-8 and expected_revision is current.
        Guarantee: edit and audit receipt commit in one transaction.
        Maintain: unrelated node bytes and emission order remain unchanged.
        Assert: source hash, revision, and node ownership match.
        Failure modes: stale source/revision or missing node rolls back.
        """
        payload.decode("utf-8")
        with self.connect() as db:
            with db:
                db.execute("BEGIN IMMEDIATE")
                doc=db.execute("SELECT * FROM documents WHERE document_id=?",(document_id,)).fetchone()
                if doc is None:
                    raise KeyError(document_id)
                source=Path(doc["source_path"])
                if not source.is_file() or hashlib.sha256(source.read_bytes()).hexdigest()!=doc["source_sha256"]:
                    raise RuntimeError("source changed since import; reimport or reconcile before editing")
                if doc["revision"]!=expected_revision:
                    raise RuntimeError(f"stale revision {expected_revision}; current is {doc['revision']}")
                node=db.execute(
                    "SELECT payload FROM nodes WHERE node_id=? AND document_id=?",(node_id,document_id)
                ).fetchone()
                if node is None:
                    raise KeyError(f"node {node_id} not in {document_id}")
                before=bytes(node["payload"])
                revision=expected_revision+1
                db.execute("UPDATE nodes SET payload=? WHERE node_id=?",(payload,node_id))
                self._refresh_render_digest(db,document_id)
                db.execute("UPDATE documents SET revision=? WHERE document_id=?",(revision,document_id))
                db.execute(
                    """INSERT INTO changes(document_id,revision,node_id,operation,before_sha256,after_sha256)
                       VALUES(?,?,?,?,?,?)""",
                    (document_id,revision,node_id,"replace",hashlib.sha256(before).hexdigest(),
                     hashlib.sha256(payload).hexdigest()),
                )
        return revision

    def insert_child(self, document_id: str, parent_id: int, ordinal: int, emission: int,
                     payload: bytes, expected_revision: int) -> int:
        """Insert a child rule with distinct sibling and document positions.

        Require: valid UTF-8 payload and unused nonnegative positions.
        Guarantee: node insert and revision increment commit atomically.
        Maintain: source-line nodes retain their original order unless explicitly reindexed.
        Assert: parent belongs to the document and expected revision is current.
        Failure modes: invalid parent, occupied position, or stale source aborts.
        """
        payload.decode("utf-8")
        if ordinal<0 or emission<0:
            raise ValueError("ordinal and emission must be nonnegative")
        with self.connect() as db:
            with db:
                db.execute("BEGIN IMMEDIATE")
                doc=db.execute("SELECT * FROM documents WHERE document_id=?",(document_id,)).fetchone()
                if doc is None:
                    raise KeyError(document_id)
                if hashlib.sha256(Path(doc["source_path"]).read_bytes()).hexdigest()!=doc["source_sha256"]:
                    raise RuntimeError("source changed since import")
                if doc["revision"]!=expected_revision:
                    raise RuntimeError("stale document revision")
                if db.execute("SELECT 1 FROM nodes WHERE node_id=? AND document_id=?",(parent_id,document_id)).fetchone() is None:
                    raise KeyError(f"parent {parent_id} not in {document_id}")
                if db.execute("SELECT 1 FROM emissions WHERE document_id=? AND emission=?",(document_id,emission)).fetchone():
                    raise ValueError("emission position is occupied; use a fractional-free gap or reindex explicitly")
                node=db.execute(
                    """INSERT INTO nodes(document_id,parent_id,ordinal,emission,kind,payload)
                       VALUES(?,?,?,?,'rule',?) RETURNING node_id""",
                    (document_id,parent_id,ordinal,emission,payload),
                ).fetchone()["node_id"]
                db.execute("INSERT INTO emissions(document_id,emission,node_id) VALUES(?,?,?)",(document_id,emission,node))
                self._refresh_render_digest(db,document_id)
                revision=expected_revision+1
                db.execute("UPDATE documents SET revision=? WHERE document_id=?",(revision,document_id))
                empty=hashlib.sha256(b"").hexdigest()
                db.execute(
                    """INSERT INTO changes(document_id,revision,node_id,operation,before_sha256,after_sha256)
                       VALUES(?,?,?,?,?,?)""",
                    (document_id,revision,node,"insert",empty,hashlib.sha256(payload).hexdigest()),
                )
        return node

    def split_rule(self, document_id: str, node_id: int, spans: list[bytes],
                   expected_revision: int) -> list[int]:
        """Replace a rule with exact ordered span nodes for reviewed subrules.

        Require: spans concatenate byte-for-byte to the current parent payload.
        Guarantee: every span receives a stable ID and replaces the parent in rendered emission order.
        Maintain: initial split output remains byte-identical while each span becomes independently editable.
        Assert: target node is a rule and revision is current.
        Failure modes: nonmatching spans, stale source, or duplicate position aborts.
        """
        if not spans or any(not span for span in spans):
            raise ValueError("spans must be nonempty byte strings")
        for span in spans:
            span.decode("utf-8")
        with self.connect() as db:
            with db:
                db.execute("BEGIN IMMEDIATE")
                doc=db.execute("SELECT * FROM documents WHERE document_id=?",(document_id,)).fetchone()
                if doc is None or doc["revision"]!=expected_revision:
                    raise RuntimeError("unknown document or stale revision")
                if hashlib.sha256(Path(doc["source_path"]).read_bytes()).hexdigest()!=doc["source_sha256"]:
                    raise RuntimeError("source changed since import")
                parent=db.execute(
                    "SELECT * FROM nodes WHERE node_id=? AND document_id=? AND kind IN ('rule','literal') AND renderable=1",
                    (node_id,document_id),
                ).fetchone()
                if parent is None:
                    raise KeyError("split target must be an imported rule")
                if b"".join(spans)!=bytes(parent["payload"]):
                    raise ValueError("spans must concatenate exactly to the original parent bytes")
                emission_row=db.execute("SELECT emission FROM emissions WHERE document_id=? AND node_id=?",
                                        (document_id,node_id)).fetchone()
                if emission_row is None:
                    raise RuntimeError("split target is not in rendered output")
                emission=emission_row["emission"]
                child_ids=[]
                for offset,span in enumerate(spans):
                    child_ids.append(db.execute(
                        """INSERT INTO nodes(document_id,parent_id,ordinal,emission,kind,payload,renderable)
                           VALUES(?,?,?,?, 'span',?,1) RETURNING node_id""",
                        (document_id,node_id,offset,emission+offset,span),
                    ).fetchone()["node_id"])
                emitted=db.execute("SELECT node_id FROM emissions WHERE document_id=? ORDER BY emission",
                                   (document_id,)).fetchall()
                sequence=[]
                for row in emitted:
                    if row["node_id"]==node_id:
                        sequence.extend(child_ids)
                    else:
                        sequence.append(row["node_id"])
                db.execute("DELETE FROM emissions WHERE document_id=?",(document_id,))
                db.execute("UPDATE nodes SET kind='literal',payload=X'',emission=-1,renderable=0 WHERE node_id=?",(node_id,))
                for final_emission,emitted_id in enumerate(sequence):
                    db.execute("UPDATE nodes SET emission=? WHERE node_id=?",(final_emission,emitted_id))
                    db.execute("INSERT INTO emissions(document_id,emission,node_id) VALUES(?,?,?)",
                               (document_id,final_emission,emitted_id))
                self._refresh_render_digest(db,document_id)
                revision=expected_revision+1
                db.execute("UPDATE documents SET revision=? WHERE document_id=?",(revision,document_id))
                db.execute(
                    """INSERT INTO changes(document_id,revision,node_id,operation,before_sha256,after_sha256)
                       VALUES(?,?,?,?,?,?)""",
                    (document_id,revision,node_id,"split",hashlib.sha256(bytes(parent["payload"])).hexdigest(),
                     hashlib.sha256(b"".join(spans)).hexdigest()),
                )
        return child_ids

    def move_node(self, document_id: str, node_id: int, parent_id: int, ordinal: int,
                  expected_revision: int) -> int:
        """Move one node within its document without changing emitted bytes.

        Require: the node and parent belong to the document and ordinal is unused.
        Guarantee: move, output order, revision, and audit receipt commit atomically.
        Maintain: a pure parent change retains emission position; sibling reordering changes it.
        Assert: parent ancestry contains no cycle and source/revision are current.
        Failure modes: stale revision, missing node, occupied ordinal, or cycle rolls back.
        """
        if ordinal < 0:
            raise ValueError("ordinal must be nonnegative")
        with self.connect() as db:
            with db:
                db.execute("BEGIN IMMEDIATE")
                doc=db.execute("SELECT * FROM documents WHERE document_id=?",(document_id,)).fetchone()
                if doc is None or doc["revision"] != expected_revision:
                    raise RuntimeError("unknown document or stale revision")
                if hashlib.sha256(Path(doc["source_path"]).read_bytes()).hexdigest() != doc["source_sha256"]:
                    raise RuntimeError("source changed since import")
                node=db.execute("SELECT * FROM nodes WHERE node_id=? AND document_id=?",(node_id,document_id)).fetchone()
                parent=db.execute("SELECT * FROM nodes WHERE node_id=? AND document_id=?",(parent_id,document_id)).fetchone()
                if node is None or parent is None:
                    raise KeyError("node and parent must belong to the document")
                if node["parent_id"]!=parent_id:
                    raise ValueError("cross-parent movement requires an explicit layout operation")
                if node_id == parent_id or db.execute(
                    """WITH RECURSIVE descendants(id) AS (
                         SELECT node_id FROM nodes WHERE parent_id=?
                         UNION ALL SELECT n.node_id FROM nodes n JOIN descendants d ON n.parent_id=d.id
                       ) SELECT 1 FROM descendants WHERE id=?""",(node_id,parent_id)
                ).fetchone():
                    raise ValueError("move would create a cycle")
                same_parent=node["parent_id"]==parent_id
                if not same_parent and db.execute("SELECT 1 FROM nodes WHERE parent_id=? AND ordinal=? AND node_id<>?",
                              (parent_id,ordinal,node_id)).fetchone():
                    raise ValueError("sibling ordinal is occupied")
                before=bytes(node["payload"])
                if node["parent_id"]==parent_id:
                    siblings=db.execute("SELECT node_id FROM nodes WHERE parent_id=? ORDER BY ordinal,node_id",(parent_id,)).fetchall()
                    order=[row["node_id"] for row in siblings]
                    order.remove(node_id)
                    order.insert(min(ordinal,len(order)),node_id)
                    for temporary_ordinal,sibling_id in enumerate(order):
                        db.execute("UPDATE nodes SET ordinal=? WHERE node_id=?",(-1000000-temporary_ordinal,sibling_id))
                    for final_ordinal,sibling_id in enumerate(order):
                        db.execute("UPDATE nodes SET ordinal=? WHERE node_id=?",(final_ordinal,sibling_id))
                    sibling_ids=set(order)
                    emitted=db.execute("SELECT emission,node_id FROM emissions WHERE document_id=? ORDER BY emission",(document_id,)).fetchall()
                    # Source nodes normally have distinct parents; when only moving siblings,
                    # rewrite their emission slots in sibling order and leave other nodes fixed.
                    slots=[row["emission"] for row in emitted if row["node_id"] in sibling_ids]
                    if len(slots)!=len(order):
                        raise RuntimeError("sibling set has non-emitting structural nodes")
                    temporary=[-1000000000-index for index in range(len(order))]
                    for slot,sibling_id in zip(temporary,order):
                        db.execute("UPDATE emissions SET emission=? WHERE document_id=? AND node_id=?",
                                   (slot,document_id,sibling_id))
                    for slot,sibling_id in zip(sorted(slots),order):
                        db.execute("UPDATE emissions SET emission=? WHERE document_id=? AND node_id=?",
                                   (slot,document_id,sibling_id))
                self._refresh_render_digest(db,document_id)
                revision=expected_revision+1
                db.execute("UPDATE documents SET revision=? WHERE document_id=?",(revision,document_id))
                digest=hashlib.sha256(before).hexdigest()
                db.execute("""INSERT INTO changes(document_id,revision,node_id,operation,before_sha256,after_sha256)
                              VALUES(?,?,?,?,?,?)""",
                           (document_id,revision,node_id,"move",digest,digest))
        return revision

    def publish(self, document_id: str, target: Path, expected_sha256: str | None,
                backup_root: Path, dry_run: bool = True) -> str:
        """Preview or safely publish one mapped Markdown projection.

        Require: caller owns target mapping; expected_sha256 is the last recorded target hash.
        Guarantee: dry run writes nothing; publish records exact readback and backup metadata.
        Maintain: target bytes are never overwritten after drift from the expected digest.
        Assert: harness_write preflights and atomically writes the exact rendered UTF-8 bytes.
        Failure modes: target drift, source drift, denied path, or readback mismatch raises.
        """
        import harness_write

        with self.connect() as db:
            source=db.execute("SELECT source_path,source_sha256 FROM documents WHERE document_id=?",
                              (document_id,)).fetchone()
        if source is None:
            raise KeyError(document_id)
        source_path=Path(source["source_path"])
        if not source_path.is_file() or hashlib.sha256(source_path.read_bytes()).hexdigest()!=source["source_sha256"]:
            raise RuntimeError("source changed since import; reimport or reconcile before publishing")
        raw=self.render(document_id)
        target=Path(target).resolve()
        current=target.read_bytes() if target.exists() else b""
        current_hash=hashlib.sha256(current).hexdigest()
        with self.connect() as db:
            recorded=db.execute("SELECT expected_sha256 FROM targets WHERE document_id=? AND target_path=?",
                                (document_id,str(target))).fetchone()
        if recorded is None:
            raise RuntimeError("target is not mapped; register its baseline before publishing")
        if expected_sha256 is not None and expected_sha256!=recorded["expected_sha256"]:
            raise RuntimeError("provided target digest differs from the registered mapping")
        expected_sha256=recorded["expected_sha256"]
        if expected_sha256 is not None and current_hash != expected_sha256:
            raise RuntimeError(f"target drift: expected {expected_sha256}, found {current_hash}")
        if dry_run:
            return "IDENTICAL" if current==raw else "PREVIEW"
        if current==raw:
            return "IDENTICAL"
        artifact=harness_write.Artifact(path=target,text=raw.decode("utf-8"),mode="file")
        changes=harness_write.plan([artifact])
        harness_write.apply(changes,backup_root)
        readback=target.read_bytes()
        digest=hashlib.sha256(raw).hexdigest()
        if readback!=raw:
            raise RuntimeError("published target readback mismatch")
        with self.connect() as db:
            with db:
                db.execute("INSERT INTO target_history(document_id,target_path,before_sha256,rendered_sha256,status) VALUES(?,?,?,?,?)",
                           (document_id,str(target),current_hash,digest,"PUBLISHED"))
                db.execute("INSERT INTO targets(document_id,target_path,expected_sha256,rendered_sha256) VALUES(?,?,?,?) "
                           "ON CONFLICT(document_id,target_path) DO UPDATE SET expected_sha256=excluded.expected_sha256,rendered_sha256=excluded.rendered_sha256",
                           (document_id,str(target),digest,digest))
                if source_path==target:
                    db.execute("UPDATE documents SET source_sha256=? WHERE document_id=?",(digest,document_id))
        return "PUBLISHED"

    def map_target(self, document_id: str, target: Path, baseline_sha256: str) -> None:
        """Register one explicitly owned target and its current baseline digest.

        Require: target is an intentional harness route and caller supplies its observed digest.
        Guarantee: only a target matching that digest becomes publishable.
        Assert: document exists and current target bytes match the supplied baseline.
        Failure modes: missing document, target mismatch, or duplicate mapping raises.
        """
        target=Path(target).resolve()
        current=target.read_bytes() if target.exists() else b""
        actual=hashlib.sha256(current).hexdigest()
        if actual!=baseline_sha256:
            raise RuntimeError(f"target baseline mismatch: expected {baseline_sha256}, found {actual}")
        with self.connect() as db:
            with db:
                if db.execute("SELECT 1 FROM documents WHERE document_id=?",(document_id,)).fetchone() is None:
                    raise KeyError(document_id)
                prior=db.execute("SELECT 1 FROM targets WHERE document_id=? AND target_path=?",
                                 (document_id,str(target))).fetchone()
                if prior:
                    raise RuntimeError("target mapping already exists")
                db.execute("INSERT INTO targets(document_id,target_path,expected_sha256,rendered_sha256) VALUES(?,?,?,?)",
                           (document_id,str(target),actual,actual))

    def export_review(self) -> str:
        """Serialize complete registry state as deterministic, reviewable JSON text.

        Require: registry schema is current.
        Guarantee: documents, stable IDs, ordering, audit, and target mappings are included.
        Maintain: row and property order are deterministic for Git diffs.
        Assert: byte payloads decode as UTF-8 and all tables have deterministic ordering.
        """
        tables={"documents":"document_id","nodes":"node_id","emissions":"document_id,emission",
                "changes":"change_id","targets":"document_id,target_path","target_history":"publication_id"}
        data={"format":"harness-instruction-registry","version":1,"tables":{}}
        with self.connect() as db:
            for table,order in tables.items():
                rows=db.execute(f"SELECT * FROM {table} ORDER BY {order}").fetchall()
                items=[]
                for row in rows:
                    item=dict(row)
                    if table=="nodes":
                        item["payload_text"]=bytes(item.pop("payload")).decode("utf-8")
                    items.append(item)
                data["tables"][table]=items
        return json.dumps(data,ensure_ascii=False,indent=2,sort_keys=True)+"\n"

    def restore_review(self, source: Path) -> int:
        """Restore a deterministic review export into an empty registry.

        Require: destination registry has no documents and source export is version 1.
        Guarantee: explicit IDs, ordering, audit entries, and target mappings are restored.
        Assert: foreign keys, SQLite integrity, and each current render hash pass.
        Failure modes: malformed export or nonempty destination aborts the transaction.
        """
        data=json.loads(Path(source).read_text(encoding="utf-8"))
        if data.get("format")!="harness-instruction-registry" or data.get("version")!=1:
            raise ValueError("unsupported instruction registry export")
        order=["documents","nodes","emissions","changes","targets","target_history"]
        tables=data.get("tables")
        if not isinstance(tables,dict) or set(tables)!=set(order):
            raise ValueError("registry export has missing or unknown tables")
        with self.connect() as db:
            with db:
                if db.execute("SELECT 1 FROM documents LIMIT 1").fetchone():
                    raise RuntimeError("restore destination must be empty")
                for table in order:
                    expected={row["name"] for row in db.execute(f"PRAGMA table_info({table})")}
                    for item in tables[table]:
                        values=dict(item)
                        if table=="nodes":
                            text=values.pop("payload_text")
                            values["payload"]=text.encode("utf-8")
                        if set(values)!=expected:
                            raise ValueError(f"invalid fields in {table} export row")
                        columns=sorted(expected)
                        db.execute(f"INSERT INTO {table} ({','.join(columns)}) VALUES ({','.join('?' for _ in columns)})",
                                   tuple(values[column] for column in columns))
                if db.execute("PRAGMA integrity_check").fetchone()[0]!="ok":
                    raise RuntimeError("restored registry integrity check failed")
                if db.execute("PRAGMA foreign_key_check").fetchone() is not None:
                    raise RuntimeError("restored registry has foreign key violations")
                rows=db.execute("SELECT document_id,render_sha256 FROM documents ORDER BY document_id").fetchall()
                for row in rows:
                    payloads=db.execute("SELECT n.payload FROM emissions e JOIN nodes n USING(node_id) WHERE e.document_id=? ORDER BY e.emission",
                                        (row["document_id"],)).fetchall()
                    actual=hashlib.sha256(b"".join(bytes(item["payload"]) for item in payloads)).hexdigest()
                    if actual!=row["render_sha256"]:
                        raise RuntimeError(f"restored render hash mismatch: {row['document_id']}")
        return len(rows)
