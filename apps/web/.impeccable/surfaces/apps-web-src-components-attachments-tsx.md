---
version: 1
slug: "apps-web-src-components-attachments-tsx"
primary_target: "apps/web/src/components/attachments.tsx"
related_targets: ["apps/web/src/components/tickets/detail.tsx", "apps/web/src/components/tickets/messages.tsx", "apps/web/src/components/tickets/notes.tsx", "apps/web/src/components/work-items/detail.tsx", "apps/web/src/components/work-items/reads.tsx", "apps/web/src/app/globals.css"]
---

# Scoped files in responses, private notes and work comments

Mode Operate. Existing-surface extension under ADR-0037, recorded from the
implementation at 039a631. Inherit PRODUCT.md, root DESIGN.md and its sidecar,
the shared apps-web brief, ticket and private-note briefs, and the public-response
brief. The user-selected Twenty direction of 2026-11-12 remains authoritative.

## Direction contract

THESIS: An authorized operator uploads a file, reads its actual verification
state, and deliberately includes ready files in the existing content action.
Uploading alone neither registers text nor sends email. Consultation guidance
describes current states and available downloads without promising writer actions.

OWN-WORLD: Keep the offwhite sidebar, continuous white working field, gray
hairlines, system sans, restrained blue actions and neutral charcoal dark mode.
Reuse native labeled file inputs, outline buttons, existing feedback and a small
Lucide paperclip. File states remain explicit words in quiet metadata. No new
palette, type scale, shadows, raster assets, fonts or decorative motion is added.

STORY: Select a native file, send it, refresh current verification state, include
ready files, then use the existing response/note/comment action. Public responses,
private notes and internal work comments keep separate purpose-bound file lists
and selections. Saved content lists filenames and byte sizes with named downloads.
Public draft review and outgoing review include the ordered filenames, byte sizes
and count; outgoing confirmation also retains exact saved text, sender and recipient.
Internal notes remain visibly separate and excluded from public delivery.

FIRST VIEWPORT: Preserve ticket subject/number/state, identity facts and current
operational actions. File controls remain inside the existing composer or permitted
consultation region. Work comment files stay with internal comments. Rows present
filename, bytes and current state before their named actions. Desktop rows wrap;
at or below 540px they stack text and actions in that order, with full-width action
groups, wrapping names and labels, and checkbox controls that do not shrink.
Keep the shared responsive navigation and comfortable native-control targets.

FORM: Code-led incumbent extension. The flat picker uses existing section rules,
24px outer spacing, 16px vertical padding and 12px row spacing. Native input hints
name PDF, PNG, JPEG, TXT and LOG, 1 byte through 10 MiB per file; inclusion is limited
to 20 ready files. Read actual quarantine/scanning/ready/rejected/failed states;
do not fabricate percentages or time estimates. Download and failed-scan retry
follow current capabilities. Without upload capability, hide selection/upload/include
controls and retain consultation copy, refresh, current states and available downloads.
Private-note visibility remains subject to existing note authority.

Retain the original file/name and exact reviewed intent through an uncertain upload;
show recovery and deliberate discard/reload before later mutation. Current download
authority is checked independently of saved link summaries. Preserve the existing
session owner's disposal of private state. Files create no content or identity grants.
No public object-store links or inline content preview are introduced.

FINISH: The original full Impeccable review inspected all 64 ticket-state captures;
the separate scored copy-fix verdict inspected all eight consultation recaptures
and returned ship for that fix. Preserve both scopes when citing acceptance.
Both themes and desktop/mobile have inherited real browser keyboard, axe, overflow
and recovery evidence. These ticket captures do not claim separately pictured work
comment layouts. Signed production-profile ClamAV UI proof, exact-final hosted gates
and consolidated target qualification remain separate acceptance work. No raster
provenance entry is needed for this extension because no raster asset ships.

## Immutable incoming-file consultation (2026-11-13)

IncomingAttachments extends the same file-row vocabulary for original received
files in case triage and the immutable ticket conversation. It adds no upload,
include, forward or inline-preview action to incoming files. Existing public
response, private-note and work-comment picker capabilities above remain separate
and unchanged. The incumbent neutral Operate world, spacing, responsive action
stacking, system type and Lucide paperclip remain authoritative; no new system,
comp, seed, QUALITY BAR card or shipping raster is introduced.

Each visible original file retains its name, byte size and explicit current state.
Incoming ready copy says verification is complete rather than promising use or
permanent safety. Current capability alone exposes named download or failed-scan
retry; consultation-only access can retain download without retry. Completed
verification with unavailable download has its own explanation. Download performs
a fresh file read before requesting bytes, uses the current filename, aborts on
disposal and revokes temporary Blob URLs. Relevant parent read error/refetch and
the protected retry lock disable stale actions.

Retry retains the original file identity/version/key through uncertainty. Its
protected POST receipt and a current actor-bound read must confirm the same
incoming case asset before acknowledgement; refreshing the parent alone does not
confirm it. Show named original-operation recovery, and deliberate refresh/discard
for a refused conflict; failed refresh preserves the original attempt. Current
files remain independent of frozen promotion text/review. Session disposal clears
private state, while a temporarily hidden block does not manufacture an empty set.

Legacy explains that files were not processed and absence proves nothing about
original attachments. Unavailable uses fixed administrator-recovery guidance;
complete empty explicitly states no file received. Hidden/null yields no block or
inferred count. Invalidated message history stays visible only within current
authority, with current capabilities deciding file actions.

The incoming-file finish verdict is ship for UI cf74597 and all 52 required
desktop/mobile light/dark captures across 13 states. This evidence supplements,
and does not replace or broaden, the earlier picker/copy-fix evidence above.
It is ordinary extension evidence, not whole-product or final engineering
qualification. Pre-existing root DESIGN.md-newer-than-sidecar drift remains
disclosed and unrepaired; this increment establishes no new tokens or defects
as system rules.
