"""The works whose descriptions may lend a sentence to a juxtaposition."""

from __future__ import annotations

from . import access
from .description_lock import locked_history_ids
from .schema import HistoryRow

_NOT_A_SOURCE_LABELS = frozenset({"DDL", "[demo]"})
_LOCK_BATCH = 500


def owned_description_sources(session, actor: dict) -> list[tuple[str, str]]:
    """(id, description) of the actor's own works that may lend a sentence.

    Only works the actor owns: a shared work or another person's is never read.
    Left out are works in the trash, works kept only in a lineage, DDL and demo
    works, works whose comment says `test data`, works with no description, and
    works held by their DDL. The description still carries its labels.
    """
    rows = session.query(
        HistoryRow.id, HistoryRow.source_text, HistoryRow.input, HistoryRow.display_label, HistoryRow.note,
    ).filter(
        access._owned_by(actor, HistoryRow.user_id),
        HistoryRow.trashed == 0,
        HistoryRow.history_visibility == "normal",
    ).all()
    kept = []
    for row in rows:
        if (row.display_label or "").strip() in _NOT_A_SOURCE_LABELS or "test data" in (row.note or "").lower():
            continue
        text = row.source_text if row.source_text is not None else row.input
        if (text or "").strip():
            kept.append((row.id, text))
    locked: set[str] = set()
    for start in range(0, len(kept), _LOCK_BATCH):
        locked |= locked_history_ids(session, [history_id for history_id, _ in kept[start:start + _LOCK_BATCH]])
    return [(history_id, text) for history_id, text in kept if history_id not in locked]
