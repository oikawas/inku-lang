from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path


SERVER_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = SERVER_ROOT / "src" / "inku_server" / "db.py"
OWNER_PATH = SERVER_ROOT / "src" / "inku_server" / "persistence" / "legacy_schema.py"
MANIFEST_NAMES = (
    ("_LINEAGE_KIND_RENAMES", "LINEAGE_KIND_RENAMES", tuple),
    ("_HISTORY_COLUMN_MIGRATIONS", "HISTORY_COLUMN_MIGRATIONS", dict),
    ("_LINEAGE_NODE_COLUMN_MIGRATIONS", "LINEAGE_NODE_COLUMN_MIGRATIONS", dict),
    ("_USER_ACCOUNT_COLUMN_MIGRATIONS", "USER_ACCOUNT_COLUMN_MIGRATIONS", dict),
    ("_HISTORY_INDEX_MIGRATIONS", "HISTORY_INDEX_MIGRATIONS", tuple),
    ("_LINEAGE_NODE_INDEX_MIGRATIONS", "LINEAGE_NODE_INDEX_MIGRATIONS", tuple),
)
PRE_EXTRACTION_MANIFEST_SHA256 = "c5094e771ef0e2ced65df92f2564fd0912929003250ed9f2fcd805a8d4fedbd1"


def _encoded_manifest(owner):
    payload = []
    for _private_name, public_name, expected_type in MANIFEST_NAMES:
        value = getattr(owner, public_name)
        assert type(value) is expected_type
        if isinstance(value, dict):
            encoded = ["dict", list(value.items())]
        else:
            encoded = ["tuple", list(value)]
        payload.append([f"_{public_name}", encoded])
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()


def test_legacy_schema_manifest_has_one_persistence_owner():
    assert OWNER_PATH.is_file(), "persistence.legacy_schema must own the legacy manifest"

    db_source = DB_PATH.read_text()
    for private_name, _public_name, _expected_type in MANIFEST_NAMES:
        assert re.search(rf"^{re.escape(private_name)}\s*=", db_source, re.MULTILINE) is None

    from inku_server import db
    from inku_server.persistence import legacy_schema

    for private_name, public_name, _expected_type in MANIFEST_NAMES:
        assert getattr(db, private_name) is getattr(legacy_schema, public_name)

    assert hashlib.sha256(_encoded_manifest(legacy_schema)).hexdigest() == PRE_EXTRACTION_MANIFEST_SHA256
