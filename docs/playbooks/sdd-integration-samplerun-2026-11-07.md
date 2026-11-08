# RUN-REPORT — integrated sw-design chain, scaled-down e2e pass

Scratch root: C:\Users\user\.harness\.tmp\sdd-sample-run (nothing outside it touched)
Governing spec: SpecsDB REQ #73 / task #94; flow: ~/.skills/sw-design/references/integrated-flow.md
Python: C:\Users\user\py310\Scripts\python.exe · PlantUML: java -jar C:\Users\user\bin\plantuml.jar
Feature: library book lending, lane (d) data-touching. Date 2026-11-07.

## Step table

| # | Artifact | Command / check | Result |
|---|---|---|---|
| 1 | INTAKE.md | written, one lane-(d) row | PASS |
| 2 | specs/001-book-lending/spec.md + PRODUCT.md | 3 EARS reqs tagged D-001/D-002; `## Product Invariants` INV-1..3 | PASS |
| 3 | docs/sphinx/conf.py + requirements.rst + index.rst; build | `python -m sphinx -b html docs/sphinx docs/_build` → exit 0. Warnings: needs_extra_options deprecated (use needs_fields); needuml not rendered (below). First build FAILED: `needs_extra_args` wrong key for 8.5 (options need `needs_extra_options`), no master doc. | PASS (with recorded warnings) |
| 4 | needuml diagram | needuml directive FAILED to parse twice (`:id:` then `:name:` are unknown options in 8.5); parses with only `:scale:` but renders nothing: "PlantUML is not available... install sphinxcontrib-plantuml" (install would touch site-packages outside scratch — refused). FALLBACK used: docs/sphinx/lending.puml hand-written + `java -jar C:\Users\user\bin\plantuml.jar docs\sphinx\lending.puml` → docs/sphinx/lending_classes.png. | PASS via fallback path (needuml render FAILED) |
| 5 | design.md (7 sections), TECH.md, decisions.md (EDR D-001, CDR D-002, type-prefixed + 4-label AI-Context) | written, ids cited | PASS |
| 6 | docs/use_cases/UC-001-borrow-book.md, UC-002-return-book.md | `validate_use_case.py --strict` (found at C:\Users\user\.claude\skills\use-case-spec\scripts\) → "2 file(s) checked: 0 error(s), 0 warning(s)" exit 0 | PASS |
| 7 | lending.ecore | Flow-doc cmd `Resource.load(...)` FAILED (AttributeError: no classmethod load on pyecore 0.15.2). Working: `ResourceSet().get_resource(URI('lending.ecore'))` → contents: 1, classes [Member, Book, Loan], EAnnotations decision:D-001 (Loan) / decision:D-002 (Member) read back. | PASS (corrected command) |
| 8 | src/lending/{__init__.py, lending.py} | `python -m pyecoregen` FAILED (no `__main__`); console script works: `pyecoregen.exe -e lending.ecore -o src` (0.5.1 flags are -e/-o, not the --out/-n the task assumed) exit 0. Header `# GENERATED FROM lending.ecore - DO NOT EDIT - decisions: D-001,D-002` prepended to both files. Import: `python -c "import sys; sys.path.insert(0,'src'); import lending"` → OK. | PASS (corrected command) |
| 9 | validation-report.md | INV-1 MISSING (no enforcement carrier; loans upper=-1, borrow() is a stub), INV-2/3 PARTIAL (attributes generated, write-once/decrement semantics not). | PASS |
| 10 | RUN-REPORT.md | this file | PASS |

Helper `_probe_ecore.py` (API discovery) deleted after use.

## Three most discriminating findings

1. Command rot at two stage boundaries: the chain's own commands do not match the installed libs — pyecore 0.15.2 has no `Resource.load` classmethod, pyecoregen 0.5.1 has no `-m` entry and different flags (`-e/-o`, not `--out/-n`), and sphinx-needs 8.5 renamed extra options to `needs_extra_options`/`needs_fields`. The integrated flow is proven on artifacts, not yet on its quoted commands.
2. needuml cannot render standalone in this env: the directive parses after stripping `:id:`/`:name:` but silently no-ops without sphinxcontrib-plantuml; the diagram artifact that mattered came from the hand-written fallback + jar. Stage 3's "incumbent" is really PlantUML-the-jar, with sphinx-needs as index/traceability glue only.
3. The decision-backlink chain snaps at codegen: EAnnotations citing D-001/D-002 load fine from the .ecore but are absent from pyecoregen output; operations arrive as NotImplementedError stubs and the loans containment stays unbounded, so INV-1 has no enforceable carrier in the generated model — the citation law survives to the header marker only, and the invariant→behavior gap must close in the user-module mixin named in TECH.md.
