# ADR-0006: Continuous work, source precision and import reconciliation

Date: 2026-11-08. Status: proposed import mapping; general model selected for
development. Real import awaits owner/scope mapping approval.

Context: row 32 is Continua; row 34 is done with recurring wording; only 8 of
34 deadlines are populated. Weekly notes lack exact timestamps and authors.

Decision: work_type one_off/ongoing, orthogonal to lifecycle state. Proposed
row-32 mapping: ongoing + in_progress, no completed_at and no generated schedule.
Do not add recurrence engine/custom lifecycle status for one ambiguous label.
Row 34 retains source done, flagged for review; no future occurrences inferred.
An explicit termination operation is required to end ongoing work.

Preserve source status/text/raw date/precision. Date-only deadline is inclusive
through that business date, represented as next-local-day start exclusive in
UTC plus original DATE/timezone. Missing stays null. No fabricated completion
time or weekly timestamp/author. Keep recorded_at distinct from occurred_at.
Calculated deadline category names completed/ongoing/no_due_date/overdue/
due_soon/on_track are not stored as authoritative workflow state.

Dry-run reconciles all rows/updates/notes, aliases and exact labels with mapping
version and explicit reference date. Import does not create users or clients
silently. A source key independent of batch/mapping version prevents replay
duplicates. Revised files need human row reconciliation.

Alternatives: mapping Continua to done loses active work; automatic recurrence
invents cadence; copying cached deadline labels perpetuates missing formulas.
Proof: 34 rows, 26 missing dates, 23 active ordinary undated records and
reference-date categories in discovery report. Business owners must confirm
ongoing semantics and contradictory row 34 before real import.
