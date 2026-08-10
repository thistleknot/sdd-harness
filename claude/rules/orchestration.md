# Orchestration routing

Who-does-what lives in `~/.claude/agents/*.md` frontmatter and is auto-injected —
this file is only the control flow. Full prose, Mermaid, and the task
classification table: `~/.claude/docs/orchestration-full-2026-07-26.md`.

```
orchestrator (session, Sonnet-5 low)
├─ IF trivial mechanical one-liner (typo, rename, no behavior change)
│    └─ implement directly → DONE
├─ ELIF fully enumerable edit, no design judgment required
│    └─ implement directly → DONE
└─ ELSE
     └─ opus_planner [high] → plan/spec v1
          └─ orchestrator implements v1 inline
               └─ sonnet_critic [med] — Gate 1: verify + RUN (no run = no pass)
                    ├─ pass → DONE
                    ├─ fail + confident → proposes fix
                    │    └─ orchestrator applies verbatim + reruns same check
                    │         ├─ pass → DONE
                    │         └─ fail → Gate 2
                    └─ fail, not confident → evidence only → Gate 2
                         │
                         └─ opus_fixer_low [low] — Gate 2: propose (cross-model)
                              └─ orchestrator applies verbatim + reruns
                                   ├─ pass → DONE
                                   └─ fail
                                        └─ opus_fixer_med [med] — Gate 3 (Ctx A):
                                           writes AND applies directly, one shot
                                             ├─ pass → DONE
                                             └─ fail → LADDER EXHAUSTED
                                                  │
                                                  └─ opus_planner [high]
                                                     ALWAYS re-plans (v2), never fixes
                                                       └─ orchestrator implements v2
                                                            └─ fail → opus_fixer_med
                                                               (Ctx B: direct, NO critic,
                                                                NO Gate 2)
                                                                 ├─ pass → DONE
                                                                 └─ fail → round 2:
                                                                    opus_planner re-plans
                                                                    v3 (TERMINAL) → implement
                                                                    → fail → opus_fixer_med
                                                                    (Ctx B) → fail → STOP
```

## Invariants

- Each gate gets exactly **one** diagnosis/fix shot. Never skip a gate.
- Gates 1–2 **propose only**; the orchestrator applies verbatim and reruns the
  exact check the diagnosing agent specified. That apply step is not a subagent
  call.
- `opus_fixer_med` is the sole agent that writes and applies directly.
- `opus_planner` **never** fixes code, in any mode, at any round. Its only
  terminal action is a new plan/spec.
- Re-plan loop is bounded to **2 rounds**; the planner states on the second that
  it is terminal. Never a third.

## Operating policies

- Max **4** subagents active. Queue rather than exceed.
- Every subagent prompt states the **5-minute** default budget; higher budgets
  declared up front, else silence past budget = hung → stop the task.
- Handoffs are expensive — inline work needs no packet. When unavoidable, the
  writer saves `agentpacket_<UTCstamp>_<from>-to-<to>.md` to the project's
  `.agentpackets/` (gitignored; `~/.claude/agentpackets/` when no project
  context). The consumer reads it, then deletes it. Sweep stale packets at
  session end.
- Context: `/compact` at 70–80%, `/clear` + state summary at 90%+.
