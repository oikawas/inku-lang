"""Build CPython's unchanged SQLite module against the selected Ubuntu library."""

from __future__ import annotations

import hashlib
import json
import shlex
import shutil
import subprocess
import sys
import sysconfig
import tarfile
import tempfile
import urllib.request
from pathlib import Path

ROOT = Path("/opt/inku-sqlite")


def main() -> None:
    contract = json.loads((ROOT / "contract.json").read_text())
    version = contract["python_version"]
    if sys.version.split()[0] != version:
        raise RuntimeError("Python interpreter does not match the SQLite build contract")
    with tempfile.TemporaryDirectory(prefix="inku-sqlite-build-") as temporary:
        folder = Path(temporary)
        archive = folder / "python.tar.xz"
        with urllib.request.urlopen(
            f"https://www.python.org/ftp/python/{version}/Python-{version}.tar.xz", timeout=60
        ) as response, archive.open("wb") as output:
            shutil.copyfileobj(response, output)
        if hashlib.sha256(archive.read_bytes()).hexdigest() != contract["python_source_sha256"]:
            raise RuntimeError("CPython source checksum mismatch")
        with tarfile.open(archive) as source:
            source.extractall(folder, filter="data")
        sources = folder / f"Python-{version}"
        include = Path(sysconfig.get_path("include"))
        module = Path(sysconfig.get_config_var("DESTSHARED")) / (
            "_sqlite3" + sysconfig.get_config_var("EXT_SUFFIX")
        )
        command = [
            *shlex.split(sysconfig.get_config_var("LDSHARED")),
            *shlex.split(sysconfig.get_config_var("CFLAGS")),
            *shlex.split(sysconfig.get_config_var("CCSHARED")),
            "-DPy_BUILD_CORE_MODULE=1",
            f"-I{ROOT / 'include'}", f"-I{include}", f"-I{include / 'internal'}",
            *shlex.split(sysconfig.get_config_var("MODULE__SQLITE3_CFLAGS") or ""),
            *map(str, sorted((sources / "Modules" / "_sqlite").glob("*.c"))),
            f"-L{ROOT / 'lib'}", f"-Wl,-rpath,{ROOT / 'lib'}", "-lsqlite3", "-o", str(module),
        ]
        subprocess.run(command, check=True)
        shutil.copyfile(sources / "LICENSE", ROOT / "licenses" / "CPython-LICENSE.txt")
        metadata = {
            **contract,
            "library_sha256": hashlib.sha256((ROOT / "lib" / "libsqlite3.so.0").read_bytes()).hexdigest(),
            "module_sha256": hashlib.sha256(module.read_bytes()).hexdigest(),
        }
        (ROOT / "metadata.json").write_text(json.dumps(metadata, indent=2) + "\n")


if __name__ == "__main__":
    main()
