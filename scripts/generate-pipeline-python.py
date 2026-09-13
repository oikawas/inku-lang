#!/usr/bin/env python3
"""Bundle the selected UniFFI Python binding from an explicitly built library.

Build in the target environment with scripts/rust-toolchain.sh first. This
generator does not render, install packages, or select a runtime route.
"""

import argparse
import hashlib
import json
import platform
import shutil
import subprocess
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--library", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    root, library, out = (p.resolve() for p in (args.root, args.library, args.out))
    expected = {
        "Darwin": "libinku_pipeline_uniffi.dylib",
        "Linux": "libinku_pipeline_uniffi.so",
    }.get(platform.system())
    if library.name != expected or not library.is_file():
        parser.error("--library must name the native pipeline library for this platform")
    if out.exists() and any(out.iterdir()):
        parser.error("--out must be an empty directory")
    out.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [str(root / "scripts/rust-toolchain.sh"), "run", "-p", "inku-pipeline-uniffi",
         "--features", "cli", "--bin", "uniffi-bindgen", "--locked", "--offline", "--",
         "generate", str(library), "--language", "python", "--out-dir", str(out),
         "--no-format"],
        check=True,
    )
    shutil.copy2(library, out / library.name)
    files = (library.name, "inku_pipeline_uniffi.py")
    manifest = {
        "schema": "inku.pipeline-python-bundle.v1",
        "platform": platform.system(),
        "machine": platform.machine(),
        "files": {name: hashlib.sha256((out / name).read_bytes()).hexdigest() for name in files},
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(out)


if __name__ == "__main__":
    main()
