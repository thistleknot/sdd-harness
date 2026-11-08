"""decision_gate.py - project-local decision gate (V2-W2 + V2-W6).

Spec: SpecsDB task #95, ddsd-gaps plan V2-W2 (enforce at the PROJECT's gate, not
the harness self-check) and V2-W6 (expiring waivers).

This is a TEMPLATE a project copies into its own repo and runs from its own
pre-commit / CI step. It is NOT wired into the harness verify.ps1 (that script is
a harness self-check; running project decisions there was the V1 category error).

Reads, from the project directory:
  decisions.md   lines:  Decision: D-<id> [Status] verify: <allowlisted command>
  waivers.md     lines:  D-<id> scope=<text> expires=<YYYY-MM-DD>

Behavior:
  - For each [Accepted] decision, run its allowlisted verify command (60s timeout).
  - A failing command is a gate FAIL unless a NON-EXPIRED waiver covers that decision id.
  - An EXPIRED waiver does not excuse a failure (it re-fails) - DDSD #5: exceptions expire.
  - Only commands on the allowlist run; anything else is refused (never executed).

Exit 0 = pass, 1 = fail, 2 = usage/storage error.
"""
import datetime
import os
import re
import subprocess
import sys

ALLOWED_CMD = re.compile(r"^(?:python(?:3)?(?:\s+-m\s+pytest)?|py(?:\s+-m\s+pytest)?|pytest)(?:\s+\S+)*$")
SHELL_METACHARS = re.compile(r"[|;&`$<>]|\|\||&&|\b(curl|wget|sh|bash|powershell|cmd|rm|mv|del)\b")
DEC_RE = re.compile(r"^Decision:\s*(\S+)\s*\[([A-Za-z]+)\]\s*verify:\s*(.+)$")
WAIV_RE = re.compile(r"^(\S+)\s+scope=(.+?)\s+expires=(\d{4}-\d{2}-\d{2})\s*$")


def load(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8-sig") as fh:  # tolerate BOM (PS 5.1 writers)
        return [ln.strip() for ln in fh if ln.strip() and not ln.startswith("#")]


def parse_decisions(md_path):
    out = []
    for ln in load(md_path):
        m = DEC_RE.match(ln)
        if m:
            out.append({"id": m.group(1), "status": m.group(2), "verify": m.group(3).strip()})
    return out


def parse_waivers(md_path):
    today = datetime.date.today()
    out = {}
    for ln in load(md_path):
        m = WAIV_RE.match(ln)
        if not m:
            continue
        try:
            exp = datetime.date.fromisoformat(m.group(3))
        except ValueError:
            continue
        out[m.group(1)] = {"scope": m.group(2), "expires": exp, "active": exp >= today}
    return out


def allowed(cmd):
    return bool(ALLOWED_CMD.match(cmd)) and not SHELL_METACHARS.search(cmd)


def main(argv):
    proj = argv[1] if len(argv) > 1 else "."
    decs = parse_decisions(os.path.join(proj, "decisions.md"))
    waivs = parse_waivers(os.path.join(proj, "waivers.md"))
    if not decs:
        print("no decisions.md entries found"); return 2
    fails = 0
    for d in decs:
        if d["status"].lower() != "accepted":
            print(f"  skip {d['id']} [{d['status']}]"); continue
        if not allowed(d["verify"]):
            print(f"  FAIL {d['id']}: verify command not on allowlist (refused): {d['verify'][:50]!r}")
            fails += 1; continue
        try:
            argv = d["verify"].split()
            if argv[0] in ("python", "python3", "py"):
                argv[0] = sys.executable
            r = subprocess.run(argv, cwd=proj, timeout=60,
                               capture_output=True, text=True)
        except subprocess.TimeoutExpired:
            print(f"  FAIL {d['id']}: verify timed out"); fails += 1; continue
        w = waivs.get(d["id"])
        if r.returncode == 0:
            print(f"  PASS {d['id']}: {d['verify']}")
        elif w and w["active"]:
            print(f"  WAIVED {d['id']} (expires {w['expires']}): {d['verify']}")
        else:
            reason = "expired waiver" if w else "no waiver"
            print(f"  FAIL {d['id']}: {d['verify']} -> rc={r.returncode} ({reason})")
            fails += 1
    print(f"decision_gate: {fails} failure(s)")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
