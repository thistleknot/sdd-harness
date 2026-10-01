#!/usr/bin/env python3
"""Battery for the ID-bearing store.

Two things are actually under test, and neither is "does SQLite work".

First, **validation that refuses**. Every guard here exists because the failure
it prevents is silent: an unexplained `pbt=n/a` turns the gate into a rubber
stamp, an empty `sut_symbol` leaves G3 with nothing to mutate, and an unknown
`--field` reaching the UPDATE statement is both a typo swallowed and an
injection seam. A guard that accepts bad input and shrugs is worse than absent.

Second, **the markdown round-trip**. The DB is authoritative and markdown is
derived, so the risk is not that rendering fails loudly -- it is that a human's
hand edit inside the generated region gets overwritten without anyone noticing.
Half these cases assert the tool *refuses* rather than that it succeeds.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from spec_paths import is_exempt  # noqa: E402
from spec_store import extract_region, splice, _region_hash  # noqa: E402

STORE = os.path.join(HERE, "spec_store.py")
CHECKS: list[tuple[str, bool]] = []


def check(name: str, got, want) -> None:
    ok = got == want
    CHECKS.append((name, ok))
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + ("" if ok else f"\n      got {got!r} want {want!r}"))


def tree() -> str:
    root = tempfile.mkdtemp(prefix="store-")
    os.makedirs(os.path.join(root, ".spec", "specs", "auth"), exist_ok=True)
    run(root, "init")
    return root


def run(root: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, STORE, *args], cwd=root,
                          capture_output=True, text=True)


def md(root: str, name: str) -> str:
    path = os.path.join(root, ".spec", "specs", "auth", name)
    return open(path, encoding="utf-8").read() if os.path.isfile(path) else ""


def write_md(root: str, name: str, text: str) -> None:
    with open(os.path.join(root, ".spec", "specs", "auth", name), "w",
              encoding="utf-8", newline="\n") as fh:
        fh.write(text)


REQ = ("--feature=auth", "--text=While active, the system SHALL refresh", "--strength=SHALL")


def main() -> int:
    # --- exemption carve-out -------------------------------------------------
    check("is_exempt: spec.db is blocked", is_exempt("/repo/.spec/spec.db"), False)
    check("is_exempt: state.json still blocked", is_exempt("/repo/.spec/specs/a/state.json"), False)
    check("is_exempt: ordinary spec markdown still exempt",
          is_exempt("/repo/.spec/specs/a/requirements.md"), True)
    check("is_exempt: source file still gated", is_exempt("/repo/src/auth.py"), False)

    # --- id allocation -------------------------------------------------------
    r = tree()
    check("init is idempotent", run(r, "init").returncode, 0)
    run(r, "add-req", *REQ)
    run(r, "add-req", "--feature=auth", "--text=Second", "--strength=MUST")
    out = run(r, "show").stdout
    check("ids allocated sequentially", ("R-1" in out and "R-2" in out), True)

    p = run(r, "add-req", "--feature=auth", "--text=Third", "--strength=MUST")
    check("ids do not restart", "R-3" in p.stdout, True)

    # --- validation refuses --------------------------------------------------
    p = run(r, "add-req", "--feature=auth", "--text=x", "--strength=PROBABLY")
    check("bad strength rejected", p.returncode, 1)
    p = run(r, "add-req", "--feature=auth", "--text=x", "--strength=MAY", "--pbt=n/a")
    check("pbt=n/a without a reason rejected", p.returncode, 1)
    p = run(r, "add-req", "--feature=auth", "--text=x", "--strength=MAY",
            "--pbt=n/a", "--pbt-reason=cosmetic")
    check("pbt=n/a with a reason accepted", p.returncode, 0)
    p = run(r, "add-req", "--feature=auth", "--text=x", "-strength=MUST")
    check("bare/typo flag rejected rather than ignored", p.returncode, 1)

    p = run(r, "add-prop", "--feature=auth", "--sut_symbol=")
    check("empty sut_symbol rejected -- G3 needs a seam", p.returncode, 1)
    p = run(r, "add-prop", "--feature=auth", "--sut_symbol=f", "--requirement_id=R-99")
    check("dangling requirement_id rejected", p.returncode, 1)
    p = run(r, "add-prop", "--feature=auth", "--sut_symbol=refresh", "--requirement_id=R-1")
    check("valid property accepted", p.returncode, 0)

    # --- update --------------------------------------------------------------
    p = run(r, "update", "R-1", "--nonexistent=1")
    check("unknown field rejected (typo + injection seam)", p.returncode, 1)
    p = run(r, "update", "R-1", "--text=Rewritten")
    check("known field accepted", p.returncode, 0)
    check("update took effect", "Rewritten" in run(r, "show").stdout, True)
    p = run(r, "update", "P-1", "--g1=maybe")
    check("bad gate value rejected", p.returncode, 1)
    run(r, "update", "P-1", "--g1=pass")
    check("gate recorded", "G1:pass" in run(r, "show").stdout, True)
    check("gate write stamps checked_at",
          "checked_at" in run(r, "update", "P-1", "--g2=pass").stdout, True)
    p = run(r, "update", "X-1", "--text=y")
    check("unknown id prefix rejected", p.returncode, 1)
    p = run(r, "update", "R-99", "--text=y")
    check("missing record rejected", p.returncode, 1)
    p = run(r, "update", "R-1")
    check("update with no fields rejected", p.returncode, 1)
    shutil.rmtree(r, ignore_errors=True)

    # --- render round-trip ---------------------------------------------------
    r = tree()
    run(r, "add-req", *REQ)
    run(r, "add-task", "--feature=auth", "--text=Implement refresh")
    check("render succeeds", run(r, "render").returncode, 0)
    first = md(r, "requirements.md")
    check("ids surface in markdown", "**R-1**" in first, True)
    check("tasks render as checkboxes", "- [ ] **T-1**" in md(r, "tasks.md"), True)

    run(r, "render")
    check("render is idempotent", md(r, "requirements.md"), first)
    check("reconcile clean after render", run(r, "reconcile").returncode, 0)

    write_md(r, "requirements.md", "# Preamble\n\nHand-written.\n\n" + first)
    run(r, "render")
    check("prose outside the markers survives", "Hand-written." in md(r, "requirements.md"), True)

    # --- hand-edit detection -------------------------------------------------
    tampered = md(r, "requirements.md").replace("refresh", "refresh IMMEDIATELY")
    write_md(r, "requirements.md", tampered)
    p = run(r, "reconcile")
    check("reconcile flags a hand-edited region", p.returncode, 1)
    check("drift names the file", "requirements.md" in p.stdout, True)
    p = run(r, "render")
    check("render refuses to overwrite a hand edit", p.returncode, 1)
    check("hand edit still present after refusal", "IMMEDIATELY" in md(r, "requirements.md"), True)
    check("--force discards it", run(r, "render", "--force").returncode, 0)
    check("forced render restored the DB view", "IMMEDIATELY" in md(r, "requirements.md"), False)
    check("reconcile clean again", run(r, "reconcile").returncode, 0)

    # a DB change with untouched markdown is staleness, not tampering
    run(r, "add-req", "--feature=auth", "--text=Added later", "--strength=MUST")
    p = run(r, "reconcile")
    check("stale markdown reported", p.returncode, 1)
    check("stale is distinguished from hand-edited", "hand-edited" in p.stdout, False)
    check("render fixes staleness without --force", run(r, "render").returncode, 0)
    shutil.rmtree(r, ignore_errors=True)

    # --- splice/extract units ------------------------------------------------
    spliced = splice("", "body")
    body, recorded = extract_region(spliced)
    check("extract recovers the body", body, "body")
    check("checksum matches on a fresh splice", recorded, _region_hash("body"))
    check("no markers means no region", extract_region("plain prose"), None)
    check("unterminated region is not a region", extract_region("<!-- spec:begin -->\nx"), None)
    check("re-splice replaces rather than appends", splice(spliced, "body").count("spec:begin"), 1)

    # --- empty store ---------------------------------------------------------
    r = tree()
    check("render on an empty store is a no-op, not an error", run(r, "render").returncode, 0)
    check("reconcile on an empty store is clean", run(r, "reconcile").returncode, 0)
    shutil.rmtree(r, ignore_errors=True)

    # --- no .spec root -------------------------------------------------------
    bare = tempfile.mkdtemp(prefix="bare-")
    check("no .spec root fails loudly", run(bare, "show").returncode, 1)
    shutil.rmtree(bare, ignore_errors=True)

    failed = sum(1 for _, ok in CHECKS if not ok)
    print(f"\n{len(CHECKS) - failed}/{len(CHECKS)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    sys.exit(main())
