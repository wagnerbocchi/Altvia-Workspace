"""Verify the PostgreSQL-only API container capability contract, without secrets."""

import ctypes
import ctypes.util
import importlib
import importlib.util
import json
import subprocess
import sys
import sysconfig
from pathlib import Path


def check_package_installers() -> None:
    for module in ("pip", "ensurepip"):
        if importlib.util.find_spec(module) is not None:
            raise RuntimeError("Unsupported package installer capability is installed")
    stdlib = Path(sysconfig.get_path("stdlib"))
    for directory in {stdlib / "site-packages", Path(sysconfig.get_path("purelib"))}:
        if (directory / "pip").exists() or any(directory.glob("pip-*.dist-info")):
            raise RuntimeError("Unsupported global or virtual package installer remains")
    if any(stdlib.rglob("pip*.whl")):
        raise RuntimeError("Unsupported package installer bootstrap wheel remains")
    for name in ("pip", "pip3", f"pip{sys.version_info.major}.{sys.version_info.minor}"):
        if (Path(sys.base_prefix) / "bin" / name).exists():
            raise RuntimeError("Unsupported package installer entrypoint remains")


def check_runtime() -> dict[str, str]:
    for module in ("sqlite3", "_sqlite3"):
        if importlib.util.find_spec(module) is not None:
            raise RuntimeError("Unsupported SQLite Python capability is installed")
    package = subprocess.run(
        ["/sbin/apk", "info", "--exists", "sqlite-libs"],
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
    check_package_installers()
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
    import zlib

    data = b"Altvia native compression control" * 1024
    if zlib.decompress(zlib.compress(data)) != data:
        raise RuntimeError("Required native zlib roundtrip failed")
    return {
        "python": sys.version.split()[0],
        "sqlite": "absent",
        "package_installers": "absent",
        "zlib": zlib.ZLIB_RUNTIME_VERSION,
        "api_imports": "passed",
    }


if __name__ == "__main__":
    print(json.dumps(check_runtime(), sort_keys=True))
