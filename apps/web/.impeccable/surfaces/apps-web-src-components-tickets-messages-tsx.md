---
version: 1
slug: "apps-web-src-components-tickets-messages-tsx"
primary_target: "apps/web/src/components/tickets/messages.tsx"
related_targets: ["apps/web/src/components/tickets/detail.tsx"]
---

# Public response drafts

Mode Operate. Local extension of ticket detail under ADR-0034. The user opted
out of further design questions; preserve the incumbent visual world and flow.

## Direction contract

THESIS Operators review and save a public response draft with an explicit unsent
state, independently of private ticket notes and ticket lifecycle.
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
No transport, recipient, sender proof, note conversion, new assets or tokens.
FINISH Real PostgreSQL/API browser evidence: persisted escaped text, explicit
keyboard review, independence from notes, scoped read-only states, ordered pages,
uncertain and acknowledged recovery, axe and desktop/mobile light/dark captures.
Finish with a fresh review and documentation of incumbent-system consistency.
