"""| Stage | Mechanism | Contract |
| CHECK | Deterministic response-format predicates | [mandatory] R14 |
| SCORE | Pair fixes/breaks by immutable item ID and stratum | [mandatory] R15 |
Spec: docs/playbooks/memory-and-harness-integration.md.
CLOSED: a style checker as a factual-correctness judge.
Preconditions: configured known checker; outputs remain raw elsewhere.
Failures: unknown checker or malformed case raises; empty output cannot pass.
"""
from __future__ import annotations

import re

OFFER = re.compile(r'\b(would you like|want me to|should I|shall I|let me know if you want|may I proceed|can I proceed)\b', re.I)
BANNED = re.compile(r"\b(bottom line|delve|here.s the thing|uncomfortable truth|genuinely)\b", re.I)
SOFTENER = re.compile(r'\b(just a minor|only a small|nothing major|probably fine|not a big deal)\b', re.I)


def check_response(case: dict, text: str) -> bool:
    """Evaluate the declared observable contract without an LLM judge.

    Require: case names one supported checker; text is the raw answer string.
    Guarantee: empty output fails; checks are deterministic and side-effect free.
    Maintain: this measures declared format/content, not general answer quality.
    Assert: an unknown checker is a configuration error.
    """
    if not isinstance(text, str) or not text.strip():
        return False
    kind = case['checker']
    if kind == 'no_offer':
        return not OFFER.search(text)
    if kind == 'answer_first':
        first = text.lstrip().splitlines()[0].strip(' #*`')
        return first.startswith(case.get('expected', 'PASS'))
    if kind == 'no_banned':
        return not BANNED.search(text)
    if kind == 'no_softener':
        return not SOFTENER.search(text)
    if kind == 'contains':
        return str(case['expected']) in text
    if kind == 'abstain':
        return bool(re.search(r"\b(unknown|do not know|don't know|insufficient evidence|not supported)\b", text, re.I))
    raise ValueError(f'unknown checker: {kind}')


def flips(baseline: list[dict], candidate: list[dict], ids: set[str]) -> dict:
    """Count paired fixes/breaks only for the selected item IDs.

    Require: both arms contain each selected ID exactly once.
    Guarantee: net equals fixes minus breaks; A/A uses the same pairing.
    Maintain: no unpaired pass-rate comparison.
    Assert: missing IDs raise rather than becoming clean results.
    """
    old = {x['id']: x for x in baseline}
    new = {x['id']: x for x in candidate}
    if not ids <= old.keys() or not ids <= new.keys():
        raise ValueError('paired items are missing')
    fixed = sum(not old[i]['passed'] and new[i]['passed'] for i in ids)
    broken = sum(old[i]['passed'] and not new[i]['passed'] for i in ids)
    return {'fixes': fixed, 'breaks': broken, 'net': fixed - broken, 'flips': fixed + broken}
