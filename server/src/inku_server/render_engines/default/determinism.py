"""Deterministic seed, hash, and value-noise primitives for the default engine."""

from __future__ import annotations

import hashlib
import json
import math
import secrets
import struct

from ...schema import Instruction, Variation

_VARIATION_SEED_FIELDS_ALL = frozenset(
    {"amplitude", "frequency", "quality", "dimensions"}
)
_WORK_COLOR_SEED_FIELDS = ("render_seed", "catalog_id", "abstract_color")

_SEED_INSTRUCTION_FIELDS = (
    "primitive",
    "from_",
    "to",
    "center",
    "radius",
    "sides",
    "position",
    "size",
    "angle_start",
    "angle_end",
    "rotation",
    "filled",
    "style",
    "weight",
    "thinness",
    "mode",
    "carve_depth",
    "variation",
    "arrangement",
    "surface",
)
_SEED_ARRANGEMENT_FIELDS = ("jitter",)


def _variation_seed_fields(ins: Instruction) -> frozenset[str] | None:
    """seed key に残す variation フィールド。None = variation ごと落とす。

    演奏されない variation が seed を動かすと、同じ意図が weight 次第で別の
    演奏になる。実際に消費されるフィールドだけを残す。判定は primitive ごとに
    異なる (cloudform は dimensions を見ず、残り 3 つを輪郭生成器の引数に使う)。
    """
    variation = ins.variation
    if variation is None:
        return None
    if ins.primitive == "cloudform":
        return frozenset({"amplitude", "frequency", "quality"})
    if _needs_blur(variation):
        # 滲みは stdDeviation だけを代表寸法と amplitude から決める。
        return frozenset({"amplitude", "quality"})
    if ins.primitive == "line":
        return _VARIATION_SEED_FIELDS_ALL if _needs_path_variation(variation) else None
    if _needs_contour_variation(variation):
        return _VARIATION_SEED_FIELDS_ALL
    return None


def _seed_for_instruction(ins: Instruction, performance_seed: int | None = None) -> int:
    """Instruction と演奏 seed から安定した乱数 seed を作る。"""
    dumped = ins.model_dump(mode="json")
    payload = {name: dumped[name] for name in _SEED_INSTRUCTION_FIELDS}
    arrangement = payload.get("arrangement")
    if isinstance(arrangement, dict):
        payload["arrangement"] = {
            name: arrangement[name] for name in _SEED_ARRANGEMENT_FIELDS
        }
    if payload.get("mode") == "additive":
        payload.pop("mode", None)
    if payload.get("carve_depth") is None:
        payload.pop("carve_depth", None)
    variation_payload = payload.get("variation")
    if isinstance(variation_payload, dict):
        fields = _variation_seed_fields(ins)
        if fields is None:
            # variation なしの Instruction と同じ key にする (pop ではなく None)。
            payload["variation"] = None
        elif fields is not _VARIATION_SEED_FIELDS_ALL:
            payload["variation"] = {
                name: value
                for name, value in variation_payload.items()
                if name in fields
            }
    surface = payload.get("surface")
    if isinstance(surface, dict) and surface.get("texture") == "solid":
        # 演奏されないフィールドを key から外す作法 (`_variation_seed_fields` と同じ)。
        # `solid` は素材の既定の埋め方で、面の質感の層はそれを 1 本も引かないから、
        # 残りの surface フィールドは何も消費されない。`filled=true` と書いた
        # Instruction と同じ key にする — 同じ要求の 2 通りの言い方が別の演奏に
        # なってはいけない。これが無いと、coerce が保存済みの `filled` へ
        # `surface` を足した瞬間に本番の全作品の筆致が振り直される。
        payload["filled"] = True
        payload["surface"] = surface = None
    if isinstance(surface, dict):
        if surface.get("spacing_gradient") == "none":
            surface.pop("spacing_gradient", None)
        if surface.get("tone_steps") == 3:
            surface.pop("tone_steps", None)
    key = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if performance_seed is not None:
        key += f":render:{performance_seed}".encode("utf-8")
    digest = hashlib.sha256(key).digest()
    return struct.unpack("<Q", digest[:8])[0]


def new_render_seed() -> int:
    """演奏ごとのマクロ揺らぎ seed。明示 seed 指定時は再現可能。"""
    return secrets.randbits(53)


def _hash_to_unit(i: int, seed: int) -> float:
    """i と seed から [-1, 1] の擬似乱数値を決定的に生成。"""
    h = hashlib.sha256(f"{seed}:{i}".encode("utf-8")).digest()
    val = struct.unpack("<q", h[:8])[0]
    return val / float(2**63)


def _value_noise_1d(x: float, seed: int) -> float:
    """smoothstep 補間の 1D value noise (擬似 perlin)。"""
    xi = math.floor(x)
    xf = x - xi
    v1 = _hash_to_unit(xi, seed)
    v2 = _hash_to_unit(xi + 1, seed)
    t = xf * xf * (3 - 2 * xf)
    return v1 * (1 - t) + v2 * t


def _needs_blur(v: Variation | None) -> bool:
    """quality=pink → SVG feGaussianBlur で滲み表現。"""
    return v is not None and v.quality == "pink"


def _needs_path_variation(v: Variation | None) -> bool:
    """quality=perlin/wave/white かつ dimensions 指定あり → polyline 揺らぎ。pink は blur で処理。"""
    if v is None:
        return False
    if v.quality in ("none", "pink"):
        return False
    return any(d in ("position_x", "position_y") for d in v.dimensions)


_CONTOUR_VARIATION_DIMS = ("position_x", "position_y", "radius")


def _needs_contour_variation(v: Variation | None) -> bool:
    """弧・閉図形の輪郭揺らぎ。line のゲートと対称で、図形の自然軸として radius を加える。"""
    if v is None:
        return False
    if v.quality in ("none", "pink"):
        return False
    return any(d in _CONTOUR_VARIATION_DIMS for d in v.dimensions)


def _wave_phase(seed: int) -> float:
    """seed から [0, 2π) の位相を決定的に導出する。

    wave は sin の位相が固定だと演奏 seed に依存せず、同じ Score が常に同じ
    山谷の位置になる。位相だけを seed 由来にすることで、周期性 (整数周波数
    なら t∈[0,1) で閉じる) と振幅・周波数の語彙を保ったまま演奏差を作る。
    """
    return _hash01(0, seed, "wave-phase") * 2 * math.pi


def _periodic_value_noise_1d(x: float, seed: int, period: int) -> float:
    """周期境界つき value noise。閉じた輪郭の継ぎ目を連続にする。"""
    xi = math.floor(x)
    xf = x - xi
    v1 = _hash_to_unit(int(xi) % period, seed)
    v2 = _hash_to_unit((int(xi) + 1) % period, seed)
    t = xf * xf * (3 - 2 * xf)
    return v1 * (1 - t) + v2 * t


def _hash01(i: int, seed: int, salt: str) -> float:
    h = hashlib.sha256(f"{seed}:{salt}:{i}".encode()).digest()
    return struct.unpack("<I", h[:4])[0] / 0xFFFFFFFF
