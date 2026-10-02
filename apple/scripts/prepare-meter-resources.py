"""Copy and verify pinned dictionaries at build time; the client never uses Python."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = Path(__file__).with_name("description-meter-resources.json")
OUTPUT = ROOT / "apple/Packages/InkuHost/Sources/InkuHost/Resources/description-meter"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site-packages", type=Path, help="Pinned Server environment's site-packages directory")
    args = parser.parse_args()
    candidates = sorted((ROOT / "server/.venv/lib").glob("python*/site-packages"))
    site = args.site_packages or (candidates[0] if len(candidates) == 1 else None)
    if site is None:
        parser.error("prepare the locked Server dependencies or pass --site-packages")
    pins = json.loads(MANIFEST.read_text())
    sources = {name: site / "sudachipy/resources" / name for name in ("sudachi.json", "char.def", "rewrite.def", "unk.def")}
    sources["system.dic"] = site / "sudachidict_small/resources/system.dic"
    sources["cmudict.dict"] = ROOT / "server/src/inku_server/cmudict/cmudict.dict"
    for name, path in sources.items():
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != pins["sha256"][name]:
            raise SystemExit(f"Pinned meter resource unavailable or changed: {name}; use Server uv.lock dependencies")
    licenses = {
        "Sudachi-LICENSE.txt": site / "sudachipy-0.7.0.dist-info/licenses/LICENSE",
        "SudachiDict-LICENSE.txt": site / "sudachidict_small-20260723.1.dist-info/licenses/LICENSE-2.0.txt",
        "CMUdict-LICENSE.txt": ROOT / "server/src/inku_server/cmudict/LICENSE",
    }
    if not all(path.is_file() for path in licenses.values()):
        raise SystemExit("Pinned meter license files unavailable")
    OUTPUT.mkdir(parents=True, exist_ok=True)
    for name, path in {**sources, **licenses}.items():
        shutil.copyfile(path, OUTPUT / name)
    shutil.copyfile(MANIFEST, OUTPUT / "manifest.json")
    print(f"Prepared pinned Japanese/English native meter resources: {OUTPUT}")


if __name__ == "__main__":
    main()
