# Orchestration routing: a party on an accordion

Operator, 2026-10-17: Scout = Haiku 5.5 low; Fighters (coders) = Haiku 5.5 medium;
Leader (orchestrator) = Sonnet 5.5 medium; Oracle = Sonnet 5.5 high. No Opus.
The Leader owns the high-level contracts (function headers, docstrings); Fighters
implement the bodies; only Sonnet medium (the Leader) corrects them.
Who-does-what is auto-injected from `~/.claude/agents/*.md`; model and effort
policy is data in `~/.harness/tiers.toml` (the translation layer). This file is
the control flow.

## The party

| Class | Agent | Effort floor -> ceiling | Gear | Job |
|---|---|---|---|---|
| Leader | the session | medium (medium model) | everything | devises the initial plan; turns specs into file sets carrying docstrings and definitions; hands them to the Fighters; resolves the low-level bugs they report (a misapplied docstring or definition); calls on the Oracle only for hard problems |
| Fighters (doers, coders) | `doer`, a team | medium -> medium | read-write | each fills the bodies of one file set to its contract and runs the check |
| Scout (reader) | `reader` (Haiku 5.5) | low -> low | read-only | reads and summarizes into a digest with `file:line` pointers |
| Oracle (the priest, a wild card) | `oracle` | high -> high | read + Bash + write specs | cuts the Gordian knot: diagnoses what the Leader could not and returns a better spec; never writes bodies |

A class is a job and a set of tools. Effort is a dial set at dispatch with the
Agent `effort` parameter; the frontmatter value is only the floor.

## The flow

1. The Leader devises the plan and turns the spec into file sets: sets of files
   carrying docstrings and definitions (the contract).
2. A team of Fighters, one per file set (parallel, within the 4-agent cap), fill
   the bodies and run the check.
3. A Fighter that hits a bug reports it. The Leader answers first: a low-level
   bug (a misapplied docstring or definition) is his to fix by repairing the
   contract and re-issuing the file set.
4. If the Leader's one clarification does not clear it, the bug goes up to the
   Oracle, who replans from the evidence: the Fighters' reports, the attempted
   fix and the Leader's failed clarification. His better spec comes back to the
   Leader, who re-interprets it into file sets, and the Fighters go again.

The Leader is the hero: he gets first crack at everything and is trusted to get it
done. The Oracle is his companion and his get-out-of-jail card, a deus ex machina
played when the hero is out of options. He is rare on purpose, and he does his best
work with the evidence of how the hero got stuck, which is why he is not called
upfront. The exception is a plan that is large or costly to get wrong (long Fighter
runs, irreversible actions): there the Leader may play the card before the Fighters
start.

## The accordion

Widen one step only on a trigger, and contract again when it clears. A handoff
costs context, so each one has to earn its place.

```
trigger                                                     widen to
file sets with contracts to fill                            Fighters (doers, low)
bulk reading / logs / search output                         Scout (reader)
a Fighter's bug is a misapplied docstring or definition     the Leader, inline (no dispatch)
a bug the Leader cannot resolve                             Oracle (high)
```

## Squash

Roles with the same model and the same effort share one context, so no handoff is
spent on them. Escalating to the Oracle raises effort (Sonnet 5.5,
high) in a fresh context, not the Leader re-reading his own work. If a window squashes the Oracle onto the Leader's
settings there is nobody above to escalate to, and the Leader keeps the problem.

## Invariants

- The ceiling is the Oracle (Sonnet 5.5 high). If the Oracle's spec does not resolve it, the
  Leader decides: he has the observation the Oracle named as missing run, or
  proceeds on the best-supported reading and logs the basis. The operator is
  asked only for the standing stops (missing credentials, a spec contradiction
  with no derivable default, a destructive action outside scope).
- The Leader owns the contract (signatures + docstrings). Fighters never edit it;
  a contract that cannot be satisfied is reported BLOCKED, and the Leader (or the
  Oracle) repairs it.
- A Fighter gets one attempt per dispatch. A failure comes back as a bug report,
  not a retry.
- The Leader gets `leader_attempts` re-issues of a file set at a reported bug
  (`tiers.toml` `[escalation]`, default 1) before it goes to the Oracle. The cap is
  a measured break-even: keep trying while P(the next attempt resolves it) exceeds
  the cost of a Leader attempt divided by the cost of an Oracle call.
- The Oracle writes specs and diagnoses; he never writes bodies. A Scout's digest
  is never evidence of pass/fail; the Leader or the Oracle re-reads the raw lines.
- The Oracle augments a plan at most **2 times** per task and says so on the
  second; after that the Leader decides.

## Operating policies

- Max **4** subagents active. Queue rather than exceed.
- Concurrent work in one checkout MUST have disjoint file ownership; overlapping edits are serialized or isolated in separate task worktrees.
- Every subagent prompt states the **5-minute** default budget; higher budgets
  declared up front, else silence past budget = hung -> stop the task.
- Handoffs are expensive; inline work needs no packet. When unavoidable, the
  writer saves `agentpacket_<UTCstamp>_<from>-to-<to>.md` to the project's
  `.agentpackets/` (gitignored; `~/.claude/agentpackets/` when no project
  context). The consumer reads it, then deletes it. Sweep stale packets at
  session end.
- Context: `/compact` at 70-80%, `/clear` + state summary at 90%+.
