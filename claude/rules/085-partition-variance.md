# Partition variance — when the knobs stop moving the result

<!-- Spec: no governing spec. Basis: CLAUDE.md law 6b, which has cited this path since it
     was written while the file did not exist (found 2026-09-12 during the glossary audit —
     a prose pointer that loads nothing and is never verified). This file is the expanded
     protocol; law 6b stays the summary. Operator instruction 2026-09-13: "do the obvious". -->

The one-line law lives in CLAUDE.md ("6b. Partition variance"). This is how to run it.

## The trigger

You are sweeping a parameter. The numbers come back and they are all the same.

**A grid whose cells agree to three significant figures is a broken instrument, not a tie.**
Read it that way. The temptation is to declare the parameter unimportant and move on, or to
widen the range and sweep harder. Both are wrong, and both cost a day.

When the knobs stop moving the result, the fault is **STRUCTURAL**. Stop sweeping. Start
removing.

## Prove the axis is live before you sweep it

A sweep only measures a parameter that actually reaches the output. Most dead sweeps are
measuring a stage that was disconnected upstream.

```
change the upstream stage's seed
diff the output
zero difference  ->  that stage never reaches the output
```

Do this **before** the sweep, not after it disappoints. It is one run and it is the
difference between a real negative result and a wasted grid.

## Rebuild from the minimum

Once you know a stage is dead, do not patch around it. Strip to the smallest thing that
produces output at all, then re-add **ONE** component per stage. A difference is only
attributable when exactly one thing changed.

This is Article VI (root-first isolation) applied to a search rather than a bug: walk
backward to the earliest link that still moves the number, and start there.

## Search in rounds, and expand rather than drill

Ranking the top 3 and then sweeping the winner's own axis harder discovers nothing. It
also silently asserts that everything you held fixed is irrelevant — an assertion you never
tested and probably cannot defend.

```
round n:    rank the top 3 along ~3 axioms
round n+1:  make those 3 the BASES
            cross them against axioms you have NOT varied yet
```

Expansion into new dimensions, never drilling the winner's own axis.

## Carry the winners forward

Re-run the surviving candidates under **identical conditions** in the new round. "Did we
improve" cannot be answered against remembered numbers — the conditions moved, the harness
moved, the data moved, and a number from two rounds ago is not comparable to a number from
now. If a winner is not re-run, it is not a winner, it is a memory.

## Never freeze a winner — only demote it

**A closure is a fact about a parameter GIVEN a context.** Record the context alongside the
value, and re-open the parameter when that context moves.

Freezing turns the search into coordinate descent, which can never escape a local optimum.
Demotion keeps the level in the pool at low priority; freezing removes it from the pool
entirely, and nothing ever puts it back.

Keep a **standing exploration budget** for re-testing rejected levels. A level rejected
under an old context is not a level rejected.

## The score is a second opinion

An automated score is evidence, not a verdict. It ranks; it does not decide. Look at the
artifacts the winning cell actually produced before you believe its number — a metric that
rewards degenerate output will rank degenerate output first, and the grid will look
perfectly healthy while doing it.

## Failure modes this rule exists to stop

| Symptom | What it actually means | Move |
|---|---|---|
| Every cell agrees to 3 s.f. | The axis is not reaching the output | Seed-diff the upstream stage |
| Widening the range changes nothing | Structural, not parametric | Strip to minimum, re-add one at a time |
| Best cell keeps winning by a hair | You are drilling its own axis | Cross the top 3 against unvaried axioms |
| "It was better last time" | Comparing against remembered numbers | Re-run the incumbent in the same round |
| A parameter is "settled" | A closure without its context | Demote, record the context, keep a re-test budget |
