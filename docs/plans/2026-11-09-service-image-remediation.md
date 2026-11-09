# Service image remediation implementation plan

Execute inline under the existing authorization to fix findings and push main.
Base: 2d825e10b673bac7886abb8ee3f6c6a4ac989cf6. Contract: ADR-0013.

1. Reproduce: retain the stock service scans using one Trivy DB. Inspect Essential
   package dependencies, Alpine package fixes, musllinux wheel availability and
   gosu source checksums. Independent pre-patch investigation is complete.
2. Correct installed images at their owning Dockerfiles. Change the API package
   absence check to apk. Build all images and prove actual native imports and
   untrimmed-builder rejection. Keep application contracts and Compose protections.
3. Extend guarded Compose acceptance to build all service images and perform an
   old Bookworm to fresh Alpine logical PostgreSQL restore with synthetic data.
   Keep old volumes untouched. Add a blocking all-service vulnerability CI job
   with raw reports and image identities, no suppression or unfixed filter.
4. Scan actual built images locally with the original DB. Run focused and required
   lint/build/runtime checks. Obtain one fresh read-only bypass/regression review;
   confirm and address concrete findings, then rerun affected checks.
5. Commit coherent batches and push main. Observe all hosted Linux API, browser,
   container and security gates. Record exact evidence and unresolved Q-01.

No real data migration or production deployment. Continue Phase 1 with the security
enforcement and recovery acceptance above; do not advance to Phase 2 before the
actual target VM gate. Further development follows the remaining Phase 1 backlog.
