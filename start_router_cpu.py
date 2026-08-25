"""Start retrieve-skills server on CPU only (no GPU allocation)."""
import os
import sys
from pathlib import Path

os.environ["CUDA_VISIBLE_DEVICES"] = ""
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"

_env_src = os.environ.get("RETRIEVE_SKILLS_SRC")
_store = Path(os.environ.get("SKILL_STORE") or Path.home() / ".skills")
_candidates = [
    Path(_env_src) if _env_src else None,
    # This entrypoint has always loaded the .claude copy; the two installs have
    # divergent code and separate index.db files, so the order is deliberate.
    Path.home() / ".claude" / "skills" / "retrieve-skills",
    _store / "retrieve-skills",
]
_found = next((c for c in _candidates if c and (c / "server.py").exists()), None)
if _found is None:
    sys.exit(
        "retrieve-skills server.py not found. Looked in:\n  "
        + "\n  ".join(str(c) for c in _candidates if c)
        + "\nSet RETRIEVE_SKILLS_SRC to override."
    )

server_dir = str(_found)
os.chdir(server_dir)
sys.path.insert(0, server_dir)

exec(open(os.path.join(server_dir, "server.py")).read())
