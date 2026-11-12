"""Guard proof artifacts against missing inventories and false clean acceptance."""

import functools
import hashlib
import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "private_file_infra_proof",
    Path(__file__).resolve().parents[3] / "scripts/private_file_infra_proof.py",
)
proof = importlib.util.module_from_spec(spec)
spec.loader.exec_module(proof)


@pytest.mark.parametrize("memory", [2048 * 1024 * 1024, 4096 * 1024 * 1024])
def test_full_profile_refuses_inadequate_engine_memory(memory):
    with pytest.raises(RuntimeError, match="memory"):
        proof.require_capacity(memory)


def test_full_profile_requires_at_least_six_gib():
    proof.require_capacity(6 * 1024 * 1024 * 1024)


@pytest.mark.parametrize(
    "result",
    [
        {"disposition": "failed", "reason": "unavailable"},
        {
            "disposition": "clean",
            "reason": "clean",
            "engine": "1.4.5",
            "database_version": 28000,
            "database_date": "2026-11-12T09:00:00+00:00",
        },
        {
            "disposition": "clean",
            "reason": "clean",
            "engine": "1.4.6",
            "database_version": None,
            "database_date": None,
        },
    ],
)
def test_acceptance_refuses_fake_or_incomplete_scan_identity(result):
    with pytest.raises(RuntimeError):
        proof.require_scan(result, "clean", "clean")


def test_global_listing_refuses_any_bucket_or_continuation():
    proof.require_empty_buckets({"Buckets": [], "ResponseMetadata": {"HTTPStatusCode": 200}})
    with pytest.raises(RuntimeError):
        proof.require_empty_buckets(
            {"Buckets": [{"Name": "private"}], "ResponseMetadata": {"HTTPStatusCode": 200}}
        )
    with pytest.raises(RuntimeError):
        proof.require_empty_buckets(
            {
                "Buckets": [],
                "ContinuationToken": "secret",
                "ResponseMetadata": {"HTTPStatusCode": 200},
            }
        )


def test_command_evidence_preserves_real_crlf_and_arbitrary_bytes(tmp_path):
    manifest = {"commands": []}
    command = [
        sys.executable,
        "-c",
        "import sys;sys.stdout.buffer.write(b'out\\r\\nlf\\n\\xff');"
        "sys.stderr.buffer.write(b'err\\r\\n')",
    ]
    result = proof.run_command(tmp_path, manifest, command, cwd=tmp_path, env=None)
    assert result.stdout == "out\r\nlf\n\ufffd"
    assert result.stderr == "err\r\n"
    entry = manifest["commands"][0]
    assert entry["outcome"] == "exit" and entry["exit"] == 0
    for channel, expected in (("stdout", b"out\r\nlf\n\xff"), ("stderr", b"err\r\n")):
        assert (tmp_path / entry[channel + "_path"]).read_bytes() == expected
        assert entry[channel + "_sha256"] == hashlib.sha256(expected).hexdigest()
        assert entry[channel + "_original_sha256"] == hashlib.sha256(expected).hexdigest()
        assert not entry[channel + "_redacted"]


def test_command_redaction_binds_safe_and_private_original_bytes_separately(tmp_path):
    manifest = {"commands": []}
    command = [
        sys.executable,
        "-c",
        "import os,sys;sys.stdout.buffer.write(os.environ['PROOF_SECRET'].encode()+b'\\r\\n')",
    ]
    proof.run_command(
        tmp_path,
        manifest,
        command,
        cwd=tmp_path,
        env={**os.environ, "PROOF_SECRET": "synthetic-private-value"},
        sensitive_values=["synthetic-private-value"],
    )
    entry = manifest["commands"][0]
    original = b"synthetic-private-value\r\n"
    safe = b"[redacted-private-credential]\r\n"
    assert (tmp_path / entry["stdout_path"]).read_bytes() == safe
    assert (tmp_path / entry["stdout_original_path"]).read_bytes() == original
    assert entry["stdout_sha256"] == hashlib.sha256(safe).hexdigest()
    assert entry["stdout_original_sha256"] == hashlib.sha256(original).hexdigest()
    assert entry["stdout_redacted"]


def test_real_timeout_retains_partial_streams_and_unknown_exit(tmp_path):
    manifest = {"commands": []}
    command = [
        sys.executable,
        "-u",
        "-c",
        "import sys,time;sys.stdout.buffer.write(b'partial-out\\r\\n');sys.stdout.flush();"
        "sys.stderr.buffer.write(b'partial-err\\r\\n');sys.stderr.flush();time.sleep(30)",
    ]
    with pytest.raises(RuntimeError, match="timed out"):
        proof.run_command(tmp_path, manifest, command, cwd=tmp_path, env=None, timeout=2)
    entry = manifest["commands"][0]
    assert entry["command"] == command and entry["outcome"] == "timeout"
    assert entry["exit"] is None and entry["timeout_seconds"] == 2
    for channel, expected in (("stdout", b"partial-out\r\n"), ("stderr", b"partial-err\r\n")):
        assert (tmp_path / entry[channel + "_path"]).read_bytes() == expected
        assert entry[channel + "_original_sha256"] == hashlib.sha256(expected).hexdigest()


def test_cleanup_failure_and_timeout_preserve_original_failure_and_final_manifest(tmp_path):
    manifest = {"commands": [], "passed": True, "source_hashes": proof.source_hashes()}
    run = functools.partial(proof.run_command, tmp_path, manifest, cwd=tmp_path, env=None)
    cleanup = [
        ([sys.executable, "-c", "raise SystemExit(7)"], 2),
        (
            [
                sys.executable,
                "-u",
                "-c",
                "import sys,time;print('cleanup-partial',flush=True);time.sleep(30)",
            ],
            2,
        ),
    ]
    original = ValueError("original-failure")
    with pytest.raises(ValueError) as caught:
        try:
            raise original
        finally:
            proof.finalize_proof(tmp_path, manifest, run, cleanup, failure=sys.exception())
    assert caught.value is original
    saved = json.loads((tmp_path / "manifest.json").read_bytes())
    assert not saved["passed"] and saved["failure"]["type"] == "ValueError"
    assert len(saved["cleanup_failures"]) == 2
    assert [row["outcome"] for row in saved["commands"]] == ["exit", "timeout"]
    assert saved["commands"][0]["exit"] == 7 and saved["commands"][1]["exit"] is None
    assert (tmp_path / "001.stdout").read_bytes() in (b"cleanup-partial\n", b"cleanup-partial\r\n")


def test_cleanup_failure_without_primary_error_fails_after_manifest_persistence(tmp_path):
    manifest = {"commands": [], "passed": True, "source_hashes": proof.source_hashes()}
    run = functools.partial(proof.run_command, tmp_path, manifest, cwd=tmp_path, env=None)
    cleanup = [([sys.executable, "-c", "raise SystemExit(9)"], 2)]
    with pytest.raises(RuntimeError, match="finalization"):
        proof.finalize_proof(tmp_path, manifest, run, cleanup)
    saved = json.loads((tmp_path / "manifest.json").read_bytes())
    assert not saved["passed"] and saved["commands"][0]["exit"] == 9
    assert len(saved["cleanup_failures"]) == 1
