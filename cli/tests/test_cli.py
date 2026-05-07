from __future__ import annotations

import json
import sys
from pathlib import Path

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

    assert payload["text"] == "一滴の墨"
    assert payload["stage1_model"] == "gemma"
    assert payload["save_history"] is True
    assert payload["include_thinking"] is False
    assert payload["catalog_id"] == "default"
    assert "color_map" not in payload
    assert "stage2_model" not in payload
    assert "history_input" not in payload


def test_paint_payload_uses_resolved_models():
    parser = cli.build_parser()
    args = parser.parse_args(["paint", "一滴の墨"])

    payload = cli._paint_payload(args, "一滴の墨", stage1_model="s1", stage2_model="s2")

    assert payload["stage1_model"] == "s1"
    assert payload["stage2_model"] == "s2"


def test_compose_payload_for_ddl_input_mode():
    parser = cli.build_parser()
    args = parser.parse_args(["paint", "白い背景に黒い線を一本引く。", "--input-mode", "ddl", "--original-text", "線"])

    payload = cli._compose_payload(args, "白い背景に黒い線を一本引く。", stage2_model="s2", color_catalog="default")

    assert payload == {
        "ddl": "白い背景に黒い線を一本引く。",
        "model": "s2",
        "original_text": "線",
        "lang": "ja",
        "catalog_id": "default",
        "auto_repair": True,
    }


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
    assert payload["save_artifacts"] is True
    assert payload["count_generation"] is True


def test_compose_response_as_paint_result_uses_effective_ddl():
    result = cli._compose_response_as_paint_result(
        {
            "ddl": "展開後DDL。",
            "score": {"instructions": []},
            "svg": "<svg></svg>",
            "elapsed_ms": 500,
            "stage2_model": "resolved",
        },
        ddl="入力DDL。",
        input_text="元入力",
        stage2_model="requested",
    )

    assert result["text"] == "元入力"
    assert result["ddl"] == "展開後DDL。"
    assert result["stage1_model"] is None
    assert result["stage2_model"] == "resolved"
    assert result["elapsed_stage1_ms"] == 0
    assert result["elapsed_total_ms"] == 500


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
        "--color-catalog",
        "ink_season",
    ])

    assert args.stage1_provider == "nvidia"
    assert args.stage1_model == "google/gemma-4-31b-it"
    assert args.stage2_provider == "local"
    assert args.stage2_model == "qwen-api"
    assert args.color_catalog == "ink_season"


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
        "text": "緑の葉が揺れる",
        "ddl": "緑の小さな楕円を散らす。",
        "score": {"instructions": [{"primitive": "ellipse", "color": "gray"}]},
    }

    trace = cli._color_trace(result, catalog_id="default")

    assert trace["green_requested"] is True
    assert trace["green_in_score"] is False
    assert "green_requested_but_missing_in_score" in trace["warnings"]


def test_color_trace_does_not_treat_words_as_green_leaf_marker():
    result = {
        "text": "言えなかった言葉を白い余白に置く",
        "ddl": "言えなかった言葉のために白い余白を残す。",
        "score": {"instructions": [{"primitive": "ellipse", "color": "white"}]},
    }

    trace = cli._color_trace(result, catalog_id="default")

    assert trace["green_requested"] is False
    assert "green" not in trace["requested_colors"]
    assert "green_requested_but_missing_in_score" not in trace["warnings"]


def test_color_trace_detects_specific_leaf_terms_as_green():
    assert cli._marker_colors("落ち葉と若葉、木の葉、葉っぱ、葉脈") == ["green"]


def test_color_trace_suppresses_negated_green_warning():
    result = {
        "text": "言えなかった言葉を白い余白に置き、緑には寄せず黒い線だけを残す。",
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
        "text": "一滴の墨",
        "ddl": "白い背景に黒い点を置く。",
        "score": {"canvas": {"width": 100, "height": 100}, "shapes": []},
        "svg": "<svg viewBox=\"0 0 10 10\"></svg>",
    }

    paths = cli._write_paint_outputs(result, out_dir=tmp_path, prefix="sample", png=False)

    assert Path(paths["svg"]).read_text(encoding="utf-8") == result["svg"]
    saved_json = json.loads(Path(paths["json"]).read_text(encoding="utf-8"))
    assert saved_json["ddl"] == result["ddl"]


def test_svg_profile_arg_is_accepted_for_paint_and_batch():
    parser = cli.build_parser()

    paint_args = parser.parse_args(["paint", "線", "--svg-profile", "editable", "--input-mode", "ddl"])
    batch_args = parser.parse_args(["batch", "--file", "prompts.txt", "--svg-profile", "compat", "--input-mode", "ddl"])

    assert paint_args.svg_profile == "editable"
    assert paint_args.input_mode == "ddl"
    assert batch_args.svg_profile == "compat"
    assert batch_args.input_mode == "ddl"


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
    class FakeCairoSvg:
        @staticmethod
        def svg2png(*, bytestring, write_to):
            Path(write_to).write_bytes(b"png")

    monkeypatch.setitem(sys.modules, "cairosvg", FakeCairoSvg)
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
