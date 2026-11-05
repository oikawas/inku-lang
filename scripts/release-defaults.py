#!/usr/bin/env python3
"""Show, check and confirm the drawing defaults a release ships to new users.

The first drawing options of a user who has saved none (per input tab: route,
sketch, composition and laws, stroke limit, color catalog, canvas and model)
live in one file, ``core/crates/inku-pipeline/data/release-defaults.json``.
The shared core reads it, so the Server, the Web and the apps that use the
core all start from it.

The release procedure shows the file to the author before the version is
finalized, and refuses to publish a version the file was not reviewed for:

    scripts/release-defaults.py show                     # the table to show the author
    scripts/release-defaults.py check --version v2.15.320
    scripts/release-defaults.py confirm --version v2.15.320

``confirm`` changes only ``reviewed_for_version``. To change a value, edit the
file, run ``confirm`` and record the change in both CHANGELOGs as an ordinary
product change. The core's own tests check that the file survives its
normalization (``draw_options::tests``).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "core" / "crates" / "inku-pipeline" / "data"
RELEASE = DATA / "release-defaults.json"
SCHEMA = "inku.release-draw-defaults.v1"
TABS = ("describe", "image", "batch_text", "batch_image")
KEYS = ("route", "sketch", "composition", "wild", "catalog", "canvas_aspect", "models")
IMAGE_TABS = ("image", "batch_image")
VERSION = re.compile(r"^v\d+\.\d+\.\d+$")

TAB_NAMES = {"describe": "記述 / Describe", "image": "画像 / Picture",
             "batch_text": "バッチ（記述）/ Batch: descriptions", "batch_image": "バッチ（画像フォルダ）/ Batch: pictures"}
KEY_NAMES = {"route": "描き方 / Drawing", "sketch": "写生 / Sketch", "composition": "構図・法則・配色 / Composition",
             "wild": "筆致制限を外す / Lift the stroke limit", "catalog": "色カタログ / Color catalog",
             "canvas_aspect": "キャンバス / Canvas", "models": "モデル / Model"}
WORDS = {"read_and_draw": "言葉で描く / In words", "stages": "型で描く / With a plan",
         "on": "オン / On", "off": "オフ / Off", "image": "画像の縦横比 / The picture's ratio"}


def load() -> dict:
    return json.loads(RELEASE.read_text(encoding="utf-8"))


def model_labels() -> dict[str, str]:
    catalog = json.loads((DATA / "model_catalog.json").read_text(encoding="utf-8"))
    labels = {}
    for provider, row in catalog.get("providers", {}).items():
        for model in row.get("models", []):
            if isinstance(model, dict) and model.get("id"):
                labels[f"{provider}:{model['id']}"] = model.get("label") or model["id"]
    return labels


def known_providers() -> set[str]:
    catalog = json.loads((DATA / "model_catalog.json").read_text(encoding="utf-8"))
    definitions = json.loads((DATA / "provider-definitions.json").read_text(encoding="utf-8"))
    return set(catalog.get("providers", {})) | {row["id"] for row in definitions if isinstance(row, dict) and row.get("id")}


def problems(release: dict) -> list[str]:
    """What makes the file unusable, in words a release can act on."""
    found = []
    if release.get("schema") != SCHEMA:
        found.append(f"schema is {release.get('schema')!r}, not {SCHEMA!r}")
    tabs = release.get("tabs")
    if not isinstance(tabs, dict) or sorted(tabs) != sorted(TABS):
        return found + [f"tabs must be exactly {', '.join(TABS)}"]
    providers = known_providers()
    for tab in TABS:
        options = tabs[tab]
        if not isinstance(options, dict) or sorted(options) != sorted(KEYS):
            found.append(f"{tab}: options must be exactly {', '.join(KEYS)}")
            continue
        if options["route"] not in ("read_and_draw", "stages"):
            found.append(f"{tab}.route: {options['route']!r}")
        for key in ("sketch", "composition", "wild"):
            if options[key] not in ("on", "off"):
                found.append(f"{tab}.{key}: {options[key]!r}")
        catalog = options["catalog"]
        if not isinstance(catalog, dict) or catalog.get("mode") not in ("fixed", "auto") or not str(catalog.get("id") or "").strip():
            found.append(f"{tab}.catalog: {catalog!r}")
        if not str(options["canvas_aspect"] or "").strip():
            found.append(f"{tab}.canvas_aspect is empty")
        models = options["models"]
        wanted = ("vision",) if tab in IMAGE_TABS else ("stage1", "stage2")
        if not isinstance(models, dict) or sorted(models) != sorted(wanted):
            found.append(f"{tab}.models must name {', '.join(wanted)}")
            continue
        for stage in wanted:
            provider, _, model = str(models[stage]).partition(":")
            if not model or provider not in providers:
                found.append(f"{tab}.models.{stage}: {models[stage]!r} is not provider:model with a known provider")
    return found


def show(release: dict) -> str:
    labels = model_labels()
    lines = [f"# Release drawing defaults ({RELEASE.relative_to(ROOT)})",
             f"reviewed_for_version: {release.get('reviewed_for_version') or '(not reviewed yet)'}", ""]
    for tab in TABS:
        options = release["tabs"][tab]
        lines.append(f"## {TAB_NAMES[tab]}")
        for key in KEYS:
            if tab in IMAGE_TABS and key in ("route", "sketch", "composition", "wild"):
                continue  # a picture neither sends nor shows these
            value = options[key]
            if key == "catalog":
                text = "記述から自動選択 / From the description" if value["mode"] == "auto" else f"{value['id']}（固定 / fixed）"
            elif key == "models":
                text = " / ".join(dict.fromkeys(f"{labels.get(ref, ref)} ({ref})" for ref in value.values()))
            else:
                text = WORDS.get(value, value)
            lines.append(f"- {KEY_NAMES[key]}: {text}")
        lines.append("")
    return "\n".join(lines)


def current_version() -> str:
    return (ROOT / "web" / "APP_VERSION").read_text(encoding="utf-8").strip()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("show", help="print the defaults as the author reads them")
    for name in ("check", "confirm"):
        command = sub.add_parser(name)
        command.add_argument("--version", help="vX.Y.Z; defaults to web/APP_VERSION")
    args = parser.parse_args(argv)
    release = load()
    found = problems(release)
    if args.command == "show":
        print(show(release) if not found else "\n".join(found))
        return 1 if found else 0
    version = args.version or current_version()
    if not VERSION.match(version):
        print(f"version {version!r} is not vX.Y.Z", file=sys.stderr)
        return 2
    if found:
        print("release defaults are not usable:\n- " + "\n- ".join(found), file=sys.stderr)
        return 1
    if args.command == "check":
        reviewed = release.get("reviewed_for_version") or ""
        if reviewed != version:
            print(f"release defaults were reviewed for {reviewed or 'no version'}, not {version}. "
                  f"Show `scripts/release-defaults.py show` to the author, then run "
                  f"`scripts/release-defaults.py confirm --version {version}`.", file=sys.stderr)
            return 1
        print(f"release defaults reviewed for {version}")
        return 0
    text = RELEASE.read_text(encoding="utf-8")
    updated, count = re.subn(r'("reviewed_for_version":\s*)"[^"]*"', lambda m: f'{m.group(1)}"{version}"', text, count=1)
    if count != 1:
        print("reviewed_for_version not found", file=sys.stderr)
        return 1
    RELEASE.write_text(updated, encoding="utf-8")
    print(f"release defaults confirmed for {version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
