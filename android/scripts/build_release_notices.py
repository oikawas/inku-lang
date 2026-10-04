"""Bundle resolved Android runtime notices and the conservative Rust inventory."""

import argparse
import hashlib
import io
import json
import re
import subprocess
import sys
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

NS = {"m": "http://maven.apache.org/POM/4.0.0"}
ROOT = Path(__file__).resolve().parents[2]


def pom(cache, group, name, version):
    paths = list((cache / group / name / version).glob("*/*.pom"))
    if len(paths) == 1:
        return ET.fromstring(paths[0].read_bytes())
    if paths:
        raise ValueError(f"ambiguous POM: {group}:{name}:{version}")
    relative = f"{group.replace('.', '/')}/{name}/{version}/{name}-{version}.pom"
    for base in ("https://repo.maven.apache.org/maven2/", "https://dl.google.com/dl/android/maven2/"):
        try:
            with urllib.request.urlopen(base + relative, timeout=30) as response:
                return ET.fromstring(response.read(1024 * 1024))
        except urllib.error.HTTPError as error:
            if error.code != 404:
                raise
    raise ValueError(f"missing POM: {group}:{name}:{version}")


def declared_licenses(cache, group, name, version, depth=0):
    if depth > 8:
        raise ValueError("POM parent chain too deep")
    document = pom(cache, group, name, version)
    result = [{"name": node.findtext("m:name", namespaces=NS),
               "url": node.findtext("m:url", namespaces=NS)}
              for node in document.findall("m:licenses/m:license", NS)]
    if result:
        return result
    parent = document.find("m:parent", NS)
    if parent is not None:
        return declared_licenses(cache, *(parent.findtext(f"m:{field}", namespaces=NS)
                                         for field in ("groupId", "artifactId", "version")), depth + 1)
    # JSR-330's published v1 POM omits licenses. Its exact source jar carries
    # the Apache-2.0 headers; keep the source location in the inventory.
    if (group, name, version) == ("javax.inject", "javax.inject", "1"):
        return [{"name": "Apache-2.0", "url": "https://www.apache.org/licenses/LICENSE-2.0.txt"}]
    raise ValueError(f"missing license declaration: {group}:{name}:{version}")


def archive_notices(data, prefix=""):
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        for name in sorted(archive.namelist()):
            if name.endswith("/"):
                continue
            if any(word in name.lower() for word in ("license", "notice", "copying")):
                yield prefix + name, archive.read(name)
            if name == "classes.jar":
                yield from archive_notices(archive.read(name), prefix + "classes.jar/")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--gradle-cache", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output / "licenses"
    output.mkdir(parents=True, exist_ok=True)
    records = []
    files = {}

    def write(name, data):
        path = output / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        files[name] = hashlib.sha256(data).hexdigest()

    for row in json.loads(args.inventory.read_text()):
        group, name, version = (row[field] for field in ("group", "name", "version"))
        for value in (group, name, version):
            if not re.fullmatch(r"[A-Za-z0-9_.-]+", value):
                raise ValueError("unsafe dependency coordinate")
        licenses = declared_licenses(args.gradle_cache, group, name, version)
        if any(not item["name"] or not item["url"] for item in licenses):
            raise ValueError(f"incomplete license: {group}:{name}:{version}")
        artifact = Path(row["file"]).read_bytes()
        names = []
        for index, (original_name, data) in enumerate(archive_notices(artifact)):
            relative = f"maven/{group}/{name}/{version}/{index:02d}-{Path(original_name).name}"
            write(relative, data)
            names.append({"original": original_name, "bundled": relative})
        relative = f"{group.replace('.', '/')}/{name}/{version}/{name}-{version}-sources.jar"
        repository = "https://dl.google.com/dl/android/maven2/" if group.startswith("androidx.") else "https://repo.maven.apache.org/maven2/"
        records.append({"coordinate": f"{group}:{name}:{version}", "licenses": licenses,
                        "source": repository + relative, "artifact_sha256": hashlib.sha256(artifact).hexdigest(),
                        "notice_files": names})

    litert = "com.google.ai.edge.litertlm/litertlm-android/0.17.1"
    entries = [name for name in files if litert in name]
    if not any(name.endswith("THIRD_PARTY_NOTICE.txt") for name in entries):
        raise ValueError("LiteRT-LM's complete native notice is missing")
    apache = next(name for name in entries if name.endswith("-LICENSE"))
    write("APACHE-2.0.txt", (output / apache).read_bytes())
    write("INKU-LICENSE.txt", (ROOT / "LICENSE").read_bytes())
    for name in ("LICENSE-MIT", "LICENSE-APACHE", "INKU_PATCHES.md"):
        write(f"resvg/{name}", (ROOT / "core/vendor/resvg" / name).read_bytes())
    rust_output = output / "RUST_THIRD_PARTY_NOTICES.txt"
    subprocess.run([sys.executable, str(ROOT / "server/scripts/build_rust_notices.py"),
                    str(ROOT / "core/Cargo.lock"), str(rust_output)], check=True)
    files[rust_output.name] = hashlib.sha256(rust_output.read_bytes()).hexdigest()
    write("README.txt", (
        "inku Android release third-party notices.\n"
        "The Maven inventory identifies the exact release runtime artifacts, their\n"
        "declared licenses and source archives. Embedded LICENSE and NOTICE files,\n"
        "including LiteRT-LM's complete native THIRD_PARTY_NOTICE, are retained.\n"
        "The Rust inventory conservatively includes Cargo.lock registry sources.\n"
        "UniFFI 0.32.0 is MPL-2.0; terms: https://www.mozilla.org/en-US/MPL/2.0/\n"
        "Exact sources: https://crates.io/api/v1/crates/<name>/<version>/download\n"
        "cesu8 1.1.0, jni-sys-macros 0.4.1 and r-efi 6.0.0 have no standalone\n"
        "license file in their archive; their declared MIT option is selected.\n"
        "The resvg patch and its licenses are included; modified source is in\n"
        f"https://github.com/oikawas/inku-lang/tree/android-v{(ROOT / 'android/VERSION').read_text().strip()}/core/vendor/resvg\n"
        "Model weights are not included. Downloaded Gemma models have their own\n"
        "license acceptance, independent of the Apache-2.0 LiteRT-LM runtime.\n"
    ).encode())
    write("maven-inventory.json", (json.dumps(records, indent=2, ensure_ascii=False) + "\n").encode())
    (output / "SHA256SUMS").write_text("".join(f"{digest}  {name}\n" for name, digest in sorted(files.items())))
    print(f"Android notices: {len(records)} runtime artifacts, {len(files)} notice files")


if __name__ == "__main__":
    main()
