---
inclusion: auto
---

# Deliberation Protocol

## When to Deliberate

Fire this protocol at key decision points in the workflow:

- **Intent extraction** — what does the user actually want?
- **Problem diagnosis** — what's actually broken and why?
- **Solution selection** — which approach to take among candidates?
- **Spec formation** — what should the artifact contain?
- **Scope decisions** — what's in, what's out, where's the boundary?

Do NOT deliberate on trivial/mechanical actions (rename a variable, fix a typo).

## The Three-Phase Protocol

### Phase 1: Expand (3 degrees out)

Before narrowing, expand the problem space deliberately:

**TRIZ** — Inventive problem solving:
- What contradictions exist? (improving X worsens Y)
- What resources are already present but unused?
- What would the ideal final result look like if there were no constraints?
- Can the problem be inverted, segmented, or merged with another?

**Bono's Six Hats** — Forced perspective rotation:
- White hat: What data/facts do we actually have? What's missing?
- Red hat: What's the gut reaction? What feels wrong?
- Black hat: What could go wrong? What are the risks?
- Yellow hat: What's the optimistic case? What's the payoff?
- Green hat: What unconventional approaches exist?
- Blue hat: What's the process here? Are we asking the right question?

**3 degrees out:**
- 1st degree: the immediate problem/intent as stated
- 2nd degree: adjacent concerns that interact with it
- 3rd degree: systemic patterns this instance is part of

Generate at least 3 candidate interpretations or approaches.

### Phase 2: Reify (surviving premises)

Collapse the expanded space down to what survives scrutiny:

- Which candidates are **falsified** by known evidence? Eliminate them.
- Which premises are **observed** (tool output, user statement, file content)?
- Which are **inferred** (derived, assumed, extrapolated)? Tag them.
- What is the **discriminating evidence** between surviving candidates?
- State the falsification condition for each survivor: "this would be wrong if..."

Output: a short list of surviving premises (2-5), each tagged [observed] or [inferred].

### Phase 3: Thesis (supporting premises, iterated)

Form the working hypothesis from surviving premises:

```
Thesis: <one-line statement of intent/solution/diagnosis>
Confidence: <low|medium|high>
Supporting premises:
  1. [observed] <fact>
  2. [inferred] <derivation>
  3. [observed] <fact>
Falsification: <what would prove this wrong>
Open questions: <what we can't yet verify>
```

**Iteration rule:** Each new piece of evidence updates the thesis. Premises get
promoted (inferred → observed) or eliminated. The thesis sharpens or pivots.
Never carry forward a premise that contradicts new evidence.

## Output Format

When deliberating on something the user should see:

```
[deliberation]
Expand: <brief 3-degree + TRIZ/hats insight>
Reify: <surviving premises, tagged>
Thesis: <current hypothesis, confidence, falsification condition>
[/deliberation]
```

When the deliberation is internal (routine decision), just apply the protocol
silently and state the conclusion. Show the work only when:
- Confidence is low (surface options to user)
- Multiple viable candidates survive reification
- The decision has irreversible consequences

## Relationship to Intent Tracking

When deliberation produces a thesis about user intent:
- If confidence is high → proceed, track as `intent:` todo
- If confidence is medium → state thesis + one alternative, ask user to confirm
- If confidence is low → surface numbered options from Phase 1 candidates

## Anti-Patterns

- Expanding without collapsing (analysis paralysis)
- Skipping expand and jumping to thesis (premature commitment)
- Carrying inferred premises as if observed (epistemic inflation)
- Deliberating on trivial decisions (overhead without value)
- Re-deliberating settled decisions (re-litigation)
