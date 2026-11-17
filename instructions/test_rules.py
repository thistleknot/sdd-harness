"""Focused round-trip and publication checks for the prompt rule registry.

Pipeline:
| Stage | Mechanism | Tag | Requirements |
|---|---|---|---|
| FIXTURES | Check exact bytes across newline and Markdown structures | [mandatory] | Requirement #4 |
| EDITS | Check emitted child insertion and sibling reorder | [mandatory] | Requirement #4 |
| PUBLISH | Check preview, exact write, idempotence, and drift rejection | [mandatory] | Requirement #4 |

R1: Each unchanged fixture MUST render byte for byte.
R2: Insert and reorder MUST modify only the intended emitted fragments.
R3: Repeated publish MUST be a no-op, and drift MUST block replacement.

CLOSED: In-memory-only mocks are rejected because exact file bytes and writer behavior are acceptance conditions.
Preconditions: pytest is available and tests run from the harness root.
Failure modes: byte mismatch, order mismatch, missing backup safety, or drift acceptance fails the suite.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

import pytest

from instructions.rules import RuleStore
from instructions.cli import main as cli_main


@pytest.mark.parametrize(
    "name,source",
    [
        ("lf", b"# Root\n- alpha\n```py\nx=1\n```\n| a | b |\n|---|---|\n"),
        ("crlf", b"# Root\r\n- beta\r\n```txt\r\nx\r\n```\r\n| c | d |\r\n|---|---|\r\n"),
        ("no-final-newline", b"# Root\nText with `code`.\n\n| x | y |\n|---|---|\nlast"),
    ],
)
def test_import_and_edit_preview_preserve_source(tmp_path: Path, name: str, source: bytes) -> None:
    """Prove exact source bytes and non-mutating whole-document previews.

    Require: the fixture includes its intended newline and Markdown structure.
    Guarantee: import renders exact bytes and preview leaves registry output untouched.
    Assert: a renderable node can be previewed without committing a revision.
    """
    source_path = tmp_path / f"{name}.md"
    source_path.write_bytes(source)
    store = RuleStore(tmp_path / f"{name}.sqlite")
    digest = store.import_markdown(name, source_path)
    assert store.render(name) == source
    assert hashlib.sha256(store.render(name)).hexdigest() == digest
    with store.connect() as db:
        node = db.execute(
            "SELECT node_id,payload FROM nodes WHERE document_id=? AND renderable=1 AND kind IN ('rule','literal') ORDER BY emission LIMIT 1",
            (name,),
        ).fetchone()
    replacement = bytes(node["payload"]).replace(b"Root", b"Changed", 1) if b"Root" in node["payload"] else bytes(node["payload"]) + b"!"
    proposed = store.preview_replace(name, node["node_id"], replacement)
    assert proposed != source
    assert store.render(name) == source


def test_insert_and_sibling_reorder_change_rendered_markdown(tmp_path: Path) -> None:
    """Prove nested insertion and sibling order feed the emitted sequence.

    Require: source has two sibling rules under one section.
    Guarantee: the inserted child is emitted and reordered siblings render in new order.
    Assert: source baseline stays unchanged outside the registry.
    """
    source = tmp_path / "outline.md"
    source.write_bytes(b"# H\n- first\n- second\n")
    store = RuleStore(tmp_path / "outline.sqlite")
    store.import_markdown("outline", source)
    with store.connect() as db:
        rows = db.execute("SELECT node_id,parent_id FROM nodes WHERE document_id='outline' AND kind='rule' ORDER BY emission").fetchall()
        revision = db.execute("SELECT revision FROM documents WHERE document_id='outline'").fetchone()[0]
    first, second = rows
    assert store.preview_insert("outline", first["node_id"], 0, 10, b"  - nested\n") == b"# H\n- first\n- second\n  - nested\n"
    store.insert_child("outline", first["node_id"], 0, 10, b"  - nested\n", revision)
    assert store.preview_move("outline", second["node_id"], first["parent_id"], 0) == b"# H\n- second\n- first\n  - nested\n"
    store.move_node("outline", second["node_id"], first["parent_id"], 0, revision + 1)
    assert store.render("outline") == b"# H\n- second\n- first\n  - nested\n"
    assert source.read_bytes() == b"# H\n- first\n- second\n"


def test_cli_previews_insert_and_move_before_committing(tmp_path: Path, capsys) -> None:
    """Verify CLI insertion and sibling movement expose full-document diffs.

    Require: CLI arguments include current optimistic revision and stable node IDs.
    Guarantee: each operation prints the document diff before its commit receipt.
    Assert: the rendered output after the command matches the shown order.
    """
    source = tmp_path / "source.md"
    source.write_bytes(b"# H\n- first\n- second\n")
    db_path = tmp_path / "rules.sqlite"
    cli_main(["--db", str(db_path), "import", "doc", str(source)])
    store = RuleStore(db_path)
    with store.connect() as db:
        rows = db.execute("SELECT node_id,parent_id FROM nodes WHERE document_id='doc' AND kind='rule' ORDER BY emission").fetchall()
    first, second = rows
    cli_main(["--db", str(db_path), "insert", "doc", str(first["node_id"]), "0", "10", "  - child\n", "--revision", "1"])
    inserted_output = capsys.readouterr().out
    assert "+  - child" in inserted_output
    assert store.render("doc").endswith(b"  - child\n")
    cli_main(["--db", str(db_path), "move", "doc", str(second["node_id"]), str(first["parent_id"]), "0", "--revision", "2"])
    moved_output = capsys.readouterr().out
    assert "+- second" in moved_output and "-- second" in moved_output
    assert store.render("doc") == b"# H\n- second\n- first\n  - child\n"


def test_split_paragraph_spans_are_independently_rendered(tmp_path: Path) -> None:
    """Split one source rule into editable spans while retaining exact initial output.

    Require: imported rule has stable surrounding bytes.
    Guarantee: split keeps baseline output, and editing one span changes only that span.
    Assert: text outside the edited span remains byte-identical.
    """
    source = tmp_path / "paragraph.md"
    source.write_bytes(b"# H\nSentence one; sentence two.\n")
    store = RuleStore(tmp_path / "paragraph.sqlite")
    store.import_markdown("paragraph", source)
    with store.connect() as db:
        row = db.execute("SELECT node_id,payload FROM nodes WHERE document_id='paragraph' AND kind='literal' AND payload LIKE '%Sentence%'").fetchone()
        revision = db.execute("SELECT revision FROM documents WHERE document_id='paragraph'").fetchone()[0]
    spans = [b"Sentence one; ", b"sentence two.\n"]
    children = store.split_rule("paragraph", row["node_id"], spans, revision)
    assert store.render("paragraph") == source.read_bytes()
    with store.connect() as db:
        revision = db.execute("SELECT revision FROM documents WHERE document_id='paragraph'").fetchone()[0]
    changed = spans[1].replace(b"two", b"changed")
    store.replace_node("paragraph", children[1], changed, revision)
    assert store.render("paragraph") == source.read_bytes().replace(spans[1], changed, 1)
    assert store.render("paragraph").replace(changed, spans[1], 1) == source.read_bytes()


def test_publish_is_idempotent_and_rejects_drift(tmp_path: Path) -> None:
    """Prove writer-backed publish behavior using a scratch target.

    Require: source baseline is imported and target does not exist.
    Guarantee: exact output is published once; repeat is a no-op; drift is rejected.
    Assert: target digest recorded by the registry matches readback.
    """
    source = tmp_path / "source.md"
    source.write_bytes(b"# T\n- rule\n")
    store = RuleStore(tmp_path / "registry.sqlite")
    store.import_markdown("source", source)
    target = tmp_path / "target.md"
    backup = tmp_path / "backup"
    empty_digest = hashlib.sha256(b"").hexdigest()
    store.map_target("source", target, empty_digest)
    assert store.publish("source", target, None, backup, True) == "PREVIEW"
    assert not target.exists()
    assert store.publish("source", target, None, backup, False) == "PUBLISHED"
    stamp = target.stat().st_mtime_ns
    with store.connect() as db:
        history_count = db.execute("SELECT COUNT(*) FROM target_history").fetchone()[0]
    assert target.read_bytes() == source.read_bytes()
    assert store.publish("source", target, None, backup, False) == "IDENTICAL"
    assert target.stat().st_mtime_ns == stamp
    with store.connect() as db:
        assert db.execute("SELECT COUNT(*) FROM target_history").fetchone()[0] == history_count
    target.write_bytes(b"drift")
    with pytest.raises(RuntimeError, match="target drift"):
        store.publish("source", target, None, backup, False)


def test_publish_back_to_import_source_advances_source_baseline(tmp_path: Path) -> None:
    """Allow a mapped source target to accept DB-authored bytes and remain usable.

    Require: source file is also an explicitly mapped target.
    Guarantee: publication advances the source baseline to exact readback.
    Assert: subsequent no-op publication passes both source and target drift checks.
    """
    source = tmp_path / "source.md"
    source.write_bytes(b"# H\n- original\n")
    store = RuleStore(tmp_path / "registry.sqlite")
    store.import_markdown("source", source)
    with store.connect() as db:
        row = db.execute("SELECT node_id,payload FROM nodes WHERE document_id='source' AND kind='rule'").fetchone()
        revision = db.execute("SELECT revision FROM documents WHERE document_id='source'").fetchone()[0]
    store.replace_node("source", row["node_id"], b"- updated\n", revision)
    store.map_target("source", source, hashlib.sha256(b"# H\n- original\n").hexdigest())
    backup = tmp_path / "backup"
    assert store.publish("source", source, None, backup, False) == "PUBLISHED"
    assert source.read_bytes() == b"# H\n- updated\n"
    assert store.publish("source", source, None, backup, False) == "IDENTICAL"


def test_three_harness_views_publish_only_edited_rule_and_detect_drift(tmp_path: Path) -> None:
    """Exercise each registered instruction view through scratch target delivery.

    Require: three independently imported Markdown views each contain the filepath requirement.
    Guarantee: only the selected rule bytes change, backups preserve original targets, and repeats are no-ops.
    Assert: each target's exact readback equals its own document render; target drift is rejected.
    """
    variants = {
        "shared": b"# Shared\n- General rule.\n- When providing file paths, write each full absolute filepath on its own line.\n",
        "claude": b"# Claude\n- Claude-specific rule.\n- When providing file paths, write each full absolute filepath on its own line.\n",
        "codex": b"# Codex\n- Codex-specific rule.\n- When providing file paths, write each full absolute filepath on its own line.\n",
    }
    store = RuleStore(tmp_path / "registry.sqlite")
    backup_root = tmp_path / "backups"
    for document_id, original in variants.items():
        source = tmp_path / f"{document_id}-source.md"
        target = tmp_path / f"{document_id}-target.md"
        source.write_bytes(original)
        target.write_bytes(original)
        store.import_markdown(document_id, source)
        baseline = hashlib.sha256(original).hexdigest()
        store.map_target(document_id, target, baseline)
        with store.connect() as db:
            node = db.execute(
                "SELECT node_id,payload FROM nodes WHERE document_id=? AND kind='rule' AND payload LIKE '%full absolute filepath%'",
                (document_id,),
            ).fetchone()
            revision = db.execute("SELECT revision FROM documents WHERE document_id=?", (document_id,)).fetchone()[0]
        changed = bytes(node["payload"]).replace(b"absolute filepath", b"absolute file path")
        store.replace_node(document_id, node["node_id"], changed, revision)
        expected = original.replace(bytes(node["payload"]), changed, 1)
        assert store.publish(document_id, target, None, backup_root, False) == "PUBLISHED"
        assert target.read_bytes() == expected == store.render(document_id)
        assert store.publish(document_id, target, None, backup_root, False) == "IDENTICAL"
        backups = list(backup_root.rglob("*"))
        assert any(path.is_file() and path.read_bytes() == original for path in backups)
        target.write_bytes(b"external drift")
        with pytest.raises(RuntimeError, match="target drift"):
            store.publish(document_id, target, None, backup_root, False)


def test_invalid_moves_and_backup_retain_registry_state(tmp_path: Path) -> None:
    """Reject invalid hierarchy changes and verify a recoverable SQLite snapshot.

    Require: imported document contains a section and one rule.
    Guarantee: stale, missing-parent, and cycle moves fail without changing render; snapshot keeps IDs.
    Assert: SQLite integrity and rendered hash match the live registry.
    """
    source = tmp_path / "source.md"
    source.write_bytes(b"# H\n- item\n")
    store = RuleStore(tmp_path / "registry.sqlite")
    digest = store.import_markdown("source", source)
    with store.connect() as db:
        section = db.execute("SELECT node_id FROM nodes WHERE document_id='source' AND kind='section'").fetchone()[0]
        rule = db.execute("SELECT node_id FROM nodes WHERE document_id='source' AND kind='rule'").fetchone()[0]
        revision = db.execute("SELECT revision FROM documents WHERE document_id='source'").fetchone()[0]
    for parent_id, expected, error in [(section, revision - 1, "stale"), (999999, revision, "node and parent"), (rule, revision, "cycle")]:
        with pytest.raises((RuntimeError, KeyError, ValueError)):
            store.move_node("source", section, parent_id, 0, expected)
        assert store.render("source") == source.read_bytes()
    snapshot = tmp_path / "snapshot.sqlite"
    with store.connect() as current, sqlite3.connect(snapshot) as backup:
        current.backup(backup)
    restored = RuleStore(snapshot)
    with store.connect() as current, restored.connect() as backup:
        current_ids = current.execute("SELECT node_id,parent_id,ordinal FROM nodes WHERE document_id='source' ORDER BY node_id").fetchall()
        backup_ids = backup.execute("SELECT node_id,parent_id,ordinal FROM nodes WHERE document_id='source' ORDER BY node_id").fetchall()
        assert [tuple(row) for row in current_ids] == [tuple(row) for row in backup_ids]
        assert backup.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    assert hashlib.sha256(restored.render("source")).hexdigest() == digest


def test_review_export_restores_node_ids_render_hashes_and_targets(tmp_path: Path, capsys) -> None:
    """Round-trip the deterministic Git review export into an empty database.

    Require: registry has edited nodes, audit receipts, emission positions, and a target mapping.
    Guarantee: text export restores IDs, output hashes, and mapped destination metadata.
    Assert: restore rejects nonempty destinations through its contract.
    """
    source = tmp_path / "source.md"
    source.write_bytes(b"# H\n- original\n")
    target = tmp_path / "target.md"
    target.write_bytes(source.read_bytes())
    store = RuleStore(tmp_path / "registry.sqlite")
    store.import_markdown("source", source)
    store.map_target("source", target, hashlib.sha256(target.read_bytes()).hexdigest())
    with store.connect() as db:
        node = db.execute("SELECT node_id FROM nodes WHERE document_id='source' AND kind='rule'").fetchone()[0]
        revision = db.execute("SELECT revision FROM documents WHERE document_id='source'").fetchone()[0]
    store.replace_node("source", node, b"- edited\n", revision)
    export_path = tmp_path / "registry-review.json"
    cli_main(["--db", str(store.path), "export-review", str(export_path)])
    restored = RuleStore(tmp_path / "restored.sqlite")
    cli_main(["--db", str(restored.path), "restore-review", str(export_path)])
    assert "restored 1 documents" in capsys.readouterr().out
    with store.connect() as current, restored.connect() as backup:
        for query in [
            "SELECT node_id,parent_id,ordinal,kind,payload FROM nodes WHERE document_id='source' ORDER BY node_id",
            "SELECT emission,node_id FROM emissions WHERE document_id='source' ORDER BY emission",
            "SELECT revision,node_id,operation,before_sha256,after_sha256 FROM changes WHERE document_id='source' ORDER BY revision",
            "SELECT target_path,expected_sha256,rendered_sha256 FROM targets WHERE document_id='source'",
        ]:
            assert [tuple(row) for row in current.execute(query)] == [tuple(row) for row in backup.execute(query)]
    assert restored.render("source") == store.render("source")
    corrupt = json.loads(export_path.read_text(encoding="utf-8"))
    corrupt["tables"]["documents"][0]["render_sha256"] = "0" * 64
    corrupt_path = tmp_path / "corrupt-review.json"
    corrupt_path.write_text(json.dumps(corrupt), encoding="utf-8")
    rejected = RuleStore(tmp_path / "rejected.sqlite")
    with pytest.raises(RuntimeError, match="render hash mismatch"):
        rejected.restore_review(corrupt_path)
    with rejected.connect() as db:
        assert db.execute("SELECT COUNT(*) FROM documents").fetchone()[0] == 0
