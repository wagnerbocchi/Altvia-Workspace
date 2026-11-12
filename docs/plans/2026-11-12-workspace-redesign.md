# Altvia Workspace visual redesign

## User direction and scope

The user explicitly requested a visual redesign of the whole Altvia Workspace
and selected Twenty CRM as the visual reference on2026-11-12. This supersedes the
prior stop-before-design boundary. Use Impeccable in Operate mode. The public
Twenty product page (https://twenty.com/product) was visually inspected for its
neutral surfaces, compact navigation, fine rules, restrained state color and
aligned operational content. Product marketing, AI and CRM-specific capabilities
are not Altvia requirements. Do not copy Twenty branding, assets or source code.

This is a replacement visual world across all26 existing routes, not completion
of the remaining MVP features. Private-file Task4 remains unimplemented and is
separate from this redesign. Do not add placeholder navigation to pending SLA,
analytics, automation, import or unified ticket/task features.

The user-selected reference overrides the exploratory Impeccable roll
seed:fb00f7b692af0efa. Build code-led, the Operate path selected by Impeccable.
No alternate visual-world tournament is needed after the explicit reference.
The existing backend/API/session/resource authority contracts stay unchanged.

## Design contract

Audience: internal support staff and managers performing repeated desktop work
in ordinary office lighting, with mobile access and optional dark mode.
Success: navigation is always easy to find; the current record and next action
are clear; lists fit useful information without shrinking text or touch targets.

- Replace the large navy masthead and isolated admin planes with a quiet neutral
  workspace shell, compact sidebar, clear current route and generous content area.
- Use existing system sans, a restrained scale, neutral light/dark surfaces,
  subtle dividers, consistent radii and semantic focus/error/selection states.
- Align operational information into readable rows/columns where its real data
  supports them. Preserve list semantics on narrow screens; never hide essential
  status, ownership, scope, uncertainty or recovery actions just to fit.
- Signature: the current navigation item and record heading share a calm context
  treatment; metadata stays aligned while the record text is free to wrap.
- Show real status words and scope. Preserve public-response/private-note
  separation and explicit review before writes/sends. No invented badges/counts.
- Desktop navigation may be compact; mobile navigation is an explicitly named
  accessible control with visible focus, appropriate expanded state, Escape and
  predictable focus recovery. Avoid new persistence for private UI state.
- Reuse native fields and installed Lucide icons. No remote fonts, new native
  dependencies, decorative imagery, mandatory motion or costly runtime effects.
- Preserve functionality and supported keyboard/accessibility behavior; no
  API/schema/security/permission changes are part of the visual redesign.

## Coverage inventory

| Family | Existing routes |
| --- | --- |
| Identity | `/` including login/account/access/error states |
| Work | `/my-work`, `/work-items/[id]`, `/projects/[id]/work` including Kanban |
| Clients | `/clients`, `/clients/[id]`, `/clients/[id]/contacts`, `/clients/[id]/contacts/[contactId]` |
| Projects | `/projects`, `/projects/[id]`, `/projects/[id]/members`, `/projects/[id]/milestones`, `/projects/[id]/milestones/[milestoneId]`, `/operational-areas` |
| Tickets | `/service-desk/tickets`, `/service-desk/tickets/new`, `/service-desk/tickets/[id]` |
| Incoming mail | `/service-desk/mail-cases`, `/service-desk/mail-cases/[id]` |
| Queues | `/service-desk/queues`, `/service-desk/queues/[id]`, `/service-desk/queues/[id]/members` |
| Identity administration | `/admin/teams`, `/admin/teams/[teamId]`, `/admin/users`, `/admin/users/[userId]` |

## Global constraints

- Main commits and direct pushes are authorized; no PR. No production or target
  operation, imports, destructive data action or SSH/security change.
- Follow AGENTS.md, master requirements and affected UI/domain contracts. Keep
  module boundaries, current action authority and client ceilings intact.
- Session recovery, hidden/inert private content, capability visibility, scoped
  query caches, original-intent receipts and reviewed versions must survive.
- No runtime copy may claim pending features are implemented. Preserve user
  supplied commands, evidence and deliberate safety/recovery explanations.
- Inspect existing Git changes. One implementer at a time. No source/fixture/build
  mutations during active test runs. Preserve all failure records.
- Keep x86-64-v1/dependency restrictions. No new server homologation per slice.

### Task 1: Complete the shared redesign and existing route coverage

**Files:** apps/web/src/app/globals.css; existing workspace-session/identity owners;
small shared shell/navigation components if responsibility merits them; affected
existing domain components only for real layout/semantics; browser tests and
synthetic capture setup. No backend runtime change.

**Consumes:** Existing authenticated session/capabilities,26 routes, real domain
UI and generated API types. **Produces:** consistent replacement visual system,
working responsive navigation and full existing functionality.

- Read Impeccable context/relevant surface briefs, new-work, mode-operate and
  craft-floor. Inspect current screenshots against CSS and the official Twenty
  product reference. Write the root surface direction before UI changes.
- Trace IdentityBoundary/session lifetime and capability visibility before
  extending the shell. Place navigation at its owning layer without duplicating
  auth state or adding a second private QueryClient.
- RED browser behavior for authenticated navigation, current-route semantics,
  mobile expansion/Escape/focus, and permission/session boundaries. Use actual
  current API fixtures. Do not test an implementation by restating its CSS.
- Implement the neutral Twenty-inspired system across all route families.
  Avoid merely recoloring the old isolated cards. Adapt directory/detail/forms,
  state badges, field groups, pagination and Kanban in their existing owners.
- Preserve native form semantics, explicit protected review/recovery, public vs
  internal boundaries and inactive/read-only access. Keep type readable and
  controls usable at320/390px; content may scroll only in a clearly labeled
  bounded region when the task needs it (for example Kanban).
- GREEN targeted navigation/session/affected cases; lint/types/build and repeated
  generated-contract equality. Then full existing browser suite once on frozen
  source. Read all failures before fixes; repeat only affected evidence afterward.
- Batch actual rendered checks, desktop1440px and mobile390px in light/dark,
  plus320px overflow and representative keyboard/axe/error/empty/long-content
  cases. Save named screenshots and a route coverage matrix; distinguish routes
  actually rendered from those only inheriting shared CSS or passing tests.
- Run Impeccable detect once on changed targets after final render inspection;
  retain findings. Root handles independent visual/source reviews and documenter.
- Commit coherent tested implementation batches. Report exact commands/results,
  hashes, screenshots, coverage and limitations; no push from the implementer.

### Task 2: Independent review, durable design system and publication

**Consumes:** Task1 source/evidence/render matrix. **Produces:** reviewed design,
DESIGN.md and .impeccable/design.json reflecting actual code, source review and
accepted validation/publication evidence.

- Root inspects actual screenshots and source evidence. Dispatch independent
  Impeccable finish reviewer with the user-selected Twenty direction and required
  screenshot matrix, and independent task source/spec review. No inherited history.
- Resolve material findings, verify affected behavior and recapture changed
  surfaces. Reuse unchanged passing evidence. Do not claim checks not executed.
- Dispatch Impeccable documenter with write access only to design docs/sidecar and
  relevant surface briefs. Record actual tokens and new world, not old promises.
- Update roadmap/continuous plan/coverage evidence accurately. Commit and publish
  directly to main, then inspect the required hosted gates and their actual logs.
- Final report distinguishes visual redesign from unfinished file UI/MVP features
  and deferred target qualification. No whole-MVP completion claim.
