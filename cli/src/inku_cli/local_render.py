"""Offline saved-Score rendering through a chosen product checkout's Rust core."""

from __future__ import annotations

import argparse
import ast
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET


class LocalRenderError(Exception):
    """An actionable local input, build, or core-rendering failure."""


_LIMIT_DIMENSIONS = {
    "max_expanded_primitives": "primitive_marks",
    "max_expanded_per_instruction": "maximum_per_template_primitive_marks",
    "max_instructions": "object_templates",
    "schema_count_max": "maximum_resolved_count",
}
_CLIP = {
    "tolerance_pixels": 0.1,
    "max_nodes": "50000",
    "max_path_elements": "200000",
    "max_flattened_points": "200000",
    "max_work": "10000000",
    "max_output_vertices": "200000",
}


def _json_file(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError) as exc:
        raise LocalRenderError(f"Cannot read JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise LocalRenderError(f"JSON must be an object: {path}")
    return value


def _run(command: list[str], **kwargs) -> subprocess.CompletedProcess:
    try:
        result = subprocess.run(command, text=True, **kwargs)
    except OSError as exc:
        raise LocalRenderError(f"Cannot execute {command[0]}: {exc}") from exc
    if result.returncode:
        detail = (result.stderr or "").strip()
        raise LocalRenderError(
            f"{Path(command[0]).name} failed (exit {result.returncode})"
            + (f": {detail}" if detail else "; see build output on stderr")
        )
    return result


def _core_root(explicit: str | None) -> Path:
    if explicit:
        root = Path(explicit).expanduser().resolve()
    else:
        root = next((p for p in Path(__file__).resolve().parents
                     if (p / "core/Cargo.toml").is_file()
                     and (p / "scripts/rust-toolchain.sh").is_file()), None)
        if root is None:
            raise LocalRenderError("Cannot locate the CLI's product checkout; pass --core-root")
    for relative in ("core/Cargo.toml", "core/Cargo.lock", "core/rust-toolchain.toml",
                     "scripts/rust-toolchain.sh"):
        if not (root / relative).is_file():
            raise LocalRenderError(f"Selected product checkout is missing {relative}: {root}")
    return root


def _build(root: Path, binary: Path) -> dict:
    """Always ask Cargo to check freshness; never trust a cached driver binary."""
    env = dict(os.environ, CARGO_NET_OFFLINE="true")
    command = [str(root / "scripts/rust-toolchain.sh"), "build", "--release",
               "--locked", "--offline", "--lib", "-p", "inku-pipeline-uniffi",
               "--target-dir", str(root / "core/target"), "--message-format=json"]
    print(f"Checking/building local core: {root}", file=sys.stderr, flush=True)
    try:
        process = subprocess.Popen(command, stdout=subprocess.PIPE, text=True, env=env)
    except OSError as exc:
        raise LocalRenderError(f"Cannot run pinned Cargo wrapper: {exc}") from exc
    artifacts = {}
    assert process.stdout is not None
    for line in process.stdout:
        try:
            message = json.loads(line)
        except ValueError:
            print(line.rstrip(), file=sys.stderr)
            continue
        if message.get("reason") == "compiler-message":
            rendered = message.get("message", {}).get("rendered")
            if rendered:
                print(rendered, end="", file=sys.stderr)
        elif message.get("reason") == "compiler-artifact":
            for filename in message.get("filenames", []):
                if filename.endswith(".rlib"):
                    artifacts[message["target"]["name"]] = filename
    if process.wait():
        raise LocalRenderError("Offline core build failed; see stderr. No dependencies or toolchains were installed.")
    channel_text = (root / "core/rust-toolchain.toml").read_text(encoding="utf-8")
    match = re.search(r'^\s*channel\s*=\s*"([^"\n]+)"', channel_text, re.MULTILINE)
    if not match:
        raise LocalRenderError("Missing pinned Rust channel")
    cargo_home = Path(os.environ.get("CARGO_HOME", Path.home() / ".cargo"))
    rustup = os.environ.get("INKU_RUSTUP_BIN", str(cargo_home / "bin/rustup"))
    rustc = _run([rustup, "which", "--toolchain", match[1], "rustc"],
                 capture_output=True, env=env).stdout.strip()
    version = _run([rustc, "--version"], capture_output=True, env=env).stdout.strip()
    if version.split()[1] != match[1]:
        raise LocalRenderError(f"Pinned rustc mismatch: {version}")
    source = Path(__file__).resolve().parent / "native/render_local.rs"
    if not source.is_file():
        raise LocalRenderError(f"CLI native driver source is missing: {source}")
    command = [rustc, "--edition=2024", "-C", "opt-level=3", str(source), "-o", str(binary)]
    required = ("inku_pipeline_uniffi", "inku_render", "inku_svg_raster", "serde_json", "resvg")
    for name in required:
        artifact = artifacts.get(name)
        if artifact is None:
            raise LocalRenderError(f"Selected core build did not produce {name}.rlib")
        command.extend(["--extern", f"{name}={artifact}"])
    for directory in sorted({str(Path(p).parent) for p in artifacts.values()}):
        command.extend(["-L", f"dependency={directory}"])
    # Build-script native libraries (e.g. Sudachi) remain next to Cargo artifacts.
    for directory in sorted((root / "core/target/release/build").glob("*/out")):
        command.extend(["-L", f"native={directory}"])
    _run(command, env=env)
    return {"rustc": version, "cargo_command": [str(p) for p in
            [root / "scripts/rust-toolchain.sh", "build", "--release", "--locked", "--offline",
             "--lib", "-p", "inku-pipeline-uniffi"]],
            "driver_sha256": hashlib.sha256(source.read_bytes()).hexdigest()}


def _provenance(root: Path) -> dict:
    result = {"checkout": str(root), "git_head": None, "git_dirty": None,
              "git_status": None, "git_available": False}
    try:
        top = subprocess.run(["git", "-C", str(root), "rev-parse", "--show-toplevel"],
                             capture_output=True, text=True)
        if top.returncode or Path(top.stdout.strip()).resolve() != root:
            return result
        head = _run(["git", "-C", str(root), "rev-parse", "HEAD"], capture_output=True)
        status = _run(["git", "-C", str(root), "status", "--porcelain=v1", "--untracked-files=all"],
                      capture_output=True)
    except (OSError, LocalRenderError):
        return result
    result.update(git_available=True, git_head=head.stdout.strip(),
                  git_dirty=bool(status.stdout), git_status=status.stdout.splitlines())
    return result


def _saved_canvas(svg: str | None) -> dict | None:
    if not svg:
        return None
    try:
        element = ET.fromstring(svg)
        width = float(element.attrib["width"])
        height = float(element.attrib["height"])
        if width > 0 and height > 0:
            return {"width": width, "height": height}
    except (ET.ParseError, KeyError, ValueError):
        pass
    raise LocalRenderError("Saved SVG has no valid numeric width/height; pass --canvas-height")


def _base_canvas_height(root: Path) -> int:
    # Read a literal source constant, without importing any Server modules/config.
    source = root / "server/src/inku_server/plugins/system/canvas_aspect/__init__.py"
    try:
        tree = ast.parse(source.read_text(encoding="utf-8"))
        for node in tree.body:
            if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name)
                    and t.id == "CANVAS_BASE_PX" for t in node.targets):
                value = ast.literal_eval(node.value)
                if isinstance(value, int) and value > 0:
                    return value
    except (OSError, SyntaxError, ValueError):
        pass
    raise LocalRenderError("Cannot read selected checkout's CANVAS_BASE_PX; pass --canvas-height")


def _seed(value, label: str):
    if value is None:
        return None
    if isinstance(value, bool) or not re.fullmatch(r"-?\d+", str(value)):
        raise LocalRenderError(f"{label} must be an integer or null")
    number = int(value)
    if not -(1 << 127) <= number < (1 << 127):
        raise LocalRenderError(f"{label} exceeds the core's signed 128-bit seed range")
    return number


def _request(args, root: Path, description: dict, document: dict) -> tuple[dict, str | None]:
    from_work = args.from_work_file is not None
    work = document if from_work else {}
    score = work.get("score") if from_work else document
    if not isinstance(score, dict):
        raise LocalRenderError("Input has no Score object")
    policy = score.get("resource_policy")
    if not isinstance(policy, dict) or not isinstance(policy.get("hard_policy"), dict):
        raise LocalRenderError("Score lacks resource_policy; checked saved replay needs a current compiled Score")
    hard = copy.deepcopy(policy["hard_policy"])
    budget = copy.deepcopy(policy.get("operational_budget"))
    if not isinstance(budget, dict) or not isinstance(budget.get("maximum"), dict):
        raise LocalRenderError("Score lacks an operational resource budget")
    # Other host limits bound DDL compilation; saved replay uses only these four.
    saved_limits = work.get("render_limits") or {}
    if not isinstance(saved_limits, dict):
        raise LocalRenderError("Saved render_limits must be an object")
    limits = {key: value for key, value in saved_limits.items() if key in _LIMIT_DIMENSIONS}
    for item in args.limits or []:
        key, separator, value = item.partition("=")
        if not separator or not re.fullmatch(r"\d+", value):
            raise LocalRenderError(f"Invalid limit {item!r}; expected KEY=nonnegative_integer")
        if key not in _LIMIT_DIMENSIONS:
            raise LocalRenderError(f"Unknown local render limit: {key}")
        limits[key] = int(value)
    for key, value in limits.items():
        dimension = _LIMIT_DIMENSIONS[key]
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise LocalRenderError(f"Invalid nonnegative resource limit: {key}")
        if value > hard["budget"]["maximum"][dimension]:
            raise LocalRenderError(f"{key} exceeds the Score's saved hard policy")
        budget["maximum"][dimension] = value
    expected = work.get("svg") if isinstance(work.get("svg"), str) else None
    aspect = args.canvas_aspect if args.canvas_aspect is not None else (
        work.get("render_canvas_aspect_id") or work.get("render_canvas_aspect") or "square")
    registry = description["canvas_registry"]["registry"]
    format_entry = next((f for f in registry["formats"] if f["id"] == aspect), None)
    if format_entry is None:
        raise LocalRenderError(f"Unknown core canvas format: {aspect}")
    canvas = None
    if args.canvas_height is None and args.canvas_aspect is None and expected:
        canvas = _saved_canvas(expected)
    if canvas is None:
        height = args.canvas_height if args.canvas_height is not None else _base_canvas_height(root)
        if height <= 0:
            raise LocalRenderError("Canvas height must be positive")
        canvas = {"width": round(height * format_entry["width_units"] / format_entry["height_units"]),
                  "height": height}
    color_map = (_json_file(Path(args.color_map).expanduser().resolve()) if args.color_map
                 else work.get("render_color_map", description["default_color_map"]))
    if not isinstance(color_map, dict) or not all(isinstance(k, str) and isinstance(v, str)
                                                for k, v in color_map.items()):
        raise LocalRenderError("Color map must be a JSON object of string keys and values")
    profile = args.svg_profile if args.svg_profile is not None else (
        work.get("render_svg_profile") or work.get("svg_profile") or "display")
    render_seed = args.render_seed if args.render_seed is not None else work.get("render_seed")
    composition_seed = (args.composition_seed if args.composition_seed is not None
                        else work.get("composition_seed", work.get("render_composition_seed")))
    wild = args.wild if args.wild is not None else work.get("render_wild", False)
    if not isinstance(wild, bool):
        raise LocalRenderError("Saved render_wild must be a boolean")
    options = {"resolved_color_map": color_map,
               "catalog_id": args.catalog_id if args.catalog_id is not None else (
                   work.get("render_color_catalog_id") or work.get("catalog_id") or "default"),
               "canvas": canvas, "canvas_aspect_id": aspect, "svg_profile": profile,
               "render_seed": _seed(render_seed, "render_seed"),
               "composition_seed": _seed(composition_seed, "composition_seed"),
               "wild": wild, "error_policy": "omit_and_continue"}
    return {"request": {"score": score, "options": options}, "hard_policy": hard,
            "operational_budget": budget, "clip": copy.deepcopy(_CLIP)}, expected


def render_local(args: argparse.Namespace) -> dict:
    """Build incrementally, render locally, and return machine-readable evidence."""
    started = time.perf_counter()
    root = _core_root(args.core_root)
    input_path = Path(args.from_work_file or args.file).expanduser().resolve()
    document = _json_file(input_path)
    svg_path = Path(args.output).expanduser().resolve()
    png_path = Path(args.png).expanduser().resolve() if args.png else None
    compare_path = Path(args.compare_svg).expanduser().resolve() if args.compare_svg else None
    protected = {input_path}
    if args.color_map:
        protected.add(Path(args.color_map).expanduser().resolve())
    if compare_path:
        protected.add(compare_path)
    if svg_path in protected or png_path in protected or svg_path == png_path:
        raise LocalRenderError("Output paths must differ from input, color-map, comparison, and each other")
    compare_bytes = None
    if compare_path:
        try:
            compare_bytes = compare_path.read_bytes()
        except OSError as exc:
            raise LocalRenderError(f"Cannot read comparison SVG {compare_path}: {exc}") from exc
    provenance = _provenance(root)
    build_started = time.perf_counter()
    cache = root / "core/target/inku-cli"
    try:
        cache.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="render-local-", dir=cache) as temporary:
            temporary = Path(temporary)
            binary = temporary / "render-local"
            build = _build(root, binary)
            build_ms = (time.perf_counter() - build_started) * 1000
            description = json.loads(_run([str(binary), "--describe"], capture_output=True).stdout)
            request, expected = _request(args, root, description, document)
            temp_svg = temporary / "output.svg"
            temp_png = temporary / "output.png"
            height = round(request["request"]["options"]["canvas"]["height"])
            result = _run([str(binary), str(temp_svg), str(temp_png) if png_path else "", str(height)],
                          input=json.dumps(request, ensure_ascii=False, allow_nan=False), capture_output=True)
            native = json.loads(result.stdout)
            svg = temp_svg.read_bytes()
            svg_path.parent.mkdir(parents=True, exist_ok=True)
            svg_path.write_bytes(svg)
            if png_path:
                png_path.parent.mkdir(parents=True, exist_ok=True)
                png_path.write_bytes(temp_png.read_bytes())
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise LocalRenderError(f"Local rendering failed: {exc}") from exc
    comparisons = []
    for source, expected_bytes in (("work.svg", expected.encode("utf-8") if expected is not None else None),
                                   (str(compare_path), compare_bytes)):
        if expected_bytes is not None:
            comparisons.append({"source": source, "equal": svg == expected_bytes,
                                "expected_bytes": len(expected_bytes),
                                "expected_sha256": hashlib.sha256(expected_bytes).hexdigest()})
    return {"svg_path": str(svg_path), "png_path": str(png_path) if png_path else None,
            "svg_bytes": len(svg), "svg_sha256": hashlib.sha256(svg).hexdigest(),
            "build_ms": build_ms, "render_ms": native["render_ms"],
            "raster_ms": native["raster_ms"], "total_ms": (time.perf_counter() - started) * 1000,
            "provenance": provenance, "build": build,
            "conditions": {**request["request"]["options"], "hard_policy": request["hard_policy"],
                           "operational_budget": request["operational_budget"], "clip": request["clip"]},
            "metadata": native["metadata"], "png_size": native["png_size"],
            "comparisons": comparisons, "comparison_equal": (
                all(c["equal"] for c in comparisons) if comparisons else None)}
