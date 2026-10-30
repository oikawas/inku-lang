"""Build the nine example words as inku.macro-definition.v2 and check or write them.

    python3 build_v2.py            # compare with the package and export files (default)
    python3 build_v2.py --write    # write the definitions into those files
    python3 build_v2.py --dump out.json

Run it from this folder. --write replaces only each word's definition in
../water-nihonga/package.json, ../sky-nihonga/package.json and the
../*.ddl.json export files that carry the word; notes, examples, pictures
and the order of the keys are kept. Rebuild the zips afterwards (README).
"""
import json
import sys
from pathlib import Path

from water_stream_ripples_rings import WORDS as WATER_LINES
from river_sea_sky import WORDS as RIVER_SEA_SKY

HERE = Path(__file__).resolve().parent
PLUGINS = HERE.parent

# id -> (namespace, Japanese names, English names); the first name is the primary one.
NAMES = {
    "Stream": ("Water", ["水流"], ["stream"]),
    "Ripples": ("Water", ["波紋"], ["ripples"]),
    "Rings": ("Water", ["水輪"], ["rings"]),
    "River": ("Water", ["川"], ["river"]),
    "Sea": ("Water", ["海"], ["sea"]),
    "Clouds": ("Sky", ["雲"], ["clouds"]),
    # 空 is a core word (an empty surface), so the sky is called 大空.
    "Heavens": ("Sky", ["大空"], ["heavens"]),
    "Rain": ("Sky", ["雨"], ["rain"]),
    "Snow": ("Sky", ["雪"], ["snow"]),
}
PACKAGES = {"Water": PLUGINS / "water-nihonga" / "package.json", "Sky": PLUGINS / "sky-nihonga" / "package.json"}


def to_v2(word_id, internal):
    """Every example word is a scene: it draws its own place on the canvas and keeps its count parameter."""
    namespace, ja, en = NAMES[word_id]
    return {
        "schema": "inku.macro-definition.v2",
        "namespace": namespace,
        "id": word_id,
        "names": {"ja": ja, "en": en},
        "kind": "scene",
        "version": internal["version"],
        "parameters": internal["parameters"],
        "components": internal["components"],
        "body": internal["body"],
    }


def build():
    words = {**WATER_LINES, **RIVER_SEA_SKY}
    assert set(words) == set(NAMES), sorted(set(words) ^ set(NAMES))
    return {word_id: to_v2(word_id, internal) for word_id, internal in words.items()}


def _replace_keeping_order(old, new):
    merged = {key: new[key] for key in old if key in new}
    merged.update({key: value for key, value in new.items() if key not in merged})
    return merged


def _targets():
    """(path, list of entries holding a definition) for every file that carries the words."""
    for path in PACKAGES.values():
        yield path, lambda doc: doc["words"]
    for path in sorted(PLUGINS.glob("*.ddl.json")):
        yield path, lambda doc: doc["plugins"]


def check_or_write(built, write):
    differences = 0
    for path, entries_of in _targets():
        doc = json.loads(path.read_text(encoding="utf-8"))
        changed = False
        for entry in entries_of(doc):
            word_id = entry["definition"]["id"]
            if entry["definition"] == built[word_id]:
                continue
            differences += 1
            print(f"{'writes' if write else 'differs'}: {path.relative_to(PLUGINS)} {word_id}")
            if write:
                entry["definition"] = _replace_keeping_order(entry["definition"], built[word_id])
                changed = True
        if changed:
            path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return differences


def main(argv):
    built = build()
    if argv[1:2] == ["--dump"]:
        Path(argv[2]).write_text(json.dumps(built, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return 0
    write = argv[1:2] == ["--write"]
    differences = check_or_write(built, write)
    if not write:
        print("all definitions match" if differences == 0 else f"{differences} definition(s) differ")
    return 1 if differences and not write else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
