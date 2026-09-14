"""OpenAPI surface helpers shared by focused authorization tests."""

import hashlib
import json

from inku_server.api import app


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
        name: _stable(schema)
        for name, schema in sorted(spec.get("components", {}).get("schemas", {}).items())
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
