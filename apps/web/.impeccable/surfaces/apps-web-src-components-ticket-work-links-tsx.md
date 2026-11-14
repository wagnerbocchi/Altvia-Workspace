---
version: 1
slug: "apps-web-src-components-ticket-work-links-tsx"
primary_target: "apps/web/src/components/ticket-work/links.tsx"
related_targets: ["apps/web/src/components/tickets/detail.tsx","apps/web/src/components/work-items/detail.tsx"]
---

# Ticket and work relationships

Mode: Operate. Scoped extension of ticket and work detail under ADR-0039,
preserving the user-selected Twenty-inspired workspace of 2026-11-12.

## Direction contract

THESIS: Operators deliberately connect existing records of the same client while
keeping their states, people and deadlines independent.
OWN-WORLD: Inherit the offwhite sidebar, continuous white content, gray rules,
system typography and restrained blue actions. Dark mode uses the incumbent
neutral charcoal equivalents. No new tokens, CSS, imagery or global destination.
STORY: Scan permitted relationships, search eligible work from a ticket, review
both current records, confirm, and consult authoritative reciprocal results.
FIRST VIEWPORT: Preserve the record heading and data. The relationship section
follows record data and precedes lifecycle actions. Inline review names both
records and their separate states. Native pagers and named actions wrap on mobile.
FORM: Code-led extension of the pinned Twenty direction. Reuse the existing
record rows, facts grid, confirmation treatment and write recovery. The signature
interaction is the focused paired review followed by explicit confirmation.
FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance

## Interaction and privacy

Only current authorized results appear; no total or hidden-counterpart metadata
is inferred. Work detail offers reciprocal consultation and removal, and directs
new linking to ticket detail. Search and relationship pages remain independent.

Review blocks ordinary record writes, including each file picker. Parent-owned
editing blocks new relationship review without disabling relationship recovery.
Uncertain writes retain the exact pair, both reviewed versions and request key.
A confirmed write with failed refresh retains only a session-owned pair intent;
its recovery retries reads of both records and relationship lists. It never sends
the confirmed mutation again. The panel hides stale relationship information
while acknowledgement is pending. A denied parent keeps only generic recovery
and removes its cached content. Session replacement disposes private intent.

## Evidence and documentation scope

GREEN04 captures cover empty, paired review, linked, reciprocal removal review,
uncertain removal, acknowledged parent denial and list read error. Every state
has 1440px desktop and 390px mobile captures in light and dark themes. The builder
opened all 28 files individually: no blank or incorrect state, clipped controls,
or horizontal overflow was observed; long literal titles wrap and states remain
separately labeled. Axe WCAG2A/AA/2.1AA and keyboard review, cancel and recovery
checks pass in the focused 17-test run. Runtime and archive provenance remain in
the private Task3 report; these observations do not imply packaged qualification.

Documentation was completed inline using Impeccable's degraded documenter role.
The implementation reuses root DESIGN.md, .impeccable/design.json and the existing
styles without a system change. Pre-existing DESIGN/sidecar freshness drift is
disclosed and left untouched. There is no shipping raster, new comp, seed or
QUALITY BAR board for this extension. Root owns independent source and visual
finish review and the resulting disposition; builder inspection is not that
independent verdict.
