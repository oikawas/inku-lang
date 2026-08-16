from __future__ import annotations

import pytest

from inku_server.autonomous_refine import vision_refine_advice

SVG = '<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"><circle cx="5" cy="5" r="2"/></svg>'


def test_vision_refine_advice_is_observational_and_kind_is_bounded():
    calls = []

    def reader(**kwargs):
        calls.append(kwargs)
        return '{"observation":"A black circle is centered.","next_direction":"Try moving the circle left.","suggested_kind":"layout_change"}'

    result = vision_refine_advice(
        svg=SVG,
        instruction="a quiet circle",
        direction="leave more space",
        enabled_kinds=["reinterpretation", "layout_change"],
        model="test:vision",
        language="en",
        settings={},
        reader=reader,
    )

    assert result == {
        "observation": "A black circle is centered.",
        "next_direction": "Try moving the circle left.",
        "suggested_kind": "layout_change",
        "model": "test:vision",
    }
    assert calls[0]["image"].startswith("data:image/png;base64,")
    assert calls[0]["payload"]["constraints"]["no_accept_reject"] is True


def test_vision_refine_advice_falls_back_to_enabled_kind_and_rejects_invalid_json():
    result = vision_refine_advice(
        svg=SVG,
        instruction="circle",
        direction="",
        enabled_kinds=["touch_change"],
        model="test:vision",
        language="ja",
        settings={},
        reader=lambda **_: '{"observation":"円が見える","next_direction":"線を揺らす","suggested_kind":"catalog_change"}',
    )
    assert result["suggested_kind"] == "touch_change"

    with pytest.raises(ValueError, match="invalid refinement advice JSON"):
        vision_refine_advice(
            svg=SVG,
            instruction="circle",
            direction="",
            enabled_kinds=["touch_change"],
            model="test:vision",
            language="ja",
            settings={},
            reader=lambda **_: "not json",
        )


def _advise(raw: str) -> dict[str, str]:
    return vision_refine_advice(
        svg=SVG,
        instruction="a quiet circle",
        direction="",
        enabled_kinds=["layout_change"],
        model="test:vision",
        language="en",
        settings={},
        reader=lambda **_: raw,
    )


BODY = '{"observation":"A circle sits low.","next_direction":"Lift it.","suggested_kind":"layout_change"}'


@pytest.mark.parametrize(
    "raw",
    [
        pytest.param(f"```json\n{BODY}\n```", id="fenced-json"),
        pytest.param(f"```\n{BODY}\n```", id="fenced-bare"),
        pytest.param(f"```JSON\n{BODY}```", id="fenced-uppercase-no-newline"),
    ],
)
def test_a_fenced_answer_is_read(raw):
    """T-139  a fenced answer is read, not rejected

    The fence strip was written as `\\s` inside a raw string, so it matched a
    literal backslash and never fired: a vision model that fences -- which is
    the default for gemma -- got "invalid refinement advice JSON" every time.
    """
    assert _advise(raw)["observation"] == "A circle sits low."


def test_prose_either_side_of_the_object_is_read():
    """T-140  an object wrapped in prose is read"""
    raw = f"Here is the advice you asked for:\n{BODY}\nLet me know if you want another pass."
    assert _advise(raw)["next_direction"] == "Lift it."


@pytest.mark.parametrize(
    "raw",
    [
        pytest.param("not json", id="no-braces"),
        pytest.param("```json\nnot json\n```", id="fenced-but-not-json"),
        pytest.param('{"observation": "unclosed"', id="unclosed-object"),
        pytest.param("[1, 2, 3]", id="a-list-is-not-advice"),
    ],
)
def test_an_answer_that_is_not_advice_still_fails(raw):
    """T-141  unwrapping did not make the guard vacuous

    Taking the fence and the prose off must not turn "the model answered with
    something else" into a pass. Each of these reaches the parser and is
    refused there, which is where it was refused before.
    """
    with pytest.raises(ValueError, match="invalid refinement advice"):
        _advise(raw)
