"""| Stage | Mechanism | Contract |
| CONFIGURE | Select model, agent, thinking mode, purity and arm overlay | [mandatory] R1,R3-R5,R8-R12 |
| CAPTURE | Close stdin and split native output streams | [mandatory] R1,R7 |
| BOUND | Terminate only the captured tree at deadline | [mandatory] R2 |
| CHECK | Persist separated checker output and validity | [mandatory] R6 |

R1-R12: capture.spec.md governs this instrument; checker.spec.md owns text scoring.
CLOSED: inherited stdin and PowerShell combined streams, RC-24 and RC-10.
Preconditions: installed native OpenCode binary; private memory endpoint for arm B.
Failure modes: malformed JSON raises after native evidence is saved; invalid runs exit 2.
"""

import argparse
import json
import os
import subprocess
import time
from pathlib import Path

from checker import check_events

PROMPTS = (
    'Write a Python function median(xs) that returns the median of a list of numbers. Output only the code.',
    'Explain in two sentences what a binary search does.',
    'What is the current task you are working on? If you do not know, say you do not know.',
)
PROBE_TITLE = 'OpenCode probe'


def main() -> None:
    """Capture one run for Codex to independently inspect and verify.

    Require: a unique output directory and the specified arm's dependencies.
    Guarantee: retain native streams, command, PID, exit and separated verdict.
    Maintain: no pre-existing process or shared memory store is changed.
    Assert: an executor timeout/nonzero exit overrides any apparent clean answer.
    """
    parser = argparse.ArgumentParser()
    parser.add_argument('--arm', choices=['A', 'B'], required=True)
    parser.add_argument('--prompt', type=int, choices=[1, 2, 3], required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--model', default='litellm/qwen3.5-reasoning-thinking-256k:4b')
    parser.add_argument('--agent')
    parser.add_argument('--thinking', action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument('--pure', action='store_true', help='Disable external plugins; arm B then exposes only its private memory MCP')
    parser.add_argument('--message', help='Use one exact diagnostic prompt instead of the selected fixed battery prompt')
    parser.add_argument('--timeout', type=float, default=180)
    parser.add_argument('--overlay', type=Path)
    parser.add_argument('--memory-url')
    args = parser.parse_args()
    if not 0 < args.timeout < 900:
        parser.error('timeout must be positive and below fifteen minutes')
    if args.message is not None and not args.message.strip():
        parser.error('--message cannot be empty')
    root = Path(__file__).parent
    args.out.mkdir(parents=True, exist_ok=False)
    config = json.loads((Path.home() / '.config/opencode/opencode.json').read_text(encoding='utf-8'))
    overlay = json.loads(args.overlay.read_text(encoding='utf-8')) if args.overlay else {}
    mcp = overlay.setdefault('mcp', {})
    private_memory = mcp.get('memory-index') if args.arm == 'B' else None
    if args.arm == 'B' and args.memory_url is None and (
        not isinstance(private_memory, dict)
        or private_memory.get('type') != 'local'
        or not private_memory.get('command')
    ):
        parser.error('arm B requires --memory-url or a private local memory-index command in --overlay')
    pure = args.pure or args.arm == 'A'
    if args.arm == 'A' or pure:
        for name in set(config['mcp']) | set(mcp):
            if args.arm == 'B' and name == 'memory-index' and private_memory and not args.memory_url:
                mcp[name] = private_memory
                continue
            mcp[name] = {'enabled': False}
    if args.arm == 'B':
        if args.memory_url:
            mcp['memory-index'] = {'type': 'remote', 'url': args.memory_url, 'enabled': True}
        else:
            mcp['memory-index']['enabled'] = True
    env = os.environ.copy()
    env['OPENCODE_CONFIG_CONTENT'] = json.dumps(overlay)
    executable = Path.home() / 'AppData/Roaming/npm/node_modules/opencode-ai/bin/opencode.exe'
    command = [str(executable), 'run', '--format', 'json']
    if args.thinking:
        command.append('--thinking')
    command.extend(['--title', PROBE_TITLE, '--print-logs', '--log-level', 'INFO', '--model', args.model])
    if args.agent:
        command.extend(['--agent', args.agent])
    if pure:
        command.append('--pure')
    prompt = args.message if args.message is not None else PROMPTS[args.prompt - 1]
    command.append(prompt)
    cwd = Path(os.environ['TEMP']) / 'opencode-start-probe'
    cwd.mkdir(exist_ok=True)
    metadata = {'arm': args.arm, 'prompt_number': args.prompt, 'prompt': prompt, 'prompt_source': 'diagnostic' if args.message is not None else 'fixed_battery', 'model': args.model, 'agent': args.agent, 'thinking': args.thinking, 'pure': pure, 'command': command, 'cwd': str(cwd), 'overlay': overlay, 'started': time.time(), 'timeout_seconds': args.timeout, 'status': 'starting'}
    receipt = args.out / 'run.json'
    receipt.write_text(json.dumps(metadata, indent=2), encoding='utf-8')
    started = time.monotonic()
    with (args.out / 'stdout.jsonl').open('wb') as stdout, (args.out / 'stderr.log').open('wb') as stderr:
        child = subprocess.Popen(command, cwd=cwd, env=env, stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr)
        metadata.update(pid=child.pid, status='running')
        receipt.write_text(json.dumps(metadata, indent=2), encoding='utf-8')
        with (root / 'processes.md').open('a', encoding='utf-8') as ledger:
            ledger.write(f'\n| {child.pid} | OpenCode {args.arm}/P{args.prompt} | {metadata["started"]} | {args.out} | taskkill /T /F /PID {child.pid} | {args.timeout}s |\n')
        print(json.dumps({'status': 'running', 'pid': child.pid, 'out': str(args.out)}), flush=True)
        timed_out = False
        try:
            child.wait(timeout=args.timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            cleanup = subprocess.run(['taskkill', '/T', '/F', '/PID', str(child.pid)], capture_output=True, text=True, check=False)
            metadata['cleanup'] = {'exit': cleanup.returncode, 'stdout': cleanup.stdout, 'stderr': cleanup.stderr}
            child.wait(timeout=10)
    metadata.update(status='finished', exit=child.returncode, timeout=timed_out, elapsed=round(time.monotonic() - started, 2))
    receipt.write_text(json.dumps(metadata, indent=2), encoding='utf-8')
    markers = json.loads((root / 'markers.json').read_text(encoding='utf-8'))['markers']
    verdict = check_events((args.out / 'stdout.jsonl').read_text(encoding='utf-8'), markers, metadata)
    if child.returncode != 0:
        verdict['invalid'].append('executor_exit')
    if timed_out:
        verdict['invalid'].append('timeout')
    verdict['valid'] = not verdict['invalid']
    (args.out / 'verdict.json').write_text(json.dumps(verdict, indent=2), encoding='utf-8')
    print(json.dumps({'arm': args.arm, 'prompt': args.prompt, 'exit': child.returncode, 'elapsed': metadata['elapsed'], 'valid': verdict['valid'], 'invalid': verdict['invalid'], 'text_chars': len(verdict['text']), 'markers': verdict['matches'], 'leaks': verdict['leaks'], 'tools': [item['tool'] for item in verdict['tools']]}), flush=True)
    raise SystemExit(0 if verdict['valid'] else 2)


if __name__ == '__main__':
    main()
