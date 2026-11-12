"""Required hosted external file-fixture boundary; local absence is an explicit skip."""

import os
from pathlib import Path

import pytest


def file_path(role):
    key = {
        "api": "ALTVIA_STORAGE_FILE",
        "scanner": "ALTVIA_SCANNER_STORAGE_FILE",
        "owner": "ALTVIA_FILE_OWNER_STORAGE_FILE",
    }[role]
    return Path(os.environ[key])


@pytest.fixture(scope="session")
def file_services():
    missing = [
        role
        for role in ["api", "scanner", "owner"]
        if not os.environ.get(
            {
                "api": "ALTVIA_STORAGE_FILE",
                "scanner": "ALTVIA_SCANNER_STORAGE_FILE",
                "owner": "ALTVIA_FILE_OWNER_STORAGE_FILE",
            }[role]
        )
    ]
    if missing:
        if os.environ.get("ALTVIA_REQUIRE_FILE_TESTS") == "1":
            pytest.fail("Required real S3 fixture configuration is missing")
        pytest.skip(
            "Real S3 file fixture not configured; mandatory hosted file gate runs this suite"
        )
    for role in ["api", "scanner", "owner"]:
        assert file_path(role).is_file(), "Configured real S3 fixture file is missing"
