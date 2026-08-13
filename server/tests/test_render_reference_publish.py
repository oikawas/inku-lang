from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


SERVER_ROOT = Path(__file__).parents[1]
GENERATOR_PATH = SERVER_ROOT / "scripts" / "gen_render_reference.py"


def _load_generator():
    spec = importlib.util.spec_from_file_location("gen_render_reference_publish", GENERATOR_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_failed_staging_does_not_touch_the_frozen_corpus(tmp_path: Path, monkeypatch) -> None:
    generator = _load_generator()
    output = tmp_path / "render-engine-32"
    output.mkdir()
    (output / "manifest.json").write_text('{"state":"frozen"}\n')
    (output / "old.svg").write_text("<svg>frozen</svg>")
    before = {path.name: path.read_bytes() for path in output.iterdir()}

    def stop_mid_write(staging: Path, *_args) -> None:
        staging.mkdir()
        (staging / "partial.svg").write_text("partial")
        raise RuntimeError("interrupted")

    monkeypatch.setattr(generator, "_write_output_directory", stop_mid_write)
    with pytest.raises(RuntimeError, match="interrupted"):
        generator._publish_output_directory({}, {}, [], output_dir=output)

    assert {path.name: path.read_bytes() for path in output.iterdir()} == before
    assert list(tmp_path.glob(".render-engine-32.*")) == []


def test_complete_staging_replaces_the_directory_as_one_corpus(tmp_path: Path) -> None:
    generator = _load_generator()
    output = tmp_path / "render-engine-32"
    output.mkdir()
    (output / "stale.svg").write_text("stale")
    manifest = {"state": "new"}

    generator._publish_output_directory(
        manifest,
        {"moved": "<svg>new</svg>"},
        ["moved"],
        output_dir=output,
    )

    assert sorted(path.name for path in output.iterdir()) == ["manifest.json", "moved.svg"]
    assert json.loads((output / "manifest.json").read_text()) == manifest
    assert (output / "moved.svg").read_text() == "<svg>new</svg>"
    assert list(tmp_path.glob(".render-engine-32.*")) == []
