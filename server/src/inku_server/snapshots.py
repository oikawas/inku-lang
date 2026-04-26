"""Saijiki スナップショット管理 — Stage 1/2 システムプロンプトの特定時点保存。"""

from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path
from threading import Lock

_SNAPSHOT_FILE = Path(os.getenv("INKU_SNAPSHOTS_FILE", "/tmp/inku-saijiki-snapshots.json"))
_snapshots: list[dict] = []
_lock = Lock()


def _load() -> None:
    global _snapshots
    if not _SNAPSHOT_FILE.exists():
        return
    try:
        _snapshots = json.loads(_SNAPSHOT_FILE.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        _snapshots = []


def _save() -> None:
    try:
        _SNAPSHOT_FILE.write_text(
            json.dumps(_snapshots, ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception:  # noqa: BLE001
        pass


_load()


def list_snapshots() -> list[dict]:
    """新しい順で返す (id, name, at のみ)。"""
    with _lock:
        return [{"id": s["id"], "name": s["name"], "at": s["at"]} for s in reversed(_snapshots)]


def get_snapshot(snapshot_id: str) -> dict | None:
    """フル内容を返す。存在しない場合は None。"""
    with _lock:
        for s in _snapshots:
            if s["id"] == snapshot_id:
                return dict(s)
    return None


def create_snapshot(name: str, stage1_prefix: str, stage2_prompt: str) -> dict:
    item = {
        "id": str(uuid.uuid4()),
        "name": name,
        "at": int(time.time() * 1000),
        "stage1_prefix": stage1_prefix,
        "stage2_prompt": stage2_prompt,
    }
    with _lock:
        _snapshots.append(item)
        _save()
    return {"id": item["id"], "name": item["name"], "at": item["at"]}


def delete_snapshot(snapshot_id: str) -> bool:
    with _lock:
        before = len(_snapshots)
        _snapshots[:] = [s for s in _snapshots if s["id"] != snapshot_id]
        changed = len(_snapshots) < before
        if changed:
            _save()
    return changed
