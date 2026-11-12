"""Integrity and secret/TLS boundary; real S3 permissions live in the packaged proof."""

import hashlib
import io
from types import SimpleNamespace

import pytest
from altvia import file_storage, file_storage_owner
from altvia.file_settings import StorageSettings
from altvia.file_storage import S3Store, StorageError
from botocore.stub import Stubber
from pydantic import ValidationError
from urllib3.exceptions import ProtocolError, ReadTimeoutError


@pytest.mark.parametrize(
    "raw",
    [
        b'<!DOCTYPE r [<!ENTITY x "expanded">]><r>&x;</r>',
        b'<!DOCTYPE r SYSTEM "file:///etc/passwd"><r/>',
        b"<r>" * 22000,
    ],
)
def test_owner_admin_xml_refuses_entities_dtd_and_oversized_replies(raw):
    with pytest.raises(ValueError, match="storage_bootstrap_refused"):
        file_storage_owner.parse_admin_reply(raw)


def test_owner_admin_xml_parses_bounded_normal_native_reply():
    assert (
        file_storage_owner.parse_admin_reply(b"<ListUserAccountsResult/>").tag
        == "ListUserAccountsResult"
    )


def settings(tmp_path, **changes):
    ca = tmp_path / "ca"
    ca.write_text("not a real CA; no network in these unit cases")
    return StorageSettings(
        endpoint="https://storage:8443",
        ca_file=ca,
        access_key="synthetic-api",
        secret_key="synthetic-secret-value",
        **changes,
    )


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://storage",
        "https://user:secret@storage",
        "https://storage/path",
        "https://storage?x=1",
        "https://storage/#x",
    ],
)
def test_settings_refuse_non_tls_or_ambiguous_endpoints(tmp_path, endpoint):
    with pytest.raises(ValidationError):
        StorageSettings(endpoint=endpoint, ca_file=tmp_path, access_key="a", secret_key="b")


def test_storage_settings_and_sdk_do_not_disclose_or_lookup_ambient_credentials(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "ambient-must-not-be-used")
    config = settings(tmp_path)
    assert "synthetic-secret-value" not in repr(config)
    assert "synthetic-api" not in repr(config)
    store = S3Store(config)
    assert store.client.meta.config.signature_version == "s3v4"
    assert store.client.meta.config.retries["total_max_attempts"] == 1
    assert store.client.meta.config.s3["addressing_style"] == "path"
    assert store.client.meta.config.s3["payload_signing_enabled"]


@pytest.mark.parametrize(
    "data,size,digest",
    [
        (b"short", 6, hashlib.sha256(b"short").hexdigest()),
        (b"long", 3, hashlib.sha256(b"long").hexdigest()),
        (b"body", 4, "0" * 64),
    ],
)
def test_put_checks_actual_source_before_network(tmp_path, data, size, digest):
    store = S3Store(settings(tmp_path))
    with Stubber(store.client), pytest.raises(StorageError, match="storage_integrity"):
        store.put_new("objects/" + "1" * 64, io.BytesIO(data), size=size, sha256=digest)


@pytest.mark.parametrize(
    "key", ["../secret", "objects/a", "objects/" + "A" * 64, "objects/" + "0" * 64 + "/x"]
)
def test_storage_rejects_nonopaque_or_path_keys(tmp_path, key):
    store = S3Store(settings(tmp_path))
    with pytest.raises(StorageError, match="storage_input"):
        store.put_new(key, io.BytesIO(b"a"), size=1, sha256=hashlib.sha256(b"a").hexdigest())


def test_duplicate_maps_to_fixed_safe_exception(tmp_path):
    store = S3Store(settings(tmp_path))
    with Stubber(store.client) as stub:
        stub.add_client_error(
            "put_object",
            service_error_code="PreconditionFailed",
            service_message="synthetic-secret-value",
            http_status_code=412,
        )
        with pytest.raises(StorageError, match="storage_exists") as caught:
            store.put_new(
                "objects/" + "1" * 64,
                io.BytesIO(b"a"),
                size=1,
                sha256=hashlib.sha256(b"a").hexdigest(),
            )
        assert caught.value.__cause__ is None
        assert "synthetic-secret-value" not in str(caught.value)


@pytest.mark.parametrize("body,length", [(b"short", 6), (b"longer", 4), (b"wrong", 5)])
def test_get_never_yields_corrupt_bytes(tmp_path, body, length):
    store = S3Store(settings(tmp_path))
    with Stubber(store.client) as stub:
        stub.add_response("get_object", {"Body": io.BytesIO(body), "ContentLength": length})
        with pytest.raises(StorageError, match="storage_integrity"):
            with store.verified_spool(
                "objects/" + "1" * 64, size=5, sha256=hashlib.sha256(b"right").hexdigest()
            ):
                pytest.fail("Unverified object escaped")


def test_verified_spool_closes_after_use(tmp_path):
    store = S3Store(settings(tmp_path))
    with Stubber(store.client) as stub:
        stub.add_response("get_object", {"Body": io.BytesIO(b"right"), "ContentLength": 5})
        with store.verified_spool(
            "objects/" + "1" * 64, size=5, sha256=hashlib.sha256(b"right").hexdigest()
        ) as source:
            assert source.read() == b"right"
        assert source.closed


def test_verified_spool_tempfile_failure_has_fixed_safe_error(tmp_path, monkeypatch):
    store = S3Store(settings(tmp_path))

    def unavailable_spool(**_):
        raise OSError("private-path-sentinel")

    monkeypatch.setattr(file_storage.tempfile, "TemporaryFile", unavailable_spool)
    with Stubber(store.client), pytest.raises(StorageError) as caught:
        with store.verified_spool("objects/" + "1" * 64, size=1, sha256="0" * 64):
            pytest.fail("Unavailable spool escaped")
    assert str(caught.value) == "storage_unavailable"
    assert caught.value.__suppress_context__


@pytest.mark.parametrize("error", [OSError("consumer-path"), ValueError("consumer-input")])
def test_verified_spool_does_not_normalize_consumer_errors(tmp_path, error):
    store = S3Store(settings(tmp_path))
    with Stubber(store.client) as stub:
        stub.add_response("get_object", {"Body": io.BytesIO(b"right"), "ContentLength": 5})
        with pytest.raises(type(error)) as caught:
            with store.verified_spool(
                "objects/" + "1" * 64, size=5, sha256=hashlib.sha256(b"right").hexdigest()
            ) as source:
                raise error
        assert caught.value is error
        assert source.closed


@pytest.mark.parametrize(
    "error", [ReadTimeoutError(None, None, "raw-sdk-sentinel"), ProtocolError("raw-sdk-sentinel")]
)
def test_owner_admin_body_transport_failures_have_fixed_safe_error(tmp_path, monkeypatch, error):
    class RawBody:
        def read(self, size):
            assert size == 65537
            raise error

    class Transport:
        closed = False

        def send(self, _):
            return SimpleNamespace(raw=RawBody(), status_code=200)

        def close(self):
            self.closed = True

    transport = Transport()
    monkeypatch.setattr(file_storage_owner, "URLLib3Session", lambda **_: transport)
    with pytest.raises(ValueError) as caught:
        file_storage_owner.admin_request(settings(tmp_path), "list-users")
    assert str(caught.value) == "storage_bootstrap_refused"
    assert caught.value.__suppress_context__
    assert transport.closed
