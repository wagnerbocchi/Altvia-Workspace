# Workspace redesign evidence

Updated 2026-11-12. The user requested a whole-system redesign and selected
Twenty CRM as the visual reference. This replaces the former navy visual system
on the 26 existing routes. It does not complete pending MVP capabilities.

## Scope and ownership

The shared authenticated shell, navigation, light/dark tokens, operational lists,
forms and record sections use neutral surfaces, fine rules and compact aligned
content. Mobile navigation is a named disclosure with keyboard focus recovery.
Existing native controls and Lucide icons are reused; no fonts, raster assets,
native dependencies, backend features or API contracts were added.

The existing identity boundary remains the authentication owner. PrivateSession
retains its private query cache and hidden/inert recovery wrapper; navigation
lives inside that wrapper. Navigation visibility does not grant resource access.
Protected writes, original-intent receipts, reviewed versions and session
recovery remain in their existing owners.

Planning commit: 2b97038. Initial shared shell: 036a99f. Operational lists and
route capture coverage: d66cc81. Reviewed corrections: 0956b32. Local development
and independent reviews are complete; publication/hosted acceptance follows below.

## Local evidence

On frozen d66cc81, the complete behavioral browser suite passed 158 tests in
10.0 minutes, exit 0. The separately executed capture test passed in 28.7 seconds.
Earlier focused runs passed 26 and 16 cases. Lint, TypeScript and production
build passed. Generated OpenAPI/TypeScript files remained byte-identical, and
the native dependency gate passed.

The controller independently verified all 123 source/test hashes stayed equal
during the full run. The complete sanitized log contains 4264 lines and 4093 JSON
events, all INFO. Known Next standalone-launch and NO_COLOR/FORCE_COLOR warnings
remain recorded; passing tests do not imply warning-free output. A comparison of
208 backend, infrastructure and lockfile Git objects against 2b97038 was identical.

The render matrix has 30 route/state entries covering all 26 routes, with 120
captures at 1440px and 390px in light/dark, plus a focused mobile-navigation
capture. Every matrix entry checks 320px horizontal overflow. Login, account,
My Work, Kanban and tickets have axe checks in all four variants. These are real
API/PostgreSQL synthetic fixtures, not runtime mock rows or client imports.

## Independent review and corrections

The Impeccable finish reviewer opened all 121 images. It found one material
layout issue: inconsistent centered desktop content widths across route families.
The source reviewer found two keyboard regressions: the skip link preceded the
shared navigation, and selecting the current mobile destination hid the focused
link. It also identified a validation gap: the default test run included the
capture case, whereas the frozen full run excluded it. This was not a reproduced
CI failure.

Commit 0956b32 fixes all three issues at their shared owners and makes captures
explicitly opt-in with ALTVIA_REDESIGN_CAPTURE=1. Discovery proved 161 functional
tests by default and exactly one capture test when explicitly selected. The
post-fix run passed 47 focused browser cases in 2.1 minutes, including the three
new keyboard regressions and existing protected flows. Lint, types and build
passed. A fresh isolated capture run passed in 30.5 seconds; the controller
verified all 122 final image/coverage hashes. Source stayed frozen across both
post-fix runs. The final Next build ID is NbAmR8ROYWpKqiHRr3-XX.

The source reviewer marked both keyboard findings and the discovery gap
ADDRESSED, with no new blocker. The visual reviewer reopened the 16 captures
directly covering its width finding and scored it resolved, disposition ship.
The initial full visual review plus this scoped verdict is the visual acceptance;
it does not claim independent authorization or interaction testing.

Impeccable context ran once. The user-selected Twenty direction superseded the
exploratory seed. The detector ran once and returned an empty finding list. The
old design system is intentionally superseded; final documentation describes
the corrected implementation before publication.

## Preserved failures and limits

Early local launches failed because Windows Store Python hid the installed
Playwright browser; the project virtual environment resolved the launcher path.
The local runner also needed an absolute scanner-socket path on Windows. An
unused task-local path allowed the worker to start; no scanner operation is
claimed. An initial capture assertion matched Next's route announcer as well as
the intended alert; scoping it to the content region resolved that test defect.
The first keyboard regression run had an accent mismatch in a locator; corrected
cases reproduced all three expected focus failures before product edits.

Initial test discovery also encountered existing fixture-required guards. A
discovery-only invocation with explicitly fake values resolved that command setup;
no browser test used those values. All original failed outputs remain retained.

The full raw runs, failures, reviews, source hashes and capture matrix are retained
under the ignored task workspace and review folder. No credentials or operational
source data belong in Git. Task-owned PostgreSQL/Redis containers and SSH forwards were removed;
no harness listeners remained on ports 3000/3443/8000, and no shared service was
stopped. No target VM homologation, production deployment, private-file UI
completion or whole-MVP completion is claimed.

## Design documentation and retained archives

The shipped Impeccable documenter replaced DESIGN.md and .impeccable/design.json,
then updated 13 superseded surface briefs. The final system records 36 exact
light/dark color tokens, system typography, responsive shared tracks and nine
self-contained component previews. YAML/JSON shape, token equality, component
references, canonical section order and narrative parity passed documentation
checks. The controller independently checked all 36 color values against source,
sidecar schema/components and the canonical sections. No unrelated PRODUCT.md
capability-history repair was included.

Archives are retained at
C:/Users/wagne/.codex/state/evidence/workspace-redesign-0956b32/.
Every archive entry was checked and the local evidence manifest was verified.
The source archive identifies the final runtime commit; documentation is recorded
in the subsequent publication commit.

- source-0956b32.zip: 570 entries, 1395202 bytes, SHA256
  295e4629484ca33bb8d3d393ded364dffe3f967cdd5a8a280efed84ede4d455b.
- reviewed-local-evidence.zip: 373 entries, 15014798 bytes, SHA256
  486dac414b16262156c57310b567a308bdaf9ef592abf30a0c2134510590274e.

## Hosted acceptance

The reviewed code and documentation are ready for the authorized direct-main
publication. The five hosted workflows must be checked on that exact publication
commit; historical green runs do not qualify this redesign. No hosted result is
claimed yet in this checkpoint.
