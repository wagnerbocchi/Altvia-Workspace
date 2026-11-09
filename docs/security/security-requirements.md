# Security requirements and initial RBAC

Status: design contract; controls below require implementation and negative
tests. No security test on a running application occurred in Phase 0.

## Policy model

Deny by default. Evaluate active identity + action permission + resource scope.
For client resources, an explicit client_access_grant is a ceiling. Then a
role_binding for that resource's project/team/queue/client must authorize the
action. Membership/assignment narrows applicable work access; it never grants
cross-client access by itself. Internal projects require explicit project/team
membership and have no fictitious client. A client manager binding can delegate
only within that approved client. A team spanning clients never bypasses ceilings.

Exact precedence for implementation: the client ceiling is always required for
client content. An operations_manager team binding authorizes its allowed actions
across projects/queues owned by that team, without an additional per-project
membership. A project_manager project binding directly authorizes that project's
actions, without an additional member row. Viewer bindings authorize reads at
their explicit scope without assignment requirements. Agent project access
requires both an agent role binding and project membership; membership permits
reads/comments, while task updates/transitions require owner/assignee identity.
Agent queue bindings authorize reads/replies within the queue and client ceiling;
ticket updates require assignment. Claiming an unassigned ticket for self needs
ticket.claim; assigning another agent needs ticket.assign. Assignment never
substitutes for a role binding, client grant or required project membership.
Internal projects apply the same role predicates without the client ceiling.

`platform_admin` may manage identity/configuration without reading customer
content. Reading that content requires the same explicit grants, or a separately
approved and audited emergency grant. Never implement blanket `is_admin` bypass.

| Action | Platform admin | Operations manager | Project manager | Agent | Viewer |
| --- | --- | --- | --- | --- | --- |
| Identity/system/mailbox secrets reference | manage | deny | deny | deny | deny |
| Customer/project/work/ticket content read | explicit content grant | allowed team/client | allowed projects | allowed membership/queue | explicit read scope |
| Client/team/project management | explicit content role | delegated scope | project/member scope only | deny | deny |
| Work create/assign/update/transition | explicit content role | permitted scope | permitted project | assigned/member scope, no grant administration | deny |
| Ticket create/assign/transition/reply | explicit content role | permitted queue/client | only additional queue role | permitted queue/client | deny |
| Internal notes read/write | separate note permission | scoped note grant | scoped note grant | scoped note grant | deny by default |
| Attachments | target + visibility grant | target + visibility grant | target + visibility grant | target + visibility grant | public-to-scope targets only |
| Ticket/work link | authority on both ends | authority on both ends | authority on both ends | authority on both ends | deny |
| SLA/automation changes | explicit scoped role | delegated scope | deny by default | deny | deny |
| Analytics/export | explicit analytics grant | permitted team/client | permitted projects | own My Work only by default | explicit read/export grant |
| Import/raw payload/audit | explicit import/audit role | explicit delegated role | deny | deny | deny |

Public messages mean requester-visible conversation, not anonymous internet
readability. No external login in MVP. A public reply's recipients must be
verified participants of that ticket/client; no arbitrary Reply-To passthrough.
Revalidate permission on writes, workers, linked previews, FTS, counts,
notifications, exports and file streaming. Role/membership revocation takes
effect on subsequent requests, not only next login.

## Trust boundaries and controls

| Threat/boundary | Required control | Verification gate |
| --- | --- | --- |
| BOLA/IDOR, high contextual priority | Policy-filtered lookup and same-client DB/link constraints | For each endpoint, other-client ID read/write/search/link/download denied |
| Privilege escalation | Distinct profile/role APIs; scoped grants, no mass assignment | Self-edit cannot set role/client/scope; deactivated user sessions rejected |
| Password/session theft | Argon2id, opaque revocable session, hashed token, HTTPS cookie, CSRF | Cookie flags/Origin check, wrong password generic, expired/revoked sessions denied |
| Stored XSS in mail/comments | Allowlisted HTML sanitization, text fallback, CSP, block remote resources | Script/event/data URL/SVG payloads cannot execute or exfiltrate |
| File exfiltration/traversal/malware | Quarantine, private opaque keys, bounded streaming, MIME sniff/type list, scanner fail-closed | Hidden note attachment and guessed key denied; archive bomb/oversize blocked |
| Email spoof/correlation | Trusted MTA authentication evidence + identity/client/thread checks, quarantine uncertainty | Forged Message-ID/From/subject/References cannot append to foreign ticket |
| SSRF/command/SQL injection | Parameterized SQL, fixed adapters, restricted egress, no URL fetch from message HTML or automation code | Untrusted URLs/expressions do not trigger network/exec |
| Replay/concurrency | Unique effect keys, outbox/transaction, optimistic versions, graph locks | Concurrent retries produce one effect; stale update 409; cycle race rejected |
| Sensitive logs/backups | Redacted structured logs, encrypted backups, restricted audit access | No password/token/body logs; restore honors private attachment ACL |
| Supply chain/CPU | Lock dependencies, SAST/SCA/secrets/container scans and VM tests | Critical findings or unsupported ISA block release |

Initial upload proposal: 10 MiB per file, 25 MiB raw MIME, <=20 attachments,
PDF/PNG/JPEG/plain text only until reviewed operational needs expand the list.
No active HTML/SVG/executable/archive download allowlist initially. Native image
parsing, MIME sanitizers, Argon2 and malware scanner require CPU homologation.
No scanner chosen in Phase 0. If unavailable, files remain quarantined; public
email attachments are not enabled with a silent scanning bypass.

## Authentication baseline (ADR-0003)

Argon2id proposed initial parameters: memory 64 MiB, iterations 3, parallelism 1;
benchmark on target under bounded login concurrency before ratification. Session
idle timeout 30 min and absolute timeout 12 h are proposed defaults. Cookie name
`__Host-altvia_session`, Secure/HttpOnly/SameSite=Lax, Path=/, no Domain.
Rotate on login/privilege change, revoke on logout/password reset/deactivation.
Passwords never logged, seeded or returned. No public signup. Login rate
controls combine account and source IP, with generic errors and retry policy.
Local access is initial; OIDC/MFA follows an available trusted IdP, not simulated MFA.

## Data protection and operations

Company must approve retention for tickets/raw mail/attachments/audit/backups
before production. No universal LGPD deadline is assumed. Record data inventory,
purpose, minimization, authorized exports, subject request procedure and deletion
holds. Exports neutralize spreadsheet formula prefixes including `= + - @` and
leading control characters. Workbook original_payload is access-restricted data.

Inject secrets by restricted files/secret manager, never Git or ordinary DB
configuration. `.env.example` contains placeholders only. App runtime DB role
cannot migrate schema. Postgres, Redis and storage are not publicly exposed.
Use HTTPS proxy, private networks, non-root apps, volume permissions, limits and
healthchecks. Backup database, attachment manifest/objects and critical config
with encryption and documented key recovery. Prove consistent restore in isolation.

CI requires build/lint/typecheck, relevant unit/integration/E2E/security tests,
SAST, SCA, secret and image scans; critical untriaged issues block release.
Direct main push authorization does not waive these gates or production approval.
Audit records identity/action/resource/correlation with allowlisted diffs,
append-only permissions and restricted reads. Application append-only logs are
not claimed cryptographically tamper-proof; off-host retention is a production decision.
