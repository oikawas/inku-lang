"""Release login startup and storage, without native rendering or OAuth."""

import json
import sys
from types import ModuleType
from unittest.mock import Mock

import pytest

from inku_server import chatgpt_runtime as runtime
from inku_server.chatgpt_store import ChatGPTError, CredentialStore


def test_release_login_container_uses_verified_startup_and_persistent_owner_storage(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("INKU_DB_URL", "sqlite:///" + str(tmp_path / "fixture.db"))
    import inku_server
    import uvicorn
    from inku_server import chatgpt_cli, db, logging_setup

    monkeypatch.setenv("INKU_CHATGPT_PLAN_ENABLED", "1")
    monkeypatch.setenv("INKU_CHATGPT_SELF_HOSTED", "1")
    monkeypatch.setenv("INKU_DEVELOPER_MODE", "0")
    monkeypatch.setenv("INKU_SINGLE_USER", "0")
    monkeypatch.setenv("INKU_CHATGPT_AUTH_DIR", str(tmp_path / "data" / "chatgpt"))
    monkeypatch.setenv("INKU_SERVER_HOST", "0.0.0.0")
    monkeypatch.setenv("INKU_SERVER_PORT", "8100")
    monkeypatch.setenv("INKU_SERVER_RELOAD", "1")
    monkeypatch.setattr(runtime, "_startup", None)
    monkeypatch.setattr(db, "get_user", lambda owner: {"id": owner, "username": owner} if owner in {"owner", "other"} else None)
    monkeypatch.setattr(db, "init_db", lambda: None)
    monkeypatch.setattr(logging_setup, "configure_logging", lambda: None)
    monkeypatch.setattr(db, "single_user_mode_enabled", lambda: False)
    assert runtime.availability()[0] is False  # An environment flag cannot verify a serving process.
    monkeypatch.setattr(sys, "argv", ["inku-chatgpt", "recipient", "--owner-id", "owner"])
    chatgpt_cli.main()
    request = json.loads(capsys.readouterr().out)
    assert runtime._startup is None  # The recipient CLI is not a server.
    store = CredentialStore()
    key = (store.root / "credential.key").read_bytes()
    assert store.root.stat().st_mode & 0o777 == 0o700
    assert all(path.stat().st_mode & 0o077 == 0 for path in store.root.iterdir())
    assert CredentialStore().host_id() == request["host_id"]
    assert (store.root / "credential.key").read_bytes() == key
    assert CredentialStore().read("other")["requests"] == {}

    api = ModuleType("inku_server.api")
    api.app = object()
    api.main = Mock(side_effect=AssertionError("unverified startup"))
    monkeypatch.setitem(sys.modules, "inku_server.api", api)
    run = Mock()
    monkeypatch.setattr(uvicorn, "run", run)
    inku_server.main()
    run.assert_called_once_with(api.app, host="0.0.0.0", port=8100, workers=1, reload=False)
    assert runtime.availability() == (True, None)
    runtime.check_owner("owner")
    with pytest.raises(ChatGPTError, match="owner_not_allowed"):
        runtime.check_owner("missing")
    monkeypatch.setattr(db, "single_user_mode_enabled", lambda: True)
    monkeypatch.setattr(db, "single_user_account", lambda: {"id": "owner"})
    with pytest.raises(ChatGPTError, match="owner_not_allowed"):
        runtime.check_owner("other")
    monkeypatch.setattr(db, "single_user_mode_enabled", lambda: False)
    runtime.configure_startup("127.0.0.1", 8100, self_hosted=False)
    assert runtime.availability()[0] is False
