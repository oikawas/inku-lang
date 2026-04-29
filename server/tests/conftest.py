import os
import tempfile
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

_TEST_DB_PATH: Path | None = None

if os.getenv("INKU_TEST_USE_CONFIGURED_DB") != "1":
    _TEST_DB_PATH = Path(tempfile.gettempdir()) / f"inku-test-{os.getpid()}.db"
    try:
        _TEST_DB_PATH.unlink()
    except FileNotFoundError:
        pass
    os.environ["INKU_DB_URL"] = f"sqlite:///{_TEST_DB_PATH}"
    os.environ.setdefault("INKU_BOOTSTRAP_ADMIN_PASSWORD", "test-admin-password")


def pytest_sessionfinish(session, exitstatus):
    if _TEST_DB_PATH is None:
        return
    try:
        _TEST_DB_PATH.unlink()
    except FileNotFoundError:
        pass
