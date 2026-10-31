"""A v2 saved work moves once without breaking its saved authority link."""

import hashlib
import json

import pytest
from sqlalchemy import create_engine

from inku_server.persistence.saijiki_v3_migration import (
    MigrationAlreadyWritten, _migrate_once_database, migrate_unit_v3,
)
from inku_server.persistence.saijiki_v3_plugins import plan_packages
from inku_server.persistence import saijiki_v3_cutover
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


def test_cutover_rolls_back_database_and_package_on_package_write_failure(tmp_path, monkeypatch):
    from pathlib import Path

    database = tmp_path / "saved.db"
    _saved_database(database)
    source = Path(__file__).resolve().parents[2] / "core/crates/inku-ddl/assets/nature-leaves-v2/package.json"
    package = json.loads(source.read_text())
    package["words"] = package["words"][:1]
    package["words"][0]["example_ja"] = "黒い太筆の線を引く。"
    directory = tmp_path / "plugins" / "Nature.leaves-copy"
    directory.mkdir(parents=True)
    file = directory / "package.json"
    original = json.dumps(package, ensure_ascii=False).encode()
    file.write_bytes(original)
    real_atomic = saijiki_v3_cutover._atomic

    def fail_package(path, data, mode):
        if path.name == "package.json":
            raise OSError("injected write failure")
        return real_atomic(path, data, mode)

    monkeypatch.setattr(saijiki_v3_cutover, "_atomic", fail_package)
    with pytest.raises(OSError, match="injected"):
        saijiki_v3_cutover.cutover(database, directory.parent, tmp_path / "attempt", journal=tmp_path / "journal")
    assert file.read_bytes() == original
    engine = create_engine(f"sqlite:///{database}")
    with engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT COUNT(*) FROM app_settings WHERE key='saijiki_v3_saved_records'").scalar_one() == 0
        assert connection.exec_driver_sql("SELECT COUNT(*) FROM pipeline_candidate_executions").scalar_one() == 1
    engine.dispose()


def test_cutover_commits_database_and_packages_together(tmp_path):
    from pathlib import Path

    database = tmp_path / "saved.db"
    _saved_database(database)
    source = Path(__file__).resolve().parents[2] / "core/crates/inku-ddl/assets/nature-leaves-v2/package.json"
    package = json.loads(source.read_text())
    package["words"] = package["words"][:1]
    package["words"][0]["example_ja"] = "黒い太筆の線を引く。"
    directory = tmp_path / "plugins" / "Nature.leaves-copy"
    directory.mkdir(parents=True)
    file = directory / "package.json"
    file.write_text(json.dumps(package, ensure_ascii=False))
    recovery = tmp_path / "attempt"
    report = saijiki_v3_cutover.cutover(database, directory.parent, recovery, journal=tmp_path / "journal")
    assert report["packages"]["changed"] == 1
    assert json.loads(file.read_text())["words"][0]["example_ja"] == "黒い太いガッシュの線を引く。"
    assert saijiki_v3_cutover.recover(database, directory.parent, recovery) == "committed"
    with pytest.raises(FileExistsError):
        saijiki_v3_cutover.cutover(database, directory.parent, recovery, journal=tmp_path / "other-journal")


def test_interrupted_uncommitted_package_is_restored_from_private_backup(tmp_path):
    database = tmp_path / "saved.db"
    _saved_database(database)
    root = tmp_path / "plugins"
    directory = root / "Example.words"
    directory.mkdir(parents=True)
    package = directory / "package.json"
    old, new = b'{"before":true}', b'{"after":true}'
    package.write_bytes(new)
    recovery = tmp_path / "attempt"
    recovery.mkdir()
    (recovery / "package-0.json").write_bytes(old)
    (recovery / "manifest.json").write_text(json.dumps({
        "database": str(database), "packages": str(root), "files": [{
            "path": "Example.words/package.json", "backup": "package-0.json", "mode": 0o600,
            "before": hashlib.sha256(old).hexdigest(), "after": hashlib.sha256(new).hexdigest(),
        }],
    }))
    assert saijiki_v3_cutover.recover(database, root, recovery) == "rolled_back"
    assert package.read_bytes() == old


def test_missing_builtin_definition_is_recovered_only_if_lock_digest_matches(tmp_path):
    database = tmp_path / "saved.db"
    _saved_database(database)
    lock = {"qualified_name": "Nature.下草", "version": "1.0.0",
            "digest": "sha256:88046b24987a2600eeb8b985f36bc15222202a5758a0f4a7638e514dd6af2aea"}
    document = {"source": "黒い太筆の線を引く。", "language": "ja", "macro_locks": [lock],
                "saijiki": "inku.saijiki.v2"}
    engine = create_engine(f"sqlite:///{database}")
    with engine.begin() as connection:
        connection.exec_driver_sql("DELETE FROM pipeline_history_links")
        connection.exec_driver_sql("DELETE FROM pipeline_candidate_executions")
        connection.exec_driver_sql("UPDATE variation_authority SET source=?, document_json=?",
                                   (document["source"], json.dumps(document, ensure_ascii=False)))
    engine.dispose()
    result = _migrate_once_database(database, migrate_unit_v3)
    assert result["refused_records"] == []
    engine = create_engine(f"sqlite:///{database}")
    with engine.connect() as connection:
        moved = json.loads(connection.exec_driver_sql("SELECT document_json FROM variation_authority").scalar_one())
    engine.dispose()
    assert moved["saijiki"] == "inku.saijiki.v3"
    assert moved["source"] == "黒い太いガッシュの線を引く。"
    assert moved["macro_locks"][0]["digest"] != lock["digest"]


def test_historical_builtin_fallback_never_ignores_a_wrong_digest(tmp_path):
    database = tmp_path / "saved.db"
    _saved_database(database)
    document = {"source": "黒い太筆の線を引く。", "language": "ja", "saijiki": "inku.saijiki.v2",
                "macro_locks": [{"qualified_name": "Nature.下草", "version": "1.0.0", "digest": "sha256:" + "0" * 64}]}
    engine = create_engine(f"sqlite:///{database}")
    with engine.begin() as connection:
        connection.exec_driver_sql("DELETE FROM pipeline_history_links")
        connection.exec_driver_sql("DELETE FROM pipeline_candidate_executions")
        connection.exec_driver_sql("UPDATE variation_authority SET document_json=?", (json.dumps(document, ensure_ascii=False),))
    engine.dispose()
    result = _migrate_once_database(database, migrate_unit_v3)
    assert any(item["kind"] == "variation_documents" for item in result["refused_records"])


def test_orphan_variation_can_reuse_exact_builtin_lock_from_saved_context(tmp_path):
    from pathlib import Path

    database = tmp_path / "saved.db"
    _saved_database(database)
    fixture = Path(__file__).resolve().parents[2] / "core/crates/inku-ddl/tests/fixtures/nature-leaves-1.0-package.json"
    definitions = [item["definition"] for item in json.loads(fixture.read_text())["entries"]]
    definition = next(item for item in definitions if item["heading"] == "下草")
    lock = {"qualified_name": "Nature.下草", "version": "1.0.0", "digest": "sha256:" + "a" * 64}
    source = "黒い太筆の線を引く。"
    digest = hashlib.sha256(source.encode()).hexdigest()
    document = json.dumps({"source": source, "language": "ja", "saijiki": "inku.saijiki.v2",
                           "macro_locks": [lock]}, ensure_ascii=False)
    engine = create_engine(f"sqlite:///{database}")
    with engine.begin() as connection:
        context = json.loads(connection.exec_driver_sql("SELECT fork_context_bytes FROM pipeline_history_links").scalar_one())
        context["config"]["definitions"] = [definition]
        context["macro_catalog"]["definition_locks"] = [lock]
        raw = json.dumps(context, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
        connection.exec_driver_sql("UPDATE pipeline_history_links SET fork_context_bytes=?,fork_context_digest=?",
                                   (raw, hashlib.sha256(raw).hexdigest()))
        from inku_server.persistence.schema import VariationAuthorityRow
        connection.execute(VariationAuthorityRow.__table__.insert().values(
            owner_id="u", variation_id="orphan", protocol_version="inku.variation-authority.v1",
            revision="1", origin="user_authored_ddl", authority="ddl_authoritative", source=source,
            document_json=document, ddl_digest=digest, authority_digest="0" * 64, updated_at=1))
    engine.dispose()
    result = _migrate_once_database(database, migrate_unit_v3)
    assert not [item for item in result["refused_records"] if item["id"].endswith("/orphan")]
    engine = create_engine(f"sqlite:///{database}")
    with engine.connect() as connection:
        moved = json.loads(connection.exec_driver_sql("SELECT document_json FROM variation_authority WHERE variation_id='orphan'").scalar_one())
    engine.dispose()
    assert moved["saijiki"] == "inku.saijiki.v3"
