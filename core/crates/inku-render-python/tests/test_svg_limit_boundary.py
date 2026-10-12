"""Linux wheel smoke for the Server's separate SVG transport, without rasterization."""

import json

import inku_render as native


def _bytes(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode()


def _clip():
    return {
        "tolerance_pixels": 0.1,
        **{name: "1000" for name in (
            "max_nodes", "max_path_elements", "max_flattened_points", "max_work", "max_output_vertices"
        )},
    }


def _options(wire_seeds=False):
    return {
        "resolved_color_map": {"black": "#000000", "white": "#ffffff"},
        "catalog_id": "default",
        "canvas": {"width": 1000.0, "height": 1000.0},
        "canvas_aspect_id": "square",
        "svg_profile": "display",
        "render_seed": "7" if wire_seeds else 7,
        "composition_seed": "17" if wire_seeds else 17,
        "wild": False,
        "error_policy": "omit_and_continue",
    }


def _configuration():
    registry = json.loads(native.pipeline_canvas_registry())
    colors = _options()["resolved_color_map"]
    palette = json.loads(native.pipeline_resolve_palette(_bytes({
        "color_map": colors, "catalog_id": "default", "render_seed": "7", "background": "white"
    })))
    assert "error" not in palette
    budget = {"maximum": {
        "logical_objects": 400, "primitive_marks": 400, "object_templates": 64,
        "maximum_per_template_primitive_marks": 240, "maximum_resolved_count": 2000,
        "template_nodes": 512, "anchor_instances": 400, "transform_instances": 400,
        "placement_instances": 400, "fill_instances": 400,
    }}
    retry = {"max_attempts": 2, "attempt_timeout_ms": "1000", "total_timeout_ms": "3000", "retry_delay_ms": "10"}
    return {
        "envelope_limits": {"max_input_bytes": 16 << 20, "max_snapshot_bytes": 32 << 20, "max_output_bytes": 64 << 20},
        "language": "en",
        "compiler": {
            "host": {
                "canvas_format_id": "square", "canvas_format_registry_id": registry["registry"]["schema"],
                "canvas_format_registry_digest": registry["digest"], "resolved_catalog_id": "default",
                "catalog_mode": "default", "background": "white", "palette": palette,
            },
            "composition_seed": "17",
            "macro_expansion_limits": {
                "max_invocations": "16", "max_depth": "16", "max_evaluation_steps": "1000",
                "max_nodes_per_invocation": "100", "max_total_nodes": "500",
            },
            "error_policy": "omit_and_continue",
            "hard_resource_policy": {"identity": "svg-limit-smoke.v1", "budget": budget},
            "operational_resource_budget": budget,
        },
        "definitions": [{
            "schema": "inku.macro-definition.v1", "namespace": "Example", "heading": "Circle",
            "version": "1.0.0", "parameters": {}, "components": {}, "body": [{
                "op": "emit", "binding": None, "fields": {
                    "shape": {"expr": "semantic_ref", "category": "shape", "id": "circle"},
                    "movement": {"expr": "semantic_ref", "category": "movement", "id": "place"},
                    "color": {"expr": "semantic_ref", "category": "color", "id": "black"},
                    "position_x": {"expr": "exact_decimal", "value": "0.5"},
                    "position_y": {"expr": "exact_decimal", "value": "0.5"},
                    "count": {"expr": "integer", "value": 1},
                },
            }],
        }],
        "macro_summaries": ["One black circle at the center"], "catalogs": [],
        "prompt_limits": {
            "max_catalog_entries": 16, "max_summary_bytes": 1024, "max_catalog_serialized_bytes": 32768,
            "max_source_bytes": 8192, "max_response_bytes": 16384,
        },
        "catalog_retry": retry, "stage1_retry": retry, "hole_retry": retry,
    }


def _envelope(snapshot, payload):
    sequence = str(int(snapshot["sequence"]) + 1) if snapshot else "0"
    return _bytes({
        "protocol": "inku.pipeline", "version": "1.0.0", "kind": "input",
        "execution_id": snapshot["execution_id"] if snapshot else "new",
        "sequence": sequence, "message_id": f"svg-limit-{sequence}", "payload": {**payload, "version": 1},
    })


def _step(snapshot, payload):
    input_bytes = _envelope(snapshot, payload)
    snapshot_bytes = _bytes(snapshot) if snapshot else b""
    result_bytes, svg = native.pipeline_step_with_svg_limit(snapshot_bytes, input_bytes, 32 << 20)
    result = json.loads(result_bytes)
    assert result["kind"] == "output", result
    return result["payload"]["result"], svg, input_bytes


def _ready_snapshot():
    pending, svg, input_bytes = _step(None, {
        "tag": "start", "variation_id": "svg-limit-smoke", "authoring_nonce": "svg-limit-smoke-1",
        "config": _configuration(),
        "authority": {
            "protocol_version": "inku.variation-authority.v1", "revision": "0",
            "origin": "user_authored_ddl", "authority": "ddl_authoritative",
        },
        "authoring": {"tag": "direct_ddl", "source": "Example.Circle."},
    })
    assert svg is None
    assert json.loads(native.pipeline_step(b"", input_bytes))["payload"]["result"] == pending
    snapshot = pending["snapshot"]
    action = snapshot["action"]
    ready, svg, _ = _step(snapshot, {
        "tag": "effect_result",
        "result": {
            "tag": "visible_normalized_ddl_committed", "identity": action["identity"],
            "ddl_digest": action["payload"]["ddl_digest"],
            "revision": action["payload"]["authority"]["next_state"]["revision"],
            "authority_digest": action["payload"]["authority_digest"],
        },
    })
    assert svg is None
    assert ready["snapshot"]["phase"]["tag"] == "score_ready"
    return ready["snapshot"]


def test_svg_limit_legacy_native_matches_old_metadata():
    payload = _bytes({"score": {"version": "0.9.0", "instructions": []}, "options": _options()}).decode()
    expected = native.render(payload)
    assert native.render_with_svg_limit(payload, 32 << 20) == expected
    assert native.render_with_svg_limit(payload, 1) == expected
    assert len(expected[0].encode()) > 1


def test_svg_limit_pipeline_native_returns_raw_svg_and_unchanged_state():
    snapshot = _ready_snapshot()
    result, svg, input_bytes = _step(snapshot, {"tag": "render", "options": _options(wire_seeds=True), "clip": _clip()})
    old = json.loads(native.pipeline_step(_bytes(snapshot), input_bytes))["payload"]["result"]
    assert svg is not None and svg.startswith("<svg")
    assert result["rendered"]["svg"] == ""
    assert svg == old["rendered"]["svg"]
    result["rendered"]["svg"] = svg
    assert result == old
    error_bytes, svg = native.pipeline_step_with_svg_limit(b"", b"{", 32 << 20)
    assert json.loads(error_bytes)["kind"] == "error" and svg is None


def test_svg_limit_saved_native_matches_old_metadata():
    snapshot = _ready_snapshot()
    compiler = snapshot["config"]["compiler"]
    input_bytes = _bytes({
        "request": {"score": snapshot["delivery"]["score"], "options": _options()},
        "hard_policy": compiler["hard_resource_policy"], "operational_budget": compiler["operational_resource_budget"],
        "clip": _clip(),
    })
    expected = json.loads(native.pipeline_render_saved(input_bytes))
    assert "error" not in expected, expected
    result_bytes, svg = native.pipeline_render_saved_with_svg_limit(input_bytes, 32 << 20)
    result = json.loads(result_bytes)
    assert result["svg"] == "" and svg == expected["svg"]
    result["svg"] = svg
    assert result == expected
    error_bytes, svg = native.pipeline_render_saved_with_svg_limit(b"{", 32 << 20)
    assert json.loads(error_bytes)["error"] == "invalid_saved_performance" and svg is None
