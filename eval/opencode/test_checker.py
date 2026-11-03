"""| Stage | Mechanism | Contract |
| FIXTURE | Construct varied native event records | [mandatory] R1-R6 |
| ASSERT | Discriminate text, tools, metadata, reasoning and invalid capture | [mandatory] R1-R6 |

R1-R6: checker.spec.md owns acceptance; pytest calls each case independently.
CLOSED: broad marker counts that cannot discriminate clean/foreign input, RC-10.
Preconditions: pytest and the sibling checker module; no live service required.
Failure modes: any contract mismatch fails without fallback.
"""

import json

import pytest

from checker import check_events


def events(text, *extra, reason='stop'):
    """Build a varied native capture for the acceptance tests.

    Require: text is the desired answer payload and extras are JSON events.
    Guarantee: preserve each extra and append an explicit finish event.
    """
    rows = [*extra, {'type': 'text', 'part': {'type': 'text', 'text': text}}, {'type': 'step_finish', 'part': {'reason': reason}}]
    return '\n'.join(json.dumps(row) for row in rows)


@pytest.mark.parametrize('marker,text', [('Asana', 'I am fixing Asana submission checks.'), ('CTP2', 'Current work: ctp2 assets.'), ('yearColorActive', 'I will restore yearColorActive before proceeding.')])
def test_foreign_answer_text_is_flagged(marker, text):
    """Require varied foreign text; guarantee a hit with its raw line reference."""
    verdict = check_events(events(text), [marker])
    assert verdict['valid']
    assert verdict['matches'] == [{'marker': marker, 'lines': [1]}]


@pytest.mark.parametrize('extra', [
    {'type': 'header', 'command': 'opencode -m litellm/qwen CTP2'},
    {'type': 'tool_use', 'part': {'tool': 'todo_list_todos', 'state': {'status': 'completed', 'input': {}, 'output': 'CTP2 work remains'}}},
    {'type': 'reasoning', 'part': {'text': 'I must avoid adopting the unrelated CTP2 task.'}},
])
def test_foreign_terms_outside_answer_are_not_conflation(extra):
    """Require metadata/tool/reasoning variants; guarantee clean answer scoring."""
    verdict = check_events(events('Binary search halves a sorted range.', extra), ['CTP2', 'litellm'])
    assert verdict['valid']
    assert verdict['matches'] == []
    assert verdict['leaks'] == []


@pytest.mark.parametrize('text', ['</think>Answer follows.', '<think>I should inspect context.</think>42', '<THINK>Planning text'])
def test_inline_reasoning_tags_are_leaks(text):
    """Require varied tag forms; guarantee the reasoning-leak signal."""
    assert check_events(events(text), [])['leaks'] == ['think_tag']


def test_copied_reasoning_is_distinct_from_clean_reasoning():
    """Require substantive reasoning; guarantee copied and separated cases differ."""
    thought = 'First I need to identify the sorted middle positions before answering.'
    extra = {'type': 'reasoning', 'part': {'text': thought}}
    assert check_events(events('Return the two middle values.', extra), [])['leaks'] == []
    assert check_events(events(thought + '\nReturn the two middle values.', extra), [])['leaks'] == ['copied_reasoning']


@pytest.mark.parametrize('raw', ['{"type":', '["text", "hello"]', '{"type":"text","part":{"text":7}}'])
def test_malformed_capture_cannot_score_clean(raw):
    """Require three malformed capture classes; guarantee failure rather than abstention."""
    with pytest.raises(ValueError):
        check_events(raw, ['foreign'])


@pytest.mark.parametrize('raw,issue', [
    (events(''), 'empty_text'),
    (events('Partial output', reason='length'), 'no_final_stop'),
    (events('Answer', {'type': 'error', 'error': {'message': 'gateway failed'}}), 'runtime_error'),
])
def test_incomplete_or_errored_runs_are_invalid(raw, issue):
    """Require distinct runtime failures; guarantee invalid classification."""
    verdict = check_events(raw, [])
    assert not verdict['valid']
    assert issue in verdict['invalid']


def test_command_terms_are_excluded_and_tool_evidence_is_preserved():
    """Require command overlap and a tool result; guarantee exclusion plus evidence retention."""
    tool = {'type': 'tool_use', 'part': {'tool': 'memory_search_memory', 'state': {'status': 'completed', 'input': {'query': 'current task'}, 'output': 'Foreign task'}}}
    verdict = check_events(events('litellm answered correctly.', tool), ['litellm'], {'command': 'opencode -m litellm/local'})
    assert verdict['excluded_markers'] == ['litellm']
    assert verdict['matches'] == []
    assert verdict['tools'][0]['input'] == {'query': 'current task'}
    assert verdict['tools'][0]['output'] == 'Foreign task'


@pytest.mark.parametrize('marker,metadata', [
    ('CTP2', {'model': 'litellm/local', 'overlay': {'agent': {'orchestrator': {'prompt': 'CTP2 image patching'}}}}),
    ('Asana', {'environment': {'OPENCODE_CONFIG_CONTENT': 'Asana submission verification'}}),
    ('missing_details', {'source_results': [{'origin': 'another project', 'text': 'fix missing_details'}]}),
])
def test_injected_context_cannot_hide_its_own_foreign_marker(marker, metadata):
    """Require a contaminated overlay; guarantee that answer adoption remains detectable."""
    verdict = check_events(events('My current task is ' + marker + '.'), [marker], metadata)
    assert verdict['matches'] == [{'marker': marker, 'lines': [1]}]
