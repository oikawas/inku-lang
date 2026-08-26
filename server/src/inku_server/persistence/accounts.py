"""User-account read and authentication persistence owner."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

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
