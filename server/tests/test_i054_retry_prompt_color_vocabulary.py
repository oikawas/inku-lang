from __future__ import annotations

from typing import get_args

import pytest

from inku_server.api_core.routers import render as render_routes
from inku_server.schema import Color, Score


_COLOR_LINE = {
    "en": ("Allowed colors: ", "."),
    "ja": ("使用できる color: ", "。"),
}


def _retry_colors(prompt: str, *, lang: str) -> tuple[str, ...]:
    prefix, suffix = _COLOR_LINE[lang]
    line = next(line for line in prompt.splitlines() if line.startswith(prefix))
    assert line.endswith(suffix)
    return tuple(line.removeprefix(prefix).removesuffix(suffix).split(", "))


@pytest.mark.parametrize("lang", ["ja", "en"])
def test_retry_prompt_uses_the_ordered_score_color_vocabulary(lang: str) -> None:
    expected = get_args(Color)
    actual = _retry_colors(
        render_routes._compose_retry_prompt(reason="empty_instructions", lang=lang),
        lang=lang,
    )

    assert actual == expected
    assert len(actual) == len(set(actual))
    assert len(actual) == len(expected)


@pytest.mark.parametrize("lang", ["ja", "en"])
def test_empty_score_retry_receives_the_ordered_score_color_vocabulary(
    monkeypatch: pytest.MonkeyPatch,
    lang: str,
) -> None:
    monkeypatch.delenv("INKU_STAGE2_COMPOSE_RETRY_LIMIT", raising=False)
    prompts: list[str | None] = []

    def fake_compose(ddl: str, **kwargs: object) -> tuple[Score, int, int]:
        prompts.append(kwargs.get("system_prompt"))
        if len(prompts) == 1:
            return Score.model_validate({"instructions": []}), 1, 2
        return (
            Score.model_validate(
                {
                    "instructions": [
                        {
                            "primitive": "circle",
                            "center": [0.5, 0.5],
                            "radius": 0.1,
                        }
                    ]
                }
            ),
            3,
            4,
        )

    monkeypatch.setattr(render_routes, "compose", fake_compose)
    detail = render_routes._call_compose_detail("one circle", lang=lang)

    assert len(prompts) == 2
    assert prompts[0] is None
    assert prompts[1] is not None
    assert _retry_colors(prompts[1], lang=lang) == get_args(Color)
    assert detail.retry_count == 1
    assert detail.retry_reasons == ["empty_instructions"]
    assert detail.fallback_used is False
