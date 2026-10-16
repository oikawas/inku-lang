//! The experiment owns its input and WASM boundary, not the host's saved work.

use inku_render::{geometry_export::export_geometry, types::*};
use inku_score::{HardResourcePolicy, OperationalResourceBudget, ResourceBudget, ResourceDemand};
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use wasm_bindgen::prelude::*;

fn seed(value: Option<&Value>) -> Result<Option<Seed>, String> {
    match value {
        None | Some(Value::Null) => Ok(None),
        Some(Value::String(v)) => v
            .parse::<Seed>()
            .map(Some)
            .map_err(|_| "invalid_seed".into()),
        Some(Value::Number(v)) => v
            .as_i64()
            .filter(|n| n.unsigned_abs() <= 9_007_199_254_740_991)
            .map(|n| Some(n as Seed))
            .ok_or("unsafe_numeric_seed_use_decimal_string".into()),
        _ => Err("invalid_seed".into()),
    }
}

fn convert(input: &str) -> Result<Value, String> {
    if input.len() > 16 * 1024 * 1024 {
        return Err("input_budget_exceeded".into());
    }
    let value: Value = serde_json::from_str(input).map_err(|_| "invalid_json")?;
    let raw = value.get("score").ok_or("missing_score")?;
    let score =
        inku_score::read_saved_score_json(&serde_json::to_vec(raw).map_err(|_| "invalid_json")?)
            .map_err(|_| "invalid_score_or_version")?;
    let saved_aspect = value
        .get("render_canvas_aspect_id")
        .or_else(|| value.get("render_canvas_aspect"))
        .and_then(Value::as_str);
    let score_aspect = match &score.canvas {
        Canvas::Id(id) => id.as_str(),
        Canvas::Spec(spec) => spec.aspect.as_str(),
    };
    let ratio = if let Some(ratio) = value.get("render_canvas_aspect_ratio") {
        ratio.as_f64().ok_or("invalid_canvas")?
    } else {
        inku_score::lookup_canvas_format(saved_aspect.unwrap_or(score_aspect))
            .map_err(|_| "unknown_canvas_format")?
            .ratio_f64()
    };
    if !ratio.is_finite() || !(0.05..=20.0).contains(&ratio) {
        return Err("invalid_canvas".into());
    }
    let canvas = CanvasSize::new(1000.0 * ratio.max(1.0), 1000.0 / ratio.min(1.0));
    let color_map = value
        .get("render_color_map")
        .and_then(Value::as_object)
        .map(|m| {
            m.iter()
                .filter_map(|(k, v)| v.as_str().map(|s| (k.clone(), s.to_owned())))
                .collect()
        })
        .unwrap_or_default();
    let request = RenderRequest {
        score,
        options: RenderOptions {
            resolved_color_map: color_map,
            catalog_id: value
                .get("render_color_catalog_id")
                .and_then(Value::as_str)
                .map(str::to_owned),
            canvas,
            canvas_aspect_id: "experiment".into(),
            svg_profile: SvgProfile::Editable,
            render_seed: seed(value.get("render_seed"))?,
            composition_seed: seed(value.get("composition_seed"))?,
            wild: value
                .get("render_wild")
                .and_then(Value::as_bool)
                .unwrap_or(false),
            error_policy: ScoreErrorPolicy::Stop,
        },
    };
    let maximum = ResourceDemand {
        logical_objects: 4096,
        primitive_marks: 4096,
        object_templates: 4096,
        maximum_per_template_primitive_marks: 4096,
        maximum_resolved_count: 4096,
        template_nodes: 8192,
        anchor_instances: 4096,
        transform_instances: 4096,
        placement_instances: 4096,
        fill_instances: 4096,
    };
    let budget = ResourceBudget { maximum };
    // A saved compact Score binds its policy identity. Admit it only when both
    // saved ceilings fit the experiment's independent ceiling, then keep them.
    let (hard, operational) = if let Some(policy) = &request.score.resource_policy {
        budget
            .check(
                policy.hard_policy.budget.maximum,
                inku_score::ResourceAuthority::HardPolicy,
            )
            .map_err(|_| "saved_resource_policy_exceeds_experiment")?;
        budget
            .check(
                policy.operational_budget.0.maximum,
                inku_score::ResourceAuthority::OperationalBudget,
            )
            .map_err(|_| "saved_resource_policy_exceeds_experiment")?;
        (policy.hard_policy.clone(), policy.operational_budget.0)
    } else {
        (
            HardResourcePolicy {
                identity: "inku.ddl3d.v1".into(),
                budget,
            },
            budget,
        )
    };
    let mut scene = export_geometry(
        &request,
        &hard,
        OperationalResourceBudget(operational),
        4096,
    )?;
    if request.options.render_seed.is_none() {
        scene.diagnostics.push("missing_saved_seed".into());
    }
    if request.options.resolved_color_map.is_empty() {
        scene.diagnostics.push("missing_saved_colors".into());
    }
    Ok(json!({
        "ok": true, "scene": scene,
        "inputDigest": Sha256::digest(input.as_bytes()).iter().map(|b| format!("{b:02x}")).collect::<String>(),
        "schemaDigest": inku_score::score_schema_digest(),
        "mappingVersion": "solid-mapping-v1", "engineVersion": inku_render::RENDER_ENGINE_VERSION,
    }))
}

#[wasm_bindgen]
pub fn prepare_scene(input: &str) -> String {
    match convert(input) {
        Ok(value) => value.to_string(),
        Err(error) => json!({"ok": false, "error": error}).to_string(),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    const SOLIDS: &str = include_str!("../../fixtures/solids.json");

    // Failure: saved ratio/seed are replaced by current defaults or rounded in JS.
    #[test]
    fn saved_context_and_long_seed_are_preserved() {
        let result = convert(SOLIDS).unwrap();
        assert_eq!(result["scene"]["canvas"], json!([1.4, 1.0]));
        assert_eq!(
            result["scene"]["marks"][0]["shape"],
            json!({"kind":"round","center":[0.28,0.25],"radii":[0.12,0.12]})
        );
        assert_eq!(
            seed(Some(&json!("9007199254740993"))).unwrap(),
            Some(9_007_199_254_740_993)
        );
        assert!(seed(Some(&json!(9007199254740993_i64))).is_err());
        assert_eq!(result, convert(SOLIDS).unwrap());
        assert_eq!(result["scene"]["marks"].as_array().unwrap().len(), 9);
    }

    // Failure: macro/placement is expanded twice or arc-pair interiors disappear.
    #[test]
    fn placed_saved_score_has_one_expansion_and_closed_pair_interiors() {
        let score: Value = serde_json::from_str(include_str!(
            "../../../../server/tests/data/score-0.19-maple-leaves-in-cells.json"
        ))
        .unwrap();
        let result =
            convert(&json!({"score":score,"render_seed":"9007199254740993"}).to_string()).unwrap();
        let marks = result["scene"]["marks"].as_array().unwrap();
        assert_eq!(marks.len(), 33);
        assert_eq!(
            marks.iter().filter(|m| !m["pairFill"].is_null()).count(),
            15
        );
        assert!(
            marks
                .iter()
                .all(|m| m["sourceIndex"].as_u64().unwrap() < 11)
        );
    }

    // Failure: invalid input or excessive demand becomes an empty success.
    #[test]
    fn rejects_bad_version_invalid_canvas_and_excessive_demand() {
        assert!(convert("{}").is_err());
        let mut value: Value = serde_json::from_str(SOLIDS).unwrap();
        value["score"]["version"] = json!("99.0.0");
        assert!(convert(&value.to_string()).is_err());
        value["score"]["version"] = json!("0.1.0");
        value["render_canvas_aspect_ratio"] = json!(0);
        assert!(convert(&value.to_string()).is_err());
        value["render_canvas_aspect_ratio"] = json!(1);
        let instruction = value["score"]["instructions"][0].clone();
        value["score"]["instructions"] = Value::Array(vec![instruction; 4097]);
        assert!(convert(&value.to_string()).is_err());
    }
}
