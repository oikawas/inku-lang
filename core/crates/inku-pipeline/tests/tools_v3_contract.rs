use inku_ddl::work_plan::{WorkPlanSlot, work_plan_capabilities, work_plan_vocabulary};
use inku_ddl::{ResolvedInstructionLanguage, saijiki_asset, saijiki_tool_guidance};
use inku_pipeline::retouch::{readable_tools, tools};
use inku_pipeline::saved_variants::{drawn_tools, score_with_tools};
use serde_json::json;
use std::collections::BTreeMap;

const CURRENT: [&str; 11] = [
    "silverpoint",
    "pencil",
    "pen",
    "chalk",
    "oil_pastel",
    "gouache",
    "watercolor",
    "oil_paint",
    "painting_knife",
    "etching",
    "computer",
];
const OLD: [&str; 6] = [
    "rotring",
    "crayon",
    "brush_thin",
    "brush_thick",
    "burin",
    "drypoint",
];

#[test]
fn current_tools_are_offered_and_saved_tools_remain_readable() {
    assert_eq!(
        tools().iter().map(|x| x.value.as_str()).collect::<Vec<_>>(),
        CURRENT
    );
    let readable = readable_tools();
    assert_eq!(readable.len(), 17);
    assert_eq!(
        readable[..11]
            .iter()
            .map(|x| x.value.as_str())
            .collect::<Vec<_>>(),
        CURRENT
    );
    assert_eq!(
        readable[11..]
            .iter()
            .map(|x| x.value.as_str())
            .collect::<Vec<_>>(),
        OLD
    );
    assert!(
        readable
            .iter()
            .all(|x| !x.ja.is_empty() && !x.en.is_empty())
    );
}

#[test]
fn saved_variants_raise_only_new_weights_and_do_not_rename_old_drawn_tools() {
    let score = json!({"version":"0.9.0","instructions":[{"weight":"brush_thin","arrangement":{"resolved":{"owner":{"kind":"source_instruction","instruction_index":0}}}}]});
    assert_eq!(drawn_tools(&score, &[0])[&0], "brush_thin");
    for value in [
        "gouache",
        "watercolor",
        "oil_pastel",
        "painting_knife",
        "etching",
    ] {
        let changed = score_with_tools(&score, &BTreeMap::from([(0, value.to_owned())]));
        assert_eq!(changed["version"], "0.24.0");
        assert_eq!(changed["instructions"][0]["weight"], value);
    }
    for value in ["pencil", "brush_thin", "rotring"] {
        let changed = score_with_tools(&score, &BTreeMap::from([(0, value.to_owned())]));
        assert_eq!(changed["version"], "0.9.0");
        assert_eq!(changed["instructions"][0]["weight"], value);
    }
}

#[test]
fn stage1_offers_every_tool_with_bilingual_description_for_all_39_forms() {
    let vocab = work_plan_vocabulary();
    let ids = vocab
        .terms(WorkPlanSlot::Tool)
        .iter()
        .map(|x| x.id.as_str())
        .collect::<Vec<_>>();
    assert_eq!(ids, CURRENT);
    let table = work_plan_capabilities();
    assert_eq!(table.forms.len(), 39);
    for form in table.forms.keys() {
        for id in CURRENT {
            assert!(table.accepts(form, WorkPlanSlot::Tool, id), "{form}/{id}");
        }
    }
    let category = saijiki_asset()
        .categories
        .iter()
        .find(|x| x.key == "tezawari")
        .unwrap();
    for lang in [
        ResolvedInstructionLanguage::Ja,
        ResolvedInstructionLanguage::En,
    ] {
        let guidance = saijiki_tool_guidance(lang).unwrap();
        assert_eq!(guidance.lines().count(), 11);
        for word in &category.words {
            if word.prompt {
                let desc = word
                    .physical_description
                    .as_ref()
                    .expect("prompt tool has physical description");
                let (label, description) = match lang {
                    ResolvedInstructionLanguage::Ja => (&word.surface_ja, &desc.ja),
                    ResolvedInstructionLanguage::En => {
                        (word.surface_en.as_ref().unwrap(), &desc.en)
                    }
                };
                assert!(!description.is_empty());
                assert!(
                    guidance
                        .lines()
                        .any(|line| line == format!("{label}: {description}"))
                );
            }
        }
    }
}

use inku_pipeline::byte_envelope::EnvelopeLimits;
use inku_pipeline::core_boundary::{
    CatalogMode, CompilerOptions, MacroExpansionLimitsDto, ResolvedHostOptions,
    ResolvedPaletteColorDto, ResolvedPaletteDto,
};
use inku_pipeline::machine::PipelineConfig;
use inku_pipeline::prompts::PromptLimits;
use inku_pipeline::protocol::{DecimalU64, RetryPolicy};
use inku_score::{
    CANVAS_FORMAT_REGISTRY_ID, Color, HardResourcePolicy, OperationalResourceBudget,
    ResourceBudget, ResourceDemand, ScoreErrorPolicy, canvas_format_registry_digest,
};
fn config() -> PipelineConfig {
    let white = ResolvedPaletteColorDto {
        abstract_color: Color::White,
        concrete_rgb: [255; 3],
        oklch_lightness: 1.0,
    };
    let black = ResolvedPaletteColorDto {
        abstract_color: Color::Black,
        concrete_rgb: [0; 3],
        oklch_lightness: 0.0,
    };
    let host = ResolvedHostOptions::new(
        "square",
        CANVAS_FORMAT_REGISTRY_ID,
        canvas_format_registry_digest().unwrap(),
        "default",
        CatalogMode::Default,
        Color::White,
        ResolvedPaletteDto {
            background: white,
            black,
            white,
            observations: None,
            paints: None,
        },
    )
    .unwrap();
    let budget = ResourceBudget {
        maximum: ResourceDemand {
            logical_objects: 400,
            primitive_marks: 400,
            object_templates: 64,
            maximum_per_template_primitive_marks: 240,
            maximum_resolved_count: 2000,
            template_nodes: 512,
            anchor_instances: 400,
            transform_instances: 400,
            placement_instances: 400,
            fill_instances: 400,
        },
    };
    let retry = RetryPolicy {
        max_attempts: 2,
        attempt_timeout_ms: DecimalU64::new(1000),
        total_timeout_ms: DecimalU64::new(3000),
        retry_delay_ms: DecimalU64::new(10),
    };
    PipelineConfig {
        plugin_offers: Vec::new(),
        envelope_limits: EnvelopeLimits {
            max_input_bytes: 1_000_000,
            max_snapshot_bytes: 1_000_000,
            max_output_bytes: 2_000_000,
        },
        language: inku_ddl::ResolvedInstructionLanguage::En,
        compiler: CompilerOptions {
            host,
            composition_seed: Some(DecimalU64::new(17)),
            macro_expansion_limits: MacroExpansionLimitsDto {
                max_invocations: DecimalU64::new(16),
                max_depth: DecimalU64::new(16),
                max_evaluation_steps: DecimalU64::new(1000),
                max_nodes_per_invocation: DecimalU64::new(100),
                max_total_nodes: DecimalU64::new(500),
            },
            error_policy: ScoreErrorPolicy::OmitAndContinue,
            hard_resource_policy: HardResourcePolicy {
                identity: "pipeline-fixture.v1".into(),
                budget,
            },
            operational_resource_budget: OperationalResourceBudget(budget),
        },
        definitions: vec![],
        macro_summaries: vec![],
        catalogs: vec![],
        catalog_seed: None,
        prompt_limits: PromptLimits {
            max_offered_plugins: 8,
            max_catalog_entries: 16,
            max_summary_bytes: 1024,
            max_catalog_serialized_bytes: 32768,
            max_source_bytes: 8192,
            max_response_bytes: 16384,
        },
        catalog_retry: retry,
        stage1_retry: retry,
        hole_retry: retry,
        sketch_retry: None,
        composition: None,
        composition_retry: None,
        laws: None,
        laws_retry: None,
        colors: None,
        colors_retry: None,
        image: None,
        image_retry: None,
        description_ddl: None,
    }
}

#[test]
fn tool_labels_in_the_saved_variant_plan_include_the_six_legacy_names() {
    let score = json!({"instructions":[{"weight":"brush_thin","arrangement":{"resolved":{"owner":{"kind":"source_instruction","instruction_index":0}}}}]});
    let request = json!({"action":"tool_plan", "config":config(), "source":"Draw one blue pen line.", "score":score, "mode":"uniform", "seed":7});
    let response: serde_json::Value = serde_json::from_slice(
        &inku_pipeline::saved_variants::saved_variants_json(&serde_json::to_vec(&request).unwrap()),
    )
    .unwrap();
    assert_eq!(response["outcome"], "ok", "{response}");
    let labels = response["tool_labels"].as_array().unwrap();
    let expected = readable_tools();
    assert_eq!(labels.len(), 17);
    for (label, tool) in labels.iter().zip(expected) {
        assert_eq!(
            label,
            &json!({"value":tool.value,"ja":tool.ja,"en":tool.en})
        );
    }
    assert_eq!(response["sentences"][0]["tool"], "brush_thin");
}
