"""Finite ASCII routing interpretation; headers never prove identity."""

import re
from dataclasses import dataclass
from email.errors import HeaderParseError

from altvia.client_contacts import normalize_contact_email
from altvia.mail_mime import root_headers

ATOM = r"[A-Za-z0-9!#$%&'*+\-/=?^_`{|}~]+"
LABEL = r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
ID = re.compile(rf"<{ATOM}(?:\.{ATOM})*@{LABEL}(?:\.{LABEL})*>", re.ASCII)


class RoutingError(ValueError):
    """Fixed routing refusal; carries no hostile values."""


@dataclass(frozen=True)
class RoutingHeaders:
    message_id: str | None
    in_reply_to: str | None
    references: tuple[str, ...]
    thread_token: str | None
    from_email: str


def _id(value: str) -> str:
    if len(value) > 320 or not ID.fullmatch(value) or len(value[1:-1].split("@")[1]) > 253:
        raise RoutingError("invalid_routing")
    return value


def parse_routing(raw: bytes) -> RoutingHeaders:
    try:
        fields: dict[str, list[str]] = {}
        for name, value in root_headers(raw):
            fields.setdefault(name.lower(), []).append(value)

        def singleton(name: str, required: bool = False) -> str | None:
            values = fields.get(name, [])
            if len(values) > 1 or (required and not values):
                raise RoutingError("invalid_routing")
            if not values:
                return None
            value = re.sub(r"\r?\n[ \t]+", " ", values[0]).strip(" \t")
            if not value.isascii() or any(
                ord(c) < 32 and c != "\t" or ord(c) == 127 for c in value
            ):
                raise RoutingError("invalid_routing")
            return value

        def mailbox(name: str, required: bool = False) -> str | None:
            value = singleton(name, required)
            if value is None:
                return None
            # A finite display-name envelope; never decode hostile RFC2047 words
            # through headerregistry's broad charset lookup. Display text is discarded.
            if "<" in value or ">" in value:
                match = re.fullmatch(
                    r'(?:[A-Za-z0-9 .!#$%&\'*+\-/=?^_`{|}~-]+|"[^"\\]*")?'
                    r"[ \t]*<([^<>]+)>",
                    value,
                )
                if match is None:
                    raise RoutingError("invalid_routing")
                value = match.group(1)
            return normalize_contact_email(value)

        sender = mailbox("from", True)
        assert sender is not None
        if any(mailbox(name) not in {None, sender} for name in ("sender", "reply-to")):
            raise RoutingError("invalid_routing")
        primary, parent = singleton("message-id"), singleton("in-reply-to")
        references = singleton("references")
        refs = tuple(_id(part) for part in re.split(r"[ \t]+", references)) if references else ()
        if references == "" or len(refs) > 64:
            raise RoutingError("invalid_routing")
        token = singleton("x-altvia-thread")
        if token is not None and not re.fullmatch("[0-9a-f]{64}", token):
            raise RoutingError("invalid_routing")
        auto, path = singleton("auto-submitted"), singleton("return-path")
        if path is not None:
            match = re.fullmatch(r"<([^<>]+)>", path)
            if match is None:
                raise RoutingError("invalid_routing")
            normalize_contact_email(match.group(1))
        content = singleton("content-type")
        if auto is not None and auto.lower() != "no" or path == "<>":
            raise RoutingError("invalid_routing")
        if content and (
            re.match(
                r"(?:multipart/report|message/(?:global-)?delivery-status)(?:[ ;]|$)", content, re.I
            )
            or re.search(r"report-type\s*=", content, re.I)
        ):
            raise RoutingError("invalid_routing")
        return RoutingHeaders(
            _id(primary) if primary is not None else None,
            _id(parent) if parent is not None else None,
            refs,
            token,
            sender,
        )
    except (ValueError, UnicodeError, HeaderParseError, OverflowError, TypeError) as error:
        raise RoutingError("invalid_routing") from error
