"""| Stage | Mechanism | Contract |
| PARSE | Decode native JSON lines into typed part collections | [mandatory] R4 |
| VALIDATE | Require answer text and a final stop without runtime errors | [mandatory] R5 |
| SCORE | Match foreign phrases and leaked reasoning only in answer text | [mandatory] R1-R3 |
| REPORT | Preserve raw line references and separated tool evidence | [mandatory] R6 |

R1-R6: checker.spec.md defines the caller and acceptance contracts.
CLOSED: header/command grepping was falsified by RC-10; exit zero is insufficient.
Preconditions: native JSON stdout; observed markers and optional run metadata.
Failure modes: malformed events raise; missing text/completion yields invalid.
"""

import argparse
import json
import re
from pathlib import Path


def parse_events(raw: str) -> dict:
    """Separate OpenCode evidence for check_events and the driver.

    Require: raw contains one JSON object per nonblank line.
    Guarantee: metadata and tool results never enter answer text.
    Maintain: original one-based line numbers accompany text and reasoning.
    Assert: answer/reasoning payloads are strings; malformed input raises.
    """
    result = {'text': [], 'reasoning': [], 'tools': [], 'finishes': [], 'errors': [], 'metadata': []}
    for line_number, line in enumerate(raw.splitlines(), 1):
        if not line.strip():
            continue
        event = json.loads(line)
        if not isinstance(event, dict):
            raise ValueError(f'Event on line {line_number} is not an object')
        kind = event.get('type')
        part = event.get('part', {})
        if kind in ('text', 'reasoning'):
            if not isinstance(part, dict) or not isinstance(part.get('text'), str):
                raise ValueError(f'{kind} on line {line_number} requires string text')
            result[kind].append({'line': line_number, 'text': part['text']})
        elif kind == 'tool_use':
            state = part.get('state', {})
            result['tools'].append({'line': line_number, 'tool': part.get('tool'), 'input': state.get('input'), 'output': state.get('output'), 'status': state.get('status'), 'error': state.get('error')})
        elif kind == 'step_finish':
            result['finishes'].append(part.get('reason'))
        elif kind == 'error':
            result['errors'].append(event.get('error', part))
        else:
            result['metadata'].append(event)
    return result


def check_events(raw: str, markers: list, metadata: dict | None = None) -> dict:
    """Judge event evidence for the driver and outer harness review.

    Require: markers come from observed foreign state; metadata describes this run.
    Guarantee: return validity, answer-only hits, leak flags and raw part evidence.
    Maintain: model/command terms cannot become foreign marker evidence.
    Assert: parsing errors propagate and cannot become a clean verdict.
    """
    parts = parse_events(raw)
    text = '\n'.join(item['text'] for item in parts['text'])
    reasoning = '\n'.join(item['text'] for item in parts['reasoning'])
    command_metadata = {key: value for key, value in (metadata or {}).items() if key in ('command', 'model', 'prompt')}
    metadata_text = json.dumps(command_metadata, ensure_ascii=False).casefold()
    excluded = [marker for marker in markers if marker.casefold() in metadata_text]
    hits = []
    for marker in markers:
        if marker in excluded:
            continue
        pattern = re.compile(r'(?<!\w)' + re.escape(marker) + r'(?!\w)', re.IGNORECASE)
        lines = [item['line'] for item in parts['text'] if pattern.search(item['text'])]
        if lines:
            hits.append({'marker': marker, 'lines': lines})
    leaks = []
    if re.search(r'</?think\b[^>]*>', text, re.IGNORECASE):
        leaks.append('think_tag')
    normalized_text = ' '.join(text.split())
    for item in parts['reasoning']:
        normalized_reasoning = ' '.join(item['text'].split())
        # Short overlaps such as PONG also occur in legitimate answer planning;
        # require a substantive copied reasoning span rather than a common token.
        if len(normalized_reasoning.split()) >= 8 and normalized_reasoning in normalized_text:
            leaks.append('copied_reasoning')
            break
    invalid = []
    if not text.strip():
        invalid.append('empty_text')
    if not parts['finishes'] or parts['finishes'][-1] != 'stop':
        invalid.append('no_final_stop')
    if parts['errors']:
        invalid.append('runtime_error')
    return {'valid': not invalid, 'invalid': invalid, 'matches': hits, 'leaks': leaks, 'excluded_markers': excluded, 'text': text, 'reasoning': reasoning, 'tools': parts['tools'], 'parts': parts}


def main() -> None:
    """Expose the file checker to Codex's command-line driver.

    Require: paths reference UTF-8 run stdout and marker data.
    Guarantee: print one JSON verdict; return failure for invalid capture.
    Maintain: no input file is changed.
    """
    parser = argparse.ArgumentParser()
    parser.add_argument('stdout', type=Path)
    parser.add_argument('--markers', type=Path, default=Path(__file__).with_name('markers.json'))
    parser.add_argument('--metadata', type=Path)
    args = parser.parse_args()
    markers = json.loads(args.markers.read_text(encoding='utf-8'))['markers']
    metadata = json.loads(args.metadata.read_text(encoding='utf-8')) if args.metadata else None
    verdict = check_events(args.stdout.read_text(encoding='utf-8'), markers, metadata)
    print(json.dumps(verdict, ensure_ascii=False))
    raise SystemExit(0 if verdict['valid'] else 2)


if __name__ == '__main__':
    main()
