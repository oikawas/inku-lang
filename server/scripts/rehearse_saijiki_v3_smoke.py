"""Fork and draw one migrated saved work inside an isolated rehearsal copy."""

from __future__ import annotations

import argparse
from collections import Counter
import json
import os
import sqlite3
import time
from pathlib import Path

from count_saijiki_v1_migration import _resolve_guarded_database


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--database", type=Path, required=True)
    args = parser.parse_args()
    root = args.run_root.resolve(strict=True)
    database = _resolve_guarded_database(root, args.database)
    os.environ.update(INKU_DB_URL=f"sqlite:///{database}", INKU_THUMBS_DB_URL="sqlite:///:memory:",
                      INKU_DB_BACKUP_SCHEDULER="0", INKU_PLUGIN_PACKAGE_DIR=str(root / "plugins"))
    from inku_server.api_core import common, rendering, thumbnails
    from inku_server.pipeline_api import LinkedHistoryForkBody
    from inku_server.pipeline_runtime import get_service, shutdown

    # This check never sends a provider request, including when the chosen
    # text has a completion gap. Artifact workers are not part of the check.
    def no_provider(_action):
        raise RuntimeError("provider_disabled_for_rehearsal")

    common._model_offered_to = lambda *_args, **_kwargs: True
    rendering._submit_history_artifact_save = lambda *_args, **_kwargs: None
    thumbnails.submit_thumbnail_build = lambda *_args, **_kwargs: None
    service = get_service()
    service.provider_for = lambda _owner: no_provider
    service.provider_with_context = lambda _owner, _context: no_provider
    with sqlite3.connect(f"file:{database}?mode=ro", uri=True) as connection:
        candidates = connection.execute(
            "SELECT h.user_id,h.id,h.ddl FROM history h JOIN pipeline_history_links l "
            "ON l.owner_id=h.user_id AND l.history_id=h.id "
            "WHERE h.ddl IS NOT NULL AND length(h.ddl) BETWEEN 1 AND 400 "
            "ORDER BY length(h.ddl) LIMIT 20"
        ).fetchall()
    reasons: Counter[str] = Counter()
    try:
        for owner, history_id, source in candidates:
            try:
                body = LinkedHistoryForkBody(kind="direct_ddl", text=source + "\n黒い円を置く。",
                                             options={"stage1_model": "chatgpt:gpt-6-luna", "render_seed": 1})
                view = service.fork_linked_history(owner, history_id, body)
                execution = view["execution_id"]
                deadline = time.monotonic() + 30
                while time.monotonic() < deadline:
                    view = service.execution(owner, execution).view()
                    job = service._jobs.get((owner, execution))
                    if job is not None and job.done() and job.exception() is not None:
                        reasons["provider_or_effect_refused"] += 1
                        break
                    if not view["busy"]:
                        break
                    time.sleep(0.05)
                if view["busy"] or view["phase"]["tag"] != "score_ready":
                    reasons["score_not_ready"] += 1
                    continue
                service.command(owner, execution, {"tag": "perform"})
                while time.monotonic() < deadline:
                    view = service.execution(owner, execution).view()
                    if not view["busy"] and view.get("rendered"):
                        print(json.dumps({"status": "completed", "history_id": history_id,
                                          "source_was_edited": True, "rendered": True}))
                        return 0
                    time.sleep(0.05)
            except Exception as error:
                reasons[type(error).__name__] += 1
                continue
        print(json.dumps({"status": "failed", "code": "no_migrated_fork_rendered", "reasons": reasons}))
        return 1
    finally:
        shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
