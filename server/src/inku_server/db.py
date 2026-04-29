"""DB layer — SQLite (default) or PostgreSQL via INKU_DB_URL.

  SQLite:     INKU_DB_URL=sqlite:///~/.local/share/inku/inku.db  (default)
  PostgreSQL: INKU_DB_URL=postgresql://user:pass@localhost/inku
"""
from __future__ import annotations

import json
import os
import secrets
import uuid
from hashlib import pbkdf2_hmac, sha256
from pathlib import Path

from sqlalchemy import BigInteger, Column, ForeignKey, Integer, String, Text, create_engine, func, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

_DEFAULT_DB = "sqlite:///" + str(Path.home() / ".local" / "share" / "inku" / "inku.db")
_DB_URL = os.getenv("INKU_DB_URL", _DEFAULT_DB)

_connect_args = {"check_same_thread": False} if _DB_URL.startswith("sqlite") else {}
engine = create_engine(_DB_URL, echo=False, future=True, connect_args=_connect_args)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


class Base(DeclarativeBase):
    pass


class HistoryRow(Base):
    __tablename__ = "history"

    id           = Column(String,     primary_key=True)
    user_id      = Column(String,     ForeignKey("user_accounts.id"), nullable=True, index=True)
    at           = Column(BigInteger, nullable=False, index=True)
    input        = Column(Text,       nullable=False, default="")
    ddl          = Column(Text,       nullable=True)
    score        = Column(Text,       nullable=False, default="{}")
    svg          = Column(Text,       nullable=False, default="")
    output_path  = Column(Text,       nullable=True)
    elapsed_ms   = Column(Integer,    nullable=False, default=0)
    stage1_model = Column(String,     nullable=True)
    stage2_model = Column(String,     nullable=True)
    tokens_in    = Column(Integer,    nullable=True)
    tokens_out   = Column(Integer,    nullable=True)
    catalog_id   = Column(String,     nullable=True)
    trashed      = Column(Integer,    nullable=False, default=0)


class UserGroupRow(Base):
    __tablename__ = "user_groups"

    id   = Column(String, primary_key=True)
    name = Column(String, nullable=False, unique=True)
    at   = Column(BigInteger, nullable=False, index=True)


class UserAccountRow(Base):
    __tablename__ = "user_accounts"

    id            = Column(String, primary_key=True)
    username      = Column(String, nullable=False, unique=True, index=True)
    email         = Column(String, nullable=False, unique=True, index=True)
    password_hash = Column(Text, nullable=False)
    role          = Column(String, nullable=False, index=True)
    group_id      = Column(String, ForeignKey("user_groups.id"), nullable=True, index=True)
    at            = Column(BigInteger, nullable=False, index=True)


class UserSessionRow(Base):
    __tablename__ = "user_sessions"

    token_hash = Column(String, primary_key=True)
    user_id    = Column(String, ForeignKey("user_accounts.id"), nullable=False, index=True)
    at         = Column(BigInteger, nullable=False, index=True)


USER_ROLES = {"admin", "group_lead", "user"}
ROLE_LABELS = {
    "admin": "管理者",
    "group_lead": "グループリード",
    "user": "ユーザー",
}
_UNSET = object()


def init_db() -> None:
    if _DB_URL.startswith("sqlite:///"):
        db_path = Path(_DB_URL[len("sqlite:///"):]).expanduser()
        db_path.parent.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(engine)
    _migrate_columns()
    _ensure_default_user_group()
    _ensure_bootstrap_admin()
    _assign_unowned_history_to_admin()


def _migrate_columns() -> None:
    with engine.connect() as conn:
        try:
            conn.execute(text("ALTER TABLE history ADD COLUMN user_id VARCHAR"))
            conn.commit()
        except Exception:  # noqa: BLE001
            pass
        try:
            conn.execute(text("ALTER TABLE history ADD COLUMN catalog_id VARCHAR"))
            conn.commit()
        except Exception:  # noqa: BLE001
            pass
        try:
            conn.execute(text("ALTER TABLE history ADD COLUMN trashed INTEGER NOT NULL DEFAULT 0"))
            conn.commit()
        except Exception:  # noqa: BLE001
            pass
        try:
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_history_user_id ON history (user_id)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_history_user_trashed_at ON history (user_id, trashed, at)"))
            conn.commit()
        except Exception:  # noqa: BLE001
            pass


def _now_ms() -> int:
    import time

    return int(time.time() * 1000)


def _hash_password(password: str) -> str:
    if not password:
        raise ValueError("password is required")
    salt = secrets.token_bytes(16)
    iterations = 310_000
    digest = pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return f"pbkdf2_sha256${iterations}${salt.hex()}${digest.hex()}"


def _hash_token(token: str) -> str:
    return sha256(token.encode("utf-8")).hexdigest()


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


def _ensure_default_user_group() -> None:
    with SessionLocal() as session:
        exists = session.query(UserGroupRow).first()
        if exists:
            return
        session.add(UserGroupRow(id=str(uuid.uuid4()), name="default", at=_now_ms()))
        session.commit()


def _ensure_bootstrap_admin() -> None:
    with SessionLocal() as session:
        if session.query(UserAccountRow).first():
            return
        group = session.query(UserGroupRow).order_by(UserGroupRow.name.asc()).first()
        password = os.getenv("INKU_BOOTSTRAP_ADMIN_PASSWORD", "inku-admin")
        session.add(
            UserAccountRow(
                id=str(uuid.uuid4()),
                username=os.getenv("INKU_BOOTSTRAP_ADMIN_USERNAME", "admin"),
                email=os.getenv("INKU_BOOTSTRAP_ADMIN_EMAIL", "admin@local"),
                password_hash=_hash_password(password),
                role="admin",
                group_id=group.id if group else None,
                at=_now_ms(),
            )
        )
        session.commit()


def _history_owner_user_id() -> str | None:
    with SessionLocal() as session:
        admin = session.query(UserAccountRow).filter(UserAccountRow.role == "admin").order_by(UserAccountRow.at.asc()).first()
        if admin:
            return admin.id
        user = session.query(UserAccountRow).order_by(UserAccountRow.at.asc()).first()
        return user.id if user else None


def admin_history_owner_id() -> str | None:
    return _history_owner_user_id()


def _assign_unowned_history_to_admin() -> None:
    owner_id = _history_owner_user_id()
    if not owner_id:
        return
    with SessionLocal() as session:
        session.query(HistoryRow).filter(HistoryRow.user_id.is_(None)).update(
            {HistoryRow.user_id: owner_id},
            synchronize_session=False,
        )
        session.commit()


def _row_to_dict(row: HistoryRow) -> dict:
    return {
        "id":           row.id,
        "user_id":      row.user_id,
        "at":           row.at,
        "input":        row.input,
        "ddl":          row.ddl,
        "score":        json.loads(row.score) if row.score else {},
        "svg":          row.svg,
        "output_path":  row.output_path,
        "elapsed_ms":   row.elapsed_ms,
        "stage1_model": row.stage1_model,
        "stage2_model": row.stage2_model,
        "tokens_in":    row.tokens_in,
        "tokens_out":   row.tokens_out,
        "catalog_id":   row.catalog_id,
        "trashed":      bool(row.trashed),
    }


def _group_to_dict(row: UserGroupRow) -> dict:
    return {"id": row.id, "name": row.name, "at": row.at}


def _user_to_dict(row: UserAccountRow, group_name: str | None = None) -> dict:
    return {
        "id": row.id,
        "username": row.username,
        "email": row.email,
        "role": row.role,
        "role_label": ROLE_LABELS.get(row.role, row.role),
        "group_id": row.group_id,
        "group_name": group_name,
        "at": row.at,
    }


def add_item(item: dict) -> dict:
    row = HistoryRow(
        id=item["id"],
        user_id=item["user_id"],
        at=item["at"],
        input=item.get("input", ""),
        ddl=item.get("ddl"),
        score=json.dumps(item.get("score", {})),
        svg=item.get("svg", ""),
        output_path=item.get("output_path"),
        elapsed_ms=item.get("elapsed_ms", 0),
        stage1_model=item.get("stage1_model"),
        stage2_model=item.get("stage2_model"),
        tokens_in=item.get("tokens_in"),
        tokens_out=item.get("tokens_out"),
        catalog_id=item.get("catalog_id"),
        trashed=0,
    )
    with SessionLocal() as session:
        session.add(row)
        session.commit()
        session.refresh(row)
        return _row_to_dict(row)


def list_user_groups() -> list[dict]:
    with SessionLocal() as session:
        rows = session.query(UserGroupRow).order_by(UserGroupRow.name.asc()).all()
        return [_group_to_dict(row) for row in rows]


def add_user_group(name: str) -> dict:
    name = name.strip()
    if not name:
        raise ValueError("group name is required")
    row = UserGroupRow(id=str(uuid.uuid4()), name=name, at=_now_ms())
    with SessionLocal() as session:
        session.add(row)
        session.commit()
        session.refresh(row)
        return _group_to_dict(row)


def delete_user_group(group_id: str) -> bool:
    with SessionLocal() as session:
        if session.query(UserAccountRow).filter(UserAccountRow.group_id == group_id).first():
            raise ValueError("group has users")
        row = session.get(UserGroupRow, group_id)
        if not row:
            return False
        session.delete(row)
        session.commit()
        return True


def list_users() -> list[dict]:
    with SessionLocal() as session:
        rows = (
            session.query(UserAccountRow, UserGroupRow.name)
            .outerjoin(UserGroupRow, UserAccountRow.group_id == UserGroupRow.id)
            .order_by(UserAccountRow.username.asc())
            .all()
        )
        return [_user_to_dict(row, group_name) for row, group_name in rows]


def get_user(user_id: str) -> dict | None:
    with SessionLocal() as session:
        row = session.get(UserAccountRow, user_id)
        if not row:
            return None
        group_name = session.get(UserGroupRow, row.group_id).name if row.group_id else None
        return _user_to_dict(row, group_name)


def authenticate_user(username: str, password: str) -> dict | None:
    with SessionLocal() as session:
        row = session.query(UserAccountRow).filter(UserAccountRow.username == username.strip()).first()
        if not row or not verify_password(password, row.password_hash):
            return None
        group_name = session.get(UserGroupRow, row.group_id).name if row.group_id else None
        return _user_to_dict(row, group_name)


def create_session(user_id: str) -> str:
    token = secrets.token_urlsafe(32)
    with SessionLocal() as session:
        if not session.get(UserAccountRow, user_id):
            raise ValueError("user not found")
        session.add(UserSessionRow(token_hash=_hash_token(token), user_id=user_id, at=_now_ms()))
        session.commit()
    return token


def get_session_user(token: str) -> dict | None:
    with SessionLocal() as session:
        session_row = session.get(UserSessionRow, _hash_token(token))
        if not session_row:
            return None
        row = session.get(UserAccountRow, session_row.user_id)
        if not row:
            return None
        group_name = session.get(UserGroupRow, row.group_id).name if row.group_id else None
        return _user_to_dict(row, group_name)


def delete_session(token: str) -> bool:
    with SessionLocal() as session:
        row = session.get(UserSessionRow, _hash_token(token))
        if not row:
            return False
        session.delete(row)
        session.commit()
        return True


def list_users_for_actor(actor: dict) -> list[dict]:
    if actor["role"] == "admin":
        return list_users()
    if actor["role"] == "group_lead" and actor.get("group_id"):
        with SessionLocal() as session:
            rows = (
                session.query(UserAccountRow, UserGroupRow.name)
                .outerjoin(UserGroupRow, UserAccountRow.group_id == UserGroupRow.id)
                .filter(UserAccountRow.group_id == actor["group_id"])
                .order_by(UserAccountRow.username.asc())
                .all()
            )
            return [_user_to_dict(row, group_name) for row, group_name in rows]
    return []


def add_user(username: str, email: str, password: str, role: str, group_id: str | None) -> dict:
    username = username.strip()
    email = email.strip()
    if not username:
        raise ValueError("username is required")
    if not email:
        raise ValueError("email is required")
    if role not in USER_ROLES:
        raise ValueError("invalid role")
    row = UserAccountRow(
        id=str(uuid.uuid4()),
        username=username,
        email=email,
        password_hash=_hash_password(password),
        role=role,
        group_id=group_id,
        at=_now_ms(),
    )
    with SessionLocal() as session:
        if group_id and not session.get(UserGroupRow, group_id):
            raise ValueError("group not found")
        session.add(row)
        session.commit()
        session.refresh(row)
        group_name = session.get(UserGroupRow, row.group_id).name if row.group_id else None
        return _user_to_dict(row, group_name)


def update_user(
    user_id: str,
    *,
    username: str | None = None,
    email: str | None = None,
    password: str | None = None,
    role: str | None = None,
    group_id: str | None | object = _UNSET,
) -> dict | None:
    with SessionLocal() as session:
        row = session.get(UserAccountRow, user_id)
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
            row.password_hash = _hash_password(password)
        if role is not None:
            if role not in USER_ROLES:
                raise ValueError("invalid role")
            row.role = role
        if group_id is not _UNSET:
            group_id = group_id if isinstance(group_id, str) else None
            if group_id and not session.get(UserGroupRow, group_id):
                raise ValueError("group not found")
            row.group_id = group_id or None
        session.commit()
        session.refresh(row)
        group_name = session.get(UserGroupRow, row.group_id).name if row.group_id else None
        return _user_to_dict(row, group_name)


def delete_user(user_id: str) -> bool:
    with SessionLocal() as session:
        row = session.get(UserAccountRow, user_id)
        if not row:
            return False
        if session.query(HistoryRow).filter(HistoryRow.user_id == user_id).first():
            raise ValueError("user has history")
        session.delete(row)
        session.commit()
        return True


def list_items(user_id: str, offset: int = 0, limit: int = 10, trashed: bool = False) -> tuple[list[dict], int]:
    with SessionLocal() as session:
        query = session.query(HistoryRow).filter(
            HistoryRow.user_id == user_id,
            HistoryRow.trashed == (1 if trashed else 0),
        )
        total: int = query.with_entities(func.count(HistoryRow.id)).scalar() or 0
        rows = (
            query
            .order_by(HistoryRow.at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )
        return [_row_to_dict(r) for r in rows], total


def delete_all(user_id: str) -> None:
    with SessionLocal() as session:
        session.query(HistoryRow).filter(HistoryRow.user_id == user_id).delete()
        session.commit()


def trash_items(user_id: str, ids: list[str]) -> int:
    if not ids:
        return 0
    with SessionLocal() as session:
        count = (
            session.query(HistoryRow)
            .filter(HistoryRow.user_id == user_id, HistoryRow.id.in_(ids), HistoryRow.trashed == 0)
            .update({HistoryRow.trashed: 1}, synchronize_session=False)
        )
        session.commit()
        return count


def restore_items(user_id: str, ids: list[str]) -> int:
    if not ids:
        return 0
    with SessionLocal() as session:
        count = (
            session.query(HistoryRow)
            .filter(HistoryRow.user_id == user_id, HistoryRow.id.in_(ids), HistoryRow.trashed == 1)
            .update({HistoryRow.trashed: 0}, synchronize_session=False)
        )
        session.commit()
        return count


def delete_items(user_id: str, ids: list[str]) -> int:
    if not ids:
        return 0
    with SessionLocal() as session:
        count = session.query(HistoryRow).filter(
            HistoryRow.user_id == user_id,
            HistoryRow.id.in_(ids),
        ).delete(synchronize_session=False)
        session.commit()
        return count
