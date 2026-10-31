"""A v2 saved work moves once without breaking its saved authority link."""

import hashlib
import json

import pytest
from sqlalchemy import create_engine

from inku_server.persistence.saijiki_v3_migration import (
    MigrationAlreadyWritten, _migrate_once_database, migrate_once, migrate_unit_v3,
)
from inku_server.persistence.saijiki_v3_plugins import plan_packages
from inku_server.persistence.variation_authority import VariationAuthorityStore
from tests.test_saijiki_v2_migrate_once import _saved_database


def test_v2_work_and_authority_move_together_once(tmp_path):
    path = tmp_path / "saved.db"
    _saved_database(path)
    source = "黒い太筆の線を引く。"
    digest = hashlib.sha256(source.encode()).hexdigest()
    engine = create_engine(f"sqlite:///{path}")
    with engine.begin() as connection:
        context = json.loads(connection.exec_driver_sql("SELECT fork_context_bytes FROM pipeline_history_links").scalar_one())
        context["ddl_digest"] = digest
        encoded = json.dumps(context, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        document = json.dumps({"source": source, "language": "ja", "macro_locks": [],
                               "saijiki": "inku.saijiki.v2"}, ensure_ascii=False)
        connection.exec_driver_sql("UPDATE history SET ddl=? WHERE id='h'", (source,))
        connection.exec_driver_sql("UPDATE variation_authority SET source=?,document_json=?,ddl_digest=?",
                                   (source, document, digest))
        connection.exec_driver_sql("UPDATE pipeline_history_links SET ddl_digest=?,fork_context_bytes=?,fork_context_digest=?",
                                   (digest, encoded, hashlib.sha256(encoded).hexdigest()))
    engine.dispose()
    journal = tmp_path / "journal.jsonl"
    result = _migrate_once_database(path, migrate_unit_v3, journal=journal)
    assert result["refused_records"] == []
    assert result["executions"]["discarded"] == 1
    assert journal.stat().st_mode & 0o777 == 0o600
    engine = create_engine(f"sqlite:///{path}")
    linked = VariationAuthorityStore(engine).read_linked_history("u", "h")
    assert linked is not None and linked.history.source == "黒い太いガッシュの線を引く。"
    with engine.connect() as connection:
        document = json.loads(connection.exec_driver_sql("SELECT document_json FROM variation_authority").scalar_one())
    assert document["saijiki"] == "inku.saijiki.v3"
    engine.dispose()
    with pytest.raises(MigrationAlreadyWritten):
        _migrate_once_database(path, migrate_unit_v3)


def test_production_entry_refuses_without_package_coordination(tmp_path):
    with pytest.raises(RuntimeError, match="package_coordination_not_implemented"):
        migrate_once(tmp_path / "any.db", migrate_unit_v3)


def test_package_plan_keeps_original_note_and_preview_and_moves_example(tmp_path):
    from pathlib import Path

    source = Path(__file__).resolve().parents[2] / "core/crates/inku-ddl/assets/nature-leaves-v2/package.json"
    package = json.loads(source.read_text())
    package["words"] = package["words"][:1]
    word = package["words"][0]
    word["example_ja"] = "黒い太筆の線を引く。"
    word["note_ja"] = "太筆という旧語を含む散文"
    directory = tmp_path / "plugins" / "Nature.leaves-copy"
    directory.mkdir(parents=True)
    path = directory / "package.json"
    original = json.dumps(package, ensure_ascii=False).encode()
    path.write_bytes(original)
    report, proposed = plan_packages(directory.parent)
    assert path.read_bytes() == original
    assert report["changed"] == 1 and not report["refused_records"]
    assert report["notes_with_old_tools"] == [{"package": directory.name, "word": 0, "language": "ja"}]
    moved = json.loads(proposed[path])["words"][0]
    assert moved["example_ja"] == "黒い太いガッシュの線を引く。"
    assert moved["note_ja"] == word["note_ja"] and moved["preview"] == word["preview"]
