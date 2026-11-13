# Security requirements and initial RBAC

Status: design contract; controls below require implementation and negative
tests. No security test on a running application occurred in Phase 0.

## Policy model

Deny by default. Evaluate active identity + action permission + resource scope.
For client resources, an explicit client_access_grant is a ceiling. Then a
role_binding for that resource's project/team/queue/client must authorize the
action. Membership/assignment narrows applicable work access; it never grants
cross-client access by itself. Internal projects require explicit project scope
and membership and have no fictitious client. A client manager binding can delegate
only within that approved client. A team spanning clients never bypasses ceilings.

Exact precedence for the implemented project/work domains (ADR-0019/0020): the
client ceiling is always required for customer content. Team metadata roles and
rosters never authorize project/work content. Direct project bindings require a
matching project membership for every role. Inherited client viewer/operations_manager
reads customer projects within the ceiling; operations_manager manages their work.
An explicit project_manager/member pair manages that project's work. Explicit
agent members read/comment/create; task updates/transitions additionally require
owner/assignee identity. Only managers change parent/owner/participants; agent
creation is self-owned and cannot delegate participants. Assignment never supplies
role, ceiling or membership. Viewers read only. Contributor lookup is bounded to
active project contributors; persisted assignment names are resolved only from
those task links, including former contributors. Archived references block new
mutations while permitting authorized reads and already committed receipt replay.
Current authority is checked before exposing a saved receipt. Retained historical
owner/participant links do not prevent independent maintenance; only new links
require active candidates, and former contributors gain no access from history.
403 API tests, 48 browser tests and actual target task/ACL/native/isolation proof
passed for d5ae972. Exact same-ID image scans report zero vulnerabilities in the
recorded snapshot; see docs/phase-2c-work-evidence.md for evidence and limits.
Ticket policy remains a later domain contract:
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
| Customer/project/work/ticket content read | explicit content grant | allowed client/project/queue | allowed projects | allowed membership/queue | explicit read scope |
| Team identity metadata/roster | global identity manage | read explicitly bound teams only | deny | deny | read explicitly bound teams only |
| Client/project/operational team configuration | explicit content role | delegated scope | project/member scope only | deny | deny |
| Work create/assign/update/transition | explicit content role | permitted scope | permitted project | assigned/member scope, no grant administration | deny |
| Ticket create/assign/transition/reply | explicit content role | permitted queue/client | only additional queue role | permitted queue/client | deny |
| Internal notes read/write | separate note permission | scoped note grant | scoped note grant | scoped note grant | deny by default |
| Attachments | target + visibility grant | target + visibility grant | target + visibility grant | target + visibility grant | public-to-scope targets only |
| Ticket/work link | authority on both ends | authority on both ends | authority on both ends | authority on both ends | deny |
| SLA/automation changes | explicit scoped role | delegated scope | deny by default | deny | deny |
| Analytics/export | explicit analytics grant | permitted team/client | permitted projects | own My Work only by default | explicit read/export grant |
| Import/raw payload/audit | explicit import/audit role | explicit delegated role | deny | deny | deny |

ADR-0029 implements private note authority as explicit queue note_access
none|read|write, default none, restricted to agent/operations_manager bindings.
Current queue role and customer ceiling also apply. Configuration managers
delegate the capability through reviewed grants with session invalidation.
Viewer downgrade/removal revokes it. Private notes use immutable plain text and
privacy-filtered activity before paging. Public transport remains independently
contracted under ADR-0005.

Public messages mean requester-visible conversation, not anonymous internet
readability. No external login in MVP. A public reply's recipients must be
verified participants of that ticket/client; no arbitrary Reply-To passthrough.
Revalidate permission on writes, workers, linked previews, FTS, counts,
notifications, exports and file streaming. Role/membership revocation takes
effect on subsequent requests, not only next login.

Phase 1C-c persists viewer/operations_manager grants only at explicit team scope.
They authorize identity metadata/roster reads, with SQL filtering before pagination
and parent authorization before roster access. /users and every metadata write or
saved POST replay require global identity.manage. Grant/revoke is restricted to
the host CLI, requires email and team UUID confirmation, and uses the shared
identity lock, session invalidation and atomic audit/outbox. Schema constraints
reject arbitrary roles/scopes. Membership never supplies a binding. Existing team
read scope survives archive until revoked. Client/resource ceilings and later
operational role rules remain separate; no persisted client grant is added here.

Phase 2A (ADR-0018) now persists client ceilings and exclusive client role bindings.
Every list/detail/activity read requires both, including for platform administrators.
Client creation is an identity configuration action requiring explicit active-manager
selection, never implicit creator access. The response/replay is a minimal receipt;
it cannot bypass customer reads. Delegation/revocation is serialized with identity
writes, invalidates target sessions and commits audit/outbox atomically. Coherent
same-state grants are no-ops even after archive/deactivation; actual new grants or
repairs require active targets. CLI changes require typed email and client UUID.
Client events contain IDs/allowlisted change names and never enter global identity
history. Expanded client data/history must survive application rollback.

## Trust boundaries and controls

Phase 2B (ADR-0019) adds explicit project membership/role scopes. Internal projects
require both; customer projects first require a ceiling and then either a direct
project role/member pair or a client viewer/operations_manager. Only client
operations_manager or project_manager may alter metadata. Team metadata roles and
global administration never grant project reads. Configuration creation returns
only a minimal receipt and explicitly delegates to the selected manager, requiring
an existing customer ceiling when applicable. Scoped creation additionally requires
team read and explicit self-selection. Every saved replay rechecks that authority.
Shared operational areas contain classification names suitable for all authenticated
staff, not customer-sensitive data. Changing classification never changes scope.
Creation visibility is API-owned and independent of list pagination; browsing or
recovering the list must not dispose an uncertain POST body/idempotency key.

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

Phase0 upload proposal was10 MiB per file,25 MiB raw MIME and<=20 attachments.
ADR0037 now selects10 MiB/file,20 per content item, PDF/PNG/JPEG/UTF8 text and
private S3 plus fail-closed scanning for development. Its implementation remains
pending. The actual incoming raw cap stays2 MiB under ADR0030; the historical
25 MiB proposal never overrides it. New outgoing attachment format2 is separately
bounded to25 MiB; legacy frozen format1 remains262144 bytes.
No active HTML/SVG/executable/archive download allowlist initially. Native image
parsing, MIME sanitizers, Argon2 and malware scanner require CPU homologation.
No scanner was chosen in Phase0. ADR0037 selects ClamAV1.4.6-r0 but provides no
CPU/security acceptance yet. Unscanned files remain quarantined if unavailable;
public attachments have no silent bypass. Policy1 is explicit scan-on-upload:
historically ready files retain that decision while current authorization and
actual byte integrity still gate access. Q-22 records whether production instead
requires expiry/on-access rescanning; no such company policy is assumed.

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

## Phase 3A queue configuration boundary

ADR-0026 implements queue/category metadata reads for explicit team viewers and
operations managers and global platform configuration administrators. Writes use
the corresponding team manager or platform configuration authority, identity-before-
auth serialization, immutable parents and queue/category versions. Roster alone
supplies no authority. Metadata grants do not supply customer ticket content
permissions. Future ticket reads require the ticket's explicit customer ceiling
and its separately implemented queue role. Queue events are redacted and scoped
to their queue activity feed. They never enter identity history.

## Native raw mail quarantine intake

ADR-0030's first native intake is restricted to the database owner and an explicit
operator opt-in. Neither API nor worker has raw-table privileges; configuration
administration does not grant an audience for unclassified customer mail. Capture
accepts bounded binary stdin, never credentials/content as CLI arguments. Errors
and minimal receipts expose no raw bytes, hashes, headers, addresses or secrets.
Input remains opaque quarantine, including hostile/malformed bytes. No MIME
rendering, external fetch, attachment extraction, identity verification, customer
mapping, ticket promotion, checkpoint advance or outbound action is performed.
Strict redacted outbox metadata is acknowledged without shared activity. UID
collisions retain all bounded variants and remain collisions on old receipt replay.
Production mailbox/identity/retention/size policy stays Q-03/Q-09/Q-16/Q-21.

## Read-only IMAPS polling

ADR-0031 adds finite owner-only, certificate/hostname-verified implicit TLS into
quarantine. No plaintext fallback, server flag/deletion writes or public content
grant. LOGIN fields are bounded/quoted; credentials and server diagnostics never
appear in CLI output. Bound individual lines/literals and cumulative control/FETCH
bytes/literal count before imaplib can accumulate unsolicited data. Validate epoch
after every SEARCH, including empty results, and every FETCH before persistence.
Namespace binding follows successful authentication/selection and excludes rotated
passwords. Current lease token/expiry fences all cursor/epoch/capture writes with
no network-held transaction. Preserve old receipts on UIDVALIDITY reset. Actual
mailbox/provider use remains separately authorized and subject to Q-03/Q-16/Q-21.

## ADR0039 manual ticket/work relationship boundary

Selected contract; implementation/negative proof is not yet claimed. Reads require
current read authority on both endpoints. Writes require existing ticket update
AND work update authority, identical non-null customer scope and new-effect active/
closed eligibility. A link grants nothing and never synchronizes either lifecycle.
Native composite FKs independently enforce ticket/customer/queue, work/project and
project/customer identity; no cross-table CHECK or privileged broad role is added.
API receives only SELECT/INSERT/DELETE on the join; worker receives no join grant.

The identity-before-auth and canonical ticket-before-work-graph/row lock protocol
owns both versions, atomic effects and two strict reciprocal audit/outbox events.
Protected POST/DELETE intents retain BOTH original reviewed versions; current
authority precedes receipts. A historical unlink retry must not delete a relink.
New activity is filtered by current counterpart scope before pagination, including
after unlink. Hidden counterpart IDs/titles/counts/events/cursors remain absent.
Retain compatible API feed filters and worker event readers on rollback; a pre-
link API can expose counterpart history and is not a safe rollback image. Refuse
contraction with links, history or receipts; no purge is authorized. Actual image-
pair rollback rehearsal remains a consolidated integrated-hardening gate.
