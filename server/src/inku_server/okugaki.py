"""Manual, read-only lineage recitation for okugaki records.

This module depends on the shared composition mirror, but no generation module
depends on it.  Requests are deliberately built one generation at a time so an
earlier observation cannot contain information from a later generation.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
from collections import OrderedDict
from datetime import datetime
from threading import Lock
from time import monotonic
from typing import Any, Callable
from zoneinfo import ZoneInfo

from inku_analysis.rasterizer import svg_to_png

from .feature_analysis import composition_family
from .model_settings import connection_for, provider_for_model

DEFAULT_MODEL = os.getenv("INKU_OKUGAKI_MODEL", "meta/llama-3.2-90b-vision-instruct")
_VISION_RESPONSE_CACHE: OrderedDict[str, tuple[float, str]] = OrderedDict()
_VISION_RESPONSE_CACHE_LOCK = Lock()
_EVALUATION_WORDS = {
    "ja": ("良い", "美しい", "成功", "失敗", "洗練", "優れ", "劣る", "最高", "最悪", "完成"),
    "en": ("good", "beautiful", "successful", "failure", "refined", "superior", "inferior", "best", "worst", "perfect"),
}


def _instruction_features(score: dict[str, Any]) -> dict[str, Any]:
    instructions = [item for item in score.get("instructions") or [] if isinstance(item, dict)]
    primitives: set[str] = set()
    colors: set[str] = set()
    densities: set[str] = set()
    angles: set[str] = set()
    paths: set[str] = set()
    retained: set[str] = set()
    for item in instructions:
        primitive = str(item.get("primitive") or "unknown")
        color = str(item.get("color") or "unknown")
        primitives.add(primitive)
        colors.add(color)
        arrangement = item.get("arrangement") if isinstance(item.get("arrangement"), dict) else {}
        density = str(arrangement.get("density") or "none")
        path = str(arrangement.get("path") or arrangement.get("layout") or "none")
        densities.add(density)
        paths.add(path)
        rotation = item.get("rotation")
        if isinstance(rotation, (int, float)):
            angles.add(f"rotation:{float(rotation) % 360:g}")
        start, end = item.get("from"), item.get("to")
        if (
            isinstance(start, (list, tuple))
            and isinstance(end, (list, tuple))
            and len(start) >= 2
            and len(end) >= 2
        ):
            dx, dy = float(end[0]) - float(start[0]), float(end[1]) - float(start[1])
            if abs(dx) > abs(dy):
                angles.add("horizontal")
            elif abs(dy) > abs(dx):
                angles.add("vertical")
            else:
                angles.add("diagonal")
        retained.add(f"{primitive}:{color}:{density}:{path}")
    return {
        "composition_family": composition_family(score),
        "primitives": sorted(primitives),
        "colors": sorted(colors),
        "densities": sorted(densities),
        "angles": sorted(angles),
        "arrangement_paths": sorted(paths),
        "score_elements": sorted(retained),
        "instruction_count": len(instructions),
    }


def _set_delta(before: dict[str, Any], after: dict[str, Any], key: str) -> dict[str, list[str]]:
    old, new = set(before.get(key) or []), set(after.get(key) or [])
    return {"added": sorted(new - old), "removed": sorted(old - new), "retained": sorted(old & new)}


def feature_delta(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    return {
        "composition_family": {
            "before": before.get("composition_family"),
            "after": after.get("composition_family"),
            "changed": before.get("composition_family") != after.get("composition_family"),
        },
        **{
            key: _set_delta(before, after, key)
            for key in ("primitives", "colors", "densities", "angles", "arrangement_paths", "score_elements")
        },
        "instruction_count": {
            "before": before.get("instruction_count", 0),
            "after": after.get("instruction_count", 0),
        },
    }


def deterministic_invariants(generations: list[dict[str, Any]]) -> dict[str, Any]:
    available = [item["features"] for item in generations if item.get("features")]
    if not available:
        return {}
    result: dict[str, Any] = {}
    families = {item["composition_family"] for item in available}
    if len(families) == 1:
        result["composition_family"] = next(iter(families))
    for key in ("primitives", "colors", "densities", "angles", "arrangement_paths", "score_elements"):
        common = set(available[0].get(key) or [])
        for item in available[1:]:
            common &= set(item.get(key) or [])
        result[key] = sorted(common)
    counts = {item.get("instruction_count", 0) for item in available}
    if len(counts) == 1:
        result["instruction_count"] = next(iter(counts))
    return result


def build_fact_sheet(branch: dict[str, Any]) -> dict[str, Any]:
    nodes = branch["nodes"]
    edges = branch["edges"]
    generations: list[dict[str, Any]] = []
    for index, node in enumerate(nodes):
        history = node.get("history")
        score = history.get("score") if isinstance(history, dict) else None
        features = _instruction_features(score) if isinstance(score, dict) else None
        generation = {
            "index": index,
            "node_id": node["id"],
            "state": node["state"],
            "at": node["at"],
            "child_count": node.get("child_count", 0),
            "branch_split": node.get("child_count", 0) > 1,
            "caption": (history or {}).get("source_text") or (history or {}).get("input"),
            "features": features,
        }
        if index:
            edge = edges[index - 1]
            generation["derivation"] = {
                "kind": edge["derivation_kind"],
                "metadata": edge.get("metadata") or {},
            }
            before = generations[index - 1].get("features")
            if before and features:
                generation["feature_delta"] = feature_delta(before, features)
        generations.append(generation)
    return {
        "target_node_id": nodes[-1]["id"],
        "branch_snapshot": [item["id"] for item in nodes],
        "generations": generations,
        "invariants": deterministic_invariants(generations),
    }


def build_generation_request(fact_sheet: dict[str, Any], index: int, prior_observations: list[str]) -> dict[str, Any]:
    """Build a prefix-only request. Tests rely on this structural boundary."""
    current = fact_sheet["generations"][index]
    return {
        "generation_index": index,
        "known_generations": fact_sheet["generations"][: index + 1],
        "prior_observations": prior_observations[:index],
        "current": current,
    }


def _png_data_url(svg: str, *, width: int = 512, height: int = 512) -> str:
    png = svg_to_png(svg, width=width, height=height)
    return "data:image/png;base64," + base64.b64encode(png).decode("ascii")


def _vision_thumbnail_data_url(svgs: list[str]) -> str | None:
    """Rasterize one work or one before/after pair once, preserving artwork aspect."""
    clean = [svg for svg in svgs if svg]
    if not clean:
        return None
    encoded = [base64.b64encode(svg.encode("utf-8")).decode("ascii") for svg in clean[:2]]
    if len(encoded) == 1:
        sheet = (
            '<svg xmlns="http://www.w3.org/2000/svg" width="512" height="512" viewBox="0 0 512 512">'
            '<rect width="512" height="512" fill="white"/>'
            f'<image href="data:image/svg+xml;base64,{encoded[0]}" x="0" y="0" width="512" height="512" '
            'preserveAspectRatio="xMidYMid meet"/>'
            '</svg>'
        )
        return _png_data_url(sheet)
    sheet = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="1024" height="512" viewBox="0 0 1024 512">'
        '<rect width="1024" height="512" fill="white"/>'
        f'<image href="data:image/svg+xml;base64,{encoded[0]}" x="0" y="0" width="512" height="512" '
        'preserveAspectRatio="xMidYMid meet"/>'
        f'<image href="data:image/svg+xml;base64,{encoded[1]}" x="512" y="0" width="512" height="512" '
        'preserveAspectRatio="xMidYMid meet"/>'
        '</svg>'
    )
    return _png_data_url(sheet, width=768, height=384)


def _system_prompt(language: str) -> str:
    if language == "en":
        return (
            "You are a first-person reader of an artwork lineage. Describe only visible, observable changes. "
            "Use 'I see' or 'it appears to me'. Never score, rank, recommend, praise, condemn, infer authorial "
            "intent or emotion, or describe this generation as progress toward a later result. Captions are context only: "
            "never quote, paraphrase, or narrate them. Name concrete shapes, colors, positions, density, and movement. "
            "Return one short paragraph only."
        )
    return (
        "あなたは作品系譜を読む一人称の鑑賞者です。見える物理と観察できる変化だけを、"
        "「私には〜と見える」「私は〜と読んだ」の形で述べてください。評価、点数、順位、推薦、"
        "作者の意図や感情の断定、後の完成へ向かう目的論を含めないでください。詞書は補助情報に限り、"
        "引用・言い換え・物語化をせず、形、色、位置、密度、動きの見える差を具体的に述べ、短い一段落だけを返してください。"
    )


def _cached_vision_response(cache_key: str, generate: Callable[[], str]) -> str:
    """Reuse successful prefix reads so retrying a failed branch resumes cheaply."""
    ttl_seconds = max(0.0, float(os.getenv("INKU_OKUGAKI_CACHE_TTL_SECONDS", "1800")))
    if ttl_seconds == 0:
        return generate()
    now = monotonic()
    with _VISION_RESPONSE_CACHE_LOCK:
        cached = _VISION_RESPONSE_CACHE.get(cache_key)
        if cached is not None and now - cached[0] <= ttl_seconds:
            _VISION_RESPONSE_CACHE.move_to_end(cache_key)
            return cached[1]
        if cached is not None:
            del _VISION_RESPONSE_CACHE[cache_key]
    response = generate()
    if not response:
        return response
    max_entries = max(1, int(os.getenv("INKU_OKUGAKI_CACHE_MAX_ENTRIES", "256")))
    with _VISION_RESPONSE_CACHE_LOCK:
        _VISION_RESPONSE_CACHE[cache_key] = (monotonic(), response)
        _VISION_RESPONSE_CACHE.move_to_end(cache_key)
        while len(_VISION_RESPONSE_CACHE) > max_entries:
            _VISION_RESPONSE_CACHE.popitem(last=False)
    return response


def _vision_cache_key(
    *, provider: str, model_id: str, base_url: str, language: str, request: dict[str, Any], images: list[str]
) -> str:
    payload = {
        "version": 1,
        "provider": provider,
        "model": model_id,
        "base_url": base_url,
        "language": language,
        "system_prompt": _system_prompt(language),
        "request": request,
        "images": [hashlib.sha256(image.encode("utf-8")).hexdigest() for image in images],
    }
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _vision_chat(
    *,
    model: str,
    language: str,
    request: dict[str, Any],
    images: list[str],
    settings: dict[str, Any],
) -> str:
    provider, model_id = provider_for_model(model, stage="stage1", settings=settings)
    connection = connection_for(provider, settings)
    if connection.get("kind") != "openai_compatible":
        raise ValueError("okugaki currently requires an OpenAI-compatible vision provider")
    if connection.get("requires_api_key") and not connection.get("api_key"):
        raise ValueError(f"{provider} API key is not configured")
    if "invariant_prompt" in request:
        instruction = str(request["invariant_prompt"])
    elif language == "ja":
        image_note = "画像は左が前世代、右が現世代です。両者の見える差を読んでください。" if len(images) > 0 and request.get("generation_index", 0) else "画像は現世代です。見える物理だけを読んでください。"
        instruction = image_note + "\n現在までに知り得る事実:\n" + json.dumps(request, ensure_ascii=False, sort_keys=True)
    else:
        image_note = "The image places the previous generation on the left and the current generation on the right. Describe their visible difference." if len(images) > 0 and request.get("generation_index", 0) else "The image is the current generation. Describe only its visible physical features."
        instruction = image_note + "\nFacts available up to this generation:\n" + json.dumps(request, ensure_ascii=False, sort_keys=True)
    content: list[dict[str, Any]] = [{"type": "text", "text": instruction}]
    content.extend({"type": "image_url", "image_url": {"url": image}} for image in images)
    cache_key = _vision_cache_key(
        provider=provider,
        model_id=model_id,
        base_url=str(connection["base_url"]),
        language=language,
        request=request,
        images=images,
    )

    def request_completion() -> str:
        from openai import OpenAI

        client = OpenAI(
            base_url=connection["base_url"],
            api_key=connection.get("api_key") or "none",
            timeout=float(os.getenv("INKU_LLM_REQUEST_TIMEOUT_SECONDS", "180")),
            max_retries=0,
        )
        response = client.chat.completions.create(
            model=model_id,
            messages=[{"role": "system", "content": _system_prompt(language)}, {"role": "user", "content": content}],
            temperature=0.35,
            max_tokens=260,
        )
        return (response.choices[0].message.content or "").strip()

    try:
        return _cached_vision_response(cache_key, request_completion)
    except Exception as exc:
        if type(exc).__name__ in {"APITimeoutError", "ReadTimeout"}:
            raise TimeoutError("Vision provider timed out") from exc
        raise


def _invariant_prompt(language: str, invariants: dict[str, Any]) -> str:
    facts = json.dumps(invariants, ensure_ascii=False, sort_keys=True)
    if language == "en":
        return (
            "In one first-person paragraph, verbalize only the following mechanically computed invariants. "
            "Do not add causality, intent, evaluation, scores, or a story of progress. Facts:\n" + facts
        )
    return (
        "次の機械抽出された不変量だけを、一人称の短い結びとして言語化してください。"
        "因果、意図、評価、点数、進歩の物語を加えないでください。\n" + facts
    )


def evaluation_warnings(body: str, language: str) -> list[str]:
    found: list[str] = []
    lowered = body.lower()
    for word in _EVALUATION_WORDS.get(language, ()):
        if (word.lower() if language == "en" else word) in lowered:
            found.append(f"evaluation_word:{word}")
    if re.search(r"\b\d+(?:\.\d+)?\s*(?:/|点|stars?|score)", body, re.IGNORECASE):
        found.append("numeric_evaluation")
    return found


def _first_person(text: str, language: str) -> str:
    clean = text.strip()
    echoed_guidance = (
        "画像は左が前世代、右が現世代です。両者の見える差を読んでください。",
        "画像は現世代です。見える物理だけを読んでください。",
        "The image places the previous generation on the left and the current generation on the right. Describe their visible difference.",
        "The image is the current generation. Describe only its visible physical features.",
    )
    for prefix in echoed_guidance:
        if clean.startswith(prefix):
            clean = clean[len(prefix):].lstrip()
            break
    if not clean:
        clean = "見える差を特定できなかった。" if language == "ja" else "no visible difference could be identified."
    if language == "ja":
        return clean if any(marker in clean for marker in ("私", "わたし")) else f"私には、{clean}"
    return clean if re.search(r"\bI\b|\bme\b|\bmy\b", clean, re.IGNORECASE) else f"I see {clean}"


def generate_okugaki(
    branch: dict[str, Any],
    *,
    model: str,
    language: str,
    settings: dict[str, Any],
    reader: Callable[..., str] | None = None,
    at: int,
) -> dict[str, Any]:
    fact_sheet = build_fact_sheet(branch)
    read = reader or _vision_chat
    observations: list[str] = []
    for index, node in enumerate(branch["nodes"]):
        request = build_generation_request(fact_sheet, index, observations)
        source_svgs: list[str] = []
        if index and branch["nodes"][index - 1].get("history", {}).get("svg"):
            source_svgs.append(branch["nodes"][index - 1]["history"]["svg"])
        if node.get("history", {}).get("svg"):
            source_svgs.append(node["history"]["svg"])
        thumbnail = _vision_thumbnail_data_url(source_svgs)
        observation = read(
            model=model,
            language=language,
            request=request,
            images=[thumbnail] if thumbnail else [],
            settings=settings,
        )
        observations.append(_first_person(observation, language))
    conclusion = _first_person(
        read(
            model=model,
            language=language,
            request={"invariant_prompt": _invariant_prompt(language, fact_sheet["invariants"])},
            images=[],
            settings=settings,
        ),
        language,
    )
    timezone_name = os.getenv("INKU_TIMEZONE", "Asia/Tokyo")
    date = datetime.fromtimestamp(at / 1000, tz=ZoneInfo(timezone_name)).date().isoformat()
    signature = f"読み手: {model} / {date}" if language == "ja" else f"Reader: {model} / {date}"
    body = "\n\n".join([*observations, conclusion, signature])
    return {
        "target_node_id": fact_sheet["target_node_id"],
        "branch_snapshot": fact_sheet["branch_snapshot"],
        "model": model,
        "at": at,
        "language": language,
        "body": body,
        "signature": signature,
        "warnings": evaluation_warnings(body, language),
        "fact_sheet": fact_sheet,
    }
