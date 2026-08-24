import os
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
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


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "child_bake_pool: let a save bake in a real child process, as production does",
    )


def pytest_sessionfinish(session, exitstatus):
    from inku_server.api_core.thumbnails import shutdown_bake_pool

    shutdown_bake_pool()
    for path in (_TEST_DB_PATH, _TEST_THUMBS_PATH):
        if path is None:
            continue
        try:
            path.unlink()
        except FileNotFoundError:
            pass


@pytest.fixture
def rebuild_in_process(monkeypatch):
    """Make the thumbnail rebuild bake in this process for the length of a test.

    The rebuild rasterizes in child processes -- resvg_py holds the GIL, so a
    pool of six threads finished twelve bakes in 11.49 s against one thread's
    10.08 s -- and monkeypatch cannot reach a child. A test that needs to
    arrange what one bake does, raise or block, asks for this fixture and then
    patches `inku_analysis.rasterizer.svg_to_png` as usual.

    This weakens nothing the tests rely on: a future re-raises on `.result()`
    whichever pool produced it. That the pool is a process pool at all is
    measured on its own, by watching which class the rebuild constructs.
    """
    from inku_server.api_core import thumbnails

    class InProcessPool(ThreadPoolExecutor):
        def __init__(self, *args, mp_context=None, **kwargs):
            super().__init__(*args, **kwargs)

    class NoContext:
        @staticmethod
        def get_context(_name):
            return None

    monkeypatch.setattr(thumbnails, "ProcessPoolExecutor", InProcessPool)
    monkeypatch.setattr(thumbnails, "multiprocessing", NoContext())


def _in_process_bake_pool():
    """The save path's pool, standing in as threads of this process."""
    return ThreadPoolExecutor(max_workers=2, thread_name_prefix="inku-thumb-bake")


@pytest.fixture(autouse=True)
def bake_in_process(request, monkeypatch):
    """Bake a freshly saved work in this process, unless the test says otherwise.

    Unlike the rebuild, which runs only when a test calls it, the save path
    bakes on every POST /api/history. Left alone it would spawn a child for each
    such test -- and a patched `svg_to_png` would never reach the one doing the
    work, so a test arranging a slow or raising bake would pass without ever
    making one. The default is therefore an in-process pool, and the tests that
    have to show the bake really leaves this process carry
    `@pytest.mark.child_bake_pool`.

    ⚠ Only the save path is redirected. The rebuild keeps its opt-in fixture
    above: replacing `ProcessPoolExecutor` for every test would change what
    `test_the_rasterizing_leaves_this_process_and_the_writing_does_not` compares
    against, and that gate is how the rebuild's own child pool is measured.

    The pool is cleared around every test either way, so one test's pool never
    answers the next test's save.
    """
    from inku_server.api_core import thumbnails

    monkeypatch.setattr(thumbnails, "_bake_pool", None)
    monkeypatch.setattr(thumbnails, "_bake_pool_closed", False)
    if "child_bake_pool" not in request.keywords:
        monkeypatch.setattr(thumbnails, "_new_bake_pool", _in_process_bake_pool)
    yield
    pool = thumbnails._bake_pool
    if pool is not None:
        pool.shutdown(wait=False)
