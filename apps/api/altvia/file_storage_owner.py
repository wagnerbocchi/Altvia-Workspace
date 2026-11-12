"""Finite owner-only native S3 bootstrap; never rotates or resets existing state."""

import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from botocore.auth import S3SigV4Auth  # type: ignore[import-untyped]
from botocore.awsrequest import AWSRequest  # type: ignore[import-untyped]
from botocore.credentials import Credentials  # type: ignore[import-untyped]
from botocore.exceptions import BotoCoreError, ClientError  # type: ignore[import-untyped]
from botocore.httpsession import URLLib3Session  # type: ignore[import-untyped]
from defusedxml import ElementTree as SafeET  # type: ignore[import-untyped]
from defusedxml.common import DefusedXmlException  # type: ignore[import-untyped]
from urllib3.exceptions import HTTPError as HTTPTransportError

from altvia.file_settings import StorageSettings
from altvia.file_storage import BUCKET, s3_client


def parse_admin_reply(raw: bytes) -> ET.Element:
    from typing import cast

    if len(raw) > 65536:
        raise ValueError("storage_bootstrap_refused")
    try:
        return cast(
            ET.Element,
            SafeET.fromstring(raw, forbid_dtd=True, forbid_entities=True, forbid_external=True),
        )
    except (ET.ParseError, DefusedXmlException):
        raise ValueError("storage_bootstrap_refused") from None


def load_storage(path: Path) -> StorageSettings:
    try:
        with path.open("rb") as stream:
            raw = stream.read(8193)
        if len(raw) > 8192:
            raise ValueError
        return StorageSettings.model_validate_json(raw)
    except (OSError, ValueError):
        raise ValueError("invalid_storage_configuration") from None


def bucket_policy(api: str, scanner: str) -> dict[str, Any]:
    objects = f"arn:aws:s3:::{BUCKET}/objects/*"
    principals = {"AWS": [api, scanner]}
    return {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Principal": principals,
                "Action": "s3:GetObject",
                "Resource": objects,
            },
            {
                "Effect": "Allow",
                "Principal": {"AWS": api},
                "Action": "s3:PutObject",
                "Resource": objects,
                "Condition": {"StringEquals": {"s3:if-none-match": "*"}},
            },
            {
                "Effect": "Deny",
                "Principal": principals,
                "Action": "s3:PutObject",
                "Resource": objects,
                "Condition": {"StringNotEquals": {"s3:if-none-match": "*"}},
            },
            {
                "Effect": "Deny",
                "Principal": {"AWS": scanner},
                "Action": "s3:PutObject",
                "Resource": objects,
            },
            {
                "Effect": "Deny",
                "Principal": principals,
                "Action": [
                    "s3:Delete*",
                    "s3:List*",
                    "s3:PutBucket*",
                    "s3:PutObjectAcl",
                    "s3:PutObjectTagging",
                    "s3:AbortMultipartUpload",
                ],
                "Resource": [f"arn:aws:s3:::{BUCKET}", f"arn:aws:s3:::{BUCKET}/*"],
            },
        ],
    }


def admin_request(settings: StorageSettings, operation: str, body: bytes = b"") -> bytes:
    if operation not in ("list-users", "create-user", "list-buckets"):
        raise ValueError("invalid_storage_admin_operation")
    request = AWSRequest(method="PATCH", url=f"{settings.endpoint}/_owner/{operation}", data=body)
    request.stream_output = True
    credentials = Credentials(
        settings.access_key.get_secret_value(), settings.secret_key.get_secret_value()
    )
    S3SigV4Auth(credentials, "s3", "us-east-1").add_auth(request)
    session = URLLib3Session(verify=str(settings.ca_file), timeout=5, proxies={})
    try:
        response = session.send(request.prepare())
        # stream=True avoids retaining arbitrarily large admin replies in memory.
        raw = response.raw.read(65537)
        if response.status_code not in (200, 201) or len(raw) > 65536:
            raise ValueError("storage_bootstrap_refused")
        return bytes(raw)
    except (BotoCoreError, OSError, HTTPTransportError):
        raise ValueError("storage_bootstrap_refused") from None
    finally:
        session.close()


def bootstrap(owner: StorageSettings, api: StorageSettings, scanner: StorageSettings) -> None:
    configs = [owner, api, scanner]
    if (
        len({c.endpoint for c in configs}) != 1
        or len({c.access_key.get_secret_value() for c in configs}) != 3
    ):
        raise ValueError("storage_bootstrap_refused")
    try:
        users = parse_admin_reply(admin_request(owner, "list-users"))
        accounts = {node.findtext("Access"): node for node in users.findall("Accounts")}
        # Inspect all existing desired identities before making any change.
        for config in (api, scanner):
            node = accounts.get(config.access_key.get_secret_value())
            if node is not None and (
                node.findtext("Secret") != config.secret_key.get_secret_value()
                or node.findtext("Role") != "user"
                or any(node.findtext(field) != "0" for field in ("UserID", "GroupID", "ProjectID"))
            ):
                raise ValueError("storage_bootstrap_refused")
        client = s3_client(owner)
        try:
            expected = bucket_policy(
                api.access_key.get_secret_value(), scanner.access_key.get_secret_value()
            )
            existing = {row["Name"] for row in client.list_buckets().get("Buckets", [])}
            if BUCKET in existing:
                acl = client.get_bucket_acl(Bucket=BUCKET)
                if acl["Owner"]["ID"] != owner.access_key.get_secret_value():
                    raise ValueError("storage_bootstrap_refused")
                actual = json.loads(client.get_bucket_policy(Bucket=BUCKET)["Policy"])
                if actual != expected:
                    raise ValueError("storage_bootstrap_refused")
            # Runtime identities must own no buckets, not even unrelated ones.
            ownership = parse_admin_reply(admin_request(owner, "list-buckets"))
            for row in ownership:
                if row.findtext("Owner") in {
                    api.access_key.get_secret_value(),
                    scanner.access_key.get_secret_value(),
                }:
                    raise ValueError("storage_bootstrap_refused")
            for config in (api, scanner):
                if config.access_key.get_secret_value() not in accounts:
                    account = ET.Element("Account")
                    for name, value in {
                        "Access": config.access_key.get_secret_value(),
                        "Secret": config.secret_key.get_secret_value(),
                        "Role": "user",
                        "UserID": "0",
                        "GroupID": "0",
                        "ProjectID": "0",
                    }.items():
                        ET.SubElement(account, name).text = value
                    admin_request(owner, "create-user", ET.tostring(account))
            if BUCKET not in existing:
                client.create_bucket(Bucket=BUCKET)
                client.put_bucket_policy(Bucket=BUCKET, Policy=json.dumps(expected))
            if json.loads(client.get_bucket_policy(Bucket=BUCKET)["Policy"]) != expected:
                raise ValueError("storage_bootstrap_refused")
        finally:
            client.close()
    except (ET.ParseError, KeyError, TypeError, BotoCoreError, ClientError, OSError):
        raise ValueError("storage_bootstrap_refused") from None


def main() -> None:
    try:
        bootstrap(
            *(
                load_storage(Path("/run/secrets") / name)
                for name in ("storage_owner", "storage_api", "storage_scanner")
            )
        )
    except ValueError:
        print("storage_bootstrap_refused", file=sys.stderr)
        raise SystemExit(1) from None
    print("storage_bootstrap_verified")


if __name__ == "__main__":
    main()
