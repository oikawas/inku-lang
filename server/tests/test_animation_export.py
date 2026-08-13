from io import BytesIO

from PIL import Image

from inku_server import animation_export


def _png(color: str, width: int = 40, height: int = 24) -> bytes:
    output = BytesIO()
    Image.new("RGBA", (width, height), color).save(output, format="PNG")
    return output.getvalue()


def test_fade_white_passes_through_white_between_frames():
    current = Image.new("RGBA", (4, 2), "red")
    following = Image.new("RGBA", (4, 2), "blue")
    try:
        frames = animation_export._transition_frames(current, following, "fade_white", 3)
        assert [frame.convert("RGB").getpixel((2, 1)) for frame in frames] == [
            (255, 127, 127),
            (255, 255, 255),
            (127, 127, 255),
        ]
    finally:
        current.close()
        following.close()
        for frame in locals().get("frames", []):
            frame.close()


def test_slide_moves_both_frames_across_the_canvas():
    current = Image.new("RGBA", (4, 2), "red")
    following = Image.new("RGBA", (4, 2), "blue")
    try:
        frames = animation_export._transition_frames(current, following, "slide", 1)
        pixels = frames[0].convert("RGB")
        assert [pixels.getpixel((x, 1)) for x in range(4)] == [
            (255, 0, 0),
            (255, 0, 0),
            (0, 0, 255),
            (0, 0, 255),
        ]
    finally:
        current.close()
        following.close()
        for frame in locals().get("frames", []):
            frame.close()


def test_builds_looping_apng_in_input_order(monkeypatch):
    colors = iter(["red", "blue"])
    monkeypatch.setattr(animation_export, "svg_to_png", lambda _svg, height: _png(next(colors), height=height))
    monkeypatch.setitem(animation_export.RESOLUTION_HEIGHTS, "1k", 24)
    payload = animation_export.build_animation(
        ["first", "second"],
        output_format="apng",
        pattern="cut",
        hold_seconds=1.25,
        resolution="1k",
    )

    image = Image.open(BytesIO(payload))
    assert image.format == "PNG"
    assert image.n_frames == 2
    assert image.info["loop"] == 0
    assert image.info["duration"] == 1250.0
    image.seek(0)
    assert image.convert("RGB").getpixel((20, 12)) == (255, 0, 0)
    image.seek(1)
    assert image.convert("RGB").getpixel((20, 12)) == (0, 0, 255)


def test_4k_and_8k_presets_use_their_height_and_transition_steps(monkeypatch):
    assert animation_export.RESOLUTION_HEIGHTS["4k"] == 2160
    assert animation_export.RESOLUTION_HEIGHTS["8k"] == 4320
    requested_heights = []

    def fake_rasterize(svg, height):
        requested_heights.append(height)
        return _png("red" if svg == "first" else "blue", height=height)

    monkeypatch.setattr(animation_export, "svg_to_png", fake_rasterize)
    monkeypatch.setitem(animation_export.RESOLUTION_HEIGHTS, "4k", 40)
    monkeypatch.setitem(animation_export.RESOLUTION_HEIGHTS, "8k", 48)
    for resolution, expected_height, expected_steps in (("4k", 40, 4), ("8k", 48, 2)):
        payload = animation_export.build_animation(
            ["first", "second"],
            output_format="apng",
            pattern="crossfade",
            hold_seconds=1,
            resolution=resolution,
        )
        image = Image.open(BytesIO(payload))
        assert image.height == expected_height
        assert image.n_frames == 2 + expected_steps
    assert requested_heights == [40, 40, 48, 48]


def test_encoded_pixel_limit_accepts_boundary_and_rejects_one_pixel_over(monkeypatch):
    assert animation_export.MAX_ENCODED_PIXELS == 600_000_000
    monkeypatch.setattr(animation_export, "svg_to_png", lambda svg, height: _png("red" if svg == "first" else "blue", width=10, height=height))
    monkeypatch.setitem(animation_export.RESOLUTION_HEIGHTS, "1k", 10)
    monkeypatch.setitem(animation_export.TRANSITION_STEPS, "1k", 3)
    monkeypatch.setattr(animation_export, "MAX_ENCODED_PIXELS", 500)

    payload = animation_export.build_animation(
        ["first", "second"],
        output_format="gif",
        pattern="crossfade",
        hold_seconds=1,
        resolution="1k",
    )
    assert Image.open(BytesIO(payload)).n_frames == 5

    monkeypatch.setattr(animation_export, "MAX_ENCODED_PIXELS", 499)
    try:
        animation_export.build_animation(
            ["first", "second"],
            output_format="gif",
            pattern="crossfade",
            hold_seconds=1,
            resolution="1k",
        )
    except ValueError as error:
        assert str(error) == "this resolution and transition pattern produce too many frames"
    else:
        raise AssertionError("an animation above the encoded pixel limit should fail")


def test_builds_gif_with_transition_frames(monkeypatch):
    colors = iter(["red", "blue"])
    monkeypatch.setattr(animation_export, "svg_to_png", lambda _svg, height: _png(next(colors), height=height))
    monkeypatch.setitem(animation_export.RESOLUTION_HEIGHTS, "1k", 24)
    monkeypatch.setitem(animation_export.TRANSITION_STEPS, "1k", 3)
    payload = animation_export.build_animation(
        ["first", "second"],
        output_format="gif",
        pattern="crossfade",
        hold_seconds=0.5,
        resolution="1k",
    )

    image = Image.open(BytesIO(payload))
    assert image.format == "GIF"
    assert image.n_frames == 5
    assert image.info["loop"] == 0


def test_builds_animation_at_custom_height(monkeypatch):
    requested_heights = []

    def fake_rasterize(_svg, height):
        requested_heights.append(height)
        return _png("green", height=height)

    monkeypatch.setattr(animation_export, "svg_to_png", fake_rasterize)
    payload = animation_export.build_animation(
        ["first", "second"],
        output_format="apng",
        pattern="cut",
        hold_seconds=1,
        resolution="1k",
        height_px=150,
    )

    image = Image.open(BytesIO(payload))
    assert image.height == 150
    assert requested_heights == [150, 150]


def test_custom_height_reproduces_the_preset_transition_ladder(monkeypatch):
    # The web client now sends height_px for every choice, including 1k / 4k / 8k,
    # so a preset arrives at the server as a raw height. The derived ladder has to
    # put the same number of frames on the wire as the preset route did, otherwise
    # every existing export silently changes length.
    # Distinct colors: an APNG writer collapses identical consecutive frames, so
    # a single flat color would hide the frame count this test is about.
    monkeypatch.setattr(
        animation_export, "svg_to_png",
        lambda svg, height: _png("red" if svg == "first" else "blue", height=height),
    )
    for resolution, height in animation_export.RESOLUTION_HEIGHTS.items():
        preset = Image.open(BytesIO(animation_export.build_animation(
            ["first", "second"], output_format="apng", pattern="crossfade",
            hold_seconds=1, resolution=resolution,
        )))
        custom = Image.open(BytesIO(animation_export.build_animation(
            ["first", "second"], output_format="apng", pattern="crossfade",
            hold_seconds=1, resolution=resolution, height_px=height,
        )))
        expected = 2 + animation_export.TRANSITION_STEPS[resolution]
        assert preset.n_frames == expected
        assert custom.n_frames == expected


def test_derived_transition_ladder_steps_down_with_height(monkeypatch):
    # A height between the presets picks the step count of the nearest preset at or
    # above it. Flattening the ladder to one constant must fail here.
    monkeypatch.setattr(
        animation_export, "svg_to_png",
        lambda svg, height: _png("red" if svg == "first" else "blue", height=height),
    )
    for height, expected_steps in ((64, 6), (1080, 6), (1081, 4), (2160, 4), (2161, 2), (4320, 2)):
        payload = animation_export.build_animation(
            ["first", "second"], output_format="apng", pattern="crossfade",
            hold_seconds=1, resolution="1k", height_px=height,
        )
        assert Image.open(BytesIO(payload)).n_frames == 2 + expected_steps


def test_rejects_custom_height_outside_supported_range():
    try:
        animation_export.build_animation(
            ["first", "second"],
            output_format="apng",
            pattern="cut",
            hold_seconds=1,
            resolution="1k",
            height_px=63,
        )
    except ValueError as error:
        assert str(error) == "animation height must be between 64 and 12000 pixels"
    else:
        raise AssertionError("out-of-range animation height should fail")


def test_requires_two_works():
    try:
        animation_export.build_animation(
            ["only"],
            output_format="apng",
            pattern="cut",
            hold_seconds=1,
            resolution="1k",
        )
    except ValueError as error:
        assert str(error) == "at least two works are required"
    else:
        raise AssertionError("single-work export should fail")
