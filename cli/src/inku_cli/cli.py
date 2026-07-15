"""Command line client for controlling an inku API server."""

from __future__ import annotations

import argparse
import base64
import io
import getpass
import hashlib
import json
import math
import os
import re
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version
from http.cookies import SimpleCookie
from pathlib import Path
from typing import Any, TypeVar

from inku_analysis import (
    composition_distance as _composition_distance,
    composition_family as _composition_family_from_score,
    motif_signatures as _motif_signatures,
)

SESSION_COOKIE_NAME = "inku_session"
DEFAULT_BASE_URL = "http://127.0.0.1:8100"
DEFAULT_REQUEST_TIMEOUT_SECONDS = 600
SERVER_DEFAULT_MODEL_LABEL = "server default"
SERVER_DEFAULT_PROVIDER_LABEL = "server default"
PROVIDERS = ("nvidia", "anthropic", "local")
COLOR_KEYS = ("white", "black", "blue", "red", "green", "gray")
ACHROMATIC_COLOR_KEYS = {"white", "black", "gray"}
CHROMATIC_ACCENT_COLOR_KEYS = {"blue", "red", "green"}
DEFAULT_COLOR_CATALOG_ID = "default"
SVG_PROFILES = ("display", "editable", "compat")
CANVAS_ASPECT_RATIOS = {
    "square": 1.0,
    "golden": 1.618,
    "a4": 1.0 / 1.414,
    "b4": 1.0 / 1.414,
    "pillar": 1.0 / 5.0,
    "oban": 2.0 / 3.0,
    "wide": 2.35,
    "byobu": 2.2,
    "vertical": 9.0 / 16.0,
}

FIGURATIVE_HINT_RE = re.compile(r"\b(body|face|eye|mouth)\b")
CANVAS_ASPECTS = tuple(CANVAS_ASPECT_RATIOS.keys())
COLOR_MARKERS: dict[str, tuple[str, ...]] = {
    "white": ("white", "ivory", "snow", "白", "雪", "光"),
    "black": ("black", "dark", "shadow", "ink", "黒", "闇", "影", "墨"),
    "blue": ("blue", "water", "night", "cold", "sky", "青", "水", "夜", "冷", "空", "湖"),
    "red": ("red", "pink", "warm", "fire", "fruit", "赤", "紅", "桜", "桃", "温", "火", "果実"),
    "green": (
        "green",
        "forest",
        "leaf",
        "grass",
        "moss",
        "bamboo",
        "garden",
        "scent",
        "緑",
        "森",
        "草",
        "苔",
        "竹",
        "庭",
        "香り",
        "芽",
        "落ち葉",
        "若葉",
        "木の葉",
        "葉っぱ",
        "葉脈",
    ),
    "gray": ("gray", "grey", "silver", "ash", "stone", "灰", "銀", "石", "埃"),
}

def _marker_in_text(marker: str, text: str, lower: str) -> bool:
    marker_lower = marker.lower()
    if marker.isascii() and any(ch.isalpha() for ch in marker):
        return re.search(rf"(?<![a-z]){re.escape(marker_lower)}(?![a-z])", lower) is not None
    return marker in text or marker_lower in lower

def _canvas_aspect_ratio(canvas_aspect: str | None) -> float:
    return CANVAS_ASPECT_RATIOS.get(canvas_aspect or "square", CANVAS_ASPECT_RATIOS["square"])
NEGATED_COLOR_MARKERS: dict[str, tuple[str, ...]] = {
    "green": (
        "not green",
        "avoid green",
        "without green",
        "no green",
        "緑には寄せず",
        "緑に寄せず",
        "緑ではなく",
        "緑を避け",
        "緑を使わず",
        "緑なし",
    ),
}
MOTIF_HINT_KEYS = ("leaf_cluster", "paper_shard", "ripple_knot", "mountain_sign")
SCORE_REPAIR_PART_MARKERS = (
    ("adjacent_reaction", "adjacent reaction"),
    ("angular_pulse", "angular pulse"),
    ("vanishing_trace", "vanishing trace"),
    ("rhythm_offset", "rhythm offset"),
    ("inherited_memory_arc", "visual event type inherited_memory restored as a three-part memory sequence"),
)
T = TypeVar("T")

class CliError(RuntimeError):
    """Expected command-line failure."""

@dataclass(frozen=True)
class CliConfig:
    base_url: str = DEFAULT_BASE_URL
    token: str | None = None
    username: str | None = None
    stage1_provider: str | None = None
    stage1_model: str | None = None
    stage2_provider: str | None = None
    stage2_model: str | None = None
    timeout_seconds: int | None = None
    color_catalog: str | None = None

def _config_path() -> Path:
    env_path = os.getenv("INKU_CLI_CONFIG")
    if env_path:
        return Path(env_path).expanduser()
    config_home = Path(os.getenv("XDG_CONFIG_HOME", Path.home() / ".config")).expanduser()
    return config_home / "inku-cli" / "config.json"

def load_config(path: Path | None = None) -> CliConfig:
    path = path or _config_path()
    if not path.exists():
        timeout_env = os.getenv("INKU_CLI_TIMEOUT_SECONDS")
        catalog_env = os.getenv("INKU_COLOR_CATALOG")
        return CliConfig(
            base_url=os.getenv("INKU_BASE_URL", DEFAULT_BASE_URL),
            timeout_seconds=int(timeout_env) if timeout_env else None,
            color_catalog=catalog_env or None,
        )
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CliError(f"failed to read config: {path}") from exc
    return CliConfig(
        base_url=str(raw.get("base_url") or os.getenv("INKU_BASE_URL") or DEFAULT_BASE_URL),
        token=raw.get("token") or None,
        username=raw.get("username") or None,
        stage1_provider=raw.get("stage1_provider") or None,
        stage1_model=raw.get("stage1_model") or None,
        stage2_provider=raw.get("stage2_provider") or None,
        stage2_model=raw.get("stage2_model") or None,
        timeout_seconds=int(raw["timeout_seconds"]) if raw.get("timeout_seconds") is not None else None,
        color_catalog=raw.get("color_catalog") or None,
    )

def save_config(config: CliConfig, path: Path | None = None) -> None:
    path = path or _config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "base_url": config.base_url,
        "token": config.token,
        "username": config.username,
        "stage1_provider": config.stage1_provider,
        "stage1_model": config.stage1_model,
        "stage2_provider": config.stage2_provider,
        "stage2_model": config.stage2_model,
        "timeout_seconds": config.timeout_seconds,
        "color_catalog": config.color_catalog,
    }
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass

def clear_config(path: Path | None = None) -> None:
    path = path or _config_path()
    try:
        path.unlink()
    except FileNotFoundError:
        pass

def _join_url(base_url: str, path: str) -> str:
    return urllib.parse.urljoin(base_url.rstrip("/") + "/", path.lstrip("/"))

def _extract_session_token(set_cookie: str | None) -> str | None:
    if not set_cookie:
        return None
    cookie = SimpleCookie()
    cookie.load(set_cookie)
    morsel = cookie.get(SESSION_COOKIE_NAME)
    return morsel.value if morsel else None

class ApiClient:
    def __init__(
        self,
        base_url: str,
        token: str | None = None,
        *,
        timeout_seconds: int = DEFAULT_REQUEST_TIMEOUT_SECONDS,
    ) -> None:
        self.base_url = base_url
        self.token = token
        self.timeout_seconds = timeout_seconds

    def request(
        self,
        method: str,
        path: str,
        *,
        data: dict[str, Any] | None = None,
        query: dict[str, Any] | None = None,
        auth: bool = True,
    ) -> tuple[dict[str, Any], urllib.response.addinfourl]:
        url = _join_url(self.base_url, path)
        if query:
            clean_query = {k: v for k, v in query.items() if v is not None}
            if clean_query:
                url += "?" + urllib.parse.urlencode(clean_query)
        body = None
        headers = {"Accept": "application/json"}
        if data is not None:
            body = json.dumps(data, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        if auth:
            if not self.token:
                raise CliError("not logged in; run `inku-cli login` first")
            headers["Authorization"] = f"Bearer {self.token}"
        req = urllib.request.Request(url, data=body, headers=headers, method=method.upper())
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_seconds) as response:
                raw = response.read()
                parsed = json.loads(raw.decode("utf-8")) if raw else {}
                return parsed, response
        except urllib.error.HTTPError as exc:
            message = exc.reason
            try:
                parsed_error = json.loads(exc.read().decode("utf-8"))
                message = parsed_error.get("detail") or parsed_error.get("message") or str(parsed_error)
            except Exception:
                pass
            raise CliError(f"HTTP {exc.code}: {message}") from exc
        except urllib.error.URLError as exc:
            raise CliError(f"failed to connect to {self.base_url}: {exc.reason}") from exc

    def request_text(
        self,
        method: str,
        path: str,
        *,
        data: dict[str, Any] | None = None,
        query: dict[str, Any] | None = None,
        auth: bool = True,
    ) -> str:
        url = _join_url(self.base_url, path)
        if query:
            clean_query = {k: v for k, v in query.items() if v is not None}
            if clean_query:
                url += "?" + urllib.parse.urlencode(clean_query)
        body = None
        headers = {"Accept": "image/svg+xml,text/plain,*/*"}
        if data is not None:
            body = json.dumps(data, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        if auth:
            if not self.token:
                raise CliError("not logged in; run `inku-cli login` first")
            headers["Authorization"] = f"Bearer {self.token}"
        req = urllib.request.Request(url, data=body, headers=headers, method=method.upper())
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_seconds) as response:
                return response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            message = exc.reason
            try:
                parsed_error = json.loads(exc.read().decode("utf-8"))
                message = parsed_error.get("detail") or parsed_error.get("message") or str(parsed_error)
            except Exception:
                pass
            raise CliError(f"HTTP {exc.code}: {message}") from exc
        except urllib.error.URLError as exc:
            raise CliError(f"failed to connect to {self.base_url}: {exc.reason}") from exc

def _cli_version() -> str:
    try:
        return version("inku-cli")
    except PackageNotFoundError:
        return "0.1.0"

def _cli_build_number() -> str | None:
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "web" / "BUILD_NUMBER"
        try:
            return candidate.read_text(encoding="utf-8").strip() or None
        except OSError:
            continue
    return None

def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

def _render_hash_for_score(
    score: dict[str, Any],
    *,
    render_seed: int | None = None,
    vary_seed: int | None = None,
    render_build_number: str | None = None,
    render_engine_id: str | None = None,
    render_engine_version: str | None = None,
    render_color_catalog_id: str | None = None,
) -> str:
    payload = {
        "version": "rh2",
        "score": score or {},
        "render_seed": render_seed,
        "vary_seed": vary_seed,
        "render_build_number": render_build_number,
        "render_engine_id": render_engine_id,
        "render_engine_version": render_engine_version,
        "render_color_catalog_id": render_color_catalog_id,
    }
    return "rh2:" + hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()

def _render_color_map(catalog: dict[str, Any]) -> dict[str, str]:
    base = catalog.get("map")
    if not isinstance(base, dict):
        raise CliError(f"invalid color catalog from server: {catalog.get('id')}")
    color_map = {str(key): str(value) for key, value in base.items()}
    palette = catalog.get("palette")
    if isinstance(palette, list):
        for item in palette:
            if isinstance(item, dict) and isinstance(item.get("name"), str) and isinstance(item.get("code"), str):
                color_map[f"palette:{item['name']}"] = item["code"]
    return color_map

def _fetch_color_catalogs(client: ApiClient) -> dict[str, Any]:
    data, _ = client.request("GET", "/api/color-catalogs", auth=False)
    catalogs = data.get("catalogs")
    if not isinstance(catalogs, list):
        raise CliError("server returned invalid color catalog list")
    by_id: dict[str, dict[str, Any]] = {}
    for catalog in catalogs:
        if isinstance(catalog, dict) and isinstance(catalog.get("id"), str):
            by_id[catalog["id"]] = catalog
    default_id = data.get("default_catalog_id") or DEFAULT_COLOR_CATALOG_ID
    if default_id not in by_id:
        raise CliError("server color catalog list does not include default catalog")
    return {"default_catalog_id": default_id, "catalogs": by_id}

def _catalog_choices(catalog_data: dict[str, Any]) -> tuple[str, ...]:
    catalogs = catalog_data.get("catalogs")
    return tuple(catalogs.keys()) if isinstance(catalogs, dict) else ()

def _catalog_by_id(catalog_data: dict[str, Any], catalog_id: str) -> dict[str, Any]:
    catalogs = catalog_data.get("catalogs")
    if not isinstance(catalogs, dict) or catalog_id not in catalogs:
        choices = ", ".join(_catalog_choices(catalog_data))
        raise CliError(f"unknown color catalog: {catalog_id}. choices: {choices}")
    catalog = catalogs[catalog_id]
    if not isinstance(catalog, dict):
        raise CliError(f"invalid color catalog from server: {catalog_id}")
    return catalog

def _print_json(data: Any) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2))

def _write_json_file(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

def _display_model(model: str | None) -> str:
    return model or SERVER_DEFAULT_MODEL_LABEL

def _display_provider(provider: str | None) -> str:
    return provider or SERVER_DEFAULT_PROVIDER_LABEL

def _resolved_stage1_provider(args: argparse.Namespace, config: CliConfig) -> str | None:
    return args.stage1_provider or config.stage1_provider

def _resolved_stage2_provider(args: argparse.Namespace, config: CliConfig) -> str | None:
    return args.stage2_provider or config.stage2_provider

def _resolved_stage1_model(args: argparse.Namespace, config: CliConfig) -> str | None:
    return args.stage1_model or config.stage1_model

def _resolved_stage2_model(args: argparse.Namespace, config: CliConfig) -> str | None:
    return args.stage2_model or config.stage2_model

def _resolved_timeout_seconds(args: argparse.Namespace, config: CliConfig) -> int:
    return args.timeout_seconds or config.timeout_seconds or DEFAULT_REQUEST_TIMEOUT_SECONDS

def _resolved_color_catalog(args: argparse.Namespace, config: CliConfig, catalog_data: dict[str, Any]) -> str:
    requested = getattr(args, "color_catalog", None) or getattr(args, "catalog_id", None) or config.color_catalog
    catalog = requested or str(catalog_data.get("default_catalog_id") or DEFAULT_COLOR_CATALOG_ID)
    _catalog_by_id(catalog_data, catalog)
    return catalog

def _color_catalog_summary(catalog_id: str, catalog_data: dict[str, Any]) -> dict[str, Any]:
    catalog = _catalog_by_id(catalog_data, catalog_id)
    color_map = _render_color_map(catalog)
    return {
        "requested_color_catalog": catalog_id,
        "resolved_color_catalog": catalog["id"],
        "color_catalog_name": catalog.get("name"),
        "color_map": dict(color_map),
    }

def _render_response_summary(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "render_build_number": result.get("render_build_number"),
        "render_seed": result.get("render_seed"),
        "render_hash": result.get("render_hash"),
        "render_hash_short": result.get("render_hash_short"),
        "render_color_catalog_id": result.get("render_color_catalog_id"),
        "render_color_catalog_name": result.get("render_color_catalog_name"),
        "render_color_catalog_sub": result.get("render_color_catalog_sub"),
        "render_color_map": result.get("render_color_map"),
        "coerce_relation_input_count": result.get("coerce_relation_input_count"),
        "coerce_relation_output_count": result.get("coerce_relation_output_count"),
        "coerce_relation_dropped_count": result.get("coerce_relation_dropped_count"),
        "coerce_relation_drop_rate": result.get("coerce_relation_drop_rate"),
        "coerce_warnings": result.get("coerce_warnings") or [],
        "coerce_branch_counts": result.get("coerce_branch_counts") or {},
    }

def _model_summary(
    stage1_model: str | None,
    stage2_model: str | None,
    *,
    stage1_provider: str | None = None,
    stage2_provider: str | None = None,
) -> dict[str, str | None]:
    return {
        "stage1_provider": stage1_provider,
        "stage1_model": stage1_model,
        "stage2_provider": stage2_provider,
        "stage2_model": stage2_model,
        "stage1_provider_display": _display_provider(stage1_provider),
        "stage1_model_display": _display_model(stage1_model),
        "stage2_provider_display": _display_provider(stage2_provider),
        "stage2_model_display": _display_model(stage2_model),
    }

def _print_model_summary(
    stage1_model: str | None,
    stage2_model: str | None,
    *,
    stage1_provider: str | None = None,
    stage2_provider: str | None = None,
) -> None:
    print(f"Stage1 provider: {_display_provider(stage1_provider)}", file=sys.stderr)
    print(f"Stage1 model: {_display_model(stage1_model)}", file=sys.stderr)
    print(f"Stage2 provider: {_display_provider(stage2_provider)}", file=sys.stderr)
    print(f"Stage2 model: {_display_model(stage2_model)}", file=sys.stderr)

def _print_color_catalog_summary(catalog_id: str, catalog_data: dict[str, Any]) -> None:
    catalog = _catalog_by_id(catalog_data, catalog_id)
    print(f"Color catalog: {catalog['id']} ({catalog.get('name') or catalog['id']})", file=sys.stderr)

def _run_with_progress(
    label: str,
    operation: Callable[[], T],
    *,
    enabled: bool = True,
) -> T:
    if not enabled:
        return operation()

    result: list[T] = []
    errors: list[BaseException] = []

    def target() -> None:
        try:
            result.append(operation())
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    thread = threading.Thread(target=target, daemon=True)
    thread.start()
    started = time.monotonic()
    frames = ("(^_^)   ", "(^_^).  ", "(^_^).. ", "(^_^)...", "(^_^) ..", "(^_^)  .")
    index = 0
    while thread.is_alive():
        elapsed = int(time.monotonic() - started)
        frame = frames[index % len(frames)]
        print(f"\r{frame} {label} {elapsed:>3}s", end="", file=sys.stderr, flush=True)
        index += 1
        thread.join(0.5)
    print("\r" + " " * 48 + "\r", end="", file=sys.stderr, flush=True)
    if errors:
        raise errors[0]
    return result[0]

def _read_text_argument(text: str | None, file_path: str | None) -> str:
    if file_path:
        if file_path == "-":
            return sys.stdin.read().strip()
        return Path(file_path).read_text(encoding="utf-8").strip()
    if text:
        return text.strip()
    raise CliError("text is required")

def _write_paint_outputs(
    result: dict[str, Any],
    *,
    out_dir: Path | None,
    prefix: str,
    png: bool,
) -> dict[str, str]:
    if out_dir is None:
        return {}
    out_dir.mkdir(parents=True, exist_ok=True)
    paths: dict[str, str] = {}
    json_path = out_dir / f"{prefix}.json"
    svg_path = out_dir / f"{prefix}.svg"
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    svg_path.write_text(str(result["svg"]), encoding="utf-8")
    paths["json"] = str(json_path)
    paths["svg"] = str(svg_path)
    if png:
        try:
            import cairosvg
        except ImportError as exc:
            raise CliError("PNG output requires cairosvg") from exc
        png_path = out_dir / f"{prefix}.png"
        cairosvg.svg2png(bytestring=str(result["svg"]).encode("utf-8"), write_to=str(png_path))
        paths["png"] = str(png_path)
    return paths

def _result_with_svg_profile(
    client: ApiClient,
    result: dict[str, Any],
    *,
    svg_profile: str,
    color_catalog: str,
) -> dict[str, Any]:
    output = dict(result)
    output["svg_profile"] = svg_profile
    if svg_profile == "display":
        return output
    output["svg"] = client.request_text(
        "POST",
        "/api/render-svg",
        data={
            "score": result.get("score") or {},
            "catalog_id": result.get("render_color_catalog_id") or color_catalog,
            "svg_profile": svg_profile,
            "render_seed": result.get("render_seed"),
        },
    )
    return output

def _review_sets(results: list[dict[str, Any]], *, slow_ms: int = 100_000) -> dict[str, list[int]]:
    fallback: list[int] = []
    slow: list[int] = []
    normal: list[int] = []
    for result in results:
        line = int(result.get("line") or 0)
        if not line:
            continue
        uses_fallback = bool(result.get("interpret_fallback_used") or result.get("compose_fallback_used"))
        is_slow = int(result.get("elapsed_total_ms") or 0) >= slow_ms
        if uses_fallback:
            fallback.append(line)
        if is_slow:
            slow.append(line)
        if not uses_fallback and not is_slow:
            normal.append(line)
    return {
        "all_success_samples": [int(result.get("line") or 0) for result in results if result.get("line")],
        "fallback_samples": fallback,
        "slow_samples": slow,
        "normal_samples": normal,
    }

def _server_timeout_reasons(result: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    for key in ("interpret_fallback_reasons", "compose_retry_reasons"):
        values = result.get(key)
        if not isinstance(values, list):
            continue
        for value in values:
            if isinstance(value, str) and "hard_timeout" in value:
                reasons.append(value)
    return reasons

def _make_contact_sheet(input_dir: Path, output_path: Path, *, columns: int, thumb_size: int, order: str = "name") -> None:
    try:
        from PIL import Image, ImageDraw
    except ImportError as exc:
        raise CliError("contact-sheet requires Pillow") from exc

    pngs = sorted(path for path in input_dir.glob("*.png") if path.name != output_path.name)
    if order == "similarity":
        artifact_scores = {Path(item["path"]).stem: item["score"] for item in _iter_score_artifacts(input_dir)}
        remaining = list(pngs)
        ordered: list[Path] = []
        if remaining:
            ordered.append(remaining.pop(0))
        while remaining:
            previous = artifact_scores.get(ordered[-1].stem, {})
            next_path = min(
                remaining,
                key=lambda candidate: (_composition_distance(previous, artifact_scores.get(candidate.stem, {})), candidate.name),
            )
            remaining.remove(next_path)
            ordered.append(next_path)
        pngs = ordered
    if not pngs:
        raise CliError(f"no PNG files found in {input_dir}")

    columns = max(1, columns)
    thumb_size = max(64, thumb_size)
    label_h = 24
    gap = 12
    rows = (len(pngs) + columns - 1) // columns
    width = columns * thumb_size + (columns + 1) * gap
    height = rows * (thumb_size + label_h) + (rows + 1) * gap
    sheet = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(sheet)

    for index, image_path in enumerate(pngs):
        row, col = divmod(index, columns)
        x = gap + col * (thumb_size + gap)
        y = gap + row * (thumb_size + label_h + gap)
        with Image.open(image_path) as image:
            image = image.convert("RGB")
            image.thumbnail((thumb_size, thumb_size))
            px = x + (thumb_size - image.width) // 2
            py = y + (thumb_size - image.height) // 2
            sheet.paste(image, (px, py))
        draw.text((x, y + thumb_size + 4), image_path.stem, fill=(40, 40, 40))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output_path)

def _png_occupancy_grid(path: Path, *, cells: int = 16) -> list[float]:
    try:
        from PIL import Image
    except ImportError as exc:
        raise CliError("analyze --diversity requires Pillow") from exc
    with Image.open(path) as image:
        image = image.convert("L").resize((cells, cells))
        pixels = list(image.getdata())
    return [1.0 - (float(pixel) / 255.0) for pixel in pixels]

def _svg_occupancy_grid(svg: str, *, cells: int = 16) -> list[float]:
    try:
        import cairosvg
        from PIL import Image
    except ImportError as exc:
        raise CliError("analyze --replay requires cairosvg and Pillow") from exc
    buffer = io.BytesIO()
    cairosvg.svg2png(bytestring=svg.encode("utf-8"), write_to=buffer)
    buffer.seek(0)
    with Image.open(buffer) as image:
        image = image.convert("L").resize((cells, cells))
        pixels = list(image.getdata())
    return [1.0 - (float(pixel) / 255.0) for pixel in pixels]

def _cosine_distance(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na <= 1e-12 and nb <= 1e-12:
        return 0.0
    if na <= 1e-12 or nb <= 1e-12:
        return 1.0
    return max(0.0, min(1.0, 1.0 - dot / (na * nb)))

def _mean_pair_distance(vectors: list[list[float]]) -> float | None:
    if len(vectors) < 2:
        return None
    total = 0.0
    count = 0
    for i, first in enumerate(vectors):
        for second in vectors[i + 1:]:
            total += _cosine_distance(first, second)
            count += 1
    return round(total / count, 6) if count else None

def _entropy_bits(counter: Counter[str]) -> float:
    total = sum(counter.values())
    if total <= 0:
        return 0.0
    entropy = 0.0
    for count in counter.values():
        if count <= 0:
            continue
        p = count / total
        entropy -= p * math.log2(p)
    return entropy

def _normalized_entropy(counter: Counter[str]) -> float | None:
    if not counter:
        return None
    k = len(counter)
    if k <= 1:
        return 0.0
    return round(_entropy_bits(counter) / math.log2(k), 6)

def _score_from_artifact(data: dict[str, Any]) -> dict[str, Any] | None:
    score = data.get("score") if isinstance(data, dict) else None
    if isinstance(score, dict):
        return score
    if isinstance(data.get("instructions"), list):
        return data
    return None

def _iter_score_artifacts(input_dir: Path) -> list[dict[str, Any]]:
    artifacts: list[dict[str, Any]] = []
    for path in sorted(input_dir.rglob("*.json")):
        if path.name in {"analysis-summary.json", "summary.json", "diversity-summary.json"}:
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict):
            continue
        score = _score_from_artifact(data)
        if score is None:
            continue
        artifacts.append({"path": str(path), "score": score, "artifact": data})
    return artifacts

def _dominant_angle_bin(score: dict[str, Any]) -> int | None:
    bins: Counter[int] = Counter()
    instructions = score.get("instructions")
    if not isinstance(instructions, list):
        return None
    for instruction in instructions:
        if not isinstance(instruction, dict):
            continue
        start = _coord_pair(instruction.get("from"))
        end = _coord_pair(instruction.get("to"))
        if start is not None and end is not None:
            angle = math.atan2(end[1] - start[1], end[0] - start[0]) % math.pi
            bins[int((angle / math.pi) * 8) % 8] += 1
        arrangement = instruction.get("arrangement")
        if isinstance(arrangement, dict):
            path = arrangement.get("path")
            layout = arrangement.get("layout")
            if path == "diagonal":
                bins[7] += 1
            elif path == "top_to_bottom" or layout == "vertical":
                bins[2] += 1
            elif path == "left_to_right" or layout == "horizontal":
                bins[0] += 1
            elif path == "wave":
                bins[0] += 1
            elif layout == "radial":
                bins[4] += 1
    if not bins:
        return None
    return bins.most_common(1)[0][0]

def _motif_census(input_dir: Path) -> dict[str, Any]:
    counts: Counter[str] = Counter()
    examples: dict[str, list[str]] = {}
    for artifact in _iter_score_artifacts(input_dir):
        stem = Path(artifact["path"]).stem
        for signature in _motif_signatures(artifact["score"]):
            counts[signature] += 1
            examples.setdefault(signature, [])
            png = input_dir / f"{stem}.png"
            if png.exists() and len(examples[signature]) < 3:
                examples[signature].append(str(png))
    return {
        "input_dir": str(input_dir),
        "motifs": [{"signature": signature, "frequency": frequency, "thumbnail_examples": examples.get(signature, [])} for signature, frequency in counts.most_common()],
        "note": "This census is a human mirror. It is not connected to generation or suppression.",
    }

def _motif_census_from_history(items: list[dict[str, Any]], *, base_url: str) -> dict[str, Any]:
    counts: Counter[str] = Counter()
    examples: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        score = item.get("score")
        if not isinstance(score, dict):
            continue
        for signature in _motif_signatures(score):
            counts[signature] += 1
            examples.setdefault(signature, [])
            item_id = str(item.get("id") or "")
            if item_id and len(examples[signature]) < 3:
                examples[signature].append({
                    "history_id": item_id,
                    "input": item.get("input"),
                    "thumbnail_url": _join_url(base_url, f"/api/history/{item_id}/svg"),
                })
    return {
        "source": "history",
        "history_count": len(items),
        "motifs": [
            {
                "signature": signature,
                "frequency": frequency,
                "thumbnail_examples": examples.get(signature, []),
            }
            for signature, frequency in counts.most_common()
        ],
        "note": "This census is a human mirror. It is not connected to generation or suppression.",
    }

def _nim_vision_chat(image_path: Path, prompt: str, *, api_key: str, model: str) -> str:
    mime = "image/png" if image_path.suffix.lower() == ".png" else "image/jpeg"
    encoded = base64.b64encode(image_path.read_bytes()).decode("ascii")
    body = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{encoded}"}},
        ]}],
        "temperature": 0.2,
        "max_tokens": 300,
    }).encode("utf-8")
    request = urllib.request.Request(
        "https://integrate.api.nvidia.com/v1/chat/completions", data=body, method="POST",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        raise CliError(f"vision request failed: {exc}") from exc
    return str(payload["choices"][0]["message"]["content"]).strip()

def _ddl_relation_present(ddl: str) -> bool:
    lower = ddl.lower()
    return any(marker in lower for marker in ("前の", "直前", "沿って", "触れない", "切る", "between", "along", "not touching", "cutting"))

def _ddl_unknown_terms(ddl: str) -> list[str]:
    # A conservative lexical sensor: only report unknown ASCII terms. Japanese
    # remains visible verbatim in the side-by-side table for human inspection.
    allowed = {
        "line", "lines", "circle", "circles", "ellipse", "ellipses", "triangle", "triangles",
        "square", "squares", "polygon", "arc", "black", "white", "blue", "red", "green", "gray",
        "thin", "thick", "small", "large", "horizontal", "vertical", "diagonal", "scatter", "grid",
        "place", "draw", "arrange", "fill", "solid", "dashed", "dotted", "along", "between", "not",
        "touching", "cutting", "top", "bottom", "left", "right", "center", "canvas", "with", "and",
        "from", "to", "in", "on", "of", "the", "a", "an", "one", "two", "three", "four", "five",
    }
    tokens = re.findall(r"[a-z][a-z_-]+", ddl.lower())
    return sorted({token for token in tokens if token not in allowed})

def command_ddl_compare(args: argparse.Namespace) -> int:
    directories = [Path(value) for value in args.input_dirs]
    collections = []
    for directory in directories:
        artifacts = _iter_score_artifacts(directory)
        by_key = {}
        for artifact in artifacts:
            payload = artifact["artifact"]
            key = str(payload.get("line") or Path(artifact["path"]).stem)
            by_key[key] = payload
        collections.append(by_key)
    keys = sorted(set().union(*(items.keys() for items in collections)))
    rows = []
    for key in keys:
        variants = []
        original = None
        for directory, items in zip(directories, collections):
            payload = items.get(key) or {}
            ddl = str(payload.get("ddl") or "")
            original = original or payload.get("text") or payload.get("input") or payload.get("original_text")
            variants.append({
                "artifact_set": str(directory), "ddl": ddl,
                "saijiki_outside_ascii_terms": _ddl_unknown_terms(ddl),
                "relation_phrase_present": _ddl_relation_present(ddl),
            })
        rows.append({"key": key, "input": original, "variants": variants})
    report = {"artifact_sets": [str(item) for item in directories], "rows": rows, "note": "Side-by-side diagnostic only; no score or automatic winner."}
    output = Path(args.output) if args.output else Path("ddl-comparison.json")
    _write_json_file(output, report)
    _print_json(report)
    return 0

def command_vision_review(args: argparse.Namespace) -> int:
    input_dir = Path(args.input_dir)
    api_key = os.getenv("NVIDIA_API_KEY") or os.getenv("NVIDIA_NIM_API_KEY")
    if not api_key:
        raise CliError("NVIDIA_API_KEY is required for vision-review")
    pngs = sorted(path for path in input_dir.glob("*.png") if path.name != "contact-sheet.png")
    rows = []
    artifacts = {Path(item["path"]).stem: item["artifact"] for item in _iter_score_artifacts(input_dir)}
    for image_path in pngs:
        artifact = artifacts.get(image_path.stem, {})
        rows.append({
            "image": str(image_path),
            "original": artifact.get("text") or artifact.get("input") or artifact.get("original_text"),
            "blind_back_translation_ja": _nim_vision_chat(image_path, "入力文を推測せず、この抽象画に実際に見えるものだけを日本語一文で記述してください。", api_key=api_key, model=args.model),
            "blind_back_translation_en": _nim_vision_chat(image_path, "Describe only what is visibly present in this abstract image in one English sentence. Do not infer its prompt.", api_key=api_key, model=args.model),
        })
    sheet = input_dir / "contact-sheet.png"
    step_back = None
    if sheet.exists():
        step_back = _nim_vision_chat(sheet, "番号付き作品のうち最も似て見える組を3組、番号で挙げ、共通して見える部品を言葉で記述してください。点数は付けないでください。", api_key=api_key, model=args.model)
    summary = {"model": args.model, "role": "regression sensor and audit aid; never an acceptance gate or generation objective", "back_translations": rows, "tabletop_step_back": step_back}
    output = Path(args.output) if args.output else input_dir / "vision-review-summary.json"
    _write_json_file(output, summary)
    print(str(output))
    return 0

def _diversity_summary(
    input_dir: Path,
    *,
    replay: int = 0,
    replay_limit: int = 5,
    client: ApiClient | None = None,
    color_catalog: str = DEFAULT_COLOR_CATALOG_ID,
    canvas_aspect: str | None = None,
) -> dict[str, Any]:
    png_paths = sorted(path for path in input_dir.rglob("*.png") if path.name != "contact-sheet.png")
    grids = [_png_occupancy_grid(path) for path in png_paths]
    artifacts = _iter_score_artifacts(input_dir)
    primitive_counts: Counter[str] = Counter()
    color_counts: Counter[str] = Counter()
    weight_counts: Counter[str] = Counter()
    layout_counts: Counter[str] = Counter()
    path_counts: Counter[str] = Counter()
    family_counts: Counter[str] = Counter()
    angle_bins: Counter[str] = Counter()
    relation_counts: Counter[str] = Counter()
    relation_sample_count = 0
    repair_part_counts: Counter[str] = Counter()
    repair_part_sample_counts: Counter[str] = Counter()
    density_counts: Counter[str] = Counter()
    for artifact in artifacts:
        score = artifact["score"]
        family_counts[_composition_family_from_score(score)] += 1
        artifact_repair_parts = _score_metrics(score).get("score_repair_part_counts") or {}
        repair_part_counts.update(artifact_repair_parts)
        repair_part_sample_counts.update(artifact_repair_parts.keys())
        angle_bin = _dominant_angle_bin(score)
        if angle_bin is not None:
            angle_bins[str(angle_bin)] += 1
        has_relation = False
        instructions = score.get("instructions")
        if not isinstance(instructions, list):
            continue
        for instruction in instructions:
            if not isinstance(instruction, dict):
                continue
            for key, counter in (("primitive", primitive_counts), ("color", color_counts), ("weight", weight_counts)):
                value = instruction.get(key)
                if isinstance(value, str):
                    counter[value] += 1
            relation = instruction.get("relation")
            if isinstance(relation, dict) and isinstance(relation.get("type"), str):
                relation_counts[relation["type"]] += 1
                has_relation = True
            arrangement = instruction.get("arrangement")
            if isinstance(arrangement, dict):
                layout = arrangement.get("layout")
                path = arrangement.get("path")
                density = arrangement.get("density")
                if isinstance(layout, str):
                    layout_counts[layout] += 1
                if isinstance(path, str):
                    path_counts[path] += 1
                if isinstance(density, str):
                    density_counts[density] += 1
        if has_relation:
            relation_sample_count += 1
    replay_items: list[dict[str, Any]] = []
    if replay > 1:
        if client is None:
            raise CliError("analyze --replay requires API access; log in or provide --base-url")
        for artifact in artifacts[: max(1, replay_limit)]:
            vectors: list[list[float]] = []
            for seed in range(1, replay + 1):
                svg = client.request_text(
                    "POST",
                    "/api/render-svg",
                    data={
                        "score": artifact["score"],
                        "catalog_id": color_catalog,
                        "canvas_aspect": canvas_aspect,
                        "render_seed": seed,
                    },
                )
                vectors.append(_svg_occupancy_grid(svg))
            replay_items.append({
                "path": artifact["path"],
                "replay_count": replay,
                "composition_distance": _mean_pair_distance(vectors),
            })
    replay_values = [item["composition_distance"] for item in replay_items if item.get("composition_distance") is not None]
    family_total = sum(family_counts.values())
    return {
        "input_dir": str(input_dir),
        "png_count": len(png_paths),
        "score_count": len(artifacts),
        "composition_distance": _mean_pair_distance(grids),
        "angle_entropy_bits": round(_entropy_bits(angle_bins), 6),
        "angle_bins": dict(sorted(angle_bins.items())),
        "vocab_entropy": {
            "primitive": _normalized_entropy(primitive_counts),
            "color": _normalized_entropy(color_counts),
            "weight": _normalized_entropy(weight_counts),
            "layout": _normalized_entropy(layout_counts),
            "path": _normalized_entropy(path_counts),
        },
        "family_counts": dict(sorted(family_counts.items())),
        "family_share_max": round(max(family_counts.values()) / family_total, 6) if family_total else None,
        "relation_counts": dict(sorted(relation_counts.items())),
        "relation_sample_count": relation_sample_count,
        "score_repair_part_counts": dict(sorted(repair_part_counts.items())),
        "score_repair_part_sample_counts": dict(sorted(repair_part_sample_counts.items())),
        "score_repair_part_sample_rates": {
            key: round(value / len(artifacts), 6) for key, value in sorted(repair_part_sample_counts.items())
        } if artifacts else {},
        "relation_sample_rate": round(relation_sample_count / len(artifacts), 6) if artifacts else None,
        "density_counts": dict(sorted(density_counts.items())),
        "replay": {
            "requested_count": replay,
            "sample_count": len(replay_items),
            "replay_divergence": round(sum(replay_values) / len(replay_values), 6) if replay_values else None,
            "items": replay_items,
        },
        "score_primitive_counts": dict(sorted(primitive_counts.items())),
        "score_color_counts": dict(sorted(color_counts.items())),
    }

def _history_hash_label(item: dict[str, Any]) -> str:
    value = item.get("render_hash_short") or str(item.get("render_hash") or "")[-4:]
    return str(value).upper()

def _history_hash_matches(item: dict[str, Any], ref: str) -> bool:
    needle = ref.strip().lower().removeprefix("#")
    render_hash = str(item.get("render_hash") or "").lower()
    short_hash = str(item.get("render_hash_short") or "").lower()
    return bool(needle) and (render_hash.endswith(needle) or short_hash == needle)

def _resolve_history_hash(items: list[dict[str, Any]], ref: str) -> dict[str, Any]:
    matches = [item for item in items if _history_hash_matches(item, ref)]
    if not matches:
        raise CliError(f"history hash not found: {ref}")
    if len(matches) > 1:
        candidates = ", ".join(
            f"#{_history_hash_label(item)} {item.get('at')} {str(item.get('input') or '')[:28]}"
            for item in matches[:8]
        )
        raise CliError(f"history hash is ambiguous: {ref}. candidates: {candidates}. Use more digits.")
    return matches[0]

def _select_history_items(
    items: list[dict[str, Any]],
    *,
    hashes: list[str],
    from_hash: str | None,
    to_hash: str | None,
) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    seen: set[str] = set()
    if from_hash or to_hash:
        if not from_hash or not to_hash:
            raise CliError("--from and --to must be used together")
        start = _resolve_history_hash(items, from_hash)
        end = _resolve_history_hash(items, to_hash)
        start_index = items.index(start)
        end_index = items.index(end)
        lo, hi = sorted((start_index, end_index))
        for item in items[lo:hi + 1]:
            item_id = str(item.get("id") or "")
            if item_id and item_id not in seen:
                selected.append(item)
                seen.add(item_id)
    for ref in hashes:
        item = _resolve_history_hash(items, ref)
        item_id = str(item.get("id") or "")
        if item_id and item_id not in seen:
            selected.append(item)
            seen.add(item_id)
    if not selected:
        raise CliError("no history hashes were specified")
    return selected

def _fetch_all_history(client: ApiClient, *, starred: bool = False, query: str | None = None) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    offset = 0
    limit = 100
    total = None
    while total is None or offset < total:
        data, _ = client.request(
            "GET",
            "/api/history",
            query={"offset": offset, "limit": limit, "q": query, "starred": starred},
        )
        page = data.get("items")
        if not isinstance(page, list):
            raise CliError("server returned invalid history list")
        items.extend(item for item in page if isinstance(item, dict))
        total = int(data.get("total") or len(items))
        if not page:
            break
        offset += len(page)
    return items

def _history_export_summary(items: list[dict[str, Any]], paths: dict[str, Any]) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    evaluation_items: list[dict[str, Any]] = []
    total_elapsed = 0
    total_in = 0
    total_out = 0
    for index, item in enumerate(items, start=1):
        tokens_in = int(item.get("tokens_in") or 0)
        tokens_out = int(item.get("tokens_out") or 0)
        elapsed = int(item.get("elapsed_ms") or 0)
        total_in += tokens_in
        total_out += tokens_out
        total_elapsed += elapsed
        results.append({
            "index": index,
            "id": item.get("id"),
            "hash": item.get("render_hash"),
            "hash_short": _history_hash_label(item),
            "at": item.get("at"),
            "text": item.get("input"),
            "ddl": item.get("ddl"),
            "elapsed_ms": elapsed,
            "tokens_in": tokens_in or None,
            "tokens_out": tokens_out or None,
            "stage1_model": item.get("stage1_model"),
            "stage2_model": item.get("stage2_model"),
            "render_build_number": item.get("render_build_number"),
            "render_engine_id": item.get("render_engine_id"),
            "render_engine_version": item.get("render_engine_version"),
            "render_canvas_aspect": item.get("render_canvas_aspect"),
            "render_canvas_aspect_id": item.get("render_canvas_aspect_id"),
            "render_canvas_aspect_ratio": item.get("render_canvas_aspect_ratio"),
            "render_color_catalog_id": item.get("render_color_catalog_id") or item.get("catalog_id"),
            "render_color_catalog_name": item.get("render_color_catalog_name"),
            **_score_metrics(item.get("score")),
        })
        artifact_paths = (item.get("_export_paths") or {}) if isinstance(item.get("_export_paths"), dict) else {}
        evaluation_items.append({
            "index": index,
            "label": artifact_paths.get("label") or f"{index:03d}-{_history_hash_label(item)}",
            "id": item.get("id"),
            "hash": item.get("render_hash"),
            "hash_short": _history_hash_label(item),
            "at": item.get("at"),
            "prompt": item.get("input"),
            "ddl": item.get("ddl"),
            "score": item.get("score"),
            "stage1_model": item.get("stage1_model"),
            "stage2_model": item.get("stage2_model"),
            "render_build_number": item.get("render_build_number"),
            "render_engine_id": item.get("render_engine_id"),
            "render_engine_version": item.get("render_engine_version"),
            "render_canvas_aspect": item.get("render_canvas_aspect"),
            "render_canvas_aspect_id": item.get("render_canvas_aspect_id"),
            "render_canvas_aspect_ratio": item.get("render_canvas_aspect_ratio"),
            "render_color_catalog_id": item.get("render_color_catalog_id") or item.get("catalog_id"),
            "render_color_catalog_name": item.get("render_color_catalog_name"),
            "paths": {key: artifact_paths.get(key) for key in ("json", "svg", "png") if artifact_paths.get(key)},
        })
    aggregate_primitive: Counter[str] = Counter()
    aggregate_color: Counter[str] = Counter()
    aggregate_density: Counter[str] = Counter()
    aggregate_fade: Counter[str] = Counter()
    for result in results:
        aggregate_primitive.update(result.get("score_primitive_counts") or {})
        aggregate_color.update(result.get("score_color_counts") or {})
        aggregate_density.update(result.get("score_density_counts") or {})
        aggregate_fade.update(result.get("score_fade_counts") or {})
    return {
        "total": len(items),
        "elapsed_total_ms": total_elapsed,
        "tokens_in": total_in or None,
        "tokens_out": total_out or None,
        "render_build_numbers": sorted({str(item.get("render_build_number")) for item in items if item.get("render_build_number") is not None}),
        "score_primitive_counts": dict(sorted(aggregate_primitive.items())),
        "score_color_counts": dict(sorted(aggregate_color.items())),
        "score_density_counts": dict(sorted(aggregate_density.items())),
        "score_fade_counts": dict(sorted(aggregate_fade.items())),
        "paths": paths,
        "ai_evaluation": {
            "contact_sheet": paths.get("contact_sheet"),
            "summary_json": paths.get("summary_json"),
            "item_json_dir": paths.get("items_dir"),
            "review_focus": [
                "Compare each contact-sheet image with its prompt, DDL, score, models, build, canvas, and color catalog metadata.",
                "Assess expression, clarity, fun, motion, color use, diversity, and regressions against the intended benchmark focus.",
            ],
            "items": evaluation_items,
        },
        "results": results,
    }

def _clear_history_export_items_dir(item_dir: Path) -> None:
    if not item_dir.exists():
        return
    for path in item_dir.iterdir():
        if path.is_file() and path.suffix.lower() in {".json", ".svg", ".png"}:
            path.unlink()

def _write_history_export(
    items: list[dict[str, Any]],
    *,
    out_dir: Path,
    columns: int,
    thumb_size: int,
) -> dict[str, Any]:
    try:
        import cairosvg
    except ImportError as exc:
        raise CliError("history-export requires cairosvg for contact-sheet PNGs") from exc

    out_dir.mkdir(parents=True, exist_ok=True)
    item_dir = out_dir / "items"
    item_dir.mkdir(parents=True, exist_ok=True)
    _clear_history_export_items_dir(item_dir)
    for index, item in enumerate(items, start=1):
        label = _history_hash_label(item) or str(index).zfill(4)
        prefix = item_dir / f"{index:03d}-{label}"
        export_item = dict(item)
        json_path = prefix.with_suffix(".json")
        svg_path = prefix.with_suffix(".svg")
        png_path = prefix.with_suffix(".png")
        export_paths = {
            "label": prefix.name,
            "json": str(json_path),
            "svg": str(svg_path),
            "png": str(png_path),
        }
        export_item["export_paths"] = export_paths
        _write_json_file(json_path, export_item)
        svg = str(item.get("svg") or "")
        svg_path.write_text(svg, encoding="utf-8")
        cairosvg.svg2png(bytestring=svg.encode("utf-8"), write_to=str(png_path))
        item["_export_paths"] = export_paths
    sheet_path = out_dir / "contact-sheet.png"
    _make_contact_sheet(item_dir, sheet_path, columns=columns, thumb_size=thumb_size)
    summary_path = out_dir / "summary.json"
    paths = {
        "out_dir": str(out_dir),
        "items_dir": str(item_dir),
        "contact_sheet": str(sheet_path),
        "summary_json": str(summary_path),
    }
    summary = _history_export_summary(items, paths)
    _write_json_file(summary_path, summary)
    return summary

def _coord_pair(value: Any) -> tuple[float, float] | None:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        return None
    x, y = value
    if not isinstance(x, (int, float)) or not isinstance(y, (int, float)):
        return None
    return float(x), float(y)

def _instruction_center(instruction: dict[str, Any]) -> tuple[float, float] | None:
    center = _coord_pair(instruction.get("center"))
    if center is not None:
        return center
    start = _coord_pair(instruction.get("from"))
    end = _coord_pair(instruction.get("to"))
    if start is not None and end is not None:
        return ((start[0] + end[0]) / 2, (start[1] + end[1]) / 2)
    position = _coord_pair(instruction.get("position"))
    size = _coord_pair(instruction.get("size"))
    if position is not None and size is not None:
        return (position[0] + size[0] / 2, position[1] + size[1] / 2)
    return None

def _near_any(value: float, targets: tuple[float, ...], *, tolerance: float = 0.035) -> bool:
    return any(abs(value - target) <= tolerance for target in targets)

def _math_balance_markers(instructions: list[dict[str, Any]]) -> dict[str, int]:
    centers: list[tuple[float, float]] = []
    radial_fibonacci_counts = 0
    for instruction in instructions:
        center = _instruction_center(instruction)
        if center is not None:
            centers.append(center)
        arrangement = instruction.get("arrangement")
        if not isinstance(arrangement, dict):
            continue
        if arrangement.get("layout") == "radial" and arrangement.get("count") in {5, 8, 13, 21}:
            radial_fibonacci_counts += 1
        arrangement_center = _coord_pair(arrangement.get("center"))
        if arrangement_center is not None:
            centers.append(arrangement_center)

    golden_like_centers = sum(
        1
        for x, y in centers
        if _near_any(x, (0.382, 0.618)) or _near_any(y, (0.382, 0.618))
    )
    rule_of_thirds_like_centers = sum(
        1
        for x, y in centers
        if _near_any(x, (1 / 3, 2 / 3)) or _near_any(y, (1 / 3, 2 / 3))
    )
    counterweight_like_opposite_placements = 0
    for index, (x1, y1) in enumerate(centers):
        for x2, y2 in centers[index + 1:]:
            if (
                (x1 - 0.5) * (x2 - 0.5) < 0
                and (y1 - 0.5) * (y2 - 0.5) < 0
                and abs(x1 - x2) >= 0.25
                and abs(y1 - y2) >= 0.25
            ):
                counterweight_like_opposite_placements += 1

    return {
        "radial_fibonacci_counts": radial_fibonacci_counts,
        "golden_like_centers": golden_like_centers,
        "rule_of_thirds_like_centers": rule_of_thirds_like_centers,
        "counterweight_like_opposite_placements": counterweight_like_opposite_placements,
    }

def _score_quality_metrics(score: dict[str, Any], instructions: list[dict[str, Any]]) -> dict[str, Any]:
    expanded_count = 0
    preserve_space = 0
    fade_count = 0
    color_cycle_count = 0
    path_motion = 0
    varied_rotation = 0
    diagonal_or_wave = 0
    rhythm_spacing_count = 0
    visual_event = 0
    visible_colors: set[str] = set()
    weight_values: set[str] = set()
    chromatic_accent_score = 0
    filled_large = 0
    bilateral_presence = 0
    gaze_presence = 0
    object_like_hints = 0
    fallback_hints = 0
    coverage_hints = 0
    centers: list[tuple[float, float]] = []

    background = score.get("background")
    background_contrast = 0
    if isinstance(background, str) and background in COLOR_KEYS:
        visible_colors.add(background)

    presence = score.get("presence")
    if isinstance(presence, dict):
        if presence.get("symmetry") == "bilateral":
            bilateral_presence += 1
        if presence.get("gaze_pressure") not in (None, "none"):
            gaze_presence += 1

    for instruction in instructions:
        center = _instruction_center(instruction)
        if center is not None:
            centers.append(center)
        color = instruction.get("color")
        if isinstance(color, str):
            visible_colors.add(color)
            if isinstance(background, str) and background in COLOR_KEYS and color != background:
                background_contrast = 1
        weight = instruction.get("weight")
        if isinstance(weight, str):
            weight_values.add(weight)
        if instruction.get("filled") is True:
            size = _coord_pair(instruction.get("size"))
            radius = instruction.get("radius")
            if size is not None and size[0] * size[1] >= 0.10:
                filled_large += 1
            elif isinstance(radius, (int, float)) and float(radius) >= 0.22:
                filled_large += 1
        rotation = instruction.get("rotation")
        if isinstance(rotation, (int, float)) and abs(float(rotation)) >= 8:
            varied_rotation += 1
        hint = instruction.get("color_hint")
        lower_hint = ""
        if isinstance(hint, str):
            lower_hint = hint.lower()
            if "fallback from ddl" in lower_hint:
                fallback_hints += 1
            if "coverage from ddl clause" in lower_hint:
                coverage_hints += 1
            if "顔" in hint or "人型" in hint or FIGURATIVE_HINT_RE.search(lower_hint):
                object_like_hints += 1
            if any(marker in lower_hint for marker in ("visual event", "accent", "collision", "jump", "反転", "衝突")):
                visual_event += 1

        arrangement = instruction.get("arrangement")
        if isinstance(arrangement, dict):
            count = arrangement.get("count")
            expanded_count += int(count) if isinstance(count, int) and count > 0 else 1
            if arrangement.get("preserve_space") is True:
                preserve_space += 1
            if arrangement.get("fade") not in (None, "none"):
                fade_count += 1
            color_cycle = arrangement.get("color_cycle")
            if isinstance(color_cycle, list) and color_cycle:
                color_cycle_count += 1
                visible_colors.update(item for item in color_cycle if isinstance(item, str))
            path = arrangement.get("path")
            if path not in (None, "none"):
                path_motion += 1
            if path in {"diagonal", "wave", "top_to_bottom", "left_to_right", "right_half"}:
                diagonal_or_wave += 1
            if arrangement.get("rhythm_spacing") not in (None, "none"):
                rhythm_spacing_count += 1
        else:
            expanded_count += 1

        if isinstance(color, str) and color in CHROMATIC_ACCENT_COLOR_KEYS:
            accent_terms = ("accent", "interruption", "focal", "point", "punctuation", "small", "中断", "アクセント", "焦点")
            is_compact = False
            size = _coord_pair(instruction.get("size"))
            radius = instruction.get("radius")
            if instruction.get("primitive") == "line":
                is_compact = True
            elif size is not None and size[0] * size[1] <= 0.035:
                is_compact = True
            elif isinstance(radius, (int, float)) and float(radius) <= 0.12:
                is_compact = True
            if is_compact and (any(term in lower_hint for term in accent_terms) or instruction.get("filled") is True):
                chromatic_accent_score += 24
                if center is not None and (abs(center[0] - 0.5) >= 0.12 or abs(center[1] - 0.5) >= 0.12):
                    chromatic_accent_score += 12

    off_center = sum(1 for x, y in centers if abs(x - 0.5) >= 0.12 or abs(y - 0.5) >= 0.12)
    counterweights = _math_balance_markers(instructions)["counterweight_like_opposite_placements"]
    instruction_count = len(instructions)
    fallback_used = fallback_hints > 0

    negative_space_pressure = min(100, preserve_space * 18 + fade_count * 8 + min(off_center, 4) * 8 + min(counterweights, 3) * 8)
    motion_energy = min(100, path_motion * 18 + diagonal_or_wave * 12 + varied_rotation * 8 + rhythm_spacing_count * 10)
    color_resonance = min(100, max(0, len(visible_colors) - 1) * 18 + color_cycle_count * 14 + background_contrast * 18)
    if visible_colors and visible_colors <= {"white", "black", "gray"}:
        achromatic_tonal_resonance = min(
            100,
            18
            + max(0, len(visible_colors) - 1) * 18
            + preserve_space * 8
            + fade_count * 6
            + min(off_center, 3) * 6
            + min(varied_rotation, 3) * 4
            + min(len(weight_values), 3) * 6,
        )
        color_resonance = max(color_resonance, achromatic_tonal_resonance)
    if visible_colors & CHROMATIC_ACCENT_COLOR_KEYS and visible_colors - CHROMATIC_ACCENT_COLOR_KEYS <= ACHROMATIC_COLOR_KEYS:
        isolated_accent_resonance = min(
            100,
            max(0, len(visible_colors & ACHROMATIC_COLOR_KEYS)) * 12
            + min(chromatic_accent_score, 48)
            + min(off_center, 3) * 6
            + min(preserve_space, 2) * 6,
        )
        color_resonance = max(color_resonance, isolated_accent_resonance)
    visual_event_score = min(100, visual_event * 28 + min(off_center, 3) * 8 + min(counterweights, 2) * 14 + (12 if color_cycle_count else 0))
    figurative_risk = min(100, bilateral_presence * 22 + gaze_presence * 18 + object_like_hints * 25 + filled_large * 10)
    fallback_quality = None
    if fallback_used:
        fallback_quality = min(100, coverage_hints * 18 + min(len(visible_colors), 3) * 12 + min(instruction_count, 5) * 8 + preserve_space * 8)
    constraint_adherence = max(0, 100 - max(0, instruction_count - 5) * 10 - max(0, expanded_count - 160) // 4 - filled_large * 8)

    return {
        "constraint_adherence": int(constraint_adherence),
        "negative_space_pressure": int(negative_space_pressure),
        "motion_energy": int(motion_energy),
        "color_resonance": int(color_resonance),
        "visual_event": int(visual_event_score),
        "figurative_risk": int(figurative_risk),
        "fallback_quality": int(fallback_quality) if fallback_quality is not None else None,
    }

def _score_metrics(score: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(score, dict):
        return {}
    instructions = score.get("instructions")
    if not isinstance(instructions, list):
        return {}

    primitive_counts: Counter[str] = Counter()
    color_counts: Counter[str] = Counter()
    motif_hint_counts: Counter[str] = Counter()
    density_counts: Counter[str] = Counter()
    fade_counts: Counter[str] = Counter()
    arrangement_count = 0
    expanded_count = 0
    clustered_arrangements = 0
    preserve_space_count = 0
    color_cycle_count = 0
    presence_counts: Counter[str] = Counter()
    presence_gaze_counts: Counter[str] = Counter()
    relation_counts: Counter[str] = Counter()
    relation_instruction_count = 0
    repair_part_counts: Counter[str] = Counter()

    presence = score.get("presence")
    if isinstance(presence, dict):
        kind = presence.get("kind")
        if isinstance(kind, str) and kind != "none":
            presence_counts[kind] += 1
        gaze = presence.get("gaze_pressure")
        if isinstance(gaze, str) and gaze != "none":
            presence_gaze_counts[gaze] += 1

    for instruction in instructions:
        if not isinstance(instruction, dict):
            continue
        primitive = instruction.get("primitive")
        color = instruction.get("color")
        if isinstance(primitive, str):
            primitive_counts[primitive] += 1
        if isinstance(color, str):
            color_counts[color] += 1
        hint = instruction.get("color_hint")
        if isinstance(hint, str):
            hint_lower = hint.lower()
            for motif in MOTIF_HINT_KEYS:
                if motif in hint:
                    motif_hint_counts[motif] += 1
            for key, marker in SCORE_REPAIR_PART_MARKERS:
                if marker in hint_lower:
                    repair_part_counts[key] += 1

        relation = instruction.get("relation")
        if isinstance(relation, dict) and isinstance(relation.get("type"), str):
            relation_counts[relation["type"]] += 1
            relation_instruction_count += 1

        arrangement = instruction.get("arrangement")
        if not isinstance(arrangement, dict):
            expanded_count += 1
            continue

        arrangement_count += 1
        count = arrangement.get("count")
        expanded_count += int(count) if isinstance(count, int) and count > 0 else 1
        density = arrangement.get("density")
        fade = arrangement.get("fade")
        if isinstance(density, str) and density != "none":
            density_counts[density] += 1
        if isinstance(fade, str) and fade != "none":
            fade_counts[fade] += 1
        if isinstance(arrangement.get("cluster_count"), int):
            clustered_arrangements += 1
        if arrangement.get("preserve_space") is True:
            preserve_space_count += 1
        color_cycle = arrangement.get("color_cycle")
        if isinstance(color_cycle, list) and color_cycle:
            color_cycle_count += 1

    quality_metrics = _score_quality_metrics(
        score,
        [instruction for instruction in instructions if isinstance(instruction, dict)],
    )
    return {
        "score_instruction_count": len(instructions),
        "score_arrangement_count": arrangement_count,
        "score_expanded_count": expanded_count,
        "score_clustered_arrangements": clustered_arrangements,
        "score_preserve_space_count": preserve_space_count,
        "score_color_cycle_count": color_cycle_count,
        "score_density_counts": dict(sorted(density_counts.items())),
        "score_fade_counts": dict(sorted(fade_counts.items())),
        "score_primitive_counts": dict(sorted(primitive_counts.items())),
        "score_color_counts": dict(sorted(color_counts.items())),
        "score_motif_hint_counts": dict(sorted(motif_hint_counts.items())),
        "score_repair_part_counts": dict(sorted(repair_part_counts.items())),
        "score_has_repair_part": bool(repair_part_counts),
        "score_presence_counts": dict(sorted(presence_counts.items())),
        "score_presence_gaze_counts": dict(sorted(presence_gaze_counts.items())),
        "score_relation_counts": dict(sorted(relation_counts.items())),
        "score_relation_instruction_count": relation_instruction_count,
        "score_has_relation": relation_instruction_count > 0,
        "score_quality_metrics": quality_metrics,
        "math_balance_markers": _math_balance_markers([
            instruction for instruction in instructions if isinstance(instruction, dict)
        ]),
    }

def _marker_colors(text: str | None) -> list[str]:
    if not text:
        return []
    lower = text.lower()
    found = [
        color
        for color, markers in COLOR_MARKERS.items()
        if any(_marker_in_text(marker, text, lower) for marker in markers)
    ]
    return sorted(found)

def _negated_marker_colors(text: str | None) -> list[str]:
    if not text:
        return []
    lower = text.lower()
    found = [
        color
        for color, markers in NEGATED_COLOR_MARKERS.items()
        if any(_marker_in_text(marker, text, lower) for marker in markers)
    ]
    return sorted(found)

def _score_color_details(score: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(score, dict):
        return {"score_colors": [], "score_color_cycle_colors": [], "score_color_hints": []}
    instructions = score.get("instructions")
    if not isinstance(instructions, list):
        return {"score_colors": [], "score_color_cycle_colors": [], "score_color_hints": []}

    colors: Counter[str] = Counter()
    cycle_colors: Counter[str] = Counter()
    hints: list[str] = []
    for instruction in instructions:
        if not isinstance(instruction, dict):
            continue
        color = instruction.get("color")
        if isinstance(color, str):
            colors[color] += 1
        hint = instruction.get("color_hint")
        if isinstance(hint, str) and hint:
            hints.append(hint)
        arrangement = instruction.get("arrangement")
        if isinstance(arrangement, dict):
            color_cycle = arrangement.get("color_cycle")
            if isinstance(color_cycle, list):
                for item in color_cycle:
                    if isinstance(item, str):
                        cycle_colors[item] += 1
    return {
        "score_colors": dict(sorted(colors.items())),
        "score_color_cycle_colors": dict(sorted(cycle_colors.items())),
        "score_color_hints": hints[:20],
    }

def _color_trace(
    result: dict[str, Any],
    *,
    catalog_id: str,
    catalog_data: dict[str, Any] | None = None,
    requested_text: str | None = None,
) -> dict[str, Any]:
    text = requested_text or result.get("text")
    ddl = result.get("ddl")
    score = result.get("score")
    details = _score_color_details(score)
    score_colors = set(details["score_colors"])
    cycle_colors = set(details["score_color_cycle_colors"])
    score_or_cycle = score_colors | cycle_colors
    negated_colors = sorted(set(_negated_marker_colors(text)) | set(_negated_marker_colors(ddl)))
    requested_colors = sorted((set(_marker_colors(text)) | set(_marker_colors(ddl))) - set(negated_colors))
    missing = [color for color in requested_colors if color in COLOR_KEYS and color not in score_or_cycle]
    green_requested = "green" in requested_colors
    green_in_score = "green" in score_or_cycle
    warnings: list[str] = []
    if missing:
        warnings.append("requested_color_missing_in_score")
    if green_requested and not green_in_score:
        warnings.append("green_requested_but_missing_in_score")
    catalog = _catalog_by_id(catalog_data, catalog_id) if catalog_data else None
    return {
        "requested_color_catalog": catalog_id,
        "resolved_color_catalog": catalog.get("id", catalog_id) if catalog else catalog_id,
        "resolved_palette": _render_color_map(catalog) if catalog else {},
        "text_color_markers": _marker_colors(text),
        "ddl_color_markers": _marker_colors(ddl),
        "negated_color_markers": negated_colors,
        "requested_colors": requested_colors,
        **details,
        "missing_requested_colors": missing,
        "green_requested": green_requested,
        "green_in_score": green_in_score,
        "green_rendered": green_in_score,
        "warnings": warnings,
    }

def _aggregate_color_traces(traces: list[dict[str, Any]]) -> dict[str, Any]:
    requested: Counter[str] = Counter()
    in_score: Counter[str] = Counter()
    missing: Counter[str] = Counter()
    warnings: Counter[str] = Counter()
    negated: Counter[str] = Counter()
    green_requested = 0
    green_in_score = 0
    for trace in traces:
        requested.update(trace.get("requested_colors") or [])
        in_score.update((trace.get("score_colors") or {}).keys())
        in_score.update((trace.get("score_color_cycle_colors") or {}).keys())
        missing.update(trace.get("missing_requested_colors") or [])
        warnings.update(trace.get("warnings") or [])
        negated.update(trace.get("negated_color_markers") or [])
        if trace.get("green_requested"):
            green_requested += 1
        if trace.get("green_in_score"):
            green_in_score += 1
    return {
        "requested_color_counts": dict(sorted(requested.items())),
        "score_color_presence_counts": dict(sorted(in_score.items())),
        "missing_requested_color_counts": dict(sorted(missing.items())),
        "warning_counts": dict(sorted(warnings.items())),
        "negated_color_counts": dict(sorted(negated.items())),
        "green_requested_samples": green_requested,
        "green_in_score_samples": green_in_score,
        "green_delivery_rate": (green_in_score / green_requested) if green_requested else None,
    }

def _aggregate_marker_lines(results: list[dict[str, Any]], key: str) -> dict[str, list[int]]:
    lines: dict[str, list[int]] = {}
    for result in results:
        line = int(result.get("line") or 0)
        if not line:
            continue
        markers = result.get(key)
        if not isinstance(markers, dict):
            continue
        for marker, count in markers.items():
            if isinstance(marker, str) and int(count or 0) > 0:
                lines.setdefault(marker, []).append(line)
    return dict(sorted(lines.items()))

def _aggregate_quality_metrics(results: list[dict[str, Any]]) -> dict[str, Any]:
    values: dict[str, list[int]] = {}
    fallback_values: list[int] = []
    for result in results:
        metrics = result.get("score_quality_metrics")
        if not isinstance(metrics, dict):
            continue
        for key, value in metrics.items():
            if key == "fallback_quality":
                if isinstance(value, int):
                    fallback_values.append(value)
                continue
            if isinstance(value, int):
                values.setdefault(key, []).append(value)
    averages = {
        key: round(sum(items) / len(items), 1)
        for key, items in sorted(values.items())
        if items
    }
    lows = {
        key: min(items)
        for key, items in sorted(values.items())
        if items
    }
    highs = {
        key: max(items)
        for key, items in sorted(values.items())
        if items
    }
    return {
        "average": averages,
        "min": lows,
        "max": highs,
        "fallback_quality_average": round(sum(fallback_values) / len(fallback_values), 1) if fallback_values else None,
        "fallback_quality_samples": len(fallback_values),
    }

def _paint_payload(
    args: argparse.Namespace,
    text: str,
    *,
    stage1_model: str | None = None,
    stage2_model: str | None = None,
    color_catalog: str | None = None,
) -> dict[str, Any]:
    color_catalog = (
        color_catalog
        or getattr(args, "color_catalog", None)
        or getattr(args, "catalog_id", None)
        or DEFAULT_COLOR_CATALOG_ID
    )
    payload: dict[str, Any] = {
        "text": text,
        "original_text": args.original_text,
        "stage1_model": stage1_model if stage1_model is not None else args.stage1_model,
        "stage2_model": stage2_model if stage2_model is not None else args.stage2_model,
        "include_thinking": args.include_thinking,
        "instruction_lang": args.instruction_lang,
        "ui_lang": args.ui_lang,
        "save_history": args.save_history,
        "save_artifacts": args.save_artifacts,
        "history_input": args.history_input,
        "catalog_id": color_catalog,
        "canvas_aspect": getattr(args, "canvas_aspect", None),
        "render_seed": getattr(args, "render_seed", None),
        "vary_seed": getattr(args, "vary_seed", None),
        "seed_text": getattr(args, "seed_text", None),
    }
    return {k: v for k, v in payload.items() if v is not None}

def _compose_payload(
    args: argparse.Namespace,
    ddl: str,
    *,
    stage2_model: str | None = None,
    color_catalog: str | None = None,
) -> dict[str, Any]:
    color_catalog = (
        color_catalog
        or getattr(args, "color_catalog", None)
        or getattr(args, "catalog_id", None)
        or DEFAULT_COLOR_CATALOG_ID
    )
    payload: dict[str, Any] = {
        "ddl": ddl,
        "model": stage2_model if stage2_model is not None else args.stage2_model,
        "original_text": args.original_text,
        "instruction_lang": args.instruction_lang,
        "ui_lang": args.ui_lang,
        "catalog_id": color_catalog,
        "canvas_aspect": getattr(args, "canvas_aspect", None),
        "auto_repair": True,
        "render_seed": getattr(args, "render_seed", None),
        "vary_seed": getattr(args, "vary_seed", None),
    }
    return {k: v for k, v in payload.items() if v is not None}

def _compose_response_as_paint_result(
    result: dict[str, Any],
    *,
    ddl: str,
    input_text: str,
    stage2_model: str | None,
    elapsed_total_ms: int | None = None,
) -> dict[str, Any]:
    elapsed = int(elapsed_total_ms if elapsed_total_ms is not None else result.get("elapsed_ms") or 0)
    effective_ddl = str(result.get("ddl") or ddl)
    return {
        "text": input_text,
        "ddl": effective_ddl,
        "score": result.get("score"),
        "svg": result.get("svg"),
        "stage1_model": None,
        "stage2_model": result.get("stage2_model") or stage2_model,
        "render_build_number": result.get("render_build_number"),
        "render_color_profile": result.get("render_color_profile"),
        "render_engine_id": result.get("render_engine_id"),
        "render_engine_version": result.get("render_engine_version"),
        "render_color_catalog_id": result.get("render_color_catalog_id"),
        "render_color_catalog_name": result.get("render_color_catalog_name"),
        "render_color_catalog_sub": result.get("render_color_catalog_sub"),
        "render_color_map": result.get("render_color_map"),
        "render_canvas_aspect": result.get("render_canvas_aspect"),
        "render_canvas_aspect_id": result.get("render_canvas_aspect_id"),
        "render_canvas_aspect_ratio": result.get("render_canvas_aspect_ratio"),
        "render_hash": result.get("render_hash"),
        "render_hash_short": result.get("render_hash_short"),
        "elapsed_stage1_ms": 0,
        "elapsed_stage2_ms": int(result.get("elapsed_ms") or elapsed),
        "elapsed_total_ms": elapsed,
        "tokens_in_stage1": None,
        "tokens_out_stage1": None,
        "tokens_in_stage2": result.get("tokens_in"),
        "tokens_out_stage2": result.get("tokens_out"),
        "interpret_fallback_used": False,
        "interpret_fallback_reasons": [],
        "compose_retry_count": result.get("retry_count", 0),
        "compose_retry_reasons": result.get("retry_reasons", []),
        "compose_fallback_used": result.get("fallback_used", False),
        "catalog_id": result.get("render_color_catalog_id"),
    }

def _history_payload_from_result(
    args: argparse.Namespace,
    result: dict[str, Any],
    *,
    input_text: str,
    ddl: str,
    stage1_model: str | None,
    stage2_model: str | None,
    color_catalog: str,
    at: int | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "input": args.history_input or input_text,
        "ddl": ddl,
        "score": result.get("score") or {},
        "svg": result.get("svg") or "",
        "at": at or int(time.time() * 1000),
        "elapsed_ms": int(result.get("elapsed_total_ms") or result.get("elapsed_ms") or 0),
        "stage1_model": stage1_model,
        "stage2_model": stage2_model,
        "tokens_in": (result.get("tokens_in_stage1") or 0) + (result.get("tokens_in_stage2") or 0) or None,
        "tokens_out": (result.get("tokens_out_stage1") or 0) + (result.get("tokens_out_stage2") or 0) or None,
        "catalog_id": color_catalog,
        "render_build_number": result.get("render_build_number"),
        "render_color_profile": result.get("render_color_profile"),
        "render_engine_id": result.get("render_engine_id"),
        "render_engine_version": result.get("render_engine_version"),
        "render_color_catalog_id": result.get("render_color_catalog_id"),
        "render_color_catalog_name": result.get("render_color_catalog_name"),
        "render_color_catalog_sub": result.get("render_color_catalog_sub"),
        "render_color_map": result.get("render_color_map"),
        "render_canvas_aspect": result.get("render_canvas_aspect"),
        "render_canvas_aspect_id": result.get("render_canvas_aspect_id"),
        "render_canvas_aspect_ratio": result.get("render_canvas_aspect_ratio"),
        "canvas_aspect": getattr(args, "canvas_aspect", None),
        "save_artifacts": args.save_artifacts if args.save_artifacts is not None else args.save_history,
        "count_generation": True,
    }
    return {k: v for k, v in payload.items() if v is not None}

def _save_history_for_result(
    client: ApiClient,
    args: argparse.Namespace,
    result: dict[str, Any],
    *,
    input_text: str,
    ddl: str,
    stage1_model: str | None,
    stage2_model: str | None,
    color_catalog: str,
) -> dict[str, Any]:
    item, _ = client.request(
        "POST",
        "/api/history",
        data=_history_payload_from_result(
            args,
            result,
            input_text=input_text,
            ddl=ddl,
            stage1_model=stage1_model,
            stage2_model=stage2_model,
            color_catalog=color_catalog,
        ),
    )
    updated = dict(result)
    updated["history_id"] = item.get("id")
    updated["history_at"] = item.get("at")
    updated["user_generation_count"] = item.get("user_generation_count")
    for key in (
        "render_hash",
        "render_hash_short",
        "render_color_catalog_id",
        "render_color_catalog_name",
        "render_color_catalog_sub",
        "render_color_map",
        "render_canvas_aspect",
        "render_canvas_aspect_id",
        "render_canvas_aspect_ratio",
    ):
        if item.get(key) is not None:
            updated[key] = item.get(key)
    return updated

def command_login(args: argparse.Namespace) -> int:
    password = args.password or getpass.getpass("Password: ")
    existing = load_config()
    base_url = args.base_url or existing.base_url
    timeout_seconds = _resolved_timeout_seconds(args, existing)
    client = ApiClient(base_url, timeout_seconds=timeout_seconds)
    data, response = client.request(
        "POST",
        "/api/auth/login",
        data={"username": args.username, "password": password},
        auth=False,
    )
    token = _extract_session_token(response.headers.get("set-cookie"))
    if not token:
        raise CliError("login succeeded but session cookie was not returned")
    username = data.get("user", {}).get("username") or args.username
    save_config(CliConfig(
        base_url=base_url,
        token=token,
        username=username,
        stage1_provider=existing.stage1_provider,
        stage1_model=existing.stage1_model,
        stage2_provider=existing.stage2_provider,
        stage2_model=existing.stage2_model,
        timeout_seconds=timeout_seconds,
        color_catalog=existing.color_catalog,
    ))
    print(f"logged in as {username}")
    return 0

def command_logout(args: argparse.Namespace) -> int:
    config = load_config()
    if config.token:
        client = ApiClient(
            args.base_url or config.base_url,
            config.token,
            timeout_seconds=_resolved_timeout_seconds(args, config),
        )
        try:
            client.request("POST", "/api/auth/logout")
        except CliError:
            pass
    clear_config()
    print("logged out")
    return 0

def command_me(args: argparse.Namespace) -> int:
    config = load_config()
    client = ApiClient(
        args.base_url or config.base_url,
        config.token,
        timeout_seconds=_resolved_timeout_seconds(args, config),
    )
    data, _ = client.request("GET", "/api/auth/me")
    _print_json(data)
    return 0

def command_models(args: argparse.Namespace) -> int:
    config = load_config()
    timeout_seconds = _resolved_timeout_seconds(args, config)
    client = ApiClient(args.base_url or config.base_url, config.token, timeout_seconds=timeout_seconds)
    catalog_data = _fetch_color_catalogs(client)
    if (
        args.stage1_provider is not None
        or args.stage1_model is not None
        or args.stage2_provider is not None
        or args.stage2_model is not None
        or args.timeout_seconds is not None
        or args.color_catalog is not None
    ):
        color_catalog = args.color_catalog if args.color_catalog is not None else config.color_catalog
        if color_catalog is not None:
            _catalog_by_id(catalog_data, color_catalog)
        config = CliConfig(
            base_url=args.base_url or config.base_url,
            token=config.token,
            username=config.username,
            stage1_provider=args.stage1_provider if args.stage1_provider is not None else config.stage1_provider,
            stage1_model=args.stage1_model if args.stage1_model is not None else config.stage1_model,
            stage2_provider=args.stage2_provider if args.stage2_provider is not None else config.stage2_provider,
            stage2_model=args.stage2_model if args.stage2_model is not None else config.stage2_model,
            timeout_seconds=timeout_seconds,
            color_catalog=color_catalog,
        )
        save_config(config)
    data = {
        "base_url": args.base_url or config.base_url,
        "username": config.username,
        "timeout_seconds": config.timeout_seconds or DEFAULT_REQUEST_TIMEOUT_SECONDS,
        "color_catalog": config.color_catalog or catalog_data["default_catalog_id"],
        "available_color_catalogs": list(_catalog_choices(catalog_data)),
        **_model_summary(
            config.stage1_model,
            config.stage2_model,
            stage1_provider=config.stage1_provider,
            stage2_provider=config.stage2_provider,
        ),
    }
    _print_json(data)
    return 0

def command_paint(args: argparse.Namespace) -> int:
    config = load_config()
    timeout_seconds = _resolved_timeout_seconds(args, config)
    client = ApiClient(args.base_url or config.base_url, config.token, timeout_seconds=timeout_seconds)
    text = _read_text_argument(args.text, args.file)
    started = int(time.time() * 1000)
    stage1_provider = _resolved_stage1_provider(args, config)
    stage1_model = _resolved_stage1_model(args, config)
    stage2_provider = _resolved_stage2_provider(args, config)
    stage2_model = _resolved_stage2_model(args, config)
    catalog_data = _fetch_color_catalogs(client)
    color_catalog = _resolved_color_catalog(args, config, catalog_data)
    _print_model_summary(
        stage1_model,
        stage2_model,
        stage1_provider=stage1_provider,
        stage2_provider=stage2_provider,
    )
    _print_color_catalog_summary(color_catalog, catalog_data)
    input_mode = getattr(args, "input_mode", "paint")
    if input_mode == "ddl":
        input_text = args.original_text or text
        raw_result, _ = _run_with_progress(
            "drawing from DDL",
            lambda: client.request("POST", "/api/compose", data=_compose_payload(
                args,
                text,
                stage2_model=stage2_model,
                color_catalog=color_catalog,
            )),
            enabled=not args.no_progress,
        )
        result = _compose_response_as_paint_result(
            raw_result,
            ddl=text,
            input_text=input_text,
            stage2_model=stage2_model,
        )
        if args.save_history:
            result = _save_history_for_result(
                client,
                args,
                result,
                input_text=input_text,
                ddl=str(result.get("ddl") or text),
                stage1_model=None,
                stage2_model=stage2_model,
                color_catalog=color_catalog,
            )
    else:
        result, _ = _run_with_progress(
            "drawing",
            lambda: client.request("POST", "/api/paint", data=_paint_payload(
                args,
                text,
                stage1_model=stage1_model,
                stage2_model=stage2_model,
                color_catalog=color_catalog,
            )),
            enabled=not args.no_progress,
        )
    prefix = args.prefix or f"inku-{started}"
    output_result = _result_with_svg_profile(client, result, svg_profile=args.svg_profile, color_catalog=color_catalog)
    paths = _write_paint_outputs(output_result, out_dir=Path(args.out_dir) if args.out_dir else None, prefix=prefix, png=args.png)
    summary = {
        "text": result.get("text"),
        "input_mode": input_mode,
        **_model_summary(
            None if input_mode == "ddl" else stage1_model,
            stage2_model,
            stage1_provider=None if input_mode == "ddl" else stage1_provider,
            stage2_provider=stage2_provider,
        ),
        "timeout_seconds": timeout_seconds,
        "svg_profile": args.svg_profile,
        **_color_catalog_summary(color_catalog, catalog_data),
        **_render_response_summary(result),
        "color_trace": _color_trace(result, catalog_id=color_catalog, catalog_data=catalog_data, requested_text=text),
        "history_id": result.get("history_id"),
        "elapsed_total_ms": result.get("elapsed_total_ms"),
        "tokens_in": (result.get("tokens_in_stage1") or 0) + (result.get("tokens_in_stage2") or 0) or None,
        "tokens_out": (result.get("tokens_out_stage1") or 0) + (result.get("tokens_out_stage2") or 0) or None,
        "interpret_fallback_used": result.get("interpret_fallback_used", False),
        "interpret_fallback_reasons": result.get("interpret_fallback_reasons", []),
        "compose_retry_count": result.get("compose_retry_count", 0),
        "compose_retry_reasons": result.get("compose_retry_reasons", []),
        "compose_fallback_used": result.get("compose_fallback_used", False),
        **_score_metrics(result.get("score")),
        "paths": paths,
    }
    if args.full_json:
        _print_json({
            **output_result,
            "input_mode": input_mode,
            **_model_summary(
                None if input_mode == "ddl" else stage1_model,
                stage2_model,
                stage1_provider=None if input_mode == "ddl" else stage1_provider,
                stage2_provider=stage2_provider,
            ),
            "timeout_seconds": timeout_seconds,
            **_color_catalog_summary(color_catalog, catalog_data),
            **_render_response_summary(result),
            "color_trace": _color_trace(result, catalog_id=color_catalog, catalog_data=catalog_data, requested_text=text),
            "paths": paths,
        })
    else:
        _print_json(summary)
    return 0

def _http_502_count(failures: list[dict[str, Any]]) -> int:
    return sum(str(item.get("message") or "").count("HTTP 502") for item in failures)

def command_batch(args: argparse.Namespace) -> int:
    config = load_config()
    timeout_seconds = _resolved_timeout_seconds(args, config)
    client = ApiClient(args.base_url or config.base_url, config.token, timeout_seconds=timeout_seconds)
    raw = _read_text_argument(None, args.file)
    lines = [line.strip() for line in raw.splitlines() if line.strip()]
    if not lines:
        raise CliError("batch input contains no non-empty lines")
    out_dir = Path(args.out_dir) if args.out_dir else None
    results: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    total_in = 0
    total_out = 0
    total_elapsed = 0
    stage1_provider = _resolved_stage1_provider(args, config)
    stage1_model = _resolved_stage1_model(args, config)
    stage2_provider = _resolved_stage2_provider(args, config)
    stage2_model = _resolved_stage2_model(args, config)
    catalog_data = _fetch_color_catalogs(client)
    color_catalog = _resolved_color_catalog(args, config, catalog_data)
    _print_model_summary(
        stage1_model,
        stage2_model,
        stage1_provider=stage1_provider,
        stage2_provider=stage2_provider,
    )
    _print_color_catalog_summary(color_catalog, catalog_data)
    input_mode = getattr(args, "input_mode", "paint")
    vary_count = max(1, int(getattr(args, "vary", 1) or 1))
    pending_timeout_retries: list[tuple[int, str, int | None]] = []
    result_index_by_line: dict[tuple[int, int | None], int] = {}

    def process_line(index: int, line: str, *, retry_timeout: bool = False) -> dict[str, Any]:
        progress_label = (
            f"retrying timeout {index}/{len(lines)}"
            if retry_timeout
            else f"drawing {index}/{len(lines)}"
        )
        if input_mode == "ddl":
            input_text = args.original_text or line
            raw_result, _ = _run_with_progress(
                f"{progress_label} from DDL",
                lambda line=line: client.request("POST", "/api/compose", data=_compose_payload(
                    args,
                    line,
                    stage2_model=stage2_model,
                    color_catalog=color_catalog,
                )),
                enabled=not args.no_progress,
            )
            result = _compose_response_as_paint_result(
                raw_result,
                ddl=line,
                input_text=input_text,
                stage2_model=stage2_model,
            )
            if args.save_history:
                result = _save_history_for_result(
                    client,
                    args,
                    result,
                    input_text=input_text,
                    ddl=str(result.get("ddl") or line),
                    stage1_model=None,
                    stage2_model=stage2_model,
                    color_catalog=color_catalog,
                )
        else:
            result, _ = _run_with_progress(
                progress_label,
                lambda line=line: client.request("POST", "/api/paint", data=_paint_payload(
                    args,
                    line,
                    stage1_model=stage1_model,
                    stage2_model=stage2_model,
                    color_catalog=color_catalog,
                )),
                enabled=not args.no_progress,
            )
        current_vary_seed = getattr(args, "vary_seed", None)
        if vary_count > 1:
            prefix = f"{args.prefix}-{index:03d}-v{current_vary_seed}" if args.prefix else f"inku-batch-{index:03d}-v{current_vary_seed}"
        else:
            prefix = f"{args.prefix}-{index:03d}" if args.prefix else f"inku-batch-{index:03d}"
        output_result = _result_with_svg_profile(client, result, svg_profile=args.svg_profile, color_catalog=color_catalog)
        paths = _write_paint_outputs(output_result, out_dir=out_dir, prefix=prefix, png=args.png)
        tokens_in = (result.get("tokens_in_stage1") or 0) + (result.get("tokens_in_stage2") or 0)
        tokens_out = (result.get("tokens_out_stage1") or 0) + (result.get("tokens_out_stage2") or 0)
        elapsed = int(result.get("elapsed_total_ms") or 0)
        entry = {
            "line": index,
            "text": result.get("text"),
            "input_mode": input_mode,
            **_model_summary(
                None if input_mode == "ddl" else stage1_model,
                stage2_model,
                stage1_provider=None if input_mode == "ddl" else stage1_provider,
                stage2_provider=stage2_provider,
            ),
            "timeout_seconds": timeout_seconds,
            **_color_catalog_summary(color_catalog, catalog_data),
            **_render_response_summary(result),
            "color_trace": _color_trace(result, catalog_id=color_catalog, catalog_data=catalog_data, requested_text=line),
            "history_id": result.get("history_id"),
            "svg_profile": args.svg_profile,
            "vary_seed": result.get("vary_seed"),
            "elapsed_total_ms": elapsed,
            "tokens_in": tokens_in or None,
            "tokens_out": tokens_out or None,
            "interpret_fallback_used": result.get("interpret_fallback_used", False),
            "interpret_fallback_reasons": result.get("interpret_fallback_reasons", []),
            "compose_retry_count": result.get("compose_retry_count", 0),
            "compose_retry_reasons": result.get("compose_retry_reasons", []),
            "compose_fallback_used": result.get("compose_fallback_used", False),
            **_score_metrics(result.get("score")),
            "paths": paths,
        }
        timeout_reasons = _server_timeout_reasons(entry)
        if timeout_reasons:
            entry["server_timeout_reasons"] = timeout_reasons
            entry["server_timeout_retry_attempted"] = retry_timeout
        return entry

    work_items = [(index, line, vary_index if vary_count > 1 else getattr(args, "vary_seed", None)) for index, line in enumerate(lines, start=1) for vary_index in range(vary_count)]
    for ordinal, (index, line, vary_seed) in enumerate(work_items, start=1):
        previous_vary_seed = getattr(args, "vary_seed", None)
        args.vary_seed = vary_seed
        try:
            entry = process_line(index, line)
            key = (index, vary_seed)
            result_index_by_line[key] = len(results)
            results.append(entry)
            timeout_reasons = entry.get("server_timeout_reasons") or []
            if timeout_reasons:
                pending_timeout_retries.append((index, line, vary_seed))
                print(
                    f"{ordinal}/{len(work_items)} server timeout ({', '.join(timeout_reasons)}); queued final retry",
                    file=sys.stderr,
                )
            print(f"{ordinal}/{len(work_items)} ok line {index} {entry['elapsed_total_ms']}ms", file=sys.stderr)
        except CliError as exc:
            failures.append({"line": index, "text": line, "vary_seed": vary_seed, "message": str(exc)})
            print(f"{ordinal}/{len(work_items)} failed line {index}: {exc}", file=sys.stderr)
            if not args.continue_on_error:
                args.vary_seed = previous_vary_seed
                break
        finally:
            args.vary_seed = previous_vary_seed
    if pending_timeout_retries:
        print(f"server timeout final retry: {len(pending_timeout_retries)} item(s)", file=sys.stderr)
    for index, line, vary_seed in pending_timeout_retries:
        previous_vary_seed = getattr(args, "vary_seed", None)
        args.vary_seed = vary_seed
        try:
            retry_entry = process_line(index, line, retry_timeout=True)
            original_result_index = result_index_by_line.get((index, vary_seed))
            if original_result_index is not None:
                results[original_result_index] = retry_entry
            else:
                results.append(retry_entry)
            timeout_reasons = retry_entry.get("server_timeout_reasons") or []
            if timeout_reasons:
                print(
                    f"{index}/{len(lines)} final retry still server timeout ({', '.join(timeout_reasons)}); using fallback result",
                    file=sys.stderr,
                )
            else:
                print(f"{index}/{len(lines)} final retry ok {retry_entry['elapsed_total_ms']}ms", file=sys.stderr)
        except CliError as exc:
            failures.append({"line": index, "text": line, "vary_seed": vary_seed, "message": f"final retry failed: {exc}"})
            print(f"{index}/{len(lines)} final retry failed: {exc}", file=sys.stderr)
        finally:
            args.vary_seed = previous_vary_seed

    total_in = sum(int(result.get("tokens_in") or 0) for result in results)
    total_out = sum(int(result.get("tokens_out") or 0) for result in results)
    total_elapsed = sum(int(result.get("elapsed_total_ms") or 0) for result in results)
    aggregate_density: Counter[str] = Counter()
    aggregate_fade: Counter[str] = Counter()
    aggregate_primitive: Counter[str] = Counter()
    aggregate_color: Counter[str] = Counter()
    aggregate_motif_hints: Counter[str] = Counter()
    aggregate_repair_parts: Counter[str] = Counter()
    aggregate_repair_part_samples: Counter[str] = Counter()
    aggregate_presence: Counter[str] = Counter()
    aggregate_presence_gaze: Counter[str] = Counter()
    aggregate_relation: Counter[str] = Counter()
    aggregate_relation_samples = 0
    aggregate_relation_instructions = 0
    aggregate_coerce_relation_input = 0
    aggregate_coerce_relation_output = 0
    aggregate_coerce_relation_dropped = 0
    aggregate_coerce_branches: Counter[str] = Counter()
    aggregate_coerce_branch_samples: Counter[str] = Counter()
    aggregate_clustered = 0
    aggregate_preserve_space = 0
    aggregate_color_cycle = 0
    aggregate_expanded = 0
    aggregate_math_balance: Counter[str] = Counter()
    color_traces: list[dict[str, Any]] = []
    for result in results:
        aggregate_density.update(result.get("score_density_counts") or {})
        aggregate_fade.update(result.get("score_fade_counts") or {})
        aggregate_primitive.update(result.get("score_primitive_counts") or {})
        aggregate_color.update(result.get("score_color_counts") or {})
        aggregate_motif_hints.update(result.get("score_motif_hint_counts") or {})
        repair_parts = result.get("score_repair_part_counts") or {}
        aggregate_repair_parts.update(repair_parts)
        aggregate_repair_part_samples.update(repair_parts.keys())
        aggregate_presence.update(result.get("score_presence_counts") or {})
        aggregate_presence_gaze.update(result.get("score_presence_gaze_counts") or {})
        aggregate_relation.update(result.get("score_relation_counts") or {})
        aggregate_relation_instructions += int(result.get("score_relation_instruction_count") or 0)
        if result.get("score_has_relation"):
            aggregate_relation_samples += 1
        aggregate_coerce_relation_input += int(result.get("coerce_relation_input_count") or 0)
        aggregate_coerce_relation_output += int(result.get("coerce_relation_output_count") or 0)
        aggregate_coerce_relation_dropped += int(result.get("coerce_relation_dropped_count") or 0)
        branch_counts = result.get("coerce_branch_counts") or {}
        aggregate_coerce_branches.update(branch_counts)
        for branch_name, branch_count in branch_counts.items():
            aggregate_coerce_branch_samples.setdefault(branch_name, 0)
            if int(branch_count or 0) > 0:
                aggregate_coerce_branch_samples[branch_name] += 1
        aggregate_math_balance.update(result.get("math_balance_markers") or {})
        aggregate_clustered += int(result.get("score_clustered_arrangements") or 0)
        aggregate_preserve_space += int(result.get("score_preserve_space_count") or 0)
        aggregate_color_cycle += int(result.get("score_color_cycle_count") or 0)
        aggregate_expanded += int(result.get("score_expanded_count") or 0)
        trace = result.get("color_trace")
        if isinstance(trace, dict):
            color_traces.append(trace)

    summary = {
        "success": len(results),
        "failed": len(failures),
        "total": len(work_items),
        "prompt_total": len(lines),
        "vary_count": vary_count,
        "input_mode": input_mode,
        **_model_summary(
            None if input_mode == "ddl" else stage1_model,
            stage2_model,
            stage1_provider=None if input_mode == "ddl" else stage1_provider,
            stage2_provider=stage2_provider,
        ),
        "timeout_seconds": timeout_seconds,
        "svg_profile": args.svg_profile,
        **_color_catalog_summary(color_catalog, catalog_data),
        "render_build_numbers": sorted({
            str(result["render_build_number"])
            for result in results
            if result.get("render_build_number") is not None
        }),
        "render_color_catalog_id": results[0].get("render_color_catalog_id") if results else None,
        "render_color_catalog_name": results[0].get("render_color_catalog_name") if results else None,
        "render_color_catalog_sub": results[0].get("render_color_catalog_sub") if results else None,
        "render_color_map": results[0].get("render_color_map") if results else None,
        "color_trace": _aggregate_color_traces(color_traces),
        "elapsed_total_ms": total_elapsed,
        "tokens_in": total_in or None,
        "tokens_out": total_out or None,
        "http_502_count": _http_502_count(failures),
        "score_expanded_count": aggregate_expanded or None,
        "score_clustered_arrangements": aggregate_clustered,
        "score_preserve_space_count": aggregate_preserve_space,
        "score_color_cycle_count": aggregate_color_cycle,
        "score_density_counts": dict(sorted(aggregate_density.items())),
        "score_fade_counts": dict(sorted(aggregate_fade.items())),
        "score_primitive_counts": dict(sorted(aggregate_primitive.items())),
        "score_color_counts": dict(sorted(aggregate_color.items())),
        "score_motif_hint_counts": dict(sorted(aggregate_motif_hints.items())),
        "score_motif_hint_lines": _aggregate_marker_lines(results, "score_motif_hint_counts"),
        "score_repair_part_counts": dict(sorted(aggregate_repair_parts.items())),
        "score_repair_part_sample_counts": dict(sorted(aggregate_repair_part_samples.items())),
        "score_repair_part_sample_rates": {
            key: round(value / len(results), 6) for key, value in sorted(aggregate_repair_part_samples.items())
        } if results else {},
        "score_repair_part_lines": _aggregate_marker_lines(results, "score_repair_part_counts"),
        "score_presence_counts": dict(sorted(aggregate_presence.items())),
        "score_presence_gaze_counts": dict(sorted(aggregate_presence_gaze.items())),
        "score_presence_lines": _aggregate_marker_lines(results, "score_presence_counts"),
        "score_relation_counts": dict(sorted(aggregate_relation.items())),
        "score_relation_instruction_count": aggregate_relation_instructions,
        "score_relation_sample_count": aggregate_relation_samples,
        "score_relation_sample_rate": round(aggregate_relation_samples / len(results), 6) if results else None,
        "score_relation_lines": _aggregate_marker_lines(results, "score_relation_counts"),
        "coerce_relation_input_count": aggregate_coerce_relation_input,
        "coerce_relation_output_count": aggregate_coerce_relation_output,
        "coerce_relation_dropped_count": aggregate_coerce_relation_dropped,
        "coerce_relation_drop_rate": (
            round(aggregate_coerce_relation_dropped / aggregate_coerce_relation_input, 6)
            if aggregate_coerce_relation_input
            else None
        ),
"coerce_branch_counts": dict(sorted(aggregate_coerce_branches.items())),
"coerce_branch_sample_counts": dict(sorted(aggregate_coerce_branch_samples.items())),
"coerce_branch_sample_rates": {
    key: round(value / len(results), 6)
    for key, value in sorted(aggregate_coerce_branch_samples.items())
} if results else {},
"coerce_removal_candidates": [
    key for key in sorted(aggregate_coerce_branches)
    if aggregate_coerce_branch_samples.get(key, 0) <= 1
],
        "coerce_warning_lines": [
            int(result["line"])
            for result in results
            if result.get("coerce_warnings") and result.get("line")
        ],
        "math_balance_markers": dict(sorted(aggregate_math_balance.items())),
        "math_balance_marker_lines": _aggregate_marker_lines(results, "math_balance_markers"),
        "score_quality_metrics": _aggregate_quality_metrics(results),
        "server_timeout_samples": [
            int(result["line"])
            for result in results
            if result.get("server_timeout_reasons") and result.get("line")
        ],
        "server_timeout_retry_attempted_samples": [
            int(result["line"])
            for result in results
            if result.get("server_timeout_retry_attempted") and result.get("line")
        ],
        "review_sets": _review_sets(results),
        "results": results,
        "failures": failures,
    }
    summary_path = Path(args.summary_json) if args.summary_json else (out_dir / "analysis-summary.json" if out_dir else None)
    if summary_path is not None:
        _write_json_file(summary_path, summary)
        print(f"summary: {summary_path}", file=sys.stderr)
    _print_json(summary)
    return 1 if failures else 0

def command_contact_sheet(args: argparse.Namespace) -> int:
    input_dir = Path(args.input_dir)
    output_path = Path(args.output) if args.output else input_dir / "contact-sheet.png"
    _make_contact_sheet(input_dir, output_path, columns=args.columns, thumb_size=args.thumb_size, order=args.order)
    print(str(output_path))
    return 0

def command_analyze(args: argparse.Namespace) -> int:
    if args.census and args.history:
        if args.input_dir:
            raise CliError("INPUT_DIR cannot be combined with --history")
        config = load_config()
        client = ApiClient(
            args.base_url or config.base_url,
            config.token,
            timeout_seconds=_resolved_timeout_seconds(args, config),
        )
        summary = _motif_census_from_history(
            _fetch_all_history(client),
            base_url=client.base_url,
        )
        if args.output:
            _write_json_file(Path(args.output), summary)
        _print_json(summary)
        return 0
    if not args.input_dir:
        raise CliError("INPUT_DIR is required unless --census --history is used")
    input_dir = Path(args.input_dir)
    if not input_dir.exists() or not input_dir.is_dir():
        raise CliError(f"input directory not found: {input_dir}")
    if args.census:
        summary = _motif_census(input_dir)
        output_path = Path(args.output) if args.output else input_dir / "motif-census.json"
        _write_json_file(output_path, summary)
        _print_json(summary)
        return 0
    if args.history:
        raise CliError("--history requires --census")
    if not args.diversity:
        raise CliError("choose --diversity or --census")
    config = load_config()
    client = None
    catalog_data = None
    color_catalog = getattr(args, "color_catalog", None) or DEFAULT_COLOR_CATALOG_ID
    if args.replay and args.replay > 1:
        client = ApiClient(
            args.base_url or config.base_url,
            config.token,
            timeout_seconds=_resolved_timeout_seconds(args, config),
        )
        catalog_data = _fetch_color_catalogs(client)
        color_catalog = _resolved_color_catalog(args, config, catalog_data)
    summary = _diversity_summary(
        input_dir,
        replay=max(0, int(args.replay or 0)),
        replay_limit=max(1, int(args.replay_limit or 5)),
        client=client,
        color_catalog=color_catalog,
        canvas_aspect=args.canvas_aspect,
    )
    output_path = Path(args.output) if args.output else input_dir / "diversity-summary.json"
    _write_json_file(output_path, summary)
    print(f"summary: {output_path}", file=sys.stderr)
    _print_json(summary)
    return 0

def command_render_score(args: argparse.Namespace) -> int:
    config = load_config()
    client = ApiClient(
        args.base_url or config.base_url,
        config.token,
        timeout_seconds=_resolved_timeout_seconds(args, config),
    )
    raw = _read_text_argument(args.score, args.file)
    try:
        score = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise CliError("score must be valid JSON") from exc
    if not isinstance(score, dict):
        raise CliError("score JSON must be an object")
    catalog_data = _fetch_color_catalogs(client)
    color_catalog = _resolved_color_catalog(args, config, catalog_data)
    svg = client.request_text(
        "POST",
        "/api/render-svg",
        data={
            "score": score,
            "catalog_id": color_catalog,
            "canvas_aspect": args.canvas_aspect,
            "svg_profile": args.svg_profile,
            "render_seed": args.render_seed,
        },
    )
    render_build_number = _cli_build_number()
    render_hash = _render_hash_for_score(
        score,
        render_seed=args.render_seed,
        vary_seed=args.vary_seed,
        render_build_number=render_build_number,
        render_engine_id="default",
        render_engine_version="2",
        render_color_catalog_id=color_catalog,
    )
    result = {
        "status": "ok",
        "score": score,
        "svg": svg,
        "render_hash": render_hash,
        "render_hash_short": render_hash[-4:].upper(),
        "render_build_number": render_build_number,
        "render_engine_id": "default",
        "render_engine_version": "2",
        "render_color_catalog_id": color_catalog,
        "render_canvas_aspect": args.canvas_aspect,
        "render_canvas_aspect_id": args.canvas_aspect,
        "render_canvas_aspect_ratio": _canvas_aspect_ratio(args.canvas_aspect),
        "render_seed": args.render_seed,
        "vary_seed": args.vary_seed,
        "svg_profile": args.svg_profile,
    }
    paths = _write_paint_outputs(result, out_dir=Path(args.out_dir) if args.out_dir else None, prefix=args.prefix or "score", png=args.png)
    result["paths"] = paths
    _print_json(result if args.full_json else {key: value for key, value in result.items() if key not in {"svg", "score"}})
    return 0

def command_demo_instruction(args: argparse.Namespace) -> int:
    config = load_config()
    client = ApiClient(
        args.base_url or config.base_url,
        config.token,
        timeout_seconds=_resolved_timeout_seconds(args, config),
    )
    data, _ = client.request(
        "POST",
        "/api/demo/instruction",
        data={
            "seed_phrase": args.seed_phrase,
            "model": args.model,
            "instruction_lang": args.instruction_lang,
            "ui_lang": args.ui_lang,
        },
    )
    print(data["instruction"])
    return 0

def command_history(args: argparse.Namespace) -> int:
    config = load_config()
    client = ApiClient(
        args.base_url or config.base_url,
        config.token,
        timeout_seconds=_resolved_timeout_seconds(args, config),
    )
    data, _ = client.request(
        "GET",
        "/api/history",
        query={"offset": args.offset, "limit": args.limit, "q": args.query, "starred": args.starred},
    )
    _print_json(data)
    return 0

def command_unread_words(args: argparse.Namespace) -> int:
    config = load_config()
    client = ApiClient(
        args.base_url or config.base_url,
        config.token,
        timeout_seconds=_resolved_timeout_seconds(args, config),
    )
    path = "/api/admin/unread-words" if args.all_users else "/api/feedback/unread-words"
    data, _ = client.request("GET", path, query={"limit": args.limit})
    _print_json({
        "scope": "all_users" if args.all_users else "current_user",
        "words": data,
        "note": "Candidate ledger only. Vocabulary promotion is decided by a human after bilingual review.",
    })
    return 0

def command_history_export(args: argparse.Namespace) -> int:
    config = load_config()
    client = ApiClient(
        args.base_url or config.base_url,
        config.token,
        timeout_seconds=_resolved_timeout_seconds(args, config),
    )
    items = _fetch_all_history(client, starred=args.starred, query=args.query)
    selected = _select_history_items(
        items,
        hashes=args.hashes or [],
        from_hash=args.from_hash,
        to_hash=args.to_hash,
    )
    summary = _write_history_export(
        selected,
        out_dir=Path(args.out_dir),
        columns=args.columns,
        thumb_size=args.thumb_size,
    )
    _print_json(summary)
    return 0

def command_version(args: argparse.Namespace) -> int:
    config = load_config()
    client = ApiClient(
        args.base_url or config.base_url,
        config.token,
        timeout_seconds=_resolved_timeout_seconds(args, config),
    )
    server_info: dict[str, Any] | None = None
    try:
        server_info, _ = client.request("GET", "/api/info", auth=False)
    except CliError:
        server_info = None
    _print_json({
        "cli": {
            "name": "inku-cli",
            "version": _cli_version(),
            "build_number": _cli_build_number(),
        },
        "server": server_info,
    })
    return 0

def _add_common_server_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--base-url", default=None, help=f"inku API base URL (default: {DEFAULT_BASE_URL})")
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=None,
        help=f"HTTP timeout in seconds (default: {DEFAULT_REQUEST_TIMEOUT_SECONDS})",
    )

def _add_paint_args(parser: argparse.ArgumentParser, *, batch: bool = False) -> None:
    _add_common_server_args(parser)
    if batch:
        parser.add_argument("--file", "-f", required=True, help="UTF-8 text file; one prompt per non-empty line, or '-'")
    else:
        parser.add_argument("text", nargs="?", help="prompt text")
        parser.add_argument("--file", "-f", help="read prompt text from a UTF-8 file, or '-'")
    parser.add_argument("--out-dir", "-o", help="directory for JSON/SVG/PNG outputs")
    parser.add_argument("--prefix", help="output filename prefix")
    parser.add_argument("--png", action="store_true", help="also render PNG output when --out-dir is set")
    parser.add_argument("--svg-profile", choices=SVG_PROFILES, default="display", help="SVG output profile for saved files")
    parser.add_argument(
        "--input-mode",
        choices=["paint", "ddl"],
        default="paint",
        help="paint: natural-language prompt through Stage 1; ddl: normalized DDL directly through Stage 2/render",
    )
    parser.add_argument("--stage1-provider", choices=PROVIDERS)
    parser.add_argument("--stage1-model")
    parser.add_argument("--stage2-provider", choices=PROVIDERS)
    parser.add_argument("--stage2-model")
    parser.add_argument("--original-text")
    parser.add_argument("--history-input")
    parser.add_argument("--catalog-id", help="color catalog id (legacy alias)")
    parser.add_argument("--color-catalog", help="server color catalog id for renderer and benchmark tracing")
    parser.add_argument("--canvas-aspect", choices=CANVAS_ASPECTS, help="canvas aspect id for paint, compose, and history")
    parser.add_argument("--render-seed", type=int, help="renderer performance seed for reproducible replay")
    parser.add_argument("--vary-seed", type=int, help="Stage 1.5 composition variation seed")
    parser.add_argument("--seed-text", help="explicit text used only to derive the renderer performance seed")
    parser.add_argument("--instruction-lang", default="auto", choices=["auto", "ja", "en"])
    parser.add_argument("--ui-lang")
    parser.add_argument("--include-thinking", action="store_true")
    parser.add_argument("--save-history", action="store_true")
    parser.add_argument("--save-artifacts", action=argparse.BooleanOptionalAction, default=None)
    parser.add_argument("--no-progress", action="store_true", help="disable elapsed-time progress animation")
    if batch:
        parser.add_argument("--continue-on-error", action="store_true")
        parser.add_argument("--summary-json", help="write batch summary JSON to this path (default: OUT_DIR/analysis-summary.json)")
        parser.add_argument("--vary", type=int, default=1, help="generate N Stage 1.5 variations per prompt")
    else:
        parser.add_argument("--full-json", action="store_true", help="print the full paint response")

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="inku-cli", description="Control an inku API server from the command line")
    subparsers = parser.add_subparsers(dest="command", required=True)

    login = subparsers.add_parser("login", help="log in and store an API session")
    _add_common_server_args(login)
    login.add_argument("--username", "-u", required=True)
    login.add_argument("--password", "-p")
    login.set_defaults(func=command_login)

    logout = subparsers.add_parser("logout", help="log out and clear the stored session")
    _add_common_server_args(logout)
    logout.set_defaults(func=command_logout)

    me = subparsers.add_parser("me", help="show the current logged-in user")
    _add_common_server_args(me)
    me.set_defaults(func=command_me)

    models = subparsers.add_parser("models", help="show or set CLI default Stage 1 / Stage 2 models")
    _add_common_server_args(models)
    models.add_argument("--stage1-provider", choices=PROVIDERS, help="save the default Stage 1 provider")
    models.add_argument("--stage1-model", help="save the default Stage 1 model for paint and batch")
    models.add_argument("--stage2-provider", choices=PROVIDERS, help="save the default Stage 2 provider")
    models.add_argument("--stage2-model", help="save the default Stage 2 model for paint and batch")
    models.add_argument("--color-catalog", help="save the default server color catalog for paint and batch")
    models.set_defaults(func=command_models)

    paint = subparsers.add_parser("paint", help="generate one drawing")
    _add_paint_args(paint)
    paint.set_defaults(func=command_paint)

    batch = subparsers.add_parser("batch", help="generate drawings from a prompt list")
    _add_paint_args(batch, batch=True)
    batch.set_defaults(func=command_batch)

    contact_sheet = subparsers.add_parser("contact-sheet", help="create a contact sheet from PNG files in a directory")
    contact_sheet.add_argument("input_dir", help="directory containing PNG outputs")
    contact_sheet.add_argument("--output", "-o", help="output PNG path (default: INPUT_DIR/contact-sheet.png)")
    contact_sheet.add_argument("--columns", type=int, default=5)
    contact_sheet.add_argument("--thumb-size", type=int, default=220)
    contact_sheet.add_argument("--order", choices=["name", "similarity"], default="name")
    contact_sheet.set_defaults(func=command_contact_sheet)

    analyze = subparsers.add_parser("analyze", help="analyze generated PNG/JSON outputs")
    _add_common_server_args(analyze)
    analyze.add_argument("input_dir", nargs="?", help="directory containing PNG and JSON outputs")
    analyze.add_argument("--diversity", action="store_true", help="compute diversity metrics and write diversity-summary.json")
    analyze.add_argument("--census", action="store_true", help="report frequent mechanical motif signatures with thumbnail examples")
    analyze.add_argument("--history", action="store_true", help="run --census over the current user history instead of a directory")
    analyze.add_argument("--output", "-o", help="summary JSON path (default: INPUT_DIR/diversity-summary.json)")
    analyze.add_argument("--replay", type=int, default=0, help="render each sampled score N times and compute replay divergence")
    analyze.add_argument("--replay-limit", type=int, default=5, help="maximum score artifacts to replay")
    analyze.add_argument("--canvas-aspect", choices=CANVAS_ASPECTS, default="square")
    analyze.add_argument("--catalog-id", help="color catalog id (legacy alias)")
    analyze.add_argument("--color-catalog", help="server color catalog id for replay rendering")
    analyze.set_defaults(func=command_analyze)

    ddl_compare = subparsers.add_parser("ddl-compare", help="compare normalized DDL artifacts side by side")
    ddl_compare.add_argument("input_dirs", nargs="+", help="two or more artifact directories")
    ddl_compare.add_argument("--output", "-o")
    ddl_compare.set_defaults(func=command_ddl_compare)

    vision_review = subparsers.add_parser("vision-review", help="use the configured NIM vision model as a read-only visual mirror")
    vision_review.add_argument("input_dir")
    vision_review.add_argument("--model", default="meta/llama-3.2-90b-vision-instruct")
    vision_review.add_argument("--output", "-o")
    vision_review.set_defaults(func=command_vision_review)

    render_score = subparsers.add_parser("render-score", help="render a Score JSON object without Stage 1 or Stage 2")
    _add_common_server_args(render_score)
    render_score.add_argument("score", nargs="?", help="Score JSON text")
    render_score.add_argument("--file", "-f", help="read Score JSON from a file, or '-'")
    render_score.add_argument("--out-dir", "-o", help="directory for JSON/SVG/PNG outputs")
    render_score.add_argument("--prefix", help="output filename prefix")
    render_score.add_argument("--png", action="store_true", help="also render PNG output when --out-dir is set")
    render_score.add_argument("--svg-profile", choices=SVG_PROFILES, default="display")
    render_score.add_argument("--canvas-aspect", default="square")
    render_score.add_argument("--render-seed", type=int, help="renderer performance seed for reproducible replay")
    render_score.add_argument("--vary-seed", type=int, help="record Stage 1.5 composition variation seed in output metadata")
    render_score.add_argument("--catalog-id", help="color catalog id (legacy alias)")
    render_score.add_argument("--color-catalog", help="server color catalog id")
    render_score.add_argument("--full-json", action="store_true", help="print SVG and Score as well")
    render_score.set_defaults(func=command_render_score)

    demo = subparsers.add_parser("demo-instruction", help="generate one demo prompt from a seed phrase")
    _add_common_server_args(demo)
    demo.add_argument("seed_phrase")
    demo.add_argument("--model")
    demo.add_argument("--instruction-lang", default="auto", choices=["auto", "ja", "en"])
    demo.add_argument("--ui-lang")
    demo.set_defaults(func=command_demo_instruction)

    history = subparsers.add_parser("history", help="list history items")
    _add_common_server_args(history)
    history.add_argument("--offset", type=int, default=0)
    history.add_argument("--limit", type=int, default=20)
    history.add_argument("--query", "-q")
    history.add_argument("--starred", action="store_true")
    history.set_defaults(func=command_history)

    unread_words = subparsers.add_parser("unread-words", help="report words the interpreter could not confidently read")
    _add_common_server_args(unread_words)
    unread_words.add_argument("--all", dest="all_users", action="store_true", help="admin-only aggregate across users")
    unread_words.add_argument("--limit", type=int, default=100)
    unread_words.set_defaults(func=command_unread_words)

    history_export = subparsers.add_parser("history-export", help="export history items by hash for benchmark review")
    _add_common_server_args(history_export)
    history_export.add_argument("hashes", nargs="*", help="individual 4+ character history hash suffixes")
    history_export.add_argument("--from", dest="from_hash", help="start hash suffix for an inclusive history-order range")
    history_export.add_argument("--to", dest="to_hash", help="end hash suffix for an inclusive history-order range")
    history_export.add_argument("--out-dir", "-o", required=True, help="output directory for contact sheet and JSON files")
    history_export.add_argument("--columns", type=int, default=5)
    history_export.add_argument("--thumb-size", type=int, default=220)
    history_export.add_argument("--query", "-q", help="filter history before resolving hashes")
    history_export.add_argument("--starred", action="store_true", help="filter history to starred items before resolving hashes")
    history_export.set_defaults(func=command_history_export)

    version_cmd = subparsers.add_parser("version", help="show CLI and server version/build information")
    _add_common_server_args(version_cmd)
    version_cmd.set_defaults(func=command_version)

    return parser

def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args) or 0)
    except CliError as exc:
        print(f"inku-cli: {exc}", file=sys.stderr)
        return 2

if __name__ == "__main__":
    raise SystemExit(main())
