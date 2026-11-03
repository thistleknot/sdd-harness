```mermaid
flowchart LR
    %% slot heavy: gpt-6.1-sol, gpt-6.5-tierra
    User[User request] --> L["Leader (the session)<br/>gpt-5.4 / medium<br/>devises the plan, writes the contract<br/>(signatures + Google docstrings),<br/>fixes low-level spec bugs<br/>(one clarification, then up)"]

    L <-->|"file sets / bug reports"| F["Fighters (doers, coders)<br/>gpt-5.4 / low<br/>a team: fill the bodies, run the check"]
    L <-->|"reading / digest"| S["Scout (reader)<br/>gpt-5.4-mini / low<br/>read-only"]
    L <-->|"stuck + evidence / better spec"| O["Oracle (wild card)<br/>gpt-6.1-sol / high<br/>get-out-of-jail card:<br/>replans from the evidence"]
```
