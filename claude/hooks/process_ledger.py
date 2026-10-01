#!/usr/bin/env python3
"""SessionStart watermark + Stop audit: flag live pids that no ledger row claims.

Spec: CLAUDE.md "Every process has a row too." (Hard defaults)
Task: harness change 2026-09-05 (operator: "running processes need to be treated
      like our file registry").

Thesis
------
`file_manifest.py` answers "may this file exist?". Nothing answered the same
question for processes, so a session could spawn a server, roll its context, forget
the pid, and leave it holding RAM until the operator noticed. That has already cost
45 GB on this machine once, and a replaced FastMCP listener another time.

The rule
--------
A process that this session started, is still running at Stop, and is claimed by no
row in `<cwd>/.tmp/processes.md` is a LEAK. Report it with the pid, its verbatim
command line, and the exact `Stop-Process` command to reap it.

WARN, NOT BLOCK -- deliberately, for the same reason `task_lineage.py` warns: a
gate that trapped the turn over a background process the operator started on purpose
would be muted inside an hour, taking the real signal with it.

Deliberately NOT flagged
------------------------
- Processes that predate this session's watermark (not ours to reap)
- Anything outside CANDIDATES -- the operator's machine is not this session's mess
- The harness's own tooling (claude, pwsh, git, node's editor server, ...)
- Any pid whose number appears anywhere in `.tmp/processes.md`

Contract
--------
Require   - stdin carries the hook payload with a `session_id`.
Guarantee - exit 0 always. `--watermark` writes one small JSON file and prints
            nothing. The Stop mode prints a finding to stderr, or nothing.
Maintain  - fails OPEN and SILENT on every unexpected condition: no psutil and no
            PowerShell, unreadable watermark, unparseable ledger, no cwd.
Assert    - never kills, signals, or otherwise touches a process. It reads, and it
            prints the command the operator can run. Enforcement that reaps on its
            own would eventually reap the wrong thing.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, OSError):
    pass

WATERMARK_DIR = os.path.join(os.path.expanduser("~"), ".claude", ".process-watermarks")
LEDGER = os.path.join(".tmp", "processes.md")

# Executables worth auditing: the ones a session actually spawns and forgets.
CANDIDATES = {"python", "python3", "pythonw", "node", "deno", "bun", "uvicorn", "gunicorn",
              "streamlit", "ollama", "llama-server", "docling", "java", "pytest",
              "jupyter", "ray", "vllm"}

# Source-of-the-session tooling. Never a leak, always running, would be pure noise.
EXEMPT = {"claude", "code", "pwsh", "powershell", "git", "bash", "sh", "cmd",
          "conhost", "windowsterminal", "explorer", "ollama app"}


def _stem(name: str) -> str:
    """'C:/py310/python.exe' -> 'python'. Bare, lowercased, no extension."""
    base = os.path.basename((name or "").replace("\\", "/")).lower()
    return base[:-4] if base.endswith(".exe") else base


# --------------------------------------------------------------------------- #
# watermark
# --------------------------------------------------------------------------- #

def _watermark_path(session_id: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", session_id or "unknown")
    return os.path.join(WATERMARK_DIR, safe + ".json")


def write_watermark(session_id: str, now: float) -> str | None:
    """Stamp when this session began. Returns the path, or None if it could not."""
    try:
        os.makedirs(WATERMARK_DIR, exist_ok=True)
        path = _watermark_path(session_id)
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"session_id": session_id, "started": now}, f)
        return path
    except Exception:
        return None


def read_watermark(session_id: str) -> float | None:
    try:
        with open(_watermark_path(session_id), encoding="utf-8") as f:
            started = json.load(f).get("started")
        return float(started) if started is not None else None
    except Exception:
        return None


# --------------------------------------------------------------------------- #
# enumeration
# --------------------------------------------------------------------------- #

def _via_psutil() -> list[dict] | None:
    try:
        import psutil
    except Exception:
        return None
    out: list[dict] = []
    for p in psutil.process_iter(["pid", "ppid", "name", "create_time", "cmdline"]):
        try:
            info = p.info
            out.append({"pid": int(info["pid"]),
                        "ppid": int(info.get("ppid") or 0),
                        "name": info.get("name") or "",
                        "started": float(info.get("create_time") or 0),
                        "cmdline": " ".join(info.get("cmdline") or []).strip()})
        except Exception:
            continue
    return out


def _via_powershell() -> list[dict] | None:
    # -NoProfile decodes native output as ANSI unless the console encoding is forced;
    # without this line every comparison against a captured string is wrong.
    script = ("[Console]::OutputEncoding = [Text.Encoding]::UTF8; "
              "Get-CimInstance Win32_Process | "
              "Select-Object ProcessId,ParentProcessId,Name,CommandLine,CreationDate | "
              "ConvertTo-Json -Compress -Depth 2")
    try:
        p = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                           capture_output=True, text=True, encoding="utf-8", timeout=8)
        if p.returncode != 0 or not p.stdout.strip():
            return None
        rows = json.loads(p.stdout)
    except Exception:
        return None
    if isinstance(rows, dict):
        rows = [rows]
    out: list[dict] = []
    for r in rows:
        try:
            out.append({"pid": int(r.get("ProcessId") or 0),
                        "ppid": int(r.get("ParentProcessId") or 0),
                        "name": r.get("Name") or "",
                        "started": _cim_epoch(r.get("CreationDate")),
                        "cmdline": (r.get("CommandLine") or "").strip()})
        except Exception:
            continue
    return out


def _cim_epoch(value) -> float:
    """CIM hands back either '/Date(1725500000000)/' or 'YYYYMMDDhhmmss.ffffff+ooo'."""
    if not value:
        return 0.0
    if isinstance(value, dict):                      # ConvertTo-Json datetime shape
        value = value.get("value") or value.get("DateTime") or ""
    text = str(value)
    m = re.search(r"/Date\((\d+)", text)
    if m:
        return int(m.group(1)) / 1000.0
    m = re.match(r"(\d{14})", text)
    if m:
        try:
            return time.mktime(time.strptime(m.group(1), "%Y%m%d%H%M%S"))
        except Exception:
            return 0.0
    return 0.0


def list_processes() -> list[dict] | None:
    """Every running process, or None when neither backend is available."""
    return _via_psutil() or _via_powershell()


# --------------------------------------------------------------------------- #
# the audit
# --------------------------------------------------------------------------- #

def claimed_pids(ledger_text: str) -> set[int]:
    """Every integer in the ledger counts as a claim.

    Generous on purpose, exactly as `task_lineage.py` is with paths: a strict parser
    rejects real ledgers over formatting and teaches the reader to ignore the hook.
    Two- and three-digit numbers (ports, dates, durations) are excluded -- a real
    Windows pid is >= 1000 in practice and a false claim is worse than a false alarm.
    """
    return {int(n) for n in re.findall(r"\b\d{4,7}\b", ledger_text or "")}


def _ancestry(processes: list[dict], pid: int | None) -> set[int]:
    """`pid` and every process above it.

    Load-bearing, and only a live run showed why: `py310/Scripts/python.exe` is a
    shim that re-execs the real interpreter, so the hook's own `os.getpid()` is the
    CHILD. Excluding self alone left the shim -- same command line, same start time
    -- looking exactly like a leaked python, and the hook reported itself every run.
    """
    if not pid:
        return set()
    parent = {p.get("pid"): p.get("ppid") for p in processes}
    seen, cur = set(), pid
    while cur and cur not in seen:
        seen.add(cur)
        cur = parent.get(cur)
    return seen


def unclaimed(processes: list[dict], since: float, claimed: set[int],
              self_pid: int | None = None) -> list[dict]:
    """Candidate processes started after `since` that no ledger row claims."""
    mine = _ancestry(processes, self_pid) | ({self_pid} if self_pid else set())

    candidates = []
    for p in processes:
        pid = p.get("pid") or 0
        if pid <= 0 or pid in mine:
            continue
        if float(p.get("started") or 0) <= since:
            continue
        stem = _stem(p.get("name") or "")
        if stem in EXEMPT or stem not in CANDIDATES:
            continue
        candidates.append(p)

    # A launcher shim and the interpreter it re-execs are ONE process to the
    # operator: reaping either takes both. Keep the child, drop the parent, so the
    # finding has one line per thing that is actually running. Computed over ALL
    # candidates, not the unclaimed remainder -- otherwise writing the child's row
    # resurrects its shim as a fresh "leak", which is how a live run found this.
    stems = {p["pid"]: _stem(p.get("name") or "") for p in candidates}
    shims = {p.get("ppid") for p in candidates
             if stems.get(p.get("ppid")) == _stem(p.get("name") or "")}

    return sorted((p for p in candidates
                   if p["pid"] not in shims and p["pid"] not in claimed),
                  key=lambda p: p["pid"])


def render(rows: list[dict], has_ledger: bool) -> str:
    head = ("PROCESSES: %d process(es) started during this session are still running "
            "with no row in .tmp/processes.md" % len(rows))
    if not has_ledger:
        head += ("\n  There is no ledger at all -- nothing this session spawned is "
                 "traceable. Writing the rows is the next step, not more code.")
    body = []
    for p in rows:
        cmd = (p.get("cmdline") or p.get("name") or "?")
        if len(cmd) > 90:
            cmd = cmd[:87] + "..."
        stamp = time.strftime("%H:%M", time.localtime(p["started"])) if p.get("started") else "?"
        body.append("    pid %-7d %-90s started %s" % (p["pid"], cmd, stamp))
    reap = "  ".join("Stop-Process -Id %d -Force" % p["pid"] for p in rows[:5])
    tail = ("\n  Either add their rows, or reap them:  %s"
            "\n  A live pid with no row is a leak. Do not report done over the top of one."
            % reap)
    return "%s\n%s%s" % (head, "\n".join(body), tail)


def main(argv: list[str]) -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        payload = {}

    session_id = str(payload.get("session_id") or "unknown")

    if "--watermark" in argv:
        write_watermark(session_id, time.time())
        return 0

    since = read_watermark(session_id)
    if since is None:
        return 0                          # no watermark, no idea what is ours

    cwd = payload.get("cwd") or os.getcwd()
    ledger_path = os.path.join(cwd, LEDGER)
    try:
        with open(ledger_path, encoding="utf-8") as f:
            ledger_text = f.read()
        has_ledger = True
    except Exception:
        ledger_text, has_ledger = "", False

    procs = list_processes()
    if not procs:
        return 0                          # no backend -- fail open and silent

    rows = unclaimed(procs, since, claimed_pids(ledger_text), self_pid=os.getpid())
    if not rows:
        return 0

    print(render(rows, has_ledger), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
