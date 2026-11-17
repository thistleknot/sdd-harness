"""Ordered, byte-preserving prompt rule registry.

Pipeline:
| Stage | Mechanism | Tag | Requirements |
|---|---|---|---|
| IMPORT | Capture Markdown source into an ordered SQLite fragment tree | [mandatory] | Requirement #4 |
| EDIT | Apply validated subtree edits and audit record in one transaction | [mandatory] | Requirement #4 |
| RENDER | Concatenate literal and editable spans in declared order | [mandatory] | Requirement #4 |
| BACKUP / REVIEW EXPORT | Preserve IDs, byte ownership, target maps, and audit state | [mandatory] | Requirement #4 |
| PUBLISH | Check registered target hash and replace through harness_write | [mandatory] | Requirement #4 |

R1: When an unchanged source is imported, rendering MUST reproduce its exact bytes.
R2: When a nested rule is edited, unrelated spans MUST preserve their bytes and sibling order.
R3: If a write fails validation or optimistic concurrency, the transaction MUST roll back.
R4: When a mapped destination is published, drift MUST be reported before replacement and exact readback verified.

CLOSED: Heading-only splitting is rejected because it changes the Markdown output; the observed migration helper replaces headings and strips edge blank lines.
Preconditions: source is UTF-8 Markdown and database path is writable.
Failure modes: malformed parent/position data, stale source hash, or failed backup raises before publication.
"""
