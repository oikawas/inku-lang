"""Persistence owner for external identity linkage and resolution."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from .schema import ExternalIdentityRow, UserAccountRow, UserGroupRow


@dataclass(frozen=True)
class ExternalIdentityStore:
    """Link normalized provider subjects and resolve their existing accounts."""

    session_factory: Callable[[], object]
    uuid_fn: Callable[[], object]
    now_ms_fn: Callable[[], int]
    user_to_dict_fn: Callable[[UserAccountRow, str | None], dict]

    def link_external_identity(
        self,
        user_id: str,
        *,
        provider: str,
        subject: str,
        email: str | None = None,
    ) -> dict:
        clean_provider = provider.strip().lower()
        clean_subject = subject.strip()
        if not clean_provider or len(clean_provider) > 64:
            raise ValueError("invalid identity provider")
        if not clean_subject or len(clean_subject) > 512:
            raise ValueError("invalid external subject")
        with self.session_factory() as session:
            if session.get(UserAccountRow, user_id) is None:
                raise ValueError("user not found")
            row = ExternalIdentityRow(
                id=str(self.uuid_fn()),
                user_id=user_id,
                provider=clean_provider,
                subject=clean_subject,
                email=(email or "").strip() or None,
                at=self.now_ms_fn(),
            )
            session.add(row)
            session.commit()
            return {
                "id": row.id,
                "user_id": row.user_id,
                "provider": row.provider,
                "subject": row.subject,
                "email": row.email,
                "at": row.at,
            }

    def get_user_by_external_identity(self, provider: str, subject: str) -> dict | None:
        with self.session_factory() as session:
            identity = session.query(ExternalIdentityRow).filter(
                ExternalIdentityRow.provider == provider.strip().lower(),
                ExternalIdentityRow.subject == subject.strip(),
            ).first()
            if identity is None:
                return None
            row = session.get(UserAccountRow, identity.user_id)
            if row is None:
                return None
            group_name = session.get(UserGroupRow, row.group_id).name if row.group_id else None
            return self.user_to_dict_fn(row, group_name)
