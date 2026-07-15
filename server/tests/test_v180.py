from __future__ import annotations

import ast
from pathlib import Path

from inku_server import db
from inku_server.api import _render_seed_from_text
from inku_server.coerce import coerce_score
from inku_server.schema import Score
from inku_server.feature_analysis import composition_distance, composition_vector, motif_signatures


def _score(*instructions: dict) -> dict:
    return {"instructions": list(instructions)}


def test_composition_vector_is_deterministic_and_distance_is_symmetric():
    first = _score({"primitive": "circle", "center": [0.5, 0.5], "radius": 0.2, "color": "red"})
    second = _score({"primitive": "line", "from": [0.1, 0.8], "to": [0.9, 0.2], "color": "gray"})

    assert composition_vector(first) == composition_vector(first)
    assert composition_distance(first, first) == 0
    assert composition_distance(first, second) == composition_distance(second, first)
    assert composition_distance(first, second) > 0


def test_motif_signature_is_mechanical_and_stable():
    score = _score({
        "primitive": "circle", "center": [0.2, 0.2], "radius": 0.2, "color": "red",
        "arrangement": {"count": 12, "layout": "scatter", "path": "diagonal"},
    })
    assert motif_signatures(score) == ("bundle_circle:red:diagonal",)


def test_seed_text_is_explicit_deterministic_and_empty_matches_none():
    first, text = _render_seed_from_text(" 今日の風 ", 123)
    second, _ = _render_seed_from_text("今日の風", None)
    assert first == second
    assert text == "今日の風"
    assert _render_seed_from_text("", 123) == (123, None)
    assert _render_seed_from_text(None, 123) == (123, None)


def test_unread_word_ledger_is_user_scoped():
    suffix = "v180-ledger"
    group = db.add_user_group(suffix)
    user = db.add_user(f"{suffix}-user", f"{suffix}@example.com", "password-123", "user", group["id"])
    try:
        db.record_unread_words(user["id"], ["未読語", "未読語"], "文脈", at=100)
        db.record_unread_words(user["id"], ["未読語"], "文脈", at=200)
        mine = db.list_unread_words(user["id"])
        assert mine[0]["word"] == "未読語"
        assert mine[0]["frequency"] == 2
        assert "user_id" not in mine[0]
        assert any(item.get("word") == "未読語" and item.get("user_count") == 1 for item in db.list_unread_words(None))
    finally:
        db.delete_user(user["id"])
        db.delete_user_group(group["id"])


def test_generation_modules_do_not_import_feature_analysis():
    package = Path(__file__).resolve().parents[1] / "src" / "inku_server"
    for name in ("renderer.py", "composer.py", "ddl_expander.py", "coerce.py"):
        tree = ast.parse((package / name).read_text(encoding="utf-8"))
        imported = {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        }
        imported.update(
            node.module or ""
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
        )
        assert not any("feature_analysis" in item or "inku_analysis" in item for item in imported), name

def test_coerce_branch_report_is_observational():
    score = Score.model_validate({
        "instructions": [
            {"primitive": "line", "from": [0.1, 0.5], "to": [0.9, 0.5], "color": "white"}
        ]
    })
    report: dict[str, int] = {}
    observed = coerce_score(score, ddl="白い線", branch_report=report)
    baseline = coerce_score(score, ddl="白い線")
    assert observed == baseline
    assert isinstance(report, dict)
    assert "coerce_and_repair_instruction" in report
    assert "with_unintentional_filled_shape_tempering" in report
    assert "with_background_dominance_governor" in report
    assert all(isinstance(value, int) and value >= 0 for value in report.values())
