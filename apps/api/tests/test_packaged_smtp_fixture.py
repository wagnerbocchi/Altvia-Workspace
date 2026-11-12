"""Exercise the trusted packaged relay over actual verified loopback TLS."""

import importlib.util
import time
from pathlib import Path
from threading import Thread

import pytest
from altvia.smtp_transport import ActiveTransports, transmit
from test_smtp_transport import certificate, frozen

__all__ = ["certificate"]


@pytest.mark.parametrize(
    "mode,expected", [("accepted", "accepted"), ("lost", "data_unknown"), ("held", "data_unknown")]
)
def test_packaged_relay_final_result(certificate, mode, expected):
    path = Path(__file__).resolve().parents[3] / "scripts/packaged_smtp_fixture.py"
    spec = importlib.util.spec_from_file_location("packaged_smtp_fixture", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    item = frozen()
    with module.synthetic_relay(*certificate, mode=mode, port=0) as relay:
        from altvia.mail_settings import SMTPAccount

        account = SMTPAccount(
            source_id=item.delivery_id,
            host="localhost",
            port=relay.server_address[1],
            tls_mode="implicit",
            username="synthetic",
            password="synthetic",
            from_email="support@example.test",
            ca_file=certificate[0],
        )
        if mode == "held":
            active, results = ActiveTransports(), []
            thread = Thread(
                target=lambda: results.append(transmit(account, item, lambda: True, active=active))
            )
            thread.start()
            assert relay.received.wait(3)
            began = time.monotonic()
            active.cancel()
            thread.join(2)
            assert not thread.is_alive() and time.monotonic() - began < 2
            assert results == [expected]
        else:
            assert transmit(account, item, lambda: True) == expected
        assert relay.messages == [item.wire]
        assert relay.envelopes == [(item.envelope_from, item.envelope_to)]
        assert relay.data_count == 1
        if mode == "accepted":
            assert relay.accepted_reply.wait(2)
        assert relay.final_250_count == (mode == "accepted")
