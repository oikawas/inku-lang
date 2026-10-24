"""`paint --image` draws from an image through the same API calls as the web image tab.

Observed at the HTTP boundary: the image goes to POST /api/pipeline/images as
bytes, the run starts with kind=image and the source note as its text, the CLI
waits for the run, asks for the performance, and writes what came back.
"""

from __future__ import annotations

import json

import pytest

from inku_cli import cli

IMAGE = b"\x89PNG\r\n\x1a\n not really a png"
CATALOGS = {
    "default_catalog_id": "default",
    "catalogs": [{
        "id": "default",
        "name": "inku Default",
        "map": {"white": "#ffffff", "black": "#111111"},
        "palette": [],
    }],
}


class FakePipeline:
    """A server whose image run is busy once before the score and once before the drawing."""

    def __init__(self, *, saved: bool = True, failure: dict | None = None, failed_phase: bool = False,
                 retried: bool = False):
        self.calls: list[tuple[str, str, object]] = []
        self.saved = saved
        self.failure = failure
        self.failed_phase = failed_phase
        self.retried = retried
        self.polls = 0

    def view(self, **fields):
        view = {"variation_id": "v1", "execution_id": "e1", "phase": {"tag": "running"}, "busy": False, **fields}
        if self.retried or self.failed_phase:
            # The record of a provider request that failed; the run may have sent it again.
            view["provider_failure"] = {"failure": "transport_timeout", "stage": "image", "attempt": 1}
        return view

    def request(self, method, path, *, data=None, content=None, **kwargs):
        self.calls.append((method, path, content if content is not None else data))
        if (method, path) == ("GET", "/api/color-catalogs"):
            return CATALOGS, None
        if (method, path) == ("POST", "/api/pipeline/images"):
            return {
                "image_id": "img-1", "thumbnail": "data:", "original_width": 4000, "original_height": 3000,
                "width": 1600, "height": 1200, "nearest_format_id": "golden",
            }, None
        if (method, path) == ("POST", "/api/pipeline/variations"):
            return self.view(busy=True), None
        if (method, path) == ("GET", "/api/pipeline/variations/v1"):
            self.polls += 1
            if self.failure is not None:
                return self.view(phase={"tag": "failed", "reason": "image_ddl_failed"}, image_failure=self.failure), None
            if self.failed_phase:
                return self.view(phase={"tag": "failed", "reason": "provider_failed"}), None
            if self.polls == 1:
                return self.view(phase={"tag": "delivered"}, delivery={"score": {"instructions": []}}), None
            result = {
                "description": "", "ddl": "円を置く。", "svg": "<svg/>", "score": {"instructions": []},
                "image_provenance": "2026年 京都で撮影", "image_ddl": {"before_review": "円。"},
                "elapsed_total_ms": 900, "elapsed_image_ms": 700,
            }
            if self.saved:
                result["history_id"] = "h1"
            return self.view(phase={"tag": "performed"}, delivery={"score": {}}, result=result), None
        if (method, path) == ("POST", "/api/pipeline/executions/e1/commands"):
            return self.view(busy=True), None
        raise AssertionError(f"unexpected request {method} {path}")


@pytest.fixture
def image_file(tmp_path):
    path = tmp_path / "photo.png"
    path.write_bytes(IMAGE)
    return path


def _run(monkeypatch, server, argv, *, vision_model="chatgpt:gpt-6-luna"):
    monkeypatch.setattr(cli, "ApiClient", lambda *args, **kwargs: server)
    monkeypatch.setattr(cli, "load_config", lambda: cli.CliConfig(vision_model=vision_model))
    monkeypatch.setattr(cli, "PIPELINE_POLL_SECONDS", 0)
    return cli.main([*argv, "--no-progress"])


def _sent(server, method, path):
    return [body for m, p, body in server.calls if (m, p) == (method, path)]


def test_an_image_run_sends_the_image_tab_requests_and_writes_the_drawing(monkeypatch, capsys, tmp_path, image_file):
    server = FakePipeline()
    code = _run(monkeypatch, server, [
        "paint", "--image", str(image_file), "--provenance", "2026年 京都で撮影",
        "--save-history", "--out-dir", str(tmp_path / "out"), "--prefix", "p",
    ])

    assert code == 0
    assert _sent(server, "POST", "/api/pipeline/images") == [IMAGE]
    [start] = _sent(server, "POST", "/api/pipeline/variations")
    assert start["kind"] == "image"
    assert start["text"] == "2026年 京都で撮影"
    assert start["image_id"] == "img-1"
    assert start["canvas_format_id"] == "image"
    options = start["options"]
    assert options["canvas_aspect"] == "golden"
    assert options["stage1_model"] == options["stage2_model"] == "chatgpt:gpt-6-luna"
    assert (options["sketch"], options["wild"], options["instruction_lang"], options["canvas_fit"]) == ("off", False, "ja", "contain")
    assert options["save_history"] is True
    assert "description" not in options
    assert _sent(server, "POST", "/api/pipeline/executions/e1/commands") == [{"tag": "perform"}]

    summary = json.loads(capsys.readouterr().out)
    assert summary["input_mode"] == "image"
    assert summary["provenance"] == "2026年 京都で撮影"
    assert summary["history_id"] == "h1"
    assert summary["image_size"] == {"original": [4000, 3000], "sent": [1600, 1200]}
    written = json.loads((tmp_path / "out" / "p.json").read_text(encoding="utf-8"))
    assert written["image_provenance"] == "2026年 京都で撮影"
    assert written["image_ddl"] == {"before_review": "円。"}
    assert (tmp_path / "out" / "p.svg").read_text(encoding="utf-8") == "<svg/>"


def test_without_save_history_the_image_run_asks_the_server_not_to_save(monkeypatch, capsys, image_file):
    # The pipeline saves by default, so leaving the key out would save the work.
    server = FakePipeline(saved=False)
    assert _run(monkeypatch, server, ["paint", "--image", str(image_file)]) == 0

    [start] = _sent(server, "POST", "/api/pipeline/variations")
    assert start["options"]["save_history"] is False
    assert start["text"] == ""
    assert json.loads(capsys.readouterr().out)["history_id"] is None


def test_a_named_paper_is_sent_instead_of_the_image_ratio(monkeypatch, capsys, image_file):
    server = FakePipeline()
    assert _run(monkeypatch, server, ["paint", "--image", str(image_file), "--canvas-aspect", "wide"]) == 0

    [start] = _sent(server, "POST", "/api/pipeline/variations")
    assert (start["canvas_format_id"], start["options"]["canvas_aspect"]) == ("wide", "wide")
    capsys.readouterr()


def test_the_provenance_is_read_from_a_file(monkeypatch, capsys, tmp_path, image_file):
    note = tmp_path / "note.txt"
    note.write_text("祖母の写真帳から\n昭和40年ごろ\n", encoding="utf-8")
    server = FakePipeline()
    assert _run(monkeypatch, server, ["paint", "--image", str(image_file), "--provenance-file", str(note)]) == 0

    [start] = _sent(server, "POST", "/api/pipeline/variations")
    assert start["text"] == "祖母の写真帳から\n昭和40年ごろ"
    capsys.readouterr()


def test_a_failed_image_run_is_an_error_and_writes_nothing(monkeypatch, capsys, tmp_path, image_file):
    server = FakePipeline(failure={"code": "image_missing", "message": "The worker no longer has the image."})
    code = _run(monkeypatch, server, ["paint", "--image", str(image_file), "--out-dir", str(tmp_path / "out")])

    assert code == 2
    assert "image_missing" in capsys.readouterr().err
    assert not (tmp_path / "out").exists()
    assert _sent(server, "POST", "/api/pipeline/executions/e1/commands") == []


def test_a_provider_failure_the_run_got_past_is_not_a_failure(monkeypatch, capsys, image_file):
    # Found on 5173 (2026-10-24): the first CLI reported such a run as "failed: None".
    server = FakePipeline(retried=True)
    assert _run(monkeypatch, server, ["paint", "--image", str(image_file)]) == 0
    assert json.loads(capsys.readouterr().out)["history_id"] == "h1"


def test_a_failed_phase_names_the_provider_failure(monkeypatch, capsys, image_file):
    server = FakePipeline(failed_phase=True)
    assert _run(monkeypatch, server, ["paint", "--image", str(image_file)]) == 2
    assert "image run v1 failed: provider_failed (image: transport_timeout)" in capsys.readouterr().err
    assert _sent(server, "POST", "/api/pipeline/executions/e1/commands") == []


@pytest.mark.parametrize("extra", [
    ["描いて"],
    ["--input-mode", "ddl"],
    ["--sketch"],
    ["--wild"],
    ["--stage1-model", "chatgpt:gpt-6-luna"],
], ids=["text", "ddl", "sketch", "wild", "stage1-model"])
def test_flags_an_image_run_cannot_use_are_refused_before_sending(monkeypatch, capsys, image_file, extra):
    server = FakePipeline()
    assert _run(monkeypatch, server, ["paint", "--image", str(image_file), *extra]) == 2
    assert "--image cannot be combined" in capsys.readouterr().err
    assert server.calls == []


def test_an_image_run_needs_a_vision_model(monkeypatch, capsys, image_file):
    server = FakePipeline()
    assert _run(monkeypatch, server, ["paint", "--image", str(image_file)], vision_model=None) == 2
    assert "Vision model" in capsys.readouterr().err
    assert server.calls == []


def test_the_vision_model_flag_overrides_the_setting(monkeypatch, capsys, image_file):
    server = FakePipeline()
    assert _run(monkeypatch, server, ["paint", "--image", str(image_file), "--vision-model", "gemini:gemma-4-31b-it"]) == 0
    [start] = _sent(server, "POST", "/api/pipeline/variations")
    assert start["options"]["stage1_model"] == "gemini:gemma-4-31b-it"
    capsys.readouterr()


def test_image_flags_without_an_image_are_refused(monkeypatch, capsys):
    server = FakePipeline()
    assert _run(monkeypatch, server, ["paint", "描いて", "--provenance", "どこか"]) == 2
    assert "are for --image" in capsys.readouterr().err
    assert server.calls == []
