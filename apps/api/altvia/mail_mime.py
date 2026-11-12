"""Bounded, non-rendering MIME text extraction from untrusted quarantine bytes."""

import base64
import binascii
import codecs
import re
from dataclasses import dataclass
from email import policy
from email.message import Message
from email.parser import BytesParser
from html.parser import HTMLParser

from altvia.mail_intake import MAX_RAW_BYTES

REJECTION_CODES = {
    "invalid_raw",
    "invalid_headers",
    "unsupported_mime",
    "invalid_multipart",
    "invalid_encoding",
    "unsupported_charset",
    "structure_limit",
    "text_limit",
    "html_limit",
    "no_text",
}


@dataclass(frozen=True)
class NormalizedMail:
    status: str
    subject: str | None = None
    body_text: str | None = None
    part_count: int | None = None
    attachment_count: int | None = None
    reason: str | None = None


class _Rejected(ValueError):
    pass


def _clean(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return "".join(
        c
        for c in text
        if (c in "\n\t" or ord(c) >= 32)
        and not 127 <= ord(c) <= 159
        and not 0x202A <= ord(c) <= 0x202E
        and not 0x2066 <= ord(c) <= 0x2069
    )


class _HTMLText(HTMLParser):
    """Discard markup and active subtrees; never resolve resources or URLs."""

    suppressed = {"script", "style", "iframe", "object", "svg", "math", "template"}
    void = {
        "area",
        "base",
        "br",
        "col",
        "embed",
        "hr",
        "img",
        "input",
        "link",
        "meta",
        "param",
        "source",
        "track",
        "wbr",
    }
    blocks = {"p", "div", "br", "li", "tr", "h1", "h2", "h3", "hr", "section", "article"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: list[str] = []
        self.tags = 0
        self.chunks: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.tags += 1
        if self.tags > 4096:
            raise _Rejected("html_limit")
        if tag in self.blocks and not any(t in self.suppressed for t in self.stack):
            self.chunks.append("\n")
        if tag not in self.void:
            self.stack.append(tag)
            if len(self.stack) > 64:
                raise _Rejected("html_limit")

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag not in self.void:
            self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        if tag in self.stack:
            index = len(self.stack) - 1 - self.stack[::-1].index(tag)
            del self.stack[index:]
        if tag in self.blocks and not any(t in self.suppressed for t in self.stack):
            self.chunks.append("\n")

    def handle_data(self, data: str) -> None:
        if not any(t in self.suppressed for t in self.stack):
            self.chunks.append(data)

    def text(self, value: str) -> str:
        self.feed(value)
        self.close()
        return re.sub(r"\n[ \t]*\n+", "\n", "".join(self.chunks)).strip()


def _headers(raw: bytes) -> tuple[Message, bytes]:
    candidates = [(raw.find(sep), sep) for sep in (b"\r\n\r\n", b"\n\n")]
    found = [(index, sep) for index, sep in candidates if index >= 0]
    if raw.startswith(b"\r\n"):
        found.append((0, b"\r\n"))
    elif raw.startswith(b"\n"):
        found.append((0, b"\n"))
    if not found:
        raise _Rejected("invalid_headers")
    index, separator = min(found, key=lambda pair: pair[0])
    block = raw[:index]
    lines = block.split(b"\n")
    if len(block) > 16384 or any(len(line) > 2048 for line in lines):
        raise _Rejected("invalid_headers")
    if b"\r" in block.replace(b"\r\n", b"") or b"\0" in block:
        raise _Rejected("invalid_headers")
    headers = BytesParser(policy=policy.default.clone(raise_on_defect=True)).parsebytes(
        block + b"\r\n\r\n", headersonly=True
    )
    if len(headers) > 100 or headers.defects:
        raise _Rejected("invalid_headers")
    for name in (
        "content-type",
        "content-transfer-encoding",
        "content-disposition",
        "mime-version",
        "subject",
        "content-id",
    ):
        if len(headers.get_all(name, [])) > 1:
            raise _Rejected("invalid_headers")
    # Access structured headers now: policy parses their parameters lazily.
    for _name, value in headers.items():
        if getattr(value, "defects", ()):
            raise _Rejected("invalid_headers")
        str(value)
    if headers.get("MIME-Version", "1.0").strip() != "1.0":
        raise _Rejected("invalid_headers")
    return headers, raw[index + len(separator) :]


def _children(body: bytes, boundary: str, ancestors: tuple[str, ...]) -> list[bytes]:
    if (
        not 1 <= len(boundary) <= 70
        or boundary in ancestors
        or any(not 32 <= ord(c) <= 126 for c in boundary)
        or boundary.endswith(" ")
    ):
        raise _Rejected("invalid_multipart")
    pattern = re.compile(
        rb"(?m)^--" + re.escape(boundary.encode("ascii")) + rb"(?P<close>--)?[ \t]*\r?$"
    )
    markers = []
    for match in pattern.finditer(body):
        markers.append(match)
        if len(markers) > 65:
            raise _Rejected("structure_limit")
    if (
        len(markers) < 2
        or not markers[-1].group("close")
        or any(m.group("close") for m in markers[:-1])
    ):
        raise _Rejected("invalid_multipart")
    children = []
    for first, last in zip(markers, markers[1:], strict=False):
        start = first.end() + (body[first.end() : first.end() + 1] == b"\n")
        child = body[start : last.start()]
        if child.endswith(b"\r\n"):
            child = child[:-2]
        elif child.endswith(b"\n"):
            child = child[:-1]
        children.append(child)
    return children


class _Normalizer:
    def __init__(self) -> None:
        self.parts = 0
        self.attachments = 0
        self.decoded = 0
        self.subject = ""

    def entity(self, raw: bytes, ancestors: tuple[str, ...] = ()) -> tuple[str, str]:
        self.parts += 1
        if self.parts > 64 or len(ancestors) >= 8:
            raise _Rejected("structure_limit")
        headers, body = _headers(raw)
        if not ancestors:
            self.subject = _clean(str(headers.get("Subject", ""))).replace("\n", " ")
            if len(self.subject) > 998 or len(self.subject.encode()) > 3992:
                raise _Rejected("invalid_headers")
        content_type = headers.get_content_type()
        attached = (
            headers.get_content_disposition() not in {None, "inline"}
            or headers.get_filename() is not None
        )
        if attached:
            self.attachments += 1
            return "", ""
        if headers.get_content_maintype() == "multipart":
            if content_type not in {
                "multipart/mixed",
                "multipart/alternative",
                "multipart/related",
            }:
                raise _Rejected("unsupported_mime")
            if headers.get("Content-Transfer-Encoding", "7bit").lower().strip() not in {
                "7bit",
                "8bit",
                "binary",
            }:
                raise _Rejected("invalid_encoding")
            boundary = headers.get_boundary()
            if boundary is None:
                raise _Rejected("invalid_multipart")
            parts = _children(body, boundary, ancestors)
            if content_type == "multipart/related" and headers.get_param("start") is not None:
                first, _ = _headers(parts[0])
                if headers.get_param("start") != first.get("Content-ID"):
                    raise _Rejected("unsupported_mime")
            values = [self.entity(part, (*ancestors, boundary)) for part in parts]
            if content_type == "multipart/alternative":
                return next(
                    (v for v in values if v[0] == "plain" and v[1]),
                    next((v for v in values if v[1]), ("", "")),
                )
            if content_type == "multipart/related":
                return values[0]
            return "plain", "\n\n".join(v[1] for v in values if v[1])
        if content_type not in {"text/plain", "text/html"}:
            self.attachments += 1
            return "", ""
        encoding = headers.get("Content-Transfer-Encoding", "7bit").lower().strip()
        if encoding == "base64":
            try:
                decoded = base64.b64decode(body.translate(None, b" \t\r\n"), validate=True)
            except binascii.Error as error:
                raise _Rejected("invalid_encoding") from error
        elif encoding == "quoted-printable":
            if re.search(rb"=(?![0-9A-Fa-f]{2}|\r?\n)", body):
                raise _Rejected("invalid_encoding")
            import quopri

            decoded = quopri.decodestring(body)
        elif encoding in {"7bit", "8bit", "binary"}:
            if encoding == "7bit" and not body.isascii():
                raise _Rejected("invalid_encoding")
            decoded = body
        else:
            raise _Rejected("invalid_encoding")
        self.decoded += len(decoded)
        if self.decoded > 262144:
            raise _Rejected("text_limit")
        try:
            charset = codecs.lookup(headers.get_content_charset("us-ascii")).name
        except LookupError as error:
            raise _Rejected("unsupported_charset") from error
        if charset not in {"utf-8", "ascii", "iso8859-1", "cp1252"}:
            raise _Rejected("unsupported_charset")
        text = decoded.decode(charset, errors="strict")
        if content_type == "text/html":
            text = _HTMLText().text(text)
        text = _clean(text).strip()
        if len(text.encode()) > 65536:
            raise _Rejected("text_limit")
        return ("html" if content_type == "text/html" else "plain"), text


def normalize(raw: bytes) -> NormalizedMail:
    """Produce all-or-nothing private text; rejection codes never contain inputs."""
    try:
        if not isinstance(raw, bytes) or not 1 <= len(raw) <= MAX_RAW_BYTES:
            raise _Rejected("invalid_raw")
        parser = _Normalizer()
        _, body = parser.entity(raw)
        if not body:
            raise _Rejected("no_text")
        if len(body.encode()) > 65536:
            raise _Rejected("text_limit")
        return NormalizedMail("ready", parser.subject, body, parser.parts, parser.attachments)
    except _Rejected as error:
        return NormalizedMail("rejected", reason=str(error))
    except (ValueError, LookupError, RecursionError):
        return NormalizedMail("rejected", reason="invalid_encoding")
