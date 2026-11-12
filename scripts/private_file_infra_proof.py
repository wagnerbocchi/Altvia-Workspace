"""Real private S3/Clam profile proof, never an S3 emulator or fake clean scanner."""

import argparse
import base64
import hashlib
import io
import json
import os
import secrets
import socket
import subprocess
import sys
import time
import zipfile
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]


def source_hashes() -> dict[str, str]:
    paths = [
        *ROOT.glob("apps/api/altvia/file*.py"),
        *ROOT.glob("infra/*storage*"),
        *ROOT.glob("infra/*clam*"),
        ROOT / "infra/compose.files.yaml",
        ROOT / "infra/versitygw.go.mod",
        ROOT / "infra/versitygw.go.sum",
        ROOT / "pyproject.toml",
        ROOT / "uv.lock",
        Path(__file__).resolve(),
        ROOT / "scripts/file_test_certificate.mjs",
    ]
    return {
        str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in paths
        if p.is_file()
    }


def require_capacity(memory: int) -> None:
    if memory < 6 * 1024**3:
        raise RuntimeError("Full signed-definition profile requires at least 6 GiB engine memory")


def require_empty_buckets(result: dict) -> None:
    if (
        result.get("ResponseMetadata", {}).get("HTTPStatusCode") != 200
        or result.get("Buckets") != []
        or result.get("ContinuationToken")
        or result.get("Owner", {}).get("DisplayName")
    ):
        raise RuntimeError("Runtime global bucket listing leaked metadata")


def require_scan(result: dict, disposition: str, reason: str) -> None:
    if (
        result.get("disposition") != disposition
        or result.get("reason") != reason
        or result.get("engine") != "1.4.6"
        or not result.get("database_version")
        or not result.get("database_date")
    ):
        raise RuntimeError("Actual signed scanner result/identity did not meet acceptance")


def inside_storage(restart: dict | None = None) -> dict:
    from altvia.file_settings import StorageSettings
    from altvia.file_storage import BUCKET, S3Store, StorageError, s3_client
    from altvia.file_storage_owner import admin_request, bootstrap, load_storage
    from botocore import UNSIGNED
    from botocore.config import Config
    from botocore.exceptions import ClientError, SSLError
    from botocore.session import Session
    from pydantic import SecretStr

    owner, api, scanner = [
        load_storage(Path("/run/secrets") / name)
        for name in ("storage_owner", "storage_api", "storage_scanner")
    ]
    data = b"Altvia actual private immutable storage proof\n"
    digest = hashlib.sha256(data).hexdigest()
    key = restart["key"] if restart else "objects/" + secrets.token_hex(32)
    store = S3Store(api)
    reader = S3Store(scanner)
    owner_client = s3_client(owner)
    checks = []

    def denied(name, operation, statuses=(403,)):
        try:
            operation()
        except ClientError as error:
            status = error.response["ResponseMetadata"]["HTTPStatusCode"]
            if status not in statuses:
                raise RuntimeError(f"{name}: unexpected refusal status {status}") from None
            checks.append({"check": name, "status": status})
        else:
            raise RuntimeError(name + ": unexpectedly permitted")

    def conditioned_copy(destination, source_bucket=BUCKET, source_key=None, header="*"):
        # Proof of native semantics only. The actual store has no copy API.
        def condition(request, **_):
            request.headers["If-None-Match"] = header

        store.client.meta.events.register("before-sign.s3.CopyObject", condition)
        try:
            return store.client.copy_object(
                Bucket=BUCKET,
                Key=destination,
                CopySource={"Bucket": source_bucket, "Key": source_key or key},
            )
        finally:
            store.client.meta.events.unregister("before-sign.s3.CopyObject", condition)

    try:
        # A fresh run intentionally attempts the real missing infrastructure
        # before owner initialization. The host saves this meaningful RED.
        if os.environ.get("ALTVIA_FILE_RED") == "1":
            store.put_new(key, io.BytesIO(data), size=len(data), sha256=digest)
            raise RuntimeError("Uninitialized storage unexpectedly admitted runtime PUT")
        bootstrap(owner, api, scanner)
        bootstrap(owner, api, scanner)  # Existing state is inspected, never reset.
        wrong_api = api.model_copy(update={"secret_key": SecretStr("synthetic-wrong-secret")})
        try:
            bootstrap(owner, wrong_api, scanner)
        except ValueError:
            checks.append({"check": "incompatible-bootstrap-refused"})
        else:
            raise RuntimeError("Incompatible identity was reset")
        if not restart:
            store.put_new(key, io.BytesIO(data), size=len(data), sha256=digest)
        try:
            store.put_new(
                key,
                io.BytesIO(b"X" * len(data)),
                size=len(data),
                sha256=hashlib.sha256(b"X" * len(data)).hexdigest(),
            )
        except StorageError as error:
            assert str(error) == "storage_exists"
        else:
            raise RuntimeError("Conditional overwrite succeeded")
        for client in (store, reader):
            with client.verified_spool(key, size=len(data), sha256=digest) as body:
                assert body.read() == data
            try:
                with client.verified_spool(key, size=len(data), sha256="0" * 64):
                    raise RuntimeError("Corrupt object escaped")
            except StorageError as error:
                assert str(error) == "storage_integrity"
        other = "altvia-proof-foreign"
        if not restart:
            owner_client.create_bucket(Bucket=other)
            owner_client.put_object(Bucket=other, Key=key, Body=b"foreign private object")
        for role, client in (("api", store.client), ("scanner", reader.client)):
            listing = client.list_buckets()
            require_empty_buckets(listing)
            # Native Owner.ID names the caller, not the bucket owner. It carries
            # no additional bucket/customer identity and must equal that caller.
            assert listing.get("Owner", {}).get("ID") in (
                None,
                api.access_key.get_secret_value()
                if role == "api"
                else scanner.access_key.get_secret_value(),
            )
            checks.append({"check": role + "-global-buckets", "status": 200, "buckets": []})
            for name, operation in [
                ("list-v1", lambda client=client: client.list_objects(Bucket=BUCKET)),
                ("list-v2", lambda client=client: client.list_objects_v2(Bucket=BUCKET)),
                ("versions", lambda client=client: client.list_object_versions(Bucket=BUCKET)),
                (
                    "multipart-list",
                    lambda client=client: client.list_multipart_uploads(Bucket=BUCKET),
                ),
                ("delete", lambda client=client: client.delete_object(Bucket=BUCKET, Key=key)),
                ("delete-bucket", lambda client=client: client.delete_bucket(Bucket=BUCKET)),
                ("get-policy", lambda client=client: client.get_bucket_policy(Bucket=BUCKET)),
                (
                    "put-policy",
                    lambda client=client: client.put_bucket_policy(Bucket=BUCKET, Policy="{}"),
                ),
                (
                    "put-acl",
                    lambda client=client: client.put_object_acl(
                        Bucket=BUCKET, Key=key, ACL="public-read"
                    ),
                ),
                ("foreign-get", lambda client=client: client.get_object(Bucket=other, Key=key)),
                ("foreign-head", lambda client=client: client.head_object(Bucket=other, Key=key)),
                (
                    "foreign-put",
                    lambda client=client: client.put_object(
                        Bucket=other, Key=key, Body=b"x", IfNoneMatch="*"
                    ),
                ),
                (
                    "foreign-prefix",
                    lambda client=client: client.put_object(
                        Bucket=BUCKET,
                        Key="elsewhere/" + secrets.token_hex(32),
                        Body=b"x",
                        IfNoneMatch="*",
                    ),
                ),
                (
                    "create-bucket",
                    lambda client=client: client.create_bucket(
                        Bucket="altvia-runtime-must-not-own"
                    ),
                ),
                (
                    "multipart-init",
                    lambda client=client: client.create_multipart_upload(Bucket=BUCKET, Key=key),
                ),
                (
                    "copy-missing-header",
                    lambda client=client: client.copy_object(
                        Bucket=BUCKET,
                        Key="objects/" + secrets.token_hex(32),
                        CopySource={"Bucket": BUCKET, "Key": key},
                    ),
                ),
            ]:
                denied(role + "-" + name, operation)
            # Native admin request uses SDK signing with ordinary credentials.
            try:
                admin_request(api if role == "api" else scanner, "list-users")
            except ValueError:
                checks.append({"check": role + "-admin-denied"})
            else:
                raise RuntimeError("Runtime user entered admin API")
        for header in (None, "wrong"):
            kwargs = {} if header is None else {"IfNoneMatch": header}
            denied(
                "api-missing-or-wrong-condition",
                lambda kwargs=kwargs: store.client.put_object(
                    Bucket=BUCKET, Key="objects/" + secrets.token_hex(32), Body=b"x", **kwargs
                ),
            )
        copy_key = "objects/" + secrets.token_hex(32)
        conditioned_copy(copy_key)
        with reader.verified_spool(copy_key, size=len(data), sha256=digest) as body:
            assert body.read() == data
        checks.append({"check": "conditional-same-scope-copy-created", "status": 200})
        denied("conditional-copy-existing", lambda: conditioned_copy(key), (412,))
        denied(
            "conditional-copy-wrong-header",
            lambda: conditioned_copy("objects/" + secrets.token_hex(32), header="wrong"),
        )
        denied(
            "conditional-copy-foreign-source",
            lambda: conditioned_copy("objects/" + secrets.token_hex(32), source_bucket=other),
        )
        denied(
            "conditional-copy-foreign-destination",
            lambda: conditioned_copy("foreign/" + secrets.token_hex(32)),
        )
        for destination in (key, "objects/" + secrets.token_hex(32)):
            upload = owner_client.create_multipart_upload(Bucket=BUCKET, Key=destination)
            part = owner_client.upload_part(
                Bucket=BUCKET, Key=destination, UploadId=upload["UploadId"], PartNumber=1, Body=data
            )
            arguments = {
                "Bucket": BUCKET,
                "Key": destination,
                "UploadId": upload["UploadId"],
                "MultipartUpload": {"Parts": [{"ETag": part["ETag"], "PartNumber": 1}]},
            }
            denied(
                "multipart-complete-missing-header",
                lambda arguments=arguments: store.client.complete_multipart_upload(**arguments),
            )
            if destination == key:
                denied(
                    "multipart-complete-existing-conditional",
                    lambda arguments=arguments: store.client.complete_multipart_upload(
                        **arguments, IfNoneMatch="*"
                    ),
                    (403, 412),
                )
            else:
                try:
                    complete = store.client.complete_multipart_upload(**arguments, IfNoneMatch="*")
                except ClientError as error:
                    assert error.response["ResponseMetadata"]["HTTPStatusCode"] == 403
                    checks.append({"check": "multipart-complete-new-conditional", "status": 403})
                else:
                    assert complete["ResponseMetadata"]["HTTPStatusCode"] == 200
                    with reader.verified_spool(destination, size=len(data), sha256=digest) as body:
                        assert body.read() == data
                    checks.append({"check": "multipart-complete-new-conditional", "status": 200})
        corrupt_key = "objects/" + secrets.token_hex(32)
        owner_client.put_object(Bucket=BUCKET, Key=corrupt_key, Body=b"X" * len(data))
        try:
            with store.verified_spool(corrupt_key, size=len(data), sha256=digest):
                raise RuntimeError("Actual corrupt storage bytes escaped")
        except StorageError as error:
            assert str(error) == "storage_integrity"
        checks.append({"check": "actual-corrupt-object-refused"})
        denied(
            "scanner-write",
            lambda: reader.client.put_object(
                Bucket=BUCKET, Key="objects/" + secrets.token_hex(32), Body=b"x", IfNoneMatch="*"
            ),
        )
        anonymous = Session().create_client(
            "s3",
            endpoint_url=api.endpoint,
            region_name="us-east-1",
            verify=str(api.ca_file),
            config=store.client.meta.config.merge(Config(signature_version=UNSIGNED)),
        )
        try:
            denied("anonymous-get", lambda: anonymous.get_object(Bucket=BUCKET, Key=key))
        finally:
            anonymous.close()
        # Verify actual TLS certificate refusal, not just a settings assertion.
        bad_tls = StorageSettings(
            endpoint=f"https://{socket.gethostbyname('storage')}:8443",
            ca_file=api.ca_file,
            access_key=api.access_key,
            secret_key=api.secret_key,
        )
        bad_client = s3_client(bad_tls)
        try:
            try:
                bad_client.get_object(Bucket=BUCKET, Key=key)
            except SSLError:
                checks.append({"check": "tls-wrong-host-refused"})
            else:
                raise RuntimeError("TLS hostname mismatch accepted")
        finally:
            bad_client.close()
        with store.verified_spool(key, size=len(data), sha256=digest) as body:
            assert body.read() == data
        return {"key": key, "sha256": digest, "checks": checks, "restart": bool(restart)}
    finally:
        store.close()
        reader.close()
        owner_client.close()


def inside_scanner(payload: dict) -> dict:
    from altvia.file_scan_transport import ClamClient
    from altvia.file_settings import ScannerSettings

    client = ClamClient(ScannerSettings())
    now = datetime.now(UTC)
    results = {}
    expanded = io.BytesIO()
    with zipfile.ZipFile(expanded, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("bounded-limit-control.txt", b"x" * (11 * 1024 * 1024))
    eicar = b"X5O!P%@AP[4\\PZX54(P^)7CC)7}$" + b"EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"
    for label, data, expected, reason in (
        ("clean", b"Actual signed current ClamAV clean control\n", "clean", "clean"),
        ("eicar", eicar, "infected", "infected"),
        ("expanded_limit", expanded.getvalue(), "failed", "limit"),
        (
            "encrypted",
            base64.b64decode(payload["encrypted_zip"], validate=True),
            "failed",
            "encrypted",
        ),
    ):
        raw = asdict(client.scan(io.BytesIO(data), db_now=now))
        require_scan(raw, expected, reason)
        raw["database_date"] = raw["database_date"].isoformat()
        results[label] = raw
    stale = client.scan(io.BytesIO(b"bytes"), db_now=now + timedelta(hours=72))
    assert stale.disposition == "failed" and stale.reason == "database_invalid"
    oversized = client.scan(io.BytesIO(b"x" * (10 * 1024 * 1024 + 1)), db_now=now)
    assert oversized.disposition == "failed" and oversized.reason == "limit"
    return {
        "profile": "actual-signed-complete-current",
        "results": results,
        "stale_refused": True,
        "oversize_refused": True,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--engine", choices=["docker", "podman"], default="docker")
    parser.add_argument("--storage-only", action="store_true")
    parser.add_argument("--inside", choices=["storage", "scanner"])
    args = parser.parse_args()
    if args.inside:
        if os.environ.get("ALTVIA_ALLOW_FILE_INFRA_TEST") != "1":
            raise SystemExit("Explicit file infrastructure test opt-in required")
        payload = json.load(sys.stdin)
        result = (
            inside_storage(payload or None) if args.inside == "storage" else inside_scanner(payload)
        )
        print(json.dumps(result, sort_keys=True))
        return
    if os.environ.get("ALTVIA_ALLOW_FILE_INFRA_TEST") != "1":
        raise SystemExit("Explicit ALTVIA_ALLOW_FILE_INFRA_TEST=1 required")
    if args.engine != "docker" and not args.storage_only:
        raise SystemExit("Complete signed-definition proof requires adequately provisioned Docker")
    os.umask(0o077)
    work = ROOT / ".superpowers/file-infra" / ("altvia-files-" + uuid4().hex[:10])
    work.mkdir(parents=True, mode=0o700)
    private = work / "secrets"
    private.mkdir(mode=0o700)
    env = {
        **os.environ,
        "ALTVIA_SECRET_DIR": str(private),
        "ALTVIA_PUBLIC_ORIGIN": "https://files-proof.invalid",
    }
    project = work.name
    for service in ("storage", "clamav", "api"):
        env[f"ALTVIA_{service.upper()}_IMAGE"] = project + ":" + service
    compose = [
        args.engine,
        "compose",
        "-f",
        "infra/compose.yaml",
        "-f",
        "infra/compose.files.yaml",
        "-p",
        project,
    ]
    manifest = {"passed": False, "storage_only": args.storage_only, "images": {}, "commands": []}
    manifest["source_hashes"] = source_hashes()
    sensitive_values = []

    def run(command, *, data=None, timeout=900, allow_failure=False):
        result = subprocess.run(
            command,
            cwd=ROOT,
            env=env,
            input=data,
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
        )
        number = len(manifest["commands"])
        evidence = {}
        for channel in ("stdout", "stderr"):
            original = getattr(result, channel)
            safe = original
            for value in sensitive_values:
                safe = safe.replace(value, "[redacted-private-credential]")
            if original != safe:
                restricted = work / "private"
                restricted.mkdir(mode=0o700, exist_ok=True)
                (restricted / f"{number:03}.{channel}").write_text(original, encoding="utf-8")
            (work / f"{number:03}.{channel}").write_text(safe, encoding="utf-8")
            evidence[channel + "_sha256"] = hashlib.sha256(safe.encode()).hexdigest()
            evidence[channel + "_original_sha256"] = hashlib.sha256(original.encode()).hexdigest()
            evidence[channel + "_redacted"] = original != safe
        manifest["commands"].append(
            {
                "command": command,
                "exit": result.returncode,
                **evidence,
            }
        )
        if result.returncode and not allow_failure:
            raise RuntimeError(
                f"Infrastructure command failed ({result.returncode}); private evidence: {work}"
            )
        return result

    def probe(phase, payload, red=False):
        extra = ["-e", "ALTVIA_FILE_RED=1"] if red else []
        result = run(
            [
                *compose,
                "run",
                "--rm",
                "--no-deps",
                "-T",
                "-e",
                "ALTVIA_ALLOW_FILE_INFRA_TEST=1",
                *extra,
                "file-infra-proof",
                "--inside",
                phase,
            ],
            data=json.dumps(payload),
            allow_failure=red,
        )
        if red:
            if result.returncode == 0:
                raise RuntimeError("Missing-infrastructure RED did not fail")
            return None
        return json.loads(result.stdout)

    try:
        if not args.storage_only:
            memory = int(run([args.engine, "info", "--format", "{{.MemTotal}}"]).stdout.strip())
            require_capacity(memory)
        run(["node", "scripts/file_test_certificate.mjs", str(private)])
        sensitive_values.append((private / "storage_key").read_text())
        configs = {}
        for role in ("owner", "api", "scanner"):
            configs[role] = {
                "endpoint": "https://storage:8443",
                "ca_file": "/run/secrets/storage_ca",
                "access_key": secrets.token_hex(16),
                "secret_key": secrets.token_hex(32),
            }
            sensitive_values.extend([configs[role]["access_key"], configs[role]["secret_key"]])
            (private / ("storage_" + role)).write_text(json.dumps(configs[role]))
        (private / "storage_root_access").write_text(configs["owner"]["access_key"])
        (private / "storage_root_secret").write_text(configs["owner"]["secret_key"])
        for path in private.iterdir():
            path.chmod(0o444)
        for service in ("storage", "api") + (() if args.storage_only else ("clamav",)):
            build = [
                args.engine,
                "build",
                "-f",
                f"infra/{service}.Dockerfile",
                "-t",
                env[f"ALTVIA_{service.upper()}_IMAGE"],
                ".",
            ]
            if args.engine == "podman":
                build.insert(2, "--format=docker")
            run(build, timeout=1200)
            manifest["images"][service] = run(
                [
                    args.engine,
                    "image",
                    "inspect",
                    "--format",
                    "{{.Id}}",
                    env[f"ALTVIA_{service.upper()}_IMAGE"],
                ]
            ).stdout.strip()
        run([*compose, "up", "-d", "--no-build", "--wait", "storage"])
        probe("storage", {}, red=True)
        storage = probe("storage", {})
        manifest["storage"] = storage
        manifest["isolation"] = {}

        def isolate(service, network_name, memory_mib, cpu_nanos, pids, internal=True):
            identifier = run([*compose, "ps", "-q", service]).stdout.strip()
            # Never retain a full inspection: the gateway process environment
            # contains root credentials read from its mounted secrets.
            host = json.loads(
                run([args.engine, "inspect", "--format", "{{json .HostConfig}}", identifier]).stdout
            )
            user = run(
                [args.engine, "inspect", "--format", "{{.Config.User}}", identifier]
            ).stdout.strip()
            assert user == "10001:10001" and host["ReadonlyRootfs"]
            assert not host.get("Privileged") and not host.get("PortBindings")
            if args.engine == "docker":
                assert "ALL" in [c.upper().removeprefix("CAP_") for c in host["CapDrop"]]
            else:
                caps = json.loads(
                    run(
                        [args.engine, "inspect", "--format", "{{json .EffectiveCaps}}", identifier]
                    ).stdout
                )
                assert caps in (None, [])
            effective = run(
                [*compose, "exec", "-T", service, "sh", "-ec", "grep '^CapEff:' /proc/self/status"]
            ).stdout.strip()
            assert effective.split() == ["CapEff:", "0000000000000000"]
            assert any("no-new-privileges" in opt for opt in host["SecurityOpt"])
            if args.engine == "docker":
                assert host["Memory"] == memory_mib * 1024**2
                assert host["NanoCpus"] == cpu_nanos and host["PidsLimit"] == pids
                control = run(
                    [
                        *compose,
                        "exec",
                        "-T",
                        service,
                        "sh",
                        "-ec",
                        "cat /sys/fs/cgroup/memory.max /sys/fs/cgroup/cpu.max "
                        "/sys/fs/cgroup/pids.max",
                    ]
                ).stdout.splitlines()
                assert int(control[0]) == memory_mib * 1024**2
                quota, period = map(int, control[1].split())
                assert quota * 1_000_000_000 == cpu_nanos * period
                assert int(control[2]) == pids
            networks = json.loads(
                run(
                    [
                        args.engine,
                        "inspect",
                        "--format",
                        "{{json .NetworkSettings.Networks}}",
                        identifier,
                    ]
                ).stdout
            )
            assert set(networks) == {project + "_" + network_name}
            for network in networks:
                state = json.loads(run([args.engine, "network", "inspect", network]).stdout)[0]
                assert bool(state.get("Internal", state.get("internal"))) == internal
            manifest["isolation"][service] = {
                "nonroot": True,
                "read_only": True,
                "no_ports": True,
                "private_network": internal,
                "resource_limits": "enforced"
                if args.engine == "docker"
                else "not-qualified-local-podman",
            }

        isolate("storage", "objects", 256, 1_000_000_000, 128)
        inventory = run(
            [
                *compose,
                "exec",
                "-T",
                "storage",
                "sh",
                "-ec",
                "versitygw --version; cat /usr/share/altvia-storage/toolchain.txt "
                "/usr/share/altvia-storage/go-build-info.txt "
                "/usr/share/altvia-storage/binary.sha256 /usr/share/altvia-storage/packages.txt; "
                "sha256sum /usr/local/bin/versitygw",
            ]
        )
        (work / "inventory-storage.txt").write_text(inventory.stdout, encoding="utf-8")
        run([*compose, "restart", "storage"])
        run([*compose, "up", "-d", "--no-build", "--wait", "storage"])
        manifest["storage_restart"] = probe("storage", storage)
        if not args.storage_only:
            # Complete current signed vendor databases; no local tiny substitute.
            run([*compose, "run", "--rm", "--no-deps", "freshclam", "--stdout"], timeout=1200)
            run(
                [*compose, "up", "-d", "--no-build", "--wait", "--wait-timeout", "300", "clamd"],
                timeout=420,
            )
            isolate("clamd", "scan", 2048, 2_000_000_000, 64)
            isolate("freshclam", "definition_download", 1536, 1_000_000_000, 32, False)
            plain = work / "encrypted-control.txt"
            plain.write_text("Synthetic encrypted archive control\n")
            encrypted = work / "encrypted-control.zip"
            run(["zip", "-j", "-P", "synthetic-proof-only", str(encrypted), str(plain)])
            payload = {"encrypted_zip": base64.b64encode(encrypted.read_bytes()).decode()}
            manifest["scanner"] = probe("scanner", payload)
            inventory = run(
                [
                    *compose,
                    "exec",
                    "-T",
                    "clamd",
                    "sh",
                    "-ec",
                    "clamd --version; cat /usr/share/altvia-clamav/packages.txt "
                    "/usr/share/altvia-clamav/native.sha256; "
                    "for f in /var/lib/clamav/*.cvd /var/lib/clamav/*.cld; do "
                    'test -f "$f" || continue; sha256sum "$f"; sigtool --info "$f"; done',
                ]
            )
            (work / "inventory-clamav.txt").write_text(inventory.stdout, encoding="utf-8")
            # Force a real signed vendor replacement of the disposable test daily
            # file. Keep the original; no real retention/deletion operation.
            run([*compose, "stop", "freshclam"])
            run(
                [
                    *compose,
                    "run",
                    "--rm",
                    "--no-deps",
                    "--entrypoint",
                    "sh",
                    "freshclam",
                    "-ec",
                    "if test -f /var/lib/clamav/daily.cvd; then "
                    "mv /var/lib/clamav/daily.cvd /var/lib/clamav/daily.saved; else "
                    "mv /var/lib/clamav/daily.cld /var/lib/clamav/daily.saved; fi",
                ]
            )
            run([*compose, "run", "--rm", "--no-deps", "freshclam", "--stdout"], timeout=1200)
            for _ in range(60):
                logs = run([*compose, "logs", "--no-color", "clamd"])
                if "Database correctly reloaded" in logs.stdout + logs.stderr:
                    break
                time.sleep(2)
            else:
                raise RuntimeError("Actual signed replacement did not reload in clamd")
            (work / "inventory-definition-reload.txt").write_text(logs.stdout + logs.stderr)
            manifest["scanner_after_update"] = probe("scanner", payload)
            run([*compose, "stop", "clamd"])
            refused = run(
                [
                    *compose,
                    "run",
                    "--rm",
                    "--no-deps",
                    "-T",
                    "-e",
                    "ALTVIA_ALLOW_FILE_INFRA_TEST=1",
                    "file-infra-proof",
                    "--inside",
                    "scanner",
                ],
                data=json.dumps(payload),
                allow_failure=True,
            )
            if refused.returncode == 0:
                raise RuntimeError("Stopped scanner released clean bytes")
        manifest["passed"] = True
    finally:
        run(
            [*compose, "logs", "--no-color", "storage", "clamd", "freshclam"],
            timeout=30,
            allow_failure=True,
        )
        run([*compose, "down"], timeout=90, allow_failure=True)  # Preserve all named volumes.
        if source_hashes() != manifest["source_hashes"]:
            manifest["passed"] = False
            manifest["source_mutation"] = True
        (work / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        print("Private file infrastructure evidence:", work)
        if manifest.get("source_mutation"):
            raise RuntimeError("Source changed during real infrastructure proof")


if __name__ == "__main__":
    main()
