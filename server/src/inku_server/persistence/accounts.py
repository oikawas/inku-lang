"""User-account read and authentication persistence owner."""

from __future__ import annotations

from collections.abc import Callable, Collection, Mapping
from dataclasses import dataclass
from hashlib import pbkdf2_hmac
import json
import secrets
from typing import Any

from sqlalchemy import text

from .access import has_permission_group
from .schema import (
    ExternalIdentityRow,
    HistoryAclRow,
    HistoryRow,
    LineageEdgeRow,
    LineageNodeRow,
    OkugakiRow,
    UnreadWordRow,
    UserAccountRow,
    UserGroupRow,
    UserPermissionGroupRow,
    UserSessionRow,
)


def hash_password(password: str) -> str:
    if not password:
        raise ValueError("password is required")
    salt = secrets.token_bytes(16)
    iterations = 310_000
    digest = pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return f"pbkdf2_sha256${iterations}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        algorithm, iterations_raw, salt_hex, digest_hex = stored_hash.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        iterations = int(iterations_raw)
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(digest_hex)
    except Exception:  # noqa: BLE001
        return False
    actual = pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return secrets.compare_digest(actual, expected)


DUMMY_PASSWORD_HASH = hash_password("inku-nonexistent-account-timing-guard")


@dataclass(frozen=True)
class BootstrapAdminPasswordResolver:
    getenv_fn: Callable[[str, str | None], str | None]

    def resolve(self) -> str | None:
        # An empty value means unset, not a zero-length password: compose interpolation
        # (${VAR:-}) and env-file templates hand one over whenever the operator left the
        # field blank. Raising there would fail startup on an empty database, where the
        # bootstrap admin is the only thing that reads this.
        password = self.getenv_fn("INKU_BOOTSTRAP_ADMIN_PASSWORD", None)
        if password:
            if len(password) < 8:
                raise ValueError(
                    "INKU_BOOTSTRAP_ADMIN_PASSWORD must be at least 8 characters"
                )
            return password

        allow_insecure = self.getenv_fn(
            "INKU_ALLOW_INSECURE_BOOTSTRAP_ADMIN", ""
        ).lower() in {"1", "true", "yes"}
        if allow_insecure:
            return "inku-admin"
        return None


def loads_or_none(raw: str | None):
    """The stored JSON, or None when there is nothing readable stored.

    None and a stored empty list have to stay apart: the first is an account
    that never answered and takes the default, the second is an account that
    asked for nothing.
    """
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


@dataclass(frozen=True)
class UserAccountProjector:
    object_session_fn: Callable[[UserAccountRow], Any]
    permission_groups_of_fn: Callable[[Any, str], list[str]]
    permission_group_labels: Mapping[str, str]
    ui_modes: Collection[str]
    ui_custom_keys: Collection[str]
    settings_tabs: Collection[str]
    normalize_history_strip_fields_fn: Callable[[Any], list[str]]
    normalize_user_model_settings_fn: Callable[[Any], dict]

    def project(self, row: UserAccountRow, group_name: str | None = None) -> dict:
        # Read the memberships through the row's own session rather than defaulting
        # to an empty list when there is none: an actor that silently came back with
        # no permission groups would be refused everywhere, and nothing would say why.
        session = self.object_session_fn(row)
        if session is None:
            raise RuntimeError("_user_to_dict needs an attached row to read permission groups")
        permission_groups = self.permission_groups_of_fn(session, row.id)

        try:
            model_settings = json.loads(row.model_settings or "{}")
        except json.JSONDecodeError:
            model_settings = {}
        try:
            ui_custom_raw = json.loads(row.ui_custom or "{}")
        except json.JSONDecodeError:
            ui_custom_raw = {}
        ui_custom = (
            {
                key: value
                for key, value in ui_custom_raw.items()
                if key in self.ui_custom_keys and isinstance(value, bool)
            }
            if isinstance(ui_custom_raw, dict)
            else {}
        )
        history_strip_fields = self.normalize_history_strip_fields_fn(
            loads_or_none(row.history_strip_fields)
        )
        return {
            "id": row.id,
            "username": row.username,
            "email": row.email,
            "permission_groups": permission_groups,
            "permission_group_labels": [
                self.permission_group_labels.get(name, name) for name in permission_groups
            ],
            "group_id": row.group_id,
            "group_name": group_name,
            "ui_theme": row.ui_theme if row.ui_theme in {"light", "dark"} else "light",
            "ui_mode": row.ui_mode if row.ui_mode in self.ui_modes else "simple",
            "ui_custom": ui_custom,
            "history_strip_fields": history_strip_fields,
            "tooltips_enabled": row.tooltips_enabled is not False,
            "download_folder_enabled": row.download_folder_enabled is True,
            "download_folder_name": row.download_folder_name,
            "settings_tab": row.settings_tab if row.settings_tab in self.settings_tabs else "db",
            "model_settings": self.normalize_user_model_settings_fn(model_settings),
            "image_generation_count": row.image_generation_count or 0,
            "at": row.at,
        }


@dataclass(frozen=True)
class AccountActorReader:
    session_factory: Callable[[], Any]
    permission_groups_of_fn: Callable[[Any, str], list[str]]

    def get(self, user_id: str) -> dict:
        with self.session_factory() as session:
            row = session.query(UserAccountRow).filter(UserAccountRow.id == user_id).first()
            if row is None:
                # No account, no groups: falls through to the owner-only branch of
                # every predicate. An unknown id must never widen anything.
                return {"id": user_id, "permission_groups": [], "group_id": None}
            return {
                "id": user_id,
                "permission_groups": self.permission_groups_of_fn(session, user_id),
                "group_id": row.group_id,
            }


@dataclass(frozen=True)
class UserAccountReader:
    session_factory: Callable[[], Any]
    user_to_dict_fn: Callable[[UserAccountRow, str | None], dict]
    verify_password_fn: Callable[[str, str], bool]
    dummy_password_hash: str

    def list_users(self) -> list[dict]:
        with self.session_factory() as session:
            rows = (
                session.query(UserAccountRow, UserGroupRow.name)
                .outerjoin(UserGroupRow, UserAccountRow.group_id == UserGroupRow.id)
                .order_by(UserAccountRow.username.asc())
                .all()
            )
            return [self.user_to_dict_fn(row, group_name) for row, group_name in rows]

    def get_user(self, user_id: str) -> dict | None:
        with self.session_factory() as session:
            row = session.get(UserAccountRow, user_id)
            if not row:
                return None
            group_name = session.get(UserGroupRow, row.group_id).name if row.group_id else None
            return self.user_to_dict_fn(row, group_name)

    def authenticate_user(self, username: str, password: str) -> dict | None:
        with self.session_factory() as session:
            row = (
                session.query(UserAccountRow)
                .filter(UserAccountRow.username == username.strip())
                .first()
            )
            stored_hash = row.password_hash if row is not None else self.dummy_password_hash
            password_matches = self.verify_password_fn(password, stored_hash)
            if row is None or not password_matches:
                return None
            group_name = session.get(UserGroupRow, row.group_id).name if row.group_id else None
            return self.user_to_dict_fn(row, group_name)

    def list_users_for_actor(self, actor: dict) -> list[dict]:
        if has_permission_group(actor, "admins"):
            return self.list_users()
        if has_permission_group(actor, "leaders") and actor.get("group_id"):
            with self.session_factory() as session:
                rows = (
                    session.query(UserAccountRow, UserGroupRow.name)
                    .outerjoin(UserGroupRow, UserAccountRow.group_id == UserGroupRow.id)
                    .filter(UserAccountRow.group_id == actor["group_id"])
                    .order_by(UserAccountRow.username.asc())
                    .all()
                )
                return [self.user_to_dict_fn(row, group_name) for row, group_name in rows]
        return []

    def list_group_peers(self, user_id: str) -> list[dict]:
        """The caller's own organisation group, as names to share a work with.

        Id and display name only, and only the caller's own group. Sharing needs a
        way to name a person, and the account listing is a member manager's -- the
        owner of a work usually is not one, so before this they had to be told a raw
        id and paste it. Opening the whole listing instead would put every name on
        the server in front of everyone, to solve a problem that stops at the
        organisation boundary.

        An account with no organisation group gets an empty list, not everyone.
        """
        with self.session_factory() as session:
            row = session.get(UserAccountRow, user_id)
            if row is None or not row.group_id:
                return []
            peers = (
                session.query(UserAccountRow)
                .filter(
                    UserAccountRow.group_id == row.group_id,
                    UserAccountRow.id != user_id,  # sharing with oneself is not a thing
                )
                .order_by(UserAccountRow.username.asc())
                .all()
            )
            return [{"id": peer.id, "username": peer.username} for peer in peers]


@dataclass(frozen=True)
class UserAccountCreator:
    session_factory: Callable[[], Any]
    uuid_fn: Callable[[], Any]
    now_fn: Callable[[], int]
    hash_password_fn: Callable[[str], str]
    normalize_permission_groups_fn: Callable[[list[str]], list[str]]
    derived_role_fn: Callable[[list[str]], str]
    set_permission_groups_fn: Callable[[Any, UserAccountRow, list[str]], list[str]]
    user_to_dict_fn: Callable[[UserAccountRow, str | None], dict]

    def add_user(
        self,
        username: str,
        email: str,
        password: str,
        permission_groups: list[str],
        group_id: str | None,
    ) -> dict:
        username = username.strip()
        email = email.strip()
        if not username:
            raise ValueError("username is required")
        if not email:
            raise ValueError("email is required")
        wanted = self.normalize_permission_groups_fn(permission_groups)
        row = UserAccountRow(
            id=str(self.uuid_fn()),
            username=username,
            email=email,
            password_hash=self.hash_password_fn(password),
            role=self.derived_role_fn(wanted),
            group_id=group_id,
            at=self.now_fn(),
        )
        with self.session_factory() as session:
            if group_id and not session.get(UserGroupRow, group_id):
                raise ValueError("group not found")
            session.add(row)
            session.commit()
            self.set_permission_groups_fn(session, row, wanted)
            session.commit()
            session.refresh(row)
            group_name = session.get(UserGroupRow, row.group_id).name if row.group_id else None
            return self.user_to_dict_fn(row, group_name)


@dataclass(frozen=True)
class UserAccountUpdater:
    session_factory: Callable[[], Any]
    hash_password_fn: Callable[[str], str]
    set_permission_groups_fn: Callable[[Any, UserAccountRow, list[str]], list[str]]
    has_permission_group_fn: Callable[[dict, str], bool]
    holds_no_elevated_group_fn: Callable[[Any], Any]
    user_to_dict_fn: Callable[[UserAccountRow, str | None], dict]
    unset: object

    def update_user(
        self,
        user_id: str,
        *,
        username: str | None = None,
        email: str | None = None,
        password: str | None = None,
        permission_groups: list[str] | None = None,
        group_id: str | None | object = None,
        actor: dict | None = None,
    ) -> dict | None:
        with self.session_factory() as session:
            query = session.query(UserAccountRow).filter(UserAccountRow.id == user_id)
            if actor is not None and not self.has_permission_group_fn(actor, "admins"):
                if not self.has_permission_group_fn(actor, "leaders") or not actor.get("group_id"):
                    return None
                query = query.filter(
                    UserAccountRow.group_id == actor["group_id"],
                    self.holds_no_elevated_group_fn(session),
                )
            row = query.first()
            if not row:
                return None
            if username is not None:
                username = username.strip()
                if not username:
                    raise ValueError("username is required")
                row.username = username
            if email is not None:
                email = email.strip()
                if not email:
                    raise ValueError("email is required")
                row.email = email
            if password is not None and password:
                row.password_hash = self.hash_password_fn(password)
            if permission_groups is not None:
                self.set_permission_groups_fn(session, row, permission_groups)
            if group_id is not self.unset:
                group_id = group_id if isinstance(group_id, str) else None
                if group_id and not session.get(UserGroupRow, group_id):
                    raise ValueError("group not found")
                row.group_id = group_id or None
            session.commit()
            session.refresh(row)
            group_name = session.get(UserGroupRow, row.group_id).name if row.group_id else None
            return self.user_to_dict_fn(row, group_name)


@dataclass(frozen=True)
class CurrentUserProfileUpdater:
    session_factory: Callable[[], Any]
    verify_password_fn: Callable[[str, str], bool]
    hash_password_fn: Callable[[str], str]
    user_to_dict_fn: Callable[[UserAccountRow, str | None], dict]

    def update_current_user_profile(
        self,
        user_id: str,
        *,
        email: str | None = None,
        password: str | None = None,
        current_password: str | None = None,
    ) -> dict | None:
        with self.session_factory() as session:
            row = session.get(UserAccountRow, user_id)
            if not row:
                return None
            if email is not None:
                email = email.strip()
                if not email:
                    raise ValueError("email is required")
                row.email = email
            if password is not None and password:
                if not current_password or not self.verify_password_fn(
                    current_password, row.password_hash
                ):
                    raise ValueError("current password is invalid")
                row.password_hash = self.hash_password_fn(password)
            session.commit()
            session.refresh(row)
            group_name = session.get(UserGroupRow, row.group_id).name if row.group_id else None
            return self.user_to_dict_fn(row, group_name)


@dataclass(frozen=True)
class UserGenerationCounter:
    session_factory: Callable[[], Any]

    def increment_user_generation_count(self, user_id: str, amount: int = 1) -> int | None:
        if amount <= 0:
            raise ValueError("amount must be positive")
        with self.session_factory() as session:
            result = session.execute(
                text(
                    """
                    UPDATE user_accounts
                    SET image_generation_count = COALESCE(image_generation_count, 0) + :amount
                    WHERE id = :user_id
                    """
                ),
                {"amount": amount, "user_id": user_id},
            )
            if result.rowcount == 0:
                session.rollback()
                return None
            session.commit()
            row = session.get(UserAccountRow, user_id)
            if not row:
                return None
            return row.image_generation_count or 0


@dataclass(frozen=True)
class UserAccountDeleter:
    session_factory: Callable[[], Any]
    has_permission_group_fn: Callable[[dict, str], bool]
    holds_no_elevated_group_fn: Callable[[Any], Any]
    owner_actor_fn: Callable[[str], dict]
    owned_by_fn: Callable[[dict, Any], Any]
    delete_acl_for_histories_fn: Callable[[Any, list[str]], None]

    def delete_user(
        self,
        user_id: str,
        *,
        cascade: bool = False,
        actor: dict | None = None,
    ) -> bool:
        with self.session_factory() as session:
            query = session.query(UserAccountRow).filter(UserAccountRow.id == user_id)
            if actor is not None and not self.has_permission_group_fn(actor, "admins"):
                if not self.has_permission_group_fn(actor, "leaders") or not actor.get("group_id"):
                    return False
                query = query.filter(
                    UserAccountRow.group_id == actor["group_id"],
                    self.holds_no_elevated_group_fn(session),
                )
            row = query.first()
            if not row:
                return False
            # The account being deleted, not the one doing the deleting: the cascade
            # selects by ownership so that widening what an admin may write never
            # widens what one deletion removes.
            target_owner = self.owner_actor_fn(user_id)
            if not cascade:
                if (
                    session.query(HistoryRow)
                    .filter(self.owned_by_fn(target_owner, HistoryRow.user_id))
                    .first()
                ):
                    raise ValueError("user has history")
            else:
                self.delete_acl_for_histories_fn(
                    session,
                    [
                        item_id
                        for item_id, in session.query(HistoryRow.id).filter(
                            self.owned_by_fn(target_owner, HistoryRow.user_id)
                        )
                    ],
                )
                session.query(HistoryRow).filter(
                    self.owned_by_fn(target_owner, HistoryRow.user_id)
                ).delete()
            # Both directions: the works this account owned, above, and the grants
            # that named this account as a guest, here. Only the first is a cascade;
            # the second would otherwise survive on other people's works.
            session.query(HistoryAclRow).filter(
                HistoryAclRow.subject_type == "user", HistoryAclRow.subject_id == user_id
            ).delete(synchronize_session=False)
            session.query(OkugakiRow).filter(
                self.owned_by_fn(target_owner, OkugakiRow.user_id)
            ).delete()
            session.query(UserSessionRow).filter(UserSessionRow.user_id == user_id).delete()
            session.query(ExternalIdentityRow).filter(ExternalIdentityRow.user_id == user_id).delete()
            session.query(UnreadWordRow).filter(UnreadWordRow.user_id == user_id).delete()
            session.query(LineageEdgeRow).filter(
                self.owned_by_fn(target_owner, LineageEdgeRow.user_id)
            ).delete()
            session.query(LineageNodeRow).filter(
                self.owned_by_fn(target_owner, LineageNodeRow.user_id)
            ).delete()
            session.query(UserPermissionGroupRow).filter(
                UserPermissionGroupRow.user_id == user_id
            ).delete()
            session.delete(row)
            session.commit()
            return True
