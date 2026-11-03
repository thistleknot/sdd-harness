# OpenRouter: the same party, any vendor in the slot

A role is pinned to a **slot** (light, mid, heavy) and an **effort**, never to a
model. Each lane below lists the models slotted into it; at dispatch the harness
takes the first one that is available. Several vendors can share a lane, so the
Leader and the Fighters can sit on different mid-lane models.

Generate the picture with `python mermaid_to_infographic.py openrouter.md`.

```mermaid
flowchart LR
    %% title: OpenRouter: any vendor fills the slot, the roles stay the same
    %% slot light: anthropic/claude-haiku-5.5, openai/gpt-5.4-mini, deepseek/deepseek-v4-flash
    %% slot mid: anthropic/claude-sonnet-5.5, openai/gpt-5.4, deepseek/deepseek-v4-pro
    %% slot heavy: openai/gpt-5.6-sol, openai/gpt-5.6-terra

    User[User request] --> L["Leader (the session)<br/>anthropic/claude-sonnet-5.5 / medium<br/>devises the plan, writes the contract<br/>(signatures + Google docstrings),<br/>fixes low-level spec bugs<br/>(one clarification, then up)"]

    L <-->|"file sets / bug reports"| F["Fighters (doers, coders)<br/>openai/gpt-5.4 / low<br/>a team: fill the bodies, run the check"]
    L <-->|"reading / digest"| S["Scout (reader)<br/>anthropic/claude-haiku-5.5 / low<br/>read-only"]
    L <-->|"stuck + evidence / better spec"| O["Oracle (wild card)<br/>openai/gpt-5.6-sol / high<br/>get-out-of-jail card:<br/>replans from the evidence"]
```

## How a role finds its model

```
role  ->  (slot, effort)  ->  first available model in the slot  ->  request with that effort
```

- **Availability** is checked against OpenRouter's live model list
  (`GET https://openrouter.ai/api/v1/models`, no key needed). A listed model with
  `reasoning` in its `supported_parameters` can take the effort dial.
- **Effort** is one dial across vendors: low, medium, high map to the same
  rungs, so squashing and scaling a window works exactly as in
  `party-2-models.md` and `party-3-models.md`.
- **A different vendor for the Oracle** gives the Leader a read that does not share
  his blind spots, at the cost of two vendors' quirks.
