"""Run the bounded Engine 41 shadow-candidate acceptance evidence.

This tool is intentionally developer-only. It reuses the frozen reference
inputs, writes only to an explicit temporary destination, and never changes the
runtime engine registry.
"""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import importlib.util
import io
import json
import math
from pathlib import Path
import re
import statistics
import time
from typing import Any, Iterable
import xml.etree.ElementTree as ET

from PIL import Image, ImageDraw, ImageOps

from inku_analysis import rasterizer
from inku_analysis.rasterizer import svg_to_png
from inku_analysis.texture_fold import fold_texture_runs
from inku_server.render_engines import (
    DEFAULT_RENDER_ENGINE,
    RUST_CANDIDATE_RENDER_ENGINE,
    RenderEngine,
)
from inku_server.schema import CLOSED_SHAPES, CanvasSpec, Score
from inku_server.svg_compat import validate_compat_svg


SCRIPT_DIR = Path(__file__).resolve().parent
REFERENCE_GENERATOR_PATH = SCRIPT_DIR / "gen_render_reference.py"
DRAWING_TAGS = {"path", "polyline", "polygon", "circle", "ellipse", "line", "rect"}
SKIPPED_TREES = {"defs", "title", "desc", "metadata"}
NUMBER_RE = re.compile(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?")
NON_FINITE_RE = re.compile(r"(?<![A-Za-z])(?:nan|[-+]?inf(?:inity)?)(?![A-Za-z])", re.I)
URL_REF_RE = re.compile(r"url\(#([^\)]+)\)")
GEOMETRY_ATTRIBUTES = {
    "d", "points", "x", "y", "x1", "y1", "x2", "y2", "cx", "cy", "r",
    "rx", "ry", "width", "height", "transform",
}
STYLE_ATTRIBUTES = {
    "fill", "fill-opacity", "stroke", "stroke-width", "stroke-opacity",
    "stroke-dasharray", "opacity", "filter", "clip-path", "mask",
}
NUMERIC_STYLE_ATTRIBUTES = {
    "fill-opacity",
    "stroke-width",
    "stroke-opacity",
    "stroke-dasharray",
    "opacity",
}

REPRESENTATIVE_CASES = (
    "A-pen-line",
    "A-brush_thick-cloudform",
    "B-perlin-broad-arc-pencil",
    "C-fill-circle-crayon",
    "C-display-surface-wash-pen",
    "C-filter-display-pencil",
    "C-ground-washi",
    "D-canvas-pillar-radial",
    "E-wild-surface-hatch-pencil",
    "F-catalog-cool_material-purple",
    "G-path-wave-edge",
    "H-pair-radial-unit",
)
PERFORMANCE_CASES = (
    "A-pen-line",
    "C-filter-display-pencil",
    "G-path-wave-edge",
)
PLATFORM_CASES = (
    "A-pen-arc",
    "B-perlin-broad-arc-pencil",
    "C-surface-grain-pencil",
    "D-canvas-pillar-path-wave",
    "G-cluster-edge",
)


class CandidateValidationError(RuntimeError):
    """One or more candidate automatic gates failed."""


def _reference_generator():
    spec = importlib.util.spec_from_file_location(
        "gen_render_reference_stage4", REFERENCE_GENERATOR_PATH
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load the render reference generator")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _local_name(name: str) -> str:
    return name.rsplit("}", 1)[-1]


def _normalized_numbers(value: str) -> str:
    def replace(match: re.Match[str]) -> str:
        number = float(match.group(0))
        if not math.isfinite(number):
            raise CandidateValidationError("non-finite SVG number")
        text = f"{number:.6f}".rstrip("0").rstrip(".")
        return "0" if text in {"", "-0"} else text

    return NUMBER_RE.sub(replace, value)


def _visible_elements(root: ET.Element) -> Iterable[ET.Element]:
    def walk(element: ET.Element, hidden: bool = False) -> Iterable[ET.Element]:
        name = _local_name(element.tag)
        hidden = hidden or name in SKIPPED_TREES
        if not hidden:
            yield element
        for child in element:
            yield from walk(child, hidden)

    return walk(root)


def _parse_svg(svg: str) -> ET.Element:
    if NON_FINITE_RE.search(svg):
        raise CandidateValidationError("SVG contains NaN or Inf")
    try:
        root = ET.fromstring(svg)
    except ET.ParseError as error:
        raise CandidateValidationError(f"malformed SVG: {error}") from error
    if _local_name(root.tag) != "svg":
        raise CandidateValidationError("document root is not SVG")
    return root


def _internal_reference_errors(root: ET.Element) -> list[str]:
    ids = {value for element in root.iter() if (value := element.get("id"))}
    references: set[str] = set()
    for element in root.iter():
        for name, value in element.attrib.items():
            references.update(URL_REF_RE.findall(value))
            if _local_name(name) == "href" and value.startswith("#"):
                references.add(value[1:])
    return sorted(references - ids)


def _metadata_meaning(metadata: dict[str, object]) -> dict[str, object]:
    ground = metadata.get("render_canvas_ground")
    if isinstance(ground, dict):
        ground = {key: value for key, value in ground.items() if value is not None}
    surfaces = metadata.get("render_surface_textures") or []
    return {
        "render_engine_id": metadata.get("render_engine_id"),
        "render_texture_version": metadata.get("render_texture_version"),
        "render_texture_profile": metadata.get("render_texture_profile"),
        "texture_degraded": metadata.get("texture_degraded"),
        "render_canvas_ground": ground or None,
        "render_surface_textures": surfaces,
    }


def _visual_signature(root: ET.Element) -> dict[str, object]:
    visible = list(_visible_elements(root))
    families: Counter[str] = Counter()
    drawing: list[tuple[str, tuple[tuple[str, str], ...]]] = []
    for element in visible:
        name = _local_name(element.tag)
        if name not in DRAWING_TAGS:
            continue
        families[name] += 1
        attributes = tuple(
            sorted(
                (
                    key,
                    _normalized_numbers(value)
                    if _local_name(key) in GEOMETRY_ATTRIBUTES | NUMERIC_STYLE_ATTRIBUTES
                    else value,
                )
                for key, value in element.attrib.items()
                if _local_name(key) in GEOMETRY_ATTRIBUTES | STYLE_ATTRIBUTES
            )
        )
        drawing.append((name, attributes))
    encoded = json.dumps(drawing, sort_keys=True, separators=(",", ":")).encode()
    return {
        "view_box": _normalized_numbers(root.get("viewBox", "")),
        "width": _normalized_numbers(root.get("width", "")),
        "height": _normalized_numbers(root.get("height", "")),
        "drawing_families": dict(sorted(families.items())),
        "drawing_digest": hashlib.sha256(encoded).hexdigest(),
    }


def _structure_signature(root: ET.Element) -> dict[str, object]:
    ids = [element.get("id") for element in root.iter() if element.get("id")]
    filter_refs = sum(
        len(URL_REF_RE.findall(value))
        for element in root.iter()
        for value in element.attrib.values()
    )
    tags = Counter(_local_name(element.tag) for element in root.iter())
    return {
        "root_children": [
            [_local_name(child.tag), child.get("id")] for child in list(root)
        ],
        "instruction_groups": sum(value.startswith("instruction_") for value in ids),
        "mark_groups": sum(value.startswith("mark_") for value in ids),
        "filters": tags["filter"],
        "patterns": tags["pattern"],
        "filter_references": filter_refs,
        "layer_order": [
            layer
            for layer in (
                "layer_00_background",
                "layer_01_canvas_ground",
                "layer_10_content",
                "layer_15_plate_tone",
                "layer_20_presence",
            )
            if layer in ids
        ],
    }


def _signature(svg: str) -> tuple[dict[str, object], dict[str, object]]:
    root = _parse_svg(svg)
    return _visual_signature(root), _structure_signature(root)


def _expected_surface_textures(score: Score) -> list[str]:
    return [
        instruction.surface.texture
        for instruction in score.instructions
        if instruction.surface is not None
        and instruction.surface.texture not in ("none", "solid")
        and instruction.primitive in CLOSED_SHAPES
    ]


def _validate_candidate(
    case_id: str,
    render_input: dict[str, Any],
    svg: str,
    metadata: dict[str, object],
    python_metadata: dict[str, object],
) -> None:
    root = _parse_svg(svg)
    missing_references = _internal_reference_errors(root)
    if missing_references:
        raise CandidateValidationError(
            f"{case_id}: missing internal references {missing_references[:5]}"
        )
    profile = render_input["svg_profile"]
    if metadata.get("render_texture_profile") != profile:
        raise CandidateValidationError(f"{case_id}: metadata profile mismatch")
    ids = {element.get("id") for element in root.iter() if element.get("id")}
    if profile in {"editable", "compat"} and not {
        "inku_artboard",
        "inku_metadata",
    } <= ids:
        raise CandidateValidationError(f"{case_id}: structured profile markers are missing")
    if profile == "compat":
        validate_compat_svg(svg)
    if _metadata_meaning(metadata) != _metadata_meaning(python_metadata):
        raise CandidateValidationError(f"{case_id}: render metadata meaning differs")

    score = Score.model_validate(render_input["score"])
    content = next(
        (element for element in root.iter() if element.get("id") == "layer_10_content"),
        None,
    )
    content_shapes = [] if content is None else [
        element
        for element in _visible_elements(content)
        if _local_name(element.tag) in DRAWING_TAGS
    ]
    if score.instructions and not content_shapes:
        raise CandidateValidationError(f"{case_id}: requested primitive content disappeared")

    ground = score.canvas.ground if isinstance(score.canvas, CanvasSpec) else None
    if ground is not None and ground.material != "plain":
        if "layer_01_canvas_ground" not in ids:
            raise CandidateValidationError(f"{case_id}: requested ground disappeared")
        if not any(_local_name(element.tag) == "pattern" for element in root.iter()):
            raise CandidateValidationError(f"{case_id}: requested ground pattern disappeared")

    for texture in _expected_surface_textures(score):
        if texture not in svg:
            raise CandidateValidationError(
                f"{case_id}: requested surface {texture!r} disappeared"
            )


def _changed_keys(left: dict[str, object], right: dict[str, object]) -> list[str]:
    return sorted(key for key in set(left) | set(right) if left.get(key) != right.get(key))


def _timings(engine: RenderEngine, render_input: dict[str, Any], repeats: int = 5) -> list[float]:
    score = Score.model_validate(render_input["score"])
    options = {
        "color_map": render_input["color_map"],
        "catalog_id": render_input["catalog_id"],
        "render_seed": render_input["render_seed"],
        "composition_seed": render_input.get("composition_seed"),
        "svg_profile": render_input["svg_profile"],
        "wild": render_input["wild"],
    }
    engine.render(score, **options)
    values = []
    for _ in range(repeats):
        started = time.perf_counter()
        engine.render(score, **options)
        values.append((time.perf_counter() - started) * 1000.0)
    return values


def _raster_timings(svg: str, width: int = 256, repeats: int = 3) -> dict[str, object]:
    render = rasterizer._resvg_renderer()
    if render is None:
        raise CandidateValidationError("resvg is unavailable")
    folded = fold_texture_runs(svg)

    def measure(payload: str) -> list[float]:
        values = []
        for _ in range(repeats):
            started = time.perf_counter()
            render(payload, width, None, None, False)
            values.append((time.perf_counter() - started) * 1000.0)
        return values

    raw = measure(svg)
    compact = measure(folded)
    return {
        "fold_changed": folded != svg,
        "raw_median_ms": round(statistics.median(raw), 3),
        "folded_median_ms": round(statistics.median(compact), 3),
    }


def _contact_sheet(
    output_dir: Path,
    pairs: dict[str, tuple[str, str]],
) -> None:
    tile_width = 300
    tile_height = 300
    label_height = 28
    gap = 8
    rows: list[tuple[str, Image.Image, Image.Image]] = []
    for case_id, (python_svg, rust_svg) in pairs.items():
        python_png = svg_to_png(python_svg, width=tile_width)
        rust_png = svg_to_png(rust_svg, width=tile_width)
        python_image = Image.open(io.BytesIO(python_png)).convert("RGB")
        rust_image = Image.open(io.BytesIO(rust_png)).convert("RGB")
        rows.append((case_id, python_image, rust_image))

    row_height = tile_height + label_height
    sheet = Image.new(
        "RGB",
        (tile_width * 2 + gap * 3, row_height * len(rows) + label_height),
        "white",
    )
    draw = ImageDraw.Draw(sheet)
    draw.text((gap, 6), "Python 40", fill="black")
    draw.text((tile_width + gap * 2, 6), "Rust 41 candidate", fill="black")
    for row, (case_id, left, right) in enumerate(rows):
        y = label_height + row * row_height
        draw.text((gap, y + 4), case_id, fill="black")
        left_fit = ImageOps.contain(left, (tile_width, tile_height))
        right_fit = ImageOps.contain(right, (tile_width, tile_height))
        left_x = gap + (tile_width - left_fit.width) // 2
        right_x = tile_width + gap * 2 + (tile_width - right_fit.width) // 2
        sheet.paste(left_fit, (left_x, y + label_height))
        sheet.paste(right_fit, (right_x, y + label_height))
    sheet.save(output_dir / "contact-sheet.png")


def _platform_sample(
    output: Path,
    inputs: dict[str, dict[str, Any]],
    engine: RenderEngine,
    source_commit: str,
) -> None:
    cases = {}
    for case_id in PLATFORM_CASES:
        render_input = inputs[case_id]
        score = Score.model_validate(render_input["score"])
        result = engine.render(
            score,
            color_map=render_input["color_map"],
            catalog_id=render_input["catalog_id"],
            render_seed=render_input["render_seed"],
            composition_seed=render_input.get("composition_seed"),
            svg_profile=render_input["svg_profile"],
            wild=render_input["wild"],
        )
        cases[case_id] = {
            "svg_sha256": hashlib.sha256(result.svg.encode()).hexdigest(),
            "metadata": result.metadata,
        }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(
            {
                "source_commit": source_commit,
                "engine_id": engine.id,
                "engine_version": engine.version,
                "cases": cases,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def run(output_dir: Path, source_commit: str) -> dict[str, object]:
    reference = _reference_generator()
    inputs = reference.build_inputs()
    output_dir.mkdir(parents=True, exist_ok=False)
    candidate_corpus = output_dir / "candidate-corpus"
    reference.generate(
        engine=RUST_CANDIDATE_RENDER_ENGINE,
        output_dir=candidate_corpus,
    )

    classifications: Counter[str] = Counter()
    differences: list[dict[str, object]] = []
    validation_errors: list[str] = []
    representative_pairs: dict[str, tuple[str, str]] = {}
    candidate_svgs: dict[str, str] = {}
    for case_id, render_input in sorted(inputs.items()):
        score = Score.model_validate(render_input["score"])
        options = {
            "color_map": render_input["color_map"],
            "catalog_id": render_input["catalog_id"],
            "render_seed": render_input["render_seed"],
            "composition_seed": render_input.get("composition_seed"),
            "svg_profile": render_input["svg_profile"],
            "wild": render_input["wild"],
        }
        python_result = DEFAULT_RENDER_ENGINE.render(score, **options)
        rust_result = RUST_CANDIDATE_RENDER_ENGINE.render(score, **options)
        candidate_svgs[case_id] = rust_result.svg
        try:
            _validate_candidate(
                case_id,
                render_input,
                rust_result.svg,
                rust_result.metadata,
                python_result.metadata,
            )
        except (CandidateValidationError, ValueError) as error:
            validation_errors.append(str(error))

        python_visual, python_structure = _signature(python_result.svg)
        rust_visual, rust_structure = _signature(rust_result.svg)
        if python_result.svg == rust_result.svg:
            classification = "byte-identical"
        elif python_visual == rust_visual and python_structure == rust_structure:
            classification = "serializer-only"
        elif python_visual == rust_visual:
            classification = "non-visual-svg-structure"
        else:
            classification = "semantic-visual-review"
        classifications[classification] += 1
        if classification != "byte-identical":
            differences.append(
                {
                    "case_id": case_id,
                    "classification": classification,
                    "visual_keys": _changed_keys(python_visual, rust_visual),
                    "structure_keys": _changed_keys(python_structure, rust_structure),
                }
            )
        if case_id in REPRESENTATIVE_CASES:
            representative_pairs[case_id] = (python_result.svg, rust_result.svg)

    performance = {}
    for case_id in PERFORMANCE_CASES:
        python_values = _timings(DEFAULT_RENDER_ENGINE, inputs[case_id])
        rust_values = _timings(RUST_CANDIDATE_RENDER_ENGINE, inputs[case_id])
        performance[case_id] = {
            "python_median_ms": round(statistics.median(python_values), 3),
            "rust_median_ms": round(statistics.median(rust_values), 3),
        }
    performance["texture_fold"] = _raster_timings(
        candidate_svgs["C-filter-display-pencil"]
    )

    representative_dir = output_dir / "representatives"
    representative_dir.mkdir()
    for case_id, (python_svg, rust_svg) in representative_pairs.items():
        (representative_dir / f"{case_id}-python40.svg").write_text(
            python_svg, encoding="utf-8"
        )
        (representative_dir / f"{case_id}-rust41.svg").write_text(
            rust_svg, encoding="utf-8"
        )
    _contact_sheet(output_dir, representative_pairs)
    _platform_sample(
        output_dir / "platform-sample-linux.json",
        inputs,
        RUST_CANDIDATE_RENDER_ENGINE,
        source_commit,
    )

    result = {
        "source_commit": source_commit,
        "case_count": len(inputs),
        "engine_current": DEFAULT_RENDER_ENGINE.version,
        "engine_candidate": RUST_CANDIDATE_RENDER_ENGINE.version,
        "classifications": dict(sorted(classifications.items())),
        "validation_error_count": len(validation_errors),
        "validation_errors": validation_errors[:50],
        "representative_cases": list(REPRESENTATIVE_CASES),
        "performance": performance,
        "rasterizer": rasterizer.rasterizer_info(),
    }
    (output_dir / "result.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (output_dir / "differences.json").write_text(
        json.dumps(differences, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    if validation_errors:
        raise CandidateValidationError(
            f"{len(validation_errors)} candidate automatic validation errors"
        )
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--platform-sample", action="store_true")
    args = parser.parse_args()
    if args.platform_sample:
        reference = _reference_generator()
        _platform_sample(
            args.output,
            reference.build_inputs(),
            RUST_CANDIDATE_RENDER_ENGINE,
            args.source_commit,
        )
        print(f"platform sample: {len(PLATFORM_CASES)} cases")
        return
    result = run(args.output, args.source_commit)
    print(f"candidate cases: {result['case_count']}")
    print(f"classifications: {json.dumps(result['classifications'], sort_keys=True)}")
    print(f"validation errors: {result['validation_error_count']}")
    print(f"artifacts: {args.output}")


if __name__ == "__main__":
    main()
