"""The download-folder setting is the half of the feature the server can hold.

A FileSystemDirectoryHandle is a live browser object: it cannot be serialised,
so it never reaches here. What the server stores is the user's intent
(`download_folder_enabled`) and the folder's display name, so the settings panel
can name the folder before IndexedDB answers -- and so the user can be told the
handle is per browser.
"""

from __future__ import annotations

import sqlite3
import uuid

from fastapi.testclient import TestClient

from inku_server import db
from inku_server.api import app


client = TestClient(app)


def _user(prefix: str) -> tuple[dict, dict[str, str], str, str]:
    suffix = uuid.uuid4().hex[:8]
    group = db.add_user_group(f"{prefix}-group-{suffix}")
    user = db.add_user(
        username=f"{prefix}-{suffix}",
        email=f"{prefix}-{suffix}@example.test",
        password="password-123",
        permission_groups=["users"],
        group_id=group["id"],
    )
    token = db.create_session(user["id"])
    return user, {"Authorization": f"Bearer {token}"}, token, group["id"]


def _cleanup(user: dict, token: str, group_id: str) -> None:
    db.delete_session(token)
    db.delete_user(user["id"])
    db.delete_user_group(group_id)


def test_setting_is_saved_and_read_back():
    user, headers, token, group_id = _user("download-folder")
    try:
        assert user["download_folder_enabled"] is False
        assert user["download_folder_name"] is None

        saved = client.patch(
            "/api/auth/me/settings",
            json={"download_folder_enabled": True, "download_folder_name": "inku-out"},
            headers=headers,
        )
        assert saved.status_code == 200
        assert saved.json()["download_folder_enabled"] is True
        assert saved.json()["download_folder_name"] == "inku-out"

        reread = client.get("/api/auth/me", headers=headers).json()
        assert reread["download_folder_enabled"] is True
        assert reread["download_folder_name"] == "inku-out"
    finally:
        _cleanup(user, token, group_id)


def test_clearing_the_folder_drops_the_name():
    user, headers, token, group_id = _user("download-folder-clear")
    try:
        client.patch(
            "/api/auth/me/settings",
            json={"download_folder_enabled": True, "download_folder_name": "inku-out"},
            headers=headers,
        )
        cleared = client.patch(
            "/api/auth/me/settings",
            json={"download_folder_enabled": False, "download_folder_name": ""},
            headers=headers,
        ).json()
        assert cleared["download_folder_enabled"] is False
        assert cleared["download_folder_name"] is None
    finally:
        _cleanup(user, token, group_id)


def test_the_setting_does_not_disturb_the_other_settings():
    user, headers, token, group_id = _user("download-folder-isolated")
    try:
        before = client.get("/api/auth/me", headers=headers).json()
        client.patch(
            "/api/auth/me/settings",
            json={"download_folder_enabled": True, "download_folder_name": "inku-out"},
            headers=headers,
        )
        after = client.get("/api/auth/me", headers=headers).json()
        for key in ("ui_theme", "ui_mode", "tooltips_enabled", "settings_tab"):
            assert after[key] == before[key], f"{key} moved"
    finally:
        _cleanup(user, token, group_id)


def test_an_overlong_folder_name_is_refused():
    user, headers, token, group_id = _user("download-folder-long")
    try:
        response = client.patch(
            "/api/auth/me/settings",
            json={"download_folder_name": "x" * 241},
            headers=headers,
        )
        assert response.status_code >= 400
    finally:
        _cleanup(user, token, group_id)


def test_a_user_row_from_before_the_columns_reads_as_off(tmp_path):
    """A user row written before the columns existed must survive the migration.

    Exercised against the real migration statements: the columns arrive by ALTER
    TABLE, and an existing row is only correct because those statements carry a
    default. The name column has none, so the row must come back NULL rather
    than failing to read.
    """
    database = tmp_path / "legacy.sqlite3"
    connection = sqlite3.connect(database)
    connection.executescript(
        """
        CREATE TABLE user_accounts (
            id VARCHAR PRIMARY KEY, username VARCHAR NOT NULL,
            ui_theme VARCHAR NOT NULL DEFAULT 'light',
            tooltips_enabled BOOLEAN NOT NULL DEFAULT 1
        );
        INSERT INTO user_accounts (id, username) VALUES ('old-user', 'legacy');
        """
    )
    connection.commit()
    columns = [row[1] for row in connection.execute("PRAGMA table_info(user_accounts)")]
    assert "download_folder_enabled" not in columns

    for column in ("download_folder_enabled", "download_folder_name"):
        connection.execute(db._USER_ACCOUNT_COLUMN_MIGRATIONS[column])
    connection.commit()

    enabled, name, tooltips = connection.execute(
        "SELECT download_folder_enabled, download_folder_name, tooltips_enabled"
        " FROM user_accounts WHERE id = 'old-user'"
    ).fetchone()
    assert enabled == 0, "an existing user came back with the folder already on"
    assert name is None
    assert tooltips == 1, "the migration disturbed a setting it does not own"
    connection.close()
