"""Persistence owner for unread-word feedback recording and aggregation."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from .schema import UnreadWordRow


UNREAD_WORD_UPSERT_BATCH_SIZE = 100


@dataclass(frozen=True)
class UnreadWordStore:
    """Store user-scoped unread words and produce the existing aggregate view."""

    session_factory: Callable[[], object]

    def record_unread_words(
        self,
        user_id: str,
        words: list[str],
        context: str,
        *,
        at: int,
    ) -> None:
        clean_words = sorted({word.strip()[:120] for word in words if word and word.strip()})
        clean_context = context.strip()[:1000]
        if not clean_words:
            return
        with self.session_factory() as session:
            # Conflict handling must happen under SQLite's writer lock. A preceding
            # SELECT lets concurrent requests both observe absence and makes one
            # INSERT fail. Seven values per row keep each batch below SQLite's
            # conservative variable limit while preserving one transaction.
            for start in range(0, len(clean_words), UNREAD_WORD_UPSERT_BATCH_SIZE):
                values = [
                    {
                        "id": str(uuid.uuid4()),
                        "user_id": user_id,
                        "word": word,
                        "context": clean_context,
                        "frequency": 1,
                        "first_at": at,
                        "last_at": at,
                    }
                    for word in clean_words[start : start + UNREAD_WORD_UPSERT_BATCH_SIZE]
                ]
                statement = sqlite_insert(UnreadWordRow).values(values)
                session.execute(
                    statement.on_conflict_do_update(
                        index_elements=[
                            UnreadWordRow.user_id,
                            UnreadWordRow.word,
                            UnreadWordRow.context,
                        ],
                        set_={
                            "frequency": UnreadWordRow.frequency + 1,
                            "last_at": statement.excluded.last_at,
                        },
                    )
                )
            session.commit()

    def list_unread_words(
        self,
        user_id: str | None = None,
        *,
        limit: int = 100,
    ) -> list[dict]:
        with self.session_factory() as session:
            query = session.query(UnreadWordRow)
            if user_id is not None:
                query = query.filter(UnreadWordRow.user_id == user_id)
            rows = query.all()
            aggregate: dict[str, dict] = {}
            users_by_word: dict[str, set[str]] = {}
            for row in rows:
                item = aggregate.setdefault(row.word, {
                    "word": row.word,
                    "frequency": 0,
                    "first_at": row.first_at,
                    "last_at": row.last_at,
                    "contexts": [],
                })
                item["frequency"] += row.frequency
                item["first_at"] = min(item["first_at"], row.first_at)
                item["last_at"] = max(item["last_at"], row.last_at)
                if row.context and row.context not in item["contexts"] and len(item["contexts"]) < 3:
                    item["contexts"].append(row.context)
                users_by_word.setdefault(row.word, set()).add(row.user_id)
            items = sorted(
                aggregate.values(),
                key=lambda item: (-item["frequency"], -item["last_at"], item["word"]),
            )
            for item in items:
                item["context"] = item["contexts"][0] if item["contexts"] else ""
                if user_id is None:
                    item["user_count"] = len(users_by_word[item["word"]])
            return items[:limit]
