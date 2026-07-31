from io import BytesIO

from PIL import Image

from inku_server import animation_export


def _png(color: str, width: int = 40, height: int = 24) -> bytes:
    output = BytesIO()
    Image.new("RGBA", (width, height), color).save(output, format="PNG")
    return output.getvalue()


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
