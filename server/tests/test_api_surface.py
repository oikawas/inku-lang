"""The router split must not change one byte of what a client can observe.

Route count and the authorization gate do not cover response models, status
codes, parameters or request bodies: an endpoint can keep its path and its
guard while quietly losing a response field (measured 2026-08-01 -- dropping
HistoryListResponse.limit left both of those green).  So compare the whole
normalized surface against a baseline taken before the split.
"""

import hashlib
import json
import pathlib

from inku_server.api import app

BASELINE = pathlib.Path(__file__).parent / "data" / "api-surface-baseline.json"


def _stable(obj) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def current_surface() -> dict:
    spec = app.openapi()
    rows = []
    for path in sorted(spec["paths"]):
        for method in sorted(spec["paths"][path]):
            op = spec["paths"][path][method]
            rows.append(
                {
                    "path": path,
                    "method": method.upper(),
                    "operationId": op.get("operationId"),
                    "params": sorted(
                        f"{p.get('in')}:{p.get('name')}:"
                        f"{'req' if p.get('required') else 'opt'}"
                        for p in op.get("parameters", [])
                    ),
                    "requestBody": _stable(op.get("requestBody")),
                    "responses": {
                        code: _stable(body)
                        for code, body in sorted(op.get("responses", {}).items())
                    },
                }
            )
    schemas = {
        name: _stable(s)
        for name, s in sorted(spec.get("components", {}).get("schemas", {}).items())
    }
    surface = {
        "endpoint_count": len(rows),
        "operation_count": len(rows),
        "schema_count": len(schemas),
        "operations": rows,
        "schemas": schemas,
    }
    surface["digest"] = hashlib.sha256(_stable(surface).encode()).hexdigest()
    return surface


def test_api_surface_is_unchanged():
    expected = json.loads(BASELINE.read_text(encoding="utf-8"))
    actual = current_surface()

    # Name the first differing operation rather than only the hash: a bare
    # digest mismatch says nothing about what moved.
    by_key = {(o["method"], o["path"]): o for o in expected["operations"]}
    for op in actual["operations"]:
        key = (op["method"], op["path"])
        assert key in by_key, f"new endpoint: {key}"
        assert op == by_key[key], f"endpoint changed: {key}"
    assert {(o["method"], o["path"]) for o in actual["operations"]} == set(by_key)
    assert actual["schemas"] == expected["schemas"]
    assert actual["digest"] == expected["digest"]
