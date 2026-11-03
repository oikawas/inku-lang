from io import BytesIO

from PIL import Image

from inku_server import animation_export


LAYERED_SVG = """<svg xmlns="http://www.w3.org/2000/svg" width="80" height="64">
<defs>
<clipPath id="clip"><rect width="80" height="64"/></clipPath>
<filter id="ink"><feColorMatrix values="1 0 0 0 0 0 1 0 0 0 0 0 1 0 0 0 0 0 1 0"/></filter>
<mask id="mask"><rect width="80" height="64" fill="white"/></mask>
</defs>
<rect id="background" width="80" height="64" fill="white"/>
<g id="art" clip-path="url(#clip)" filter="url(#ink)" transform="translate(1 2)">
<g id="stroke-1"><rect width="20" height="60" fill="red"/></g>
<g id="stroke-2" mask="url(#mask)"><rect x="20" width="20" height="60" fill="green"/></g>
<g id="stroke-3"><rect x="40" width="20" height="60" fill="blue"/></g>
</g></svg>"""


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


def test_line_animation_starts_complete_and_then_builds_up(monkeypatch):
    import json
    import inku_render

    monkeypatch.setattr(inku_render, "pipeline_line_animation", lambda _payload: json.dumps({
        "frames": [{"svg": "red"}, {"svg": "green"}, {"svg": "blue"}],
        "matches_saved_svg": False, "outcome": "complete",
    }).encode())
    monkeypatch.setattr(animation_export, "svg_to_png", lambda svg, height, font_files: _png(svg, height=height))
    payload, matches, outcome = animation_export.build_layer_animation(
        {}, output_format="gif", hold_seconds=0.3, replay="once", resolution="1k", height_px=64,
    )
    image = Image.open(BytesIO(payload))
    pixels = []
    for index in range(image.n_frames):
        image.seek(index)
        pixels.append(image.convert("RGB").getpixel((1, 1)))
    assert pixels == [(0, 0, 255), (255, 0, 0), (0, 128, 0), (0, 0, 255)]
    assert matches is False
    assert outcome == "complete"


def test_line_animation_reverse_plays_back_from_completed_sequence(monkeypatch):
    import json
    import inku_render

    monkeypatch.setattr(inku_render, "pipeline_line_animation", lambda _payload: json.dumps({
        "frames": [{"svg": "red"}, {"svg": "green"}, {"svg": "blue"}],
        "matches_saved_svg": True, "outcome": "complete",
    }).encode())
    monkeypatch.setattr(animation_export, "svg_to_png", lambda svg, height, font_files: _png(svg, height=height))
    payload, matches, _ = animation_export.build_layer_animation(
        {}, output_format="apng", replay="reverse", resolution="1k", height_px=64,
    )
    image = Image.open(BytesIO(payload))
    pixels = []
    for index in range(image.n_frames):
        image.seek(index)
        pixels.append(image.convert("RGB").getpixel((1, 1)))
    assert pixels == [(0, 0, 255), (255, 0, 0), (0, 128, 0), (0, 0, 255), (0, 128, 0), (255, 0, 0)]
    assert image.info["loop"] == 0
    assert matches is True


def test_saved_lock_digest_is_sent_in_document_format(monkeypatch):
    import json
    from types import SimpleNamespace
    from inku_server import pipeline_api, pipeline_runtime
    from inku_server.api_core.routers.history import _line_animation_request

    compiler = {"host": {}, "composition_seed": None, "error_policy": "omit_and_continue"}
    config = {"compiler": compiler, "definitions": [{"id": "saved"}], "language": "ja"}
    lock = {"qualified_name": "Test.word", "version": "1", "digest": "a" * 64}
    work = {"saved_config": config, "macro_catalog": {"definition_locks": [lock]}}

    class Settings:
        manifest = {"render": {"options": {"canvas": {"height": 1000}}, "clip": {}}}

        def config_for(self, _owner, source):
            return source["saved_config"]

    binding = SimpleNamespace(canvas_registry={"registry": {"formats": [{"id": "square", "width_units": 1, "height_units": 1}]}},
                              resolve_palette=lambda _request: json.dumps({"background": "white"}).encode())
    monkeypatch.setattr(pipeline_runtime, "get_service", lambda: SimpleNamespace(store=None, binding=binding, config_for=Settings().config_for))
    monkeypatch.setattr(pipeline_api, "saved_work_parent", lambda *_args: (None, work))
    request = _line_animation_request("owner", {"id": "id", "ddl": "円", "svg": "svg", "score": {},
                                                       "render_seed": 1, "render_color_map": {"white": "#fff"}}, True)
    assert request["document"]["macro_locks"][0]["digest"] == "sha256:" + "a" * 64
    assert lock["digest"] == "a" * 64
    assert request["definitions"] == [{"id": "saved"}]
