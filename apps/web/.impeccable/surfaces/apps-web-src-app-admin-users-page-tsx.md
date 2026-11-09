---
version: 1
slug: "apps-web-src-app-admin-users-page-tsx"
primary_target: "apps/web/src/app/admin/users/page.tsx"
related_targets: ["apps/web/src/app/admin/users/[userId]/page.tsx"]
---

## Scope

Operate. Extend the existing linked identity administration pages with account
directory/detail routes. Portuguese, real persisted data, no redesign or assets.

## Direction contract

THESIS: Review one named account before changing its access. Refuse decorative
counts and a crowded all-account editing grid.

OWN-WORLD: Preserve navy wayfinding, cool ground, flat bordered working plane,
system sans and existing semantic focus/error/action tokens. Office use at desktop
and on mobile; keep both user-selected light and dark themes.

STORY: Find/create account, review active state and global role, then manage
credentials or explicit team read grants. Team membership never grants access.

FIRST VIEWPORT: Back link, account heading/email/state, then identity and security
controls in separated sections. Directory puts a compact labeled new-account form
above bounded account rows. Detail separates sensitive controls from scoped roles;
desktop pairs existing grants and team choice, mobile stacks them. Inline named
confirmations and explicit uncertain-result verification own the interaction.

FORM: Code-led local extension of incumbent linked directory/detail composition.
Routine layout decisions delegated by user; no open visual-world/concept round.

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance

## Constraints

ADR-0016 authoritative. Passwords only in uncontrolled inputs/private intent refs;
no password in render state, mutation variables, storage, URLs, SSR or logs. No
automatic retry. Preserve uncertain original intent across independent read
recovery. Bound paging and fence callbacks to current session. Inline confirmation
warns of session revocation, with actionable last-admin refusal. No design-system
change. Existing provisional branding and pre-existing sidecar drift remain.
