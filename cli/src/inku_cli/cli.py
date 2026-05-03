"""Command line client for controlling an inku API server."""

from __future__ import annotations

import argparse
import getpass
import json
import os
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

SESSION_COOKIE_NAME = "inku_session"
DEFAULT_BASE_URL = "http://127.0.0.1:8100"
DEFAULT_REQUEST_TIMEOUT_SECONDS = 600
SERVER_DEFAULT_MODEL_LABEL = "server default"
SERVER_DEFAULT_PROVIDER_LABEL = "server default"
PROVIDERS = ("nvidia", "anthropic", "local")
COLOR_KEYS = ("white", "black", "blue", "red", "green", "gray")
DEFAULT_COLOR_CATALOG_ID = "default"
COLOR_MARKERS: dict[str, tuple[str, ...]] = {
    "white": ("white", "ivory", "snow", "paper", "白", "雪", "紙", "光"),
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
        "render_color_catalog": result.get("render_color_catalog"),
        "render_color_map": result.get("render_color_map"),
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


def _make_contact_sheet(input_dir: Path, output_path: Path, *, columns: int, thumb_size: int) -> None:
    try:
        from PIL import Image, ImageDraw
    except ImportError as exc:
        raise CliError("contact-sheet requires Pillow") from exc

    pngs = sorted(path for path in input_dir.glob("*.png") if path.name != output_path.name)
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

    for index, path in enumerate(pngs):
        row, col = divmod(index, columns)
        x = gap + col * (thumb_size + gap)
        y = gap + row * (thumb_size + label_h + gap)
        with Image.open(path) as image:
            image = image.convert("RGB")
            image.thumbnail((thumb_size, thumb_size))
            px = x + (thumb_size - image.width) // 2
            py = y + (thumb_size - image.height) // 2
            sheet.paste(image, (px, py))
        draw.text((x, y + thumb_size + 4), path.stem, fill=(40, 40, 40))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output_path)


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
            for motif in MOTIF_HINT_KEYS:
                if motif in hint:
                    motif_hint_counts[motif] += 1

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
        if any(marker.lower() in lower or marker in text for marker in markers)
    ]
    return sorted(found)


def _negated_marker_colors(text: str | None) -> list[str]:
    if not text:
        return []
    lower = text.lower()
    found = [
        color
        for color, markers in NEGATED_COLOR_MARKERS.items()
        if any(marker.lower() in lower or marker in text for marker in markers)
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
        "lang": args.lang,
        "save_history": args.save_history,
        "save_artifacts": args.save_artifacts,
        "history_input": args.history_input,
        "catalog_id": color_catalog,
    }
    return {k: v for k, v in payload.items() if v is not None}


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
    paths = _write_paint_outputs(result, out_dir=Path(args.out_dir) if args.out_dir else None, prefix=prefix, png=args.png)
    summary = {
        "text": result.get("text"),
        **_model_summary(
            stage1_model,
            stage2_model,
            stage1_provider=stage1_provider,
            stage2_provider=stage2_provider,
        ),
        "timeout_seconds": timeout_seconds,
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
            **result,
            **_model_summary(
                stage1_model,
                stage2_model,
                stage1_provider=stage1_provider,
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
    for index, line in enumerate(lines, start=1):
        try:
            result, _ = _run_with_progress(
                f"drawing {index}/{len(lines)}",
                lambda line=line: client.request("POST", "/api/paint", data=_paint_payload(
                    args,
                    line,
                    stage1_model=stage1_model,
                    stage2_model=stage2_model,
                    color_catalog=color_catalog,
                )),
                enabled=not args.no_progress,
            )
            prefix = f"{args.prefix}-{index:03d}" if args.prefix else f"inku-batch-{index:03d}"
            paths = _write_paint_outputs(result, out_dir=out_dir, prefix=prefix, png=args.png)
            tokens_in = (result.get("tokens_in_stage1") or 0) + (result.get("tokens_in_stage2") or 0)
            tokens_out = (result.get("tokens_out_stage1") or 0) + (result.get("tokens_out_stage2") or 0)
            elapsed = int(result.get("elapsed_total_ms") or 0)
            total_in += tokens_in
            total_out += tokens_out
            total_elapsed += elapsed
            results.append({
                "line": index,
                "text": result.get("text"),
                **_model_summary(
                    stage1_model,
                    stage2_model,
                    stage1_provider=stage1_provider,
                    stage2_provider=stage2_provider,
                ),
                "timeout_seconds": timeout_seconds,
                **_color_catalog_summary(color_catalog, catalog_data),
                **_render_response_summary(result),
                "color_trace": _color_trace(result, catalog_id=color_catalog, catalog_data=catalog_data, requested_text=line),
                "history_id": result.get("history_id"),
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
            })
            print(f"{index}/{len(lines)} ok {elapsed}ms", file=sys.stderr)
        except CliError as exc:
            failures.append({"line": index, "text": line, "message": str(exc)})
            print(f"{index}/{len(lines)} failed: {exc}", file=sys.stderr)
            if not args.continue_on_error:
                break
    aggregate_density: Counter[str] = Counter()
    aggregate_fade: Counter[str] = Counter()
    aggregate_primitive: Counter[str] = Counter()
    aggregate_color: Counter[str] = Counter()
    aggregate_motif_hints: Counter[str] = Counter()
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
        "total": len(lines),
        **_model_summary(
            stage1_model,
            stage2_model,
            stage1_provider=stage1_provider,
            stage2_provider=stage2_provider,
        ),
        "timeout_seconds": timeout_seconds,
        **_color_catalog_summary(color_catalog, catalog_data),
        "render_build_numbers": sorted({
            str(result["render_build_number"])
            for result in results
            if result.get("render_build_number") is not None
        }),
        "render_color_catalog": results[0].get("render_color_catalog") if results else None,
        "render_color_map": results[0].get("render_color_map") if results else None,
        "color_trace": _aggregate_color_traces(color_traces),
        "elapsed_total_ms": total_elapsed,
        "tokens_in": total_in or None,
        "tokens_out": total_out or None,
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
        "math_balance_markers": dict(sorted(aggregate_math_balance.items())),
        "math_balance_marker_lines": _aggregate_marker_lines(results, "math_balance_markers"),
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
    _make_contact_sheet(input_dir, output_path, columns=args.columns, thumb_size=args.thumb_size)
    print(str(output_path))
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
        data={"seed_phrase": args.seed_phrase, "model": args.model, "lang": args.lang},
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
    parser.add_argument("--stage1-provider", choices=PROVIDERS)
    parser.add_argument("--stage1-model")
    parser.add_argument("--stage2-provider", choices=PROVIDERS)
    parser.add_argument("--stage2-model")
    parser.add_argument("--original-text")
    parser.add_argument("--history-input")
    parser.add_argument("--catalog-id", help="color catalog id (legacy alias)")
    parser.add_argument("--color-catalog", help="server color catalog id for renderer and benchmark tracing")
    parser.add_argument("--lang", default="ja", choices=["ja", "en"])
    parser.add_argument("--include-thinking", action="store_true")
    parser.add_argument("--save-history", action="store_true")
    parser.add_argument("--save-artifacts", action=argparse.BooleanOptionalAction, default=None)
    parser.add_argument("--no-progress", action="store_true", help="disable elapsed-time progress animation")
    if batch:
        parser.add_argument("--continue-on-error", action="store_true")
        parser.add_argument("--summary-json", help="write batch summary JSON to this path (default: OUT_DIR/analysis-summary.json)")
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
    contact_sheet.set_defaults(func=command_contact_sheet)

    demo = subparsers.add_parser("demo-instruction", help="generate one demo prompt from a seed phrase")
    _add_common_server_args(demo)
    demo.add_argument("seed_phrase")
    demo.add_argument("--model")
    demo.add_argument("--lang", default="ja", choices=["ja", "en"])
    demo.set_defaults(func=command_demo_instruction)

    history = subparsers.add_parser("history", help="list history items")
    _add_common_server_args(history)
    history.add_argument("--offset", type=int, default=0)
    history.add_argument("--limit", type=int, default=20)
    history.add_argument("--query", "-q")
    history.add_argument("--starred", action="store_true")
    history.set_defaults(func=command_history)

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
