"""Fail-closed source scan policy; retained evidence never contains source or secret matches."""

import argparse
import json
import re
from pathlib import Path


def sanitize(report: dict, kind: str) -> dict:
    findings = []
    if kind == "bandit":
        if report.get("errors") != [] or not isinstance(report.get("results"), list):
            raise ValueError("Incomplete SAST scan")
        rows = [
            (
                row.get("filename"),
                row.get("test_id"),
                row.get("issue_severity"),
                row.get("line_number"),
            )
            for row in report["results"]
        ]
    elif kind == "trivy":
        if report.get("SchemaVersion") != 2:
            raise ValueError("Incomplete secret scan")
        if "Results" not in report:
            # Trivy 0.75 omits Results on a successful clean filesystem scan.
            # An absent report or an explicit null must never become a clean scan.
            if (
                not isinstance(report.get("Trivy"), dict)
                or report["Trivy"].get("Version") != "0.75.0"
                or not isinstance(report.get("ArtifactName"), str)
                or not report["ArtifactName"]
                or report.get("ArtifactType") != "filesystem"
                or not isinstance(report.get("ReportID"), str)
                or not report["ReportID"]
                or not isinstance(report.get("CreatedAt"), str)
                or not report["CreatedAt"]
            ):
                raise ValueError("Incomplete secret scan")
        elif not isinstance(report["Results"], list):
            raise ValueError("Incomplete secret scan")
        rows = []
        for target in report.get("Results", []):
            secrets = target.get("Secrets", [])
            if not isinstance(secrets, list):
                raise ValueError("Invalid secret scan result")
            rows.extend(
                (target.get("Target"), row.get("RuleID"), row.get("Severity"), row.get("StartLine"))
                for row in secrets
            )
    else:
        raise ValueError("Unsupported scanner")
    for path, rule, severity, line in rows:
        if (
            not isinstance(path, str)
            or not 1 <= len(path) <= 1000
            or not isinstance(rule, str)
            or not re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", rule)
            or severity not in {"UNKNOWN", "LOW", "MEDIUM", "HIGH", "CRITICAL"}
            or type(line) is not int
            or line < 1
        ):
            raise ValueError("Invalid finding metadata")
        findings.append({"path": path, "rule": rule, "severity": severity, "line": line})
    return {
        "tool": kind,
        "findings": findings,
        "blocking_count": sum(
            kind == "trivy" or row["severity"] in {"MEDIUM", "HIGH", "CRITICAL", "UNKNOWN"}
            for row in findings
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("kind", choices=("bandit", "trivy"))
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    try:
        result = sanitize(json.loads(args.input.read_text()), args.kind)
        args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    except (ValueError, TypeError, KeyError, AttributeError, OSError):
        print("Source security evidence invalid; gate refused.")
        return 1
    print(
        f"Source security: {len(result['findings'])} findings; {result['blocking_count']} blocking."
    )
    return 1 if result["blocking_count"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
