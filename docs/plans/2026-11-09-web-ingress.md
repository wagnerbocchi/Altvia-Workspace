# Foundation web ingress implementation plan

Execute inline under standing development/main-push authorization. Contract:
ADR-0014; incumbent PRODUCT.md/DESIGN.md and browser behavior in ADR-0008.

1. Package existing Next app with standalone output. Add infra/web.Dockerfile,
   explicit .dockerignore source allowlist and scripts/check_web_runtime.mjs.
   Verify actual Linux build, traced file layout, native versions and Sharp
   absence. No visible UI changes or new dependency versions.
2. Extend infra/compose.yaml with bounded credential-free web and DNS-resolving
   same-origin ingress. Extend scripts/container_smoke.py for all four images,
   canaries, non-root/read-only/isolation, HTTP/document/native/stop acceptance.
3. Add scripts/container_browser.mjs with guarded synthetic credentials over
   stdin, certificate public-key pin and reserved test-host resolution. Prove
   login, focus, assets/hydration/CSP, session after web recreation, CSRF/Origin,
   logout and desktop/mobile light/dark accessibility/screenshots. Run through
   real Compose, never a new fake gateway or mocked identity endpoint.
4. Include web in existing all-service image scanning. Keep API/browser existing
   gates. Extend hosted container CI to install Chromium and retain only synthetic
   screenshots for inspection. One fresh read-only final review, confirm/fix real
   findings, execute all relevant gates, commit/push and record exact evidence.

Stop when real frontend/API identity works through the actual packaged HTTPS
stack and all image/runtime tests pass. No domain features, idle worker or Redis
without a consumer. Actual VM/CPU, load/production backups and rollout remain open.
