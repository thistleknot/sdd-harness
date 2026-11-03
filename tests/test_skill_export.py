"""| Stage | Mechanism | Contract |
| CHECK | Validate selected native skill projections and router registrations without writes | [mandatory] R10-R12, R23-R28 |

Spec: docs/playbooks/memory-and-harness-integration.md R10-R12, R23-R28.
CLOSED: treating a matching URL as usable when the native client disables it.
Preconditions: isolated native config fixture.
Failures: stale, missing or disabled registrations are reported by target.
"""
import json
from pathlib import Path

import adapter


def test_codex_projection_copies_skills_and_keeps_router_transport(tmp_path, monkeypatch):
    """Require: Codex is both a file-copy and MCP client; Guarantee: native location is explicit."""
    monkeypatch.setattr(adapter.Path, 'home', classmethod(lambda cls: tmp_path))

    projection = adapter.skill_projection_contract('codex')

    assert projection == {
        'strategy': 'GENERATE',
        'transport': 'copy+mcp',
        'target': str(tmp_path / '.agents' / 'skills'),
    }
    assert 'codex' in adapter.SKILL_ROUTER_TARGETS
    assert adapter.SKILL_COPY_TARGETS['codex'] == '.agents/skills'


def test_disabled_router_is_reported_even_when_url_matches(tmp_path, monkeypatch):
    """Require: URL points at canonical router; Guarantee: disabled client is drift."""
    config = tmp_path / 'client.json'
    config.write_text(json.dumps({'mcpServers': {'retrieve-skills': {
        'url': 'http://127.0.0.1:8765/mcp', 'disabled': True,
    }}}))
    monkeypatch.setattr(adapter, 'SKILL_ROUTER_TARGETS', ('claude',))
    monkeypatch.setattr(adapter, 'mcp_projection_contract', lambda _: {
        'target': str(config), 'key': 'mcpServers',
    })
    issues = adapter._skill_router_issues(
        {'mcp_servers': {'retrieve-skills': {'url': 'http://127.0.0.1:8765/mcp'}}},
        tmp_path, [], indexed=False,
    )
    assert issues == ['claude: retrieve-skills is disabled']


def test_reconciliation_reports_unsafe_package_and_continues(tmp_path, monkeypatch):
    """Require: one unsafe and one ordinary legacy package; Guarantee: safe package is still planned."""
    monkeypatch.setattr(adapter.Path, 'home', classmethod(lambda cls: tmp_path))
    legacy = tmp_path / 'Documents' / 'dev' / 'skills'
    unsafe = legacy / 'unsafe' / 'SKILL.md'
    safe = legacy / 'safe' / 'SKILL.md'
    unsafe.parent.mkdir(parents=True)
    safe.parent.mkdir(parents=True)
    unsafe.write_text('unsafe package', encoding='utf-8')
    safe.write_text('safe package', encoding='utf-8')
    monkeypatch.setattr(adapter, 'skill_package_files', lambda package: (_ for _ in ()).throw(
        ValueError('skill resource escapes package')) if package.name == 'unsafe' else [package / 'SKILL.md'])

    report = adapter.reconcile_skill_master(tmp_path / '.skills')

    assert len(report['skipped']) == 1
    assert report['skipped'][0]['source'].endswith('unsafe')
    assert [entry['source'] for entry in report['imported']] == [str(safe)]

def test_selected_router_clients_do_not_write_copy_targets(tmp_path, monkeypatch, capsys):
    """Require: canonical package and router subset; Guarantee: no unrelated copy target is planned."""
    monkeypatch.setattr(adapter.Path, 'home', classmethod(lambda cls: tmp_path))
    master = tmp_path / '.skills'
    package = master / 'demo'
    package.mkdir(parents=True)
    (package / 'SKILL.md').write_text('---\nname: demo\ndescription: demo\n---\n', encoding='utf-8')
    monkeypatch.setattr(adapter, 'validate_skill', lambda _: [])
    monkeypatch.setattr(adapter, 'skill_package_files', lambda _: [package / 'SKILL.md'])
    checked = []
    monkeypatch.setattr(adapter, '_skill_router_issues',
                        lambda config, root, names, *, indexed, targets=None: checked.extend(targets or ()) or [])

    result = adapter.sync_skills({}, ['demo'], check=True, master=master, clients=['claude', 'kiro'])
    output = capsys.readouterr().out

    assert result == 0
    assert checked == ['claude', 'kiro']
    assert not any((tmp_path / relative).exists() for relative in adapter.SKILL_COPY_TARGETS.values())
    assert 'shared index visibility is global' in output
