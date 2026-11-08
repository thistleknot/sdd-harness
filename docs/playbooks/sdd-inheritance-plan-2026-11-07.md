# Inherit sw-design + DDSE/SDD resources into the harness

SUPERSEDED for objectives by `sdd-integration-plan-2026-11-07.md` (same folder; promoted from `.tmp` 2026-11-07): this thread's storage/export work shipped (task #93), but the material was stored as references, never bonded into workflow; the integration campaign continues in the new folder.

CURRENT 2026-11-07. Objective: make two new resources — the `sw-design` skill at `~\.skills\sw-design\SKILL.md` and the note `~\.harness\docs\references\ddse and other sdd resources.md` — visible to `~\.claude` and `~\.codex` through the inheritance routes that already exist. No new sync mechanism.

The XDA shared-workspace thread stays CURRENT at the `.tmp` top level with its own open items (SpecsDB task #91 close, live handoff test); this thread lives in this dated subfolder so unrelated work is not overwritten.

## Goal restatement

- Stated: look at sw-design and the ddse/SDD resource note; apply plan-do to them.
- Actual need: the constitution (Article I) requires "a design exists (structural + behavioral layers)" but names no toolchain that produces it. `sw-design` supplies the toolchain (speckit spec -> Sphinx-Needs reqs -> needuml UML -> AIUP use cases + entity model -> Ecore -> pyecoregen classes). The ddse note supplies the conceptual boundary (Kiro design.md = whole-system architecture; AIUP entity model = data structure nested inside design). Inheriting both closes the design-layer gap for claude and codex.

## Governing contract

Requirements + Structural. Touches observable skill visibility in two live trees and adds reference docs, so spec-first applies: SpecsDB requirement #73 and task #93 recorded before execution.

## Chosen approach — existing routes only

| Route | Mechanism | Evidence it exists |
|---|---|---|
| claude skills | `~\.skills\sync_skills.ps1` mirror (skill-sync protocol) | script present in `.skills`, `.claude`, `.copilot`, `.hermes`, `.pi` roots |
| claude docs | vault `~\.harness\claude\docs\` -> `sync-to-claude.ps1 -Push` | vault has `docs/`; script maps vault->live with newer-and-smaller hold guard |
| codex skills | `python adapter.py --target skills --skill sw-design --apply` then `--target codex` | adapter.py L85: `SKILL_COPY_TARGETS = {'codex': '.agents/skills', ...}`; R19: native copy required, shared-index membership does not count |
| traceability | `.specs\file-manifest.md` rows for new files; playbook cross-links | manifest precedent in critique-todo 2026-11-02 |

## Rejected options

- New sync scripts or hand-copies into `~\.claude`/`~\.codex`: bypasses the git-backed safety model and the reduction guard.
- Vendoring the four external repos into `~\.harness\references\` now: plausible (sdd-skill and spec-kit are already vendored there) but it is an operator call — gate G1.
- Editing constitution Article I to name sw-design as the design-layer toolchain: the constitution is gates, not guidelines; gate G2.

## Waves — 3 remain; expected passes W1 4/4, W2 3/3, W3 2 gates

**W1 (parallel, disjoint files)**
1. Sync `sw-design` into `~\.claude\skills\sw-design\` via sync_skills.ps1. Verify: SKILL.md exists there.
2. Write a distilled DDSE reference into the vault at `~\.harness\claude\docs\references\ddse-and-other-sdd-resources.md` (link list + the design-layer-vs-entity-model distinction, stripped of chat-paste artifacts). Original raw note stays untouched in `~\.harness\docs\references\` as source. Verify: file exists, UTF-8/LF.
3. Add a "Design layer" section to `~\.harness\docs\playbooks\playbook-harness-sdd.md` naming both resources with paths. Verify: grep finds both paths.
4. Add manifest rows for the new vault file to `.specs\file-manifest.md`. Verify: manifest lint passes.

**W2 (sequential, shared tree)**
5. `python adapter.py --target skills --skill sw-design --apply`, then `--target codex`. Verify: native copy at `~\.agents\skills\sw-design\`, adapter drift check reports zero issues (R19/R20).
6. `.\sync-to-claude.ps1 -DryRun` — confirm the distilled doc is listed and nothing is held as a regression — then `-Push`. Verify: file present in `~\.claude\docs\references\`.
7. Smoke: sw-design appears in a claude session's skill list; `Get-ChildItem ~\.agents\skills\sw-design` non-empty.

**W3 (decision gates — nothing starts past them until recorded)**
- G1: vendor `pi-sdd-kit` / `spec-driven-development-book` / `Anioko/spec-driven-development` into `~\.harness\references\`, or keep link-only?
- G2: promote sw-design from playbook reference to a named design-layer toolchain in constitution Article I?

## Acceptance

- sw-design visible natively in both live trees (`.claude\skills`, `.agents\skills`).
- Distilled DDSE reference in vault and in `~\.claude\docs\references\` after -Push; sync reports no held files.
- Playbook names both resources; SpecsDB #73 active, #93 tracks waves; manifest rows exist.

## Open question back to operator

The local ddse note is read in full; the four external pages themselves are not fetched. If their content beyond the links must inform the distilled reference, say so (paste or authorize a fetch).
