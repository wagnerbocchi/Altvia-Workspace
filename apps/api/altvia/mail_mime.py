"""Bounded, non-rendering MIME text extraction from untrusted quarantine bytes."""

import base64
import binascii
import codecs
import quopri
import re
from dataclasses import dataclass
from email import policy
from email.errors import HeaderParseError
from email.header import decode_header
from email.message import Message
from email.parser import BytesParser
from html.parser import HTMLParser
from io import BytesIO
from typing import Literal
from urllib.parse import unquote_to_bytes

from altvia.attachments import media_type, validate_filename
from altvia.identity import IdentityError
from altvia.mail_intake import MAX_RAW_BYTES

PARSER_VERSION = 2

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


def _charset(value: str) -> str:
    try:
        charset = codecs.lookup(value).name
    except LookupError as error:
        raise _Rejected("unsupported_charset") from error
    if charset not in {"utf-8", "ascii", "iso8859-1", "cp1252"}:
        raise _Rejected("unsupported_charset")
    return charset


def _subject(value: str) -> str:
    # Validate the original wire representation before decode_header can turn
    # surrogateescaped raw bytes into ASCII backslash escapes in mixed chunks.
    value.encode("ascii", errors="strict")
    for word in re.finditer(r"=\?([^?]*?)\?([bq])\?(.*?)\?=", value, re.IGNORECASE | re.DOTALL):
        word_charset = _charset(word.group(1))
        encoded = word.group(3).encode("ascii")
        if any(c < 33 or c > 126 for c in encoded) or b"?" in encoded:
            raise _Rejected("invalid_encoding")
        if word.group(2).lower() == "b":
            decoded = base64.b64decode(encoded, validate=True)
        else:
            if re.search(rb"=(?![0-9A-Fa-f]{2})", encoded):
                raise _Rejected("invalid_encoding")
            decoded = quopri.decodestring(encoded.replace(b"_", b" "))
        # Each word must be valid independently, before adjacent bytes merge.
        decoded.decode(word_charset, errors="strict")
    chunks = []
    # decode_header handles RFC2047 transfer encoding without invoking charsets.
    # Decode bytes ourselves before headerregistry can use its broader codecs.
    for data, charset in decode_header(value):
        if isinstance(data, str):
            data = data.encode("ascii", errors="strict")
        chunks.append(data.decode(_charset(charset or "us-ascii"), errors="strict"))
    subject = _clean("".join(chunks)).replace("\n", " ")
    if len(subject) > 998 or len(subject.encode()) > 3992:
        raise _Rejected("invalid_headers")
    return subject


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

    def _count_token(self) -> None:
        self.tags += 1
        if self.tags > 4096:
            raise _Rejected("html_limit")

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._count_token()
        if tag in self.blocks and not any(t in self.suppressed for t in self.stack):
            self.chunks.append("\n")
        if tag not in self.void:
            self.stack.append(tag)
            if len(self.stack) > 64:
                raise _Rejected("html_limit")

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in self.suppressed:
            # HTML non-void active elements cannot be safely treated as XML voids.
            raise _Rejected("unsupported_mime")
        self.handle_starttag(tag, attrs)
        if tag not in self.void:
            self._close_tag(tag)

    def handle_endtag(self, tag: str) -> None:
        self._count_token()
        self._close_tag(tag)

    def _close_tag(self, tag: str) -> None:
        if tag in self.stack:
            index = len(self.stack) - 1 - self.stack[::-1].index(tag)
            if any(t in self.suppressed for t in self.stack[index + 1 :]):
                raise _Rejected("unsupported_mime")
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


def _root_headers(raw: bytes) -> tuple[Message, bytes]:
    if not isinstance(raw, bytes) or not 1 <= len(raw) <= MAX_RAW_BYTES:
        raise _Rejected("invalid_headers")
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
    return headers, raw[index + len(separator) :]


def root_headers(raw: bytes) -> tuple[tuple[str, str], ...]:
    """Bounded raw root fields, without broad structured-header interpretation."""
    try:
        headers, _ = _root_headers(raw)
        return tuple(headers.raw_items())
    except (ValueError, UnicodeError, HeaderParseError, OverflowError) as error:
        raise ValueError("invalid_headers") from error


def _headers(raw: bytes) -> tuple[Message, bytes, str]:
    headers, body = _root_headers(raw)
    raw_headers = list(headers.raw_items())
    for name in (
        "content-type",
        "content-transfer-encoding",
        "content-disposition",
        "mime-version",
        "subject",
        "content-id",
    ):
        if sum(key.lower() == name for key, _ in raw_headers) > 1:
            raise _Rejected("invalid_headers")
    subject = _subject(next((value for key, value in raw_headers if key.lower() == "subject"), ""))
    # Access structured headers now: policy parses their parameters lazily.
    try:
        # Parse each actual value through the public policy seam, preserving
        # repeated fields without ever invoking headerregistry for Subject.
        for name, raw_value in raw_headers:
            if name.lower() == "subject":
                continue
            value = headers.policy.header_fetch_parse(name, raw_value)
            if getattr(value, "defects", ()):
                raise _Rejected("invalid_headers")
            str(value)
    except OverflowError as error:
        # DateHeader's integer-to-datetime conversion can overflow on hostile years.
        raise _Rejected("invalid_headers") from error
    if headers.get("MIME-Version", "1.0").strip() != "1.0":
        raise _Rejected("invalid_headers")
    return headers, body, subject


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
        headers, body, subject = _headers(raw)
        if not ancestors:
            self.subject = subject
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
                first, _, _ = _headers(parts[0])
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
        charset = _charset(headers.get_content_charset("us-ascii"))
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
    except (ValueError, LookupError, RecursionError, HeaderParseError):
        return NormalizedMail("rejected", reason="invalid_encoding")


@dataclass(frozen=True)
class ExtractedFile:
    filename: str
    media_type: str
    content: bytes


@dataclass(frozen=True)
class ExtractedFiles:
    status: Literal["complete", "unavailable"]
    files: tuple[ExtractedFile, ...] = ()
    reason: str | None = None


class _FileUnavailable(ValueError):
    pass


def _file_parameter(value: str, parameter: str) -> str | None:
    """Check finite wire forms before stdlib can recover or combine parameters."""
    value = re.sub(r"\r?\n[ \t]+", " ", value)
    token = r"[^\x00-\x20\x7f()<>@,;:\\\"/\[\]?=]+"
    quoted = r'"(?:[^"\\\x00-\x1f\x7f]|\\[\x20-\x7e])*"'
    main, separator, rest = value.partition(";")
    if not main.strip():
        raise _FileUnavailable("file_parameter")
    found = None
    while separator:
        match = re.match(rf"\s*({token})\s*=\s*({quoted}|{token})\s*(;|$)", rest)
        if match is None:
            raise _FileUnavailable("file_parameter")
        name, wire, separator = match.groups()
        rest = rest[match.end() :]
        name = name.lower()
        if name == parameter or name.startswith(parameter + "*"):
            if found is not None or name not in {parameter, parameter + "*"}:
                raise _FileUnavailable("file_parameter")
            # Rename to a plain parameter to let the public stdlib API unquote
            # without applying RFC2231's broad charset/percent recovery first.
            field = Message(policy=policy.compat32)
            field["Content-Disposition"] = "attachment; value=" + wire
            decoded = field.get_param("value", header="Content-Disposition")
            if not isinstance(decoded, str) or "=?" in decoded:
                raise _FileUnavailable("file_parameter")
            if name.endswith("*"):
                pieces = decoded.split("'", 2)
                if len(pieces) != 3:
                    raise _FileUnavailable("file_parameter")
                charset, language, encoded = pieces
                if language and re.fullmatch(r"[A-Za-z0-9-]{1,35}", language) is None:
                    raise _FileUnavailable("file_parameter")
                if re.search(r"%(?![0-9A-Fa-f]{2})", encoded):
                    raise _FileUnavailable("file_parameter")
                try:
                    decoded = unquote_to_bytes(encoded).decode(_charset(charset), errors="strict")
                except (ValueError, LookupError) as error:
                    raise _FileUnavailable("file_parameter") from error
            found = decoded
    return found


def _file_headers(raw: bytes) -> tuple[Message, bytes, str | None]:
    headers, _ = _root_headers(raw)
    names = []
    for key, value in headers.raw_items():
        try:
            key.encode("ascii", errors="strict")
            value.encode("ascii", errors="strict")
        except UnicodeError as error:
            reason = (
                "file_parameter"
                if key.lower() in {"content-type", "content-disposition"}
                else "file_structure"
            )
            raise _FileUnavailable(reason) from error
        parameter = {"content-type": "name", "content-disposition": "filename"}.get(key.lower())
        if parameter is not None:
            name = _file_parameter(value, parameter)
            if name is not None:
                names.append(name)
    if len(set(names)) > 1:
        raise _FileUnavailable("file_parameter")
    # Existing bounded/strict structural ownership stays unchanged for parser2.
    headers, body, _ = _headers(raw)
    return headers, body, names[0] if names else None


def _file_content(body: bytes, encoding: str) -> bytes:
    if encoding == "base64":
        try:
            return base64.b64decode(body.translate(None, b" \t\r\n"), validate=True)
        except binascii.Error as error:
            raise _FileUnavailable("file_encoding") from error
    if encoding == "quoted-printable":
        if re.search(rb"=(?![0-9A-Fa-f]{2}|\r?\n)", body):
            raise _FileUnavailable("file_encoding")
        return quopri.decodestring(body)
    if encoding not in {"7bit", "8bit", "binary"} or (encoding == "7bit" and not body.isascii()):
        raise _FileUnavailable("file_encoding")
    return body


class _FileExtractor:
    def __init__(self) -> None:
        self.parts = 0
        self.decoded = 0
        self.files: list[ExtractedFile] = []

    def entity(self, raw: bytes, ancestors: tuple[str, ...] = ()) -> None:
        self.parts += 1
        if self.parts > 64 or len(ancestors) >= 8:
            raise _FileUnavailable("file_structure")
        headers, body, filename = _file_headers(raw)
        content_type = headers.get_content_type()
        attached = headers.get_content_disposition() not in {None, "inline"} or filename is not None
        encoding = headers.get("Content-Transfer-Encoding", "7bit").lower().strip()
        if not attached and headers.get_content_maintype() == "multipart":
            if content_type not in {
                "multipart/mixed",
                "multipart/alternative",
                "multipart/related",
            }:
                raise _FileUnavailable("file_structure")
            if encoding not in {"7bit", "8bit", "binary"}:
                raise _FileUnavailable("file_encoding")
            boundary = headers.get_boundary()
            if boundary is None:
                raise _FileUnavailable("file_structure")
            children = _children(body, boundary, ancestors)
            if content_type == "multipart/related" and headers.get_param("start") is not None:
                first, _, _ = _headers(children[0])
                if headers.get_param("start") != first.get("Content-ID"):
                    raise _FileUnavailable("file_structure")
            for child in children:
                self.entity(child, (*ancestors, boundary))
            return
        if not attached and content_type in {"text/plain", "text/html"}:
            return
        if len(self.files) >= 20:
            raise _FileUnavailable("file_count")
        if headers.get_content_maintype() in {"multipart", "message"}:
            raise _FileUnavailable("file_type")
        if filename is None:
            raise _FileUnavailable("file_filename")
        try:
            validate_filename(filename)
        except IdentityError as error:
            raise _FileUnavailable("file_filename") from error
        content = _file_content(body, encoding)
        self.decoded += len(content)
        if not 1 <= len(content) <= 10485760 or self.decoded > MAX_RAW_BYTES:
            raise _FileUnavailable("file_size")
        try:
            actual_type = media_type(BytesIO(content), filename)
        except IdentityError as error:
            raise _FileUnavailable("file_type") from error
        self.files.append(ExtractedFile(filename, actual_type, content))


def extract_files(raw: bytes) -> ExtractedFiles:
    """Interpret one bounded ordered original-file set, without publishing it."""
    try:
        if not isinstance(raw, bytes) or not 1 <= len(raw) <= MAX_RAW_BYTES:
            raise _FileUnavailable("file_structure")
        extractor = _FileExtractor()
        extractor.entity(raw)
        return ExtractedFiles("complete", tuple(extractor.files))
    except _FileUnavailable as error:
        return ExtractedFiles("unavailable", reason=str(error))
    except (ValueError, LookupError, RecursionError, HeaderParseError):
        return ExtractedFiles("unavailable", reason="file_structure")
