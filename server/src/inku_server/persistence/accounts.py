"""User-account read and authentication persistence owner."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .access import has_permission_group
from .schema import UserAccountRow, UserGroupRow


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
