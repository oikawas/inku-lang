"""Bundle the license files of the exact Cargo.lock crates used for native builds."""

import os
from pathlib import Path
import sys
import tomllib


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit("usage: build_rust_notices.py CARGO_LOCK OUTPUT")

    lock_path = Path(sys.argv[1])
    output_path = Path(sys.argv[2])
    cargo_home = Path(os.environ.get("CARGO_HOME", Path.home() / ".cargo"))
    registry = cargo_home / "registry" / "src"
    packages = tomllib.loads(lock_path.read_text())["package"]
    entries = []

    for package in sorted(packages, key=lambda item: (item["name"], item["version"])):
        if not package.get("source", "").startswith("registry+"):
            continue
        name, version = package["name"], package["version"]
        matches = list(registry.glob(f"*/{name}-{version}"))
        if len(matches) != 1:
            raise SystemExit(f"expected one registry source for {name} {version}, found {len(matches)}")
        source = matches[0]
        manifest = tomllib.loads((source / "Cargo.toml").read_text())
        license_expression = manifest["package"].get("license", "UNDECLARED")
        if license_expression == "UNDECLARED":
            raise SystemExit(f"missing license expression for {name} {version}")
        files = sorted(
            path for path in source.iterdir()
            if path.is_file()
            and ("license" in path.name.lower() or path.name.upper().startswith("COPYING"))
        )
        entries.append(f"\n{'=' * 72}\n{name} {version}\nLicense: {license_expression}\n")
        entries.append(f"Exact source: https://crates.io/api/v1/crates/{name}/{version}/download\n")
        if not files:
            entries.append("No standalone license file is present in this crate archive.\n")
            continue
        for file in files:
            entries.append(f"\n--- {file.name} ---\n")
            entries.append(file.read_text(errors="replace"))
            entries.append("\n")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        "Rust dependency license files from core/Cargo.lock.\n"
        "This is a conservative lockfile inventory; not every crate necessarily\n"
        "contributes code to this binary. Missing standalone files are stated\n"
        "explicitly and require source/license review before public release.\n"
        + "".join(entries)
    )


if __name__ == "__main__":
    main()
