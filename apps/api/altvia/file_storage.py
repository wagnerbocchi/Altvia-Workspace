"""Bounded immutable standard-SDK PUT and fully verified private GET spools."""

import hashlib
import re
import tempfile
from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from typing import Any, BinaryIO, cast

import botocore.session  # type: ignore[import-untyped]
from botocore.config import Config  # type: ignore[import-untyped]
from botocore.exceptions import BotoCoreError, ClientError  # type: ignore[import-untyped]

from altvia.file_settings import MAX_FILE_BYTES, StorageSettings

BUCKET = "altvia-files"


class StorageError(Exception):
    """Only fixed safe reason strings cross this transport boundary."""


def validate_object(key: str, size: int, digest: str) -> None:
    if (
        not re.fullmatch(r"objects/[0-9a-f]{64}", key)
        or type(size) is not int
        or not 1 <= size <= MAX_FILE_BYTES
        or not re.fullmatch(r"[0-9a-f]{64}", digest)
    ):
        raise StorageError("storage_input")


def s3_client(settings: StorageSettings) -> Any:
    # Explicit credentials prevent the SDK from consulting metadata, environment
    # credential chains or user profiles. No optional native CRT/transfer manager.
    return botocore.session.Session().create_client(
        "s3",
        endpoint_url=settings.endpoint,
        region_name="us-east-1",
        aws_access_key_id=settings.access_key.get_secret_value(),
        aws_secret_access_key=settings.secret_key.get_secret_value(),
        verify=str(settings.ca_file),
        config=Config(
            signature_version="s3v4",
            connect_timeout=2,
            read_timeout=5,
            retries={"total_max_attempts": 1, "mode": "standard"},
            s3={"addressing_style": "path", "payload_signing_enabled": True},
            proxies={},
            request_checksum_calculation="when_required",
            response_checksum_validation="when_required",
        ),
    )


def checked_copy(source: BinaryIO, target: BinaryIO, size: int, digest: str) -> None:
    count, actual = 0, hashlib.sha256()
    while True:
        chunk = source.read(min(65536, size + 1 - count))
        if not chunk:
            break
        count += len(chunk)
        if count > size:
            raise StorageError("storage_integrity")
        actual.update(chunk)
        target.write(chunk)
    if count != size or actual.hexdigest() != digest:
        raise StorageError("storage_integrity")
    target.seek(0)


class S3Store:
    def __init__(self, settings: StorageSettings) -> None:
        self.client = s3_client(settings)

    def close(self) -> None:
        self.client.close()

    def put_new(self, key: str, source: BinaryIO, *, size: int, sha256: str) -> None:
        validate_object(key, size, sha256)
        try:
            with cast(BinaryIO, tempfile.TemporaryFile(mode="w+b")) as spool:
                checked_copy(source, spool, size, sha256)
                self.client.put_object(
                    Bucket=BUCKET,
                    Key=key,
                    Body=spool,
                    ContentLength=size,
                    ContentType="application/octet-stream",
                    IfNoneMatch="*",
                )
        except ClientError as error:
            reason = (
                "storage_exists"
                if error.response.get("ResponseMetadata", {}).get("HTTPStatusCode") == 412
                else "storage_unavailable"
            )
            raise StorageError(reason) from None
        except (BotoCoreError, OSError, ValueError):
            raise StorageError("storage_unavailable") from None

    @contextmanager
    def verified_spool(self, key: str, *, size: int, sha256: str) -> Iterator[BinaryIO]:
        validate_object(key, size, sha256)
        with ExitStack() as resources:
            try:
                spool = resources.enter_context(cast(BinaryIO, tempfile.TemporaryFile(mode="w+b")))
                response = self.client.get_object(Bucket=BUCKET, Key=key)
                body = response["Body"]
                try:
                    if response["ContentLength"] != size:
                        raise StorageError("storage_integrity")
                    checked_copy(body, spool, size, sha256)
                finally:
                    body.close()
            except (BotoCoreError, ClientError, OSError, ValueError):
                raise StorageError("storage_unavailable") from None
            # Consumer errors must not be mistaken for infrastructure errors.
            yield spool
