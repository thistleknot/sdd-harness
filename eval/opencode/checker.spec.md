# OpenCode event checker

CURRENT 2026-10-25: The checker remains a pure event instrument; capture validity
does not imply task-quality success or a memory/conflation result.

## Structural

def parse_events(raw: str) -> dict: separate text/reasoning/tools and completion; pure transformation, no owned state.
def check_events(raw: str, markers: list, metadata: dict | None) -> dict: score answer-only foreign markers and leaks; pure transformation.
def main() -> None: expose the checker CLI; arguments and files are external types.
Config: markers — observed foreign phrases, list of strings, varies by measurement campaign.
Config: metadata — command/model/prompt, mapping, varies by run.

## Behavioral: parse_events

Input: raw — UTF-8 JSON events, str.
Uses: JSON decoder — one object per nonblank line; raises on malformed JSON.
Initialize: result ← empty text/reasoning/tool/completion/error collections.
Loop over nonblank input lines:
    Decode one event; assert an object.
    When event is text or reasoning: assert string content; append to its own collection.
    Otherwise When event is tool_use: retain name/input/output/error in the tool collection.
    Otherwise When event is step_finish: retain the completion reason.
    Otherwise When event is error: retain the error separately.
    Otherwise: retain metadata without promoting it to answer text.
Return separated collections with original event line numbers.

## Requirements

- R1: When checking foreign markers, the checker MUST search answer text only.
  - Given three foreign text fixtures, When checked, Then each MUST be flagged.
  - Given foreign terms only in metadata, tools, or reasoning, Then none MUST be flagged.
- R2: When a marker occurs in command/model/prompt metadata, it MUST be excluded.
  - Given litellm only in command/header, When checked, Then conflation MUST be false.
  - Injected configuration/context overlays MUST NOT exclude the foreign state being measured.
- R3: If text contains think tags or repeats substantive reasoning, the checker MUST flag leakage.
  - Given tags, copied reasoning, and a clean separated reasoning fixture, Then leakage MUST discriminate.
- R4: If parsing fails, the checker MUST fail rather than score a clean answer.
  - Malformed JSON, non-object events, and non-string text MUST raise.
- R5: If text is empty, a runtime error occurs, or the last finish is not stop, the run MUST be invalid.
  - Tool-call intermediate finishes MUST NOT suffice as final completion.
- R6: A marker hit MUST retain the raw text line numbers for outer review.

Validated against spec skill: signatures, external types, scoped collections,
bounded loop, exclusive branches, error paths and acceptance traceability.
CLOSED: command/header grepping (RC-10); treating exit zero alone as success (RC-09).
