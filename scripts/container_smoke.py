"""Guarded black-box proof of the actual image/Compose/TLS/persistence boundary."""

import argparse
import json
import os
import secrets
import socket
import subprocess
import time
from pathlib import Path
from uuid import uuid4

import httpx

ROOT = Path(__file__).resolve().parents[1]


def check_legacy_volume_refusal(engine, image):
    inspect = subprocess.run(
        [engine, "image", "inspect", image], check=True, capture_output=True, text=True
    )
    entrypoint = json.loads(inspect.stdout)[0]["Config"]["Entrypoint"]
    command = [engine, "run", "--rm", "--read-only", "--network=none", "--tmpfs=/tmp"]
    if engine == "podman":
        command.append("--cgroups=disabled")
    result = subprocess.run(
        [
            *command,
            "--entrypoint=sh",
            image,
            "-ec",
            "mkdir -p /tmp/legacy; printf 17 > /tmp/legacy/PG_VERSION; "
            'export PGDATA=/tmp/legacy; exec "$@" postgres',
            "guard-probe",
            *entrypoint,
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 1 or "Refusing unmarked PostgreSQL data" not in result.stderr:
        raise RuntimeError("Legacy PostgreSQL volume refusal proof failed")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--engine", choices=["docker", "podman"], default="docker")
    args = parser.parse_args()
    if os.environ.get("ALTVIA_ALLOW_CONTAINER_TEST") != "1":
        raise SystemExit("Explicit ALTVIA_ALLOW_CONTAINER_TEST=1 required")
    # Exercise secret generation under the restrictive umask used on operators' hosts.
    os.umask(0o077)
    assert (ROOT / "infra/api.Dockerfile").is_file(), "API container artifact missing"
    project = "altvia-test-" + uuid4().hex[:10]
    work = ROOT / ".superpowers/container-tests" / project
    work.mkdir(parents=True, mode=0o700)
    secret_dir = work / "secrets"
    secret_dir.mkdir(mode=0o700)
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    origin = f"https://workspace.altvia.test:{port}"
    original_dns = socket.getaddrinfo

    def test_dns(host, *args, **kwargs):
        # Resolve only this reserved test name locally; preserve TLS/SNI validation
        # against a domain-only certificate with no loopback-IP SAN.
        if host in ("workspace.altvia.test", b"workspace.altvia.test"):
            host = "127.0.0.1"
        return original_dns(host, *args, **kwargs)

    socket.getaddrinfo = test_dns
    owner_password, runtime_password, password, worker_password, redis_password = [
        secrets.token_urlsafe(32) for _ in range(5)
    ]
    files = {
        "postgres_password": owner_password,
        "owner_database_url": f"postgresql+psycopg://altvia_owner:{owner_password}@postgres/altvia_test",
        "runtime_database_url": f"postgresql+psycopg://altvia_app:{runtime_password}@postgres/altvia_test",
        "worker_database_url": f"postgresql+psycopg://altvia_worker:{worker_password}@postgres/altvia_test",
        "redis_url": f"redis://:{redis_password}@redis:6379/0",
        "redis_password": redis_password,
    }
    for name, content in files.items():
        path = secret_dir / name
        path.write_text(content, encoding="utf-8")
        path.chmod(0o444)
    env = {
        **os.environ,
        "ALTVIA_SECRET_DIR": str(secret_dir),
        "ALTVIA_PUBLIC_ORIGIN": origin,
        "ALTVIA_HTTPS_PORT": str(port),
        "ALTVIA_DATABASE_NAME": "altvia_test",
        "ALTVIA_API_IMAGE": project + ":test",
        "ALTVIA_POSTGRES_IMAGE": project + ":postgres",
        "ALTVIA_INGRESS_IMAGE": project + ":ingress",
        "ALTVIA_WEB_IMAGE": project + ":web",
        "ALTVIA_REDIS_IMAGE": project + ":redis",
    }
    # Never inherit a host DB credential into the test stack.
    env.pop("ALTVIA_DATABASE_URL", None)
    compose = [args.engine, "compose", "-f", str(ROOT / "infra/compose.yaml"), "-p", project]

    def run(command, *, data=None, timeout=240):
        result = subprocess.run(
            command,
            input=data,
            text=True,
            encoding="utf-8",
            capture_output=True,
            cwd=ROOT,
            env=env,
            timeout=timeout,
        )
        if result.returncode:
            # Exact output stays private; exceptions never echo SQL, URLs or secrets.
            (work / "last-command.stdout").write_text(result.stdout, encoding="utf-8")
            (work / "last-command.stderr").write_text(result.stderr, encoding="utf-8")
            raise RuntimeError(
                f"Container command failed ({result.returncode}); private logs: {work}"
            )
        return result.stdout

    def exec_api(code, payload=None):
        return run(
            [*compose, "exec", "-T", "api", "python", "-c", code],
            data=json.dumps(payload) if payload is not None else None,
        )

    def container(service):
        container_id = run([*compose, "ps", "-a", "-q", service]).strip()
        return json.loads(run([args.engine, "inspect", container_id]))[0]

    def await_ready(client):
        for _ in range(90):
            try:
                if client.get("/api/v1/health/ready").status_code == 200:
                    return
            except httpx.HTTPError:
                pass
            time.sleep(0.5)
        raise RuntimeError("HTTPS readiness did not recover")

    started = False
    canary = ROOT / "apps/api/altvia" / (".env.container-test-" + uuid4().hex)
    web_canary = ROOT / "apps/web/src" / (".env.container-test-" + uuid4().hex + ".ts")
    try:
        run(["node", "scripts/container_tls.mjs", str(secret_dir)])
        with canary.open("x", encoding="utf-8") as source:
            source.write(password)
        with web_canary.open("x", encoding="utf-8") as source:
            source.write("export const mustNeverShip = " + json.dumps(password) + ";")
        build = [
            args.engine,
            "build",
            "-f",
            "infra/api.Dockerfile",
            "-t",
            env["ALTVIA_API_IMAGE"],
            ".",
        ]
        if args.engine == "podman":
            # OCI output discards Docker HEALTHCHECK metadata in Podman builds.
            build.insert(2, "--format=docker")
        run(build, timeout=600)
        for service in ("postgres", "ingress", "web", "redis"):
            service_build = [
                args.engine,
                "build",
                "-f",
                f"infra/{service}.Dockerfile",
                "-t",
                env[f"ALTVIA_{service.upper()}_IMAGE"],
                ".",
            ]
            if args.engine == "podman":
                service_build.insert(2, "--format=docker")
            run(service_build, timeout=600)
        # Verify the allowlist at the builder boundary too, before file tracing
        # could omit an accidentally copied secret from only the final image.
        web_builder = project + ":web-builder-probe"
        run(
            [
                args.engine,
                "build",
                "--target",
                "build",
                "-f",
                "infra/web.Dockerfile",
                "-t",
                web_builder,
                ".",
            ],
            timeout=600,
        )
        run(
            [
                args.engine,
                "run",
                "--rm",
                "--read-only",
                "--network=none",
                "--cap-drop=ALL",
                web_builder,
                "node",
                "-e",
                "require('node:assert/strict').equal(require('node:fs').existsSync("
                + json.dumps("/opt/altvia/apps/web/src/" + web_canary.name)
                + "),false)",
            ]
        )
        check_legacy_volume_refusal(args.engine, env["ALTVIA_POSTGRES_IMAGE"])
        # The builder remains general-purpose. Check rejection on that actual
        # untrimmed stage so a disabled/broken capability checker cannot pass.
        builder_probe = project + ":builder-probe"
        run(
            [
                args.engine,
                "build",
                "--target",
                "dependencies",
                "-f",
                "infra/api.Dockerfile",
                "-t",
                builder_probe,
                ".",
            ],
            timeout=600,
        )
        rejection = subprocess.run(
            [
                args.engine,
                "run",
                "--rm",
                "-i",
                "--read-only",
                "--network=none",
                "--cap-drop=ALL",
                builder_probe,
                "python",
                "-",
            ],
            input=(ROOT / "scripts/check_api_runtime.py").read_text(encoding="utf-8"),
            text=True,
            capture_output=True,
            cwd=ROOT,
            env=env,
            timeout=60,
        )
        if (
            rejection.returncode != 1
            or "Unsupported SQLite Python capability is installed" not in rejection.stderr
        ):
            raise RuntimeError("Untrimmed builder capability rejection proof failed")
        installer_probe = (
            "namespace={'__name__':'installer_probe'}; exec("
            + repr((ROOT / "scripts/check_api_runtime.py").read_text(encoding="utf-8"))
            + ",namespace); namespace['check_package_installers']()"
        )
        installer_rejection = subprocess.run(
            [
                args.engine,
                "run",
                "--rm",
                "-i",
                "--read-only",
                "--network=none",
                "--cap-drop=ALL",
                builder_probe,
                "python",
                "-",
            ],
            input=installer_probe,
            text=True,
            capture_output=True,
            cwd=ROOT,
            env=env,
            timeout=60,
        )
        if (
            installer_rejection.returncode != 1
            or "package installer" not in installer_rejection.stderr
        ):
            raise RuntimeError("Untrimmed builder installer rejection proof failed")
        started = True
        run([*compose, "up", "-d", "--no-build", "--wait", "--wait-timeout", "150"])
        for service in ["api", "ingress", "web", "worker", "redis"]:
            inspect = container(service)
            assert inspect["Config"]["User"] not in ("", "0", "root")
            assert inspect["HostConfig"]["ReadonlyRootfs"]
        for service in ["api", "postgres", "web", "worker", "redis"]:
            assert not container(service)["HostConfig"].get("PortBindings")
        web_config = container("web")
        assert list(web_config["NetworkSettings"]["Networks"]) == [project + "_ingress"]
        assert not any(item.startswith("ALTVIA_") for item in web_config["Config"]["Env"])
        assert not any(
            mount["Destination"].startswith("/run/secrets") for mount in web_config["Mounts"]
        )
        web_inventory = json.loads(
            run(
                [*compose, "exec", "-T", "web", "node", "scripts/check_web_runtime.mjs"]
            ).splitlines()[-1]
        )
        assert web_inventory["standalone"] == "present" and web_inventory["sharp"] == "absent"
        assert web_inventory["package_installers"] == "absent"
        assert web_inventory["zlib"] == "1.4" and web_inventory["brotli"] == "1.2.1"
        api_env = container("api")["Config"]["Env"]
        assert not any(item.startswith("ALTVIA_DATABASE_URL=") for item in api_env)
        assert not any(item.startswith("ALTVIA_REDIS_URL=") for item in api_env)
        assert list(container("redis")["NetworkSettings"]["Networks"]) == [project + "_queue"]
        assert set(container("worker")["NetworkSettings"]["Networks"]) == {
            project + "_queue",
            project + "_database",
        }
        assert (
            run(
                [args.engine, "network", "inspect", "--format", "{{.Internal}}", project + "_queue"]
            ).strip()
            == "true"
        )
        assert container("worker")["Image"] == container("api")["Image"]
        worker_probe = """
from pathlib import Path
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.engine import make_url
from altvia.config import WorkerSettings
from altvia.database import make_engine
s=WorkerSettings()
assert make_url(s.database_url.get_secret_value()).username == 'altvia_worker'
assert not Path('/run/secrets/ALTVIA_RUNTIME_DATABASE_URL').exists()
assert not Path('/run/secrets/ALTVIA_WORKER_DATABASE_URL').exists()
e=make_engine(s)
for statement in ['SELECT * FROM users', 'SELECT * FROM sessions', 'SELECT * FROM audit_logs',
                  "UPDATE outbox_events SET payload='{}'", 'DELETE FROM activity_events']:
    try:
        with e.begin() as c: c.execute(text(statement))
    except DBAPIError: pass
    else: raise RuntimeError('Worker privilege boundary failed')
e.dispose()
"""
        run([*compose, "exec", "-T", "worker", "python", "-c", worker_probe])
        runtime_inventory = json.loads(
            run([*compose, "exec", "-T", "api", "python", "check_api_runtime.py"])
        )
        assert runtime_inventory["sqlite"] == "absent"
        assert runtime_inventory["api_imports"] == "passed"
        assert runtime_inventory["package_installers"] == "absent"
        assert runtime_inventory["zlib"] == "1.4"
        # Cross-libc recovery uses logical SQL and a fresh database, never an old
        # data directory. The disconnected legacy source has synthetic data only.
        legacy = project + "-legacy"
        legacy_started = False
        try:
            run(
                [
                    args.engine,
                    "run",
                    "-d",
                    "--name",
                    legacy,
                    "--network=none",
                    "--memory=512m",
                    "--cpus=1",
                    "--pids-limit=128",
                    "--security-opt=no-new-privileges:true",
                    "--mount",
                    f"type=volume,source={legacy}-data,target=/var/lib/postgresql/data",
                    "-e",
                    "POSTGRES_USER=altvia_owner",
                    "-e",
                    "POSTGRES_DB=altvia_test",
                    "-e",
                    "POSTGRES_HOST_AUTH_METHOD=trust",
                    "docker.io/library/postgres@sha256:"
                    "73bedc9eaa0121b92b9b26bb52e5141b3f6f37479c7ef913c0160455763ca80a",
                ]
            )
            legacy_started = True
            for _attempt in range(60):
                ready = subprocess.run(
                    [args.engine, "exec", legacy, "pg_isready", "-U", "altvia_owner"],
                    capture_output=True,
                    timeout=10,
                )
                if ready.returncode == 0:
                    # Wait for the permanent TCP server, not initdb's temporary socket server.
                    tcp = subprocess.run(
                        [
                            args.engine,
                            "exec",
                            legacy,
                            "pg_isready",
                            "-h",
                            "127.0.0.1",
                            "-U",
                            "altvia_owner",
                        ],
                        capture_output=True,
                        timeout=10,
                    )
                    if tcp.returncode == 0:
                        break
                time.sleep(1)
            else:
                raise RuntimeError("Synthetic legacy database not ready")
            legacy_sql = [
                args.engine,
                "exec",
                "-i",
                legacy,
                "psql",
                "-X",
                "-v",
                "ON_ERROR_STOP=1",
                "-U",
                "altvia_owner",
                "-d",
                "altvia_test",
            ]
            run(
                legacy_sql,
                data="""
CREATE TABLE compatibility_probe (label text PRIMARY KEY, body text NOT NULL,
    CHECK(length(label)>0));
INSERT INTO compatibility_probe VALUES ('acao', 'Ação de recuperação'),
    ('cafe', 'Café e atendimento'), ('unicode', '中文 teste');
CREATE INDEX compatibility_probe_fts ON compatibility_probe USING gin
    (to_tsvector('portuguese', body));
""",
            )
            dump = run(
                [
                    args.engine,
                    "exec",
                    legacy,
                    "pg_dump",
                    "-U",
                    "altvia_owner",
                    "-d",
                    "altvia_test",
                    "--no-owner",
                    "--no-acl",
                ]
            )
            run(
                [
                    *compose,
                    "exec",
                    "-T",
                    "postgres",
                    "createdb",
                    "-U",
                    "altvia_owner",
                    "altvia_restore_test",
                ]
            )
            restored_sql = [
                *compose,
                "exec",
                "-T",
                "postgres",
                "psql",
                "-X",
                "-v",
                "ON_ERROR_STOP=1",
                "-U",
                "altvia_owner",
                "-d",
                "altvia_restore_test",
            ]
            run(restored_sql, data=dump)
            query = (
                "SELECT md5(string_agg(label || body, ',' ORDER BY label COLLATE \"C\")) "
                "FROM compatibility_probe;"
            )
            source_hash = run([*legacy_sql, "-At", "-c", query]).strip()
            destination_hash = run([*restored_sql, "-At", "-c", query]).strip()
            assert source_hash == destination_hash and len(source_hash) == 32
            run(
                restored_sql,
                data="""
DO $$ BEGIN
    IF (SELECT count(*) FROM compatibility_probe) <> 3 OR
       (SELECT count(*) FROM compatibility_probe
        WHERE to_tsvector('portuguese', body) @@ plainto_tsquery('portuguese', 'recuperação')) <> 1
    THEN RAISE EXCEPTION 'Restored Unicode/FTS data mismatch'; END IF;
    BEGIN
        INSERT INTO compatibility_probe VALUES ('acao', 'duplicate');
        RAISE EXCEPTION 'Restored primary key missing';
    EXCEPTION WHEN unique_violation THEN NULL; END;
END $$;
""",
            )
            print("Bookworm-to-Alpine logical restore/Unicode/FTS/constraint proof passed.")
        finally:
            if legacy_started:
                run([args.engine, "rm", "-f", legacy])  # Synthetic source volume is preserved.
        exec_api(
            "from pathlib import Path; import importlib.util; "
            "assert not Path('/run/secrets/ALTVIA_RUNTIME_DATABASE_URL').exists(); "
            "assert not Path('/opt/altvia/.env').exists(); "
            "assert not Path('/opt/altvia/apps/api/altvia/__pycache__').exists(); "
            "assert importlib.util.find_spec('pytest') is None"
        )
        exec_api(
            "from pathlib import Path; assert not Path("
            + repr("/opt/altvia/apps/api/altvia/" + canary.name)
            + ").exists()"
        )
        seed = """
import json,sys
from sqlalchemy.orm import Session
from sqlalchemy.engine import make_url
from altvia.config import Settings
from altvia.database import make_engine
from altvia import management
s=Settings()
assert make_url(s.database_url.get_secret_value()).database == 'altvia_test'
data=json.load(sys.stdin)
with Session(make_engine(s)) as db, db.begin():
    management.bootstrap_admin(db,'admin@example.test','Container Admin',data['password'])
    management.create_user(db,'reader@example.test','Container Reader',data['password'])
"""
        exec_api(seed, {"password": password})
        with httpx.Client(
            base_url=origin,
            verify=str(secret_dir / "tls_cert"),
            headers={"Origin": origin},
            timeout=10,
            trust_env=False,
        ) as client:
            await_ready(client)
            document = client.get("/")
            assert document.status_code == 200 and "Altvia Workspace" in document.text
            assert "no-store" in document.headers["cache-control"]
            assert "'nonce-" in document.headers["content-security-policy"]
            assert "'unsafe-eval'" not in document.headers["content-security-policy"]
            assert client.get("/api/v1/auth/me").status_code == 401
            login = client.post(
                "/api/v1/auth/sessions", json={"email": "admin@example.test", "password": password}
            )
            assert login.status_code == 201
            assert (
                "Secure" in login.headers["set-cookie"]
                and "HttpOnly" in login.headers["set-cookie"]
            )
            client.headers["X-CSRF-Token"] = login.json()["csrf_token"]
            teams = []
            for name in ["Visible", "Hidden"]:
                response = client.post(
                    "/api/v1/teams", json={"name": name}, headers={"Idempotency-Key": uuid4().hex}
                )
                assert response.status_code == 201
                teams.append(response.json()["id"])
            path = f"/api/v1/teams/{teams[0]}"
            account_body = {
                "email": "http-administered@example.test",
                "display_name": "Container HTTP Account",
                "password": password,
            }
            account_headers = {"Idempotency-Key": uuid4().hex}
            account_response = client.post(
                "/api/v1/users", json=account_body, headers=account_headers
            )
            assert account_response.status_code == 201
            assert (
                client.post("/api/v1/users", json=account_body, headers=account_headers).json()
                == account_response.json()
            )
            account_path = f"/api/v1/users/{account_response.json()['id']}"
            password_headers = {"Idempotency-Key": uuid4().hex, "If-Match": '"1"'}
            reset = client.post(
                account_path + "/password", json={"password": password}, headers=password_headers
            )
            assert reset.status_code == 200 and reset.json()["version"] == 2
            assert (
                client.post(
                    account_path + "/password",
                    json={"password": password},
                    headers=password_headers,
                ).json()
                == reset.json()
            )
            changes = [
                ("team-roles", {"team_id": teams[0], "role_name": "viewer", "enabled": True}),
                ("team-roles", {"team_id": teams[0], "role_name": "viewer", "enabled": False}),
                ("activation", {"active": False}),
                ("activation", {"active": True}),
                ("platform-admin", {"enabled": True}),
                ("platform-admin", {"enabled": False}),
            ]
            for version, (suffix, body) in enumerate(changes, 2):
                changed = client.post(
                    account_path + "/" + suffix,
                    json=body,
                    headers={"Idempotency-Key": uuid4().hex, "If-Match": f'"{version}"'},
                )
                assert changed.status_code == 200 and changed.json()["version"] == version + 1
            assert client.get(account_path + "/team-roles").json()["items"] == []
            # Real registered JSON consumer, with synchronous writes available
            # even while the transport is stopped and subsequently lost/recreated.
            run([*compose, "stop", "redis"])
            changed = client.post(
                account_path + "/activation",
                json={"active": False},
                headers={"Idempotency-Key": uuid4().hex, "If-Match": '"8"'},
            )
            assert changed.status_code == 200 and changed.json()["version"] == 9
            assert client.get("/api/v1/health/ready").status_code == 200
            run(
                [
                    *compose,
                    "up",
                    "-d",
                    "--no-deps",
                    "--no-build",
                    "--force-recreate",
                    "--wait",
                    "redis",
                ]
            )
            for _ in range(60):
                activity = client.get("/api/v1/identity-activity?limit=100")
                assert activity.status_code == 200
                if any(
                    row["resource_id"] == account_response.json()["id"]
                    and row["aggregate_version"] == 9
                    for row in activity.json()["items"]
                ):
                    break
                time.sleep(0.5)
            else:
                raise RuntimeError("Durable worker did not recover after Redis loss")
            changed = client.post(
                account_path + "/activation",
                json={"active": True},
                headers={"Idempotency-Key": uuid4().hex, "If-Match": '"9"'},
            )
            assert changed.status_code == 200 and changed.json()["version"] == 10
            # Freeze only this disposable broker: existing sockets blackhole,
            # unlike a stopped service that immediately refuses connections.
            run([*compose, "pause", "redis"])
            try:
                batch = exec_api(
                    """
import json,sys
from sqlalchemy.orm import Session
from altvia.config import Settings
from altvia.database import make_engine
from altvia import management
with Session(make_engine(Settings())) as db, db.begin():
    user=management.create_user(db,'shutdown@example.test','Shutdown',json.load(sys.stdin)['password'])
    for active in [False,True]*13:
        management.set_account_active(db,'shutdown@example.test',active)
    print(json.dumps({'id':str(user.id)}))
""",
                    {"password": password},
                )
                batch_id = json.loads(batch)["id"]
                count_batch = """
import json,sys
from uuid import UUID
from sqlalchemy import select,func
from sqlalchemy.orm import Session
from altvia.config import WorkerSettings
from altvia.database import make_engine
from altvia.models import OutboxEvent,ActivityEvent
data=json.load(sys.stdin)
with Session(make_engine(WorkerSettings())) as db:
    table=ActivityEvent if data['projected'] else OutboxEvent
    resource=table.resource_id if data['projected'] else table.aggregate_id
    query=select(func.count()).select_from(table).where(resource==UUID(data['id']))
    if not data['projected']: query=query.where(table.status=='processing')
    print(db.scalar(query))
"""

                def batch_count(projected):
                    return int(
                        run(
                            [*compose, "exec", "-T", "worker", "python", "-c", count_batch],
                            data=json.dumps({"id": batch_id, "projected": projected}),
                        )
                    )

                for _ in range(40):
                    if batch_count(False) >= 24:
                        break
                    time.sleep(0.25)
                else:
                    raise RuntimeError("Outage proof did not observe a claimed dispatch batch")
                shutdown_started = time.monotonic()
                run([*compose, "stop", "-t", "30", "worker"], timeout=40)
                shutdown_seconds = time.monotonic() - shutdown_started
                worker_state = container("worker")["State"]
                assert worker_state["ExitCode"] == 0 and not worker_state["OOMKilled"]
                assert shutdown_seconds < 30
            finally:
                run([*compose, "unpause", "redis"])
            # Unpause restores sockets before the next healthcheck updates state.
            # Wait for that real dependency recovery before restarting the worker.
            for _ in range(30):
                if container("redis")["State"]["Health"]["Status"] == "healthy":
                    break
                time.sleep(0.5)
            else:
                raise RuntimeError("Redis health did not recover after the broker blackhole")
            run([*compose, "start", "worker"])
            for _ in range(120):
                if batch_count(True) == 27:
                    break
                time.sleep(0.5)
            else:
                raise RuntimeError("Interrupted dispatch leases did not recover after restart")
            (work / "worker-outage-proof.json").write_text(
                json.dumps(
                    {
                        "exit_code": 0,
                        "shutdown_seconds": shutdown_seconds,
                        "recovered_events": 27,
                        "broker_blackholed": True,
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            assert (
                client.patch(
                    path,
                    json={"name": "Forbidden"},
                    headers={"Origin": "https://other.example.test", "If-Match": '"1"'},
                ).status_code
                == 403
            )
            assert (
                client.patch(
                    path,
                    json={"name": "Forbidden"},
                    headers={"X-CSRF-Token": "wrong", "If-Match": '"1"'},
                ).status_code
                == 403
            )
            run([*compose, "up", "-d", "--no-deps", "--no-build", "--force-recreate", "api"])
            await_ready(client)
            assert client.get("/api/v1/auth/me").status_code == 200
            run([*compose, "up", "-d", "--no-deps", "--force-recreate", "postgres"])
            await_ready(client)
            assert client.get(path).json()["name"] == "Visible"
            assert client.get(account_path).json()["version"] == 10
            assert client.get("/api/v1/auth/me").status_code == 200
            run([*compose, "stop", "postgres"])
            assert client.get("/api/v1/health/ready").status_code == 503
            assert client.get("/api/v1/health/live").status_code == 200
            run([*compose, "start", "postgres"])
            await_ready(client)
            grant = """
import json,sys
from uuid import UUID
from sqlalchemy.orm import Session
from altvia.config import Settings
from altvia.database import make_engine
from altvia.management import set_team_role
with Session(make_engine(Settings())) as db,db.begin():
    set_team_role(db,'reader@example.test',UUID(json.load(sys.stdin)['team']),'viewer',True)
"""
            exec_api(grant, {"team": teams[0]})
            login = client.post(
                "/api/v1/auth/sessions", json={"email": "reader@example.test", "password": password}
            )
            assert login.status_code == 201 and login.json()["user"]["capabilities"] == []
            assert [row["id"] for row in client.get("/api/v1/teams").json()["items"]] == [teams[0]]
            assert client.get(f"/api/v1/teams/{teams[1]}").status_code == 404
            assert client.get("/api/v1/users").status_code == 403
            assert client.get(f"{path}/members").status_code == 200
        run(
            ["node", "scripts/container_browser.mjs", args.engine, project, str(work)],
            data=json.dumps(
                {"origin": origin, "email": "admin@example.test", "password": password}
            ),
            timeout=240,
        )
        run([*compose, "run", "--rm", "migrate"])
        run([*compose, "stop", "-t", "30", "worker"])
        assert container("worker")["State"]["ExitCode"] == 0
        run([*compose, "stop", "-t", "30", "web"])
        # Next16.4.5 closes the HTTP server/Next resources, then explicitly exits
        # 143 for SIGTERM (dist/server/lib/start-server.js). Do not normalize it.
        web_state = container("web")["State"]
        assert web_state["ExitCode"] == 143 and not web_state["OOMKilled"]
        run([*compose, "stop", "-t", "30", "api"])
        assert container("api")["State"]["ExitCode"] == 0
        logs = run([*compose, "logs", "--no-color"])
        assert all(
            value not in logs
            for value in [
                password,
                owner_password,
                runtime_password,
                worker_password,
                redis_password,
            ]
        )
        print(
            "Container TLS/ACL/accounts/worker/Redis/replay/persistence/readiness/"
            "non-root/secret/SIGTERM proof passed."
        )
    finally:
        socket.getaddrinfo = original_dns
        canary.unlink(missing_ok=True)
        web_canary.unlink(missing_ok=True)
        if started:
            run([*compose, "down"], timeout=90)
        print(f"Task stack stopped; volumes preserved. Private test configuration: {work}")


if __name__ == "__main__":
    main()
