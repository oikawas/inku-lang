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
        stage1_model="stage1",
        stage2_model="stage2",
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
    assert "stage2_model" not in payload
    assert "history_input" not in payload


def test_paint_payload_uses_resolved_models():
    parser = cli.build_parser()
    args = parser.parse_args(["paint", "一滴の墨"])

    payload = cli._paint_payload(args, "一滴の墨", stage1_model="s1", stage2_model="s2")

    assert payload["stage1_model"] == "s1"
    assert payload["stage2_model"] == "s2"


def test_model_summary_marks_server_default():
    summary = cli._model_summary(None, "gemma")

    assert summary["stage1_model"] is None
    assert summary["stage1_model_display"] == "server default"
    assert summary["stage2_model"] == "gemma"
    assert summary["stage2_model_display"] == "gemma"


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
