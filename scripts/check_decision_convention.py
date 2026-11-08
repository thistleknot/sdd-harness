"""check_decision_convention.py - SpecsDB decision-convention check (WARN-only).

Spec: SpecsDB REQ #73 / task #95; convention per decisions #36, #39; v2 per
ddsd-gaps plan V2-W1 (allowlist), V2-W4 (lifecycle tokens), V2-W5 (CDR teeth).

Validates decisions created on/after CUTOFF:
  1. title starts with a type token: ADR | CDR | EDR | IDR | MDD
  2. context carries an AI-Context block with all four labels
  3. context carries Status: and Owner: lines (lifecycle + accountability)
  4. every command on the "Verification commands:" line is on the ALLOWLIST
     (static check only - this script NEVER executes commands; execution happens
     at the target project's own gate via decision_gate.py)
  5. a CDR decision must carry at least one allowlisted executable command,
     else it is a "label-only CDR" (DDSD #4: a contract with no test is a sticker)

Violations print WARN lines. Exit 0 unless the DB cannot be read (fail fast on
storage, never on content).
"""
import os
import re
import sqlite3
import sys

DB = os.environ.get("SPECS_DB", r"C:\Users\user\.mcp\specs\specs.db")
CUTOFF = os.environ.get("SPECS_CONVENTION_CUTOFF", "2026-11-07")
TYPES = ("ADR", "CDR", "EDR", "IDR", "MDD")
LABELS = ("AI-Context:", "Constraints:", "Patterns:", "Anti-patterns:", "Verification commands:")
LIFECYCLE = ("Status:", "Owner:")

# Allowlist: only test-runner forms. Paths must be project-relative (no leading
# absolute drive, no '..'). Anything with shell metacharacters is rejected.
SHELL_METACHARS = re.compile(r"[|;&`$<>]|\|\||&&|\b(curl|wget|sh|bash|zsh|powershell|cmd|rm|mv|del)\b")
ALLOWED_CMD = re.compile(r"^(?:python(?:3)?(?:\s+-m\s+pytest)?|py(?:\s+-m\s+pytest)?|pytest)(?:\s+\S+)*$")
REL_PATH = re.compile(r"^[A-Za-z0-9_./-]+\.(?:py)$")


def _commands_of(context: str):
    """Return the list of command strings on the Verification commands: line."""
    m = re.search(r"Verification commands:(.*)", context)
    if not m:
        return []
    raw = m.group(1).strip()
    parts = re.split(r"[;\n]", raw)
    return [p.strip() for p in parts if p.strip()]


def _command_allowed(cmd: str) -> bool:
    if SHELL_METACHARS.search(cmd):
        return False
    if not ALLOWED_CMD.match(cmd):
        return False
    # any bare .py path referenced must be project-relative
    for tok in cmd.split():
        if tok.endswith(".py") and (os.path.isabs(tok) or ".." in tok or tok.startswith("/")):
            return False
    return True


def main() -> int:
    try:
        conn = sqlite3.connect(DB)
        rows = conn.execute(
            "select id, title, context from decisions where created_at >= ?", (CUTOFF,)
        ).fetchall()
        skipped = conn.execute(
            "select count(*) from decisions where created_at < ?", (CUTOFF,)
        ).fetchone()[0]
    except sqlite3.Error as exc:
        print(f"  FAIL  cannot read {DB}: {exc}")
        return 1

    print(f"  checked {len(rows)} decision(s) since {CUTOFF}, skipped {skipped} legacy  [{DB}]")
    for i, title, context in rows:
        title = title or ""
        context = context or ""
        tmatch = re.match(r"^(" + "|".join(TYPES) + r"):", title)
        if not tmatch:
            print(f"  WARN  decision {i}: missing type prefix ({'/'.join(TYPES)})")
            continue
        dtype = tmatch.group(1)
        missing = [label for label in LABELS if label not in context]
        if missing:
            print(f"  WARN  decision {i}: AI-Context block missing {', '.join(missing)}")
            continue
        miss_life = [line for line in LIFECYCLE if line not in context]
        if miss_life:
            print(f"  WARN  decision {i}: missing lifecycle line(s) {', '.join(miss_life)}")
        cmds = _commands_of(context)
        bad = [c for c in cmds if not _command_allowed(c)]
        for c in bad:
            print(f"  WARN  decision {i}: verification command not on allowlist: {c[:60]!r}")
        if dtype == "CDR" and not any(_command_allowed(c) for c in cmds):
            print(f"  WARN  decision {i}: label-only CDR - a contract decision needs >=1 allowlisted executable command")
    return 0


if __name__ == "__main__":
    sys.exit(main())
