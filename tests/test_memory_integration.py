"""Acceptance battery for scoped evidence memory; no embedding/model calls."""
import asyncio
import importlib.util
import io
import json
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest

MEMORY = Path.home() / '.skills/memory-index'
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(MEMORY))
sys.path.insert(0, str(ROOT / 'hooks'))
import conversation_store as cs
import mem_server as server
import session_handoff
import session_resume
import codebase_map


def tool(name):
    """Return FastMCP's actual registered function across decorator versions."""
    value = getattr(server, name)
    return getattr(value, 'fn', value)


@pytest.fixture
def memory(tmp_path, monkeypatch):
    """Use real SQLite and three distinct projects with equal display names."""
    projects = []
    for parent in ('north', 'south', 'west'):
        project = tmp_path / parent / 'shared-name'
        project.mkdir(parents=True)
        projects.append(project)
    conn = cs.connect(tmp_path / 'memory/conversations.sqlite3')
    monkeypatch.setattr(server, '_conv_conn', conn)
    monkeypatch.setattr(server, 'MEM_DIR', tmp_path / 'memory')
    def forbidden(*args, **kwargs):
        """Fail if a lexical operation attempts to use a model backend."""
        raise AssertionError('no embedding/model calls allowed')
    monkeypatch.setattr(server, 'embed', forbidden)
    yield conn, projects
    conn.close()


def add(conn, project, name='orchard', **kwargs):
    """Write a raw-backed fixture with explicit source metadata."""
    return cs.write_record(conn, name, 'orchard calibration needs twelve reference samples',
        workspace_root=str(project), source_ref='trace:operator/17', epistemic='observed', **kwargs)


@pytest.mark.parametrize('current', [0, 1, 2])
def test_project_shared_session_and_source_authorization(memory, current):
    """Foreign project/session IDs cannot be opened even when their IDs are known."""
    conn, projects = memory
    mids = [add(conn, p) for p in projects]
    shared = cs.write_record(conn, 'shared preference', 'orchard reports use SI units', scope='shared', source_ref='user:units')
    session = add(conn, projects[current], 'work', session_id='alpha', memory_function='working')
    hits = cs.search_records(conn, 'orchard', workspace_root=str(projects[current]), session_id='alpha')
    assert {x['memory_id'] for x in hits} == {mids[current], shared, session}
    hits = cs.search_records(conn, 'orchard', workspace_root=str(projects[current]), session_id='beta')
    assert {x['memory_id'] for x in hits} == {mids[current], shared}
    assert cs.open_record(conn, mids[(current+1)%3], workspace_root=str(projects[current])) is None
    assert cs.open_record(conn, session, workspace_root=str(projects[current]), session_id='beta') is None


def test_reads_revisions_feedback_retirement_and_redaction(memory):
    """Reading is not utility evidence; revision and retirement retain immutable sources."""
    conn, projects = memory
    mid = add(conn, projects[0])
    before = conn.total_changes
    for _ in range(4):
        assert cs.search_records(conn, 'calibration', workspace_root=str(projects[0]))
        assert cs.open_record(conn, mid, workspace_root=str(projects[0]))
    assert conn.total_changes == before
    raw = conn.execute('SELECT content FROM volleys').fetchall()
    updated = cs.write_record(conn, 'orchard', 'calibration password=veryprivate ' + 'x'*6100,
        workspace_root=str(projects[0]), session_id='later', memory_id=mid, source_ref='trace:fix/18')
    assert updated == mid
    opened = cs.open_record(conn, mid, workspace_root=str(projects[0]))
    assert len(opened['body']) == 6000 and 'veryprivate' not in opened['body']
    assert conn.execute('SELECT content FROM volleys ORDER BY rowid LIMIT 1').fetchone()[0] == raw[0][0]
    args = dict(workspace_root=str(projects[0]))
    assert cs.record_feedback(conn, mid, 'eval:1', 'helpful', 'receipt:1', **args)['helpful'] == 1
    assert cs.record_feedback(conn, mid, 'eval:1', 'helpful', 'receipt:1', **args)['helpful'] == 1
    with pytest.raises(ValueError):
        cs.record_feedback(conn, mid, 'eval:1', 'harmful', 'receipt:2', **args)
    count = cs.volley_count(conn)
    cs.retire_record(conn, mid, 'obsolete:2', **args)
    assert cs.open_record(conn, mid, **args) is None
    assert cs.volley_count(conn) == count
    assert conn.execute('SELECT COUNT(*) FROM memory_revisions WHERE memory_id=?', (mid,)).fetchone()[0] == 3


@pytest.mark.parametrize('arguments', [{}, {'scope':'session'}, {'scope':'nonsense'}])
def test_missing_or_invalid_context_cannot_fall_back_global(memory, arguments):
    """Invalid scope/context fails rather than exposing shared task state."""
    with pytest.raises(ValueError):
        cs.search_records(memory[0], 'anything', **arguments)


def test_legacy_import_is_idempotent_and_unknown_is_audit_only(memory):
    """Legacy global defaults are not interpreted as permission to share task state."""
    conn, projects = memory
    folder = server.MEM_DIR
    folder.mkdir(exist_ok=True)
    fixtures = {'unknown.md':'---\nname: unknown\nmetadata:\n  scope: global\n---\norchard old task',
        'shared.md':'---\nname: reusable\nmetadata:\n  scope: shared\n---\norchard reusable lesson',
        'plain.md':'orchard unattributed source',
        'malformed.md':'---\nname: malformed\ndescription: value: with colon\n---\norchard malformed metadata',
        'invalid-scope.md':'---\nname: invalid\nmetadata:\n  scope: user\n---\norchard unsupported metadata scope',
        'user.md':'---\nname: preference\ntype: user\nmetadata:\n  scope: user\n---\norchard reusable user preference'}
    for name, text in fixtures.items():
        (folder/name).write_text(text, encoding='utf-8')
    tool('index_memory')()
    before = conn.total_changes
    tool('index_memory')()
    assert conn.total_changes == before
    assert len(cs.search_records(conn, 'orchard', workspace_root=str(projects[0]))) == 2
    assert conn.execute("SELECT COUNT(*) FROM memory_records WHERE scope='shared' AND type='user'").fetchone()[0] == 1
    assert len(json.loads(tool('audit_memory')())) == 4
    assert 'metadata_errors=2' in tool('index_memory')()
    assert {p.name:p.read_text(encoding='utf-8') for p in folder.glob('*.md')} == fixtures


def test_large_legacy_markdown_imports_as_stable_source_offset_chunks(memory, tmp_path, monkeypatch):
    """Require: a source exceeds the record cap; Guarantee: every character survives stable chunks."""
    conn, _ = memory
    source_root = tmp_path / 'legacy'
    source_root.mkdir()
    original = ('tree-ring evidence ' * 7000) + 'final marker'
    (source_root / 'large.md').write_text(original, encoding='utf-8')
    handoffs = source_root / 'handoffs'
    handoffs.mkdir()
    (handoffs / 'stale.md').write_text('generated task continuation', encoding='utf-8')
    monkeypatch.setattr(server, 'MEM_DIR', source_root)

    imported = tool('index_memory')()
    rows = conn.execute("SELECT memory_id,raw_id,body,source_ref FROM memory_records").fetchall()
    rows = sorted(rows, key=lambda row: int(row['source_ref'].split('#chars=')[1].split(':')[0]))
    assert f'{len(rows)} records from 1 markdown sources' in imported
    assert len(rows) == 3
    raw_chunks = [conn.execute('SELECT content FROM volleys WHERE volley_id=?', (row['raw_id'],)).fetchone()[0] for row in rows]
    assert ''.join(raw_chunks) == original
    assert all(len(row['body']) <= 60000 for row in rows)
    assert [row['source_ref'].split('#chars=')[1] for row in rows] == [
        f'{start}:{min(start + 60000, len(original))}' for start in range(0, len(original), 60000)
    ]

    tool('index_memory')()
    assert conn.execute('SELECT COUNT(*) FROM memory_records').fetchone()[0] == 3
    assert conn.execute('SELECT COUNT(*) FROM volleys').fetchone()[0] == 3


def test_mcp_contract_and_catalog_without_inference(memory):
    """Real registered MCP tools can write/search/open evidence without a model backend."""
    _, projects = memory
    answer = tool('add_memory')('measured', 'reference', 'sensor record', 'measured sensor offset 17',
        workspace_root=str(projects[0]), source_ref='instrument:17', epistemic='observed')
    mid = answer.split()[-1]
    search = tool('search_memory')('sensor', workspace_root=str(projects[0]))
    assert mid in search and 'source=instrument:17' in search
    assert 'measured sensor offset 17' in tool('open_memory')(mid, workspace_root=str(projects[0]))
    assert json.loads(tool('memory_feedback')(mid,'run:17','helpful','measurement:17',workspace_root=str(projects[0])))['promotion_allowed'] is False
    health = asyncio.run(server.health(None))
    assert json.loads(health.body)['store'] == str(server.MEM_DIR/'conversations.sqlite3')
    names = asyncio.run(server.mcp.get_tools())
    assert {'search_memory','log_memory','add_memory','index_memory','append_volley','get_hot_window',
            'get_project_history','anneal_memory','memory_stats','open_memory','update_memory','retire_memory','memory_feedback','audit_memory'} <= names.keys()


def test_continuity_never_resumes_global_or_same_basename_foreign_handoff(memory, monkeypatch):
    """Three same-name workspaces each resume their own generated archive only."""
    _, projects = memory
    monkeypatch.setattr(session_handoff, 'HANDOFF_DIR', server.MEM_DIR/'handoffs')
    monkeypatch.setattr(session_resume, 'MEMORY_DIR', server.MEM_DIR)
    global_file = server.MEM_DIR/'handoffs/prompt-global.md'
    global_file.parent.mkdir(parents=True)
    global_file.write_text('foreign active task')
    assert session_resume.find_prompt_md(str(projects[0])) is None
    for i, project in enumerate(projects):
        path = session_handoff.resolve_output_path(str(project), 'handoff')
        path.write_text(f'Project-URI: {cs.project_identity(str(project))}\nproject {i}', encoding='utf-8')
    for i, project in enumerate(projects):
        chosen = session_resume.find_prompt_md(str(project))
        assert chosen and chosen.read_text().endswith(f'project {i}')


def test_caller_contracts_name_search_open_and_feedback():
    """Every caller contract names workspace_root, open_memory and memory_feedback.

    Spec: .harness/docs/playbooks/memory-and-harness-integration.md R19
    Covers the OpenCode plugin, Pi extension, Kiro steering and memory server instructions.
    """
    texts = {
        'opencode': (ROOT / 'plugin/.opencode/plugins/sdd-harness.js').read_text(encoding='utf-8'),
        'pi': (ROOT / 'plugin/.pi/extensions/sdd-harness.ts').read_text(encoding='utf-8'),
        'kiro': (ROOT / 'plugin/install.py').read_text(encoding='utf-8'),
        'server': (Path.home() / '.mcp/memory-index/mem_server.py').read_text(encoding='utf-8'),
    }
    for name, text in texts.items():
        for term in ('workspace_root', 'open_memory', 'memory_feedback'):
            assert term in text, f'{name} contract omits {term}'


@pytest.mark.parametrize('payload', [{}, {'session_id':''}, {'session_id':'real-session'}])
def test_empty_code_map_id_fails_open(memory, monkeypatch, payload):
    """Missing IDs do not construct invalid markers; normal IDs retain behavior."""
    _, projects = memory
    monkeypatch.setattr(sys, 'stdin', io.StringIO(json.dumps(payload)))
    monkeypatch.setattr(codebase_map, 'SESSION_MARKER', projects[0]/'marker')
    monkeypatch.setattr(codebase_map, 'disabled', lambda: False)
    monkeypatch.setattr(codebase_map, 'generate_map', lambda root: 'bounded map')
    assert codebase_map.main() in (0, None)


def test_git_worktree_identity_is_common_but_equal_repo_names_are_not(tmp_path):
    """Use an actual tiny Git repository to distinguish workspace and project identity."""
    repo = tmp_path/'main'
    repo.mkdir()
    subprocess.run(['git','init',str(repo)],check=True,capture_output=True)
    subprocess.run(['git','-C',str(repo),'-c','user.name=Fixture','-c','user.email=fixture@example.invalid','commit','--allow-empty','-m','fixture'],check=True,capture_output=True)
    worktree = tmp_path/'branch'
    subprocess.run(['git','-C',str(repo),'worktree','add','-b','fixture-branch',str(worktree)],check=True,capture_output=True)
    assert cs.project_identity(str(repo)) == cs.project_identity(str(worktree))
