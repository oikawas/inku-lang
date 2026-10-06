"""The shared Skia native notice inventory, used by platform packagers.

The Apple tuple shape and license labels match its existing notice snapshot.
Platform packagers own output formatting; versions, sources and texts live here.
"""

import json
from pathlib import Path
import tomllib

ROOT = Path(__file__).resolve().parents[1]
LICENSES = ROOT / "core/crates/inku-display/licenses"
SKIA_LICENSES = LICENSES / "skia-m153"
RUST_SKIA_LICENSE = LICENSES / "rust-skia-0.153.3-LICENSE"


def native_libraries(platform: str) -> tuple:
    if platform not in {"apple", "android"}:
        raise ValueError(f"unknown Skia notice platform: {platform}")
    manifest = json.loads((LICENSES / "native-libraries.json").read_text())
    cargo = tomllib.loads((LICENSES.parent / "Cargo.toml").read_text())
    for target in cargo["target"].values():
        if target["dependencies"]["skia-safe"]["version"] != "=" + manifest["binding_version"]:
            raise ValueError("Skia notice inventory does not match the pinned binding")
    if not RUST_SKIA_LICENSE.read_bytes():
        raise ValueError("empty rust-skia license")
    result = []
    for item in manifest["libraries"]:
        if platform not in item["platforms"]:
            continue
        for name in item["files"]:
            if Path(name).name != name or not (SKIA_LICENSES / name).read_bytes():
                raise ValueError(f"invalid Skia notice file: {name}")
        result.append((item["name"], item["version"], item["license"], item["source"],
                       item["files"], item["note"]))
    return tuple(result)


def bundle_android(write) -> None:
    """Emit the shared Android inventory and its exact texts through the packager."""
    libraries = native_libraries("android")
    names = sorted({name for _, _, _, _, files, _ in libraries for name in files})
    for name in names:
        write(f"skia/{name}", (SKIA_LICENSES / name).read_bytes())
    write(f"skia/{RUST_SKIA_LICENSE.name}", RUST_SKIA_LICENSE.read_bytes())
    inventory = [{"name": name, "version": version, "license": expression, "source": source,
                  "files": [f"skia/{file}" for file in files], "note": note}
                 for name, version, expression, source, files, note in libraries]
    write("skia/native-libraries.json", (json.dumps(inventory, indent=2) + "\n").encode())
