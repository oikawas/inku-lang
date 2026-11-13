"""A saved work's composition record, as the shared core reads it beside the work's DDL.

A read-and-draw work (言葉で描く) keeps its composition in its saving context
(``description_ddl.composition``): which thing each line of the DDL belongs to
(``things``) and the things the composition's answer names (``answer.things``).
The shared core titles an untitled DDL from these two (``chunk_moves.rs``).

This was the AI refinement's (``autonomous_refine.py``) until the author removed
it on 2026-11-13; the reading it does is kept for the thesis-handle work.
"""

from __future__ import annotations

from typing import Any


def composition_of(item: dict[str, Any]) -> dict[str, Any] | None:
    """A read-and-draw work's composition record as the core titles a DDL from it: each line's thing, and the things."""
    record = item.get("description_ddl")
    composition = record.get("composition") if isinstance(record, dict) else None
    if not isinstance(composition, dict):
        return None
    owners, things = composition.get("things"), (composition.get("answer") or {}).get("things")
    if isinstance(owners, list) and isinstance(things, list):
        return {"owners": owners, "things": things}
    return None
