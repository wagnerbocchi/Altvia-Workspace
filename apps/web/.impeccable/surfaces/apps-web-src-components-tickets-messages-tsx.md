---
version: 1
slug: "apps-web-src-components-tickets-messages-tsx"
primary_target: "apps/web/src/components/tickets/messages.tsx"
related_targets: ["apps/web/src/components/tickets/detail.tsx"]
---

# Public responses and verified delivery

Mode Operate. Local extension of ticket detail under ADR-0034/0035. The user opted
out of further design questions; preserve the incumbent visual world and flow.

## Direction contract

THESIS Operators review and save a public response draft with an explicit unsent
state, then review the exact saved text, ticket-attested recipient and configured sender before explicit queueing. Private notes remain independent.
OWN-WORLD Inherit navy masthead, flat admin planes, semantic light/dark colors,
native fields, current typography, visible focus and wrapping plain text.
STORY Chronological persisted drafts follow ticket data/lifecycle. A separate
composer becomes an inline review, then saves only the reviewed original intent.
FIRST VIEWPORT Preserve subject/number/state and current operational actions.
Responses precede private notes without moving or blending their content. Mobile
keeps the same stacked order; explicit review is the signature interaction.
FORM Code-led incumbent extension, seed:f6e79c570b8eee00. Reuse record-list,
work-prose, action-row, fields, shared feedback and the single ticket write owner.
Retain body/version/key through uncertain outcomes and focus/failed refresh.
Keep acknowledgement ID and block later mutations until authoritative reads pass.
Delivery uses persisted states, safe failure/uncertainty help and bounded explicit refresh. Retain the frozen review through HTTP uncertainty, lost ownership and acknowledged read failures; session loss removes private state. No note conversion, new assets or tokens.
FINISH Real PostgreSQL/API browser evidence: persisted escaped text, explicit
keyboard review, independence from notes, scoped read-only states, ordered pages,
uncertain and acknowledged recovery, axe and desktop/mobile light/dark captures.
Actual local TLS relay and real worker prove acceptance, rejection and uncertainty without claiming recipient delivery. Finish with a fresh independent review and documentation of incumbent-system consistency. Root owns the visual disposition.
