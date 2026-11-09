"""Build and scan the complete installed service images; no suppression policy."""

import argparse
import hashlib
import json
import subprocess
from collections import Counter
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
SCANNER = (
    "docker.io/aquasec/trivy@sha256:"
    "af6acf9a6b85dfe389a1941505c0ce9efef52a4719635e1a962f022a3d855daa"
)


def summarize_report(report: dict) -> dict[str, int]:
    results = report.get("Results")
    if report.get("SchemaVersion") != 2 or not isinstance(results, list) or not results:
        raise ValueError("Incomplete Trivy evidence")
    if not any(row.get("Class") == "os-pkgs" and row.get("Type") for row in results):
        raise ValueError("OS package detection missing")
    counts: Counter[str] = Counter()
    for row in results:
        for finding in row.get("Vulnerabilities", []):
            severity = finding.get("Severity")
            if severity not in {"UNKNOWN", "LOW", "MEDIUM", "HIGH", "CRITICAL"}:
                raise ValueError("Unrecognized vulnerability severity")
            counts[severity] += 1
    if counts["HIGH"] or counts["CRITICAL"]:
        raise RuntimeError(f"Installed HIGH/CRITICAL vulnerabilities: {dict(counts)}")
    return dict(counts)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--engine", choices=["docker", "podman"], default="docker")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--cache-dir", type=Path)
    parser.add_argument("--skip-db-update", action="store_true")
    args = parser.parse_args()
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    cache = (args.cache_dir or output / "cache").resolve()
    cache.mkdir(parents=True, exist_ok=True)
    manifest = {"scanner": SCANNER, "images": {}, "passed": False}
    prefix = "localhost/altvia-security-" + uuid4().hex[:10]
    engine = args.engine

    def run(command: list[str]) -> bytes:
        return subprocess.run(command, cwd=ROOT, check=True, capture_output=True).stdout

    scanner = [engine, "run", "--rm"]
    if engine == "podman":
        scanner.append("--cgroups=disabled")  # Dev scanner only; never service Compose limits.
    scanner.extend(
        [
            "--mount",
            f"type=bind,source={output},target=/scan,readonly",
            "--mount",
            f"type=bind,source={cache},target=/root/.cache/trivy",
            SCANNER,
        ]
    )
    try:
        # Download once. Every service in this run must use precisely the same DB.
        if not args.skip_db_update:
            run([*scanner, "image", "--download-db-only", "--quiet"])
        manifest["database_metadata"] = json.loads((cache / "db/metadata.json").read_text())
        with (cache / "db/trivy.db").open("rb") as database_file:
            manifest["database_sha256"] = hashlib.file_digest(database_file, "sha256").hexdigest()
        failed = False
        for service in ("api", "postgres", "ingress", "web"):
            tag = f"{prefix}:{service}"
            build = [engine, "build", "-f", f"infra/{service}.Dockerfile", "-t", tag, "."]
            if engine == "podman":
                build.insert(2, "--format=docker")
            run(build)
            identity = run([engine, "image", "inspect", "--format", "{{.Id}}", tag])
            archive = output / f"{service}.tar"
            try:
                save = [engine, "save", "-o", str(archive)]
                if engine == "podman":
                    save.append("--format=docker-archive")
                run([*save, tag])
                raw = run(
                    [
                        *scanner,
                        "image",
                        "--quiet",
                        "--skip-version-check",
                        "--skip-db-update",
                        "--scanners=vuln",
                        "--ignorefile=/dev/null",
                        "--list-all-pkgs",
                        "--format=json",
                        "--input",
                        f"/scan/{archive.name}",
                    ]
                )
                report_path = output / f"{service}.json"
                report_path.write_bytes(raw)
                entry = {
                    "image_id": identity.decode().strip(),
                    "report_sha256": hashlib.sha256(raw).hexdigest(),
                }
                manifest["images"][service] = entry
                try:
                    entry["counts"] = summarize_report(json.loads(raw))
                    print(service, json.dumps(entry), flush=True)
                except (ValueError, RuntimeError) as error:
                    failed = True
                    entry["failure"] = str(error)
                    print(service, str(error), flush=True)
            finally:
                archive.unlink(missing_ok=True)
        if failed:
            raise RuntimeError("Service image security gate failed; inspect retained JSON")
        manifest["passed"] = True
    finally:
        (output / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
