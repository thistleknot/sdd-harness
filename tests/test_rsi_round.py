"""| Stage | Mechanism | Contract |
| VERIFY | Exercise the offline battery and fail-closed paired gate | [mandatory] R13-R15 |

Spec: docs/playbooks/memory-and-harness-integration.md.
CLOSED: live-model tests in this suite; execution requires explicit operator opt-in.
Preconditions: local Python and repository source tree.
Failures: invalid battery or incomplete evidence is surfaced as a test failure.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'eval' / 'rsi'))
import round as runner


def test_dry_run_loads_battery_without_creating_checkpoint(tmp_path, monkeypatch):
    """Require: no execution opt-in; Guarantee: 20 planned items and no provider process."""
    monkeypatch.setattr(runner.subprocess, 'Popen', lambda *a, **k: (_ for _ in ()).throw(AssertionError('provider launched')))
    out = tmp_path / 'dry-run'
    result = runner.run_arm('plancheck', out)
    assert result['mode'] == 'dry'
    assert len(result['items']) == 20
    assert not out.exists()


def test_gate_requires_complete_activation_and_paired_evidence(tmp_path):
    """Require: fixed matching 20-case evidence; Guarantee: absent activation is NOT TESTED."""
    cases, evaluator = runner.load_battery()

    def arm(name, passed_ids=(), token=100):
        items = [{**case, 'valid': True, 'passed': case['id'] in passed_ids,
                  'output': 'RSI_CANARY' if name == 'canary' else 'observed output'} for case in cases]
        return {'arm': name, 'mode': 'executed', 'items': items, 'evaluator_hash': evaluator,
                'reader_hash': 'same-reader', 'tokens': token, 'seconds': 10, 'samples': 1}

    baseline = arm('baseline')
    repeat = arm('repeat')
    candidate = arm('candidate', {x['id'] for x in [case for case in cases if case['group'] == 'target' and case['split'] == 'train'][:5]})
    canary = arm('canary')
    result = runner.gate(baseline, repeat, candidate, canary)
    assert result['status'] == 'NOT TESTED'
    assert 'activation' in result['reason']

    target_ids = [x['id'] for x in cases if x['group'] == 'target' and x['split'] == 'train']
    activation = tmp_path / 'activation.json'
    activation.write_text(json.dumps({'source': 'harness', 'firings': 1, 'item_ids': target_ids[:1]}))
    result = runner.gate(baseline, repeat, candidate, canary, activation_ref=str(activation))
    assert result['status'] == 'PASS'
    assert result['next_state'] == 'awaiting_acceptance'
