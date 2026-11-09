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
