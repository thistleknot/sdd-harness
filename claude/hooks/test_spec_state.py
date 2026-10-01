#!/usr/bin/env python3
"""Battery for per-requirement coverage in `spec_state.py status`.

What is actually under test is the *verdict*, not the formatting. A coverage
report is only worth reading if UNCOVERED and EXEMPT stay distinguishable: an
unproved requirement that prints as EXEMPT is a hole the report hides, which is
strictly worse than no report at all. The same goes for PARTIAL vs PASS -- a
property whose gates were never run must never read as proved.

The second theme is **degradation**. `status` is a report, never a gate, so a
repo with no store, a feature with no requirements, and a corrupt DB must each
still produce the rest of the status output with exit 0.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

STATE = os.path.join(HERE, "spec_state.py")
STORE = os.path.join(HERE, "spec_store.py")
CHECKS: list[tuple[str, bool]] = []


def check(name: str, got, want) -> None:
    ok = got == want
    CHECKS.append((name, ok))
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + ("" if ok else f"\n      got {got!r} want {want!r}"))


def run(root: str, script: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, script, *args], cwd=root,
                          capture_output=True, text=True)


def tree(with_store: bool = True) -> str:
    """A spec-driven repo with one spec named 'auth'."""
    root = tempfile.mkdtemp(prefix="state-")
    run(root, STATE, "init")
    run(root, STATE, "new", "auth")
    if with_store:
        run(root, STORE, "init")
    return root


def status(root: str, *args: str) -> str:
    p = run(root, STATE, "status", *args)
    check(f"status exits 0 {' '.join(args)}".strip(), p.returncode, 0)
    return p.stdout


def verdict_of(out: str, rid: str) -> str | None:
    """The verdict token on the coverage line for one requirement id."""
    for line in out.splitlines():
        parts = line.split()
        if parts and parts[0] == rid:
            return parts[1]
    return None


REQ = ("add-req", "--feature=auth", "--strength=SHALL")


def main() -> int:
    # --- degradation ---------------------------------------------------------
    bare = tempfile.mkdtemp(prefix="bare-")
    p = run(bare, STATE, "status")
    check("not spec-driven: status still exits 0", p.returncode, 0)
    check("not spec-driven: says so", "not spec-driven" in p.stdout, True)
    shutil.rmtree(bare, ignore_errors=True)

    r = tree(with_store=False)
    out = status(r)
    check("store absent: spec is still listed", "auth" in out, True)
    check("store absent: coverage block is silent", "coverage:" in out, False)
    shutil.rmtree(r, ignore_errors=True)

    r = tree()
    out = status(r)
    check("empty store: coverage says no requirements",
          "no requirements for this feature" in out, True)
    shutil.rmtree(r, ignore_errors=True)

    # --- verdicts ------------------------------------------------------------
    r = tree()
    # R-1 unproved, R-2 exempt with a reason, R-3..R-6 carry properties.
    run(r, STORE, *REQ, "--text=R1 unproved")
    run(r, STORE, *REQ, "--text=R2 exempt", "--pbt=n/a",
        "--pbt_reason=pure IO shim, nothing to quantify over")
    for n in range(3, 7):
        run(r, STORE, *REQ, f"--text=R{n} proved")
        run(r, STORE, "add-prop", "--feature=auth", f"--requirement_id=R-{n}",
            "--sut_symbol=refresh")
    # P-1 belongs to R-3 and stays unrun. The rest get explicit gates.
    for pid, gate in (("P-2", "pass"), ("P-3", "fail"), ("P-4", "pass")):
        run(r, STORE, "update", pid, f"--g1={gate}", f"--g2={gate}",
            f"--g3={gate}", f"--g4={gate}")
    # P-4's requirement is fully proved; P-2 is too. Break P-2's G3 only, to
    # prove one failing gate out of four is enough to sink the requirement.
    run(r, STORE, "update", "P-2", "--g3=unrun")

    out = status(r, "--full")
    check("no properties and no reason is UNCOVERED", verdict_of(out, "R-1"), "UNCOVERED")
    check("pbt=n/a with a reason is EXEMPT", verdict_of(out, "R-2"), "EXEMPT")
    check("EXEMPT shows the reason", "pure IO shim" in out, True)
    check("never-run gates are PARTIAL", verdict_of(out, "R-3"), "PARTIAL")
    check("one unrun gate among passes is PARTIAL", verdict_of(out, "R-4"), "PARTIAL")
    check("any failing gate is FAIL", verdict_of(out, "R-5"), "FAIL")
    check("all four gates passing is PASS", verdict_of(out, "R-6"), "PASS")

    # --- default view hides only the settled rows ----------------------------
    plain = status(r)
    check("default view hides PASS rows", verdict_of(plain, "R-6"), None)
    check("default view keeps UNCOVERED", verdict_of(plain, "R-1"), "UNCOVERED")
    check("default view keeps FAIL", verdict_of(plain, "R-5"), "FAIL")
    check("default view keeps EXEMPT visible as a decision",
          verdict_of(plain, "R-2"), "EXEMPT")
    check("summary counts every requirement, shown or not",
          "6 requirements" in plain, True)

    # --- a corrupt DB must not take the report down --------------------------
    with open(os.path.join(r, ".spec", "spec.db"), "wb") as fh:
        fh.write(b"this is not a database")
    p = run(r, STATE, "status")
    check("corrupt db: status still exits 0", p.returncode, 0)
    check("corrupt db: the rest of the report survives", "Spec root" in p.stdout, True)
    check("corrupt db: no coverage claims are made", "coverage:" in p.stdout, False)
    shutil.rmtree(r, ignore_errors=True)

    # --- argument handling ---------------------------------------------------
    r = tree()
    p = run(r, STATE, "status", "--ful")
    check("a mistyped flag is refused, not ignored", p.returncode, 1)
    shutil.rmtree(r, ignore_errors=True)

    failed = sum(1 for _, ok in CHECKS if not ok)
    print(f"\n{len(CHECKS) - failed}/{len(CHECKS)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    sys.exit(main())
