import json
import runpy

import pytest


def test_ci_source_reports_keep_all_severities_but_never_source_or_match():
    sanitize = runpy.run_path("scripts/summarize_source_security.py")["sanitize"]
    secret = "do-not-persist-a-credential"
    report = {
        "SchemaVersion": 2,
        "Results": [
            {
                "Target": "source/file.py",
                "Secrets": [
                    {
                        "RuleID": "private-key",
                        "Severity": "HIGH",
                        "StartLine": 4,
                        "Match": secret,
                        "Code": {"Lines": [{"Content": secret}]},
                    }
                ],
            }
        ],
    }
    result = sanitize(report, "trivy")
    assert secret not in json.dumps(result)
    assert result["blocking_count"] == 1 and result["findings"][0]["line"] == 4
    low = sanitize(
        {
            "errors": [],
            "results": [
                {
                    "test_id": "B101",
                    "issue_severity": "LOW",
                    "filename": "apps/api/cli.py",
                    "line_number": 5,
                    "code": secret,
                }
            ],
        },
        "bandit",
    )
    assert low["blocking_count"] == 0 and len(low["findings"]) == 1
    assert secret not in json.dumps(low)


def test_clean_pinned_trivy_report_can_omit_results_but_not_scanner_metadata():
    sanitize = runpy.run_path("scripts/summarize_source_security.py")["sanitize"]
    # The pinned scanner emits this shape with exit0 for a clean fs/secret scan.
    clean = {
        "SchemaVersion": 2,
        "Trivy": {"Version": "0.75.0"},
        "ReportID": "e0a76dd5-777b-4cbd-9c0e-4a839b2edc40",
        "CreatedAt": "2026-11-09T22:00:00Z",
        "ArtifactName": "/source",
        "ArtifactType": "filesystem",
    }
    assert sanitize(clean, "trivy") == {"tool": "trivy", "findings": [], "blocking_count": 0}
    for field in ("Trivy", "ArtifactName", "ArtifactType"):
        incomplete = {key: value for key, value in clean.items() if key != field}
        with pytest.raises(ValueError):
            sanitize(incomplete, "trivy")


@pytest.mark.parametrize(
    "report,kind",
    [
        ({}, "bandit"),
        ({"errors": ["failed"], "results": []}, "bandit"),
        ({"Results": []}, "trivy"),
        ({"SchemaVersion": 2, "Results": [{"Secrets": "bad"}]}, "trivy"),
    ],
)
def test_ci_security_rejects_incomplete_or_failed_scanner_data(report, kind):
    sanitize = runpy.run_path("scripts/summarize_source_security.py")["sanitize"]
    with pytest.raises(ValueError):
        sanitize(report, kind)
