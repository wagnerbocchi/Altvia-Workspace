"""Security gate must inspect every target and fail closed on invalid evidence."""

import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "scan_service_images", Path(__file__).resolve().parents[3] / "scripts/scan_service_images.py"
)
scan = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scan)


def report(*vulnerabilities):
    return {
        "SchemaVersion": 2,
        "Results": [
            {"Class": "os-pkgs", "Type": "alpine", "Target": "OS"},
            {"Class": "lang-pkgs", "Target": "binary", "Vulnerabilities": list(vulnerabilities)},
        ],
    }


def test_gate_preserves_lower_severity_counts():
    assert scan.summarize_report(report({"Severity": "MEDIUM"})) == {"MEDIUM": 1}


@pytest.mark.parametrize("severity", ["HIGH", "CRITICAL"])
def test_gate_rejects_findings_in_non_os_targets(severity):
    with pytest.raises(RuntimeError, match="HIGH/CRITICAL"):
        scan.summarize_report(report({"Severity": severity}))


@pytest.mark.parametrize(
    "data",
    [
        {},
        {"SchemaVersion": 2, "Results": []},
        {"SchemaVersion": 2, "Results": [{"Class": "lang-pkgs"}]},
        report({"Severity": "unexpected"}),
        report({}),
    ],
)
def test_gate_refuses_incomplete_or_unrecognized_evidence(data):
    with pytest.raises((ValueError, RuntimeError)):
        scan.summarize_report(data)


@pytest.mark.parametrize("service", ["storage", "clamav"])
def test_private_service_gate_refuses_missing_native_or_go_inventory(service):
    with pytest.raises(ValueError, match="inventory"):
        scan.require_service_inventory(report(), service)
