"""The Android saijiki snapshot must not fall behind `saijiki.py`.

This is the gate the hand-copied list never had. On 2026-07-26 the Android
`saijikiGroups` was synced to the ten touch words of that day; on 2026-07-27 the
server returned the silverpoint to the vocabulary (a2d1d100) and nothing on the
client noticed, so the app displayed ten words against the server's eleven for
two weeks. Byte identity with a freshly rendered file is what closes that.

Note what this test does NOT establish: that the app reads the generated file.
A screen still wired to a hand-written list passes here. That property lives in
the Kotlin suite (SaijikiIsGeneratedTest), because it is a fact about the screen.
"""

from __future__ import annotations

import importlib.util
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]

# `android/` is permanently excluded from every pentala sync path (standing rule
# 2026-07-30), so on the deployed server the tree is absent. Key the skip to the
# DIRECTORY, so that a moved or renamed output is a failure rather than a skip.
ANDROID_TREE = ROOT / "android"
GENERATOR = ROOT / "server/scripts/gen_saijiki_kt.py"

android_only = pytest.mark.skipif(
    not ANDROID_TREE.is_dir(), reason="android/ is absent (pentala)"
)


def _load_generator():
    spec = importlib.util.spec_from_file_location("gen_saijiki_kt", GENERATOR)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@android_only
def test_generated_kotlin_matches_the_table() -> None:
    module = _load_generator()
    checked_in = module._OUTPUT
    assert checked_in.is_file(), f"snapshot missing: {checked_in}"
    assert checked_in.read_text(encoding="utf-8") == module.render_kt(), (
        "android saijiki snapshot is stale"
        " -- rebake with: cd server && uv run python scripts/gen_saijiki_kt.py"
    )


@android_only
def test_snapshot_carries_both_language_surfaces_for_every_category() -> None:
    """Calibration: a generator that emitted one language would still be current.

    The identity check above compares the file to the generator, so a generator
    that dropped English would agree with its own output. This reads the shipped
    file against the table instead.
    """
    import sys

    src = str(ROOT / "server" / "src")
    if src not in sys.path:
        sys.path.insert(0, src)
    from inku_server.saijiki import display_categories

    module = _load_generator()
    text = module._OUTPUT.read_text(encoding="utf-8")

    ja = display_categories("ja")
    en = display_categories("en")
    assert len(ja) == 10, f"expected ten display categories, table has {len(ja)}"

    for cat_ja, cat_en in zip(ja, en):
        assert f'key = "{cat_ja["key"]}"' in text, f"category missing: {cat_ja['key']}"
        for word in cat_ja["words"]:
            assert f'"{word}"' in text, f"ja word missing: {word}"
        for word in cat_en["words"]:
            assert f'"{word}"' in text, f"en word missing: {word}"
