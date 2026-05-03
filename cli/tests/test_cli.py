from __future__ import annotations

import json
from pathlib import Path

from inku_cli import cli


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
        color_catalog="impressionism",
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
    assert payload["color_map"]["green"] == "#2f6b3a"
    assert "catalog_id" not in payload
    assert "stage2_model" not in payload
    assert "history_input" not in payload


def test_paint_payload_uses_resolved_models():
    parser = cli.build_parser()
    args = parser.parse_args(["paint", "一滴の墨"])

    payload = cli._paint_payload(args, "一滴の墨", stage1_model="s1", stage2_model="s2")

    assert payload["stage1_model"] == "s1"
    assert payload["stage2_model"] == "s2"


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
        "japanese",
    ])

    assert args.stage1_provider == "nvidia"
    assert args.stage1_model == "google/gemma-4-31b-it"
    assert args.stage2_provider == "local"
    assert args.stage2_model == "qwen-api"
    assert args.color_catalog == "japanese"


def test_color_catalog_payload_sets_catalog_and_map():
    parser = cli.build_parser()
    args = parser.parse_args(["paint", "緑の葉", "--color-catalog", "mexican"])

    payload = cli._paint_payload(args, "緑の葉")

    assert payload["catalog_id"] == "mexican"
    assert payload["color_map"]["green"] == "#008f39"


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
