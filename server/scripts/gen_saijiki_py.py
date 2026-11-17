"""Generate the Server vocabulary snapshot from the shared Saijiki v4 asset."""
from __future__ import annotations

import json
from pathlib import Path
from pprint import pformat

ROOT = Path(__file__).resolve().parents[2]
ASSET = ROOT / "core/crates/inku-ddl/assets/saijiki-v4.json"
OUTPUT = ROOT / "server/src/inku_server/saijiki_generated.py"


def render_py() -> str:
    asset = json.loads(ASSET.read_text(encoding="utf-8"))
    if asset["asset_id"] != "inku.saijiki.v4":
        raise ValueError("unexpected Saijiki asset")
    return ('"""Generated from saijiki-v4.json by gen_saijiki_py.py; do not edit."""\n\n'
            + 'BUNDLES = ' + pformat(asset["bundles"], width=100, sort_dicts=False) + '\n\n'
            + 'RELATIONS_BUNDLE = ' + repr(asset["relations_bundle"]) + '\n\n'
            + 'RELATION_DESCRIPTIONS = ' + pformat({item['relation_type']: item.get('description') for item in asset['relations']}, width=100, sort_dicts=False) + '\n\n'
            + 'CATEGORIES = ' + pformat(asset["categories"], width=100, sort_dicts=False) + '\n')


if __name__ == "__main__":
    OUTPUT.write_text(render_py(), encoding="utf-8")
    print(f"wrote {OUTPUT}")
