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
