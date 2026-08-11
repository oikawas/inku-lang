import os
import tempfile
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

_TEST_DB_PATH: Path | None = None
_TEST_THUMBS_PATH: Path | None = None

if os.getenv("INKU_TEST_USE_CONFIGURED_DB") != "1":
    _TEST_DB_PATH = Path(tempfile.gettempdir()) / f"inku-test-{os.getpid()}.db"
    try:
        _TEST_DB_PATH.unlink()
    except FileNotFoundError:
        pass
    os.environ["INKU_DB_URL"] = f"sqlite:///{_TEST_DB_PATH}"
    # Named for this run rather than left to derive itself. The derived default
    # is thumbs.db beside the canonical file, which here is the system temp
    # directory -- two runs at once would share one store, and nothing would
    # clean it up afterwards.
    _TEST_THUMBS_PATH = Path(tempfile.gettempdir()) / f"inku-test-thumbs-{os.getpid()}.db"
    try:
        _TEST_THUMBS_PATH.unlink()
    except FileNotFoundError:
        pass
    os.environ["INKU_THUMBS_DB_URL"] = f"sqlite:///{_TEST_THUMBS_PATH}"
    os.environ.setdefault("INKU_BOOTSTRAP_ADMIN_PASSWORD", "test-admin-password")


def pytest_sessionfinish(session, exitstatus):
    for path in (_TEST_DB_PATH, _TEST_THUMBS_PATH):
        if path is None:
            continue
        try:
            path.unlink()
        except FileNotFoundError:
            pass
