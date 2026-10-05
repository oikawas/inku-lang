#!/usr/bin/env python3
"""Write the macOS application's third-party notices from the exact locked inputs.

The output is a reviewed, committed snapshot that the About window shows. It is
regenerated explicitly; the release script runs --check so a dependency change
cannot ship with stale notices. Rust crates are those `cargo tree` resolves for
inku-pipeline-uniffi on both Apple targets (registry, git, path and vendored),
including proc-macro crates; build-script-only dependencies are not shipped.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
from pathlib import Path
import re
import struct
import subprocess
import tomllib

ROOT = Path(__file__).resolve().parents[2]
APPLE = ROOT / "apple"
OUTPUT = APPLE / "Sources/InkuUI/Resources/third-party-notices.json"
TARGETS = ("aarch64-apple-darwin", "x86_64-apple-darwin")
METER_MANIFEST = APPLE / "scripts/description-meter-resources.json"
METER_RESOURCES = APPLE / "Packages/InkuHost/Sources/InkuHost/Resources/description-meter"
FONT_RESOURCES = APPLE / "Packages/InkuExport/Sources/InkuExport/Resources"
SWIFT_CHECKOUTS = (APPLE / "build/macOS/SourcePackages/checkouts", APPLE / ".build/checkouts")
LICENSE_NAME = re.compile(r"^(licen[cs]e|copying|notice|copyright)", re.IGNORECASE)
# Crate archives without a license file, supplemented from the upstream repository's
# own file at the same release (the published crates are unmodified).
SUDACHIDICT_LEGAL = APPLE / "scripts/licenses/SudachiDict-v20260723-LEGAL"
UPSTREAM_LICENSES = {("https://github.com/mozilla/uniffi-rs", "0.32.0"): APPLE / "scripts/licenses/uniffi-rs-v0.32.0-LICENSE"}
# A new Swift package must be reviewed and named here before it can ship.
SWIFT_LICENSES = {"grdb.swift": "MIT"}
TREE_LINE = re.compile(r"^(\S+) v(\S+)(?: \(([^)]*)\))?$")


class NoticeError(Exception):
    pass


def run(command: list[str]) -> str:
    result = subprocess.run(command, text=True, capture_output=True, cwd=ROOT)
    if result.returncode:
        raise NoticeError(f"{' '.join(command[:3])} failed: {result.stderr.strip()}")
    return result.stdout


def cargo(*arguments: str) -> str:
    return run([str(ROOT / "scripts/rust-toolchain.sh"), *arguments])


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace").replace("\r\n", "\n").strip() + "\n"


class Notices:
    def __init__(self) -> None:
        self.components: list[dict] = []
        self.texts: dict[str, str] = {}

    def text(self, label: str, body: str) -> dict:
        key = hashlib.sha256(body.encode()).hexdigest()[:16]
        self.texts[key] = body
        return {"label": label, "text": key}

    def add(self, group: str, name: str, version: str, license_expression: str, source: str,
            texts: list[dict], note: str = "") -> None:
        if not texts:
            raise NoticeError(f"no license text for {name} {version}")
        self.components.append({"group": group, "name": name, "version": version,
                                "license": license_expression, "source": source,
                                "note": note, "texts": texts})


def license_files(directory: Path, stop: Path) -> list[Path]:
    """License files of a package, or of the nearest enclosing directory up to its root."""
    current = directory
    while True:
        files = sorted(path for path in current.iterdir() if path.is_file() and LICENSE_NAME.match(path.name))
        if files or current == stop or stop not in current.parents:
            return files
        current = current.parent


def toolchain_sysroot() -> Path:
    channel = tomllib.loads((ROOT / "core/rust-toolchain.toml").read_text())["toolchain"]["channel"]
    rustup = os.environ.get("INKU_RUSTUP_BIN") or str(Path(os.environ.get("CARGO_HOME", Path.home() / ".cargo")) / "bin/rustup")
    return Path(run([rustup, "run", channel, "rustc", "--print", "sysroot"]).strip())


def standard_texts(notices: Notices, sysroot: Path, package: dict) -> list[dict]:
    expression = package["license"]
    upstream = UPSTREAM_LICENSES.get((package.get("repository"), package["version"]))
    if upstream is not None:
        return [notices.text(f"{upstream.name} (the crate archive has no license file)", read_text(upstream))]
    names = {"MIT": "MIT.txt", "Apache-2.0": "Apache-2.0.txt", "BSD-2-Clause": "BSD-2-Clause.txt", "ISC": "ISC.txt"}
    for identifier in re.findall(r"[A-Za-z0-9.\-]+", expression):
        if identifier in names:
            body = read_text(sysroot / "share/doc/rust/licenses" / names[identifier])
            return [notices.text(f"{identifier} (standard text; the crate archive has no license file)", body)]
    raise NoticeError(f"no standard text for {expression}")


def rust_crates(notices: Notices, sysroot: Path) -> None:
    # All features, so the metadata also locates the generator-only uniffi_bindgen.
    metadata = json.loads(cargo("metadata", "--format-version", "1", "--locked", "--offline", "--all-features"))
    packages = metadata["packages"]
    members: set[tuple[str, str, str]] = set()
    for target in TARGETS:
        tree = cargo("tree", "--locked", "--offline", "-p", "inku-pipeline-uniffi", "--target", target,
                     "-e", "normal", "--prefix", "none", "--format", "{p}")
        for line in tree.splitlines():
            match = TREE_LINE.match(line.strip().removesuffix(" (*)").removesuffix(" (proc-macro)"))
            if not match:
                raise NoticeError(f"unexpected cargo tree line: {line}")
            members.add((match[1], match[2], match[3] or ""))
    # The Swift binding compiled into the app is generated from uniffi_bindgen's templates.
    members.add(("uniffi_bindgen", "0.32.0", ""))
    cargo_home = Path(os.environ.get("CARGO_HOME", Path.home() / ".cargo")).resolve()
    for name, version, source in sorted(members):
        candidates = [item for item in packages if item["name"] == name and item["version"] == version]
        if source.startswith("/"):
            candidates = [item for item in candidates if Path(item["manifest_path"]).parent == Path(source)]
        elif source:
            candidates = [item for item in candidates if (item["source"] or "").startswith("git+")]
        else:
            candidates = [item for item in candidates if (item["source"] or "").startswith("registry+")]
        if len(candidates) != 1:
            raise NoticeError(f"cannot identify {name} {version} {source} in cargo metadata")
        package = candidates[0]
        directory = Path(package["manifest_path"]).parent.resolve()
        expression = package.get("license") or ""
        if not expression:
            raise NoticeError(f"missing license expression for {name} {version}")
        note = ""
        if package["source"] is None and directory.is_relative_to(ROOT / "core/vendor"):
            relative = directory.relative_to(ROOT)
            origin = f"vendored in this repository at {relative}"
            source_url = f"https://crates.io/crates/{name}/{version}"
            note = (f"Vendored at {relative} from the published crate, with inku changes "
                    f"described in {relative}/INKU_PATCHES.md.")
            stop = directory
        elif package["source"] is None:
            origin = f"this repository, {directory.relative_to(ROOT)}"
            source_url = "https://github.com/oikawas/inku-lang"
            stop = ROOT
        elif package["source"].startswith("git+"):
            repository, revision = package["source"][4:].split("#", 1)
            repository = repository.split("?", 1)[0].removesuffix(".git")
            origin = f"git {repository} at {revision}"
            source_url = f"{repository}/tree/{revision}"
            # A git dependency's license may sit at the repository root above the crate.
            stop = next(parent for parent in [directory, *directory.parents]
                        if parent.parent.name == "checkouts" and parent.is_relative_to(cargo_home))
        else:
            origin = "crates.io"
            source_url = f"https://crates.io/crates/{name}/{version}"
            stop = directory
        if "MPL" in expression:
            note = ("Unmodified. Source Code Form: "
                    f"https://crates.io/api/v1/crates/{name}/{version}/download")
        files = license_files(directory, stop)
        texts = ([notices.text(path.name, read_text(path)) for path in files]
                 if files else standard_texts(notices, sysroot, package))
        notices.add("rust", name, version, expression, source_url, texts, note or f"From {origin}.")


def swift_packages(notices: Notices) -> None:
    pins: dict[str, dict] = {}
    resolved = sorted(path for path in APPLE.rglob("Package.resolved")
                      if not any(part in {".build", "build"} for part in path.relative_to(APPLE).parts))
    for path in resolved:
        for pin in json.loads(path.read_text())["pins"]:
            previous = pins.setdefault(pin["identity"], pin)
            if previous["state"] != pin["state"]:
                raise NoticeError(f"Package.resolved files disagree on {pin['identity']}")
    for identity, pin in sorted(pins.items()):
        if identity not in SWIFT_LICENSES:
            raise NoticeError(f"review the license of the new Swift package {identity}")
        revision = pin["state"]["revision"]
        checkout = next((base / Path(pin["location"]).stem for base in SWIFT_CHECKOUTS
                         if (base / Path(pin["location"]).stem).is_dir()
                         and run(["git", "-C", str(base / Path(pin["location"]).stem), "rev-parse", "HEAD"]).strip() == revision),
                        None)
        if checkout is None:
            raise NoticeError(f"no checkout of {identity} at {revision}; build the app or run swift build first")
        files = license_files(checkout, checkout)
        location = pin["location"].removesuffix(".git")
        notices.add("swift", Path(pin["location"]).stem, pin["state"]["version"], SWIFT_LICENSES[identity],
                    f"{location}/tree/{pin['state']['version']}",
                    [notices.text(path.name, read_text(path)) for path in files],
                    f"Swift package at revision {revision}.")


def rust_standard_library(notices: Notices, sysroot: Path) -> None:
    channel = tomllib.loads((ROOT / "core/rust-toolchain.toml").read_text())["toolchain"]["channel"]
    page = (sysroot / "share/doc/rust/COPYRIGHT-library.html").read_text(encoding="utf-8")
    page = re.sub(r"<(br|/p|/div|/h[1-6]|/li|/pre)[^>]*>", "\n", page)
    plain = html.unescape(re.sub(r"<[^>]+>", "", page))
    plain = re.sub(r"\n[ \t]*(?:\n[ \t]*)+", "\n\n", "\n".join(line.rstrip() for line in plain.splitlines()))
    licenses = sysroot / "share/doc/rust/licenses"
    notices.add("rust", "Rust standard library", channel, "MIT OR Apache-2.0",
                f"https://github.com/rust-lang/rust/tree/{channel}/library",
                [notices.text("COPYRIGHT-library", plain.strip() + "\n"),
                 notices.text("MIT", read_text(licenses / "MIT.txt")),
                 notices.text("Apache-2.0", read_text(licenses / "Apache-2.0.txt"))],
                "Linked into the native core library.")


def font_name(path: Path, wanted: int) -> str:
    data = path.read_bytes()
    count = struct.unpack(">H", data[4:6])[0]
    for index in range(count):
        tag, _, offset, _ = struct.unpack(">4sIII", data[12 + 16 * index:28 + 16 * index])
        if tag != b"name":
            continue
        _, records, strings = struct.unpack(">HHH", data[offset:offset + 6])
        for record in range(records):
            platform, _, _, name_id, length, start = struct.unpack(
                ">6H", data[offset + 6 + 12 * record:offset + 18 + 12 * record])
            if platform == 3 and name_id == wanted:
                begin = offset + strings + start
                return data[begin:begin + length].decode("utf-16-be")
    raise NoticeError(f"{path.name} has no name record {wanted}")


def bundled_resources(notices: Notices) -> None:
    manifest = json.loads(METER_MANIFEST.read_text())
    meter_license = METER_RESOURCES / "SudachiDict-LICENSE.txt"
    if not meter_license.is_file():
        raise NoticeError("prepare the description meter resources first (apple/scripts/prepare-meter-resources.py)")
    engine, japanese, english = manifest["sudachi_engine"], manifest["japanese_dictionary"], manifest["english_dictionary"]
    notices.add("resources", "Sudachi settings and character definitions", engine["version"], engine["license"],
                f"{engine['source']}/tree/{engine['revision']}/python/py_src/sudachipy/resources",
                [notices.text("LICENSE", read_text(METER_RESOURCES / "Sudachi-LICENSE.txt"))],
                "sudachi.json, char.def, rewrite.def and unk.def, unmodified.")
    notices.add("resources", f"SudachiDict ({japanese['edition']})", japanese["version"], japanese["license"],
                japanese["source"], [notices.text("LICENSE-2.0.txt", read_text(meter_license)),
                                     notices.text("LEGAL", read_text(SUDACHIDICT_LEGAL))],
                "system.dic, unmodified, from the PyPI sudachidict-small package. The wheel omits the upstream LEGAL "
                "notice for the UniDic data in the small lexicon, so it is reproduced from the v20260723 tag.")
    notices.add("resources", "The CMU Pronouncing Dictionary", english["revision"][:12], "BSD-2-Clause-style (CMU)",
                f"{english['source']}/tree/{english['revision']}",
                [notices.text("LICENSE", read_text(ROOT / "server/src/inku_server/cmudict/LICENSE"))],
                "cmudict.dict, unmodified. Copyright (C) 1993-2015 Carnegie Mellon University.")
    font = FONT_RESOURCES / "NotoSerifJP-Variable.ttf"
    notices.add("resources", "Noto Serif JP", font_name(font, 5).split(";", 1)[0].removeprefix("Version "), "OFL-1.1",
                "https://github.com/notofonts/noto-cjk",
                [notices.text("OFL.txt", read_text(FONT_RESOURCES / "OFL.txt"))],
                f"NotoSerifJP-Variable.ttf, unmodified. Font copyright: {font_name(font, 0)}")


def build() -> dict:
    notices = Notices()
    sysroot = toolchain_sysroot()
    notices.add("inku", "inku", "", "MIT", "https://github.com/oikawas/inku-lang",
                [notices.text("LICENSE", read_text(ROOT / "LICENSE"))],
                "This application, its native core and its bundled resources made for inku.")
    swift_packages(notices)
    rust_standard_library(notices, sysroot)
    rust_crates(notices, sysroot)
    bundled_resources(notices)
    return {"schema": "inku.macos-third-party-notices.v1",
            "inputs": {"core/Cargo.lock": hashlib.sha256((ROOT / "core/Cargo.lock").read_bytes()).hexdigest(),
                       "apple/Package.resolved": hashlib.sha256((APPLE / "Package.resolved").read_bytes()).hexdigest()},
            "components": notices.components, "texts": dict(sorted(notices.texts.items()))}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true", help="Fail when the committed snapshot differs")
    arguments = parser.parse_args()
    try:
        notices = build()
        rendered = json.dumps(notices, ensure_ascii=False, indent=1) + "\n"
    except (NoticeError, OSError, KeyError, ValueError) as error:
        print(f"Third-party notices unavailable: {error}")
        return 1
    if arguments.check:
        if not OUTPUT.is_file() or OUTPUT.read_text(encoding="utf-8") != rendered:
            print(f"{OUTPUT.relative_to(ROOT)} is stale; run apple/scripts/build-macos-notices.py and review the diff")
            return 1
        print(f"Third-party notices match the locked inputs ({len(notices['components'])} components)")
        return 0
    OUTPUT.write_text(rendered, encoding="utf-8")
    print(f"Wrote {OUTPUT.relative_to(ROOT)} ({len(notices['components'])} components)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
