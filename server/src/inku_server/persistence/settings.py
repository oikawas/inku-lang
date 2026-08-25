"""Persistence-owned storage for generic application settings."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Callable

from sqlalchemy.orm import Session

from .schema import AppSettingRow


@dataclass(frozen=True)
class AppSettingsStore:
    """Read and write JSON object settings through explicit runtime dependencies."""

    session_factory: Callable[[], Session]
    now_ms: Callable[[], int]

    def read(self, key: str) -> dict | None:
        with self.session_factory() as session:
            row = session.get(AppSettingRow, key)
            if not row:
                return None
            try:
                value = json.loads(row.value or "{}")
            except json.JSONDecodeError:
                return None
            return value if isinstance(value, dict) else None

    def write(self, key: str, value: dict) -> dict:
        with self.session_factory() as session:
            row = session.get(AppSettingRow, key)
            if row:
                row.value = json.dumps(value, ensure_ascii=False)
                row.at = self.now_ms()
            else:
                row = AppSettingRow(
                    key=key,
                    value=json.dumps(value, ensure_ascii=False),
                    at=self.now_ms(),
                )
                session.add(row)
            session.commit()
            return value
