# Approval scope

Operator, 2026-11-09: "I should only be asked to approve sets of features (as I input them).
Derived requirements and artifacts happen after the fact, if needed. I can ask questions about
any artifact at any time."

## Rule

1. **Approval is required only for a feature set the operator submits** as input (the customer
   input). Nothing else requires approval.
2. **Derived artifacts proceed without approval**: requirements, design, tasks, UML and
   functional diagrams, entity model, workflows, decision records. The agent drafts and
   advances them.
3. **The operator reviews derived artifacts by question**, after the fact. The agent
   answers them and fixes what the operator rejects.
4. **Spec gates are advisory.** A gate may report that a phase is unapproved, but it does not
   block edits. (Implemented in `~/.claude/hooks/spec_gate.py`.)
5. **Stops are only those in CLAUDE.md §8**: missing credentials, spec contradiction with no
   derivable default, destructive action outside stated scope.

## Format of a request for the operator's word

- One summarized paragraph in requirement style: what will be done, and why.
- No file to open, no artifact to review. The operator answers "proceed" or objects.
- Default is proceed. Silence is approval.

## Export

This file is exported with `~/.harness`. Downstream harnesses (opencode, codex, claude) read it
as policy. Harnesses that run no spec gate follow it through their own instructions.
