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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--engine", choices=["docker", "podman"], default="docker")
    args = parser.parse_args()
    if os.environ.get("ALTVIA_ALLOW_CONTAINER_TEST") != "1":
        raise SystemExit("Explicit ALTVIA_ALLOW_CONTAINER_TEST=1 required")
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
    owner_password, runtime_password, password = [secrets.token_urlsafe(32) for _ in range(3)]
    files = {
        "postgres_password": owner_password,
        "owner_database_url": f"postgresql+psycopg://altvia_owner:{owner_password}@postgres/altvia_test",
        "runtime_database_url": f"postgresql+psycopg://altvia_app:{runtime_password}@postgres/altvia_test",
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
    }
    # Never inherit a host DB credential into the test stack.
    env.pop("ALTVIA_DATABASE_URL", None)
    compose = [args.engine, "compose", "-f", str(ROOT / "infra/compose.yaml"), "-p", project]

    def run(command, *, data=None, timeout=240):
        result = subprocess.run(
            command, input=data, text=True, capture_output=True, cwd=ROOT, env=env, timeout=timeout
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
    try:
        run(["node", "scripts/container_tls.mjs", str(secret_dir)])
        with canary.open("x", encoding="utf-8") as source:
            source.write(password)
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
        started = True
        run([*compose, "up", "-d", "--no-build", "--wait", "--wait-timeout", "150"])
        for service in ["api", "ingress"]:
            inspect = container(service)
            assert inspect["Config"]["User"] not in ("", "0", "root")
            assert inspect["HostConfig"]["ReadonlyRootfs"]
        for service in ["api", "postgres"]:
            assert not container(service)["HostConfig"].get("PortBindings")
        api_env = container("api")["Config"]["Env"]
        assert not any(item.startswith("ALTVIA_DATABASE_URL=") for item in api_env)
        exec_api(
            "from pathlib import Path; import importlib.util; "
            "assert not Path('/run/secrets/ALTVIA_RUNTIME_DATABASE_URL').exists(); "
            "assert not Path('/opt/altvia/.env').exists(); "
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
        run([*compose, "run", "--rm", "migrate"])
        run([*compose, "stop", "-t", "30", "api"])
        assert container("api")["State"]["ExitCode"] == 0
        logs = run([*compose, "logs", "--no-color"])
        assert all(value not in logs for value in [password, owner_password, runtime_password])
        print("Container TLS/ACL/persistence/readiness/non-root/secret/SIGTERM proof passed.")
    finally:
        socket.getaddrinfo = original_dns
        canary.unlink(missing_ok=True)
        if started:
            run([*compose, "down"], timeout=90)
        print(f"Task stack stopped; volumes preserved. Private test configuration: {work}")


if __name__ == "__main__":
    main()
