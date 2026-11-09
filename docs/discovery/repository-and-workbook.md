# Discovery and workbook reconciliation

Analysis date: 2026-11-08, America/Sao_Paulo. Classification: internal.

## Repository and tools

The workspace initially contained only `.git`, an unborn `master`, no tracked
files, no commits and no remote. No application, tests, CI, migrations, dependency
lockfiles or repository instructions existed on disk. The global instructions
provided in chat were applied. The user subsequently selected
`https://github.com/wagnerbocchi/Altvia-Workspace.git`: `git ls-remote` succeeded
with no refs. Origin now points to that repository. Work targets `main`, per
the user's explicit subsequent authorization to push without PR.

Available bundled tooling observed: Python 3.12.14, Node v24.22.1 and Git
2.56.0.windows.1. `docker` was not found by `Get-Command`. Local OS is Windows;
this workstation is not evidence about the Ubuntu guest's instruction set.
No target hostname, authenticated SSH channel or target runtime evidence was supplied.

## Provenance and method

The master specification v1.1, dated 2026-11-06, was read in full (544 lines).
It was copied byte-for-byte to the repository root, SHA-256
`2c94b7773d1c5442c897377a83de25920ce078d6f5bb021b7c08660721191dc5`.

The XLSX is 30,257 bytes, SHA-256
`679aea3bdb41cd9cebbc3f9144470ca77fcd236b6136234c3ffeb658b8694013`.
It was read without modification using the bundled Python standard library:
ZIP package, workbook relationships, all shared strings, all populated cells in
both worksheets, styles/date formats, shared formulas and caches, validations,
filter, notes, weekly updates and summary precedents. A local private copy lives
in `data/sources/Acompanhamento_Atividades_Altvia_Nov2026.xlsx`; it is excluded
from Git. Extracted raw inventory is temporary and is not a public deliverable.
No Excel engine recalculation or visual workbook redesign was performed.

The worksheet XML omits `dimension`. Bounds inferred from populated cells are
`Acompanhamento!A1:N35` and `Resumo!A1:H16`, as described by the specification.
Two sheets, both visible. No merged cells, VBA or external-workbook links were
found. There are comment/threaded-comment, drawing, person and document-task
parts. G1's note instructs the user to enter DD/MM/AAAA; it is source metadata,
not execution authorization. Data contains operational incident/client details.

## Verified totals

| Dimension | Observed |
| --- | --- |
| Activities | 34, rows 2 through 35, all with owner/title/status/priority |
| Status | Em andamento 14; Aguardando terceiros 8; A fazer 7; Concluido 4; Continua 1 |
| Priority | Media 21; Alta 9; Critica 2; Baixa 2 |
| Owners | Neto 6; Rodolfo 7; Luiz Paulo 5; Eduardo Belmonte 3; Alexandre Violante 6; Wagner Bocchi 7 |
| Deadline physically populated | 8 |
| Deadline physically absent | 26 |
| Saved deadline labels | Sem prazo 20; Concluido 4; Continua 1; Vence em breve 2; No prazo 4; blank 3 |
| Saved overdue | 0 |
| Notes J | 8 nonempty cells, rows 8,10,11,14,15,21,25,34 |
| Weekly updates | K: 16 nonempty; L/M/N: 1 each, all at row 34; 19 updates total |
| Involved people E | 4 blank cells: rows 15,19,23,27 |

Portuguese labels above use ASCII for compact documentation; exact accents and
trailing whitespace remain in the unchanged source. In particular K1 and N1
end in a space. No source text is normalized destructively.

## Formula and summary defects

There are 61 formula cells in Acompanhamento (including shared followers),
not just the 6 shared-formula anchors. H/I are missing at rows 5,6,12;
H35 is missing while I35 exists. Therefore saved `Sem prazo=20` excludes three
ordinary undated activities. Summary H counts I labels, not blank G dates.
Of 26 absent G dates, 2 are completed and 1 is continuous. Thus active ordinary
work without deadline is **23**, while all records without a deadline total **26**.
These are different metrics and must be named separately in the dashboard.

The 49 Resumo formulas include 42 owner-specific COUNTIF/COUNTIFS cells and
7 shared SUM total cells. Status columns C:F total 33 because continuous work
has no dedicated summary column. Owner totals still total 34. No work is missing
from the source. Full-column formulas include row 35; the autofilter does not:
`$A$1:$J$34` omits the final activity and all weekly columns K:N.

The weekday data is sparse. H/I caches reflect a reference consistent with
2026-11-06 (e.g. two live dates have zero remaining days), but a complete save
timestamp is not established. Do not present this inference as a verified
time of edit. Most summary values depend on cached deadline labels.

Formula semantics from anchors: completed/continuous records bypass deadline
arithmetic, otherwise blank G means no deadline; date before TODAY means overdue;
0 through 3 calendar days means due soon. Formula strings were inspected,
including shared ranges. No formula error cells were observed in saved data.

## Dates and explicit recalculation

The workbook uses the default 1900 date system (`date1904` absent). Date formats
164/166 are `dd/mm/yyyy` and `d/m/yyyy`. Serials were decoded against 1899-12-30
for these modern dates. All eight values are whole-day dates, not known instants.

| Source row | Serial | Local calendar date | Source state | Category at 2026-11-08 |
| --- | --- | --- | --- | --- |
| 2 | 46330 | 2026-11-04 | done | completed |
| 7 | 46329 | 2026-11-03 | done | completed |
| 9 | 46332 | 2026-11-06 | in_progress | overdue |
| 20 | 46332 | 2026-11-06 | in_progress | overdue |
| 22 | 46339 | 2026-11-13 | todo | on_track |
| 25 | 46356 | 2026-11-30 | blocked | on_track |
| 27 | 46336 | 2026-11-10 | in_progress | due_soon |
| 28 | 46346 | 2026-11-20 | in_progress | on_track |

Independent domain calculation at fixed reference date 2026-11-08 in
America/Sao_Paulo gives completed 4, ongoing 1, no_due_date 23, overdue 2,
due_soon 1 and on_track 3, totaling 34. At 2026-11-06 the same rules give
overdue 0, due_soon 2, on_track 4. This was a calculation from raw dates/states,
not execution of Excel's TODAY() engine. Original caches are preserved.

## Validations and ambiguity inventory

- E2:E40 list: Fabio, Eduardo, Rodolfo, Neto, Wagner, Alexandre, Luiz, Terceiro.
  Existing cells also contain comma-separated multiple names. Do not interpret
  the validation as proof of a single assignee or authoritative user directory.
- F2:F40 and E41:F84 use the status list, including Bloqueado and Continua.
  The range E41:F84 applies a status validation to the people column too.
  Bloqueado is allowed but has no actual row in this file.
- D2:D84 validates four priorities. G2:G84 allows dates greater than 36526.
  Allowing blank dates is intentional. There are 9 conditional-format blocks.
- Short aliases Eduardo/Luiz/Wagner/Alexandre cannot silently provision accounts.
  Fabio is a participant without an owner row. Terceiro is an external-party
  marker, not an internal user or a specific external contact.
- Row 32 is continuous and has no completion timestamp. ADR-0006 proposes
  `work_type=ongoing`, with active status and no generated recurrence schedule.
- Row 34 says completed but its note and weeks 2-4 say recurring. Preserve done
  as source fact and flag semantic conflict for owner review. Never generate
  future instances or infer a historical completion instant.
- Weekly updates report narrative progress that can differ from the status.
  Preserve both, without an inferred exact timestamp, date or author.
- One update mentions OpenSearch and tests in another project. It is historical
  text, not a dependency instruction or proof that Altvia tests have run.

There are 29 distinct `Frente / Cliente` strings. Every entry below requires
classification in a versioned mapping; none is an approved client/project ID.

| Exact source label | Rows | Review concern |
| --- | --- | --- |
| Seguranca / Incidentes | 2 | Operational area; incident scope unknown |
| Unimed Marilia (Oracle) | 3,4 | Separate client from technology/project |
| Unimed Bandeirantes (Oracle) | 5 | Compare alias UN Bandeirantes |
| Altvia Cloud (infra e redes) | 6 | Internal service versus project |
| Unimed Tupa | 7 | Client candidate |
| Redes / OpenStack | 8 | Area and technology mixed |
| Redes | 9 | Area candidate |
| OpenStack | 10,11 | Project or platform |
| Onapp/ OpenStack | 12 | Migration project candidate |
| Acessos | 13 | Area candidate |
| Seguranca (alerta geral) | 14 | Area and broad scope |
| Backups | 15 | Area/service candidate |
| Altvia | 16 | Internal work candidate |
| Governanca | 17 | Area candidate |
| Superfin / Altvia | 18 | Multiple organizations; no automatic cross-client grant |
| Unimed Marilia | 19 | Compare Oracle-specific label |
| IA DPO | 20 | Project/client needs confirmation |
| WeAI | 21 | Project/client needs confirmation |
| Honda | 22 | Client candidate |
| UN Bandeirantes | 23,24 | Alias requires approval |
| B3 | 25,26 | Client candidate |
| Monitoramento | 27,28 | Area/service candidate |
| Unimed Nacional (CNU) | 29 | Client candidate |
| Eduvalle | 30 | Client candidate |
| Bravvius | 31 | Client candidate |
| Unimar | 32 | Client candidate; continuous work |
| Sigmaward (SIEM/SOAR) | 33 | Separate project; no runtime inheritance |
| Seguranca | 34 | Area; recurring wording conflicts with done |
| Servidor Wazuh | 35 | Asset/project label, client named in title |

Accents are elided in this mapping inventory only. The real import mapping must
use exact original strings and retain raw values alongside normalized lookups.

## Import contract, not an importer

Stage immutable source hash/sheet/row/raw payload and mapping version. Dry-run
must produce all 34 dispositions, 19 weekly-update dispositions, 8 note
dispositions, identity mappings, scope mappings and the reconciliation above.
No silent user creation, client merge, deadline fill, ticket invention or recurrence.
Hash + sheet + row identifies a source record; a new mapping revises resolution
of that same row instead of creating a duplicate task. Batch ID is not the
deduplication key. Changed workbooks require explicit reconciliation against
previous imports because a row number alone is not a durable business key.

Commit only an approved logical batch in one database transaction. Lock the
batch and enforce uniqueness for concurrent retries. Persist original dates
with precision `date`, timezone and conversion policy. UTC due_at is derived
from the start of the following local day as an exclusive deadline, not an
invented midnight start deadline. Imported status may be done while historical
completed_at is unknown; mark provenance rather than invent a timestamp.
Raw workbook/payload is restricted data with retention/access audit. A batch
rollback must reference created resource IDs, reject overwriting subsequent
edits, and require explicit authorization before destructive reversal.
