"""Persistence owner for authentication session lifecycle."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from hashlib import sha256

from .schema import UserAccountRow, UserGroupRow, UserSessionRow


def hash_token(token: str) -> str:
    return sha256(token.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class SessionStore:
    """Create, resolve, expire, and remove authentication sessions."""

    session_factory: Callable[[], object]
    token_urlsafe_fn: Callable[[int], str]
    hash_token_fn: Callable[[str], str]
    now_ms_fn: Callable[[], int]
    max_age_seconds: int
    user_to_dict_fn: Callable[[UserAccountRow, str | None], dict]

    def create_session(self, user_id: str) -> str:
        token = self.token_urlsafe_fn(32)
        with self.session_factory() as session:
            if not session.get(UserAccountRow, user_id):
                raise ValueError("user not found")
            self.delete_expired_sessions(session)
            session.add(UserSessionRow(
                token_hash=self.hash_token_fn(token), user_id=user_id, at=self.now_ms_fn(),
            ))
            session.commit()
        return token

    def session_expiry_cutoff_ms(self, now_ms: int | None = None) -> int | None:
        if self.max_age_seconds <= 0:
            return None
        now = self.now_ms_fn() if now_ms is None else now_ms
        return now - (self.max_age_seconds * 1000)

    def delete_expired_sessions(self, session) -> int:
        cutoff = self.session_expiry_cutoff_ms()
        if cutoff is None:
            return 0
        return (
            session.query(UserSessionRow)
            .filter(UserSessionRow.at < cutoff)
            .delete(synchronize_session=False)
        )

    def get_session_user(self, token: str) -> dict | None:
        with self.session_factory() as session:
            session_row = session.get(UserSessionRow, self.hash_token_fn(token))
            if not session_row:
                return None
            cutoff = self.session_expiry_cutoff_ms()
            if cutoff is not None and session_row.at < cutoff:
                session.delete(session_row)
                session.commit()
                return None
            row = session.get(UserAccountRow, session_row.user_id)
            if not row:
                session.delete(session_row)
                session.commit()
                return None
            group_name = session.get(UserGroupRow, row.group_id).name if row.group_id else None
            return self.user_to_dict_fn(row, group_name)

    def delete_session(self, token: str) -> bool:
        with self.session_factory() as session:
            row = session.get(UserSessionRow, self.hash_token_fn(token))
            if not row:
                return False
            session.delete(row)
            session.commit()
            return True
