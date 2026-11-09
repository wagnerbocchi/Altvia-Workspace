# Team administration browser implementation plan

Execute inline. User authorizes incremental development and direct main pushes.
Base adad11e. Spec: ADR-0015; inherited PRODUCT.md/DESIGN.md; Impeccable surface brief.

1. Add guarded synthetic admin/account fixtures and actual-browser acceptance
   tests first; prove the new team route is absent. Enable focused Playwright
   arguments in the existing harness. Use a task-owned PostgreSQL and one local
   Podman-VM SSH forwarding connection when host port forwarding is unavailable.
2. Extend the existing HTTP transport and generated team DTO client. Extract
   shared identity framing and isolate private query caches by session lifecycle,
   including late-response fencing. Preserve the existing seven identity tests.
3. Implement linked team list/create and detail/roster/account selection using
   native forms and inherited tokens. Add bounded cursor paging, explicit
   confirmations, original-intent POST verification and reviewed-version writes.
4. Run actual focused/full browser and API/type/build/contract checks. Review
   source independently and render desktop/mobile light/dark/edge states with
   Impeccable finish review/documentation. Fix confirmed issues, then build/scan
   actual images and run full hosted Compose/security/browser/API gates.
5. Commit coherent batches, push main and record exact results/limitations.

Review focus: late private responses across sessions; unknown POST outcomes and
historical replays; stale roster/detail versions; form preservation on focus/error;
inactive/duplicate/long/HTML-like names; cursor bounds and denied deep links.

Stop after a real persisted team/roster workflow passes. No HTTP account/role
mutation, Phase2 business module, real import or production rollout. Q-01 remains.

## Completion evidence

Contract e9cfe74 preceded implementation 960cd7d. Source recovery/concurrency
findings were fixed with browser regressions; independent follow-ups cleared the
targeted fixes. Impeccable finish disposition ship and documentation comparison
completed without changing the incumbent visual system. Test-only CI correction
ba8c937 passed all four hosted gates: 244 API tests, 21 real browser tests, actual
packaged Compose/TLS/roster/recovery proof and zero reported image vulnerabilities.
Exact commands, run links, retained evidence and remaining Phase 1 gates are in
docs/phase-1c-evidence.md, Phase1C-i. This plan's bounded delivery is complete.
