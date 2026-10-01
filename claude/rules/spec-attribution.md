# Spec attribution — every generated file says what authorises it

Reaching an approved `implement` phase proves the phases were approved. It says nothing
about whether the file you are about to write is in scope. Two different questions; the
phase gate answers only the first.

**The rule: no artifact without a named source of guidance, written INTO the artifact.**

This exists so the operator can always do one of two things at a glance: correct the spec,
or discover there was none. An unattributed file offers neither — it looks equally like
faithful implementation and like invention.

## Before writing

State out loud, in the response, the task id the change serves. **No task = no write.** The
move is to add the task, not to skip the check. A task with no `_Files:` line is not
implementable; populating the catalog IS the next step.

If no spec covers the work, say **"no governing spec found"** explicitly and draft or amend
one first. Silence is not permission.

## In the artifact

Every generated or substantially-rewritten file carries its provenance at the top, in
whatever comment syntax it uses:

```python
"""src/thing.py — one line on what it does.

Spec: .spec/specs/<feature>/requirements.md REQ-J11 (scored worked examples)
Task: tasks.md #29
"""
```

```markdown
<!-- Spec: .spec/specs/<feature>/judge-rubric.md REQ-J11 · Task: tasks.md #29 -->
```

Data and config files get the same treatment where the format allows a comment. Where it
does not (strict JSON, CSV), the provenance goes in the sibling manifest or the writer.

**Cite the requirement, not just the feature.** "Spec: judge-rubric.md" tells the operator
where to look; "REQ-J11" tells them what to correct.

## When the guidance is not a spec

Say what it actually was, and mark it as unspec'd rather than inventing a citation:

```python
# NO GOVERNING SPEC. Basis: operator instruction 2026-08-28 ("show the correct answer
# so the judge knows what a correct answer looks like"). Promote to a REQ before this
# is depended on.
```

Never fabricate a requirement id. An invented citation is worse than none — it defeats the
one thing the attribution exists to enable.

## On handing back

Every changed file must be claimed by a task. Report unclaimed changes **as unclaimed** —
never fold them quietly into "and I also fixed…". A file that needed changing but belongs
to no task means the spec is wrong: amend the spec, then write (Article IX).

## Bash does not launder this

`python patch.py`, `sed -i`, and a heredoc are the same act as Edit. The PreToolUse gate
mostly watches Edit/Write, so a shell-mediated source write needs MORE self-imposed
discipline, not less — precisely because nothing will stop you.
