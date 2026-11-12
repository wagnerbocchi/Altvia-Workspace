# Private MIME normalization operator runbook

This finite owner-only development command implements ADR-0032. It does not prove
sender identity, expose previews to users, change tickets, send mail, scan/extract
attachments or advance IMAP progress. No production mailbox/data is authorized.
Use only a reviewed quarantined variant, with the existing protected owner
database configuration external to commands/logs. Runtime credentials cannot
read or write raw mail or normalized results.

From the project environment, with the owner database secret already configured:

```powershell
$env:ALTVIA_ALLOW_MAIL_NORMALIZE = "1"
uv run python -m altvia.mail_normalize --variant-id "<reviewed-variant-uuid>"
Remove-Item Env:ALTVIA_ALLOW_MAIL_NORMALIZE
```

Use the variant ID from the owner-side capture receipt, never an inferred client
or email address. Output contains source_id, variant_id, status and replayed only.
Exit 0 means the immutable ready or rejected result is durable, not that the mail
is safe or authorized for display. Repeating the command returns replayed=true,
without a new source version/event. Exit 1 is a fixed config/storage diagnostic;
exit 2 is a redacted argument error. Do not paste credentials or message content
into troubleshooting logs.

Ready contains only untrusted subject/plain text and bounded structural counts,
stored in owner-only inbound_mail_previews. HTML attributes/markup are not
retained and no URL is fetched. Future user interfaces must escape all extracted text. Rejected keeps
a fixed reason and no partial text. Original immutable bytes and collision state
remain unchanged, including on rejected/attachment-only/unsupported input.

Supported: plain/HTML text, mixed/alternative/related; charset UTF-8/ASCII/
ISO-8859-1/Windows-1252; strict base64/quoted-printable or 7bit/8bit/binary.
An unlabelled text charset defaults to ASCII. Related start must match its first
root; other multipart types reject. Attached text and message/rfc822 stay opaque.
No decoder replaces malformed bytes; no body is silently truncated. ADR-0032
records exact raw/header/part/depth/decoded/text/HTML bounds and fixed reasons.

The existing source lock serializes persistence with capture/checkpoints; parsing
runs outside write transactions. Source version exhaustion blocks new results,
not replay. An event failure rolls back result and version together. No event or
audit contains subject, body, reason, attachment count or address. Both old/new
private metadata events are consumed without shared activity.

Rollback retains migration b46087000019 and compatible private event handling.
Downgrade refuses results or durable normalized history. Do not delete evidence
or rewrite parser_version=1 rows to bypass the guard. A future changed parser
requires an explicit versioning/reprocessing contract; raw bytes remain available.
Q-03/Q-09/Q-11/Q-16/Q-21 and final actual-target qualification remain open.
