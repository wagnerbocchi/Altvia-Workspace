"""Hostile MIME normalization without network, rendering or identity inference."""

import base64

import pytest
from altvia.mail_mime import normalize


def message(body=b"hello", headers=b"Content-Type: text/plain; charset=utf-8"):
    return headers + b"\r\n\r\n" + body


def multipart(parts, kind="mixed", boundary="test-boundary", extra=b""):
    token = boundary.encode()
    return message(
        b"preamble\r\n"
        + b"".join(b"--" + token + b"\r\n" + part + b"\r\n" for part in parts)
        + b"--"
        + token
        + b"--\r\nepilogue",
        f'Content-Type: multipart/{kind}; boundary="{boundary}"'.encode() + extra,
    )


def test_utf8_subject_and_strict_encoded_plain_text():
    mail = normalize(
        message(
            base64.b64encode("Ola, acao: olá!".encode()),
            b"Subject: =?utf-8?b?T2zDoSE=?=\r\nContent-Type: text/plain; charset=utf-8\r\n"
            b"Content-Transfer-Encoding: base64",
        )
    )
    assert mail.status == "ready" and mail.subject == "Olá!"
    assert mail.body_text == "Ola, acao: olá!"
    assert (mail.part_count, mail.attachment_count, mail.reason) == (1, 0, None)


def test_alternative_prefers_plain_and_html_fallback_has_no_markup_or_active_content():
    html = message(
        b"<p>Hello &amp; world</p><script>secret()</script><svg>hidden</svg>"
        b'<img src="https://invalid.example/private"><a href="javascript:x">Visible</a>',
        b"Content-Type: text/html; charset=utf-8",
    )
    fallback = normalize(html)
    assert fallback.status == "ready"
    assert "Hello & world" in fallback.body_text and "Visible" in fallback.body_text
    assert all(
        s not in fallback.body_text for s in ("secret", "hidden", "https", "<img", "javascript")
    )
    plain = message(b"Plain wins")
    assert normalize(multipart([html, plain], "alternative")).body_text == "Plain wins"


def test_mixed_attachments_and_nested_related_never_become_body():
    attached = message(b"Do not use", b'Content-Type: text/plain; name="secret.txt"')
    forwarded = message(b"Subject: private\r\n\r\nattached", b"Content-Type: message/rfc822")
    root = message(b"<p>Root</p>", b"Content-Type: text/html\r\nContent-ID: <root>")
    related = multipart(
        [root, message(b"opaque", b"Content-Type: image/png")], "related", extra=b'; start="<root>"'
    )
    result = normalize(
        multipart([message(b"First"), attached, forwarded, related], boundary="outer")
    )
    assert result.status == "ready" and result.body_text == "First\n\nRoot"
    assert result.part_count == 7 and result.attachment_count == 3


@pytest.mark.parametrize(
    "charset,body,expected",
    [
        ("windows-1252", b"=93Ol=E1=94", "“Olá”"),
        ("iso-8859-1", b"Ol=E1", "Olá"),
        ("us-ascii", b"plain=20text", "plain text"),
    ],
)
def test_quoted_printable_charset_aliases(charset, body, expected):
    result = normalize(
        message(
            body,
            f"Content-Type: text/plain; charset={charset}\r\n"
            "Content-Transfer-Encoding: quoted-printable".encode(),
        )
    )
    assert result.status == "ready" and result.body_text == expected


def test_controls_and_line_endings_are_normalized_without_identity():
    body = "a\x00\x1b\r\nb\t\u202ec\u2066d\u2069".encode()
    result = normalize(
        message(
            body,
            b"From: victim@example.test\r\nReply-To: other@example.test\r\n"
            b"Content-Type: text/plain; charset=utf-8\r\nContent-Transfer-Encoding: 8bit",
        )
    )
    assert result.body_text == "a\nb\tcd"
    assert not hasattr(result, "sender")


@pytest.mark.parametrize(
    "raw",
    [
        b"",
        b"no separator",
        b"x" * (2097152 + 1),
        message(b"x", b"Content-Type: text/plain\r\nContent-Type: text/html"),
        message(b"x", b"Content-Transfer-Encoding: gzip"),
        message(b"%%%", b"Content-Transfer-Encoding: base64"),
        message(b"=ZZ", b"Content-Transfer-Encoding: quoted-printable"),
        message(b"\xff", b"Content-Type: text/plain; charset=utf-8"),
        message(b"x", b"Content-Type: text/plain; charset=utf-7"),
        message(b"x", b"Subject: " + b"a" * 2050),
        message(b"x", b"Subject: " + b"a" * 999),
        message(b"x", b"X-Test: x\r\n" * 101),
        message(b"x", b"X-Test: " + b"x" * 1800 + (b"\r\n " + b"x" * 1800) * 10),
        message(b"body", b"Content-Type: multipart/mixed; boundary=x"),
        multipart([message()], "encrypted"),
        multipart([message()], "related", extra=b'; start="<absent>"'),
        message(b"opaque", b"Content-Type: application/octet-stream"),
        message(b"x" * 65537),
        message(b"<br>" * 4097, b"Content-Type: text/html"),
        message(b"<div>" * 65 + b"x" + b"</div>" * 65, b"Content-Type: text/html"),
    ],
)
def test_hostile_or_unsupported_messages_reject_without_partial_text(raw):
    result = normalize(raw)
    assert result.status == "rejected" and result.reason
    assert (
        result.subject is result.body_text is result.part_count is result.attachment_count is None
    )
    assert len(result.reason) <= 32 and "private" not in result.reason


def test_structure_limits_apply_before_building_unbounded_children():
    assert normalize(multipart([message()] * 64)).status == "rejected"
    assert normalize(multipart([message()] * 63)).part_count == 64
    raw = message()
    for _ in range(7):
        raw = multipart([raw], boundary=f"nested-{_}")
    assert normalize(raw).status == "ready"
    assert normalize(multipart([raw], boundary="overflow")).status == "rejected"


def test_decoded_total_budget_counts_unselected_alternatives():
    parts = [message(b"x" * 40000) for _ in range(7)]
    assert normalize(multipart(parts, "alternative")).status == "rejected"


def test_lf_headers_and_body_size_exact_boundary():
    result = normalize(b"Subject: plain\n\n" + b"x" * 65536)
    assert result.status == "ready" and len(result.body_text) == 65536


def test_duplicate_boundaries_and_missing_close_do_not_select_partial_content():
    raw = multipart([multipart([message()], boundary="same")], boundary="same")
    assert normalize(raw).status == "rejected"
    assert (
        normalize(multipart([message()]).replace(b"--test-boundary--", b"not-close")).status
        == "rejected"
    )


def test_unrecognized_disposition_is_opaque_attachment():
    unknown = message(
        b"Do not use", b"Content-Type: text/plain\r\nContent-Disposition: custom-kind"
    )
    result = normalize(multipart([message(b"Visible"), unknown]))
    assert result.status == "ready" and result.body_text == "Visible"
    assert result.attachment_count == 1


def test_numeric_date_overflow_is_a_fixed_all_or_nothing_rejection():
    raw = message(
        b"Visible",
        b"Date: Wed, 1 Jan 999999999999999999999999999999 "
        b"00:00:00 +0000\r\nContent-Type: text/plain",
    )
    result = normalize(raw)
    assert result.status == "rejected" and result.reason == "invalid_headers"
    assert result.body_text is result.subject is None


@pytest.mark.parametrize(
    "body",
    [
        b"<div><template></div>hidden-template</template><p>Visible</p>",
        b"<div><object></div>hidden-object</object><p>Visible</p>",
        b"<div><svg></div>hidden-svg</svg><p>Visible</p>",
        b"<script/>hidden-script<p>Visible</p>",
        b"<template/>hidden-template<p>Visible</p>",
    ],
)
def test_malformed_active_subtrees_never_release_hidden_text(body):
    result = normalize(message(body, b"Content-Type: text/html"))
    assert result.status == "rejected" and result.subject is result.body_text is None


@pytest.mark.parametrize(
    "word",
    [
        b"=?utf-7?q?+AOk-?=",
        b"=?rot13?q?secret?=",
        b"=?unknown-codec?q?secret?=",
    ],
)
def test_subject_unsupported_codecs_reject_without_partial_content(word):
    result = normalize(message(b"Visible", b"Subject: " + word))
    assert result.status == "rejected" and result.reason == "unsupported_charset"
    assert result.subject is result.body_text is None


@pytest.mark.parametrize(
    "word,expected",
    [
        (b"=?UTF8?b?T2zDoSE=?=", "Olá!"),
        (b"=?latin1?q?Ol=E1?=", "Olá"),
        (b"=?windows-1252?q?=93Ol=E1=94?=", "“Olá”"),
        (b"=?us-ascii?q?plain_text?=", "plain text"),
        (b"=?utf-8?q?Ol=C3=A1_?=\r\n =?UTF8?b?YcOnw6Nv?=", "Olá ação"),
    ],
)
def test_subject_supported_aliases_and_folded_words_decode_strictly(word, expected):
    result = normalize(message(b"Visible", b"Subject: " + word))
    assert result.status == "ready" and result.subject == expected


@pytest.mark.parametrize("subject", [b"=?utf-8?b?/w==?=", "Unencoded café".encode()])
def test_subject_invalid_encoded_or_unencoded_international_bytes_reject(subject):
    result = normalize(message(b"Visible", b"Subject: " + subject))
    assert result.status == "rejected" and result.subject is result.body_text is None


@pytest.mark.parametrize(
    "tokens",
    [
        b"</p>" * 4096,
        b"<p>x</p>" * 2048,
        b"<i/>" * 4096,
        b"<br>" * 4096,
    ],
)
def test_html_exact_real_token_budget_and_single_self_closing_count(tokens):
    assert normalize(message(b"Visible" + tokens, b"Content-Type: text/html")).status == "ready"
    result = normalize(message(b"Visible" + tokens + b"</void>", b"Content-Type: text/html"))
    assert result.status == "rejected" and result.reason == "html_limit"
    assert result.subject is result.body_text is None


@pytest.mark.parametrize(
    "subject",
    [
        b"=?utf-8?b?a?=",
        b"raw-\xff =?ascii?q?ok?=",
        b"=?ascii?q?ok?= raw-\xff",
        b"=?ascii?q?ok?=\r\n raw-\xc3\xa9",
        b"=?utf-8?b?SG!VsbG8=?=",
        b"=?utf-8?q?=C3?= =?utf-8?q?=A9?=",
        b"=?utf-8?b?ww==?= =?utf-8?b?qQ==?=",
        b"=?ascii?q?bad=ZZ?=",
    ],
)
def test_subject_malformed_words_and_raw_bytes_reject_before_lossy_assembly(subject):
    result = normalize(message(b"Visible", b"Subject: " + subject))
    assert result.status == "rejected" and result.subject is result.body_text is None


def test_each_repeated_header_value_is_validated():
    raw = message(
        b"Visible",
        b"Date: Wed, 1 Jan 2025 00:00:00 +0000\r\n"
        b"Date: Wed, 1 Jan 999999999999999999999999999999 00:00:00 +0000",
    )
    result = normalize(raw)
    assert result.status == "rejected" and result.reason == "invalid_headers"
    valid = message(b"Visible", b"X-Trace: one\r\nX-Trace: two")
    assert normalize(valid).status == "ready"
