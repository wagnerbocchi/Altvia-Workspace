"""Verify the PostgreSQL-only API container capability contract, without secrets."""

import ctypes
import ctypes.util
import importlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path


def check_runtime() -> dict[str, str]:
    for module in ("sqlite3", "_sqlite3"):
        if importlib.util.find_spec(module) is not None:
            raise RuntimeError("Unsupported SQLite Python capability is installed")
    package = subprocess.run(
        ["/usr/bin/dpkg-query", "--show", "libsqlite3-0"],
        text=True,
        capture_output=True,
        check=False,
    )
    if package.returncode != 1 or package.stdout:
        raise RuntimeError("SQLite package absence could not be established")
    if ctypes.util.find_library("sqlite3") is not None:
        raise RuntimeError("Unsupported SQLite shared library is discoverable")
    try:
        ctypes.CDLL("libsqlite3.so.0")
    except OSError:
        pass
    else:
        raise RuntimeError("Unsupported SQLite shared library is loadable")
    for directory in {Path(sys.base_prefix) / "lib", Path(sys.prefix) / "lib", Path("/usr/lib")}:
        if any(directory.rglob("*sqlite*.so*")):
            raise RuntimeError("SQLite native object remains in the runtime")
    # Keep the API's required native/stdlib and CLI/migration paths usable.
    for module in (
        "ssl",
        "zlib",
        "gzip",
        "zipfile",
        "bz2",
        "lzma",
        "hashlib",
        "termios",
        "psycopg",
        "argon2",
        "alembic",
        "altvia.main",
        "altvia.cli",
        "altvia.provision",
    ):
        importlib.import_module(module)
    return {"python": sys.version.split()[0], "sqlite": "absent", "api_imports": "passed"}


if __name__ == "__main__":
    print(json.dumps(check_runtime(), sort_keys=True))
