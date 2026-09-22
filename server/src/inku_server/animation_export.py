"""Build APNG and GIF files from saved inku performances."""

from __future__ import annotations

from collections.abc import Iterator
from io import BytesIO
from typing import Literal
from xml.etree import ElementTree

from inku_analysis.rasterizer import svg_to_png
from PIL import Image

AnimationFormat = Literal["apng", "gif"]
AnimationPattern = Literal["cut", "crossfade", "fade_white", "slide"]
LayerReplay = Literal["restart", "reverse", "once"]

RESOLUTION_HEIGHTS = {"1k": 1080, "4k": 2160, "8k": 4320}
TRANSITION_STEPS = {"1k": 6, "4k": 4, "8k": 2}
MAX_ENCODED_PIXELS = 600_000_000
GIF_MAX_FRAME_DURATION_MS = 655_350

_NON_VISUAL_TAGS = {"defs", "desc", "metadata", "style", "title"}


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


def _encode_frames(
    frames: list[Image.Image],
    durations: list[int],
    output_format: AnimationFormat,
    *,
    play_once: bool = False,
) -> bytes:
    output = BytesIO()
    if output_format == "apng":
        frames[0].save(
            output,
            format="PNG",
            save_all=True,
            append_images=frames[1:],
            duration=durations,
            loop=1 if play_once else 0,
            disposal=2,
            blend=0,
            compress_level=6,
        )
    else:
        gif_frames = [
            frame.convert("P", palette=Image.Palette.ADAPTIVE, colors=256)
            for frame in frames
        ]
        try:
            options = {
                "format": "GIF",
                "save_all": True,
                "append_images": gif_frames[1:],
                "duration": durations,
                "disposal": 2,
                "optimize": False,
            }
            if not play_once:
                options["loop"] = 0
            gif_frames[0].save(output, **options)
        finally:
            for frame in gif_frames:
                frame.close()
    return output.getvalue()


def _local_name(element: ElementTree.Element) -> str:
    return element.tag.rsplit("}", 1)[-1] if isinstance(element.tag, str) else ""


def _is_background(element: ElementTree.Element) -> bool:
    element_id = element.get("id", "").casefold()
    return "background" in element_id


def _visual_children(
    parent: ElementTree.Element,
    *,
    root_children: bool = False,
) -> list[ElementTree.Element]:
    visual = [
        child
        for child in parent
        if _local_name(child) not in _NON_VISUAL_TAGS
    ]
    has_explicit_background = any(_is_background(child) for child in visual)
    children = [child for child in visual if not _is_background(child)]
    if (
        root_children
        and not has_explicit_background
        and len(children) > 1
        and _local_name(children[0]) == "rect"
    ):
        return children[1:]
    return children


def _layer_records(
    root: ElementTree.Element,
) -> list[tuple[ElementTree.Element, int, ElementTree.Element]]:
    containers = [
        element
        for element in root.iter()
        if element.get("id", "").casefold().startswith("layer_")
        and not _is_background(element)
    ]
    if containers:
        records = []
        for container in containers:
            visible = set(_visual_children(container))
            records.extend(
                (container, index, child)
                for index, child in enumerate(container)
                if child in visible
            )
        if records:
            return records

    root_visible = _visual_children(root, root_children=True)
    if len(root_visible) == 1 and _local_name(root_visible[0]) == "g":
        wrapper = root_visible[0]
        wrapper_visible = set(_visual_children(wrapper))
        records = [
            (wrapper, index, child)
            for index, child in enumerate(wrapper)
            if child in wrapper_visible
        ]
        if records:
            return records

    root_visible_set = set(root_visible)
    return [
        (root, index, child)
        for index, child in enumerate(root)
        if child in root_visible_set
    ]


def _frame_layer_counts(layer_count: int, frame_count: int) -> list[tuple[int, int]]:
    segments = frame_count - 1
    requested = [
        (2 * layer_count * step + segments) // (2 * segments)
        for step in range(frame_count)
    ]
    consolidated: list[tuple[int, int]] = []
    for count in requested:
        if consolidated and consolidated[-1][0] == count:
            previous_count, repeats = consolidated[-1]
            consolidated[-1] = (previous_count, repeats + 1)
        else:
            consolidated.append((count, 1))
    return consolidated


def _encoded_repeats(plan: list[tuple[int, int]], replay: LayerReplay) -> list[int]:
    repeats = [repeat_count for _layer_count, repeat_count in plan]
    if replay != "reverse":
        return repeats
    repeats[0] = repeats[0] * 2 - 1
    repeats[-1] = repeats[-1] * 2 - 1
    return [*repeats, *[repeat_count for _count, repeat_count in plan[-2:0:-1]]]


def _prepare_progressive_svg(
    svg: str,
    frame_count: int,
) -> tuple[
    ElementTree.Element,
    list[tuple[ElementTree.Element, int, ElementTree.Element]],
    list[tuple[int, int]],
]:
    try:
        root = ElementTree.fromstring(svg)
    except ElementTree.ParseError as error:
        raise ValueError("saved SVG is not valid XML") from error

    records = _layer_records(root)
    if not records:
        raise ValueError("saved SVG has no drawable layers")
    for parent, _index, element in records:
        parent.remove(element)
    return root, records, _frame_layer_counts(len(records), frame_count)


def _progressive_svg_states_from_prepared(
    svg: str,
    root: ElementTree.Element,
    records: list[tuple[ElementTree.Element, int, ElementTree.Element]],
    plan: list[tuple[int, int]],
) -> Iterator[tuple[str, int]]:
    revealed = 0
    for target, repeats in plan:
        while revealed < target:
            parent, index, element = records[revealed]
            parent.insert(index, element)
            revealed += 1
        state_svg = svg if target == len(records) else ElementTree.tostring(root, encoding="unicode")
        yield state_svg, repeats


def _progressive_svg_states(svg: str, frame_count: int) -> Iterator[tuple[str, int]]:
    root, records, plan = _prepare_progressive_svg(svg, frame_count)
    return _progressive_svg_states_from_prepared(svg, root, records, plan)


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

        return _encode_frames(encoded_frames, durations, output_format)
    finally:
        for frame in encoded_frames:
            frame.close()
        for frame in frames:
            frame.close()


def build_layer_animation(
    svg: str,
    *,
    output_format: AnimationFormat,
    frame_count: int = 12,
    hold_seconds: float = 0.3,
    replay: LayerReplay = "restart",
    resolution: Literal["1k", "4k", "8k"],
    height_px: int | None = None,
) -> bytes:
    """Build a progressive animation from the layers of one saved SVG."""
    if not 2 <= frame_count <= 120:
        raise ValueError("layer animation frame count must be between 2 and 120")
    if replay not in {"restart", "reverse", "once"}:
        raise ValueError("unsupported layer animation replay setting")
    height = height_px if height_px is not None else RESOLUTION_HEIGHTS[resolution]
    if height_px is not None and not 64 <= height <= 12000:
        raise ValueError("animation height must be between 64 and 12000 pixels")

    root, records, plan = _prepare_progressive_svg(svg, frame_count)
    hold_ms = max(100, round(hold_seconds * 1000))
    encoded_repeats = _encoded_repeats(plan, replay)
    if output_format == "gif" and any(
        hold_ms * repeats > GIF_MAX_FRAME_DURATION_MS for repeats in encoded_repeats
    ):
        raise ValueError("GIF cannot preserve this frame count and animation interval")
    states = _progressive_svg_states_from_prepared(svg, root, records, plan)
    first_svg, first_repeats = next(states)
    first_png = Image.open(BytesIO(svg_to_png(first_svg, height=height))).convert("RGBA")
    width = first_png.width
    encoded_frame_count = len(encoded_repeats)
    if width * height * encoded_frame_count > MAX_ENCODED_PIXELS:
        first_png.close()
        raise ValueError("this resolution and replay setting produce too many frames")

    first_frame = Image.new("RGBA", (width, height), "white")
    first_frame.alpha_composite(
        first_png,
        ((width - first_png.width) // 2, (height - first_png.height) // 2),
    )
    first_png.close()
    forward_frames = [first_frame]
    forward_durations = [hold_ms * first_repeats]
    reverse_frames: list[Image.Image] = []
    try:
        for state_svg, repeats in states:
            forward_frames.append(_fit_frame(state_svg, width, height))
            forward_durations.append(hold_ms * repeats)

        encoded_frames = forward_frames
        durations = forward_durations
        if replay == "reverse":
            reverse_frames = [frame.copy() for frame in forward_frames[-2:0:-1]]
            encoded_frames = [*forward_frames, *reverse_frames]
            durations = [hold_ms * repeats for repeats in encoded_repeats]
        return _encode_frames(
            encoded_frames,
            durations,
            output_format,
            play_once=replay == "once",
        )
    finally:
        for frame in reverse_frames:
            frame.close()
        for frame in forward_frames:
            frame.close()
