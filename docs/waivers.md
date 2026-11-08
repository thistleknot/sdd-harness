# Waivers — per-decision, scoped, expiring (policy/rule-conflict-protocol.md sibling)

Format (one line per waiver; the project's decision_gate.py enforces expiry):

```
D-<id> scope=<what exactly is excused> expires=<YYYY-MM-DD>
```

Rules: an expired waiver never excuses a failure (DDSD #5: exceptions expire or they
are lies). A waiver covers its scope only — a different violation of the same decision
still fails. Waivers are appended, never edited; removal is a new "withdrawn" line.

| decision | scope | expires |
|---|---|---|
