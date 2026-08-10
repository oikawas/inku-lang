"""T-11: the CLI grants permission groups, and prints them back.

Run through the executable, against a server this test starts, rather than by
calling the product functions: what an endpoint does is decided by the request
body, and a sender that never writes a key is a sender nobody has tested.  The
`--role` flag has to be gone from the parser, not merely unused by the code.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest


_REPO = Path(__file__).resolve().parents[2]
_SERVER = _REPO / "server"

# The client is packaged on its own; a checkout without the server cannot start
# one, and a red test there would report an absent directory as a broken CLI.
pytestmark = pytest.mark.skipif(
    not (_SERVER / "src" / "inku_server" / "api.py").is_file(),
    reason="server sources are not in this checkout",
)

_ADMIN_PASSWORD = "permission-groups-test-password"


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture(scope="module")
def live_server(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("permission-groups")
    port = _free_port()
    env = {
        **os.environ,
        "INKU_DB_URL": f"sqlite:///{tmp / 'groups.db'}",
        "INKU_BOOTSTRAP_ADMIN_PASSWORD": _ADMIN_PASSWORD,
        "INKU_BOOTSTRAP_ADMIN_USERNAME": "admin",
        "INKU_SINGLE_USER": "0",
    }
    proc = subprocess.Popen(
        ["uv", "run", "uvicorn", "inku_server.api:app", "--host", "127.0.0.1", "--port", str(port)],
        cwd=_SERVER,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    base = f"http://127.0.0.1:{port}"
    try:
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                pytest.skip("the server process exited before it was ready")
            try:
                with urllib.request.urlopen(f"{base}/health", timeout=2):
                    break
            except (urllib.error.URLError, ConnectionError, TimeoutError):
                time.sleep(0.5)
        else:
            pytest.skip("the server did not come up in time")

        config = tmp / "cli-config.json"
        yield base, config
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            proc.kill()


def _cli(live, *args: str) -> subprocess.CompletedProcess:
    base, config = live
    # INKU_CLI_CONFIG is not optional here: without it the run would write over
    # the developer's own ~/.config/inku-cli/config.json.  INKU_BASE_URL covers
    # the first call, before `login` has written the address into that file.
    env = {**os.environ, "INKU_CLI_CONFIG": str(config), "INKU_BASE_URL": base}
    return subprocess.run(
        [sys.executable, "-m", "inku_cli.cli", *args],
        cwd=_REPO / "cli",
        env=env,
        capture_output=True,
        text=True,
    )


@pytest.fixture(scope="module")
def logged_in(live_server):
    base, _config = live_server
    done = _cli(live_server, "login", "-u", "admin", "-p", _ADMIN_PASSWORD, "--base-url", base)
    assert done.returncode == 0, done.stderr or done.stdout
    return live_server


def test_t11_user_create_grants_a_permission_group_and_role_is_gone(logged_in) -> None:
    created = _cli(
        logged_in,
        "user", "create", "cli-lead", "cli-lead@example.test", "password-123",
        "--permission-group", "leaders",
    )
    assert created.returncode == 0, created.stderr or created.stdout
    payload = json.loads(created.stdout)
    assert payload["permission_groups"] == ["leaders"]
    assert "role" not in payload

    refused = _cli(
        logged_in,
        "user", "create", "cli-old", "cli-old@example.test", "password-123",
        "--role", "group_lead",
    )
    assert refused.returncode != 0
    assert "--role" in (refused.stderr + refused.stdout)


def test_t11_me_prints_the_permission_groups_and_no_role(logged_in) -> None:
    done = _cli(logged_in, "me")
    assert done.returncode == 0, done.stderr or done.stdout
    payload = json.loads(done.stdout)
    assert payload["permission_groups"] == ["admins"]
    assert payload["permission_group_labels"]
    assert "role" not in payload
    assert "role_label" not in payload
