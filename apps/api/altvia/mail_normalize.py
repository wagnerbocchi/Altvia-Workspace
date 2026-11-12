"""Owner-only atomic MIME interpretation of immutable quarantined variants."""

import json
import os
import sys
from dataclasses import asdict, dataclass
from uuid import UUID

from sqlalchemy import Engine, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from altvia.config import DatabaseSettings
from altvia.database import make_engine
from altvia.mail_intake import MAX_VERSION, SafeMailParser, record_intake_event
from altvia.mail_mime import normalize
from altvia.models import InboundMailEnvelope, InboundMailPreview, InboundMailVariant, MailboxSource


class NormalizeError(ValueError):
    """Fixed safe operator error; contains no raw mail or headers."""


@dataclass(frozen=True)
class NormalizeReceipt:
    source_id: UUID
    variant_id: UUID
    status: str
    replayed: bool


def normalize_variant(engine: Engine, variant_id: UUID) -> NormalizeReceipt:
    with Session(engine) as db:
        variant = db.get(InboundMailVariant, variant_id)
        if variant is None:
            raise NormalizeError("variant_unavailable")
        source_id = db.scalar(
            select(InboundMailEnvelope.source_id).where(
                InboundMailEnvelope.id == variant.envelope_id
            )
        )
        raw = variant.raw_message
    # Parsing immutable bytes cannot block source writers with a long transaction.
    normalized = normalize(raw)
    with Session(engine) as db, db.begin():
        source = db.scalar(
            select(MailboxSource).where(MailboxSource.id == source_id).with_for_update()
        )
        if source is None:
            raise NormalizeError("source_unavailable")
        variant = db.get(InboundMailVariant, variant_id)
        if variant is None:
            raise NormalizeError("variant_unavailable")
        existing = db.get(InboundMailPreview, variant_id)
        if existing is not None:
            return NormalizeReceipt(source.id, variant_id, existing.status, True)
        if source.version >= MAX_VERSION:
            raise NormalizeError("source_version_exhausted")
        db.add(
            InboundMailPreview(
                variant_id=variant_id,
                parser_version=1,
                status=normalized.status,
                subject=normalized.subject,
                body_text=normalized.body_text,
                part_count=normalized.part_count,
                attachment_count=normalized.attachment_count,
                reason=normalized.reason,
            )
        )
        source.version += 1
        db.flush()
        record_intake_event(
            db,
            source,
            "mailbox.message_normalized",
            {
                "envelope_id": str(variant.envelope_id),
                "variant_id": str(variant_id),
                "status": normalized.status,
            },
        )
        return NormalizeReceipt(source.id, variant_id, normalized.status, False)


def main(argv: list[str] | None = None) -> int:
    if os.environ.get("ALTVIA_ALLOW_MAIL_NORMALIZE") != "1":
        print("Explicit ALTVIA_ALLOW_MAIL_NORMALIZE=1 is required.", file=sys.stderr)
        return 1
    parser = SafeMailParser(
        description="Restricted private MIME interpretation", allow_abbrev=False
    )
    parser.add_argument("--variant-id", required=True, type=UUID)
    args = parser.parse_args(argv)
    engine = None
    try:
        engine = make_engine(DatabaseSettings())
        receipt = normalize_variant(engine, args.variant_id)
        print(json.dumps(asdict(receipt), default=str))
        return 0
    except (SQLAlchemyError, ValueError, OSError, OverflowError):
        print("Mail normalization failed; no result acknowledged.", file=sys.stderr)
        return 1
    finally:
        if engine is not None:
            engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
