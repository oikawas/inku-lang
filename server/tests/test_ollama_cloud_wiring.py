"""Ollama Cloud の配線 — tools のまま思考を止め、version の推測で Score を捨てない。

2026-07-29 に無料枠で叩ける 8 モデルを 4 実行ずつ 2 条件で測った結果の実装。
生ログは `cli/out2/766-v2.9.7-ollama-cloud-bench/`。

決め手になった 2 つ:

  1. **思考抑止は cloud にも要る。**「cloud のモデルは思考しない」は gemma4:31b 1 本の
     挙動を provider 全体の性質として書いたものだった。抑止で clean run 6 → 9、
     空応答 15 → 6
  2. **失敗の最大要因は `version` の literal。**32 実行のうち 9 実行が version 以外に
     何のエラーも無く落ちていた。モデルは `"1.0"` と書く
"""

from __future__ import annotations

import pytest

from inku_server.composer import SCORE_VERSION, _score_from_model_output
from inku_server.schema import Score

MINIMAL = {"instructions": [{"primitive": "circle", "center": [0.5, 0.5], "radius": 0.1}]}


def test_the_version_constant_is_read_off_the_literal() -> None:
    """定数を 2 度書くと片方だけ動く。Literal から読むこと。"""
    assert SCORE_VERSION == Score.model_validate(MINIMAL).version


def test_a_guessed_version_does_not_cost_the_score() -> None:
    """`"1.0"` は 2026-07-29 に 9 実行を落とした実際の値。"""
    score = _score_from_model_output({**MINIMAL, "version": "1.0"})
    assert score.version == SCORE_VERSION
    assert len(score.instructions) == 1


@pytest.mark.parametrize("guess", ["1.0", "1", "0.1", "2.0.0", "", None])
def test_any_wrong_version_is_dropped_rather_than_rewritten(guess: object) -> None:
    """書き換えではなく削除。既定値が埋めるので、モデルの意図を推測しないで済む。"""
    assert _score_from_model_output({**MINIMAL, "version": guess}).version == SCORE_VERSION


def test_the_legal_version_survives_untouched() -> None:
    assert _score_from_model_output({**MINIMAL, "version": SCORE_VERSION}).version == SCORE_VERSION


def test_other_validation_errors_still_raise() -> None:
    """version を許したのであって、検証を緩めたのではない。"""
    with pytest.raises(Exception):
        _score_from_model_output({**MINIMAL, "instructions": [{"primitive": "circle", "color": "yellow"}]})
    with pytest.raises(Exception):
        _score_from_model_output({"version": "1.0"})


def test_a_non_mapping_is_left_for_pydantic_to_reject() -> None:
    with pytest.raises(Exception):
        _score_from_model_output(["not", "a", "score"])


def _structured_for(provider: str, monkeypatch: pytest.MonkeyPatch) -> dict:
    """`_compose_openai` が provider ごとに組む引数を、通信せずに取り出す。

    保存済み設定は DB から来るが、テストに DB は無い。組み込みカタログを返させて
    provider の解決だけ通す。
    """
    import inku_server.composer as composer
    from inku_server.model_settings import default_model_settings

    monkeypatch.setattr(composer, "_current_model_settings", default_model_settings)
    seen: dict = {}

    class _Client:
        class chat:
            class completions:
                @staticmethod
                def create(**kwargs):
                    seen.update(kwargs)
                    raise RuntimeError("stop before the request")

        def __init__(self, **_kwargs) -> None:
            pass

    import openai

    real = openai.OpenAI
    openai.OpenAI = _Client  # type: ignore[misc]
    try:
        with pytest.raises(Exception):
            composer._compose_openai("DDL", model=f"{provider}:whatever", provider=provider)
    finally:
        openai.OpenAI = real  # type: ignore[misc]
    return seen


def test_the_cloud_keeps_tools_and_gains_the_suppression(monkeypatch: pytest.MonkeyPatch) -> None:
    """cloud は構造化出力を 3 形態とも無視するので tools を外せない (2026-07-27 実測)。"""
    sent = _structured_for("ollama-cloud", monkeypatch)
    assert sent.get("reasoning_effort") == "none"
    assert "tools" in sent
    assert "response_format" not in sent


def test_local_ollama_keeps_the_schema_path(monkeypatch: pytest.MonkeyPatch) -> None:
    """ローカルは decoder が縛れるので response_format。tools はプロンプトを圧迫する。"""
    sent = _structured_for("ollama", monkeypatch)
    assert sent.get("reasoning_effort") == "none"
    assert "response_format" in sent
    assert "tools" not in sent


def test_other_providers_are_not_told_to_stop_thinking(monkeypatch: pytest.MonkeyPatch) -> None:
    """抑止は tool call を失わせることがある。測っていない provider へは広げない。"""
    sent = _structured_for("nvidia", monkeypatch)
    assert "reasoning_effort" not in sent
    assert "tools" in sent


def _stage1_kwargs_for(provider: str, monkeypatch: pytest.MonkeyPatch) -> dict:
    """Stage 1 が provider ごとに送る引数。段 2 と別経路なので別に測る。"""
    import inku_server.interpreter as interpreter
    from inku_server.model_settings import default_model_settings

    monkeypatch.setattr(interpreter, "_current_model_settings", default_model_settings)
    seen: dict = {}

    class _Client:
        class chat:
            class completions:
                @staticmethod
                def create(**kwargs):
                    seen.update(kwargs)
                    raise RuntimeError("stop before the request")

        def __init__(self, **_kwargs) -> None:
            pass

    import openai

    real = openai.OpenAI
    openai.OpenAI = _Client  # type: ignore[misc]
    try:
        with pytest.raises(Exception):
            interpreter._interpret_openai_detail(
                "大きな太陽が昇る",
                model=f"{provider}:whatever",
                provider=provider,
                system_prompt="x",
            )
    finally:
        openai.OpenAI = real  # type: ignore[misc]
    return seen


@pytest.mark.parametrize("provider", ["ollama", "ollama-cloud"])
def test_stage1_stops_the_thinking_for_both_ollamas(provider: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """Stage 1 も MAX_TOKENS を思考と分け合う。段 2 だけ直しても半分しか届かない。"""
    assert _stage1_kwargs_for(provider, monkeypatch).get("reasoning_effort") == "none"


def test_stage1_leaves_other_providers_thinking(monkeypatch: pytest.MonkeyPatch) -> None:
    assert "reasoning_effort" not in _stage1_kwargs_for("nvidia", monkeypatch)
