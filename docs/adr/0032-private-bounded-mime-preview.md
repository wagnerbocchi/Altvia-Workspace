# ADR-0032 Private bounded MIME text normalization

Date 2026-11-11. Phase 3E-c, scoped FR-007/012. Master specification and
ADR-0004/0005/0030/0031 apply. The user authorized continued development and
direct main publication, with unresolved provider/privacy choices registered.

## Decision and alternatives

Normalize an explicitly selected quarantined raw variant through an owner-only
finite command, separately from IMAPS capture. Persist an immutable parser-v1
result and private metadata event atomically. Do not change raw receipts, poll
checkpoints, collision state or any ticket. No runtime/API/browser access, sender
proof, account/contact lookup, thread correlation, promotion or outbound delivery.

Use standard-library bounded per-entity MIME headers/transfer codecs and
HTMLParser for text extraction. Do not parse an unrestricted recursive message
tree first: bound structure before constructing child entities. A third-party
sanitizer and HTML rendering are unnecessary while this boundary emits text only.
No HTML is persisted in the normalized result; extracted text remains untrusted
and a future UI must escape it. Neither test nor runtime fetches URLs/images.

Supported entities: text/plain and text/html; multipart/mixed, alternative and
related. Mixed joins inline text in wire order; alternative prefers plain text,
then HTML fallback; related selects its first root and requires any explicit
start parameter to identify that root. Attachment disposition or any filename
prevents a text leaf from becoming body text. Other leaf media, including
message/rfc822, remain opaque attachments. No archive or attached message is
expanded. Unknown multipart types, invalid structure/encoding/charset and
resource exhaustion persist a fixed rejection code, never partial body text.

Limits: raw 2097152 bytes; 64 entities; depth 8; each header block 16384 bytes,
physical header line 2048 bytes and 100 header fields; MIME boundary 1..70
printable ASCII bytes without trailing space; decoded inline text aggregate
262144 bytes; final body 65536 UTF-8 bytes; subject 998 characters/3992 UTF-8 bytes.
HTML extraction permits 4096 tags and nesting 64. Suppress executable/embedded
content and its text (script/style/iframe/object/svg/math/template), discard all
attributes, normalize line endings and remove unsafe control/directional chars.
Never silently truncate an oversized result. Limits remain provisional Q-21.

Charsets are UTF-8, US-ASCII, ISO-8859-1 and Windows-1252 aliases. Decode strictly;
unknown or invalid encodings are rejected. Accept 7bit/8bit/binary and strictly
validated base64/quoted-printable for body text. Default text charset is ASCII.
Require complete multipart closing boundaries and unambiguous singleton MIME
headers. Preserve raw bytes as the authority for a later broader parser version.

## Persistence, replay, locking and events

Migration b46087000019 adds owner-only inbound_mail_previews keyed by variant_id
with RESTRICT FK, parser_version=1, status ready|rejected, subject/body/counts
only for ready, fixed reason only for rejected and created_at. SQL checks bound
text/counts and exclude mixed/null states. An update/delete trigger makes results
append-only. Downgrade refuses any preview or normalized event history; rollback
retains expansion and compatible private event consumption. No runtime grants.

Read immutable variant bytes and normalize outside write transactions. Persist by
locking its source first, matching capture's order; recheck variant/source and
return an existing result without version/event changes. Collision variants may
be normalized independently but remain quarantined and ineligible for implied
promotion. A later collision cannot reinterpret earlier previews as verified.
Advance source version and commit result/audit/outbox in one transaction. Failures
leave no acknowledged result. Concurrent retries converge on one immutable row.

mailbox.message_normalized uses the existing intake aggregate/envelope plus
variant_id and status ready|rejected only. No subject, body, counts, reason,
address, credential or header enters audit/outbox/shared activity. Preserve all
old payload shapes; strict consumer acknowledges this event privately. The CLI
requires ALTVIA_ALLOW_MAIL_NORMALIZE=1 and --variant-id UUID. Output IDs, status
and replay only; all malformed arguments/config/storage failures are redacted.

## Costs and acceptance

Text extraction avoids an HTML sanitizer dependency and rendering attack surface,
at the cost of formatting and links. Strict bounded MIME rejects some legitimate
provider messages; immutable raw data permits later reviewed reprocessing.
Manual variant selection avoids guessing scheduling/verification policy; later
promotion remains separately authorized. Immutable results require a new parser
version rather than overwriting historical interpretations.

Prove real PostgreSQL persistence, concurrent replay, rollback, immutable results,
both runtime denials, strict private/legacy events and guarded migration; exercise
actual owner CLI without body output. Test encoded Portuguese/HTML fallback,
multipart selection, attachments, malformed/hostile syntax, nested/part/size/tag
limits and controls. Package the actual command and recreate PostgreSQL before
checking durable result. Local/CI/security gates continue; final baseline-VM
qualification remains deferred. No live mailbox or real data is used.
