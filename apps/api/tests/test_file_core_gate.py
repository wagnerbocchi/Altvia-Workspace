"""The hosted full API gate cannot silently omit required private file tests."""

import importlib.util
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
