# ADR-0005: Native mail with verified correlation and uncertainty handling

Date: 2026-11-08. Status: selected security design; mailbox/provider policy pending.

Decision: secure IMAP/SMTP adapters with external secret references, no Plane or
Zammad APIs. Durable ingress identity `(mailbox,UIDVALIDITY,UID)` with checkpoint
advance only after record commit. Preserve Message-ID/raw hash for secondary
deduplication. Identical content alone is not duplicate proof. UID reset/resync
uses corroborated headers/hash and collision quarantine rather than dropping mail.

Correlate References/In-Reply-To and unguessable internal thread token only after
checking ticket/client/participant identity. Subject alone never correlates.
From/Reply-To and Message-ID are attacker-controlled. Use authentication results
only from the configured trusted receiving MTA, with documented forwarding policy.
Unverifiable messages go to restricted triage/quarantine, never append to another
client's conversation. A first contact can create an unverified triage request,
not gain access to customer history. Automatic outbound recipients require
verified ticket participants. Auto-replies/DSNs must not generate mail loops.

MIME parsing is bounded, text fallback preserved, HTML allowlist sanitized,
remote resources disabled. Files remain private/quarantined pending scan.
Private note is structurally incapable of creating an outbound delivery.

Public reply and outbound record commit together; worker sends using stable
Message-ID and a recorded envelope. Positive SMTP acceptance records accepted,
not final recipient delivery. If acknowledgement is lost after DATA, mark
uncertain and require reconciliation/manual decision before resend. SMTP cannot
promise exactly once; provider-supported idempotency can strengthen this later.

Alternatives: subject-only routing/From trust leaks data; forced resend on every
timeout can duplicate customer responses; relying on an external helpdesk violates
independence. Proof includes spoofed/malformed mail, UID reset, collision,
forwarding, unsafe HTML, attachment ACL, private-note non-delivery and ambiguous
SMTP acceptance. Credentials, raw content and addresses are redacted from logs.
