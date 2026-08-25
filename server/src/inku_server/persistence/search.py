"""History search policy and query execution with explicit runtime dependencies."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy import func, or_, text

from .schema import HistoryRow


def _fts_match_query(search: str) -> str:
    return '"' + search.replace('"', '""') + '"'


# A whole render hash, with the version prefix (`rh3:`) or without it: a reader
# who trims the prefix off still means the same work. The prefix is matched
# loosely rather than spelled `rh3` so that a later version does not silently
# stop being searchable.
_WHOLE_RENDER_HASH = re.compile(r"(?:[a-z0-9]+:)?[0-9a-f]{64}", re.IGNORECASE)


def _is_render_hash_suffix_search(search: str) -> bool:
    """Text that can only be a render hash, and so is matched against its end.

    Two shapes arrive here. The four characters the UI prints on a work's chip,
    and the whole hash its copy button puts on the clipboard -- which is what a
    reader pastes back into the search box, and which used to reach the
    full-text path instead and find nothing.

    Both are matched as a suffix: that is what the short form is, and the long
    form is trivially one.
    """
    if len(search) == 4 and search.isascii() and search.isalnum():
        return True
    return bool(_WHOLE_RENDER_HASH.fullmatch(search))


def _history_search_clause(search: str):
    pattern = f"%{search}%"
    clauses = [
        HistoryRow.input.ilike(pattern),
        HistoryRow.ddl.ilike(pattern),
        HistoryRow.stage1_model.ilike(pattern),
        HistoryRow.stage2_model.ilike(pattern),
        HistoryRow.catalog_id.ilike(pattern),
    ]
    if _is_render_hash_suffix_search(search):
        clauses.append(HistoryRow.render_hash.ilike(f"%{search}"))
    return or_(*clauses)


def _use_history_fts(search: str, *, fts_enabled: bool, dialect_name: str) -> bool:
    return (
        fts_enabled
        and dialect_name == "sqlite"
        and len(search) >= 3
        and not _is_render_hash_suffix_search(search)
    )


@dataclass(frozen=True)
class HistorySearchService:
    """History listing behavior with host runtime dependencies supplied explicitly."""

    fts_enabled: bool
    dialect_name: str
    session_factory: Callable
    actor_of: Callable
    readable_by: Callable
    readable_sql: Callable
    rows_to_dicts_with_lineage: Callable

    def use_history_fts(self, search: str) -> bool:
        return _use_history_fts(
            search,
            fts_enabled=self.fts_enabled,
            dialect_name=self.dialect_name,
        )

    def list_items_with_fts(
        self,
        session,
        actor: dict,
        offset: int,
        limit: int,
        trashed: bool,
        search: str,
        starred: bool,
        for_revision: bool = False,
        for_share: bool = False,
    ) -> tuple[list[dict], int]:
        visible, visible_params = self.readable_sql(actor, "h.user_id", "h.id")
        params = {
            **visible_params,
            "trashed": 1 if trashed else 0,
            "match": _fts_match_query(search),
            "limit": limit,
            "offset": offset,
        }
        starred_clause = "AND h.starred = 1" if starred else ""
        # Both marks filter at once and independently: asking for starred and for
        # for_revision means both, not either.
        for_revision_clause = "AND h.for_revision = 1" if for_revision else ""
        # The third mark narrows the same way: AND, not OR. Asking for the bundle
        # asks for the works in it, not for the works in it plus one's own.
        for_share_clause = "AND h.for_share = 1" if for_share else ""
        total = session.execute(
            text(
                f"""
                SELECT count(h.id)
                FROM history h
                JOIN history_fts ON history_fts.rowid = h.rowid
                WHERE {visible}
                  AND h.trashed = :trashed
                  AND h.history_visibility = 'normal'
                  {starred_clause}
                  {for_revision_clause}
                  {for_share_clause}
                  AND history_fts MATCH :match
                """
            ),
            params,
        ).scalar() or 0
        ids = [
            row[0]
            for row in session.execute(
                text(
                    f"""
                    SELECT h.id
                    FROM history h
                    JOIN history_fts ON history_fts.rowid = h.rowid
                    WHERE {visible}
                      AND h.trashed = :trashed
                      AND h.history_visibility = 'normal'
                      {starred_clause}
                      {for_revision_clause}
                      {for_share_clause}
                      AND history_fts MATCH :match
                    ORDER BY h.at DESC
                    LIMIT :limit OFFSET :offset
                    """
                ),
                params,
            )
        ]
        if not ids:
            return [], int(total)
        order = {item_id: index for index, item_id in enumerate(ids)}
        rows = session.query(HistoryRow).filter(HistoryRow.id.in_(ids)).all()
        items = self.rows_to_dicts_with_lineage(session, rows, actor)
        return sorted(items, key=lambda item: order[item["id"]]), int(total)

    def list_items(
        self,
        user_id: str,
        offset: int = 0,
        limit: int = 10,
        trashed: bool = False,
        query_text: str = "",
        starred: bool = False,
        for_revision: bool = False,
        for_share: bool = False,
    ) -> tuple[list[dict], int]:
        actor = self.actor_of(user_id)
        with self.session_factory() as session:
            query = session.query(HistoryRow).filter(
                self.readable_by(actor, HistoryRow.user_id, HistoryRow.id),
                HistoryRow.trashed == (1 if trashed else 0),
                HistoryRow.history_visibility == "normal",
            )
            if starred:
                query = query.filter(HistoryRow.starred == 1)
            if for_revision:
                query = query.filter(HistoryRow.for_revision == 1)
            if for_share:
                query = query.filter(HistoryRow.for_share == 1)
            search = query_text.strip()
            if search and self.use_history_fts(search):
                return self.list_items_with_fts(
                    session,
                    actor,
                    offset,
                    limit,
                    trashed,
                    search,
                    starred,
                    for_revision,
                    for_share,
                )
            if search:
                query = query.filter(_history_search_clause(search))
            total: int = query.with_entities(func.count(HistoryRow.id)).scalar() or 0
            rows = (
                query.order_by(HistoryRow.at.desc(), HistoryRow.id.asc())
                .offset(offset)
                .limit(limit)
                .all()
            )
            return self.rows_to_dicts_with_lineage(session, rows, actor), total
