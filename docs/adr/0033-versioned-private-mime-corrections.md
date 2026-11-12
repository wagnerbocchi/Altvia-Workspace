# ADR-0033 Versioned corrections for private MIME interpretation

Date 2026-11-11. Follow-up to ADR-0032's R3/R4 review gaps. Existing development,
direct main publication and development-first qualification authorization apply.
No live mailbox, production rollout, user-facing preview or new grant is implied.

## Decision

Close the Subject charset and HTML token-budget gaps as parser version 2. Keep
every parser-v1 row unchanged. Normalize the same raw variant under v2 without
overwriting a prior interpretation; replay only the exact (variant_id,2) result.
The previous boundary explicitly required versioning changed interpretations.
A patch silently relabeling/replaying v1 as corrected would violate that rule.

Extend inbound_mail_previews' primary key to (variant_id,parser_version), allow
only versions 1 and 2 and retain all text/state/append-only constraints and FK.
Migration b46087000020 does not rewrite/delete v1 values or change grants. The
model's new-write default is 2; the historical database default 1 remains intact.
The owner command always explicitly writes version 2 and returns parser_version
with its existing IDs/status/replay fields. No caller-controlled parser selector,
legacy algorithm implementation or speculative future-version framework.

Before this development migration or rollback, stop/drain owner normalization
commands. Old version-1 command binaries assume a one-column ORM key and are not
supported against the expanded schema. API roles cannot access this table; the
version-aware command and private consumer are the supported tools throughout
the compatibility window. Application rollback retains expansion and those
compatible tools. Do not run old/new owner commands concurrently. No production
migration or host/service change is authorized by this contract.

Downgrade to revision 19 is safe only without v2 rows or v2 normalized audit/
outbox history. Lock preview/audit/outbox before the guard and key contraction.
Refuse with a fixed diagnostic if expanded data exists, preserving all evidence.
An old v1 row remains historical interpretation only, never proof of v2 policy.

## Parser correction ownership

Decode RFC 2047 Subject words with the standard library's transfer decoder, then
the same explicit canonical charset allowlist as body text: UTF-8, ASCII,
ISO-8859-1 and Windows-1252 aliases. Validate before invoking a structured Subject
header decoder; do not let its broader codec registry reinterpret the subject.
Plain unencoded Subject text must be ASCII; RFC 6532/raw UTF-8 header acceptance
remains outside this finite subset. Decode strictly, preserve folded encoded
words' semantics and apply the existing subject/control/byte bounds. Unsupported
charsets reject the entire result with fixed unsupported_charset, never partial
subject/body. Raw bytes remain available for reviewed future interpretation.

Require raw Subject ASCII before the standard decoder can escape surrogate bytes.
Validate every encoded word's base64/quoted-printable syntax and strictly decode
its bytes independently before adjacent-word assembly. Contain HeaderParseError
as a fixed durable rejection. Other raw header occurrences use the public policy
header_fetch_parse seam individually, preserving duplicate-value validation while
avoiding the broader Subject headerregistry path or private parse-tree APIs.

Count every actual HTML start, end and self-closing token toward 4096. A
self-closing token counts once; an internal synthetic stack closure does not
consume another token. Count unmatched/void end tags too. Keep nesting64,
active-subtree rejection/suppression and raw/decoded/text bounds unchanged.

## Private event compatibility

Reuse mailbox.message_normalized with schema_version=2 and exact legacy fields
plus parser_version="2". Extend the strict existing intake validator/recorder;
schema1 accepts only the original envelope without parser_version. Other intake
events remain schema1. Both versions are acknowledged without shared activity.
No subject/body/reason/count/address enters audit/outbox or command output.
Source lock, version exhaustion, atomic writes and retry behavior are unchanged;
each new interpretation advances the source once, each replay advances nothing.

## Alternatives, costs and proof

Keeping one row per variant cannot durably correct an old interpretation without
overwriting history. A second table/legacy view adds duplicate storage ownership
or schema comparison machinery. A composite key owns the invariant directly;
its cost is explicit command compatibility and guarded rollback coordination.
The strict Subject subset rejects some legitimate unencoded international headers;
there is no claim of complete provider compatibility. Shared charset validation
and token accounting introduce no dependency, binary or ISA change.

Observe R3/R4 regressions fail then pass, including aliases/folding, unsupported
known/unknown codecs, strict bytes, exact4096/4097 token boundaries and non-void
self-closing tokens. Prove PostgreSQL v1 upgrade preservation, concurrent v2
replay, immutable coexisting results, event1/2 strictness/private consumption,
guarded rollback/history, runtime denial, CLI and recreated packaged results.
Inspect full hosted/security evidence; final target qualification stays deferred.

## Build availability follow-up

During exact-source acceptance, both web-image jobs failed before runtime proof.
A fresh local build reproduced the signed Alpine repository removing pinned
nodejs24.22.1-r1 and offering24.22.3-r0. Retain the same image family/digest and
exact package pinning, updating only Node's maintained patch pin to24.22.3-r0.
The corrected real image build passed its Node24/module137/locale/standalone/
no-Sharp/no-installer capability checks. All hosted gates and five-image scans
remain required for the resulting artifact. Earlier ISA qualification does not
transfer to this changed runtime; final actual-target qualification remains open.
