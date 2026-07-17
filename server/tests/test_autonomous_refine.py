from __future__ import annotations

import pytest

from inku_server.autonomous_refine import vision_refine_advice

SVG = '<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"><circle cx="5" cy="5" r="2"/></svg>'


def test_vision_refine_advice_is_observational_and_kind_is_bounded():
    calls = []

    def reader(**kwargs):
        calls.append(kwargs)
        return '{"observation":"A black circle is centered.","next_direction":"Try moving the circle left.","suggested_kind":"layout_variation"}'

    result = vision_refine_advice(
        svg=SVG,
        instruction="a quiet circle",
        direction="leave more space",
        enabled_kinds=["reinterpretation", "layout_variation"],
        model="test:vision",
        language="en",
        settings={},
        reader=reader,
    )

    assert result == {
        "observation": "A black circle is centered.",
        "next_direction": "Try moving the circle left.",
        "suggested_kind": "layout_variation",
        "model": "test:vision",
    }
    assert calls[0]["image"].startswith("data:image/png;base64,")
    assert calls[0]["payload"]["constraints"]["no_accept_reject"] is True


def test_vision_refine_advice_falls_back_to_enabled_kind_and_rejects_invalid_json():
    result = vision_refine_advice(
        svg=SVG,
        instruction="circle",
        direction="",
        enabled_kinds=["touch_variation"],
        model="test:vision",
        language="ja",
        settings={},
        reader=lambda **_: '{"observation":"円が見える","next_direction":"線を揺らす","suggested_kind":"catalog_change"}',
    )
    assert result["suggested_kind"] == "touch_variation"

    with pytest.raises(ValueError, match="invalid refinement advice JSON"):
        vision_refine_advice(
            svg=SVG,
            instruction="circle",
            direction="",
            enabled_kinds=["touch_variation"],
            model="test:vision",
            language="ja",
            settings={},
            reader=lambda **_: "not json",
        )
