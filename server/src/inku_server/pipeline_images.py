"""Transient image inputs and review drawings for the shared pipeline.

Only image references cross the durable pipeline boundary. Pixel bytes live in
this worker until the run ends; an upload waiting to start expires as well.
"""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
import threading
import time
import warnings
from dataclasses import dataclass
from io import BytesIO

from PIL import Image, ImageOps, UnidentifiedImageError

from .pipeline_candidate import CandidateHostError, _bytes


IMAGE_UPLOAD_MAX_BYTES = 32 * 1024 * 1024
IMAGE_UPLOAD_TTL_SECONDS = 15 * 60


def image_reference(data: bytes, media_type: str, width: int, height: int) -> dict:
    return {"media_type": media_type, "width": width, "height": height,
            "sha256": hashlib.sha256(data).hexdigest(), "byte_len": len(data)}


def image_data_url(data: bytes, media_type: str) -> str:
    return f"data:{media_type};base64," + base64.b64encode(data).decode("ascii")


@dataclass(frozen=True)
class PreparedImage:
    jpeg: bytes
    reference: dict
    original_width: int
    original_height: int
    nearest_format_id: str
    thumbnail: str

    def authoring_input(self) -> dict:
        return {"sent": self.reference, "original_width": self.original_width,
                "original_height": self.original_height}

    def view(self, image_id: str) -> dict:
        return {"image_id": image_id, "thumbnail": self.thumbnail,
                "original_width": self.original_width, "original_height": self.original_height,
                "width": self.reference["width"], "height": self.reference["height"],
                "nearest_format_id": self.nearest_format_id}


def prepare_image(binding, raw: bytes) -> PreparedImage:
    policy_fn = getattr(binding, "image_input_policy", None)
    canvas_fn = getattr(binding, "image_canvas", None)
    if not callable(policy_fn) or not callable(canvas_fn):
        raise CandidateHostError("binding_image_unavailable")
    if not raw:
        raise CandidateHostError("image_invalid")
    if len(raw) > IMAGE_UPLOAD_MAX_BYTES:
        raise CandidateHostError("image_too_large")
    policy = json.loads(policy_fn())["policy"]
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(raw)) as source:
                if source.format not in {"JPEG", "PNG", "GIF", "TIFF"}:
                    raise CandidateHostError("image_invalid")
                source.seek(0)
                oriented = ImageOps.exif_transpose(source)
                width, height = oriented.size
                canvas = json.loads(canvas_fn(_bytes({"original": [width, height]})))
                if "error" in canvas:
                    raise CandidateHostError("image_invalid")
                # A transparent input is viewed on paper, rather than on the
                # black RGB values hidden behind its transparent pixels.
                rgba = oriented.convert("RGBA")
                rgb = Image.new("RGB", rgba.size, "white")
                rgb.paste(rgba, mask=rgba.getchannel("A"))
                rgb = rgb.resize(tuple(canvas["sent"]), Image.Resampling.LANCZOS)
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError,
            Image.DecompressionBombWarning) as error:
        raise CandidateHostError("image_invalid") from error
    encoded = BytesIO()
    rgb.save(encoded, format="JPEG", quality=int(policy["jpeg_quality"]))
    jpeg = encoded.getvalue()
    if len(jpeg) > int(policy["max_bytes"]):
        raise CandidateHostError("image_too_large")
    thumbnail = rgb.copy()
    thumbnail.thumbnail((256, 256), Image.Resampling.LANCZOS)
    encoded_thumb = BytesIO()
    thumbnail.save(encoded_thumb, format="JPEG", quality=70)
    return PreparedImage(jpeg, image_reference(jpeg, "image/jpeg", *rgb.size), width, height,
                         canvas["nearest_format_id"], image_data_url(encoded_thumb.getvalue(), "image/jpeg"))


class PendingImages:
    """Bounded, owner-scoped uploads awaiting one run in this worker."""

    def __init__(self, capacity: int, *, clock=time.monotonic):
        self.capacity = capacity
        self.clock = clock
        self._items: dict[tuple[str, str], tuple[float, PreparedImage]] = {}
        self._lock = threading.RLock()
        self._timer: threading.Timer | None = None

    def _schedule_expiry(self) -> None:
        if self._timer is not None:
            self._timer.cancel()
        self._timer = None
        if self._items:
            delay = max(0.01, min(value[0] for value in self._items.values()) - self.clock())
            self._timer = threading.Timer(delay, self._expire_waiting)
            self._timer.daemon = True
            self._timer.start()

    def _expire_waiting(self) -> None:
        with self._lock:
            self._expire()
            self._schedule_expiry()

    def _expire(self) -> None:
        now = self.clock()
        for key, (expires, _) in list(self._items.items()):
            if expires <= now:
                del self._items[key]

    def add(self, owner: str, image: PreparedImage) -> dict:
        with self._lock:
            self._expire()
            if len(self._items) >= self.capacity:
                # Discard only a pending upload, never another running image.
                oldest = min(self._items, key=lambda key: self._items[key][0])
                del self._items[oldest]
            image_id = secrets.token_urlsafe(24)
            self._items[(owner, image_id)] = (self.clock() + IMAGE_UPLOAD_TTL_SECONDS, image)
            self._schedule_expiry()
            return image.view(image_id)

    def get(self, owner: str, image_id: str) -> PreparedImage:
        with self._lock:
            self._expire()
            item = self._items.get((owner, image_id))
            if item is None:
                raise CandidateHostError("image_missing")
            return item[1]

    def consume(self, owner: str, image_id: str) -> None:
        with self._lock:
            self._items.pop((owner, image_id), None)
            self._schedule_expiry()

    def clear(self) -> None:
        with self._lock:
            self._items.clear()
            self._schedule_expiry()


def review_drawing(binding, snapshot: dict, render: dict, *, owner: str) -> tuple[dict, str] | None:
    """Use the core's pending review canvas and the work's actual paint settings."""
    from inku_analysis.rasterizer import svg_to_png
    from .api_core.rendering import _generated_svg_limit_bytes, _render_capacity, _validate_generated_svg

    draw = getattr(binding, "image_review_svg", None)
    if not callable(draw):
        return None
    payload = snapshot["action"]["payload"]
    limit = _generated_svg_limit_bytes()
    request = {**render, "max_svg_bytes": limit}
    with _render_capacity(owner):
        answer = json.loads(draw(_bytes(snapshot), _bytes(request)))
        if not isinstance(answer.get("svg"), str):
            return None
        svg = answer["svg"]
        _validate_generated_svg(svg, limit)
        png = svg_to_png(svg, width=int(payload["width"]), height=int(payload["height"]))
    with Image.open(BytesIO(png)) as raster:
        if raster.size != (payload["width"], payload["height"]):
            return None
    reference = image_reference(png, "image/png", int(payload["width"]), int(payload["height"]))
    return reference, image_data_url(png, "image/png")
