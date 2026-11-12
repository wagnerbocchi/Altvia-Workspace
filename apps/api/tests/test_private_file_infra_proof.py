"""Guard proof artifacts against missing inventories and false clean acceptance."""

import importlib.util
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
