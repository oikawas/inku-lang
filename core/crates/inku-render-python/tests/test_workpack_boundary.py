import json

from inku_render import (
    pipeline_workpack_encode_line,
    pipeline_workpack_plan,
    pipeline_workpack_read_line,
)


def test_workpack_byte_facades_share_record_identity_and_order():
    counts = dict(history=0, lineage_node=0, lineage_edge=0, annotation=1, colophon=0)
    producer = dict(host="fixture", app_version="1", build=1, schema_version=11)
    header = pipeline_workpack_encode_line(json.dumps({
        "kind": "header", "exported_at": 123, "producer": producer, "counts": counts,
    }).encode())
    assert header["error"] is None
    assert json.loads(pipeline_workpack_read_line(header["line"], line_number=1)) == {
        "outcome": "header", "format_version": 1, "counts": counts, "producer": producer,
    }
    result = pipeline_workpack_encode_line(json.dumps({
        "kind": "annotation", "record": {"history_id": "a", "note": " 文 / ", "for_revision": 1},
    }).encode())
    assert result == {
        "line": '{"for_revision":1,"history_id":"a","kind":"annotation","note":"文 /"}'.encode(),
        "error": None,
    }
    row = json.loads(pipeline_workpack_read_line(result["line"], line_number=2))
    assert row.pop("outcome") == "record"
    assert row == {"kind": "annotation", "key": "a", "identity": {"history_id": "a"}}
    plan = pipeline_workpack_plan(json.dumps({
        "action": "plan", "counts": counts, "records": [row], "existing": {},
    }).encode())
    assert json.loads(plan) == {
        "outcome": "ok", "works": [], "edges": [], "annotations": [], "colophons": [],
        "node_roots": {}, "skipped": 0,
    }
