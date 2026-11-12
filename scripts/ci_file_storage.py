"""Bounded real S3 fixture for the single hosted API suite; no AV or public port."""

import argparse
import hashlib
import importlib.util
import ipaddress
import json
import os
import re
import secrets
import sys
import time
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]


def available_subnet(occupied):
    # Finite RFC1918 /24 candidates; never adopt an overlapping automatic pool.
    for subnet in ipaddress.ip_network("10.240.0.0/12").subnets(new_prefix=24):
        if not any(old.version == 4 and subnet.overlaps(old) for old in occupied):
            return subnet
    raise RuntimeError("private_network_pool_exhausted")


def network_create_command(project, subnet):
    return [
        "docker",
        "network",
        "create",
        "--driver",
        "bridge",
        "--internal",
        "--subnet",
        str(subnet),
        project,
    ]


def occupied_subnets(run):
    identifiers = run(["docker", "network", "ls", "--quiet"]).stdout.splitlines()
    if len(identifiers) > 256 or any(
        not re.fullmatch(r"[0-9a-f]{12,64}", identifier) for identifier in identifiers
    ):
        raise ValueError("private_network_inventory_invalid")
    if not identifiers:
        return []
    try:
        networks = json.loads(run(["docker", "network", "inspect", *identifiers]).stdout)
        if not isinstance(networks, list) or len(networks) != len(identifiers):
            raise ValueError
        occupied = []
        for network in networks:
            ipam = network["IPAM"]
            configs = ipam["Config"]
            if configs is None:
                if (network.get("Name"), network.get("Driver")) not in {
                    ("host", "host"),
                    ("none", "null"),
                } or ipam.get("Driver") != "default":
                    raise ValueError
                continue
            if not isinstance(configs, list):
                raise ValueError
            occupied.extend(ipaddress.ip_network(config["Subnet"]) for config in configs)
        return occupied
    except (ValueError, TypeError, KeyError):
        raise ValueError("private_network_inventory_invalid") from None


def create_private_network(run, project):
    # Native IPAM reserves the explicit pool. Re-inspect only a known overlap
    # race, at most three attempts; unrelated errors never broaden the fixture.
    for attempt in range(3):
        subnet = available_subnet(occupied_subnets(run))
        result = run(network_create_command(project, subnet), allow_failure=True)
        if result.returncode:
            if "pool overlaps with other one" in result.stderr.lower() and attempt < 2:
                continue
            raise RuntimeError("private_network_create_failed")
        try:
            rows = json.loads(run(["docker", "network", "inspect", project]).stdout)
            if not isinstance(rows, list) or len(rows) != 1:
                raise ValueError
            network = rows[0]
            configs = network["IPAM"]["Config"]
            address = subnet.network_address + 10
            if (
                network["Name"] != project
                or network["Driver"] != "bridge"
                or network["Internal"] is not True
                or len(configs) != 1
                or ipaddress.ip_network(configs[0]["Subnet"]) != subnet
                or ipaddress.ip_address(configs[0]["Gateway"]) not in subnet
                or ipaddress.ip_address(configs[0]["Gateway"]) == address
            ):
                raise ValueError
            return str(subnet), str(address)
        except (ValueError, TypeError, KeyError):
            raise ValueError("private_network_created_invalid") from None
    raise RuntimeError("private_network_create_failed")


def verify_suite(path: Path) -> int:
    # JUnit is our own bounded pytest output, not external XML or mail content.
    from defusedxml import ElementTree as SafeET

    if not path.is_file() or path.stat().st_size > 10 * 1024 * 1024:
        raise ValueError("file_suite_not_executed")
    root = SafeET.fromstring(
        path.read_bytes(), forbid_dtd=True, forbid_entities=True, forbid_external=True
    )
    groups = {"test_attachments": [], "test_attachment_scan": []}
    for case in root.iter("testcase"):
        module = case.get("classname", "").split(".")[-1]
        if module in groups:
            groups[module].append(case)
    if any(len(cases) < 10 for cases in groups.values()) or any(
        list(case) for cases in groups.values() for case in cases
    ):
        raise ValueError("file_suite_not_executed")
    return sum(map(len, groups.values()))


def hashes():
    paths = [
        p
        for directory in ["apps/api", "infra", "scripts"]
        for p in (ROOT / directory).rglob("*")
        if p.is_file() and "__pycache__" not in p.parts
    ]
    return {
        str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in paths
        if p.suffix in {".py", ".yaml", ".toml", ".mjs", ".conf", ".sh", ".Dockerfile"}
        or p.name.endswith("Dockerfile")
    } | {
        p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest()
        for p in ["pyproject.toml", "uv.lock"]
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["start", "verify", "stop"])
    args = parser.parse_args()
    if os.environ.get("ALTVIA_ALLOW_TEST_DB") != "1":
        raise SystemExit("Explicit disposable API test opt-in required")
    if args.command == "verify":
        count = verify_suite(ROOT / ".superpowers/api-tests.xml")
        print(f"Required real S3 attachment suites executed: {count} passed")
        return
    if args.command == "start":
        if not sys.platform.startswith("linux") or not os.environ.get("GITHUB_ENV"):
            raise SystemExit("Private bridge fixture requires the isolated Linux CI caller")
        os.umask(0o077)
        work = ROOT / ".superpowers/api-files" / ("altvia-api-files-" + uuid4().hex[:10])
        work.mkdir(mode=0o700, parents=True)
        manifest = {
            "passed": False,
            "commands": [],
            "source_hashes": hashes(),
            "project": work.name,
        }
        with Path(os.environ["GITHUB_ENV"]).open("a") as target:
            target.write(f"ALTVIA_FILE_TEST_WORK={work}\n")
    else:
        path = os.environ.get("ALTVIA_FILE_TEST_WORK")
        if not path:
            return
        work = Path(path).resolve()
        if work.parent != (ROOT / ".superpowers/api-files").resolve() or not work.name.startswith(
            "altvia-api-files-"
        ):
            raise SystemExit("Refusing non-task fixture path")
        manifest = json.loads((work / "manifest.json").read_text())
    private = work / "secrets"
    private.mkdir(mode=0o700, exist_ok=True)
    spec = importlib.util.spec_from_file_location(
        "file_infra_commands", ROOT / "scripts/private_file_infra_proof.py"
    )
    proof = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(proof)
    env = {**os.environ, "ALTVIA_ALLOW_FILE_INFRA_TEST": "1"}
    sensitive = []

    def run(command, **options):
        return proof.run_command(
            work, manifest, command, cwd=ROOT, env=env, sensitive_values=sensitive, **options
        )

    project = work.name
    try:
        if args.command == "stop":
            # Preserve the container, network, object volume and command evidence.
            run(["docker", "stop", "--time", "10", project], timeout=30, allow_failure=True)
            return
        image = project + ":storage"
        run(["docker", "build", "-f", "infra/storage.Dockerfile", "-t", image, "."], timeout=900)
        manifest["storage_image"] = run(
            ["docker", "image", "inspect", "--format", "{{.Id}}", image]
        ).stdout.strip()
        subnet, address = create_private_network(run, project)
        manifest["private_subnet"] = subnet
        run(["node", "scripts/file_test_certificate.mjs", str(private), address])
        sensitive.append((private / "storage_key").read_text())
        configs = {}
        for role in ["owner", "api", "scanner"]:
            config = {
                "endpoint": f"https://{address}:8443",
                "ca_file": str(private / "storage_ca"),
                "access_key": secrets.token_hex(16),
                "secret_key": secrets.token_hex(32),
            }
            sensitive.extend([config["access_key"], config["secret_key"]])
            configs[role] = private / ("storage_" + role)
            configs[role].write_text(json.dumps(config))
        owner = json.loads(configs["owner"].read_text())
        (private / "storage_root_access").write_text(owner["access_key"])
        (private / "storage_root_secret").write_text(owner["secret_key"])
        mounts = []
        for name in [
            "storage_root_access",
            "storage_root_secret",
            "storage_cert",
            "storage_key",
            "storage_ca",
        ]:
            (private / name).chmod(0o444)
            mounts += ["-v", f"{private / name}:/run/secrets/{name}:ro"]
        run(
            [
                "docker",
                "run",
                "-d",
                "--name",
                project,
                "--network",
                project,
                "--ip",
                address,
                "--network-alias",
                "storage",
                "--read-only",
                "--tmpfs",
                "/tmp:size=32m",
                "--cap-drop=ALL",
                "--security-opt=no-new-privileges:true",
                "--memory=256m",
                "--cpus=1",
                "--pids-limit=128",
                "-v",
                project + "-objects:/data",
                *mounts,
                image,
            ]
        )
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            state = run(
                ["docker", "inspect", "--format", "{{.State.Health.Status}}", project]
            ).stdout.strip()
            if state == "healthy":
                break
            time.sleep(1)
        else:
            raise RuntimeError("private_storage_not_healthy")
        from altvia.file_storage_owner import bootstrap, load_storage

        bootstrap(*(load_storage(configs[role]) for role in ["owner", "api", "scanner"]))
        ports = json.loads(
            run(
                ["docker", "inspect", "--format", "{{json .HostConfig.PortBindings}}", project]
            ).stdout
        )
        if ports:
            raise RuntimeError("private_storage_published_port")
        manifest["private_address"] = address
        manifest["bootstrap"] = "existing-native-owner-bootstrap"
        with Path(os.environ["GITHUB_ENV"]).open("a") as target:
            for key, value in {
                "ALTVIA_STORAGE_FILE": configs["api"],
                "ALTVIA_SCANNER_STORAGE_FILE": configs["scanner"],
                "ALTVIA_FILE_OWNER_STORAGE_FILE": configs["owner"],
                "ALTVIA_REQUIRE_FILE_TESTS": "1",
            }.items():
                target.write(f"{key}={value}\n")
        manifest["passed"] = True
    finally:
        manifest["final_source_hashes"] = hashes()
        manifest["source_unchanged"] = manifest["source_hashes"] == manifest["final_source_hashes"]
        (work / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
        if not manifest["source_unchanged"]:
            raise RuntimeError("fixture_source_changed")


if __name__ == "__main__":
    main()
