"""Private file interpretation is strict, bounded and independent of parser2 text."""

import base64
from dataclasses import FrozenInstanceError

import pytest
from altvia import mail_mime
from test_mail_mime import message, multipart


def file_part(
    content=b"%PDF-1.7\noriginal",
    name=b'filename="report.pdf"',
    encoding="base64",
    declared="application/pdf",
):
    if encoding == "base64":
        content = base64.encodebytes(content)
    elif encoding == "quoted-printable":
        # Encode line endings too: text-oriented encoders can canonicalize them.
        content = b"".join(f"={byte:02X}".encode() for byte in content)
    return message(
        content,
        f"Content-Type: {declared}\r\nContent-Transfer-Encoding: {encoding}".encode()
        + b"\r\nContent-Disposition: attachment; "
        + name,
    )


def extract(raw):
    # Missing implementation is an ordinary assertion failure in the RED run.
    assert hasattr(mail_mime, "extract_files"), "pure file extraction is not implemented"
    before = mail_mime.normalize(raw)
    result = mail_mime.extract_files(raw)
    assert mail_mime.normalize(raw) == before
    return result


def unavailable(raw, reason):
    result = extract(raw)
    assert result.status == "unavailable"
    assert result.files == ()
    assert result.reason == reason


def test_pdf_rfc2231_preserves_original_bytes_and_existing_parser2_text():
    raw = multipart([message(b"Visible body"), file_part(name=b"filename*=UTF8''caf%C3%A9.pdf")])
    assert mail_mime.normalize(raw) == mail_mime.NormalizedMail("ready", "", "Visible body", 3, 1)
    result = extract(raw)
    assert result.status == "complete" and result.reason is None
    assert len(result.files) == 1
    item = result.files[0]
    assert (item.filename, item.media_type, item.content) == (
        "caf\u00e9.pdf",
        "application/pdf",
        b"%PDF-1.7\noriginal",
    )
    with pytest.raises(FrozenInstanceError):
        item.filename = "changed.pdf"
    with pytest.raises(FrozenInstanceError):
        result.files = ()


@pytest.mark.parametrize(
    "name,content,actual",
    [
        ("a.pdf", b"%PDF-1.7\x00\xff", "application/pdf"),
        ("a.png", b"\x89PNG\r\n\x1a\n\x00\xff", "image/png"),
        ("a.jpg", b"\xff\xd8\xff\x00", "image/jpeg"),
        ("a.jpeg", b"\xff\xd8\xff\x00", "image/jpeg"),
        ("a.txt", "caf\u00e9\n".encode(), "text/plain"),
        ("a.log", b"\xef\xbb\xbfplain log\n", "text/plain"),
    ],
)
@pytest.mark.parametrize("encoding", ["base64", "quoted-printable", "8bit", "binary"])
def test_supported_actual_types_and_transfer_encodings(name, content, actual, encoding):
    result = extract(
        file_part(
            content, f'filename="{name}"'.encode(), encoding, declared="application/octet-stream"
        )
    )
    assert result.status == "complete" and result.reason is None
    assert [(f.filename, f.media_type, f.content) for f in result.files] == [
        (name, actual, content)
    ]


@pytest.mark.parametrize("encoding", ["7bit", "8bit", "binary", "base64", "quoted-printable"])
def test_ascii_file_transfer_encodings(encoding):
    result = extract(file_part(b"a=1\r\nb=2", b'filename="a.log"', encoding))
    assert result.status == "complete" and result.files[0].content == b"a=1\r\nb=2"


def test_traverses_every_inline_branch_in_order_without_deduplication():
    first = file_part(b"one", b'filename="a.txt"')
    second = file_part(b"two", b'filename="a.txt"')
    raw = multipart(
        [
            multipart([message(), first], "alternative", boundary="alt"),
            multipart([message(), second], "related", boundary="related"),
        ]
    )
    assert [f.content for f in extract(raw).files] == [b"one", b"two"]


def test_twenty_files_and_no_file_text_are_complete():
    result = extract(multipart([file_part()] * 20))
    assert result.status == "complete" and len(result.files) == 20
    result = extract(message())
    assert (result.status, result.files, result.reason) == ("complete", (), None)


def test_twenty_first_candidate_discards_entire_set():
    unavailable(multipart([file_part()] * 21), "file_count")


@pytest.mark.parametrize(
    "bad,reason",
    [
        (file_part(b""), "file_size"),
        (file_part(b"not a pdf"), "file_type"),
        (file_part(b"PK\x03\x04", b'filename="a.zip"'), "file_type"),
        (file_part(b"<html>unsafe", b'filename="a.txt"'), "file_type"),
        (file_part(b"\xff", b'filename="a.txt"'), "file_type"),
        (file_part(b"a\x00b", b'filename="a.txt"'), "file_type"),
        (message(b"Subject: nested\r\n\r\nx", b"Content-Type: message/rfc822"), "file_type"),
        (
            multipart(
                [file_part()],
                boundary="attached",
                extra=b'\r\nContent-Disposition: attachment; filename="a.pdf"',
            ),
            "file_type",
        ),
        (
            message(
                b"%%%",
                b"Content-Type: application/pdf\r\nContent-Disposition: attachment; "
                b"filename=a.pdf\r\nContent-Transfer-Encoding: base64",
            ),
            "file_encoding",
        ),
        (
            message(
                b"=ZZ",
                b"Content-Type: application/pdf\r\nContent-Disposition: attachment; "
                b"filename=a.pdf\r\nContent-Transfer-Encoding: quoted-printable",
            ),
            "file_encoding",
        ),
        (file_part(encoding="gzip"), "file_encoding"),
        (file_part(b"%PDF-\xff", encoding="7bit"), "file_encoding"),
        (message(b"%PDF-", b"Content-Type: application/pdf"), "file_filename"),
    ],
)
def test_one_bad_candidate_never_returns_partial_files(bad, reason):
    unavailable(multipart([message(), file_part(), bad]), reason)


@pytest.mark.parametrize(
    "name",
    [
        b'filename="../x.pdf"',
        b'filename="x\\\\y.pdf"',
        b'filename=".hidden.pdf"',
        b'filename=" x.pdf"',
        b'filename="x.pdf "',
        b'filename="x.pdf."',
        b'filename=""',
        b'filename="' + b"x" * 252 + b'.pdf"',
        b"filename*=UTF8''x%E2%80%AE.pdf",
        b"filename*=UTF8''x%00.pdf",
    ],
)
def test_unsafe_names_use_core_policy_without_trimming(name):
    unavailable(file_part(name=name), "file_filename")


@pytest.mark.parametrize(
    "parameter,expected",
    [
        (b'filename="plain.pdf"', "plain.pdf"),
        (b"filename*=UTF8''caf%C3%A9.pdf", "caf\u00e9.pdf"),
        (b"filename*=utf-8'pt-BR'caf%C3%A9.pdf", "caf\u00e9.pdf"),
        (b"filename*=latin1''caf%E9.pdf", "caf\u00e9.pdf"),
        (b"filename*=windows-1252'en'%93file%94.pdf", "\u201cfile\u201d.pdf"),
        (b"filename*=us-ascii''plain.pdf", "plain.pdf"),
        (b'filename="semi;colon.pdf"', "semi;colon.pdf"),
        (b'filename="say\\"hi.pdf"', 'say"hi.pdf'),
    ],
)
def test_finite_parameter_names_decode_strictly(parameter, expected):
    result = extract(file_part(name=parameter))
    assert result.status == "complete" and result.files[0].filename == expected


def test_type_name_alone_or_agreeing_disposition_filename_is_accepted():
    content = b"%PDF-1"
    for extra in (b"", b"\r\nContent-Disposition: inline; filename*=UTF8''caf%C3%A9.pdf"):
        raw = message(
            content,
            b"Content-Type: application/pdf; name*=UTF8''caf%C3%A9.pdf"
            b"\r\nContent-Transfer-Encoding: 7bit" + extra,
        )
        assert extract(raw).files[0].filename == "caf\u00e9.pdf"


def test_plain_type_name_and_inline_filename_are_candidates():
    raw = message(b"plain", b"Content-Type: text/plain; name=a.log")
    assert extract(raw).files[0].content == b"plain"
    raw = message(
        b"plain", b"Content-Type: text/plain\r\nContent-Disposition: inline; filename=a.log"
    )
    assert extract(raw).files[0].filename == "a.log"


@pytest.mark.parametrize(
    "parameter",
    [
        b"filename*=UTF8''bad%.pdf",
        b"filename*=UTF8''bad%GG.pdf",
        b"filename*=UTF8''bad%C3.pdf",
        b"filename*=ascii''bad%FF.pdf",
        b"filename*=windows-1252''bad%81.pdf",
        b"filename*=utf-7''file.pdf",
        b"filename*=unknown''file.pdf",
        b"filename*=UTF8'bad_tag'file.pdf",
        b"filename*=UTF8'" + b"a" * 36 + b"'file.pdf",
        b"filename*=UTF8'file.pdf",
        b"filename*=UTF8''bad%00.pdf; filename=x.pdf",
        b'filename="a.pdf"; filename="a.pdf"',
        b"filename=a.pdf; filename*=UTF8''a.pdf",
        b"filename*0*=UTF8''a; filename*1*=.pdf",
        b"filename*0=a; filename*1=.pdf",
        b'filename="=?utf-8?b?YS5wZGY=?="',
        b'filename="caf\xc3\xa9.pdf"',
        b'filename="unterminated.pdf',
        b"filename",
        b"filename=a.pdf; broken",
    ],
)
def test_ambiguous_or_unsupported_parameter_forms_are_unavailable(parameter):
    unavailable(file_part(name=parameter), "file_parameter")


def test_conflicting_cross_header_names_are_unavailable():
    raw = file_part().replace(
        b"Content-Type: application/pdf", b"Content-Type: application/pdf; name=other.pdf"
    )
    unavailable(raw, "file_parameter")


@pytest.mark.parametrize(
    "encoding,body",
    [
        ("base64", b"abc"),
        ("base64", b"YWJj!"),
        ("base64", b"YW=Jj"),
        ("quoted-printable", b"bad="),
        ("quoted-printable", b"bad=A"),
        ("quoted-printable", b"bad=\rX"),
    ],
)
def test_malformed_transfer_encoding_is_not_repaired(encoding, body):
    raw = message(
        body,
        f"Content-Transfer-Encoding: {encoding}\r\nContent-Type: application/pdf".encode()
        + b"\r\nContent-Disposition: attachment; filename=a.pdf",
    )
    unavailable(raw, "file_encoding")


def test_base64_whitespace_and_quoted_printable_soft_breaks_preserve_bytes():
    prefix = b"Content-Disposition: attachment; filename=a.pdf\r\nContent-Transfer-Encoding: "
    assert extract(message(b"J V B\tE\r\nRi0=", prefix + b"base64")).files[0].content == b"%PDF-"
    assert (
        extract(message(b"%PD=\r\nF-", prefix + b"quoted-printable")).files[0].content == b"%PDF-"
    )


@pytest.mark.parametrize(
    "raw",
    [
        b"",
        b"no separator",
        b"x" * 2097153,
        message(b"x", b"Content-Type: text/plain\r\nContent-Type: text/html"),
        message(b"x", b"X-Test: " + b"x" * 2049),
        message(b"x", b"X-Test: x\r\n" * 101),
        message(b"x", b"X-Test: " + b"x" * 1800 + (b"\r\n " + b"x" * 1800) * 10),
        multipart([message()], "encrypted"),
        multipart([message()]).replace(b"--test-boundary--", b"missing"),
        multipart([multipart([message()], boundary="same")], boundary="same"),
        multipart([message()] * 64),
        message(b"x", b"Content-Type: multipart/mixed"),
        multipart([message()], "related", extra=b'; start="<absent>"'),
        multipart([message()], boundary="x" * 71),
    ],
)
def test_structure_and_raw_limits_discard_file_set(raw):
    unavailable(raw, "file_structure")


def test_exact_raw_entity_depth_and_header_boundaries():
    raw = file_part(b"%PDF-", encoding="binary")
    raw += b"x" * (2097152 - len(raw))
    result = extract(raw)
    assert result.status == "complete" and len(result.files[0].content) < 2097152
    unavailable(raw + b"x", "file_structure")
    assert extract(multipart([message()] * 63)).status == "complete"
    raw = message()
    for depth in range(7):
        raw = multipart([raw], boundary=f"depth-{depth}")
    assert extract(raw).status == "complete"
    unavailable(multipart([raw], boundary="overflow"), "file_structure")
    assert extract(message(b"x", b"X: " + b"a" * 2044)).status == "complete"
    assert extract(message(b"x", b"X: x\r\n" * 100)).status == "complete"
    # Exactly 16384 header bytes with physical lines <=2048 and <=100 fields.
    block = b"X: " + b"a" * 2044 + (b"\r\n " + b"a" * 2044) * 7 + b"\r\n " + b"a" * 5
    assert len(block) == 16384
    assert extract(message(b"x", block)).status == "complete"
    unavailable(message(b"x", block + b"a"), "file_structure")
