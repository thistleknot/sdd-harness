#!/usr/bin/env python3
"""Synthetic battery for `process_ledger.py`. No live session, no spawning.

Spec: CLAUDE.md "Every process has a row too." (Hard defaults)
Task: harness change 2026-09-05 (process registry)

Follows `test_file_manifest.py`: hand the pure functions an injected process list
and assert what falls out. Nothing here starts, signals, or kills a process --
the live proof is a real backgrounded pid, run by hand, and it is not this file's
job. Every fail-open branch gets a case, because fail-open is the one property
whose regression is silent.

Run: python hooks/test_process_ledger.py
"""
from __future__ import annotations

import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import process_ledger as pl  # noqa: E402

NOW = 1_725_000_000.0
BEFORE, AFTER = NOW - 600, NOW + 600


def proc(pid, name, started=AFTER, cmdline=None, ppid=0):
    return {"pid": pid, "ppid": ppid, "name": name, "started": started,
            "cmdline": cmdline or (name + " job.py")}


CASES = []


def case(name):
    def deco(fn):
        CASES.append((name, fn))
        return fn
    return deco


# ------------------------------------------------------------------ watermark

@case("watermark round-trips through the filesystem")
def _():
    pl.WATERMARK_DIR = tempfile.mkdtemp(prefix="pltest_")
    assert pl.write_watermark("sess-abc", NOW) is not None
    assert pl.read_watermark("sess-abc") == NOW


@case("missing watermark reads as None, not zero")
def _():
    pl.WATERMARK_DIR = tempfile.mkdtemp(prefix="pltest_")
    assert pl.read_watermark("never-written") is None


@case("corrupt watermark fails open to None")
def _():
    pl.WATERMARK_DIR = tempfile.mkdtemp(prefix="pltest_")
    os.makedirs(pl.WATERMARK_DIR, exist_ok=True)
    with open(pl._watermark_path("sess-bad"), "w", encoding="utf-8") as f:
        f.write("{not json")
    assert pl.read_watermark("sess-bad") is None


@case("session id with path separators cannot escape the watermark dir")
def _():
    pl.WATERMARK_DIR = tempfile.mkdtemp(prefix="pltest_")
    p = pl._watermark_path("../../evil/id")
    assert os.path.dirname(os.path.abspath(p)) == os.path.abspath(pl.WATERMARK_DIR), p


# ------------------------------------------------------------------ claims

@case("pids are read out of a messy real-world ledger")
def _():
    ledger = """# Processes

| pid | command | started | for | stop | done by |
|---|---|---|---|---|---|
| 41220 | python train.py --epochs 3 | 14:02 | SFT run | Stop-Process -Id 41220 -Force | ~15:30 |

Also still up: the uvicorn on port 8000, pid 41880 -- reap with
`Stop-Process -Id 41880 -Force` once the smoke test is green.
"""
    got = pl.claimed_pids(ledger)
    assert 41220 in got and 41880 in got, got


@case("short numbers (ports, times) are not mistaken for pids")
def _():
    got = pl.claimed_pids("port 8000, 3 epochs, 14:02, 2026")
    assert got == {8000, 2026}, got          # 4-digit floor; 3 and 14 excluded


@case("empty or absent ledger claims nothing")
def _():
    assert pl.claimed_pids("") == set()
    assert pl.claimed_pids(None) == set()


# ------------------------------------------------------------------ the audit

@case("a candidate started after the watermark with no row is reported")
def _():
    rows = pl.unclaimed([proc(41220, "python.exe")], NOW, set())
    assert [r["pid"] for r in rows] == [41220], rows


@case("every candidate claimed by a row means silence")
def _():
    procs = [proc(41220, "python.exe"), proc(41880, "node.exe")]
    assert pl.unclaimed(procs, NOW, {41220, 41880}) == []


@case("partly claimed reports only the rest")
def _():
    procs = [proc(41220, "python.exe"), proc(41880, "node.exe"), proc(42010, "ollama.exe")]
    rows = pl.unclaimed(procs, NOW, {41880})
    assert [r["pid"] for r in rows] == [41220, 42010], rows


@case("a process older than the watermark is not ours to reap")
def _():
    assert pl.unclaimed([proc(41220, "python.exe", started=BEFORE)], NOW, set()) == []


@case("non-candidate executables are the operator's machine, not a leak")
def _():
    procs = [proc(1, "chrome.exe"), proc(2, "Teams.exe"), proc(3, "steam.exe")]
    assert pl.unclaimed(procs, NOW, set()) == []


@case("harness tooling is exempt even though it matches nothing else")
def _():
    procs = [proc(1, "claude.exe"), proc(2, "pwsh.exe"), proc(3, "git.exe"),
             proc(4, "powershell.exe")]
    assert pl.unclaimed(procs, NOW, set()) == []


@case("the hook never reports itself")
def _():
    assert pl.unclaimed([proc(999, "python.exe")], NOW, set(), self_pid=999) == []


@case("the hook never reports its own launcher shim (whole ancestor chain)")
def _():
    # py310/Scripts/python.exe re-execs the real interpreter: os.getpid() is the
    # child, and the parent shim carries an identical command line. Live-run bug.
    shim = proc(24660, "python.exe", cmdline="python.exe hooks/process_ledger.py")
    me = proc(5040, "python.exe", cmdline="python.exe hooks/process_ledger.py", ppid=24660)
    leak = proc(41220, "python.exe", cmdline="python train.py")
    rows = pl.unclaimed([shim, me, leak], NOW, set(), self_pid=5040)
    assert [r["pid"] for r in rows] == [41220], rows


@case("ancestry stops on a cycle instead of hanging")
def _():
    a, b = proc(10, "python.exe", ppid=11), proc(11, "python.exe", ppid=10)
    assert pl._ancestry([a, b], 10) == {10, 11}
    assert pl._ancestry([a, b], None) == set()


@case("bare posix names with no .exe are matched too")
def _():
    rows = pl.unclaimed([proc(41220, "python3"), proc(41221, "uvicorn")], NOW, set())
    assert [r["pid"] for r in rows] == [41220, 41221], rows


@case("a launcher shim and its interpreter collapse to one line")
def _():
    shim = proc(29224, "python.exe", cmdline="py310/Scripts/python.exe -c ...")
    real = proc(36008, "python.exe", cmdline="Python310/python.exe -c ...", ppid=29224)
    rows = pl.unclaimed([shim, real], NOW, set())
    assert [r["pid"] for r in rows] == [36008], rows


@case("claiming the child does not resurrect its shim as a new leak")
def _():
    shim = proc(29224, "python.exe", cmdline="py310/Scripts/python.exe -c ...")
    real = proc(36008, "python.exe", cmdline="Python310/python.exe -c ...", ppid=29224)
    assert pl.unclaimed([shim, real], NOW, {36008}) == []


@case("a genuine parent/child of DIFFERENT kinds both report")
def _():
    parent = proc(500, "node.exe")
    child = proc(501, "python.exe", ppid=500)
    rows = pl.unclaimed([parent, child], NOW, set())
    assert [r["pid"] for r in rows] == [500, 501], rows


@case("full paths reduce to their stem")
def _():
    assert pl._stem("C:\\Users\\user\\py310\\python.exe") == "python"
    assert pl._stem("/usr/bin/node") == "node"
    assert pl._stem("") == ""


# ------------------------------------------------------------------ rendering

@case("the finding carries the pid, the command, and a runnable reap")
def _():
    out = pl.render([proc(41220, "python.exe", cmdline="python train.py --epochs 3")], True)
    assert "41220" in out
    assert "train.py" in out
    assert "Stop-Process -Id 41220 -Force" in out


@case("a missing ledger is called out as the next step")
def _():
    out = pl.render([proc(41220, "python.exe")], False)
    assert "no ledger at all" in out


@case("an absurd command line is truncated, not dumped")
def _():
    out = pl.render([proc(41220, "python.exe", cmdline="python " + "x" * 500)], True)
    assert max(len(line) for line in out.splitlines()) < 160, out


# ------------------------------------------------------------------ fail-open

@case("CIM timestamps parse from both shapes, and garbage yields 0")
def _():
    assert pl._cim_epoch("/Date(1725000000000)/") == 1_725_000_000.0
    assert pl._cim_epoch("20260905141500.000000+000") > 0
    assert pl._cim_epoch("nonsense") == 0.0
    assert pl._cim_epoch(None) == 0.0


@case("main exits 0 on malformed stdin, empty payload, and unknown session")
def _():
    import io
    pl.WATERMARK_DIR = tempfile.mkdtemp(prefix="pltest_")
    for raw in ("{not json", "", '{"session_id": "never-seen", "cwd": "%s"}'
                % tempfile.mkdtemp(prefix="pltest_").replace("\\", "/")):
        stdin, sys.stdin = sys.stdin, io.StringIO(raw)
        try:
            assert pl.main([]) == 0, raw
        finally:
            sys.stdin = stdin


@case("watermark mode writes the stamp and stays silent")
def _():
    import io
    pl.WATERMARK_DIR = tempfile.mkdtemp(prefix="pltest_")
    stdin, sys.stdin = sys.stdin, io.StringIO('{"session_id": "sess-live"}')
    try:
        assert pl.main(["--watermark"]) == 0
    finally:
        sys.stdin = stdin
    stamped = pl.read_watermark("sess-live")
    assert stamped is not None and abs(stamped - time.time()) < 60, stamped


def run():
    failed = []
    for name, fn in CASES:
        try:
            fn()
            print("  PASS  " + name)
        except AssertionError as exc:
            failed.append((name, exc))
            print("  FAIL  " + name + "  " + str(exc))
        except Exception as exc:  # noqa: BLE001
            failed.append((name, exc))
            print("  ERROR " + name + "  " + repr(exc))
    print("\n{}/{} passed".format(len(CASES) - len(failed), len(CASES)))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(run())
