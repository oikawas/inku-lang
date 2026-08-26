"""Persistence owner for user groups."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .schema import HistoryAclRow, PermissionGroupRow, UserAccountRow, UserGroupRow, UserPermissionGroupRow


PERMISSION_GROUPS = ("admins", "leaders", "users")
PERMISSION_GROUP_LABELS = {
    "admins": "管理者",
    "leaders": "リーダー",
    "users": "ユーザー",
}
ROLE_MIRROR_BY_GROUP = {"admins": "admin", "leaders": "group_lead"}
ELEVATED_PERMISSION_GROUPS = ("admins", "leaders")
LEGACY_ROLE_TO_PERMISSION_GROUP = {
    "admin": "admins",
    "group_lead": "leaders",
    "user": "users",
}


def derived_role(names) -> str:
    """The legacy role column's value, derived from permission groups."""
    for group, role in ROLE_MIRROR_BY_GROUP.items():
        if group in names:
            return role
    return "user"


def normalize_permission_groups(names) -> list[str]:
    """Requested names, deduplicated and ordered by the fixed vocabulary."""
    if isinstance(names, str):
        raise ValueError("permission_groups must be a list")
    requested = set(names or ())
    unknown = requested - set(PERMISSION_GROUPS)
    if unknown:
        raise ValueError(f"invalid permission group: {sorted(unknown)[0]}")
    if not requested:
        raise ValueError("at least one permission group is required")
    return [name for name in PERMISSION_GROUPS if name in requested]


@dataclass(frozen=True)
class PermissionGroupMembershipStore:
    uuid_fn: Callable[[], object]
    now_ms_fn: Callable[[], int]

    def group_ids(self, session) -> dict[str, str]:
        return {row.name: row.id for row in session.query(PermissionGroupRow).all()}

    def groups_of(self, session, user_id: str) -> list[str]:
        held = {name for (name,) in session.query(PermissionGroupRow.name).join(UserPermissionGroupRow, UserPermissionGroupRow.permission_group_id == PermissionGroupRow.id).filter(UserPermissionGroupRow.user_id == user_id).all()}
        return [name for name in PERMISSION_GROUPS if name in held]

    def set_groups(self, session, row: UserAccountRow, names) -> list[str]:
        wanted = normalize_permission_groups(names)
        by_name = self.group_ids(session)
        missing = [name for name in wanted if name not in by_name]
        if missing:
            raise ValueError(f"permission group not found: {missing[0]}")
        session.query(UserPermissionGroupRow).filter(UserPermissionGroupRow.user_id == row.id).delete(synchronize_session=False)
        for name in wanted:
            session.add(UserPermissionGroupRow(id=str(self.uuid_fn()), user_id=row.id, permission_group_id=by_name[name], at=self.now_ms_fn()))
        row.role = derived_role(wanted)
        return wanted

    def holds_no_elevated_group(self, session):
        elevated = session.query(UserPermissionGroupRow.user_id).join(PermissionGroupRow, PermissionGroupRow.id == UserPermissionGroupRow.permission_group_id).filter(PermissionGroupRow.name.in_(ELEVATED_PERMISSION_GROUPS))
        return ~UserAccountRow.id.in_(elevated)


def group_to_dict(row: UserGroupRow) -> dict:
    return {"id": row.id, "name": row.name, "at": row.at}


@dataclass(frozen=True)
class DefaultUserGroupSeeder:
    session_factory: Callable[[], Any]
    uuid_fn: Callable[[], object]
    now_ms_fn: Callable[[], int]

    def ensure(self, session=None) -> None:
        if session is not None:
            self._ensure_in_session(session, owns_session=False)
            return
        with self.session_factory() as active_session:
            self._ensure_in_session(active_session, owns_session=True)

    def _ensure_in_session(self, session, *, owns_session: bool) -> None:
        if session.query(UserGroupRow).first():
            return
        session.add(UserGroupRow(id=str(self.uuid_fn()), name="default", at=self.now_ms_fn()))
        if owns_session:
            session.commit()
        else:
            session.flush()


@dataclass(frozen=True)
class PermissionGroupSeeder:
    session_factory: Callable[[], Any]
    uuid_fn: Callable[[], object]
    now_ms_fn: Callable[[], int]

    def ensure(self, session=None) -> None:
        if session is not None:
            self._ensure_in_session(session, owns_session=False)
            return
        with self.session_factory() as active_session:
            self._ensure_in_session(active_session, owns_session=True)

    def _ensure_in_session(self, session, *, owns_session: bool) -> None:
        existing = {row.name for row in session.query(PermissionGroupRow).all()}
        added = False
        for name in PERMISSION_GROUPS:
            if name in existing:
                continue
            session.add(PermissionGroupRow(id=str(self.uuid_fn()), name=name, at=self.now_ms_fn()))
            added = True
        if not added:
            return
        if owns_session:
            session.commit()
        else:
            session.flush()


@dataclass(frozen=True)
class LegacyRoleMembershipMigrator:
    session_factory: Callable[[], Any]
    uuid_fn: Callable[[], object]
    now_ms_fn: Callable[[], int]

    def migrate(self, session=None) -> None:
        if session is not None:
            self._migrate_in_session(session, owns_session=False)
            return
        with self.session_factory() as active_session:
            self._migrate_in_session(active_session, owns_session=True)

    def _migrate_in_session(self, session, *, owns_session: bool) -> None:
        by_name = PermissionGroupMembershipStore(self.uuid_fn, self.now_ms_fn).group_ids(session)
        if not by_name:
            return
        assigned = {
            user_id
            for (user_id,) in session.query(UserPermissionGroupRow.user_id).distinct().all()
        }
        added = False
        for row in session.query(UserAccountRow).all():
            if row.id in assigned:
                continue
            name = LEGACY_ROLE_TO_PERMISSION_GROUP.get(row.role, "users")
            session.add(
                UserPermissionGroupRow(
                    id=str(self.uuid_fn()),
                    user_id=row.id,
                    permission_group_id=by_name[name],
                    at=self.now_ms_fn(),
                )
            )
            added = True
        if not added:
            return
        if owns_session:
            session.commit()
        else:
            session.flush()


@dataclass(frozen=True)
class UserGroupStore:
    session_factory: Callable[[], Any]
    uuid_fn: Callable[[], object]
    now_ms_fn: Callable[[], int]

    def list_user_groups(self) -> list[dict]:
        with self.session_factory() as session:
            rows = session.query(UserGroupRow).order_by(UserGroupRow.name.asc()).all()
            return [group_to_dict(row) for row in rows]

    def add_user_group(self, name: str) -> dict:
        name = name.strip()
        if not name:
            raise ValueError("group name is required")
        row = UserGroupRow(id=str(self.uuid_fn()), name=name, at=self.now_ms_fn())
        with self.session_factory() as session:
            session.add(row)
            session.commit()
            session.refresh(row)
            return group_to_dict(row)

    def update_user_group(self, group_id: str, name: str) -> dict | None:
        name = name.strip()
        if not name:
            raise ValueError("group name is required")
        with self.session_factory() as session:
            row = session.get(UserGroupRow, group_id)
            if not row:
                return None
            row.name = name
            row.at = self.now_ms_fn()
            session.commit()
            session.refresh(row)
            return group_to_dict(row)

    def delete_user_group(self, group_id: str) -> bool:
        with self.session_factory() as session:
            if session.query(UserAccountRow).filter(UserAccountRow.group_id == group_id).first():
                raise ValueError("group has users")
            row = session.get(UserGroupRow, group_id)
            if not row:
                return False
            # Grants naming this organisation outlive it otherwise, and a later group
            # created with the same id would inherit them.
            session.query(HistoryAclRow).filter(
                HistoryAclRow.subject_type == "org_group", HistoryAclRow.subject_id == group_id
            ).delete(synchronize_session=False)
            session.delete(row)
            session.commit()
            return True
