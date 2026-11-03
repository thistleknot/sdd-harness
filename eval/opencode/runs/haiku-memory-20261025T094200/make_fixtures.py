"""Create synthetic private memory fixtures for the OpenCode 2B smoke test (plan gate 3).

Spec: none found (scratch driver for plan gate 3; not production source).
Writes only to a unique TEMP fixture directory. Copies no user memories.
"""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, 'C:/Users/user/.mcp/memory-index')
import conversation_store as cs  # noqa: E402

fixture_dir = Path(tempfile.mkdtemp(prefix='haiku-memfix-'))
ws_a = fixture_dir / 'alpha' / 'fixture-ws'
ws_b = fixture_dir / 'beta' / 'fixture-ws'
ws_a.mkdir(parents=True)
ws_b.mkdir(parents=True)
conn = cs.connect(fixture_dir / 'conversations.sqlite3')
print(json.dumps({'fixture_dir': str(fixture_dir), 'ws_a': str(ws_a), 'ws_b': str(ws_b)}))
