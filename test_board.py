"""| Stage | Mechanism | Tag | Requirements |
|---|---|---|---|
| FIXTURE | Create temporary stores, repositories, and synthetic campaigns | [mandatory] | R1 |
| EXERCISE | Import, transition, and render independent board stories | [mandatory] | R2 |
| VERIFY | Assert isolation, dependencies, and byte-identical round trips | [contract] | R2 |

R1: When board tests run, the system shall use self-contained fixtures instead of the operator's changing plan.md.
R2: When a campaign is rendered and reimported, the system shall preserve dependencies, status, and lesson text.
CLOSED: Live campaign fixtures are rejected because exported snapshots omit machine-owned board output and campaign state changes invalidate assertions.
Preconditions: pytest and git are installed. Failure modes: state-machine or round-trip defects fail assertions.

Spec: specs.db REQ #40, REQ #43. Task: specs.db task #65 (ledger T2).
"""
import subprocess
import sys
from multiprocessing import Process
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import board  # noqa: E402
from board import BoardError  # noqa: E402


def _git(cwd, *args):
    subprocess.run(["git", *args], cwd=str(cwd), check=True, capture_output=True)


def make_repo(path: Path) -> Path:
    path.mkdir(parents=True)
    _git(path, "init", "-q")
    _git(path, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "--allow-empty", "-q", "-m", "init")
    return path


@pytest.fixture
def conn(tmp_path):
    c = board.connect(tmp_path / "b.db")
    yield c
    c.close()


def mk(conn, key="K", n=1, deps=None, feature=None):
    fid = feature or board.create_feature(conn, key, "F", "req")["id"]
    return fid, board.add_story(conn, key, fid, f"story {n}", ["check"], deps or [])


def to_review(conn, sid, key="K", who="a"):
    board.claim_story(conn, key, sid, who, "br", "/wt")
    board.submit_story(conn, key, sid, who, "ok")


def test_project_key(tmp_path):
    a = make_repo(tmp_path / "a")
    b = make_repo(tmp_path / "b")
    c = make_repo(tmp_path / "c")
    keys = {board.project_key(str(p)) for p in (a, b, c)}
    assert len(keys) == 3
    wt = tmp_path / "wt"
    _git(a, "worktree", "add", "-q", str(wt), "-b", "side")
    assert board.project_key(str(wt)) == board.project_key(str(a))
    sub = a / "sub"
    sub.mkdir()
    assert board.project_key(str(sub)) == board.project_key(str(a))
    plain = tmp_path / "plain"
    plain.mkdir()
    with pytest.raises(BoardError):
        board.project_key(str(plain))
    with pytest.raises(BoardError):
        board.project_key(str(tmp_path / "missing"))


def test_project_isolation(conn):
    ids = {}
    for k in ("A", "B", "C"):
        fid, s = mk(conn, k)
        ids[k] = (fid, s["id"])
    for k in ("A", "B", "C"):
        assert [s["id"] for s in board.list_stories(conn, k)] == [ids[k][1]]
        for other in ("A", "B", "C"):
            if other != k:
                with pytest.raises(BoardError):
                    board.get_story(conn, k, ids[other][1])
                with pytest.raises(BoardError):
                    board.add_story(conn, k, ids[other][0], "x", ["c"], [])
                with pytest.raises(BoardError):
                    board.add_story(conn, k, ids[k][0], "x", ["c"], [ids[other][1]])


def test_legal_paths(conn):
    _, s = mk(conn)
    sid = s["id"]
    assert s["status"] == "todo" and s["next_action"]
    board.claim_story(conn, "K", sid, "a", "br", "/wt")
    board.submit_story(conn, "K", sid, "a", "pytest ok")
    d = board.accept_story(conn, "K", sid, "b")
    assert d["status"] == "done" and d["reviewer_session"] == "b" and d["assignee_session"] == "a"

    _, s2 = mk(conn, n=2)
    sid = s2["id"]
    board.claim_story(conn, "K", sid, "a", "br", "/wt")
    board.submit_story(conn, "K", sid, "a", "out1")
    r = board.reject_story(conn, "K", sid, "b", "fix it")
    assert r["status"] == "in-progress" and r["review_note"] == "fix it"
    board.submit_story(conn, "K", sid, "a", "out2")
    assert board.accept_story(conn, "K", sid, "b")["status"] == "done"

    _, s3 = mk(conn, n=3)
    assert board.cancel_story(conn, "K", s3["id"], "a", "nope")["status"] == "cancelled"


def test_illegal_transitions(conn):
    _, s = mk(conn)
    sid = s["id"]
    with pytest.raises(BoardError, match="claim"):
        board.accept_story(conn, "K", sid, "b")
    with pytest.raises(BoardError, match="[Cc]laim"):
        board.submit_story(conn, "K", sid, "a", "out")
    board.claim_story(conn, "K", sid, "a", "br", "/wt")
    with pytest.raises(BoardError, match="submit"):
        board.claim_story(conn, "K", sid, "a", "br", "/wt")
    with pytest.raises(BoardError, match="submit"):
        board.claim_story(conn, "K", sid, "z", "br", "/wt")
    to_review(conn, mk(conn, n=2)[1]["id"], who="a")
    _, s3 = mk(conn, n=3)
    to_review(conn, s3["id"])
    board.accept_story(conn, "K", s3["id"], "b")
    with pytest.raises(BoardError, match="No action allowed"):
        board.accept_story(conn, "K", s3["id"], "b")
    with pytest.raises(BoardError):
        board.cancel_story(conn, "K", s3["id"], "b", "r")
    with pytest.raises(BoardError):
        board.claim_story(conn, "K", sid, "", "br", "/wt")


def test_dependency_rule(conn):
    fid, a = mk(conn, n=1)
    _, b = mk(conn, n=2, deps=[a["id"]], feature=fid)
    assert b["depends_on"] == [a["id"]]
    with pytest.raises(BoardError, match="dependency"):
        board.claim_story(conn, "K", b["id"], "s", "br", "/wt")
    to_review(conn, a["id"])
    with pytest.raises(BoardError, match="dependency"):
        board.claim_story(conn, "K", b["id"], "s", "br", "/wt")
    board.accept_story(conn, "K", a["id"], "b")
    assert board.claim_story(conn, "K", b["id"], "s", "br", "/wt")["status"] == "in-progress"


def test_cycles_impossible_by_construction(conn):
    # dependencies may name only existing stories, so a cycle cannot be built;
    # self-dependency (the id the new story would get) and unknown ids are rejected.
    fid, a = mk(conn)
    for bad in (a["id"] + 1, 9999, -1):
        with pytest.raises(BoardError):
            board.add_story(conn, "K", fid, "x", ["c"], [bad])
    assert len(board.list_stories(conn, "K")) == 1
    with pytest.raises(BoardError):
        board.add_story(conn, "K", fid, "x", [], [])
    with pytest.raises(BoardError):
        board.add_story(conn, "K", 999, "x", ["c"], [])


def test_review_gate(conn):
    _, s = mk(conn)
    sid = s["id"]
    board.claim_story(conn, "K", sid, "a", "br", "/wt")
    for bad in ("", "   ", "\n\t"):
        with pytest.raises(BoardError):
            board.submit_story(conn, "K", sid, "a", bad)
    with pytest.raises(BoardError):
        board.submit_story(conn, "K", sid, "other", "out")
    board.submit_story(conn, "K", sid, "a", "out")
    with pytest.raises(BoardError):
        board.accept_story(conn, "K", sid, "a")
    with pytest.raises(BoardError):
        board.reject_story(conn, "K", sid, "a", "note")
    for bad in ("", "  "):
        with pytest.raises(BoardError):
            board.reject_story(conn, "K", sid, "b", bad)
    assert board.reject_story(conn, "K", sid, "b", "why")["status"] == "in-progress"
    board.submit_story(conn, "K", sid, "a", "out")
    assert board.accept_story(conn, "K", sid, "c")["status"] == "done"


def test_feature_status(conn):
    fid = board.create_feature(conn, "K", "F", "r")["id"]
    assert board.feature_status(conn, "K", fid) == "empty"
    s1 = board.add_story(conn, "K", fid, "one", ["c"], [])["id"]
    s2 = board.add_story(conn, "K", fid, "two", ["c"], [])["id"]
    assert board.feature_status(conn, "K", fid) == "todo"
    board.claim_story(conn, "K", s1, "a", "b", "/w")
    assert board.feature_status(conn, "K", fid) == "in-progress"
    board.submit_story(conn, "K", s1, "a", "o")
    assert board.feature_status(conn, "K", fid) == "in-progress"
    board.accept_story(conn, "K", s1, "b")
    board.cancel_story(conn, "K", s2, "a", "r")
    assert board.feature_status(conn, "K", fid) == "done"

    f2 = board.create_feature(conn, "K", "G", "r")["id"]
    t1 = board.add_story(conn, "K", f2, "t1", ["c"], [])["id"]
    t2 = board.add_story(conn, "K", f2, "t2", ["c"], [])["id"]
    board.cancel_story(conn, "K", t1, "a", "r")
    board.cancel_story(conn, "K", t2, "a", "r")
    assert board.feature_status(conn, "K", f2) == "cancelled"

    f3 = board.create_feature(conn, "K", "H", "r")["id"]
    u1 = board.add_story(conn, "K", f3, "u1", ["c"], [])["id"]
    board.claim_story(conn, "K", u1, "a", "b", "/w")
    board.submit_story(conn, "K", u1, "a", "o")
    board.accept_story(conn, "K", u1, "b")
    assert board.feature_status(conn, "K", f3) == "done"

    with pytest.raises(BoardError):
        board.create_feature(conn, "K", " ", "r")


def test_slug_unique(conn):
    fid = board.create_feature(conn, "K", "F", "r")["id"]
    a = board.add_story(conn, "K", fid, "Same Title!", ["c"], [])
    b = board.add_story(conn, "K", fid, "Same Title!", ["c"], [])
    assert a["slug"] == "same-title" and b["slug"] == "same-title-2"


def _writer(db, tag):
    c = board.connect(db)
    fid = board.create_feature(c, "K", "F" + tag, "r")["id"]
    for i in range(20):
        board.add_story(c, "K", fid, f"story {tag} {i}", ["c"], [])
    c.close()


def test_concurrent_writers(tmp_path):
    db = tmp_path / "shared.db"
    board.connect(db).close()
    ps = [Process(target=_writer, args=(db, t)) for t in ("p", "q")]
    for p in ps:
        p.start()
    for p in ps:
        p.join(120)
    assert [p.exitcode for p in ps] == [0, 0]
    c = board.connect(db)
    stories = board.list_stories(c, "K")
    assert len(stories) == 40
    assert len({s["id"] for s in stories}) == 40
    assert len({s["slug"] for s in stories}) == 40


SYNTH = """# header
## Layer 1 - parallel
- [DONE] T1 First thing
  _Files:_ a.py
  _Verify:_ run a
- [OPEN] T2 Second thing
  _Files:_ b.py
  _Verify:_ run b
## Layer 2 - sequential (ordered)
- [WIP] T3 Third thing
  _Verify:_ run c
- [BLOCKED] T4 Fourth thing
  _Files:_ d.py
  _Verify:_ run d
  _Blocked:_ waiting on credentials
- [OPEN] T5 Fifth thing
  _Verify:_ run e
"""


def _shape(c, key, fid):
    stories = board.list_stories(c, key, fid)
    by_id = {s["id"]: s["title"] for s in stories}
    return {
        s["title"]: (s["status"], s["review_note"], frozenset(by_id[d] for d in s["depends_on"]))
        for s in stories
    }


CAMPAIGN = """# Deployment fixture

This independent campaign exercises parallel checks and ordered changes.

## Layer 1 - sequential
- [DONE] T110 Check inputs
  _Verify:_ validate sample
  _Lessons:_ keep input evidence

## Layer 2 - parallel
- [DONE] T210 Inspect transport
  _Verify:_ inspect transport fixture
- [DONE] T220 Inspect storage
  _Verify:_ inspect storage fixture

## Layer 3 - sequential
- [OPEN] T310 Prepare configuration
  _Verify:_ compare configuration
- [OPEN] T311a Check projection
  _Verify:_ read projected fixture
- [OPEN] T320 Check recovery
  _Verify:_ restore fixture

## Layer 4 - parallel
- [WIP] T410 Exercise catalogs
  _Verify:_ list fixture tools
- [OPEN] T420 Archive outputs
  _Verify:_ inspect archive
- [OPEN] T430 Inspect matrix
  _Verify:_ compare capabilities
"""


def test_import_campaign_fixture(conn):
    text = CAMPAIGN
    ntasks = sum(1 for ln in text.splitlines() if ln.startswith("- ["))
    ndone = sum(1 for ln in text.splitlines() if ln.startswith("- [DONE]"))
    res = board.import_plan(conn, "K", text, "Plan", "s")
    stories = {s["id"]: s for s in board.list_stories(conn, "K", res["feature_id"])}
    ids = res["stories"]
    assert len(ids) == ntasks == len(stories)
    assert sum(1 for s in stories.values() if s["status"] == "done") == ndone
    layer2 = {ids["T210"], ids["T220"]}
    for t in ("T311a", "T320"):
        assert layer2 <= set(stories[ids[t]]["depends_on"])
    assert ids["T310"] in stories[ids["T311a"]]["depends_on"]
    assert ids["T311a"] in stories[ids["T320"]]["depends_on"]
    assert ids["T310"] not in stories[ids["T320"]]["depends_on"]


def test_import_synthetic_structure(conn):
    s = board.import_plan(conn, "K", SYNTH, "P", "s")["stories"]
    st = {t: board.get_story(conn, "K", i) for t, i in s.items()}
    assert [st[t]["status"] for t in ("T1", "T2", "T3", "T4", "T5")] == [
        "done", "todo", "in-progress", "todo", "todo"]
    assert st["T1"]["depends_on"] == []
    assert st["T3"]["depends_on"] == sorted([s["T1"], s["T2"]])
    assert st["T4"]["depends_on"] == sorted([s["T1"], s["T2"], s["T3"]])
    assert st["T5"]["depends_on"] == sorted([s["T1"], s["T2"], s["T4"]])
    assert st["T4"]["review_note"] == "waiting on credentials"
    assert st["T1"]["acceptance_checks"] == ["run a", "Files: a.py"]


def test_render_roundtrip_fresh_db(conn, tmp_path):
    res = board.import_plan(conn, "K", SYNTH, "P", "s")
    md = board.render_plan(conn, "K", res["feature_id"])
    assert "_Blocked:_ waiting on credentials" in md
    assert "## Layer 2 - sequential" in md
    c2 = board.connect(tmp_path / "fresh.db")
    res2 = board.import_plan(c2, "K", md, "P", "s")
    assert _shape(c2, "K", res2["feature_id"]) == _shape(conn, "K", res["feature_id"])
    assert board.render_plan(conn, "K", res["feature_id"]) == md
    assert board.render_plan(c2, "K", res2["feature_id"]) == md
    c2.close()


def test_import_twice_empty_and_unknown_raise(conn):
    board.import_plan(conn, "K", SYNTH, "P", "s")
    with pytest.raises(BoardError):
        board.import_plan(conn, "K", SYNTH, "P", "s")
    with pytest.raises(BoardError):
        board.import_plan(conn, "K", "just prose\nno tasks\n", "Q", "s")
    with pytest.raises(BoardError):
        board.import_plan(conn, "K", "- [OPEN] T1 a\n- [OPEN] T1 b\n", "R", "s")
    with pytest.raises(BoardError):
        board.render_plan(conn, "K", 999)


def test_render_campaign_fixture_byte_identical(conn):
    text = CAMPAIGN
    res = board.import_plan(conn, "K", text, "Plan", "s")
    md = board.render_plan(conn, "K", res["feature_id"])
    assert md == text
    assert md.count("_Lessons:_") == text.count("_Lessons:_") > 0


def test_status_change_differs_only_in_tag_line(conn):
    text = CAMPAIGN
    res = board.import_plan(conn, "K", text, "Plan", "s")
    ready = next(
        s for s in board.list_stories(conn, "K", res["feature_id"]) if s["status"] == "todo"
    )
    conn.execute("UPDATE story SET status='in-progress' WHERE id=?", (ready["id"],))
    md = board.render_plan(conn, "K", res["feature_id"])
    old, new = text.splitlines(), md.splitlines()
    assert len(old) == len(new)
    diff = [(o, n) for o, n in zip(old, new) if o != n]
    assert diff == [(f"- [OPEN] {ready['title']}", f"- [WIP] {ready['title']}")]


def test_add_lesson_renders_once_under_task(conn):
    text = CAMPAIGN
    res = board.import_plan(conn, "K", text, "Plan", "s")
    sid = res["stories"]["T420"]
    story = board.add_lesson(conn, "K", sid, "s", "second thought")
    assert story["body"].endswith("\n  _Lessons:_ second thought")
    md = board.render_plan(conn, "K", res["feature_id"])
    old, new = text.splitlines(), md.splitlines()
    # Attach lessons before the next task or layer without changing neighboring text.
    start = next(i for i, ln in enumerate(old) if ln.startswith("- [") and " T420 " in ln)
    end = next((i for i in range(start + 1, len(old)) if old[i].startswith(("- [", "## "))), len(old))
    while end > start + 1 and old[end - 1] == "":
        end -= 1
    expected = old[:end] + ["  _Lessons:_ second thought"] + old[end:]
    assert new == expected
    assert board.render_plan(conn, "K", res["feature_id"]) == md
    with pytest.raises(BoardError):
        board.add_lesson(conn, "K", sid, "s", "  ")
    board.cancel_story(conn, "K", sid, "s", "dropped")
    with pytest.raises(BoardError):
        board.add_lesson(conn, "K", sid, "s", "too late")


def test_added_story_gets_trailing_layer_and_reimports(conn, tmp_path):
    text = CAMPAIGN
    res = board.import_plan(conn, "K", text, "Plan", "s")
    nlayers = text.count("\n## Layer ") + text.startswith("## Layer ")
    story = board.add_story(conn, "K", res["feature_id"], "Added thing", ["run it"], [])
    md = board.render_plan(conn, "K", res["feature_id"])
    assert md.startswith(text)
    tail = md[len(text):]
    assert tail == (f"\n## Layer {nlayers + 1} - added on the board\n"
                    f"- [OPEN] T{story['id']} Added thing\n  _Verify:_ run it\n")
    with pytest.raises(BoardError, match="already exists"):
        board.import_plan(conn, "K", md, "Plan", "s")
    c2 = board.connect(tmp_path / "fresh.db")
    res2 = board.import_plan(c2, "K", md, "Plan", "s")
    assert len(res2["stories"]) == len(res["stories"]) + 1
    c2.close()


def _lesson_writer(db, story_id, tag, n):
    c = board.connect(db)
    for i in range(n):
        board.add_lesson(c, "K", story_id, f"s-{tag}", f"{tag}-{i}")
    c.close()


def test_concurrent_lessons_on_one_story_are_all_kept(tmp_path):
    """Two processes appending lessons to the same story lose none (REQ #45).

    Before the append moved inside the write transaction, 22 of 50 were lost.
    """
    db = tmp_path / "race.db"
    c = board.connect(db)
    feat = board.create_feature(c, "K", "race", "r")
    story = board.add_story(c, "K", feat["id"], "one story", ["check"], [])
    ps = [Process(target=_lesson_writer, args=(str(db), story["id"], t, 25)) for t in ("a", "b", "c")]
    for p in ps:
        p.start()
    for p in ps:
        p.join()
        assert p.exitcode == 0
    body = board.get_story(c, "K", story["id"])["body"]
    assert body.count("_Lessons:_") == 75
    for t in ("a", "b", "c"):
        for i in range(25):
            assert f"_Lessons:_ {t}-{i}\n" in body + "\n"
    c.close()
