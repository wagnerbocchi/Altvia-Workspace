---
version: 1
slug: "apps-web-src-app-admin-users-page-tsx"
primary_target: "apps/web/src/app/admin/users/page.tsx"
related_targets: ["apps/web/src/app/admin/users/[userId]/page.tsx"]
---

## Scope

Operate. Extend the existing linked identity administration pages with account
directory/detail routes. Portuguese, real persisted data, and the shared neutral
workspace system; no route-specific world or assets.

## Direction contract

THESIS: Review one named account before changing its access. Refuse decorative
counts and a crowded all-account editing grid.

OWN-WORLD: Offwhite sidebar, continuous white working field, gray hairlines, system sans,
restrained blue actions, soft semantic state chips and native labeled fields.
Dark mode uses neutral charcoal equivalents. Inherit the shared operational
track, responsive navigation and visible focus recorded in root DESIGN.md.

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
warns of session revocation, with actionable last-admin refusal. The shared
2026-11-12 redesign sets visual tokens; this account flow adds no separate world.

## Foundation activity extension

ADR-0017 adds a recent administrative-history section below the existing account
list in the same flat plane. Preserve the complete directory/detail system. Use
real cursor-paged activity, semantic action labels, real timestamps, resource and
actor identifiers with wrapping text, local refresh/error/empty states. No metrics,
ornament, new palette, assets or new visual world. Ordinary identity users never
mount this section. History read recovery remains independent of credential
intent recovery; session replacement disposes both. Review desktop/mobile in
both themes and verify full-page overflow with the longer directory.
