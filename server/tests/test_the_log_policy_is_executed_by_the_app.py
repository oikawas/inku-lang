"""The log retention policy is executed by the application, not by the host OS.

Until 2026-08-09 the settings screen generated a systemd drop-in and a logrotate
snippet for an operator to copy. The drop-in said
`StandardOutput=journal+append:/var/log/inku/inku-api.log`, which systemd cannot
parse, so it was silently ignored and the files stayed at 0 bytes for months --
and the container distribution had nowhere to copy either file to (ledger I-167).

These tests hold the shape that fixes both: the app writes, rotates and prunes
its own files, and the container is pointed at the data volume.
"""
from __future__ import annotations

import gzip

import logging
import pathlib

import pytest

from inku_server import logging_setup
from inku_server.api_core.routers import settings as settings_router

ROOT = pathlib.Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def _isolate_logging(tmp_path, monkeypatch):
    """Every test gets its own log directory and a clean root logger."""
    monkeypatch.setenv("INKU_LOG_DIR", str(tmp_path / "logs"))
    root = logging.getLogger()
    kept = list(root.handlers)
    yield
    logging_setup.configure_logging({"enabled": False})
    root.handlers[:] = kept


def _policy(**over) -> dict:
    base = {"enabled": True, "retention_days": 90, "rotate": "daily", "compress": True}
    base.update(over)
    return base


# T-1 -- the app actually writes a line to a file it made itself.
def test_an_enabled_policy_puts_a_written_line_into_a_file():
    logging_setup.configure_logging(_policy())
    logging.getLogger("inku_server.test").warning("a line the app wrote itself")

    handler = logging_setup.installed_file_handler()
    assert handler is not None
    handler.flush()
    written = pathlib.Path(handler.baseFilename)
    assert written.exists()
    assert "a line the app wrote itself" in written.read_text(encoding="utf-8")


# T-2 -- disabled means no file, not an empty one.
def test_a_disabled_policy_writes_no_file_at_all():
    logging_setup.configure_logging(_policy(enabled=False))
    assert logging_setup.installed_file_handler() is None
    assert logging_setup.current_log_files() == []


# T-3 -- "retention days" has to arrive at the handler to mean anything. This is
# the effective value, not the number the screen prints back at you.
def test_retention_days_reaches_the_handler_as_the_kept_count():
    handler = logging_setup.configure_logging(_policy(retention_days=17))
    assert handler is not None
    assert handler.backupCount == 17


# T-4 -- the three choices must land on three different schedules. A build that
# collapses them still returns the stored string, so the string cannot be the gate.
@pytest.mark.parametrize(
    "rotate,expected",
    [("daily", ("midnight", 1)), ("weekly", ("W0", 1)), ("monthly", ("midnight", 30))],
)
def test_each_rotation_choice_is_a_distinct_schedule(rotate, expected):
    assert logging_setup.rotation_schedule(rotate) == expected
    assert len({logging_setup.rotation_schedule(r) for r in ("daily", "weekly", "monthly")}) == 3


# T-5 -- compression is performed, not described.
def test_compression_produces_a_gzip_member_on_rotation():
    handler = logging_setup.configure_logging(_policy(compress=True))
    assert handler is not None
    logging.getLogger("inku_server.test").warning("before the roll")
    handler.flush()

    rolled = pathlib.Path(handler.baseFilename).with_suffix(".log.rolled")
    handler.rotator(handler.baseFilename, str(rolled))

    packed = rolled.with_name(rolled.name + ".gz")
    assert packed.exists(), "compress=True must leave a .gz behind"
    assert "before the roll" in gzip.decompress(packed.read_bytes()).decode("utf-8")
    assert not pathlib.Path(handler.baseFilename).exists()


def test_without_compression_the_rotated_file_stays_plain():
    handler = logging_setup.configure_logging(_policy(compress=False))
    assert handler is not None
    logging.getLogger("inku_server.test").warning("before the roll")
    handler.flush()

    rolled = pathlib.Path(handler.baseFilename).with_suffix(".log.rolled")
    handler.rotator(handler.baseFilename, str(rolled))

    assert rolled.exists()
    assert not rolled.with_name(rolled.name + ".gz").exists()


# T-6 -- journalctl and docker logs must keep working. Writing files is an
# addition, not a move.
def test_lines_keep_going_to_the_stream_as_well():
    # Start from a root with no handlers at all. Asserting "a StreamHandler is
    # present" against the ambient root passes on pytest's own capture handler,
    # so removing the product code that installs one changed nothing -- measured
    # 2026-08-09, the perturbation was a miss until this line was added.
    root = logging.getLogger()
    borrowed = list(root.handlers)
    root.handlers[:] = []
    try:
        logging_setup.configure_logging(_policy())
        streams = [
            h for h in root.handlers
            if isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler)
        ]
        assert streams, "the stream handler is what journalctl and docker logs read"
    finally:
        root.handlers[:] = borrowed


# T-7 -- the directory follows the environment, the way INKU_DB_BACKUP_DIR does.
def test_the_log_directory_follows_the_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("INKU_LOG_DIR", str(tmp_path / "somewhere-else"))
    assert logging_setup.log_dir() == tmp_path / "somewhere-else"

    monkeypatch.delenv("INKU_LOG_DIR", raising=False)
    assert logging_setup.log_dir() == pathlib.Path.home() / ".local" / "share" / "inku" / "logs"


# T-8 -- the two generators are gone from the response model. Negative gate.
def test_the_response_no_longer_carries_host_os_config():
    fields = set(settings_router.LogRetentionStatus.model_fields)
    assert "systemd_dropins" not in fields
    assert "logrotate_config" not in fields
    assert "services" not in fields


# T-9 -- and the positive one it is paired with: the response names the place the
# app actually writes to. T-8 alone is satisfied by deleting the whole feature.
def test_the_response_names_the_directory_the_app_writes_to():
    logging_setup.configure_logging(_policy())
    logging.getLogger("inku_server.test").warning("something to find")
    handler = logging_setup.installed_file_handler()
    assert handler is not None
    handler.flush()

    status = settings_router._log_retention_status(_policy())
    assert status.log_dir == str(logging_setup.log_dir())
    assert logging_setup.LOG_FILE_NAME in status.files
    assert pathlib.Path(handler.baseFilename).parent == pathlib.Path(status.log_dir)


# T-12 -- the startup banner may only claim what the policy actually says. It
# used to print /var/log/inku/inku-api.log unconditionally while that file sat
# at 0 bytes. Added while implementing, so it carries its own perturbation.
def test_the_banner_names_the_destination_the_policy_chose(monkeypatch):
    from inku_server import api as api_module
    from inku_server import db as db_module

    monkeypatch.setattr(db_module, "get_log_retention_settings", lambda: {"enabled": True})
    assert api_module._log_destination() == str(logging_setup.log_dir())

    monkeypatch.setattr(db_module, "get_log_retention_settings", lambda: {"enabled": False})
    assert "no file" in api_module._log_destination()

    # ...and the banner has to be the thing that says it. Reading _log_destination()
    # on its own leaves the printed line free to keep its old hardcoded path, which
    # is exactly what it did: the perturbation that restored the constant was a miss
    # until this walked the banner itself (measured 2026-08-09).
    monkeypatch.setattr(db_module, "get_log_retention_settings", lambda: {"enabled": True})
    printed = api_module._startup_banner(
        service_name="inku-api", service_kind="test", emoji="*"
    )
    assert str(logging_setup.log_dir()) in printed
    assert "/var/log/inku" not in printed


# T-13 -- the entry point has to walk the wiring. Everything above tests
# configure_logging(); none of it notices if main() stops calling it, which is
# the exact failure this whole issue was: a policy that is stored and never run.
def test_the_entry_point_applies_the_policy_before_serving(monkeypatch):
    from inku_server import api as api_module

    called: list[str] = []
    monkeypatch.setattr(
        "inku_server.logging_setup.configure_logging",
        lambda *a, **k: called.append("configured"),
    )
    import uvicorn

    monkeypatch.setattr(uvicorn, "run", lambda *a, **k: called.append("served"))
    api_module.main()

    assert called == ["configured", "served"], (
        "main() must apply the stored log policy, and do it before serving"
    )


# T-10 -- the container is pointed at the data volume, so the files survive a
# restart exactly as the DB backups do.
def test_the_image_points_the_log_directory_at_the_data_volume():
    dockerfile = ROOT / "server" / "Dockerfile"
    if not dockerfile.exists():
        pytest.skip("the image definition is not part of this checkout")
    text = dockerfile.read_text(encoding="utf-8")
    assert "INKU_LOG_DIR=/data/logs" in text
    assert "/data/logs" in text.split("mkdir -p", 1)[1].split("\n", 1)[0]


# T-11 -- what the daemon collects from stdout needs its own ceiling; the app's
# retention does not reach it.
def test_the_compose_services_cap_what_the_daemon_collects():
    compose = ROOT / "compose.yaml"
    if not compose.exists():
        pytest.skip("the compose file is not part of this checkout")
    text = compose.read_text(encoding="utf-8")
    assert text.count("max-size:") >= 2, "both api and web need a ceiling"
    assert text.count("max-file:") >= 2
    api_block, web_block = text.split("  web:", 1)
    assert "max-size:" in api_block, "the api service is uncapped"
    assert "max-size:" in web_block, "the web service is uncapped"
