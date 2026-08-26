"""Persistence owner for user groups."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .schema import HistoryAclRow, UserAccountRow, UserGroupRow


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


def group_to_dict(row: UserGroupRow) -> dict:
    return {"id": row.id, "name": row.name, "at": row.at}


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
