"""Build APNG and GIF files from saved inku performances."""

from __future__ import annotations

from io import BytesIO
from typing import Literal

from inku_analysis.rasterizer import svg_to_png
from PIL import Image

AnimationFormat = Literal["apng", "gif"]
AnimationPattern = Literal["cut", "crossfade", "fade_white", "slide"]

RESOLUTION_HEIGHTS = {"1k": 1080, "4k": 2160, "8k": 4320}
TRANSITION_STEPS = {"1k": 6, "4k": 4, "8k": 2}
MAX_ENCODED_PIXELS = 600_000_000


def _fit_frame(svg: str, width: int, height: int) -> Image.Image:
    rendered = Image.open(BytesIO(svg_to_png(svg, height=height))).convert("RGBA")
    if rendered.width > width or rendered.height > height:
        rendered.thumbnail((width, height), Image.Resampling.LANCZOS)
    frame = Image.new("RGBA", (width, height), "white")
    x = (width - rendered.width) // 2
    y = (height - rendered.height) // 2
    frame.alpha_composite(rendered, (x, y))
    rendered.close()
    return frame


def _transition_frames(
    current: Image.Image,
    following: Image.Image,
    pattern: AnimationPattern,
    steps: int,
) -> list[Image.Image]:
    if pattern == "cut":
        return []
    frames: list[Image.Image] = []
    white = Image.new("RGBA", current.size, "white") if pattern == "fade_white" else None
    try:
        for step in range(1, steps + 1):
            progress = step / (steps + 1)
            if pattern == "crossfade":
                frames.append(Image.blend(current, following, progress))
            elif white is not None:
                if progress < 0.5:
                    frames.append(Image.blend(current, white, progress * 2))
                else:
                    frames.append(Image.blend(white, following, (progress - 0.5) * 2))
            else:
                frame = Image.new("RGBA", current.size, "white")
                offset = round(current.width * progress)
                frame.alpha_composite(current, (-offset, 0))
                frame.alpha_composite(following, (current.width - offset, 0))
                frames.append(frame)
        return frames
    finally:
        if white is not None:
            white.close()


def build_animation(
    svgs: list[str],
    *,
    output_format: AnimationFormat,
    pattern: AnimationPattern,
    hold_seconds: float,
    resolution: Literal["1k", "4k", "8k"],
    height_px: int | None = None,
) -> bytes:
    """Rasterize saved SVGs and encode a looping APNG or GIF."""
    if len(svgs) < 2:
        raise ValueError("at least two works are required")
    height = height_px if height_px is not None else RESOLUTION_HEIGHTS[resolution]
    if height_px is not None and not 64 <= height <= 12000:
        raise ValueError("animation height must be between 64 and 12000 pixels")
    transition_steps = TRANSITION_STEPS[resolution] if height_px is None else (6 if height <= 1080 else 4 if height <= 2160 else 2)
    first_png = Image.open(BytesIO(svg_to_png(svgs[0], height=height))).convert("RGBA")
    width = first_png.width
    transition_count = 0 if pattern == "cut" else transition_steps
    encoded_frame_count = len(svgs) + (len(svgs) - 1) * transition_count
    if width * height * encoded_frame_count > MAX_ENCODED_PIXELS:
        first_png.close()
        raise ValueError("this resolution and transition pattern produce too many frames")
    first_frame = Image.new("RGBA", (width, height), "white")
    first_frame.alpha_composite(first_png, ((width - first_png.width) // 2, (height - first_png.height) // 2))
    frames = [first_frame, *[_fit_frame(svg, width, height) for svg in svgs[1:]]]
    first_png.close()

    hold_ms = max(100, round(hold_seconds * 1000))
    transition_ms = max(40, min(120, hold_ms // 4))
    encoded_frames: list[Image.Image] = []
    durations: list[int] = []
    try:
        for index, frame in enumerate(frames):
            encoded_frames.append(frame.copy())
            durations.append(hold_ms)
            if index >= len(frames) - 1:
                continue
            transitions = _transition_frames(
                frame,
                frames[index + 1],
                pattern,
                transition_steps,
            )
            encoded_frames.extend(transitions)
            durations.extend([transition_ms] * len(transitions))

        output = BytesIO()
        if output_format == "apng":
            encoded_frames[0].save(
                output,
                format="PNG",
                save_all=True,
                append_images=encoded_frames[1:],
                duration=durations,
                loop=0,
                disposal=2,
                blend=0,
                compress_level=6,
            )
        else:
            gif_frames = [
                frame.convert("P", palette=Image.Palette.ADAPTIVE, colors=256)
                for frame in encoded_frames
            ]
            try:
                gif_frames[0].save(
                    output,
                    format="GIF",
                    save_all=True,
                    append_images=gif_frames[1:],
                    duration=durations,
                    loop=0,
                    disposal=2,
                    optimize=False,
                )
            finally:
                for frame in gif_frames:
                    frame.close()
        return output.getvalue()
    finally:
        for frame in encoded_frames:
            frame.close()
        for frame in frames:
            frame.close()
