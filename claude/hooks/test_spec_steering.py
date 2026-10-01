#!/usr/bin/env python3
"""Battery for steering loading and inclusion modes.

The rule under test is "what actually reaches the model". Half the cases are
false-positive probes: injecting an empty stub every turn, or injecting a
fileMatch doc on every unrelated file, would train the model to skip the
steering block -- which is a slower, quieter version of not having steering.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from spec_paths import (  # noqa: E402
    load_steering, parse_frontmatter, render_steering, steering_matches_path,
)
from spec_state import steering_context  # noqa: E402

FILLED = "Real content that should reach the model."


def tree(**files: str) -> str:
    """A .spec tree whose steering/ holds the given name -> raw text files."""
    root = tempfile.mkdtemp(prefix="steer-")
    os.makedirs(os.path.join(root, ".spec", "steering"), exist_ok=True)
    os.makedirs(os.path.join(root, ".spec", "specs"), exist_ok=True)
    for name, text in files.items():
        with open(os.path.join(root, ".spec", "steering", name.replace("__", ".")),
                  "w", encoding="utf-8") as fh:
            fh.write(text)
    return root


def doc(inclusion: str | None = None, patterns: str | None = None, body: str = FILLED) -> str:
    fm = ""
    if inclusion:
        fm = "---\ninclusion: " + inclusion
        if patterns:
            fm += f"\nfileMatchPattern: {patterns}"
        fm += "\n---\n\n"
    return fm + "# Doc\n\n" + body


CHECKS: list[tuple[str, bool]] = []


def check(name: str, got, want) -> None:
    ok = got == want
    CHECKS.append((name, ok))
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + ("" if ok else f"   <-- got {got!r}, want {want!r}"))


def main() -> int:
    # ---- front matter parsing -------------------------------------------
    meta, body = parse_frontmatter("---\ninclusion: fileMatch\nfileMatchPattern: [\"*.ts\", \"*.tsx\"]\n---\n\nBody here")
    check("frontmatter: inclusion parsed", meta.get("inclusion"), "fileMatch")
    check("frontmatter: inline list parsed", meta.get("fileMatchPattern"), ["*.ts", "*.tsx"])
    check("frontmatter: body separated", body.strip(), "Body here")
    check("frontmatter: absent is tolerated", parse_frontmatter("# Just markdown")[0], {})
    check("frontmatter: unterminated block is not eaten",
          parse_frontmatter("---\ninclusion: always\n# no close")[0], {})

    # ---- defaults and mode resolution ------------------------------------
    r = tree(product__md=doc(), tech__md=doc("always"), legacy__md=doc("nonsense-mode"))
    docs = {d["stem"]: d for d in load_steering(os.path.join(r, ".spec"))}
    check("no frontmatter defaults to always", docs["product"]["inclusion"], "always")
    check("explicit always honored", docs["tech"]["inclusion"], "always")
    check("unknown mode falls back to always", docs["legacy"]["inclusion"], "always")

    # `product` and `tech` both resolve to always, but only `tech` chose it.
    # The resolved mode alone cannot tell them apart, so the warning in
    # `status` depends entirely on these flags. Assert them directly.
    check("undeclared doc is marked undeclared", docs["product"]["declared"], False)
    check("explicit always is marked declared", docs["tech"]["declared"], True)
    check("declared doc carries no unknown_mode", docs["tech"]["unknown_mode"], None)
    check("undeclared doc carries no unknown_mode", docs["product"]["unknown_mode"], None)
    check("unknown mode is declared but recorded",
          (docs["legacy"]["declared"], docs["legacy"]["unknown_mode"]),
          (True, "nonsense-mode"))
    check("load order is deterministic (alphabetical)",
          [d["stem"] for d in load_steering(os.path.join(r, ".spec"))],
          ["legacy", "product", "tech"])
    shutil.rmtree(r, ignore_errors=True)

    # ---- empty stubs must NOT be injected --------------------------------
    r = tree(product__md="---\ninclusion: always\n---\n\n# Product\n\n<!-- Fill this in. -->\n",
             tech__md=doc("always"))
    ctx = steering_context(r, "")
    check("empty stub is not injected", "Product" in (ctx or ""), False)
    check("filled doc IS injected", FILLED in (ctx or ""), True)
    shutil.rmtree(r, ignore_errors=True)

    # ---- manual mode ------------------------------------------------------
    r = tree(runbook__md=doc("manual"), product__md=doc("always"))
    # Probe the `### <stem>` header render_steering emits, never the shared body
    # text: an earlier version checked for "Doc", which both fixtures contained,
    # so the always-doc satisfied the assertion about the manual one.
    check("manual doc absent without reference",
          "### runbook" in (steering_context(r, "do a thing") or ""), False)
    check("always doc present regardless",
          "### product" in (steering_context(r, "do a thing") or ""), True)
    check("manual doc injected when named",
          "### runbook" in (steering_context(r, "check #runbook please") or ""), True)
    check("unrelated hash does not pull it in",
          "### runbook" in (steering_context(r, "issue #42 is open") or ""), False)
    shutil.rmtree(r, ignore_errors=True)

    # ---- fileMatch mode ---------------------------------------------------
    r = tree(api__md=doc("fileMatch", '["src/api/**/*.py"]'), product__md=doc("always"))
    d_api = [d for d in load_steering(os.path.join(r, ".spec")) if d["stem"] == "api"][0]
    check("fileMatch never rides UserPromptSubmit",
          "### api" in (steering_context(r, "edit the api") or ""), False)
    check("fileMatch matches a covered path",
          steering_matches_path(d_api, "/repo/src/api/users.py"), True)
    check("fileMatch rejects an uncovered path",
          steering_matches_path(d_api, "/repo/src/ui/button.tsx"), False)
    check("fileMatch rejects a near-miss directory",
          steering_matches_path(d_api, "/repo/src/apiary/x.py"), False)
    check("always doc never matches by path",
          steering_matches_path([d for d in load_steering(os.path.join(r, ".spec"))
                                 if d["stem"] == "product"][0], "/repo/src/api/users.py"), False)
    shutil.rmtree(r, ignore_errors=True)

    # ---- budget -----------------------------------------------------------
    big = [{"stem": f"d{i}", "body": "x" * 3000, "empty": False} for i in range(5)]
    out = render_steering(big, budget=8000)
    check("budget truncates rather than blowing context", len(out) < 9000, True)
    check("truncation is reported, not silent", "truncated" in out, True)

    # ---- unarmed repo -----------------------------------------------------
    bare = tempfile.mkdtemp(prefix="bare-")
    check("unarmed repo yields no steering", steering_context(bare, "hello"), None)
    shutil.rmtree(bare, ignore_errors=True)

    # ---- end to end through the actual hook -------------------------------
    r = tree(product__md=doc("always"), api__md=doc("fileMatch", '["src/api/*.py"]'))
    subprocess.run([sys.executable, os.path.join(HERE, "spec_state.py"), "new", "demo"],
                   cwd=r, capture_output=True, text=True)

    p = subprocess.run([sys.executable, os.path.join(HERE, "spec_state.py")], cwd=r,
                       input=json.dumps({"hook_event_name": "UserPromptSubmit", "cwd": r, "prompt": "hi"}),
                       capture_output=True, text=True)
    ups = json.loads(p.stdout)["hookSpecificOutput"]["additionalContext"]
    check("hook: UserPromptSubmit carries phase line", "Spec state:" in ups, True)
    check("hook: UserPromptSubmit carries always steering", "### product" in ups, True)
    check("hook: UserPromptSubmit omits fileMatch steering", "### api" in ups, False)

    p = subprocess.run([sys.executable, os.path.join(HERE, "spec_state.py")], cwd=r,
                       input=json.dumps({"hook_event_name": "PostToolUse", "cwd": r,
                                         "tool_input": {"file_path": os.path.join(r, "src/api/users.py")}}),
                       capture_output=True, text=True)
    pt = json.loads(p.stdout)["hookSpecificOutput"]["additionalContext"]
    check("hook: PostToolUse injects matching fileMatch doc", "### api" in pt, True)
    check("hook: PostToolUse does not re-inject always docs", "### product" in pt, False)

    p = subprocess.run([sys.executable, os.path.join(HERE, "spec_state.py")], cwd=r,
                       input=json.dumps({"hook_event_name": "PostToolUse", "cwd": r,
                                         "tool_input": {"file_path": os.path.join(r, "README.md")}}),
                       capture_output=True, text=True)
    check("hook: PostToolUse silent on non-matching file", p.stdout.strip(), "")
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
