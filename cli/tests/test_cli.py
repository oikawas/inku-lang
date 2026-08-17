from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import subprocess
import urllib.error
import urllib.request
import sys
from pathlib import Path

import pytest

from inku_analysis.rasterize_batch import Failure, Report
from inku_cli import cli


CATALOG_DATA = {
    "default_catalog_id": "default",
    "catalogs": {
        "default": {
            "id": "default",
            "name": "inku Default",
            "map": {"white": "#ffffff", "black": "#111111", "blue": "#2c3e91", "red": "#a2342a", "green": "#2f6b3a", "gray": "#888888"},
            "palette": [],
        },
        "vivid_material": {
            "id": "vivid_material",
            "name": "Vivid Material",
            "map": {"white": "#f4f4f4", "black": "#1c1c1c", "blue": "#73c2fb", "red": "#f50087", "green": "#008f39", "gray": "#7d6f66"},
            "palette": [{"name": "Fresh Green", "code": "#008f39"}],
        },
    },
}


def test_extract_session_token_from_login_cookie():
    token = cli._extract_session_token("inku_session=abc123; HttpOnly; Path=/; SameSite=lax")
    assert token == "abc123"


def test_join_url_rejects_absolute_or_embedded_query_paths():
    with pytest.raises(cli.CliError):
        cli._join_url("http://127.0.0.1:8100", "https://example.test/api/info")
    with pytest.raises(cli.CliError):
        cli._join_url("http://127.0.0.1:8100", "/api/history?limit=10")


def test_api_parser_supports_all_public_http_methods():
    parser = cli.build_parser()
    for method in ("GET", "POST", "PUT", "PATCH", "DELETE"):
        args = parser.parse_args(["api", method, "/api/info"])
        assert args.method == method
        assert args.func is cli.command_api


def test_api_json_body_accepts_inline_and_rejects_conflicting_sources(tmp_path):
    inline = argparse.Namespace(data='{"ok":true}', file=None)
    assert cli._api_json_body(inline) == {"ok": True}
    body_file = tmp_path / "body.json"
    body_file.write_text('["one","two"]', encoding="utf-8")
    from_file = argparse.Namespace(data=None, file=str(body_file))
    assert cli._api_json_body(from_file) == ["one", "two"]
    with pytest.raises(cli.CliError):
        cli._api_json_body(argparse.Namespace(data="{}", file=str(body_file)))


def test_config_roundtrip(tmp_path):
    path = tmp_path / "config.json"
    config = cli.CliConfig(
        base_url="http://example.test",
        token="token-1",
        username="admin",
        stage1_provider="nvidia",
        stage1_model="stage1",
        stage2_provider="local",
        stage2_model="stage2",
        vision_provider="nvidia",
        vision_model="meta/llama-3.2-90b-vision-instruct",
        timeout_seconds=900,
        color_catalog="open_air_light",
    )
    cli.save_config(config, path)

    assert path.stat().st_mode & 0o777 == 0o600
    assert cli.load_config(path) == config

    cli.clear_config(path)
    assert not path.exists()


def test_paint_payload_drops_none_values():
    parser = cli.build_parser()
    args = parser.parse_args(["paint", "一滴の墨", "--save-history", "--stage1-model", "gemma"])

    payload = cli._paint_payload(args, "一滴の墨")

    assert payload["description"] == "一滴の墨"
    assert payload["stage1_model"] == "gemma"
    assert payload["save_history"] is True
    assert payload["include_thinking"] is False
    assert payload["catalog_id"] == "default"
    assert "color_map" not in payload
    assert "stage2_model" not in payload
    assert "history_input" not in payload


def test_paint_payload_makes_the_description_the_text_the_author_typed():
    """記述は作品の出自なので、位置引数以外のものが記述の席に座ることはない。

    以前は `--description` が位置引数と記述を切り離していたが、記述は記録ではなく
    **プラグインの発火・Stage 1.5 の文脈・種・言語の 4 つを動かす**ので、その DDL を
    生んでいない文字列を座らせられる旗ごと外した (2026-08-04 作者裁定)。
    """
    parser = cli.build_parser()
    args = parser.parse_args(["paint", "一滴の墨\n\n感情: 静か"])

    payload = cli._paint_payload(args, "一滴の墨\n\n感情: 静か")

    assert payload["description"] == "一滴の墨\n\n感情: 静か"
    assert payload["stage1_input"] == "一滴の墨\n\n感情: 静か"


def test_paint_payload_includes_trace_only_when_flag_set():
    parser = cli.build_parser()
    with_trace = cli._paint_payload(parser.parse_args(["paint", "x", "--trace"]), "x")
    without = cli._paint_payload(parser.parse_args(["paint", "x"]), "x")
    assert with_trace["include_trace"] is True
    assert "include_trace" not in without


def test_write_paint_outputs_saves_trace_file(tmp_path):
    result = {"svg": "<svg></svg>", "trace": {"stage1_ddl": "x", "stage2_raw_attempts": []}}
    paths = cli._write_paint_outputs(result, out_dir=tmp_path, prefix="smoke", png=False)
    trace_file = tmp_path / "smoke-trace.json"
    assert trace_file.exists()
    assert json.loads(trace_file.read_text())["stage1_ddl"] == "x"
    assert paths["trace"] == str(trace_file)
    # no trace in the response -> no trace file
    plain = cli._write_paint_outputs({"svg": "<svg></svg>"}, out_dir=tmp_path, prefix="plain", png=False)
    assert not (tmp_path / "plain-trace.json").exists()
    assert "trace" not in plain


def test_paint_payload_uses_resolved_models():
    parser = cli.build_parser()
    args = parser.parse_args(["paint", "一滴の墨"])

    payload = cli._paint_payload(args, "一滴の墨", stage1_model="s1", stage2_model="s2")

    assert payload["stage1_model"] == "s1"
    assert payload["stage2_model"] == "s2"


def test_paint_payload_includes_canvas_aspect():
    parser = cli.build_parser()
    args = parser.parse_args(["paint", "一滴の墨", "--canvas-aspect", "golden"])

    payload = cli._paint_payload(args, "一滴の墨")

    assert payload["canvas_aspect"] == "golden"


def test_compose_payload_for_ddl_input_mode():
    """DDL で書き起こした作品に記述は無い。**鍵ごと欠落する**のが正しい姿。

    web の「指示書を新規作成」が `description: ''` を送るのと同じ形で、どちらも種は
    DDL に落ちる。空文字を送ることと鍵を送らないことの差は `ComposeRequest` の
    `default=None` が吸収する。
    """
    parser = cli.build_parser()
    args = parser.parse_args(["paint", "白い背景に黒い線を一本引く。", "--input-mode", "ddl"])

    payload = cli._compose_payload(args, "白い背景に黒い線を一本引く。", stage2_model="s2", color_catalog="default")

    assert payload == {
        "ddl": "白い背景に黒い線を一本引く。",
        "model": "s2",
        "instruction_lang": "auto",
        "catalog_id": "default",
        "auto_repair": True,
    }
    assert "description" not in payload


def test_compose_payload_carries_the_prose_a_plugin_fires_on():
    """`--fires-on` is the only way a plugin expands in ddl input mode.

    Whether a plugin fires is decided by the description (`source_text` on the
    server); the DDL is only hashed for the seed. A DDL that spells a plugin
    word therefore expands to nothing on its own, which reads as the plugin
    being broken rather than as the description being absent.
    """
    parser = cli.build_parser()
    args = parser.parse_args(
        ["paint", "落葉", "--input-mode", "ddl", "--fires-on", "落葉"]
    )

    payload = cli._compose_payload(args, "落葉", stage2_model="s2", color_catalog="default")

    assert payload["fires_on"] == "落葉"
    # The DDL is unchanged: the flag adds prose, it does not rewrite the input.
    assert payload["ddl"] == "落葉"


def test_compose_payload_omits_an_empty_fires_on():
    parser = cli.build_parser()
    args = parser.parse_args(["paint", "落葉", "--input-mode", "ddl", "--fires-on", "   "])

    payload = cli._compose_payload(args, "落葉", stage2_model="s2", color_catalog="default")

    # Blank is not a description: sending "" would claim the work has one.
    assert "fires_on" not in payload


def test_compose_result_keeps_which_plugin_expanded():
    """Without this the saved JSON says nothing fired even when one did.

    `/api/compose` has always returned the provenance; this mapping did not
    name it, so a run in ddl input mode could not be told apart from one where
    no plugin was reached.
    """
    result = {
        "ddl": "落葉 赤と灰を枚ごとに交互に。",
        "plugin_provenance": [{"plugin_term": "Nature.落葉", "units": "18"}],
        "plugin_warnings": ["one warning"],
    }

    mapped = cli._compose_response_as_paint_result(
        result, ddl="落葉", input_text="落葉", stage2_model="s2"
    )

    assert mapped["plugin_provenance"] == [{"plugin_term": "Nature.落葉", "units": "18"}]
    assert mapped["plugin_warnings"] == ["one warning"]


def test_compose_result_reports_no_expansion_as_an_empty_list():
    mapped = cli._compose_response_as_paint_result(
        {"ddl": "円を置く。"}, ddl="円を置く。", input_text="円を置く。", stage2_model="s2"
    )

    # An empty list, not a missing key: a reader that counts entries must not
    # have to tell "no plugins" from "this CLI does not report plugins".
    assert mapped["plugin_provenance"] == []
    assert mapped["plugin_warnings"] == []


def test_compose_payload_includes_canvas_aspect():
    parser = cli.build_parser()
    args = parser.parse_args(["paint", "白い背景に黒い線を一本引く。", "--input-mode", "ddl", "--canvas-aspect", "wide"])

    payload = cli._compose_payload(args, "白い背景に黒い線を一本引く。", stage2_model="s2", color_catalog="default")

    assert payload["canvas_aspect"] == "wide"


def test_history_payload_from_compose_result():
    parser = cli.build_parser()
    args = parser.parse_args(["paint", "白い背景に黒い線を一本引く。", "--input-mode", "ddl", "--save-history"])
    result = {
        "score": {"instructions": []},
        "svg": "<svg></svg>",
        "elapsed_total_ms": 1200,
        "tokens_in_stage2": 10,
        "tokens_out_stage2": 20,
        "render_engine_id": "default",
        "ddl_version": "3",
        "ddl_engine_version": "9",
    }

    payload = cli._history_payload_from_result(
        args,
        result,
        input_text="線",
        ddl="白い背景に黒い線を一本引く。",
        stage1_model=None,
        stage2_model="s2",
        color_catalog="default",
        at=123,
    )

    assert payload["input"] == "線"
    assert payload["ddl"] == "白い背景に黒い線を一本引く。"
    assert "stage1_model" not in payload
    assert payload["stage2_model"] == "s2"
    assert payload["tokens_in"] == 10
    assert payload["tokens_out"] == 20
    assert payload["ddl_version"] == "3"
    assert payload["ddl_engine_version"] == "9"
    assert payload["save_artifacts"] is True
    assert payload["count_generation"] is True


def test_history_payload_includes_requested_canvas_aspect():
    parser = cli.build_parser()
    args = parser.parse_args(["paint", "線", "--save-history", "--canvas-aspect", "oban"])

    payload = cli._history_payload_from_result(
        args,
        {"score": {"instructions": []}, "svg": "<svg></svg>"},
        input_text="線",
        ddl="線を引く。",
        stage1_model="s1",
        stage2_model="s2",
        color_catalog="default",
        at=123,
    )

    assert payload["canvas_aspect"] == "oban"


def test_compose_response_as_paint_result_uses_effective_ddl():
    result = cli._compose_response_as_paint_result(
        {
            "ddl": "展開後DDL。",
            "ddl_version": "3",
            "ddl_engine_version": "9",
            "score": {"instructions": []},
            "svg": "<svg></svg>",
            "elapsed_ms": 500,
            "stage2_model": "resolved",
        },
        ddl="入力DDL。",
        input_text="元入力",
        stage2_model="requested",
    )

    assert result["description"] == "元入力"
    assert result["ddl"] == "展開後DDL。"
    assert result["stage1_model"] is None
    assert result["stage2_model"] == "resolved"
    assert result["ddl_version"] == "3"
    assert result["ddl_engine_version"] == "9"
    assert result["elapsed_stage1_ms"] == 0
    assert result["elapsed_total_ms"] == 500


def test_compose_response_as_paint_result_carries_coerce_diagnostics():
    diagnostics = {
        "coerce_branch_counts": {"with_ddl_coverage": 2},
        "coerce_relation_input_count": 3,
        "coerce_relation_output_count": 2,
        "coerce_relation_dropped_count": 1,
        "coerce_warnings": ["relation dropped"],
    }
    result = cli._compose_response_as_paint_result(
        diagnostics, ddl="DDL。", input_text="入力", stage2_model="model"
    )

    for key, value in diagnostics.items():
        assert result[key] == value


def test_model_summary_marks_server_default():
    summary = cli._model_summary(None, "gemma", stage2_provider="nvidia")

    assert summary["stage1_provider"] is None
    assert summary["stage1_model"] is None
    assert summary["stage1_provider_display"] == "server default"
    assert summary["stage1_model_display"] == "server default"
    assert summary["stage2_provider"] == "nvidia"
    assert summary["stage2_model"] == "gemma"
    assert summary["stage2_provider_display"] == "nvidia"
    assert summary["stage2_model_display"] == "gemma"


def test_models_command_accepts_providers():
    parser = cli.build_parser()
    args = parser.parse_args([
        "models",
        "--stage1-provider",
        "nvidia",
        "--stage1-model",
        "google/gemma-4-31b-it",
        "--stage2-provider",
        "local",
        "--stage2-model",
        "qwen-api",
        "--vision-provider",
        "nvidia",
        "--vision-model",
        "meta/llama-3.2-90b-vision-instruct",
        "--color-catalog",
        "ink_season",
    ])

    assert args.stage1_provider == "nvidia"
    assert args.stage1_model == "google/gemma-4-31b-it"
    assert args.stage2_provider == "local"
    assert args.stage2_model == "qwen-api"
    assert args.vision_provider == "nvidia"
    assert args.vision_model == "meta/llama-3.2-90b-vision-instruct"
    assert args.color_catalog == "ink_season"


def test_the_colophon_subcommand_replaced_okugaki_outright():

    """奥書のサブコマンドは `colophon`。**ローマ字は残していない。**

    辞書 (`web/src/lib/i18n/GLOSSARY.md`) が 奥書 = colophon と定めており、
    打鍵する名前は `paint` / `refine` / `lineage` と同じ欄にある。
    エイリアスを残さないのは作者裁定 (2026-07-27)。
    """
    parser = cli.build_parser()
    assert parser.parse_args(["colophon", "node-1"]).func is cli.command_colophon
    with pytest.raises(SystemExit):
        parser.parse_args(["okugaki", "node-1"])


def test_the_staffage_flag_is_gone_in_both_spellings():
    """T-10 of 契約 fold-away-the-staffage-level: 添景の旗は無い。

    `--tenkei` は 2026-07-27 に `--staffage` へ改名された。**v2.11.0 で軸ごと
    畳んだので、両方の綴りが落ちている。**綴りを 1 つずつ見るのは、改名の履歴が
    ある旗では「片方だけ残す」が一番起きやすい失敗だからである。
    """
    parser = cli.build_parser()
    for spelling in ("--staffage", "--tenkei"):
        with pytest.raises(SystemExit):
            parser.parse_args(["paint", "一滴の墨", spelling, "sparse"])

    args = parser.parse_args(["paint", "一滴の墨"])
    assert "tenkei" not in cli._paint_payload(args, "一滴の墨")


def _all_option_strings(parser) -> set[str]:
    """サブパーサまで降りて旗を集める。

    **上位パーサの `_actions` だけを見ると穴が開く** — 実際の旗はサブコマンド側に
    付いているので、`--tenkei` をエイリアスとして残しても素通りした (摂動で実測)。
    """
    flags = {option for action in parser._actions for option in action.option_strings}
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            for sub in action.choices.values():
                flags |= _all_option_strings(sub)
    return flags


def test_no_cli_flag_is_spelled_tenkei_or_staffage():
    """走査は旗の一覧そのものに当てる。名指しの一覧は穴を残す。

    到達確認の目印は `--canvas-aspect` — サブコマンド側にだけ在る旗で、これが
    見えていなければ走査がサブパーサまで届いていない（`--staffage` を目印に
    していたが、その旗ごと無くなった）。
    """
    flags = _all_option_strings(cli.build_parser())
    assert "--canvas-aspect" in flags, "走査がサブパーサまで届いていない"
    assert not [flag for flag in flags if "tenkei" in flag or "staffage" in flag]


@pytest.mark.parametrize("command", ["paint", "batch"])
def test_the_drawing_commands_have_no_description_flag(command):
    """**旗は削除であって改名ではない。** 一度も名指しでない綴りも一緒に落ちている。

    元は `--original-text` が `--description` へ改名されたことの番人だった
    (2026-07-27 作者裁定)。その旗そのものが 2026-08-04 に外れたので、**消したのでは
    なく退行の向きを裏返して残す** — 名前で数える棚卸しは改名と削除を取り違えるので、
    旧綴りも新綴りも同時に見る ([[test_inventory_by_name_misreads_renames]])。
    """
    parser = cli.build_parser()
    base = ["paint", "一滴の墨"] if command == "paint" else ["batch", "--file", "-"]
    for retired in ("--description", "--original-text"):
        with pytest.raises(SystemExit):
            parser.parse_args([*base, retired, "一滴の墨"])
    assert "--description" not in _all_option_strings(_subparser(command))


def test_refine_perform_keeps_its_own_description_flag():
    """同じ綴りの別定義。**巻き込んで消していないことの表明。**

    `refine perform --description` は既存作品の記述を上書きして描き直す旗で、
    出自を後から貼る旗ではない。読み手は `command_refine` の payload。
    """
    flags = _all_option_strings(_subparser("refine"))
    assert "--description" in flags
    action = next(
        item
        for item in _subparser("refine")._subparsers._group_actions[0].choices["perform"]._actions
        if "--description" in (item.option_strings or [])
    )
    assert "override" in (action.help or "")


def _all_help_strings(parser) -> list[str]:
    helps = [action.help for action in parser._actions if action.help]
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            for sub in action.choices.values():
                helps.extend(_all_help_strings(sub))
    return helps


def test_no_cli_flag_says_original_text():
    """走査は旗の一覧そのものに当てる。名指しの一覧は穴を残す。

    到達確認の目印は `--canvas-aspect`。**`--description` は目印に使えない** —
    `paint` / `batch` から外れて `refine perform` にだけ残ったので、走査がサブパーサ
    まで届いていなくても届いていても、どちらでも真になりうる。
    """
    flags = _all_option_strings(cli.build_parser())
    assert "--canvas-aspect" in flags, "走査がサブパーサまで届いていない"
    assert not [flag for flag in flags if "original" in flag]


def test_the_drawing_commands_do_not_call_the_description_a_prompt():
    """辞書は 記述 = description と定め `prompt` を退けている。help も表示に出る語である。

    **走査は `paint` / `batch` に限る。** `review evaluate --prompt` などの `prompt` は
    **LLM のプロンプトという別の指示対象**で、辞書が禁じているのは記述を指す用法のほう。
    """
    parser = cli.build_parser()
    subparsers = next(
        action for action in parser._actions
        if isinstance(action, argparse._SubParsersAction)
    )
    for name in ("paint", "batch"):
        helps = _all_help_strings(subparsers.choices[name])
        assert helps, f"{name} の help を集められていない"
        assert not [text for text in helps if "prompt" in text.lower()], name


def test_inspect_sends_the_description_key_to_paint(monkeypatch, tmp_path):
    """**自前で payload を組む経路も `description` を送ること。**

    Build 724 の改名は `_paint_payload` には当たったが、**`inspect` と
    `refine generate` が自分で組んでいた payload 2 つを取りこぼした**。どちらも
    旧鍵 `text` を送り続けており、`description` が必須になった要求は **422 で落ちていた**
    (Build 728 で修正)。**ユニットテストは実サーバを叩かないので緑のままだった** —
    捕まえるには送信そのものを覗くしかない。
    """
    calls = []

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def request(self, method, path, *, data=None, **kwargs):
            calls.append((method, path, data))
            return {"ddl": "中心に黒い円を置く。", "render_hash_short": "ABCD"}, None

    monkeypatch.setattr(cli, "ApiClient", FakeClient)
    parser = cli.build_parser()
    args = parser.parse_args(
        ["inspect", "一滴の墨", "--models", "m1", "--out-dir", str(tmp_path)]
    )
    assert cli.command_inspect(args) == 0

    posts = [data for method, path, data in calls if path == "/api/paint"]
    assert posts, "paint を叩いていない"
    for payload in posts:
        assert payload["description"] == "一滴の墨"
        assert "text" not in payload
    parser = cli.build_parser()
    legacy = parser.parse_args(["colophon", "node-1", "--model", "legacy-vision"])
    explicit = parser.parse_args(["colophon", "node-1", "--vision-model", "new-vision"])
    review = parser.parse_args(["vision-review", "out", "--vision-model", "review-vision"])

    assert legacy.model == "legacy-vision"
    assert legacy.vision_model is None
    assert explicit.vision_model == "new-vision"
    assert review.vision_model == "review-vision"


def test_color_catalog_payload_sets_catalog_and_map():
    parser = cli.build_parser()
    args = parser.parse_args(["paint", "緑の葉", "--color-catalog", "vivid_material"])

    payload = cli._paint_payload(args, "緑の葉")

    assert payload["catalog_id"] == "vivid_material"
    assert "color_map" not in payload


def test_color_catalog_summary_uses_server_catalog_data():
    summary = cli._color_catalog_summary("vivid_material", CATALOG_DATA)

    assert summary["resolved_color_catalog"] == "vivid_material"
    assert summary["color_catalog_name"] == "Vivid Material"
    assert summary["color_map"]["green"] == "#008f39"
    assert summary["color_map"]["palette:Fresh Green"] == "#008f39"


def test_color_trace_reports_missing_green():
    result = {
        "description": "緑の葉が揺れる",
        "ddl": "緑の小さな楕円を散らす。",
        "score": {"instructions": [{"primitive": "ellipse", "color": "gray"}]},
    }

    trace = cli._color_trace(result, catalog_id="default")

    assert trace["green_requested"] is True
    assert trace["green_in_score"] is False
    assert "green_requested_but_missing_in_score" in trace["warnings"]


def test_color_trace_does_not_treat_words_as_green_leaf_marker():
    result = {
        "description": "言えなかった言葉を白い余白に置く",
        "ddl": "言えなかった言葉のために白い余白を残す。",
        "score": {"instructions": [{"primitive": "ellipse", "color": "white"}]},
    }

    trace = cli._color_trace(result, catalog_id="default")

    assert trace["green_requested"] is False
    assert "green" not in trace["requested_colors"]
    assert "green_requested_but_missing_in_score" not in trace["warnings"]


def test_color_trace_does_not_read_crescent_as_scent():
    result = {
        "description": "A single white crescent waits in an off-center dark field.",
        "ddl": "Fill background with black. Place a white crescent arc in the upper right.",
        "score": {"instructions": [{"primitive": "arc", "color": "white"}]},
    }

    trace = cli._color_trace(result, catalog_id="default")

    assert "green" not in trace["text_color_markers"]
    assert "green" not in trace["ddl_color_markers"]
    assert "green" not in trace["requested_colors"]


def test_color_trace_detects_specific_leaf_terms_as_green():
    assert cli._marker_colors("落ち葉と若葉、木の葉、葉っぱ、葉脈") == ["green"]


def test_color_trace_suppresses_negated_green_warning():
    result = {
        "description": "言えなかった言葉を白い余白に置き、緑には寄せず黒い線だけを残す。",
        "ddl": "白い余白に黒い線だけを置く。",
        "score": {"instructions": [{"primitive": "line", "color": "black"}]},
    }

    trace = cli._color_trace(result, catalog_id="default")

    assert "green" in trace["text_color_markers"]
    assert trace["negated_color_markers"] == ["green"]
    assert "green" not in trace["requested_colors"]
    assert trace["green_requested"] is False
    assert "green_requested_but_missing_in_score" not in trace["warnings"]


def test_timeout_prefers_args_then_config_then_default():
    parser = cli.build_parser()
    config = cli.CliConfig(timeout_seconds=900)

    default_args = parser.parse_args(["models"])
    explicit_args = parser.parse_args(["models", "--timeout-seconds", "1200"])

    assert cli._resolved_timeout_seconds(default_args, config) == 900
    assert cli._resolved_timeout_seconds(explicit_args, config) == 1200
    assert cli._resolved_timeout_seconds(default_args, cli.CliConfig()) == 600


def test_write_paint_outputs(tmp_path):
    result = {
        "description": "一滴の墨",
        "ddl": "白い背景に黒い点を置く。",
        "score": {"canvas": {"width": 100, "height": 100}, "shapes": []},
        "svg": "<svg viewBox=\"0 0 10 10\"></svg>",
    }

    paths = cli._write_paint_outputs(result, out_dir=tmp_path, prefix="sample", png=False)

    assert Path(paths["svg"]).read_text(encoding="utf-8") == result["svg"]
    saved_json = json.loads(Path(paths["json"]).read_text(encoding="utf-8"))
    assert saved_json["ddl"] == result["ddl"]


def test_svg_profile_and_canvas_aspect_args_are_accepted_for_paint_and_batch():
    parser = cli.build_parser()

    paint_args = parser.parse_args(["paint", "線", "--svg-profile", "editable", "--input-mode", "ddl", "--canvas-aspect", "golden"])
    batch_args = parser.parse_args(["batch", "--file", "prompts.txt", "--svg-profile", "compat", "--input-mode", "ddl", "--canvas-aspect", "wide"])

    assert paint_args.svg_profile == "editable"
    assert paint_args.input_mode == "ddl"
    assert paint_args.canvas_aspect == "golden"
    assert batch_args.svg_profile == "compat"
    assert batch_args.input_mode == "ddl"
    assert batch_args.canvas_aspect == "wide"


def test_result_with_svg_profile_regenerates_non_display_svg():
    class FakeClient:
        def __init__(self):
            self.calls = []

        def request_text(self, method, path, *, data=None, query=None, auth=True):
            self.calls.append((method, path, data, query, auth))
            return "<svg><title>editable</title></svg>"

    client = FakeClient()
    result = {
        "score": {"instructions": []},
        "svg": "<svg><title>display</title></svg>",
        "render_color_catalog_id": "vivid_material",
    }

    output = cli._result_with_svg_profile(client, result, svg_profile="editable", color_catalog="default")

    assert output["svg_profile"] == "editable"
    assert output["svg"] == "<svg><title>editable</title></svg>"
    assert client.calls[0][0:2] == ("POST", "/api/render-svg")
    assert client.calls[0][2]["catalog_id"] == "vivid_material"
    assert client.calls[0][2]["svg_profile"] == "editable"
    assert result["svg"] == "<svg><title>display</title></svg>"


def test_result_with_svg_profile_sends_both_seeds():
    """[I-157]: a non-display export is the performance it exports.

    The performance seed was sent and the placement seed was not, so the file
    written out put the marks somewhere else than the picture it came from.
    Both are read off the result, raw: renderer.py:3486 falls back to the
    performance seed when a work carries no composition seed, so repeating that
    rule here would be a second copy of it.
    """
    class FakeClient:
        def __init__(self):
            self.calls = []

        def request_text(self, method, path, *, data=None, query=None, auth=True):
            self.calls.append((method, path, data, query, auth))
            return "<svg><title>editable</title></svg>"

    client = FakeClient()
    result = {
        "score": {"instructions": []},
        "svg": "<svg><title>display</title></svg>",
        "render_seed": 4242,
        "composition_seed": 0,
    }

    cli._result_with_svg_profile(client, result, svg_profile="editable", color_catalog="default")

    sent = client.calls[0][2]
    assert sent["render_seed"] == 4242
    # `is`, not truthiness: 0 is a seed the placement stage must honour, and an
    # `or` here would drop it and move every mark.
    assert sent["composition_seed"] == 0
    assert "composition_seed" in sent


def test_score_metrics_reports_density_cluster_and_fade_fields():
    score = {
        "instructions": [
            {
                "primitive": "square",
                "color": "white",
                "arrangement": {
                    "count": 110,
                    "layout": "scatter",
                    "density": "high",
                    "cluster_count": 9,
                    "fade": "outward",
                    "preserve_space": True,
                    "color_cycle": ["red", "blue"],
                },
            },
            {
                "primitive": "line",
                "color": "black",
            },
        ],
    }

    metrics = cli._score_metrics(score)

    assert metrics["score_instruction_count"] == 2
    assert metrics["score_arrangement_count"] == 1
    assert metrics["score_expanded_count"] == 111
    assert metrics["score_clustered_arrangements"] == 1
    assert metrics["score_preserve_space_count"] == 1
    assert metrics["score_color_cycle_count"] == 1
    assert metrics["score_density_counts"] == {"high": 1}
    assert metrics["score_fade_counts"] == {"outward": 1}
    assert metrics["score_primitive_counts"] == {"line": 1, "square": 1}
    assert metrics["score_color_counts"] == {"black": 1, "white": 1}
    assert metrics["score_motif_hint_counts"] == {}
    assert metrics["score_quality_metrics"]["constraint_adherence"] == 100
    assert metrics["score_quality_metrics"]["motion_energy"] == 0
    assert metrics["score_quality_metrics"]["negative_space_pressure"] > 0
    assert metrics["score_quality_metrics"]["color_resonance"] > 0
    assert metrics["score_quality_metrics"]["figurative_risk"] == 0
    assert metrics["score_quality_metrics"]["fallback_quality"] is None
    assert metrics["math_balance_markers"] == {
        "counterweight_like_opposite_placements": 0,
        "golden_like_centers": 0,
        "radial_fibonacci_counts": 0,
        "rule_of_thirds_like_centers": 0,
    }


def test_score_metrics_reports_math_balance_markers():
    score = {
        "instructions": [
            {
                "primitive": "ellipse",
                "color": "blue",
                "center": [0.382, 0.33],
                "size": [0.12, 0.08],
                "arrangement": {"count": 8, "layout": "radial", "center": [0.618, 0.667]},
            },
            {
                "primitive": "square",
                "color": "red",
                "position": [0.12, 0.12],
                "size": [0.1, 0.1],
            },
            {
                "primitive": "line",
                "color": "black",
                "from": [0.78, 0.78],
                "to": [0.98, 0.98],
            },
        ],
    }

    metrics = cli._score_metrics(score)

    assert metrics["math_balance_markers"] == {
        "counterweight_like_opposite_placements": 3,
        "golden_like_centers": 2,
        "radial_fibonacci_counts": 1,
        "rule_of_thirds_like_centers": 2,
    }


def test_score_metrics_reports_repair_part_counts():
    score = {
        "instructions": [
            {"primitive": "arc", "color": "black", "color_hint": "visual event adjacent reaction added to hold focal event"},
            {"primitive": "polygon", "color": "blue", "color_hint": "visual event restored as a small angular pulse"},
            {"primitive": "arc", "color": "blue", "color_hint": "vanishing trace restored with a fading endpoint"},
            {"primitive": "square", "color": "gray", "color_hint": "visual event restored as a small handmade rhythm offset"},
        ],
    }

    metrics = cli._score_metrics(score)

    assert metrics["score_repair_part_counts"] == {
        "adjacent_reaction": 1,
        "angular_pulse": 1,
        "rhythm_offset": 1,
        "vanishing_trace": 1,
    }
    assert metrics["score_has_repair_part"] is True


def test_score_metrics_reports_motif_hint_counts():
    score = {
        "instructions": [
            {"primitive": "ellipse", "color": "green", "color_hint": "leaf_cluster motif restored from DDL intent"},
            {"primitive": "arc", "color": "black", "color_hint": "leaf_cluster motif restored from DDL intent"},
            {"primitive": "square", "color": "black", "color_hint": "paper_shard motif restored from DDL intent"},
        ],
    }

    metrics = cli._score_metrics(score)

    assert metrics["score_motif_hint_counts"] == {"leaf_cluster": 2, "paper_shard": 1}


def test_score_metrics_counts_inherited_memory_arc_repair_part():
    score = {
        "instructions": [
            {
                "primitive": "arc",
                "color": "gray",
                "color_hint": "visual event type inherited_memory restored as a three-part memory sequence",
            },
            {"primitive": "line", "color": "black", "color_hint": "visual event adjacent reaction added to hold focal event"},
        ],
    }

    metrics = cli._score_metrics(score)

    assert metrics["score_repair_part_counts"] == {"adjacent_reaction": 1, "inherited_memory_arc": 1}


def test_render_response_summary_keeps_coerce_relation_metrics():
    summary = cli._render_response_summary(
        {
            "render_hash_short": "ABCD",
            "coerce_relation_input_count": 3,
            "coerce_relation_output_count": 2,
            "coerce_relation_dropped_count": 1,
            "coerce_relation_drop_rate": 0.333333,
            "coerce_warnings": ["relation dropped during coerce validation"],
        }
    )

    assert summary["render_hash_short"] == "ABCD"
    assert summary["coerce_relation_input_count"] == 3
    assert summary["coerce_relation_output_count"] == 2
    assert summary["coerce_relation_dropped_count"] == 1
    assert summary["coerce_relation_drop_rate"] == 0.333333
    assert summary["coerce_warnings"] == ["relation dropped during coerce validation"]


def test_aggregate_marker_lines_reports_sample_lines():
    results = [
        {"line": 1, "math_balance_markers": {"golden_like_centers": 1}, "score_motif_hint_counts": {"leaf_cluster": 2}},
        {"line": 2, "math_balance_markers": {"golden_like_centers": 0}, "score_motif_hint_counts": {"paper_shard": 1}},
        {"line": 3, "math_balance_markers": {"radial_fibonacci_counts": 1}, "score_motif_hint_counts": {}},
    ]

    assert cli._aggregate_marker_lines(results, "math_balance_markers") == {
        "golden_like_centers": [1],
        "radial_fibonacci_counts": [3],
    }
    assert cli._aggregate_marker_lines(results, "score_motif_hint_counts") == {
        "leaf_cluster": [1],
        "paper_shard": [2],
    }


def test_review_sets_groups_successful_samples_without_excluding_slow():
    sets = cli._review_sets(
        [
            {"line": 1, "elapsed_total_ms": 20_000},
            {"line": 2, "elapsed_total_ms": 140_000},
            {"line": 3, "elapsed_total_ms": 30_000, "compose_fallback_used": True},
            {"line": 4, "elapsed_total_ms": 180_000, "interpret_fallback_used": True},
        ]
    )

    assert sets["all_success_samples"] == [1, 2, 3, 4]
    assert sets["normal_samples"] == [1]
    assert sets["slow_samples"] == [2, 4]
    assert sets["fallback_samples"] == [3, 4]


def test_server_timeout_reasons_detects_stage_hard_timeouts_only():
    result = {
        "interpret_fallback_reasons": ["stage1_hard_timeout"],
        "compose_retry_reasons": ["empty_instructions", "stage2_hard_timeout"],
    }

    assert cli._server_timeout_reasons(result) == ["stage1_hard_timeout", "stage2_hard_timeout"]
    assert cli._server_timeout_reasons({"compose_retry_reasons": ["empty_instructions"]}) == []


def test_batch_accepts_summary_json_option():
    parser = cli.build_parser()
    args = parser.parse_args(["batch", "--file", "prompts.txt", "--summary-json", "summary.json"])

    assert args.summary_json == "summary.json"


def test_history_export_parser_accepts_hash_range_and_individuals():
    parser = cli.build_parser()
    args = parser.parse_args([
        "history-export",
        "ABCD",
        "1234",
        "--from",
        "F3DE",
        "--to",
        "0A9C",
        "--out-dir",
        "out",
    ])

    assert args.hashes == ["ABCD", "1234"]
    assert args.from_hash == "F3DE"
    assert args.to_hash == "0A9C"
    assert args.out_dir == "out"


def test_select_history_items_resolves_short_hashes_and_ranges():
    items = [
        {"id": "1", "render_hash": "a" * 60 + "1111", "render_hash_short": "1111"},
        {"id": "2", "render_hash": "b" * 60 + "2222", "render_hash_short": "2222"},
        {"id": "3", "render_hash": "c" * 60 + "3333", "render_hash_short": "3333"},
    ]

    selected = cli._select_history_items(items, hashes=["3333"], from_hash="1111", to_hash="2222")

    assert [item["id"] for item in selected] == ["1", "2", "3"]


def test_resolve_history_hash_rejects_ambiguous_short_hash():
    items = [
        {"id": "1", "render_hash": "a" * 60 + "1111", "render_hash_short": "1111", "input": "one"},
        {"id": "2", "render_hash": "b" * 60 + "1111", "render_hash_short": "1111", "input": "two"},
    ]

    try:
        cli._resolve_history_hash(items, "1111")
    except cli.CliError as exc:
        assert "ambiguous" in str(exc)
    else:
        raise AssertionError("expected ambiguous hash error")


def test_history_export_writes_contact_sheet_and_evaluation_json(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "svg_to_png", lambda svg, **kwargs: b"png")
    monkeypatch.setattr(cli, "_make_contact_sheet", lambda input_dir, output_path, *, columns, thumb_size: Path(output_path).write_bytes(b"sheet"))

    item_dir = tmp_path / "items"
    item_dir.mkdir()
    (item_dir / "stale.png").write_bytes(b"old")
    (item_dir / "stale.json").write_text("{}", encoding="utf-8")
    items = [
        {
            "id": "h1",
            "render_hash": "a" * 60 + "ABCD",
            "render_hash_short": "ABCD",
            "at": 123,
            "input": "丸が跳ねる",
            "ddl": "赤い丸を置く。",
            "score": {"instructions": [{"primitive": "ellipse", "color": "red"}]},
            "svg": "<svg></svg>",
            "elapsed_ms": 1200,
            "tokens_in": 10,
            "tokens_out": 20,
            "stage1_model": "s1",
            "stage2_model": "s2",
            "render_build_number": "352",
            "render_engine_id": "default",
            "render_engine_version": "1",
            "render_canvas_aspect": "1:1",
            "render_color_catalog_id": "default",
            "render_color_catalog_name": "inku Default",
        }
    ]

    summary = cli._write_history_export(items, out_dir=tmp_path, columns=4, thumb_size=180)

    assert not (item_dir / "stale.png").exists()
    assert not (item_dir / "stale.json").exists()
    assert (tmp_path / "contact-sheet.png").read_bytes() == b"sheet"
    assert (tmp_path / "summary.json").exists()
    exported_item = json.loads((item_dir / "001-ABCD.json").read_text(encoding="utf-8"))
    assert exported_item["export_paths"]["png"].endswith("001-ABCD.png")
    assert summary["ai_evaluation"]["contact_sheet"].endswith("contact-sheet.png")
    assert summary["ai_evaluation"]["items"][0]["prompt"] == "丸が跳ねる"
    assert summary["ai_evaluation"]["items"][0]["paths"]["json"].endswith("001-ABCD.json")
    assert summary["results"][0]["score_primitive_counts"] == {"ellipse": 1}


def test_history_export_names_the_ddl_layer_and_accepts_older_rows():
    summary = cli._history_export_summary(
        [
            {"id": "old", "score": {"instructions": []}},
            {
                "id": "current",
                "score": {"instructions": []},
                "ddl_version": "3",
                "ddl_engine_version": "9",
            },
        ],
        {},
    )

    assert summary["results"][0]["ddl_version"] is None
    assert summary["results"][0]["ddl_engine_version"] is None
    assert summary["ai_evaluation"]["items"][0]["ddl_version"] is None
    assert summary["ai_evaluation"]["items"][0]["ddl_engine_version"] is None
    assert summary["results"][1]["ddl_version"] == "3"
    assert summary["results"][1]["ddl_engine_version"] == "9"
    assert summary["ai_evaluation"]["items"][1]["ddl_version"] == "3"
    assert summary["ai_evaluation"]["items"][1]["ddl_engine_version"] == "9"


def test_aggregate_quality_metrics_reports_average_and_fallback_quality():
    results = [
        {
            "score_quality_metrics": {
                "constraint_adherence": 100,
                "negative_space_pressure": 40,
                "motion_energy": 30,
                "color_resonance": 20,
                "visual_event": 10,
                "figurative_risk": 0,
                "fallback_quality": None,
            }
        },
        {
            "score_quality_metrics": {
                "constraint_adherence": 80,
                "negative_space_pressure": 60,
                "motion_energy": 50,
                "color_resonance": 40,
                "visual_event": 30,
                "figurative_risk": 20,
                "fallback_quality": 70,
            }
        },
    ]

    summary = cli._aggregate_quality_metrics(results)

    assert summary["average"]["constraint_adherence"] == 90.0
    assert summary["min"]["figurative_risk"] == 0
    assert summary["max"]["motion_energy"] == 50
    assert summary["fallback_quality_average"] == 70.0
    assert summary["fallback_quality_samples"] == 1


def test_quality_metrics_scores_achromatic_tonal_resonance():
    score = {
        "instructions": [
            {
                "primitive": "line",
                "color": "gray",
                "from": [0.2, 0.7],
                "to": [0.8, 0.3],
                "rotation": -18,
                "arrangement": {"count": 5, "layout": "scatter", "fade": "outward", "preserve_space": True},
            }
        ]
    }

    metrics = cli._score_metrics(score)

    assert metrics["score_quality_metrics"]["color_resonance"] > 0


def test_quality_metrics_scores_achromatic_value_contrast_without_extra_colors():
    score = {
        "instructions": [
            {
                "primitive": "line",
                "color": "gray",
                "from": [0.15, 0.75],
                "to": [0.82, 0.28],
                "weight": "thin",
                "rotation": -14,
                "arrangement": {"count": 1, "layout": "scatter", "fade": "outward", "preserve_space": True},
            },
            {
                "primitive": "line",
                "color": "black",
                "from": [0.2, 0.78],
                "to": [0.62, 0.36],
                "weight": "heavy",
            },
        ]
    }

    metrics = cli._score_metrics(score)

    assert metrics["score_color_counts"] == {"black": 1, "gray": 1}
    assert metrics["score_quality_metrics"]["color_resonance"] >= 50


def test_quality_metrics_counts_background_color_as_rendered_color():
    score = {
        "background": "blue",
        "instructions": [
            {
                "primitive": "ellipse",
                "color": "white",
                "center": [0.5, 0.5],
                "size": [0.12, 0.08],
                "arrangement": {"count": 2, "layout": "scatter", "color_cycle": ["white", "blue"]},
            }
        ],
    }

    metrics = cli._score_metrics(score)

    assert metrics["score_color_counts"] == {"white": 1}
    assert metrics["score_quality_metrics"]["color_resonance"] >= 50


def test_quality_metrics_scores_isolated_chromatic_accent():
    score = {
        "instructions": [
            {
                "primitive": "line",
                "color": "black",
                "from": [0.1, 0.7],
                "to": [0.8, 0.45],
                "arrangement": {"count": 1, "layout": "scatter", "fade": "outward", "preserve_space": True},
            },
            {
                "primitive": "square",
                "color": "red",
                "center": [0.68, 0.42],
                "size": [0.08, 0.08],
                "filled": True,
                "color_hint": "small red interruption",
            },
        ]
    }

    metrics = cli._score_metrics(score)

    assert metrics["score_color_counts"] == {"black": 1, "red": 1}
    assert metrics["score_quality_metrics"]["color_resonance"] >= 54


def test_quality_metrics_scores_rhythm_spacing_as_motion_energy():
    score = {
        "instructions": [
            {
                "primitive": "ellipse",
                "color": "blue",
                "center": [0.5, 0.5],
                "size": [0.08, 0.04],
                "arrangement": {
                    "count": 7,
                    "layout": "horizontal",
                    "rhythm_spacing": "syncopated",
                },
            }
        ]
    }

    metrics = cli._score_metrics(score)

    assert metrics["score_quality_metrics"]["motion_energy"] > 0


def test_quality_metrics_does_not_treat_surface_as_face():
    score = {
        "instructions": [
            {
                "primitive": "arc",
                "color": "black",
                "center": [0.58, 0.62],
                "radius": 0.18,
                "angle_start": 198,
                "angle_end": 342,
                "color_hint": "surface tension restored as a quiet shadow trace",
            }
        ]
    }

    metrics = cli._score_metrics(score)

    assert metrics["score_quality_metrics"]["figurative_risk"] == 0


def test_paper_words_do_not_request_white_by_themselves():
    trace = cli._color_trace(
        {"description": "新聞紙が迷うように回っている。", "ddl": "灰色の四角を置く。", "score": {"instructions": [{"primitive": "square", "color": "gray"}]}},
        catalog_id="default",
        catalog_data=CATALOG_DATA,
    )

    assert "white" not in trace["requested_colors"]
    assert trace["missing_requested_colors"] == []



def test_paint_payload_includes_render_seed():
    parser = cli.build_parser()
    args = parser.parse_args(["paint", "一滴の墨", "--render-seed", "123"])

    payload = cli._paint_payload(args, "一滴の墨")

    assert payload["render_seed"] == 123


def test_analyze_parser_accepts_diversity_output():
    parser = cli.build_parser()
    args = parser.parse_args(["analyze", "out", "--diversity", "--output", "diversity.json"])

    assert args.input_dir == "out"
    assert args.diversity is True
    assert args.output == "diversity.json"


def test_diversity_summary_counts_png_score_and_relations(tmp_path):
    from PIL import Image

    Image.new("RGB", (16, 16), "white").save(tmp_path / "a.png")
    image = Image.new("RGB", (16, 16), "white")
    for x in range(8):
        for y in range(16):
            image.putpixel((x, y), (0, 0, 0))
    image.save(tmp_path / "b.png")
    (tmp_path / "a.json").write_text(json.dumps({
        "score": {
            "instructions": [
                {"primitive": "line", "color": "black", "weight": "pen", "from": [0.1, 0.2], "to": [0.9, 0.2]},
                {"primitive": "circle", "color": "red", "weight": "brush_thin", "center": [0.5, 0.5], "radius": 0.1, "relation": {"type": "not_touching", "gap": "narrow"}},
            ]
        }
    }), encoding="utf-8")

    summary = cli._diversity_summary(tmp_path)

    assert summary["png_count"] == 2
    assert summary["score_count"] == 1
    assert summary["composition_distance"] is not None
    assert summary["relation_counts"] == {"not_touching": 1}
    assert summary["relation_sample_rate"] == 1.0
    assert summary["vocab_entropy"]["primitive"] == 1.0



def test_composition_family_distinguishes_right_half_from_diagonal():
    score = {
        "instructions": [
            {
                "primitive": "ellipse",
                "center": [0.72, 0.5],
                "size": [0.08, 0.04],
                "arrangement": {"layout": "scatter", "path": "right_half"},
            }
        ]
    }

    assert cli._composition_family_from_score(score) == "one_sided_focus"


def test_composition_family_uses_dominant_layout_votes():
    score = {
        "instructions": [
            {"primitive": "line", "from": [0.1, 0.2], "to": [0.9, 0.2], "arrangement": {"layout": "horizontal", "path": "left_to_right"}},
            {"primitive": "ellipse", "center": [0.5, 0.5], "size": [0.08, 0.04], "arrangement": {"layout": "scatter", "path": "diagonal"}},
        ]
    }

    assert cli._composition_family_from_score(score) == "horizontal_strata"


def test_score_metrics_counts_relations():
    metrics = cli._score_metrics({
        "instructions": [
            {"primitive": "line", "color": "black", "from": [0.1, 0.2], "to": [0.9, 0.2]},
            {"primitive": "circle", "color": "red", "center": [0.5, 0.5], "radius": 0.1, "relation": {"type": "cutting", "gap": "medium"}},
        ]
    })

    assert metrics["score_relation_counts"] == {"cutting": 1}
    assert metrics["score_relation_instruction_count"] == 1
    assert metrics["score_has_relation"] is True


def test_diversity_summary_replay_requires_client(tmp_path):
    (tmp_path / "a.json").write_text(json.dumps({
        "score": {"instructions": [{"primitive": "line", "from": [0.1, 0.2], "to": [0.9, 0.2]}]}
    }), encoding="utf-8")

    try:
        cli._diversity_summary(tmp_path, replay=2)
    except cli.CliError as exc:
        assert "--replay requires API access" in str(exc)
    else:
        raise AssertionError("expected replay without client to fail")


class _ReplayClient:
    """A stand-in renderer whose ink density answers to the seeds we choose.

    `sensitive_to` names which seed actually moves the drawing, so a test can ask
    for a server that only the composition seed reaches, or only the performance
    seed. That is what tells the two sweeps apart: a harness that varies one seed
    while reporting both columns cannot make the blind column come out at zero.
    """

    def __init__(self, sensitive_to: str = "both") -> None:
        self.sensitive_to = sensitive_to
        self.requests: list[dict] = []

    def request_text(self, method: str, path: str, *, data: dict) -> str:
        self.requests.append(dict(data))
        ink = 0
        if self.sensitive_to in ("composition", "both"):
            ink += int(data.get("composition_seed") or 0) * 3
        if self.sensitive_to in ("performance", "both"):
            ink += int(data.get("render_seed") or 0) * 3
        width = max(1, min(16, ink))
        # The white ground has to be painted: a transparent SVG rasterizes to
        # alpha 0, which the grayscale conversion reads as full ink everywhere,
        # and then every repetition looks identical no matter what the seeds did.
        return (
            '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 16 16">'
            '<rect x="0" y="0" width="16" height="16" fill="white"/>'
            f'<rect x="0" y="0" width="{width}" height="16" fill="black"/>'
            "</svg>"
        )


def _replay_score_dir(tmp_path):
    (tmp_path / "a.json").write_text(json.dumps({
        "score": {"instructions": [{"primitive": "line", "from": [0.1, 0.2], "to": [0.9, 0.2]}]}
    }), encoding="utf-8")
    return tmp_path


def _replay_summary(tmp_path, client, *, replay: int = 3, replay_limit: int = 5):
    return cli._diversity_summary(
        _replay_score_dir(tmp_path),
        replay=replay,
        replay_limit=replay_limit,
        client=client,
    )


# T-1
def test_replay_composition_sweep_varies_composition_seed_and_pins_the_performance_seed(tmp_path):
    client = _ReplayClient()

    _replay_summary(tmp_path, client, replay=3)

    composition_sweep = client.requests[:3]
    assert [request["composition_seed"] for request in composition_sweep] == [1, 2, 3]
    assert {request["render_seed"] for request in composition_sweep} == {cli._REPLAY_PINNED_SEED}


# T-2
def test_replay_performance_sweep_varies_render_seed_and_pins_the_composition_seed(tmp_path):
    client = _ReplayClient()

    _replay_summary(tmp_path, client, replay=3)

    performance_sweep = client.requests[3:6]
    assert [request["render_seed"] for request in performance_sweep] == [1, 2, 3]
    assert {request["composition_seed"] for request in performance_sweep} == {cli._REPLAY_PINNED_SEED}


# T-3
def test_replay_reports_composition_and_performance_separately(tmp_path):
    summary = _replay_summary(tmp_path, _ReplayClient(), replay=3)

    replay = summary["replay"]
    assert replay["composition_divergence"] is not None
    assert replay["performance_divergence"] is not None
    item = replay["items"][0]
    assert item["composition_distance"] is not None
    assert item["performance_distance"] is not None


# T-4  (paired with T-5)
def test_replay_composition_column_alone_moves_for_a_composition_only_renderer(tmp_path):
    summary = _replay_summary(tmp_path, _ReplayClient("composition"), replay=3)

    item = summary["replay"]["items"][0]
    assert item["composition_distance"] > 0
    assert item["performance_distance"] == 0


# T-5  (paired with T-4: either one alone passes an implementation that builds
#       both columns from a single sweep)
def test_replay_performance_column_alone_moves_for_a_performance_only_renderer(tmp_path):
    summary = _replay_summary(tmp_path, _ReplayClient("performance"), replay=3)

    item = summary["replay"]["items"][0]
    assert item["performance_distance"] > 0
    assert item["composition_distance"] == 0


# T-6
def test_replay_costs_two_renders_per_repetition(tmp_path):
    client = _ReplayClient()

    _replay_summary(tmp_path, client, replay=4)

    assert len(client.requests) == 8


# T-7
def test_replay_records_which_seed_each_column_varied_and_that_old_runs_do_not_compare(tmp_path):
    summary = _replay_summary(tmp_path, _ReplayClient(), replay=2)

    note = summary["replay"]["seed_note"]
    assert "composition_distance varies composition_seed" in note
    assert "performance_distance varies render_seed" in note
    assert "not" in note and "comparable" in note


# T-8
def test_replay_limit_still_caps_the_artifacts(tmp_path):
    for name in ("a", "b", "c"):
        (tmp_path / f"{name}.json").write_text(json.dumps({
            "score": {"instructions": [{"primitive": "line", "from": [0.1, 0.2], "to": [0.9, 0.2]}]}
        }), encoding="utf-8")
    client = _ReplayClient()

    summary = cli._diversity_summary(tmp_path, replay=2, replay_limit=2, client=client)

    assert summary["replay"]["sample_count"] == 2
    assert len(client.requests) == 8


def test_v180_report_parsers_accept_history_census_and_unread_scopes():
    parser = cli.build_parser()

    census = parser.parse_args(["analyze", "--census", "--history"])
    unread = parser.parse_args(["unread-words", "--all", "--limit", "25"])

    assert census.input_dir is None
    assert census.census is True
    assert census.history is True
    assert unread.all_users is True
    assert unread.limit == 25


def test_v180_history_census_has_thumbnail_references_without_scores():
    summary = cli._motif_census_from_history([
        {
            "id": "history-1",
            "input": "赤い円",
            "score": {
                "instructions": [
                    {"primitive": "circle", "color": "red", "center": [0.5, 0.5], "radius": 0.2}
                ]
            },
        }
    ], base_url="http://example.test")

    assert summary["history_count"] == 1
    assert summary["motifs"][0]["frequency"] == 1
    example = summary["motifs"][0]["thumbnail_examples"][0]
    assert example["history_id"] == "history-1"
    assert example["thumbnail_url"] == "http://example.test/api/history/history-1/svg"
    assert "score" not in example


def test_v180_http_502_cost_ledger_counts_existing_failures():
    failures = [
        {"message": "HTTP 502: upstream failed"},
        {"message": "final retry failed: HTTP 502: upstream failed"},
        {"message": "HTTP 422: invalid"},
    ]

    assert cli._http_502_count(failures) == 2

def test_score_metrics_reports_cloudform_usage_and_context_as_mirror_only():
    score = {
        "instructions": [
            {
                "primitive": "cloudform",
                "center": [0.5, 0.5],
                "size": [0.6, 0.2],
                "mode": "carve",
                "surface": {"texture": "wash"},
                "variation": {"quality": "wave"},
                "arrangement": {"count": 4, "layout": "scatter"},
                "relation": {"type": "not_touching"},
            }
        ]
    }

    metrics = cli._score_metrics(score)

    assert metrics["score_cloudform_count"] == 1
    assert metrics["score_cloudform_expanded_count"] == 4
    assert metrics["score_has_cloudform"] is True
    assert metrics["score_cloudform_context_counts"] == {
        "arranged:scatter": 1,
        "mode:carve": 1,
        "relation:not_touching": 1,
        "surface:wash": 1,
        "variation:wave": 1,
    }


def test_plugin_parser_supports_list_validate_and_reload():
    parser = cli.build_parser()
    listed = parser.parse_args(["plugin", "list"])
    validated = parser.parse_args(["plugin", "validate", "sample.inku-plugin.md"])
    reloaded = parser.parse_args(["plugin", "reload"])
    assert listed.func is cli.command_plugin
    assert listed.plugin_action == "list"
    assert validated.file == "sample.inku-plugin.md"
    assert reloaded.plugin_action == "reload"


def test_plugin_validate_sends_document_body(monkeypatch, tmp_path, capsys):
    plugin_file = tmp_path / "sample.inku-plugin.md"
    plugin_file.write_text("---\nnamespace: Test\n---\n", encoding="utf-8")
    calls = []

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def request(self, method, path, *, data=None, **kwargs):
            calls.append((method, path, data))
            return {"valid": True}, None

    monkeypatch.setattr(cli, "ApiClient", FakeClient)
    parser = cli.build_parser()
    args = parser.parse_args(["plugin", "validate", str(plugin_file)])
    assert cli.command_plugin(args) == 0
    assert calls == [
        ("POST", "/api/plugins/validate", {"document": "---\nnamespace: Test\n---\n"})
    ]
    assert json.loads(capsys.readouterr().out) == {"valid": True}


def test_png_output_records_the_rasterizer_that_produced_it(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "svg_to_png", lambda svg, **kwargs: b"png")

    paths = cli._write_paint_outputs(
        {"svg": "<svg></svg>"}, out_dir=tmp_path, prefix="smoke", png=True
    )

    assert paths["png_rasterizer"]["backend"] == "resvg"
    assert paths["png_rasterizer"]["version"]
    # No PNG requested -> nothing to attribute.
    without = cli._write_paint_outputs(
        {"svg": "<svg></svg>"}, out_dir=tmp_path, prefix="plain", png=False
    )
    assert "png_rasterizer" not in without


def test_png_output_fails_when_resvg_is_absent(tmp_path, monkeypatch):
    """There is no fallback to warn about any more -- it raises instead.

    A backend that drops the material filters writes a PNG that looks cleaner
    than the work is, so the CLI would rather write nothing.
    """
    def unavailable(svg, **kwargs):
        raise cli.RasterizerUnavailable("resvg-py is not installed")

    monkeypatch.setattr(cli, "svg_to_png", unavailable)

    with pytest.raises(cli.CliError, match="resvg-py"):
        cli._write_paint_outputs({"svg": "<svg></svg>"}, out_dir=tmp_path, prefix="one", png=True)


def test_no_warning_when_resvg_is_present(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cli, "svg_to_png", lambda svg, **kwargs: b"png")

    cli._write_paint_outputs({"svg": "<svg></svg>"}, out_dir=tmp_path, prefix="quiet", png=True)

    assert capsys.readouterr().err == ""

def test_refine_perform_replaces_generate_but_keeps_the_legacy_spelling(monkeypatch):
    """`perform` is public; `generate` remains parseable without appearing in help."""
    calls = []

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def request(self, method, path, *, data=None, **kwargs):
            calls.append((method, path, data))
            if method == "GET":
                return {
                    "items": [
                        {
                            "id": "work-1",
                            "lineage_node_id": "node-1",
                            "source_text": "a small black circle",
                            "render_seed": 1,
                            "composition_seed": 2,
                            "interpretation_seed": "seed",
                            "render_color_catalog_id": "default",
                        }
                    ]
                }, None
            return {"svg": "<svg />", "render_hash_short": "ABCD"}, None

    monkeypatch.setattr(cli, "ApiClient", FakeClient)
    monkeypatch.setattr(cli, "_print_json", lambda data: None)
    parser = cli.build_parser()
    public = parser.parse_args(["refine", "perform", "work-1", "--kind", "color"])
    legacy = parser.parse_args(["refine", "generate", "work-1", "--kind", "color"])

    assert public.refine_cmd == "perform"
    assert legacy.refine_cmd == "generate"
    assert cli.command_refine(public) == 0
    assert cli.command_refine(legacy) == 0

    posted = [data for method, path, data in calls if method == "POST" and path == "/api/paint"]
    assert len(posted) == 2
    assert posted[0] == posted[1]

    refine = next(
        action.choices["refine"]
        for action in parser._actions
        if isinstance(action, argparse._SubParsersAction)
    )
    help_text = refine.format_help()
    assert "perform" in help_text
    assert "generate" not in help_text


def test_refine_color_asks_the_server_to_draw_a_different_catalog(monkeypatch):
    """The payload key is the whole feature here.

    `/api/paint` ignores fields it does not declare, so a stale key name is
    accepted with a 200 and silently leaves `catalog_mode` at "fixed" -- the
    refinement then redraws the same catalog it started from. Asserting the exit
    code or the response cannot see that, so read the key the CLI actually sent.
    """
    calls = []

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def request(self, method, path, *, data=None, **kwargs):
            calls.append((method, path, data))
            if method == "GET":
                return {
                    "items": [
                        {
                            "id": "work-1",
                            "lineage_node_id": "node-1",
                            "source_text": "a small black circle",
                            "render_seed": 1,
                            "composition_seed": 2,
                            "interpretation_seed": "seed",
                            "render_color_catalog_id": "ink_season",
                        }
                    ]
                }, None
            return {"svg": "<svg />", "render_hash_short": "ABCD"}, None

    monkeypatch.setattr(cli, "ApiClient", FakeClient)
    monkeypatch.setattr(cli, "_print_json", lambda data: None)
    parser = cli.build_parser()
    assert cli.command_refine(parser.parse_args(["refine", "perform", "work-1", "--kind", "color"])) == 0

    posted = [data for method, path, data in calls if method == "POST" and path == "/api/paint"]
    assert len(posted) == 1
    assert posted[0].get("catalog_mode") == "random"
    # The name the server dropped on 2026-08-01. Sending it again is a no-op.
    assert "random_color_catalog" not in posted[0]

    # The other three kinds must not ask for a draw.
    for kind in ("touch", "layout", "reading"):
        calls.clear()
        assert cli.command_refine(parser.parse_args(["refine", "perform", "work-1", "--kind", kind])) == 0
        other = [data for method, path, data in calls if method == "POST" and path == "/api/paint"]
        assert other[0].get("catalog_mode") is None


# --------------------------------------------------------------------------- #
# The eight request keys the CLI never named                                    #
#                                                                               #
# `/api/paint` has always accepted them; the CLI simply left them out of the    #
# request body, so every CLI run took the server default while the web UI sent  #
# its own. The result was that no CLI drawing ever went through Stage 0.5, and  #
# `--wild` / variation / `catalog_mode` were unreachable from the command line. #
# --------------------------------------------------------------------------- #

# (argv fragment, request key, the value the key must carry)
SENDER_PARITY_FLAGS = [
    (["--sketch"], "sketch", True),
    (["--sketch-grain", "coarse"], "sketch_grain", "coarse"),
    (["--sketch-text", "a wet black line"], "sketch_text", "a wet black line"),
    (["--variation-amplitude", "large"], "variation_amplitude", "large"),
    (["--variation-seed", "7"], "variation_seed", 7),
    (["--wild"], "wild", True),
    (["--catalog-mode", "auto"], "catalog_mode", "auto"),
    (["--interpretation-seed", "reading-2"], "interpretation_seed", "reading-2"),
]

# What a bare `paint TEXT` puts on the wire today. Frozen deliberately: the whole
# point of the change is that adding the eight keys must not alter the request of
# a run that names none of them, or every past bench stops being comparable.
PAYLOAD_KEYS_WITHOUT_FLAGS = {
    "catalog_id",
    "description",
    "include_thinking",
    "instruction_lang",
    "save_history",
    "stage1_input",
}

# Every key the payload dict could carry before the eight were added.
PAYLOAD_KEYS_BEFORE = {
    "canvas_aspect",
    "catalog_id",
    "composition_seed",
    "description",
    "history_input",
    "include_thinking",
    "include_trace",
    "instruction_lang",
    "render_seed",
    "save_artifacts",
    "save_history",
    "seed_text",
    "stage1_input",
    "stage1_model",
    "stage2_model",
    "ui_lang",
}

# Every pre-existing flag, so that the "all keys" count is measured and not assumed.
ALL_PRIOR_FLAGS = [
    "--stage1-model", "s1",
    "--stage2-model", "s2",
    "--include-thinking",
    "--ui-lang", "ja",
    "--save-history",
    "--save-artifacts",
    "--history-input", "history text",
    "--catalog-id", "default",
    "--canvas-aspect", "golden",
    "--render-seed", "11",
    "--composition-seed", "22",
    "--seed-text", "seed",
    "--trace",
]


@pytest.mark.parametrize("argv,key,value", SENDER_PARITY_FLAGS, ids=[key for _, key, _ in SENDER_PARITY_FLAGS])
def test_paint_payload_carries_each_layer_flag(argv, key, value):
    """One case per key, so a dropped line names the key it dropped.

    Rolled into a single test, deleting one line from the payload dict would
    still be one red, and the report would not say which layer stopped being
    asked for.
    """
    parser = cli.build_parser()
    payload = cli._paint_payload(parser.parse_args(["paint", "一滴の墨", *argv]), "一滴の墨")

    assert key in payload, f"{key} は旗を立てても送られていない"
    assert payload[key] == value


def test_paint_payload_without_the_new_flags_is_byte_for_byte_the_old_request():
    """Without this, an implementation that always sends all eight passes above.

    `False` is not `None`, so a bare `"wild": args.wild` survives the drop-None
    filter and puts an eighteenth key on the wire for every existing bench run.
    """
    parser = cli.build_parser()
    payload = cli._paint_payload(parser.parse_args(["paint", "一滴の墨"]), "一滴の墨")

    assert set(payload) == PAYLOAD_KEYS_WITHOUT_FLAGS
    for _, key, _ in SENDER_PARITY_FLAGS:
        assert key not in payload, f"{key} を渡していないのに送っている"


def test_paint_payload_grows_by_exactly_the_eight_keys():
    """16 keys before, 24 after -- and the 16 are the same 16.

    It was 17 and 25 until the staffage level was folded away (v2.11.0) and
    `tenkei` left the request body with the `--staffage` flag.
    """
    parser = cli.build_parser()
    argv = ["paint", "一滴の墨", *ALL_PRIOR_FLAGS]
    prior_only = cli._paint_payload(parser.parse_args(argv), "一滴の墨")
    assert set(prior_only) == PAYLOAD_KEYS_BEFORE
    assert len(prior_only) == 16

    new_flags = [item for argv_fragment, _, _ in SENDER_PARITY_FLAGS for item in argv_fragment]
    everything = cli._paint_payload(parser.parse_args([*argv, *new_flags]), "一滴の墨")
    assert len(everything) == 24
    assert set(everything) - PAYLOAD_KEYS_BEFORE == {key for _, key, _ in SENDER_PARITY_FLAGS}


def _subparser(name: str) -> argparse.ArgumentParser:
    parser = cli.build_parser()
    action = next(a for a in parser._actions if isinstance(a, argparse._SubParsersAction))
    return action.choices[name]


@pytest.mark.parametrize("command", ["paint", "batch"])
def test_both_drawing_commands_accept_the_layer_flags(command):
    """`batch` is where the benches run. A flag on `paint` alone reaches no bench."""
    flags = _all_option_strings(_subparser(command))
    for argv, key, _ in SENDER_PARITY_FLAGS:
        assert argv[0] in flags, f"{command} に {argv[0]} が無い ({key})"

    base = ["paint", "一滴の墨"] if command == "paint" else ["batch", "--file", "-"]
    every_flag = [item for argv, _, _ in SENDER_PARITY_FLAGS for item in argv]
    parsed = cli.build_parser().parse_args([*base, *every_flag])
    assert parsed.sketch is True
    assert parsed.wild is True
    assert parsed.catalog_mode == "auto"


@pytest.mark.parametrize("argv,key,value", SENDER_PARITY_FLAGS, ids=[key for _, key, _ in SENDER_PARITY_FLAGS])
def test_every_layer_flag_carries_help(argv, key, value):
    """A flag nobody can find from `--help` is a flag nobody uses."""
    for command in ("paint", "batch"):
        action = next(
            item for item in _subparser(command)._actions
            if argv[0] in (item.option_strings or [])
        )
        assert (action.help or "").strip(), f"{command} {argv[0]} の help が空"


def _readme_usage_block(command: str) -> str:
    readme = (Path(__file__).resolve().parents[1] / "README.md").read_text(encoding="utf-8")
    header = f"### `inku-cli {command}`\n\n```\n"
    start = readme.index(header) + len(header)
    return readme[start:readme.index("\n```\n", start)]


@pytest.mark.parametrize("command", ["paint", "batch"])
def test_the_manual_lists_the_layer_flags(command):
    """The manual is part of the feature: an undocumented flag is an unused flag.

    Looking for the flag anywhere in the block is not enough. The usage synopsis
    at the top of the block names every flag as `[--wild]`, so deleting the entry
    that says what `--wild` DOES leaves the bare name behind and a whole-block
    search stays green. Assert on the options entry, and on what it says.
    """
    block = _readme_usage_block(command)
    assert "usage: inku-cli" in block
    synopsis = " ".join(block[:block.index("\noptions:")].split())
    flat = " ".join(block.split())
    for argv, key, _ in SENDER_PARITY_FLAGS:
        flag = argv[0]
        assert re.search(rf"(?<![\w-]){re.escape(flag)}(?![\w-])", synopsis), \
            f"cli/README.md の {command} usage の一行目の並びに {flag} が無い ({key})"
        assert re.search(rf"^  {re.escape(flag)}\b", block, re.M), \
            f"cli/README.md の {command} usage の options に {flag} の項目が無い ({key})"
        action = next(
            item for item in _subparser(command)._actions
            if flag in (item.option_strings or [])
        )
        # The first words of the live help, so a manual that keeps the name but
        # describes an older behaviour is a failure rather than a pass.
        opening = " ".join((action.help or "").split()[:6])
        assert opening and opening in flat, \
            f"cli/README.md の {command} usage の {flag} の説明が help と食い違っている"


def test_the_sketch_help_says_whose_default_it_is():
    """The whole contract started from the defaults differing per sender."""
    action = next(
        item for item in _subparser("paint")._actions
        if "--sketch" in (item.option_strings or []) and item.option_strings == ["--sketch"]
    )
    help_text = (action.help or "").lower()
    assert "server default is off" in help_text
    assert "web" in help_text and "fine" in help_text


def test_sketch_fields_reach_the_artifact_summary():
    """Stage 0.5 is the only layer whose output is prose, and prose is not in the SVG.

    Without carrying these, a bench run through --sketch keeps the drawing and
    loses the sentence the later stages actually read. sketch_state is the
    fourth: it says which of the silences a missing prose is.
    """
    summary = cli._sketch_response_summary({
        "sketch_text": "黒い線が一本、紙の左から右へ走る。",
        "sketch_grain": "fine",
        "sketch_fallback_used": False,
        "sketch_state": "fine",
    })
    assert summary == {
        "sketch_text": "黒い線が一本、紙の左から右へ走る。",
        "sketch_grain": "fine",
        "sketch_fallback_used": False,
        "sketch_state": "fine",
    }

    # A compose (DDL-mode) result never runs Stage 0.5; the keys are still present
    # so a reader does not have to know which route wrote the artifact. The state
    # travels from the response, because "the layer did not apply here" and "the
    # layer was refused" are different facts about the drawing.
    composed = cli._compose_response_as_paint_result(
        {"svg": "<svg />", "score": {}, "sketch_state": "not_applicable"},
        ddl="白い背景に黒い線を一本引く。",
        input_text="線",
        stage2_model="s2",
    )
    assert composed["sketch_text"] is None
    assert composed["sketch_grain"] is None
    assert composed["sketch_fallback_used"] is False
    assert composed["sketch_state"] == "not_applicable"


def test_the_cli_history_save_carries_what_the_layer_did():
    """The CLI is a sender to POST /api/history, and a sender that says nothing
    about the layer has its works recorded as older than the column."""
    args = argparse.Namespace(
        history_input=None, canvas_aspect=None, save_artifacts=None, save_history=True
    )
    payload = cli._history_payload_from_result(
        args,
        {
            "score": {},
            "svg": "<svg />",
            "sketch_text": "円がある。円は黒い。",
            "sketch_grain": "coarse",
            "sketch_state": "coarse",
        },
        input_text="円",
        ddl="円を置く。",
        stage1_model=None,
        stage2_model="s2",
        color_catalog="default",
        at=1,
    )
    assert payload["sketch_text"] == "円がある。円は黒い。"
    assert payload["sketch_grain"] == "coarse"
    assert payload["sketch_state"] == "coarse"

    # Nothing to say is said by saying nothing: the key is dropped rather than
    # sent as null, and the server derives the state from what the row carries.
    quiet = cli._history_payload_from_result(
        args,
        {"score": {}, "svg": "<svg />"},
        input_text="円",
        ddl="円を置く。",
        stage1_model=None,
        stage2_model="s2",
        color_catalog="default",
        at=1,
    )
    assert "sketch_state" not in quiet


def test_the_saved_artifact_names_the_sketch_fields_even_when_the_server_omits_them(tmp_path):
    """Measured against the live server on 2026-08-04, not imagined.

    `/api/paint` leaves null fields out of the response body, so a run WITHOUT
    --sketch came back with no `sketch_text` key at all. Writing the response
    through unchanged gave the two runs of one bench different key sets, and left
    "Stage 0.5 did not run here" indistinguishable from an older CLI, an older
    server, or a truncated file.
    """
    from_a_run_without_sketch = {"svg": "<svg />", "render_hash_short": "8F21"}
    cli._write_paint_outputs(from_a_run_without_sketch, out_dir=tmp_path, prefix="quiet", png=False)
    saved = json.loads((tmp_path / "quiet.json").read_text(encoding="utf-8"))
    assert saved["sketch_text"] is None
    assert saved["sketch_grain"] is None
    assert saved["sketch_fallback_used"] is False

    # What the server did say is kept as it said it.
    from_a_run_with_sketch = {"svg": "<svg />", "sketch_text": "葉がある。", "sketch_grain": "fine"}
    cli._write_paint_outputs(from_a_run_with_sketch, out_dir=tmp_path, prefix="sketched", png=False)
    spoken = json.loads((tmp_path / "sketched.json").read_text(encoding="utf-8"))
    assert spoken["sketch_text"] == "葉がある。"
    assert spoken["sketch_grain"] == "fine"


# ---------------------------------------------------------------------------
# The render limit flags (`config update --limit-*`)
#
# The CLI is the only sender that can reach PUT /api/settings/limits: web has
# the Limits tab, android has no settings route at all. Nothing else watches
# what these nine flags put in the request body, and a receiver that drops
# unknown keys keeps a misspelled name at 200
# (silent_sender_is_never_tested / api_field_rename_count_all_senders).
# ---------------------------------------------------------------------------


def _fake_client_recording(monkeypatch):
    calls = []

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def request(self, method, path, *, data=None, **kwargs):
            calls.append((method, path, data))
            return {}, None

    monkeypatch.setattr(cli, "ApiClient", FakeClient)
    return calls


def test_config_update_sends_only_the_render_limit_flags_that_were_given(monkeypatch):
    """A partial update carries the flags that were passed and nothing else.

    The server merges the body over what is stored, so sending the untouched
    fields as well would overwrite a value the author set from the web tab.
    """
    calls = _fake_client_recording(monkeypatch)
    parser = cli.build_parser()
    args = parser.parse_args(
        [
            "config",
            "update",
            "--limit-literal-count-threshold",
            "480",
            "--limit-max-instructions",
            "60",
        ]
    )
    assert cli.command_config(args) == 0
    assert calls == [
        (
            "PUT",
            "/api/settings/limits",
            {"literal_count_threshold": 480, "max_instructions": 60},
        )
    ]


def test_every_render_limit_flag_reaches_the_body_under_its_own_name(monkeypatch):
    """Each of the nine flags carries its own value, one for one.

    Distinct values per field, so a flag wired to the wrong key -- or to the
    same key twice -- cannot pass (invariance_gate_misses_the_binding).
    """
    calls = _fake_client_recording(monkeypatch)
    parser = cli.build_parser()
    argv = ["config", "update"]
    expected = {}
    for offset, name in enumerate(cli.RENDER_LIMIT_FIELDS):
        value = 101 + offset
        argv += ["--limit-" + name.replace("_", "-"), str(value)]
        expected[name] = value
    assert cli.command_config(parser.parse_args(argv)) == 0
    assert calls == [("PUT", "/api/settings/limits", expected)]


def test_limits_reset_replaces_the_body_instead_of_adding_to_it(monkeypatch):
    """A value passed alongside --limits-reset must not survive it.

    Asserted WITH another flag on the same line: on its own the body is empty
    either way, so replacing and merging look identical and the assertion is
    vacuous (half_perturbation_masked_by_resnap).
    """
    calls = _fake_client_recording(monkeypatch)
    parser = cli.build_parser()
    args = parser.parse_args(
        ["config", "update", "--limits-reset", "--limit-max-instructions", "60"]
    )
    assert cli.command_config(args) == 0
    assert calls == [("PUT", "/api/settings/limits", {"reset_to_defaults": True})]


def test_config_update_without_a_limit_flag_sends_no_limits_request(monkeypatch):
    """The control for the three tests above: no flag, no request.

    Without this a handler that always PUT the full set would still pass them.
    """
    calls = _fake_client_recording(monkeypatch)
    parser = cli.build_parser()
    assert cli.command_config(parser.parse_args(["config", "update"])) == 0
    assert calls == []


def test_the_cli_limit_names_match_the_server_dataclass():
    """The names are written out here, so they can drift from the server's.

    Skips on the ABSENCE OF THE server DIRECTORY rather than a missing file --
    the CLI is installed on its own in some checkouts
    (server_tests_reading_client_sources_fail_on_pentala).
    """
    repo_root = Path(cli.__file__).resolve().parents[3]
    server_dir = repo_root / "server"
    if not server_dir.is_dir():
        pytest.skip("server/ is not present in this checkout")
    source = (server_dir / "src" / "inku_server" / "limits.py").read_text(encoding="utf-8")
    body = source.split("class Limits:", 1)[1].split("DEFAULT_LIMITS", 1)[0]
    declared = set(re.findall(r"^    ([a-z_]+): int = ", body, flags=re.MULTILINE))
    assert declared, "no fields read off the server dataclass"
    assert declared == set(cli.RENDER_LIMIT_FIELDS)


# --- The Command Line Help Reference is generated, and these hold it there ---
#
# The manual once named --original-text three renames after the flag had become
# --description, because the reference section is `--help` copied by hand and
# nothing compared the copy to the parser. The section now belongs to
# scripts/gen_readme_help.py; what follows asserts two of the three edges
# between parser, manual and generator, plus the markers that bound the region.

HELP_START = "<!-- HELP_START -->"
HELP_END = "<!-- HELP_END -->"
GENERATOR = Path(__file__).resolve().parents[1] / "scripts" / "gen_readme_help.py"

# The generator pins this so the file does not depend on the terminal that ran
# it. The gate has to read at the same width or every wrapped line disagrees.
os.environ["COLUMNS"] = "80"


def _command_paths(parser: argparse.ArgumentParser, prefix: str = "") -> list[str]:
    """Every command the parser declares. Walked here rather than imported from
    the generator, so a missing generator cannot make this gate vacuous."""
    found = [prefix]
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            for name, sub in action.choices.items():
                found.extend(_command_paths(sub, f"{prefix} {name}".strip()))
    return found


MANUAL_COMMAND_PATHS = _command_paths(cli.build_parser())


def _marked_region() -> str:
    readme = (Path(__file__).resolve().parents[1] / "README.md").read_text(encoding="utf-8")
    assert HELP_START in readme and HELP_END in readme, (
        "cli/README.md の help マーカーが欠けている。"
        "マーカーは生成器が書いてよい範囲の境界なので、消えると"
        "「見る対象が減る」だけで検査が緑になる"
    )
    return readme[readme.index(HELP_START) + len(HELP_START):readme.index(HELP_END)]


def test_the_manual_keeps_both_help_markers():
    """Deleting a marker must not be a silent way to shrink what is checked."""
    region = _marked_region()
    assert region.count("### `inku-cli") == len(MANUAL_COMMAND_PATHS), (
        f"マーカー間の節が {region.count('### `inku-cli')} で、"
        f"パーサの経路 {len(MANUAL_COMMAND_PATHS)} と合わない"
    )


@pytest.mark.parametrize("path", MANUAL_COMMAND_PATHS, ids=[p or "root" for p in MANUAL_COMMAND_PATHS])
def test_the_manual_is_what_the_parser_prints(path):
    """A flag added without regenerating leaves the manual describing an older
    command. Compare the whole block, not the flag names: a stale description
    under the right name is the failure that started this."""
    title = f"inku-cli {path}".strip()
    header = f"### `{title}`\n\n```\n"
    region = _marked_region()
    assert header in region, (
        f"cli/README.md のマーカー間に `{title}` の節が無い。"
        f"`uv run python scripts/gen_readme_help.py` で再生成する"
    )
    start = region.index(header) + len(header)
    documented = region[start:region.index("\n```\n", start)]

    parser = cli.build_parser()
    for name in path.split():
        action = next(a for a in parser._actions if isinstance(a, argparse._SubParsersAction))
        parser = action.choices[name]

    assert documented == parser.format_help(), (
        f"cli/README.md の `{title}` が --help と食い違っている。"
        f"`uv run python scripts/gen_readme_help.py` で再生成する"
    )


def test_the_generator_says_the_manual_is_current():
    """The other edge: manual against generator. The gate above would stay green
    if the generator were broken, and a gate without a repair path is why the
    ruling asked for the script rather than the assertion alone."""
    assert GENERATOR.is_file(), (
        f"{GENERATOR} が無い。ゲートが赤くなったとき 1,200 行を直す手段が消える"
    )
    done = subprocess.run(
        [sys.executable, str(GENERATOR), "--check"],
        capture_output=True,
        text=True,
        cwd=GENERATOR.parent.parent,
    )
    assert done.returncode == 0, done.stderr or done.stdout


# T-9
def test_the_manual_lists_the_rasterize_command():
    """A subcommand added without regenerating leaves a manual that does not know
    the command exists. The gates above compare the blocks that are there; this
    one says which command has to be among them."""
    assert "### `inku-cli rasterize`" in _marked_region(), (
        "cli/README.md の help 節に rasterize が無い。"
        "`uv run python scripts/gen_readme_help.py` で再生成する"
    )


def test_cli_product_source_has_no_orphaned_render_version_or_hash_helpers():
    source = Path(cli.__file__).read_text(encoding="utf-8")

    for name in ("_SERVER_RENDER_VERSION_KEYS", "_server_render_versions", "_render_hash_for_score"):
        assert name not in source, f"{name} remains in cli/src"


SERVER_INFO = {
    "name": "inku-server",
    "version": "v2.11.4",
    "release_version": "2.7.2",
    "build_number": "859",
    "render_engine_id": "default",
    "render_engine_version": "22",
    "ddl_version": "3",
    "ddl_engine_version": "7",
}


class _FakeResponse:
    """Just the headers: /api/render-svg says in them what the SVG cannot."""

    def __init__(self, headers):
        self.headers = dict(headers)


def _render_score_client(info=None, *, info_fails=False, render_headers=None):
    """A client for `render-score`: catalogs and the JSON drawing response."""
    payload = SERVER_INFO if info is None else info
    headers = {} if render_headers is None else dict(render_headers)

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def request(self, method, path, **kwargs):
            if path == "/api/color-catalogs":
                # The wire format is a list; CATALOG_DATA is the normalized one.
                return {
                    "default_catalog_id": CATALOG_DATA["default_catalog_id"],
                    "catalogs": list(CATALOG_DATA["catalogs"].values()),
                }, None
            if path == "/api/render-score":
                if info_fails:
                    raise cli.CliError("connection refused")
                sent = kwargs.get("data") or {}
                FakeClient.sent.append(sent)
                score = json.loads(json.dumps(sent["score"]))
                score.setdefault("canvas", "square")
                if sent.get("ddl"):
                    score["instructions"] = [
                        *score.get("instructions", []),
                        {"primitive": "line"},
                        {"primitive": "circle"},
                        {"primitive": "square"},
                    ]
                catalog_id = (
                    headers.get("X-Inku-Color-Catalog-Id")
                    or sent.get("catalog_id")
                    or CATALOG_DATA["default_catalog_id"]
                )
                response = {
                    "score": score,
                    "svg": (
                        "<svg data-ddl='true'></svg>"
                        if sent.get("ddl")
                        else "<svg></svg>"
                    ),
                    "render_hash": f"rh3:{payload.get('render_engine_version', 'missing')}:{bool(sent.get('ddl'))}",
                    "render_hash_short": "ABCD",
                    "render_build_number": payload.get("build_number"),
                    "render_engine_id": payload.get("render_engine_id"),
                    "render_engine_version": payload.get("render_engine_version"),
                    "ddl_version": payload.get("ddl_version"),
                    "ddl_engine_version": payload.get("ddl_engine_version"),
                    "render_color_catalog_id": catalog_id,
                    "render_color_source": headers.get("X-Inku-Color-Source") or "catalog",
                    "render_canvas_aspect": sent.get("canvas_aspect") or "square",
                    "render_canvas_aspect_id": sent.get("canvas_aspect") or "square",
                    "render_canvas_aspect_ratio": 1.0,
                    "render_seed": sent.get("render_seed") or 1,
                    "composition_seed": sent.get("composition_seed"),
                    # I-154: the limits that drew it, which of the four sources
                    # decided them, and which of them took effect. Mirrored here
                    # because the server sends all three on this route.
                    "render_limits": {"represented_count_max": 120},
                    "render_limits_source": "work" if sent.get("work_id") else "settings",
                    "render_limit_notes": ["represented_count_max: 600 drawn as 120"],
                }
                return response, _FakeResponse(headers)
            raise AssertionError(f"unexpected request: {method} {path}")

        def request_raw(self, method, path, **kwargs):
            raise AssertionError(f"unexpected raw request: {method} {path}")

    FakeClient.sent = []
    return FakeClient


def _run_render_score(monkeypatch, capsys, client, *extra_argv):
    monkeypatch.setattr(cli, "ApiClient", client)
    parser = cli.build_parser()
    args = parser.parse_args([
        "render-score",
        json.dumps({"version": "0.1.0", "background": "white", "instructions": []}),
        "--color-catalog", "default",
        "--render-seed", "4242",
        *extra_argv,
    ])
    assert cli.command_render_score(args) == 0
    return json.loads(capsys.readouterr().out)


def test_render_score_names_the_engine_version_the_server_drew_with(monkeypatch, capsys):
    """The server drew it, so the server names the engine it drew with.

    This used to be the literal "2" while the engine had reached 22, so every
    artifact the command wrote claimed an engine twenty versions old. Nothing in
    the SVG says otherwise, which is why it went unnoticed.
    """
    result = _run_render_score(monkeypatch, capsys, _render_score_client())

    assert result["render_engine_version"] == "22"


def test_render_score_names_the_ddl_layer_versions_the_server_drew_with(monkeypatch, capsys):
    info = {**SERVER_INFO, "ddl_version": "13", "ddl_engine_version": "29"}
    result = _run_render_score(monkeypatch, capsys, _render_score_client(info))

    assert result["ddl_version"] == "13"
    assert result["ddl_engine_version"] == "29"


def test_render_score_sends_the_composition_seed_it_records(monkeypatch, capsys):
    """Recording a seed the picture was not drawn with is worse than not naming one.

    Since render engine 23 `composition_seed` decides the placement, so the request
    has to carry it. The command wrote it into the output metadata and into the
    render hash while never sending it, so both named a seed the server never saw
    and the drawing kept the placement of `--render-seed`.
    """
    client = _render_score_client()
    result = _run_render_score(monkeypatch, capsys, client, "--composition-seed", "777")

    assert client.sent[-1]["composition_seed"] == 777
    assert result["composition_seed"] == 777


def test_render_score_leaves_the_composition_seed_out_when_it_is_not_asked_for(monkeypatch, capsys):
    """The counterpart: absent must stay absent, not become a number.

    The server reads this field with `is not None`, so sending anything other
    than None would take the placement off the performance seed for every caller
    that never asked for a composition seed.
    """
    client = _render_score_client()
    _run_render_score(monkeypatch, capsys, client)

    assert client.sent[-1]["composition_seed"] is None


def test_render_score_takes_the_build_number_from_the_server(monkeypatch, capsys):
    """Not from whichever checkout the CLI happens to be run from.

    A CLI pointed at pentala used to record the Mac's `web/BUILD_NUMBER` for a
    drawing the Mac did not make.
    """
    info = {**SERVER_INFO, "build_number": "1234"}
    result = _run_render_score(monkeypatch, capsys, _render_score_client(info))

    assert result["render_build_number"] == "1234"
    assert result["render_build_number"] != cli._cli_build_number()


def test_render_score_takes_the_engine_id_from_the_server(monkeypatch, capsys):
    info = {**SERVER_INFO, "render_engine_id": "experimental"}
    result = _run_render_score(monkeypatch, capsys, _render_score_client(info))

    assert result["render_engine_id"] == "experimental"


def test_render_score_refuses_to_guess_when_the_server_will_not_say(monkeypatch):
    """No fallback, for the reason `_rasterize_png` has none.

    An artifact that names a version nobody checked still gets used to decide
    things, and unlike a dropped filter a wrong version is invisible in the
    drawing itself. Missing keys count as not saying.
    """
    monkeypatch.setattr(cli, "ApiClient", _render_score_client(info_fails=True))
    parser = cli.build_parser()
    args = parser.parse_args([
        "render-score",
        json.dumps({"version": "0.1.0", "background": "white", "instructions": []}),
        "--color-catalog", "default",
    ])
    with pytest.raises(cli.CliError, match="/api/render-score"):
        cli.command_render_score(args)

    incomplete = {key: value for key, value in SERVER_INFO.items() if key != "render_engine_version"}
    monkeypatch.setattr(cli, "ApiClient", _render_score_client(incomplete))
    with pytest.raises(cli.CliError, match="render_engine_version"):
        cli.command_render_score(args)

    incomplete = {key: value for key, value in SERVER_INFO.items() if key != "ddl_engine_version"}
    monkeypatch.setattr(cli, "ApiClient", _render_score_client(incomplete))
    with pytest.raises(cli.CliError, match="ddl_engine_version"):
        cli.command_render_score(args)


def test_render_score_hashes_with_the_server_engine_version(monkeypatch, capsys):
    """The version is material to the hash, not decoration beside it.

    Two runs that differ only in the engine the server reports must not collide:
    the same score drawn by two engines is two works.
    """
    first = _run_render_score(monkeypatch, capsys, _render_score_client())
    other = _run_render_score(
        monkeypatch, capsys, _render_score_client({**SERVER_INFO, "render_engine_version": "23"})
    )

    assert first["render_hash"] != other["render_hash"]


def test_render_score_hands_ddl_to_the_named_endpoint(monkeypatch, capsys):
    client = _render_score_client()

    result = _run_render_score(
        monkeypatch,
        capsys,
        client,
        "--ddl-text",
        "Draw the explicit DDL constraints.",
        "--full-json",
    )

    assert len(result["score"]["instructions"]) == 3


def test_render_score_sends_the_ddl_field_to_the_server(monkeypatch, capsys):
    client = _render_score_client()

    _run_render_score(
        monkeypatch,
        capsys,
        client,
        "--ddl-text",
        "Draw the explicit DDL constraints.",
    )

    assert client.sent[-1]["ddl"] == "Draw the explicit DDL constraints."


def test_render_score_without_a_ddl_flag_sends_no_ddl(monkeypatch, capsys):
    client = _render_score_client()

    result = _run_render_score(monkeypatch, capsys, client, "--full-json")

    assert result["svg"] == "<svg></svg>"
    assert "ddl" not in client.sent[-1]


def _legacy_render_hash_for_score(
    score,
    *,
    render_seed,
    composition_seed,
    render_build_number,
    render_engine_id,
    render_engine_version,
    render_color_catalog_id,
):
    payload = {
        "version": "rh2",
        "score": score or {},
        "render_seed": render_seed,
        "composition_seed": composition_seed,
        "render_build_number": render_build_number,
        "render_engine_id": render_engine_id,
        "render_engine_version": render_engine_version,
        "render_color_catalog_id": render_color_catalog_id,
    }
    canonical = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return "rh2:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def test_render_score_without_ddl_changes_only_server_owned_output_keys(
    monkeypatch, capsys
):
    result = _run_render_score(
        monkeypatch, capsys, _render_score_client(), "--full-json"
    )
    input_score = {
        "version": "0.1.0",
        "background": "white",
        "instructions": [],
    }
    old_hash = _legacy_render_hash_for_score(
        input_score,
        render_seed=4242,
        composition_seed=None,
        render_build_number=SERVER_INFO["build_number"],
        render_engine_id=SERVER_INFO["render_engine_id"],
        render_engine_version=SERVER_INFO["render_engine_version"],
        render_color_catalog_id=CATALOG_DATA["default_catalog_id"],
    )
    origin = {
        **result,
        "score": input_score,
        "render_hash": old_hash,
        "render_hash_short": old_hash[-4:].upper(),
    }

    changed = {key for key in result if result[key] != origin[key]}

    assert changed == {"score", "render_hash", "render_hash_short"}
    assert result["svg"] == origin["svg"]


def test_render_score_rejects_both_ddl_sources(monkeypatch):
    monkeypatch.setattr(cli, "ApiClient", _render_score_client())
    parser = cli.build_parser()
    args = parser.parse_args(
        [
            "render-score",
            json.dumps({"version": "0.1.0", "background": "white", "instructions": []}),
            "--ddl-text",
            "inline",
            "--ddl-file",
            "ddl.txt",
        ]
    )

    with pytest.raises(cli.CliError, match="--ddl-text and --ddl-file"):
        cli.command_render_score(args)


def test_render_score_reads_ddl_from_standard_input(monkeypatch, capsys):
    client = _render_score_client()
    monkeypatch.setattr(sys, "stdin", io.StringIO("DDL from stdin\n"))

    _run_render_score(monkeypatch, capsys, client, "--ddl-file", "-")

    assert client.sent[-1]["ddl"] == "DDL from stdin"


def test_the_manual_lists_both_render_score_ddl_flags():
    header = "### `inku-cli render-score`\n\n```\n"
    region = _marked_region()
    start = region.index(header)
    end = region.index("\n```\n", start + len(header))
    render_score_help = region[start:end]

    assert "--ddl-text" in render_score_help
    assert "--ddl-file" in render_score_help


# `rasterize` -- the CLI is the thin door onto inku_analysis.rasterize_batch, which
# is where the rule for burning a picture lives. These two say the door is thin.

def _rasterize_corpus(tmp_path):
    """A directory a naive implementation would actually try to rasterize."""
    src = tmp_path / "svg"
    src.mkdir()
    for name in ("one", "two"):
        (src / f"{name}.svg").write_text(
            '<svg xmlns="http://www.w3.org/2000/svg" width="40" height="20">'
            '<circle cx="10" cy="10" r="5" fill="black"/></svg>',
            encoding="utf-8",
        )
    return src


# T-7
def test_rasterize_calls_the_shared_batch_and_burns_nothing_of_its_own(monkeypatch, capsys, tmp_path):
    src = _rasterize_corpus(tmp_path)
    calls = []

    def fake_rasterize_dir(source, target, **kwargs):
        calls.append((Path(source), Path(target)))
        return Report(written=(Path("one.png"),), failed=())

    def forbidden(*args, **kwargs):
        raise AssertionError("the CLI rasterized on its own instead of calling rasterize_dir")

    monkeypatch.setattr(cli, "rasterize_dir", fake_rasterize_dir)
    # A second implementation written here would reach the rasterizer through this
    # name, the way `paint --png` does.
    monkeypatch.setattr(cli, "svg_to_png", forbidden)

    args = cli.build_parser().parse_args(
        ["rasterize", "--in", str(src), "--out", str(tmp_path / "png")]
    )
    assert cli.command_rasterize(args) == 0

    assert calls == [(src, tmp_path / "png")]
    assert json.loads(capsys.readouterr().out)["written"] == 1


# T-8
@pytest.mark.parametrize(
    "extra, expected",
    [
        ([], {"width": None, "workers": 1}),
        (["--width", "1618", "--workers", "6"], {"width": 1618, "workers": 6}),
    ],
    ids=["without-flags", "with-flags"],
)
def test_rasterize_hands_width_and_workers_straight_through(monkeypatch, capsys, tmp_path, extra, expected):
    """Including when the flags are absent: a default that stops at the parser and
    never reaches the batch is a flag nobody is carrying."""
    seen = {}

    def fake_rasterize_dir(source, target, *, width, workers):
        seen.update(width=width, workers=workers)
        return Report(written=(), failed=())

    monkeypatch.setattr(cli, "rasterize_dir", fake_rasterize_dir)
    args = cli.build_parser().parse_args(
        ["rasterize", "--in", str(_rasterize_corpus(tmp_path)), "--out", str(tmp_path / "png"), *extra]
    )
    assert cli.command_rasterize(args) == 0
    capsys.readouterr()

    assert seen == expected


def test_rasterize_reports_the_files_it_could_not_burn(monkeypatch, capsys, tmp_path):
    """A dropped population has to be readable from the artifact, not only from
    the terminal, and the exit status has to say the run was not whole."""
    monkeypatch.setattr(
        cli,
        "rasterize_dir",
        lambda source, target, **kwargs: Report(
            written=(Path("one.png"),),
            failed=(Failure(Path("two.svg"), "child killed by signal 11"),),
        ),
    )
    args = cli.build_parser().parse_args(
        ["rasterize", "--in", str(_rasterize_corpus(tmp_path)), "--out", str(tmp_path / "png")]
    )
    assert cli.command_rasterize(args) == 1

    captured = capsys.readouterr()
    summary = json.loads(captured.out)
    assert (summary["attempted"], summary["written"], summary["failed"]) == (2, 1, 1)
    assert summary["unresolved"] == [{"source": "two.svg", "reason": "child killed by signal 11"}]
    assert "UNRESOLVED two.svg" in captured.err


# --from-work: the work's own colors ------------------------------------------
#
# The flag has to reach the drawing, not a log line. Each test below names a
# place where dropping it would change the output, so an argument that is
# parsed and then discarded cannot pass them (contract perturbation P-6).


def _run_render_score_from_work(monkeypatch, capsys, client, *extra_argv):
    """Like `_run_render_score`, minus the catalog: --from-work refuses both."""
    monkeypatch.setattr(cli, "ApiClient", client)
    parser = cli.build_parser()
    args = parser.parse_args([
        "render-score",
        json.dumps({"version": "0.1.0", "background": "white", "instructions": []}),
        "--render-seed", "4242",
        *extra_argv,
    ])
    assert cli.command_render_score(args) == 0
    return json.loads(capsys.readouterr().out)


def test_from_work_sends_the_work_reference(monkeypatch, capsys):
    """The server cannot read a work's recorded colors without being told which work.

    Nothing in the SVG says which colors decided it, so a flag that stopped at
    argparse would look exactly like one that worked.
    """
    client = _render_score_client(render_headers={"X-Inku-Color-Source": "snapshot"})
    _run_render_score_from_work(monkeypatch, capsys, client, "--from-work", "history-77")

    assert client.sent[-1]["work_id"] == "history-77"


def test_from_work_leaves_the_catalog_to_the_work(monkeypatch, capsys):
    """It must not also name a catalog.

    `_resolved_color_catalog` refuses any id outside today's list, so resolving
    one here would refuse exactly the works this flag exists for: the ones whose
    catalog has since been renamed or retired.
    """
    client = _render_score_client(render_headers={"X-Inku-Color-Source": "snapshot"})
    _run_render_score_from_work(monkeypatch, capsys, client, "--from-work", "history-77")

    assert client.sent[-1]["catalog_id"] is None


def test_from_work_records_the_catalog_the_server_drew_with(monkeypatch, capsys):
    """The id in the output is the one that drew, not the one that was asked for.

    With --from-work the CLI asked for nothing, and the render hash below names
    this id: reading it off the response is the only way the hash can describe
    the picture that came back.
    """
    client = _render_score_client(
        render_headers={
            "X-Inku-Color-Source": "snapshot",
            "X-Inku-Color-Catalog-Id": "japanese",
        }
    )
    result = _run_render_score_from_work(monkeypatch, capsys, client, "--from-work", "history-77")

    assert result["render_color_catalog_id"] == "japanese"
    assert result["render_color_source"] == "snapshot"


def test_render_score_without_from_work_still_names_its_own_catalog(monkeypatch, capsys):
    """The control. Without the flag nothing about the old path moves.

    A change that simply stopped resolving catalogs would pass every test above
    and fail this one.
    """
    client = _render_score_client()
    result = _run_render_score(monkeypatch, capsys, client)

    assert client.sent[-1]["work_id"] is None
    assert client.sent[-1]["catalog_id"] == CATALOG_DATA["default_catalog_id"]
    assert result["render_color_source"] == "catalog"


def test_from_work_refuses_to_also_be_given_a_catalog(monkeypatch, capsys):
    """Two answers to one question: say so rather than silently pick one."""
    client = _render_score_client()
    monkeypatch.setattr(cli, "ApiClient", client)
    parser = cli.build_parser()
    args = parser.parse_args([
        "render-score",
        json.dumps({"version": "0.1.0", "background": "white", "instructions": []}),
        "--from-work", "history-77",
        "--color-catalog", "ink_season",
    ])

    with pytest.raises(cli.CliError):
        cli.command_render_score(args)


def test_from_work_does_not_resolve_colors_in_the_cli(monkeypatch, capsys):
    """`_render_color_map` is the CLI resolving colors for itself.

    The snapshot path must not pass through it: a client that builds its own
    color map is a client that can disagree with the work.
    """
    calls = []
    original = cli._render_color_map
    monkeypatch.setattr(
        cli, "_render_color_map", lambda catalog: calls.append(catalog) or original(catalog)
    )
    client = _render_score_client(render_headers={"X-Inku-Color-Source": "snapshot"})
    _run_render_score_from_work(monkeypatch, capsys, client, "--from-work", "history-77")

    assert calls == []


# --- Single-user mode: the server decides who a request is, not the client ---


class _CapturedRequest:
    """Stands in for urlopen so the header the client would have sent is visible."""

    def __init__(self, status: int, body: bytes = b"{}"):
        self.status = status
        self.body = body
        self.seen: list[dict[str, str]] = []

    def __call__(self, req, timeout=None):
        self.seen.append(dict(req.headers))
        if self.status >= 400:
            raise urllib.error.HTTPError(req.full_url, self.status, "denied", {}, io.BytesIO(b'{"detail":"x"}'))

        class _Response:
            def __init__(self, body):
                self._body = body

            def read(self):
                return self._body

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

        return _Response(self.body)


def test_a_request_without_a_stored_session_still_reaches_the_server(monkeypatch):
    """A server in single-user mode answers it; refusing here would decide that
    on the client, which does not know the mode."""
    captured = _CapturedRequest(200, b'{"username":"admin"}')
    monkeypatch.setattr(cli.urllib.request, "urlopen", captured)
    client = cli.ApiClient("http://127.0.0.1:8199", None)
    payload, _ = client.request("GET", "/api/auth/me")
    assert payload == {"username": "admin"}
    assert len(captured.seen) == 1
    assert not any(key.lower() == "authorization" for key in captured.seen[0])


def test_a_server_that_does_want_credentials_still_gets_the_old_advice(monkeypatch):
    """The control: the message is now given after asking, not instead of asking."""
    captured = _CapturedRequest(401)
    monkeypatch.setattr(cli.urllib.request, "urlopen", captured)
    client = cli.ApiClient("http://127.0.0.1:8199", None)
    with pytest.raises(cli.CliError, match="not logged in"):
        client.request("GET", "/api/auth/me")
    assert len(captured.seen) == 1


# --- sharing one work, and a lineage that crosses owners ---------------------


class _AclClient:
    """Records every call and answers the ACL routes from an in-memory list."""

    def __init__(self, *args, **kwargs):
        pass

    calls: list = []
    stored: list = []

    def request(self, method, path, *, data=None, **kwargs):
        type(self).calls.append((method, path, data))
        if path.endswith("/acl") and method == "GET":
            return list(type(self).stored), None
        if path.endswith("/acl") and method == "PUT":
            type(self).stored = [
                {**entry, "id": f"row-{i}", "history_id": "work-1", "at": 0}
                for i, entry in enumerate(data["entries"])
            ]
            return list(type(self).stored), None
        return {}, None


def _acl_client(monkeypatch, stored=()):
    _AclClient.calls = []
    _AclClient.stored = [dict(entry) for entry in stored]
    monkeypatch.setattr(cli, "ApiClient", _AclClient)
    monkeypatch.setattr(cli, "_print_json", lambda data: None)
    return _AclClient


def test_history_share_sends_the_subject_it_was_given(monkeypatch):
    """P-14's target: a client that drops --to-user shares with nobody and says
    nothing, because PUT with an empty list is a valid request."""
    client = _acl_client(monkeypatch)
    args = cli.build_parser().parse_args(
        ["history", "share", "work-1", "--to-user", "bob-id", "--permission", "write"]
    )
    assert cli.command_history_share(args) == 0
    put = [data for method, _path, data in client.calls if method == "PUT"]
    assert put == [{"entries": [
        {"subject_type": "user", "subject_id": "bob-id", "permission": "write"}
    ]}]


def test_history_share_keeps_the_guests_already_on_the_list(monkeypatch):
    """PUT replaces the whole list, so sharing has to read it first. Sending
    only the new entry would silently revoke everyone else."""
    client = _acl_client(monkeypatch, stored=[
        {"subject_type": "user", "subject_id": "carol-id", "permission": "read"}
    ])
    args = cli.build_parser().parse_args(
        ["history", "share", "work-1", "--to-group", "circle-b", "--permission", "read"]
    )
    assert cli.command_history_share(args) == 0
    put = [data for method, _path, data in client.calls if method == "PUT"][0]
    subjects = {(e["subject_type"], e["subject_id"]) for e in put["entries"]}
    assert subjects == {("user", "carol-id"), ("org_group", "circle-b")}


def test_history_unshare_removes_only_the_named_subject(monkeypatch):
    client = _acl_client(monkeypatch, stored=[
        {"subject_type": "user", "subject_id": "bob-id", "permission": "read"},
        {"subject_type": "user", "subject_id": "carol-id", "permission": "read"},
    ])
    args = cli.build_parser().parse_args(["history", "unshare", "work-1", "--to-user", "bob-id"])
    assert cli.command_history_share(args) == 0
    put = [data for method, _path, data in client.calls if method == "PUT"][0]
    assert [e["subject_id"] for e in put["entries"]] == ["carol-id"]


def test_history_still_lists_without_a_subcommand(monkeypatch):
    """`history` was a flat listing command before it had subcommands, and
    `inku-cli history --limit 20` has to keep meaning what it did."""
    args = cli.build_parser().parse_args(["history", "--limit", "20"])
    assert args.history_action is None
    assert args.func is cli.command_history


def test_refine_save_translates_the_kind_the_flag_offers(monkeypatch, tmp_path):
    """The four --kind choices are not the four names the server accepts.

    `save` sent the flag value straight through, so every invocation came back
    422 "invalid lineage derivation kind" -- no value worked, and the subcommand
    had never once succeeded. `perform` had the translation all along.
    """
    calls = []

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def request(self, method, path, *, data=None, **kwargs):
            calls.append((method, path, data))
            return {"id": "child-1"}, None

    score = tmp_path / "score.json"
    score.write_text('{"canvas":"square","instructions":[]}', encoding="utf-8")
    monkeypatch.setattr(cli, "ApiClient", FakeClient)
    monkeypatch.setattr(cli, "_print_json", lambda data: None)

    for flag_kind, server_kind in cli._DERIVATION_KIND_BY_REFINE_KIND.items():
        calls.clear()
        args = cli.build_parser().parse_args([
            "refine", "save", "node-1", "--kind", flag_kind,
            "--file", str(score), "--input-text", "t",
        ])
        assert cli.command_refine(args) == 0
        posted = [data for method, path, data in calls if path == "/api/history"][0]
        assert posted["derivation_kind"] == server_kind
        assert posted["lineage_parent_node_id"] == "node-1"


def test_refine_perform_resolves_a_parent_the_listing_cannot_reach(monkeypatch):
    """A work shared BY someone else is not in the caller's own listing.

    Both lookups `perform` used -- the first page, then a text search -- go
    through /api/history, which answers with what the caller owns or is given,
    paged and matched on text. Neither is a way to name one id. Without the
    lineage fallback a lineage could never cross owners from the command line.
    """
    calls = []

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def request(self, method, path, *, data=None, query=None, **kwargs):
            calls.append((method, path))
            if path == "/api/history":
                return {"items": []}, None       # not mine, and not findable by text
            if path.endswith("/lineage"):
                return {
                    "focus_node_id": "their-node",
                    "nodes": [{
                        "id": "their-node",
                        "redacted": None,
                        "history": {
                            "id": "their-work", "lineage_node_id": "their-node",
                            "source_text": "a pine", "render_seed": 1,
                            "composition_seed": 2, "interpretation_seed": "s",
                            "render_color_catalog_id": "default",
                        },
                    }],
                }, None
            return {"svg": "<svg />", "render_hash_short": "ABCD"}, None

    monkeypatch.setattr(cli, "ApiClient", FakeClient)
    monkeypatch.setattr(cli, "_print_json", lambda data: None)
    args = cli.build_parser().parse_args(["refine", "perform", "their-work", "--kind", "touch"])
    assert cli.command_refine(args) == 0
    assert ("GET", "/api/history/their-work/lineage") in calls


def test_single_user_set_sends_the_account_it_was_given(monkeypatch):
    calls = []

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def request(self, method, path, *, data=None, **kwargs):
            calls.append((method, path, data))
            return {"enabled": True, "user_id": "successor", "eligible": []}, None

    monkeypatch.setattr(cli, "ApiClient", FakeClient)
    monkeypatch.setattr(cli, "_print_json", lambda data: None)

    show = cli.build_parser().parse_args(["single-user", "show"])
    assert cli.command_single_user(show) == 0
    move = cli.build_parser().parse_args(["single-user", "set", "successor"])
    assert cli.command_single_user(move) == 0

    assert calls == [
        ("GET", "/api/settings/single-user", None),
        ("PUT", "/api/settings/single-user", {"user_id": "successor"}),
    ]


def test_lineage_show_labels_a_withheld_parent_apart_from_a_deleted_one(monkeypatch, capsys):
    """T-27. The two states render identically -- an empty card -- so the label
    is the only thing telling the reader whether asking would help."""
    graph = {
        "focus_node_id": "mine",
        "nodes": [
            {"id": "withheld", "state": "active", "at": 1, "redacted": "not_permitted"},
            {"id": "gone", "state": "tombstone", "at": 2, "redacted": "deleted", "child_count": 1},
            {"id": "mine", "state": "active", "at": 3, "redacted": None,
             "history": {"source_text": "my own work"}},
        ],
        "edges": [
            {"parent_node_id": "withheld", "child_node_id": "mine",
             "derivation_kind": "touch_change", "at": 1},
            {"parent_node_id": "gone", "child_node_id": "withheld",
             "derivation_kind": "touch_change", "at": 2},
        ],
    }

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def request(self, method, path, **kwargs):
            return graph, None

    monkeypatch.setattr(cli, "ApiClient", FakeClient)
    args = cli.build_parser().parse_args(["lineage", "show", "mine"])
    assert cli.command_lineage(args) == 0
    printed = capsys.readouterr().out

    assert "[Private]" in printed, "a withheld parent is not labelled"
    assert "[Deleted]" in printed, "a deleted parent is not labelled"
    # And they are on different lines: one label for both would be the defect.
    private_line = next(line for line in printed.splitlines() if "[Private]" in line)
    deleted_line = next(line for line in printed.splitlines() if "[Deleted]" in line)
    assert "withheld"[:8] in private_line
    assert "gone"[:8] in deleted_line
    assert "my own work" in printed


def test_history_peers_asks_for_the_callers_own_organisation(monkeypatch):
    """Sharing takes an id, and the member directory is a manager's. This is the
    one route that answers a plain member, and it stops at their organisation."""
    calls = []

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def request(self, method, path, **kwargs):
            calls.append((method, path))
            return [{"id": "peer-1", "username": "carol"}], None

    monkeypatch.setattr(cli, "ApiClient", FakeClient)
    monkeypatch.setattr(cli, "_print_json", lambda data: None)
    args = cli.build_parser().parse_args(["history", "peers"])
    assert cli.command_history_share(args) == 0
    assert calls == [("GET", "/api/auth/me/group-peers")]
    # Not the directory: /api/users answers 403 for a plain member anyway, and
    # asking it here would make the subcommand useless to the people who need it.
    assert all(path != "/api/users" for _method, path in calls)


# ── T-15 ────────────────────────────────────────────────────────────────────
# The `history` command is the one listing sender that names include_svg, and it
# names it in both directions on purpose. A sender that only writes the flag when
# it is false leaves the true case decided by the server alone, and nothing on
# this side would notice the day that default moved.
def test_the_history_listing_asks_for_the_drawings_unless_told_otherwise(monkeypatch):
    sent = []

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def request(self, method, path, **kwargs):
            sent.append((method, path, kwargs.get("query") or {}))
            return {"items": []}, None

    monkeypatch.setattr(cli, "ApiClient", FakeClient)
    monkeypatch.setattr(cli, "_print_json", lambda data: None)
    parser = cli.build_parser()

    assert cli.command_history(parser.parse_args(["history"])) == 0
    assert cli.command_history(parser.parse_args(["history", "--no-svg"])) == 0

    assert [(m, p) for m, p, _q in sent] == [("GET", "/api/history")] * 2
    default_query, no_svg_query = sent[0][2], sent[1][2]
    # Written in both cases, not only when it is false.
    assert "include_svg" in default_query and "include_svg" in no_svg_query
    assert default_query["include_svg"] is True, (
        "without the flag the CLI must ask for the drawings; its export path "
        "writes whatever arrives straight to a file and rasterizes it"
    )
    assert no_svg_query["include_svg"] is False


# ── T-201 ───────────────────────────────────────────────────────────────────
# I-191: a work says which organisation group may read it, and the listing can
# be asked for that bundle. Measured by running the command and reading the
# query it built -- the argument's NAME appearing in build_parser() says only
# that the flag parses, and the sender that has to carry it is a different line
# in a different function.
def test_the_history_listing_carries_the_share_filter_in_both_directions(monkeypatch):
    sent = []

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def request(self, method, path, **kwargs):
            sent.append((method, path, kwargs.get("query") or {}))
            return {"items": []}, None

    monkeypatch.setattr(cli, "ApiClient", FakeClient)
    monkeypatch.setattr(cli, "_print_json", lambda data: None)
    parser = cli.build_parser()

    assert cli.command_history(parser.parse_args(["history"])) == 0
    assert cli.command_history(parser.parse_args(["history", "--for-share"])) == 0

    assert [(m, p) for m, p, _q in sent] == [("GET", "/api/history")] * 2
    plain, filtered = sent[0][2], sent[1][2]
    # Written in both cases, like include_svg beside it: a sender that only
    # writes the key when it is true leaves the false case to the server's
    # default, and nothing on this side would notice the day that moved.
    assert "for_share" in plain and "for_share" in filtered
    assert plain["for_share"] is False
    assert filtered["for_share"] is True
    # And it narrows beside the other two rather than replacing them.
    assert filtered["starred"] is False and filtered["for_revision"] is False


def test_the_history_export_sender_carries_the_share_filter(monkeypatch):
    """The other sender of the same listing: the one that resolves hashes.

    Two senders, counted rather than assumed. `history` and `history-export`
    build the query in different functions, and a flag added to one of them
    leaves the other asking a question its own argument says it is not asking.
    """
    sent = []

    class FakeClient:
        base_url = "http://127.0.0.1:8100"

        def __init__(self, *args, **kwargs):
            pass

        def request(self, method, path, **kwargs):
            sent.append((method, path, kwargs.get("query") or {}))
            return {"items": [], "total": 0}, None

    assert cli._fetch_all_history(FakeClient(), for_share=True) == []
    assert cli._fetch_all_history(FakeClient()) == []
    assert [(m, p) for m, p, _q in sent] == [("GET", "/api/history")] * 2
    assert sent[0][2]["for_share"] is True
    assert sent[1][2]["for_share"] is False


def _subparser(name: str) -> argparse.ArgumentParser:
    """The parser argparse built for one subcommand, found by walking the root."""
    for action in cli.build_parser()._actions:
        if isinstance(action, argparse._SubParsersAction) and name in action.choices:
            return action.choices[name]
    raise AssertionError(f"`{name}` is not a subcommand of inku-cli")


def test_measure_raster_asks_nothing_of_a_server():
    """T-118. Counting pixels needs no API, so the server flags are not there.

    A subcommand that accepts `--base-url` invites being pointed at a running
    inku, and the next question after that is which build's renderer produced
    the pictures -- which is a question about the PNGs on disk, not the server.
    """
    measure_raster = _subparser("measure-raster")
    declared = {option for action in measure_raster._actions for option in action.option_strings}
    assert "--base-url" not in declared and "--timeout-seconds" not in declared, declared
    with pytest.raises(SystemExit):
        cli.build_parser().parse_args(["measure-raster", "--in", "x", "--base-url", "http://localhost:8100"])


def test_measure_raster_declares_no_way_to_change_the_width():
    """T-119. Shrinking is unreachable, not a flag that defaults to off.

    The width belongs to the burning step (`rasterize --width`); the counting
    step measures what it was handed. A flag here -- even one nobody passes --
    is the halving line coming back with a name.
    """
    measure_raster = _subparser("measure-raster")
    declared = {option for action in measure_raster._actions for option in action.option_strings}
    assert declared == {"-h", "--help", "--in", "--out"}, declared
    forbidden = re.compile(r"width|scale|half|reduce|shrink|resize|thumb|dpi|px", re.I)
    assert not [option for option in declared if forbidden.search(option)], declared


# I-154: what drew this, and under whose numbers ------------------------------


def test_render_score_reports_the_limits_and_where_they_came_from(monkeypatch, capsys):
    """T-105. Three keys, and the middle one is the one that cannot be inferred.

    `render_limits` names numbers; only the source says whether they came off
    the work's own row or off today's settings, and the artifact this command
    writes is the only record of which. A run that dropped it would still print
    a plausible set of limits.
    """
    result = _run_render_score(monkeypatch, capsys, _render_score_client())

    assert result["render_limits"] == {"represented_count_max": 120}
    assert result["render_limits_source"] == "settings"
    assert result["render_limit_notes"] == ["represented_count_max: 600 drawn as 120"]


def test_render_score_from_work_reports_the_work_as_the_limits_source(monkeypatch, capsys):
    """The reading that makes the key worth carrying: it moves with the request."""
    client = _render_score_client(render_headers={"X-Inku-Color-Source": "snapshot"})
    result = _run_render_score_from_work(monkeypatch, capsys, client, "--from-work", "history-77")

    assert result["render_limits_source"] == "work"


def test_limits_flag_reaches_the_request(monkeypatch, capsys):
    """`--limits key=value` is the whole of what a feature test can run through.

    Without the flag the request must carry no `limits` key at all: an empty
    dict reads as "override with nothing", and the server would then bound it
    against today's settings instead of letting the work's row decide.
    """
    client = _render_score_client()
    _run_render_score(
        monkeypatch, capsys, client, "--limits", "represented_count_max=60", "ddl_count_max=500"
    )
    assert client.sent[-1]["limits"] == {"represented_count_max": 60, "ddl_count_max": 500}

    client = _render_score_client()
    _run_render_score(monkeypatch, capsys, client)
    assert client.sent[-1]["limits"] is None


def test_limits_flag_refuses_what_is_not_a_pair():
    with pytest.raises(cli.CliError):
        cli._limits_argument(["represented_count_max"])
    with pytest.raises(cli.CliError):
        cli._limits_argument(["represented_count_max=lots"])


def test_a_non_display_export_names_the_work_it_is_exporting(monkeypatch):
    """T-106. The export draws under the limits the work was drawn under.

    The browser's export already does this -- it goes through
    GET /api/history/{id}/svg, which hands the row over -- and this path did
    not, so the same drawing left the CLI under today's ceiling. Nothing in the
    SVG says which numbers drew it, so a missing key looks like a working one.
    """

    class FakeClient:
        def __init__(self):
            self.calls = []

        def request_text(self, method, path, *, data=None, query=None, auth=True):
            self.calls.append((method, path, data, query, auth))
            return "<svg><title>editable</title></svg>"

    client = FakeClient()
    saved = {
        "score": {"instructions": []},
        "svg": "<svg><title>display</title></svg>",
        "history_id": "history-77",
    }
    cli._result_with_svg_profile(client, saved, svg_profile="editable", color_catalog="default")
    assert client.calls[0][2]["work_id"] == "history-77"

    # A fresh drawing has no row. Sending a null id would only be able to 404,
    # so the key has to be absent rather than present and empty.
    client = FakeClient()
    unsaved = {"score": {"instructions": []}, "svg": "<svg><title>display</title></svg>"}
    cli._result_with_svg_profile(client, unsaved, svg_profile="editable", color_catalog="default")
    assert "work_id" not in client.calls[0][2]
