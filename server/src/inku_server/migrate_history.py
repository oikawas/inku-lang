"""Migrate history.json → SQLite/PostgreSQL DB.

Usage:
    uv run python -m inku_server.migrate_history [--json PATH]
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from . import db as _db
from .db import SessionLocal, HistoryRow


def _output_prefix_for(item_id: str, at_ms: int, output_dir: Path) -> Path:
    dt = datetime.fromtimestamp(at_ms / 1000, tz=timezone.utc).astimezone()
    date_dir = output_dir / dt.strftime("%Y-%m-%d")
    return date_dir / (dt.strftime("%Y%m%d_%H%M%S") + "_" + item_id[:8])


def migrate(json_path: Path, output_dir: Path) -> None:
    _db.init_db()

    items = json.loads(json_path.read_text(encoding="utf-8"))
    print(f"source: {len(items)} items")

    with SessionLocal() as session:
        existing_ids: set[str] = {r.id for r in session.query(HistoryRow.id).all()}

    skipped = inserted = 0
    with SessionLocal() as session:
        for item in items:
            item_id = item.get("id", "")
            if item_id in existing_ids:
                skipped += 1
                continue

            at_ms = item.get("at", 0)
            prefix = _output_prefix_for(item_id, at_ms, output_dir)

            row = HistoryRow(
                id=item_id,
                at=at_ms,
                input=item.get("input", ""),
                ddl=item.get("ddl"),
                score=json.dumps(item.get("score", {})),
                svg=item.get("svg", ""),
                output_path=str(prefix),
                elapsed_ms=item.get("elapsed_ms", 0),
                stage1_model=item.get("stage1_model"),
                stage2_model=item.get("stage2_model"),
                tokens_in=item.get("tokens_in"),
                tokens_out=item.get("tokens_out"),
            )
            session.add(row)
            inserted += 1
            if inserted % 20 == 0:
                session.flush()
                print(f"  inserted {inserted}...", flush=True)

        session.commit()

    print(f"done: inserted={inserted} skipped={skipped}")


def main() -> None:
    default_json = Path.home() / ".local" / "share" / "inku" / "history.json"
    default_outputs = Path.home() / ".local" / "share" / "inku" / "outputs"

    parser = argparse.ArgumentParser(description="Migrate history.json to DB")
    parser.add_argument("--json", type=Path, default=default_json, help="Path to history.json")
    parser.add_argument("--outputs", type=Path, default=default_outputs, help="Output files base dir")
    args = parser.parse_args()

    if not args.json.exists():
        print(f"history.json not found: {args.json}", file=sys.stderr)
        sys.exit(1)

    migrate(args.json, args.outputs)


if __name__ == "__main__":
    main()
