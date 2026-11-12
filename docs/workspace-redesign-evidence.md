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

The first publication is c60bf177c84defceeae64a899d1c542b86ea1f62. Source security
and image security passed: 22 LOW SAST findings, zero blocking findings, zero
secrets and zero vulnerabilities in all seven scanned images. API checks passed
1198 cases, with three explicitly guarded native ClamAV checks skipped and one
Pydantic field-alias warning; the required real-S3 gate confirmed 37 passing cases.
The separate private-file container job also passed. This publication is not
accepted yet:

- Browser run 43312139697: 160 passed, one failed. The new administration
  navigation case's login received HTTP 429 after earlier full-suite logins.
- Container run 43312140056: api-runtime failed at the packaged browser child
  after the preceding packaged persistence/mail/search checks passed. The child
  still uses account navigation links without opening the new mobile disclosure.
  The hosted log retains the child exit, not its private locator diagnostic;
  exact reproduction and correction are required before claiming that cause.

The failed runs and complete available logs are retained. These failures require
test-flow/isolation correction and renewed hosted proof; they are not hidden by
the earlier local passing results. The final corrected publication remains
pending at this checkpoint. Production authentication limits must not be
weakened to make a test pass.

The failed publication's 21 downloaded evidence files, including all six full
job logs and four digest-verified artifacts, are retained in
ci-c60bf17-failed.zip: 457663 bytes, SHA256
5a97fb1e572b395eb20e6d1c20dd0a88b938065d79b4afcb13c430c5f00b0790.
The archive additionally contains its verified manifest. CI runner action/Node
deprecation warnings are retained separately from test failures.

## Hosted-proof correction

Commit 2e8b94d changes only browser tests, the synthetic fixture and the packaged
browser proof. It opens the named mobile disclosure for four shared destinations.
The actual stale first click was reproduced against the real local application.
The complete dynamically extracted packaged UI body then passed in 27.2 seconds,
including teams, accounts, clients, contacts, projects, areas, tasks, subtasks,
comments, board, accessibility and logout. The TLS/CSP/CSRF/recreation prelude is
unchanged and still requires the full packaged hosted run.

The new navigation case had introduced the ninth shared-admin login within a
600-second fixed window. One real authenticated seed session now replaces the
separate account-visual and navigation setups. The total returns to eight; no
account, grant, production limit, clock, retry or sleep was added. A deterministic
probe confirmed eight accepted logins, ninth HTTP 429 and continued auth/me 200
for the seeded session. That probe plus navigation passed eight cases. The
affected administration/visual/team/navigation suite passed 30 cases in 1.4
minutes, including last-admin refusal and session replacement. Lint/types,
JavaScript syntax and Ruff passed; default discovery remains 161 functional cases.

Temporary diagnostic probes were archived and removed from normal discovery.
The controller verified all four proof files stayed frozen during the final
affected run. Task containers, forwards and listeners were cleaned up. Runtime
UI/API/design source is unchanged, so existing render and visual review evidence
remains applicable. Final corrected hosted acceptance is still pending here.

Independent scoped source review approved 2e8b94d with no actionable finding,
confirming session ownership, unchanged authentication controls, preserved proof
assertions and the complete mobile navigation migration.
