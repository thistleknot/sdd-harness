# Provenance contract

**The original source is immutable.** It is never edited in place, never
summarized over, never deleted. Everything downstream is an *interpretation
layer* that must cite the source it was derived from.

## The layers

| Layer | What it is | Where it lives | Mutable? |
|---|---|---|---|
| 1. SOURCE | The raw captured artifact: the operator's own prompt, a PDF/DOCX/EPUB, an article, a third-party repo | `~/Documents/wiki/**` (raw capture)<br>`~/.skills/integrated/**` (curated golden-source extract) | **No** |
| 2. SPEC | Requirements / EARS clauses / acceptance criteria read *off* the source | `specs/requirements.md`, `specs/canon.md` | Yes |
| 3. STEERING / DESIGN | How this project chooses to apply the spec | `.kiro/steering/`, `specs/design.md` | Yes |
| 4. IMPLEMENTATION | Code, hooks, adapters | repo body | Yes |

Read top-down, each layer is an *opinion about* the layer above it. An opinion
you cannot trace back to a source is unfalsifiable, and unfalsifiable guidance
is what slop is made of.

## Caveat amending the SDD keep-rule

The standing rule is that SDD artifacts (requirements, design, EARS, UML,
PDR/DDL) are **not** sprawl and are not cut. This extends it:

> **Source material is not sprawl either.** A slop-cut may compress or merge
> interpretation layers (2-4). It must never delete a SOURCE, and must never
> leave an interpretation layer citing a source that no longer exists.

Compressing an interpretation is reversible — the source can regenerate it.
Deleting the source is not reversible, and it silently converts every
downstream doc into an unverifiable assertion.

## Rules

1. **Never edit anything under a SOURCE path.** Copy it out, then edit the copy.
2. **Every interpretation doc carries a `## Source` block** naming the exact
   path it derives from. `inspirations.md` already does this — match it.
3. **Large or binary sources stay where they are**; record the path, not a copy.
   (The Eden Marco book is a 78 MB PDF + 199 MB Docling JSON. Point at it.)
4. **Deleting an interpretation layer is allowed. Deleting a source is not.**
5. If a source's provenance is uncertain, mark it `UNVERIFIED` rather than
   guessing an attribution. A wrong attribution breaks the trail home.

See `SOURCES.md` for the registry.
