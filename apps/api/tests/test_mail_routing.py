"""Bounded routing grammar at the owner publication boundary."""

import pytest
from altvia.mail_routing import RoutingError, parse_routing


def raw(headers=""):
    return ("From: Requester <requester@example.test>\r\n" + headers + "\r\nbody").encode()


def test_exact_ids_missing_and_folded_references():
    result = parse_routing(
        raw(
            "Message-ID: "
            "<Case.!#$%&'*+-/=?^_`{|}~@Example.test>\r\nReferences: "
            "<a@b.test>\r\n <B@b.test>\r\n"
        )
    )
    assert result.message_id == "<Case.!#$%&'*+-/=?^_`{|}~@Example.test>"
    assert result.references == ("<a@b.test>", "<B@b.test>")
    assert result.from_email == "requester@example.test"
    assert parse_routing(raw()).message_id is None


@pytest.mark.parametrize(
    "headers",
    [
        "Message-ID: broken\r\n",
        "Message-ID: <a@b.test>\r\nMessage-ID: <b@b.test>\r\n",
        "Message-ID: <a..b@c.test>\r\n",
        "Message-ID: <a@-b.test>\r\n",
        "Message-ID: <a@[127.0.0.1]>\r\n",
        "Message-ID: <a@b.test> (comment)\r\n",
        "In-Reply-To: <a@b.test> <b@b.test>\r\n",
        "References: " + "<a@b.test> " * 65 + "\r\n",
        "X-Altvia-Thread: " + "A" * 64 + "\r\n",
        "Auto-Submitted: auto-replied\r\n",
        "Return-Path: <>\r\n",
        "Content-Type: multipart/report; report-type=delivery-status\r\n",
        "Reply-To: stranger@example.test\r\n",
        "From: requester@example.test\r\n",
        "Sender: requester@example.test, stranger@example.test\r\n",
    ],
)
def test_hostile_routing_refuses_fixed_error(headers):
    with pytest.raises(RoutingError, match="^invalid_routing$"):
        parse_routing(raw(headers))


@pytest.mark.parametrize(
    "value", [b"bad", b"From: a@b.test\r\nX: " + b"x" * 2049 + b"\r\n\r\nx", raw("X: a\r\n" * 101)]
)
def test_root_bounds(value):
    with pytest.raises(RoutingError):
        parse_routing(value)


@pytest.mark.parametrize(
    "headers",
    [
        "Message-ID: <a@" + "b" * 64 + ".test>\r\n",
        "Message-ID: <" + "a" * 309 + "@example.test>\r\n",
        "Message-ID: <a@" + ".".join(["a" * 63] * 4) + ">\r\n",
        "Message-ID: <>\r\n",
        "Message-ID: <a @b.test>\r\n",
        "References: <a@b.test><b@b.test>\r\n",
        "References: \r\n",
        "In-Reply-To: (comment) <a@b.test>\r\n",
        "Message-ID: <\u00e9@b.test>\r\n",
        "X-Altvia-Thread: " + "a" * 64 + "\r\nX-Altvia-Thread: " + "a" * 64 + "\r\n",
        "Return-Path: (hidden)<>\r\n",
        "Return-Path: < >\r\n",
        "Sender: requester@example.test\r\nSender: requester@example.test\r\n",
    ],
)
def test_additional_finite_bounds(headers):
    with pytest.raises(RoutingError, match="^invalid_routing$"):
        parse_routing(raw(headers))


def test_maximum_identifier_domain_and_reference_bounds():
    primary = "<" + "a" * 53 + "@" + ".".join(["b" * 63] * 3 + ["b" * 61]) + ">"
    assert len(primary) == 309
    fields = "Message-ID: " + primary + "\r\nReferences: " + " ".join(["<a@b.test>"] * 64) + "\r\n"
    result = parse_routing(raw(fields))
    assert result.message_id == primary and len(result.references) == 64
