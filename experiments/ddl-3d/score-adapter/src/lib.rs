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

/// The chunk (DDL 27 title) of each saved Score instruction, read by compiling
/// the saved DDL again. `None` when it does not compile to as many instructions
/// as the saved Score has (plugin words, a later edit of the Score, an engine
/// change): the viewer then gives each instruction its own layer.
fn score_chunks(
    ddl: &str,
    language: Option<&str>,
    composition_seed: Option<Seed>,
    expected: usize,
    hard: &HardResourcePolicy,
    operational: ResourceBudget,
) -> Option<Vec<Option<String>>> {
    use inku_ddl::ResolvedInstructionLanguage as Language;
    let language = match language {
        Some("ja") => Language::Ja,
        Some("en") => Language::En,
        _ if ddl.chars().any(|c| ('\u{3040}'..='\u{9fff}').contains(&c)) => Language::Ja,
        _ => Language::En,
    };
    // Generous, caller-owned limits: this compile only reads the chunks.
    let limits = inku_ddl::MacroExpansionLimits {
        max_invocations: 4096,
        max_depth: 32,
        max_evaluation_steps: 1_000_000,
        max_nodes_per_invocation: 4096,
        max_total_nodes: 65_536,
    };
    let result = inku_ddl::compile_ddl_to_score_with_resources(
        inku_ddl::NormalizedDdlDocument::new(ddl, language, Vec::new()).ok()?,
        &[],
        composition_seed.and_then(|seed| u64::try_from(seed).ok()),
        limits,
        inku_ddl::ScoreLoweringContext::resolve("square", inku_score::Color::White).ok()?,
        inku_ddl::ScoreErrorPolicy::OmitAndContinue,
        hard.clone(),
        OperationalResourceBudget(operational),
    );
    inku_ddl::score_instruction_chunks(&result).filter(|names| names.len() == expected)
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
    let (chunks, chunk_source) = match value.get("ddl").and_then(Value::as_str) {
        None => (Value::Null, "no_ddl"),
        Some(ddl) => match score_chunks(
            ddl,
            value
                .get("instruction_lang_resolved")
                .and_then(Value::as_str),
            request.options.composition_seed,
            request.score.instructions.len(),
            &hard,
            operational,
        ) {
            Some(names) => (json!(names), "ddl"),
            None => (Value::Null, "ddl_mismatch"),
        },
    };
    if request.options.render_seed.is_none() {
        scene.diagnostics.push("missing_saved_seed".into());
    }
    if request.options.resolved_color_map.is_empty() {
        scene.diagnostics.push("missing_saved_colors".into());
    }
    Ok(json!({
        "ok": true, "scene": scene, "chunks": chunks, "chunkSource": chunk_source,
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
    const RECOVERED: &str = include_str!("../../fixtures/recovered-score.json");

    #[test]
    fn score_0_22_brushmarks_remain_available_in_3d() {
        let mut value: Value = serde_json::from_str(SOLIDS).unwrap();
        value["score"]["version"] = json!("0.22.0");
        value["score"]["instructions"][0]["surface"] = json!({"texture":"brushmarks"});
        let result = convert(&value.to_string()).unwrap();
        assert!(!result["scene"]["marks"].as_array().unwrap().is_empty());
    }

    // Failure: a viewer built from an older core rejects the newest saved works
    // as invalid_score_or_version (I-734: 0.24 against a 0.23 build).
    #[test]
    fn latest_score_edition_is_available_in_3d() {
        let mut value: Value = serde_json::from_str(SOLIDS).unwrap();
        value["score"]["version"] = json!(inku_score::ScoreEdition::LATEST.as_str());
        let result = convert(&value.to_string()).unwrap();
        assert!(!result["scene"]["marks"].as_array().unwrap().is_empty());
    }

    // Failure: any presence field rejects the whole saved work, even kind:none.
    #[test]
    fn presence_retains_shared_paint_and_all_instruction_marks() {
        let mut value: Value = serde_json::from_str(SOLIDS).unwrap();
        let baseline = convert(&value.to_string()).unwrap();
        value["score"]["presence"] = json!({"kind":"figure_like", "intensity":"low",
            "symmetry":"none", "gaze_pressure":"none", "contour_density":"low"});
        let painted = convert(&value.to_string()).unwrap();
        assert_eq!(painted["scene"]["marks"], baseline["scene"]["marks"]);
        let svg = painted["scene"]["presenceSvg"].as_str().unwrap();
        assert!(svg.contains("presence_layer") && svg.contains("<path"));
        assert!(!svg.contains("<rect"));
        assert_eq!(painted, convert(&value.to_string()).unwrap());
        value["score"]["presence"]["kind"] = json!("none");
        let none = convert(&value.to_string()).unwrap();
        assert!(none["scene"]["presenceSvg"].is_null());
        assert_eq!(none["scene"]["marks"], baseline["scene"]["marks"]);
    }

    // Failure: a relation-only recovery rejects all otherwise drawable shapes;
    // actual resource omissions must retain the remaining original source IDs.
    #[test]
    fn recovered_score_keeps_drawable_content_and_reports_each_recovery() {
        let result = convert(RECOVERED).unwrap();
        let marks = result["scene"]["marks"].as_array().unwrap();
        assert_eq!(
            marks
                .iter()
                .map(|m| m["sourceIndex"].as_u64().unwrap())
                .collect::<Vec<_>>(),
            vec![0, 0, 1]
        );
        assert_eq!(
            result["scene"]["recoveries"],
            json!([{
                "kind": "execution", "instruction_index": 1, "dependency_instruction_index": 0,
                "reason": "unsupported_joint_geometry", "disposition": "relation_omitted"
            }])
        );

        let mut value: Value = serde_json::from_str(RECOVERED).unwrap();
        value["score"]["resource_policy"]["operational_budget"]["maximum"]["primitive_marks"] =
            json!(1);
        let limited = convert(&value.to_string()).unwrap();
        let marks = limited["scene"]["marks"].as_array().unwrap();
        assert_eq!(marks.len(), 1);
        assert_eq!(marks[0]["sourceIndex"], json!(1));
        let recoveries = limited["scene"]["recoveries"].as_array().unwrap();
        assert!(recoveries.iter().any(|d| d["kind"] == "resource_omitted"));
        assert!(
            recoveries
                .iter()
                .any(|d| d["kind"] == "relation_omitted" && d["instruction_index"] == 1)
        );
    }

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

    #[test]
    fn contained_score_places_geometry_and_paint_in_the_same_paper_frame() {
        let mut value: Value = serde_json::from_str(SOLIDS).unwrap();
        value["render_canvas_aspect_id"] = json!("square");
        value["render_canvas_aspect_ratio"] = json!(1);
        let full = convert(&value.to_string()).unwrap();
        value["score"]["canvas"] = json!({
            "aspect": "square", "declared_ratio": {"width_units": 2, "height_units": 1},
            "fit": "contain"
        });
        let fitted = convert(&value.to_string()).unwrap();
        assert_eq!(fitted["scene"]["canvas"], json!([1.0, 1.0]));
        let mark = &fitted["scene"]["marks"][0];
        assert_eq!(
            mark["shape"],
            json!({"kind":"round","center":[0.2,0.125],"radii":[0.06,0.06]})
        );
        assert_eq!(mark["transform"], json!([1.0, 0.0, 0.0, 1.0, 0.0, 0.25]));
        let full_center = &full["scene"]["marks"][0]["appearance"]["center"];
        let fitted_center = &mark["appearance"]["center"];
        assert!(
            (fitted_center[0].as_f64().unwrap() - full_center[0].as_f64().unwrap()).abs() < 1e-10
        );
        assert!(
            (fitted_center[1].as_f64().unwrap() - (0.25 + full_center[1].as_f64().unwrap() / 2.0))
                .abs()
                < 1e-10
        );
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
