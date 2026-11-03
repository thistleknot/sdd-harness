"""| Stage | Mechanism | Contract |
| MINE | Deterministic evidence-linked correction/error classes | [mandatory] R13 |
| PLAN | Freeze battery/checker/reader identity and reserve budgets | [mandatory] R13-R14 |
| RUN | Persist owned calls and raw receipts in resumable SQLite | [opt] --execute R13 |
| GATE | Paired A/A, activation, guards, held-out and baseline-k | [mandatory] R14-R15 |
| DECIDE | Retain rejection/acceptance evidence before promotion | [mandatory] R16 |
Spec: docs/playbooks/memory-and-harness-integration.md.
CLOSED: model calls by default, unbudgeted retries, held-out proposer leakage.
Preconditions: configured explicit model/reader for execution; default is dry.
Failures: incomplete/invalid runs are NOT TESTED; store/configuration errors raise.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import signal
import sqlite3
import subprocess
import sys
import time

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib

import checkers

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import harness_write
import adapter

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
DEFAULT_BATTERY = HERE / 'battery.toml'
DEFAULT_RESULTS = ROOT / 'eval/results/rsi'
RULES = {'unnecessary_permission': checkers.OFFER, 'banned_phrase': checkers.BANNED,
         'defect_softener': checkers.SOFTENER}


def digest(value: bytes) -> str:
    """Require: bytes; Guarantee: stable SHA-256 evaluator/evidence identity."""
    return hashlib.sha256(value).hexdigest()


def load_battery(path: Path = DEFAULT_BATTERY) -> tuple[list[dict], str]:
    """Load the fixed held-in/held-out/guard contract and evaluator identity.

    Require: 20 unique cases: target 8 train/4 held-out and 8 guards.
    Guarantee: held-out prompts have distinct normalized templates.
    Maintain: source/checker changes invalidate old comparisons.
    Assert: malformed battery fails before a model can be called.
    """
    data = tomllib.loads(path.read_text(encoding='utf-8'))
    cases = data['cases']
    if len(cases) != 20 or len({x['id'] for x in cases}) != 20:
        raise ValueError('battery requires 20 unique cases')
    expected = {('target', 'train'): 8, ('target', 'held_out'): 4, ('guard', 'train'): 8}
    for pair, count in expected.items():
        if sum((x['group'], x['split']) == pair for x in cases) != count:
            raise ValueError(f'wrong battery partition {pair}')
    prompts = [re.sub(r'\s+', ' ', x['prompt'].strip()).lower() for x in cases]
    if len(set(prompts)) != 20:
        raise ValueError('battery prompts overlap')
    for case in cases:
        checkers.check_response(case, 'configuration probe')
    evaluator = digest(path.read_bytes() + (HERE / 'checkers.py').read_bytes())
    return cases, evaluator


def checkpoint(path: Path) -> sqlite3.Connection:
    """Open resumable execution state; dry planning never calls this function.

    Require: authorized output location.
    Guarantee: each reserved/launched/completed call has a persistent receipt.
    Maintain: no duplicate automatic paid retry after interruption.
    Assert: an arm's frozen configuration cannot change on resume.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript('''
    CREATE TABLE IF NOT EXISTS arms (arm TEXT PRIMARY KEY, config TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS calls (
      arm TEXT NOT NULL, item_id TEXT NOT NULL, attempt INTEGER NOT NULL,
      state TEXT NOT NULL, pid INTEGER, receipt TEXT NOT NULL, reservation INTEGER NOT NULL,
      PRIMARY KEY(arm,item_id,attempt));
    CREATE TABLE IF NOT EXISTS decisions (candidate TEXT PRIMARY KEY, verdict TEXT NOT NULL,
      acceptance_ref TEXT NOT NULL, receipt TEXT NOT NULL);
    ''')
    return conn


def _text(content) -> str:
    """Require: provider content; Guarantee: retain textual user content without tool results."""
    if isinstance(content, str):
        return content
    return '\n'.join(x.get('text', '') for x in content if isinstance(x, dict) and x.get('type') == 'text') if isinstance(content, list) else ''


def mine(trace_root: Path, event_db: Path | None = None, excluded_sessions: set[str] | None = None,
         max_files: int = 100, max_file_bytes: int = 10000000) -> dict:
    """Mine real raw traces deterministically without model-generated clustering.

    Require: bounded input set; event DB is opened read-only.
    Guarantee: each class includes count, recency and up to three verbatim source lines.
    Maintain: evaluation sessions are excluded; identical inputs produce identical JSON.
    Assert: missing evidence yields no invented class.
    """
    excluded_sessions = excluded_sessions or set()
    classes = {name: {'name': name, 'count': 0, 'latest': '', 'examples': []} for name in RULES}
    def observe(text: str, source: str, timestamp: str):
        """Attach a raw evidence line to each matching deterministic failure class."""
        for name, regex in RULES.items():
            if regex.search(text):
                item = classes[name]
                item['count'] += 1
                item['latest'] = max(item['latest'], timestamp)
                if len(item['examples']) < 3:
                    item['examples'].append({'source': source, 'text': text[:1000], 'timestamp': timestamp})
    files = sorted(trace_root.rglob('*.jsonl'))[:max_files]
    skipped = []
    for path in files:
        if path.stat().st_size > max_file_bytes:
            skipped.append(str(path))
            continue
        previous = None
        for line_no, line in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
            if not line.strip():
                continue
            row = json.loads(line)
            if str(row.get('sessionId', row.get('session_id', ''))) in excluded_sessions:
                continue
            text = _text(row.get('message', {}).get('content', ''))
            if row.get('type') == 'assistant' and text:
                previous = (text, f'{path}:{line_no}', str(row.get('timestamp', '')))
            elif row.get('type') == 'user' and previous and re.search(r'\b(no|wrong|stop|don.t|wtf|instead|already)\b', text, re.I):
                observe(*previous)
                previous = None
    if event_db and event_db.is_file():
        conn = sqlite3.connect(event_db.resolve().as_uri() + '?mode=ro', uri=True)
        try:
            columns = {x[1] for x in conn.execute('PRAGMA table_info(events)')}
            if {'event_id', 'tool_error', 'timestamp'} <= columns:
                for eid, error, stamp in conn.execute('SELECT event_id,tool_error,timestamp FROM events WHERE tool_error IS NOT NULL ORDER BY event_id'):
                    observe(str(error), f'{event_db}#events/{eid}', str(stamp))
        finally:
            conn.close()
    ranked = sorted((x for x in classes.values() if x['count']), key=lambda x: (-x['count'], x['latest'], x['name']))
    return {'classes': ranked, 'skipped_large_files': skipped, 'files_considered': len(files)}


def _provider_receipt(stdout: str, stderr: str, returncode: int, case: dict, elapsed: float) -> dict:
    """Normalize one provider result while retaining raw stdout/stderr.

    Require: completed captured subprocess.
    Guarantee: missing usage, errors or empty/length-limited output are invalid.
    Maintain: raw evidence survives all classifications.
    Assert: valid capture and checker success are distinct fields.
    """
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError:
        payload = {}
    usage = payload.get('usage') or {}
    output = payload.get('result', payload.get('text', ''))
    if not isinstance(output, str):
        output = ''
    tokens = sum(int(usage.get(key, 0)) for key in ('input_tokens', 'output_tokens', 'cache_creation_input_tokens', 'cache_read_input_tokens'))
    valid = returncode == 0 and bool(output.strip()) and bool(usage) and not payload.get('is_error') and payload.get('stop_reason') not in {'max_tokens', 'length'}
    return {'id': case['id'], 'group': case['group'], 'split': case['split'], 'valid': valid,
            'passed': bool(valid and checkers.check_response(case, output)), 'output': output,
            'tokens': tokens, 'seconds': elapsed, 'session_id': payload.get('session_id', ''),
            'raw_stdout': stdout, 'raw_stderr': stderr, 'exit': returncode}


def run_arm(arm: str, output: Path, *, battery: Path = DEFAULT_BATTERY, execute: bool = False,
            model: str | None = None, command: list[str] | None = None, overlay: Path | None = None,
            call_budget: int = 20, token_budget: int = 500000, wall_seconds: float = 300,
            call_seconds: float = 45, input_reserve: int = 20000, max_output_tokens: int = 1024,
            samples: int = 1) -> dict:
    """Plan or execute a bounded checkpointed reader arm; default makes zero calls.

    Require: explicit execute/model, budgets and an immutable reader/configuration.
    Guarantee: reserve before launch, stop on breach, retain raw results and never retry an observed running call.
    Maintain: completed checkpoints resume without additional calls.
    Assert: reported usage exceeding reservation invalidates the arm and stops execution.
    """
    cases, evaluator = load_battery(battery)
    if not re.fullmatch(r'[A-Za-z0-9_-]+', arm) or not 0 < wall_seconds < 900 or not 0 < call_seconds <= wall_seconds:
        raise ValueError('invalid arm name or time bounds')
    if min(call_budget, token_budget, input_reserve, max_output_tokens, samples) <= 0 or samples > 20:
        raise ValueError('positive budgets and samples 1..20 are required')
    if not execute:
        return {'arm': arm, 'mode': 'dry', 'calls': 0, 'evaluator_hash': evaluator,
                'items': [{'id': x['id'], 'group': x['group'], 'split': x['split']} for x in cases]}
    if not model:
        raise ValueError('--execute requires an explicit model; no paid/default escalation exists')
    command = command or ['claude', '-p', '--model', '{model}', '--no-session-persistence', '--output-format', 'json', '{prompt}']
    if not command or not all(isinstance(x, str) for x in command) or not any('{prompt}' in x for x in command):
        raise ValueError('reader command must be an argument array containing {prompt}')
    reader = digest(json.dumps([model, command, input_reserve, max_output_tokens], sort_keys=True).encode())
    config = {'evaluator_hash': evaluator, 'reader_hash': reader, 'model': model, 'command': command,
              'overlay_hash': digest(overlay.read_bytes()) if overlay else '', 'samples': samples,
              'call_budget': call_budget, 'token_budget': token_budget, 'wall_seconds': wall_seconds,
              'call_seconds': call_seconds, 'input_reserve': input_reserve, 'max_output_tokens': max_output_tokens}
    output.mkdir(parents=True, exist_ok=True)
    conn = checkpoint(output / 'checkpoints.sqlite3')
    frozen = json.dumps(config, sort_keys=True)
    old = conn.execute('SELECT config FROM arms WHERE arm=?', (arm,)).fetchone()
    if old and old[0] != frozen:
        raise ValueError('arm configuration changed; use a distinct arm instead of reusing checkpoints')
    with conn:
        conn.execute('INSERT OR IGNORE INTO arms VALUES (?,?)', (arm, frozen))
    started = time.monotonic()
    receipts = []
    used_calls = conn.execute('SELECT COUNT(*) FROM calls WHERE arm=?', (arm,)).fetchone()[0]
    prior = conn.execute('SELECT receipt,reservation FROM calls WHERE arm=?', (arm,)).fetchall()
    used_tokens = sum(max(json.loads(x[0]).get('tokens', 0), x[1] if not json.loads(x[0]).get('valid') else 0) for x in prior)
    prior_seconds = sum(json.loads(x[0]).get('seconds', 0) for x in prior)
    exhausted = False
    for case in cases:
        attempts = []
        for attempt in range(samples):
            old_call = conn.execute('SELECT * FROM calls WHERE arm=? AND item_id=? AND attempt=?', (arm, case['id'], attempt)).fetchone()
            if old_call:
                if old_call['state'] in {'running', 'reserved'}:
                    raise RuntimeError(f'call {old_call["pid"]} lacks a terminal receipt; inspect that owned PID before resuming')
                attempts.append(json.loads(old_call['receipt']))
                continue
            reserve = input_reserve + max_output_tokens
            remaining = wall_seconds - prior_seconds - (time.monotonic() - started)
            if exhausted or used_calls >= call_budget or used_tokens + reserve > token_budget or remaining <= 0:
                attempts.append({'id': case['id'], 'group': case['group'], 'split': case['split'], 'valid': False,
                                 'passed': False, 'output': '', 'tokens': 0, 'seconds': 0, 'invalid': 'budget_exhausted'})
                exhausted = True
                continue
            values = {'prompt': case['prompt'], 'model': model, 'max_tokens': str(max_output_tokens)}
            argv = [part.replace('{prompt}', values['prompt']).replace('{model}', model).replace('{max_tokens}', values['max_tokens']) for part in command]
            if overlay:
                if Path(argv[0]).stem.lower() != 'claude':
                    raise ValueError('overlay execution currently uses the incumbent Claude settings interface only')
                argv += ['--settings', str(overlay.resolve())]
            env = {**os.environ, 'MEM_IN_EXTRACTION': '1', 'RSI_EVALUATION': '1', 'CLAUDE_CODE_MAX_OUTPUT_TOKENS': str(max_output_tokens)}
            with conn:
                conn.execute('INSERT INTO calls VALUES (?,?,?,?,?,?,?)', (arm, case['id'], attempt, 'reserved', None, '{}', reserve))
            call_start = time.monotonic()
            child = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                     text=True, encoding='utf-8', errors='replace', env=env, start_new_session=os.name != 'nt')
            with conn:
                conn.execute("UPDATE calls SET state='running',pid=? WHERE arm=? AND item_id=? AND attempt=?", (child.pid, arm, case['id'], attempt))
            timed_out = False
            try:
                stdout, stderr = child.communicate(timeout=min(call_seconds, remaining))
            except subprocess.TimeoutExpired:
                timed_out = True
                if os.name == 'nt':
                    subprocess.run(['taskkill', '/T', '/F', '/PID', str(child.pid)], capture_output=True, check=False)
                else:
                    os.killpg(child.pid, signal.SIGKILL)
                stdout, stderr = child.communicate(timeout=10)
            receipt = _provider_receipt(stdout, stderr, child.returncode, case, time.monotonic()-call_start)
            if timed_out or receipt['tokens'] > reserve:
                receipt.update(valid=False, passed=False, invalid='timeout' if timed_out else 'provider_exceeded_token_reservation')
                exhausted = True
            used_calls += 1
            used_tokens += max(receipt['tokens'], reserve if not receipt['valid'] else 0)
            with conn:
                conn.execute("UPDATE calls SET state='finished',receipt=? WHERE arm=? AND item_id=? AND attempt=?", (json.dumps(receipt), arm, case['id'], attempt))
            attempts.append(receipt)
        selected = max(attempts, key=lambda x: (x['valid'], x['passed']))
        receipts.append({**selected, 'tokens': sum(x['tokens'] for x in attempts), 'seconds': sum(x['seconds'] for x in attempts), 'attempts': attempts})
    conn.close()
    result = {**config, 'arm': arm, 'mode': 'executed', 'items': receipts, 'calls': used_calls,
              'tokens': sum(x['tokens'] for x in receipts), 'seconds': sum(x['seconds'] for x in receipts)}
    (output / f'{arm}.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    sessions = sorted({x.get('session_id') for item in receipts for x in item.get('attempts', []) if x.get('session_id')})
    (output / f'{arm}-sessions.json').write_text(json.dumps(sessions), encoding='utf-8')
    (output / f'{arm}-proposer.json').write_text(json.dumps(proposer_view(result), indent=2), encoding='utf-8')
    return result


def proposer_view(result: dict) -> list[dict]:
    """Require: raw arm result; Guarantee: only target held-in evidence enters the proposer view."""
    return [x for x in result['items'] if x['group'] == 'target' and x['split'] == 'train']


def gate(baseline: dict, repeat: dict, candidate: dict, canary: dict,
         baseline_k: dict | None = None, activation_ref: str = '', canary_token: str = 'RSI_CANARY') -> dict:
    """Compute the preregistered paired gate; missing evidence is NOT TESTED.

    Require: identical evaluator/reader, complete fixed items and external activation evidence.
    Guarantee: PASS requires headroom, noise separation, guards, held-out and matched budget.
    Maintain: no automatic acceptance or promotion.
    Assert: compared samples/evidence cannot be silently substituted.
    """
    arms = [baseline, repeat, candidate, canary] + ([baseline_k] if baseline_k else [])
    if any(a.get('mode') != 'executed' or len(a.get('items', [])) != 20 or not all(x['valid'] for x in a['items']) for a in arms):
        return {'status': 'NOT TESTED', 'reason': 'invalid or incomplete arm'}
    if len({a.get('evaluator_hash') for a in arms}) != 1 or len({a.get('reader_hash') for a in arms}) != 1:
        return {'status': 'NOT TESTED', 'reason': 'evaluator/reader identity mismatch'}
    ids = [{x['id'] for x in a['items']} for a in arms]
    if any(x != ids[0] or len(x) != 20 for x in ids):
        return {'status': 'NOT TESTED', 'reason': 'unpaired item IDs'}
    groups = {name: {x['id'] for x in baseline['items'] if predicate(x)} for name, predicate in {
        'target': lambda x: x['group']=='target' and x['split']=='train',
        'held_out': lambda x: x['split']=='held_out', 'guard': lambda x: x['group']=='guard'}.items()}
    if [len(groups[x]) for x in ('target','held_out','guard')] != [8,4,8]:
        return {'status': 'NOT TESTED', 'reason': 'invalid partitions'}
    noise = {name: checkers.flips(baseline['items'], repeat['items'], values)['flips'] for name, values in groups.items()}
    delta = {name: checkers.flips(baseline['items'], candidate['items'], values) for name, values in groups.items()}
    canary_hits = sum(canary_token in x['output'] for x in canary['items'])
    activation_path = Path(activation_ref) if activation_ref else None
    activation = json.loads(activation_path.read_text(encoding='utf-8')) if activation_path and activation_path.is_file() else {}
    if not activation or activation.get('source') != 'harness' or activation.get('firings', 0) < 1 or not set(activation.get('item_ids', [])) & groups['target'] or canary_hits < 20-sum(noise.values()) or any(canary_token in x['output'] for x in baseline['items']):
        return {'status': 'NOT TESTED', 'reason': 'activation/canary not established', 'noise': noise}
    target_failures = [sum(not x['passed'] for x in a['items'] if x['id'] in groups['target']) for a in (baseline, repeat)]
    if min(target_failures) < 5:
        return {'status': 'NOT TESTED', 'reason': 'insufficient target headroom'}
    required_k = max(1, math.ceil(candidate['tokens'] / max(baseline['tokens'], 1)))
    if required_k > 1 and (not baseline_k or baseline_k.get('samples') != required_k):
        return {'status': 'NOT TESTED', 'reason': f'matched baseline requires samples={required_k}'}
    control = baseline_k if required_k > 1 else baseline
    matched = checkers.flips(control['items'], candidate['items'], groups['target'])
    target = delta['target']
    rules = {'target_effect': ((target['fixes']>=5 and target['breaks']==0) or (target['fixes']>=7 and target['breaks']<=1)) and target['net']>noise['target'],
             'guard': delta['guard']['breaks']<=noise['guard'],
             'held_out': delta['held_out']['net']>=0 and delta['held_out']['breaks']<=noise['held_out'],
             'matched_budget': matched['net']>noise['target']}
    return {'status': 'PASS' if all(rules.values()) else 'REJECT', 'rules': rules, 'noise': noise,
            'delta': delta, 'matched': matched, 'baseline_k': required_k, 'activation_ref': activation_ref,
            'token_delta': candidate['tokens']-baseline['tokens'], 'seconds_delta': candidate['seconds']-baseline['seconds'],
            'evaluator_hash': candidate['evaluator_hash'], 'reader_hash': candidate['reader_hash'],
            'next_state': 'awaiting_acceptance' if all(rules.values()) else 'rejected'}


def record_decision(output: Path, candidate: str, verdict: dict, *, acceptance_ref: str = '',
                    contract: dict | None = None) -> dict:
    """Retain rejection/acceptance and predicted-versus-observed evidence.

    Require: named candidate, a bounded single-component contract and gate result.
    Guarantee: reject history survives; acceptance is separate from PASS.
    Maintain: at most three candidates and one added skill per candidate.
    Assert: no live files are modified by recording a decision.
    """
    contract = contract or {}
    required = {'component','failure_class','mechanism','predicted_fixes','predicted_breaks','invariants','falsifier','rollback'}
    if not required <= contract.keys() or len(contract.get('added_skills', [])) > 1:
        raise ValueError('complete single-component candidate contract required; at most one added skill')
    if acceptance_ref and verdict['status'] != 'PASS':
        raise ValueError('only a passing gate can be accepted')
    conn = checkpoint(output / 'checkpoints.sqlite3')
    known = {r[0] for r in conn.execute('SELECT candidate FROM decisions')}
    if candidate not in known and len(known) >= 3:
        raise ValueError('round candidate limit reached')
    previous = conn.execute('SELECT verdict,receipt FROM decisions WHERE candidate=?', (candidate,)).fetchone()
    if previous and previous[0] == 'REJECT':
        raise ValueError('candidate is CLOSED/rejected; new evidence requires a distinct contract')
    if previous and json.loads(previous[1])['contract'] != contract:
        raise ValueError('a candidate contract is immutable once recorded')
    receipt = {'candidate': candidate, 'contract': contract, 'gate': verdict,
               'acceptance_ref': acceptance_ref, 'state': 'accepted' if acceptance_ref else verdict.get('next_state', verdict['status'])}
    with conn:
        conn.execute('INSERT OR REPLACE INTO decisions VALUES (?,?,?,?)', (candidate, verdict['status'], acceptance_ref, json.dumps(receipt)))
    conn.close()
    with (output / ('rejects.jsonl' if verdict['status']=='REJECT' else 'history.jsonl')).open('a', encoding='utf-8') as stream:
        stream.write(json.dumps(receipt, sort_keys=True)+'\n')
    return receipt


def promote(output: Path, candidate: str, *, apply: bool = False) -> dict:
    """Plan/apply an accepted single-component candidate and export through the adapter.

    Require: passing recorded gate, separate acceptance reference and hashed staged artifacts.
    Guarantee: unaccepted changes cannot reach live hooks/skills; every replacement is backed up.
    Maintain: only canonical hooks/registry or one selected skill are eligible.
    Assert: changed staged bytes or evaluator drift invalidate promotion.
    """
    conn = checkpoint(output / 'checkpoints.sqlite3')
    row = conn.execute('SELECT receipt FROM decisions WHERE candidate=?', (candidate,)).fetchone()
    conn.close()
    if not row:
        raise ValueError('candidate decision is missing')
    receipt = json.loads(row[0])
    if receipt['gate']['status'] != 'PASS' or not receipt['acceptance_ref']:
        raise ValueError('promotion requires PASS and separate acceptance evidence')
    if receipt['gate'].get('evaluator_hash') != load_battery()[1]:
        raise ValueError('evaluator changed after acceptance; promotion is invalid')
    contract = receipt['contract']
    artifacts = contract.get('artifacts', [])
    if not artifacts:
        raise ValueError('candidate contract has no staged artifacts')
    skills = set()
    planned = []
    for artifact in artifacts:
        source, destination = Path(artifact['source']).resolve(), Path(artifact['destination']).resolve()
        if not source.is_relative_to(output.resolve()):
            raise ValueError('candidate source must be staged within this round')
        content = source.read_bytes()
        if digest(content) != artifact['sha256']:
            raise ValueError('staged artifact no longer matches its contract')
        master = Path.home() / '.skills'
        if destination.is_relative_to(master.resolve()):
            name = destination.relative_to(master.resolve()).parts[0]
            skills.add(name)
        elif not (destination.is_relative_to((ROOT/'hooks').resolve()) or destination == (ROOT/'harness.json').resolve()):
            raise ValueError('promotion destination is outside hooks, registry or canonical skills')
        planned.append((destination, content))
    if len(skills) > 1 or (skills and any(not dest.is_relative_to((Path.home()/'.skills').resolve()) for dest, _ in planned)):
        raise ValueError('candidate must edit one hook component or one skill package')
    result = {'candidate': candidate, 'state': 'planned', 'paths': [str(x[0]) for x in planned],
              'acceptance_ref': receipt['acceptance_ref']}
    if apply:
        for destination, content in planned:
            harness_write.write_bytes(destination, content, adapter.BACKUP_RUN)
        config = adapter.load_harness()
        if skills:
            if adapter.sync_skills(config, sorted(skills), apply=True):
                raise RuntimeError('skill export has unresolved drift; candidate remains unpromoted')
        else:
            for sync in adapter.TARGETS.values():
                sync(config)
        result['state'] = 'promoted'
        with (output/'history.jsonl').open('a', encoding='utf-8') as stream:
            stream.write(json.dumps(result, sort_keys=True)+'\n')
    return result


def main(argv: list[str] | None = None) -> int:
    """Expose bounded offline-first mining/execution/gating interfaces.

    Require: explicit subcommand; execute is never implied by run.
    Guarantee: default run prints its plan and makes zero model calls.
    Maintain: no OpenCode command or automatic promotion is launched.
    Assert: errors have nonzero exits rather than success-shaped fallback output.
    """
    parser = argparse.ArgumentParser(description='Offline-first harness improvement runner')
    sub = parser.add_subparsers(dest='action', required=True)
    mining = sub.add_parser('mine')
    mining.add_argument('--traces', type=Path, required=True)
    mining.add_argument('--events', type=Path)
    mining.add_argument('--output', type=Path, required=True)
    mining.add_argument('--exclude-sessions', type=Path)
    running = sub.add_parser('run')
    running.add_argument('--arm', required=True)
    running.add_argument('--output', type=Path, default=DEFAULT_RESULTS/'round-01')
    running.add_argument('--battery', type=Path, default=DEFAULT_BATTERY)
    mode = running.add_mutually_exclusive_group()
    mode.add_argument('--execute', action='store_true')
    mode.add_argument('--dry', action='store_true')
    running.add_argument('--model')
    running.add_argument('--command', help='JSON argv array; no shell interpolation')
    running.add_argument('--overlay', type=Path)
    running.add_argument('--call-budget', type=int, default=20)
    running.add_argument('--token-budget', type=int, default=500000)
    running.add_argument('--wall-seconds', type=float, default=300)
    running.add_argument('--call-seconds', type=float, default=45)
    running.add_argument('--samples', type=int, default=1)
    verdict_parser = sub.add_parser('verdict')
    for arm in ('baseline','repeat','candidate','canary'):
        verdict_parser.add_argument('--'+arm, type=Path, required=True)
    verdict_parser.add_argument('--baseline-k', type=Path)
    verdict_parser.add_argument('--activation-ref', required=True)
    verdict_parser.add_argument('--output', type=Path, required=True)
    decide = sub.add_parser('decide')
    decide.add_argument('--output', type=Path, required=True)
    decide.add_argument('--candidate', required=True)
    decide.add_argument('--verdict', type=Path, required=True)
    decide.add_argument('--contract', type=Path, required=True)
    decide.add_argument('--acceptance-ref', default='')
    promoting = sub.add_parser('promote')
    promoting.add_argument('--output', type=Path, required=True)
    promoting.add_argument('--candidate', required=True)
    promoting.add_argument('--apply', action='store_true')
    args = parser.parse_args(argv)
    if args.action == 'mine':
        exclusions = set(json.loads(args.exclude_sessions.read_text())) if args.exclude_sessions else set()
        result = mine(args.traces, args.events, exclusions)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2, sort_keys=True), encoding='utf-8')
    elif args.action == 'run':
        result = run_arm(args.arm, args.output, battery=args.battery, execute=args.execute, model=args.model,
            command=json.loads(args.command) if args.command else None, overlay=args.overlay,
            call_budget=args.call_budget, token_budget=args.token_budget, wall_seconds=args.wall_seconds,
            call_seconds=args.call_seconds, samples=args.samples)
    elif args.action == 'verdict':
        arms = [json.loads(getattr(args, name).read_text()) for name in ('baseline','repeat','candidate','canary')]
        result = gate(*arms, baseline_k=json.loads(args.baseline_k.read_text()) if args.baseline_k else None, activation_ref=args.activation_ref)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2), encoding='utf-8')
    elif args.action == 'decide':
        result = record_decision(args.output, args.candidate, json.loads(args.verdict.read_text()),
                                 acceptance_ref=args.acceptance_ref, contract=json.loads(args.contract.read_text()))
    else:
        result = promote(args.output, args.candidate, apply=args.apply)
    print(json.dumps({k:v for k,v in result.items() if k not in {'items','command','classes'}}, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
