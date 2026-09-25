//! Host-side expectations for the Android packaged-render device test.
//!
//! Builds, from frozen corpus inputs, the same canonical request the Android
//! test sends through JNI, renders it with the host core of this commit, and
//! writes `<case>.request.json`, `<case>.svg`, `renderer_reference.json`, and
//! `expected.json` (engine identity). The device then checks that the packaged library returns the same
//! bytes, whatever the current render engine version is.
//!
//! usage: render-parity-expected <manifest.json> <out-dir> <case>...

use std::fs;
use std::path::PathBuf;

use serde_json::{Value, json};

const CANVAS_BASE_PX: f64 = 1000.0;

fn canvas_ratio(registry: &Value, aspect: &str) -> f64 {
    let format = registry["registry"]["formats"]
        .as_array()
        .expect("canvas registry formats")
        .iter()
        .find(|format| format["id"] == aspect)
        .unwrap_or_else(|| panic!("unknown canvas format {aspect}"));
    format["width_units"].as_f64().expect("width_units") / format["height_units"].as_f64().expect("height_units")
}

fn main() {
    let mut args = std::env::args().skip(1);
    let manifest_path = PathBuf::from(args.next().expect("manifest path"));
    let out_dir = PathBuf::from(args.next().expect("output directory"));
    let cases: Vec<String> = args.collect();
    assert!(!cases.is_empty(), "at least one case is required");

    let manifest: Value = serde_json::from_str(&fs::read_to_string(&manifest_path).expect("read manifest"))
        .expect("parse manifest");
    let registry: Value =
        serde_json::from_str(&inku_pipeline_uniffi::canvas_registry()).expect("parse canvas registry");
    fs::create_dir_all(&out_dir).expect("create output directory");

    for name in &cases {
        let input = &manifest["cases"][name]["input"];
        assert!(input.is_object(), "case {name} is missing from the manifest");
        let aspect = input["score"]["canvas"]["aspect"].as_str().expect("canvas aspect");
        // Same rounding as Android's CanvasAspects.sizeFor.
        let width = (CANVAS_BASE_PX * canvas_ratio(&registry, aspect)).round_ties_even() as i64;
        let request = json!({
            "score": input["score"],
            "options": {
                "resolved_color_map": input["color_map"],
                "catalog_id": input["catalog_id"],
                "canvas": {"width": width, "height": CANVAS_BASE_PX as i64},
                "canvas_aspect_id": aspect,
                "svg_profile": input["svg_profile"],
                "render_seed": input["render_seed"],
                "composition_seed": Value::Null,
                "wild": input["wild"],
            },
        });
        let parsed = serde_json::from_value(request.clone()).expect("canonical render request");
        let output = inku_render::render::render(parsed).unwrap_or_else(|error| panic!("render {name}: {error}"));
        fs::write(out_dir.join(format!("{name}.request.json")), request.to_string()).expect("write request");
        fs::write(out_dir.join(format!("{name}.svg")), output.svg).expect("write svg");
    }

    let reference = serde_json::to_string(&inku_render::reference::renderer_reference()).expect("renderer reference");
    fs::write(out_dir.join("renderer_reference.json"), reference).expect("write renderer reference");

    let (engine_id, engine_version) = inku_render::render_engine_identity();
    let expected = json!({
        "render_engine_id": engine_id,
        "render_engine_version": engine_version,
        "cases": cases,
    });
    fs::write(out_dir.join("expected.json"), expected.to_string()).expect("write expected");
}
