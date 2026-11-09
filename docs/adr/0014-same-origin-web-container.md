# ADR-0014: Same-origin immutable frontend runtime

Date: 2026-11-09. Status: implemented and development-validated on465a85b.
Actual Docker/browser/security acceptance passed; see docs/phase-1c-evidence.md.
Real target-VM homologation and production readiness remain open.
Extends ADR-0008/0011/0013 within Foundation. No Phase2 advancement.

## Intent and ownership

Serve the existing real browser login/account/logout through the same Compose
HTTPS edge as the API. Today that edge returns404 for pages and the browser tests
use a development gateway. Preserve the incumbent Impeccable visual world and all
identity/error/accessibility behavior. No new UI controls, business module, SSR
identity cache, BFF, server action or second authorization implementation.

Next standalone output owns the web process. The edge routes /api/v1/ to FastAPI
and page/static requests to web. No API, database or web host port is published.
Web receives no database/TLS/owner credentials, runs non-root/read-only with
dropped capabilities, no-new-privileges, bounded resources and temporary /tmp.
Keep nonce-based dynamic document CSP, no-store private documents, secure cookies,
exact Origin/CSRF and generated contracts. Strip client forwarding headers and
set only the edge's HTTPS/Host values. Container DNS refresh covers web recreation.
Static assets retain Next's own cache semantics; no shared identity caching.

## Images and native compatibility

Use the official pinned Node24 Alpine builder and locked pnpm11.25.0 dependency
graph. Copy only standalone server/traced dependencies and built static assets
to a pinned Alpine runtime with the signed vendor Node24 LTS package. Alpine
shares zlib, Brotli, OpenSSL, SQLite and other native libraries, making vendor
patch provenance explicit rather than relying on older embedded copies in a
generic Node image. No npm/yarn/corepack/developer tools in the final service.
Vendor nodejs24.22.1-r1 includes downstream fixes; builder Node24.22.2 is the same
supported major/module ABI. Required native paths need functional validation.

Rejected alternatives: static export cannot preserve nonce/dynamic document
semantics; the development gateway is not a deployment ingress; stock Node24.21
retains vulnerable global installer/embedded dependencies; distroless Node24
retains34 medium/12 low Debian occurrences without vendor fixes. Reuse the signed
Alpine package model already established by ADR-0013, without private Node builds.

Keep Sharp excluded and optimization unavailable. Inspect the actual final
dependency tree and native runtime versions. All required artifacts must support
x86-64-v1; no -march=native or new higher-ISA requirement. Modern builds/scans
do not homologate the unavailable VM. Q-01 remains a hard Phase1 exit gate.

## Proof and rollback

Extend the existing synthetic guarded Compose flow. Assert web isolation,
non-root/read-only/capability bounds, secret-canary exclusion, final native guard,
root document headers/static assets and no Sharp route. Run a real Chromium
login/reload/logout through the actual HTTPS edge, preserve the session across
web recreation, reject CSRF/Origin attacks and check desktop/mobile themes/axe.
The browser accepts only the test certificate's public-key pin; independent
HTTP probes validate its CA and domain SAN. No global certificate/trust changes.
Store only synthetic screenshots, never credentials or browser cookies.

Install full ICU data so the runtime preserves pt-BR formatting support rather
than silently falling back to English. The locale capability is checked natively.
Next16.4.5 explicitly closes HTTP/Next resources then exits143 on SIGTERM. Preserve
that documented source behavior; reject OOM/forced137 and other unexpected exits.

Scan web alongside the other three actual images with the same DB and existing
blocking HIGH/CRITICAL policy; retain all severities. Verify graceful stop and
existing API/DB recovery/ACL behavior. No schema or volume migration. Rollback
selects the previous compatible application images/configuration, preserving
PostgreSQL's existing family marker and volumes. No real deployment authorized.
