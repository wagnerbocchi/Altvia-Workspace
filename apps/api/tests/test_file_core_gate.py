"""The hosted full API gate cannot silently omit required private file tests."""

import importlib.util
import ipaddress
import json
import subprocess
from pathlib import Path

import pytest


def gate():
    path = Path("scripts/ci_file_storage.py")
    assert path.is_file(), "bounded hosted S3 fixture owner missing"
    spec = importlib.util.spec_from_file_location("ci_file_storage", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_required_gate_rejects_empty_skipped_or_failed_file_suites(tmp_path):
    owner = gate()
    for contents in [
        "<testsuites/>",
        '<testsuites><testsuite><testcase classname="test_attachments">'
        "<skipped/></testcase></testsuite></testsuites>",
        '<testsuites><testsuite><testcase classname="test_attachment_scan">'
        "<failure/></testcase></testsuite></testsuites>",
    ]:
        path = tmp_path / "result.xml"
        path.write_text(contents)
        with pytest.raises(ValueError, match="file_suite_not_executed"):
            owner.verify_suite(path)


def test_api_job_starts_requires_verifies_and_stops_its_real_s3_fixture():
    source = Path(".github/workflows/api-ci.yml").read_text()
    assert "scripts/ci_file_storage.py start" in source
    assert "scripts/ci_file_storage.py verify" in source
    assert "scripts/ci_file_storage.py stop" in source
    assert 'ALTVIA_REQUIRE_FILE_TESTS: "1"' in source
    assert source.count("uv run pytest -q") == 1


def test_required_gate_accepts_executed_successful_real_service_suites(tmp_path):
    owner = gate()
    cases = "".join(
        f'<testcase classname="{module}" name="{number}"/>'
        for module in ["test_attachments", "test_attachment_scan"]
        for number in range(10)
    )
    path = tmp_path / "result.xml"
    path.write_text("<testsuites><testsuite>" + cases + "</testsuite></testsuites>")
    assert owner.verify_suite(path) == 20


class NativeNetwork:
    """Only the native network command boundary; no HTTP or file-status mocks."""

    def __init__(self, occupied=(), failures=()):
        self.occupied = list(occupied)
        self.failures = list(failures)
        self.calls = []
        self.created = None

    def run(self, command, **options):
        self.calls.append((command, options))
        if command[1:] == ["network", "ls", "--quiet"]:
            output = "\n".join(f"{index + 1:012x}" for index in range(len(self.occupied)))
            return subprocess.CompletedProcess(command, 0, output, "")
        if command[1:3] == ["network", "inspect"]:
            if self.created and command[3] == self.created["Name"]:
                rows = [self.created]
            else:
                rows = [{"IPAM": {"Config": [{"Subnet": subnet}]}} for subnet in self.occupied]
            return subprocess.CompletedProcess(command, 0, json.dumps(rows), "")
        assert command[1:3] == ["network", "create"]
        assert "--subnet" in command, "Docker static endpoints require a user-configured subnet"
        assert "--internal" in command and command[command.index("--driver") + 1] == "bridge"
        subnet = command[command.index("--subnet") + 1]
        proposed = ipaddress.ip_network(subnet)
        assert all(not proposed.overlaps(ipaddress.ip_network(old)) for old in self.occupied)
        if self.failures:
            message = self.failures.pop(0)
            if "overlap" in message.lower():
                self.occupied.append(subnet)
            return subprocess.CompletedProcess(command, 1, "", message)
        self.created = {
            "Name": command[-1],
            "Driver": "bridge",
            "Internal": True,
            "IPAM": {"Config": [{"Subnet": subnet, "Gateway": str(proposed.network_address + 1)}]},
        }
        return subprocess.CompletedProcess(command, 0, "created-id\n", "")


def native_owner():
    owner = gate()
    assert callable(getattr(owner, "create_private_network", None)), (
        "explicit native IPAM owner missing"
    )
    return owner


def test_native_network_explicit_nonoverlapping_subnet_precedes_static_endpoint():
    native = NativeNetwork(["172.17.0.0/16", "10.240.0.0/24", "fd00::/64"])
    subnet, address = native_owner().create_private_network(
        native.run, "altvia-api-files-0123456789"
    )
    assert subnet == "10.240.1.0/24" and address == "10.240.1.10"
    create = next(command for command, _ in native.calls if command[2] == "create")
    assert create.index("--subnet") < len(create) - 1
    assert native.calls[0][0][1:] == ["network", "ls", "--quiet"]
    assert native.calls[-1][0][1:] == ["network", "inspect", "altvia-api-files-0123456789"]


def test_native_network_pool_exhaustion_does_not_create_or_broaden():
    native = NativeNetwork(["10.240.0.0/12"])
    with pytest.raises(RuntimeError, match="private_network_pool_exhausted"):
        native_owner().create_private_network(native.run, "altvia-api-files-0123456789")
    assert not any(command[2] == "create" for command, _ in native.calls)


def test_native_network_overlap_race_rechecks_inventory_before_retry():
    native = NativeNetwork(failures=["Pool overlaps with other one on this address space"])
    subnet, address = native_owner().create_private_network(
        native.run, "altvia-api-files-0123456789"
    )
    assert (subnet, address) == ("10.240.1.0/24", "10.240.1.10")
    assert sum(command[2] == "create" for command, _ in native.calls) == 2
    assert sum(command[2] == "ls" for command, _ in native.calls) == 2


def test_native_network_overlap_retries_are_finite_and_other_errors_fail_once():
    for message, expected in [("Pool overlaps with other one", 3), ("permission denied", 1)]:
        native = NativeNetwork(failures=[message] * 4)
        with pytest.raises(RuntimeError, match="private_network_create_failed"):
            native_owner().create_private_network(native.run, "altvia-api-files-0123456789")
        assert sum(command[2] == "create" for command, _ in native.calls) == expected


def test_native_network_malformed_inventory_fails_before_creation():
    native = NativeNetwork(["not-a-cidr"])
    with pytest.raises(ValueError, match="private_network_inventory_invalid"):
        native_owner().create_private_network(native.run, "altvia-api-files-0123456789")
    assert not any(command[2] == "create" for command, _ in native.calls)


def test_native_network_inventory_is_bounded_before_inspection():
    native = NativeNetwork(["172.17.0.0/16"] * 257)
    with pytest.raises(ValueError, match="private_network_inventory_invalid"):
        native_owner().create_private_network(native.run, "altvia-api-files-0123456789")
    assert len(native.calls) == 1


def test_native_network_created_boundary_is_verified_before_returning_endpoint():
    native = NativeNetwork()

    def unexpected_public_network(command, **options):
        result = native.run(command, **options)
        if command[2] == "inspect" and native.created is not None:
            rows = json.loads(result.stdout)
            rows[0]["Internal"] = False
            result.stdout = json.dumps(rows)
        return result

    with pytest.raises(ValueError, match="private_network_created_invalid"):
        native_owner().create_private_network(
            unexpected_public_network, "altvia-api-files-0123456789"
        )
