# Shared SDD deliverables contract

This contract is consumed by `~/.skills/spec/SKILL.md`,
`~/.skills/sw-design/SKILL.md`, and `specs.sdd_workflow`. The Python Pydantic
models are the machine-readable authority; `python -m specs.sdd_workflow schema`
prints their JSON Schema. Skills retain domain-specific content guidance.

## Handoff envelope

Each workflow checkpoint has `schema_version`, `workflow_id`, `profile`,
`workspace`, `intent`, `artifacts`, and `completed_stages`. Every artifact row
has `artifact_id`, `kind`, workspace-relative `path`, exact-byte `sha256`,
`producer_stage`, `status`, and `producer_role`. Unknown fields are rejected.

The shared artifact kinds are `intent`, `decision_record`, `specification`,
`requirements`, `design`, `use_cases`, `entity_model`, `approval`, `ecore`,
`generated_classes`, `implementation`, `tests`, `validation_report`, and
`verification_report`. Kind-specific document content stays with its skill;
the harness validates typed metadata, required stage outputs, path containment,
non-empty bytes, hashes, and the structured approval/report formats.

## Stage owners and required outputs

| Profile | Stage | Required output kinds | Producer | Approval authority |
|---|---|---|---|---|
| spec | draft | specification | spec | none |
| spec | validate | validation_report | spec | none |
| spec | review | approval | human | reviewer ID in approval JSON |
| spec | implement | implementation, tests | implementer | none |
| spec | verify | verification_report | verifier | none |
| sw-design | decisions | decision_record | sw-design | none |
| sw-design | specification | specification | spec | none |
| sw-design | requirements | requirements | sw-design | none |
| sw-design | design | design | sw-design | none |
| sw-design | use-cases | use_cases, entity_model | sw-design | none |
| sw-design | review | approval | human | reviewer ID in approval JSON |
| sw-design | ecore | ecore | sw-design | none |
| sw-design | generate | generated_classes | pyecoregen | none |
| sw-design | verify | verification_report | verifier | none |

Each stage can emit multiple artifacts of each required kind. Stages advance
strictly in profile order. The review output must be an `approval` artifact with
`status: approved`, `reviewer_id`, and `review_decision: approved`; its JSON file
must repeat `{"decision":"approved","reviewer_id":"..."}`. A validation or
verification report must be JSON with `{"passed":true,"checks":[...]}` and
`status: validated`.

The harness verifies report schema and artifact integrity; it does not rerun
arbitrary project tests or prove that a report's semantic claims are true.
Validation and verification reports must cite the actual checks run, and the
host should supply authenticated command evidence when it can.

## pyecoregen decision backlinks

The sw-design generation stage runs the following after pyecoregen succeeds:

```powershell
python scripts/annotate_generated.py --ecore <model>.ecore --output <generated-dir>
```

The command reads decision IDs only from EAnnotations whose
source is `decision` or begins `decision:`; requirement IDs and unrelated
annotation details are not decision backlinks. Each generated Python file gets
one leading `# GENERATED FROM <ecore-name> - DO NOT EDIT - decisions: <ids>`
line, with IDs sorted and comma-separated. An empty decision set is rendered as
`decisions: none`. Repeating the command replaces that marker instead of
stacking headers. The command fails before writing when the Ecore input or
output directory is missing, or when the output directory contains no Python
files.

## Gate and resume behavior

Initialize and inspect schema:

```powershell
python -m specs.sdd_workflow init --state .sdd/workflow.json --workspace . --profile spec --workflow-id feature-123 --intent "<objective>"
python -m specs.sdd_workflow schema
```

After a stage writes its deliverables, provide a JSON array of artifact rows and
commit the handoff:

```powershell
python -m specs.sdd_workflow advance --state .sdd/workflow.json --workspace . --stage draft --artifacts .sdd/draft-artifacts.json
```

`advance` refuses skipped/repeated stages, missing output kinds, malformed
artifact rows, missing or empty files, workspace escapes, stale hashes, and
failed report/approval checks. It writes the receipt atomically only after all
checks pass. The `PostTaskExec` gate runner invokes the same validator whenever
its payload declares `sdd_workflow_path`, `sdd_stage`, `sdd_workspace`, and
`sdd_artifacts`.

Resume before running further work:

```powershell
python -m specs.sdd_workflow resume --state .sdd/workflow.json --workspace .
```

Matching receipts and their artifacts are reused without rerunning their stage.
The earliest missing or changed artifact invalidates its receipt and all later
receipts; resume reports the next stage and persists that reduced checkpoint.
Regenerate only from that stage. A handoff that fails validation leaves the prior
checkpoint unchanged and reports the unmet requirement.

The approval row enforces declared human review shape and reviewer attribution;
identity authentication remains the host harness's responsibility. The SDD
gate is only authoritative in hosts that surface the validator as a blocking
`PostTaskExec` gate; hosts without that capability run the same CLI as an
explicit gate and must report it as advisory if they cannot stop continuation.
