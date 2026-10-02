//! A fill range written in numbers draws as the position word with the same
//! numbers. Renders SVG; run on the Linux rendering lane only.

use std::collections::BTreeMap;

use inku_ddl::{
    CompilerResourceExecutionResult, MacroExpansionLimits, NormalizedDdlDocument,
    ResolvedInstructionLanguage, ScoreErrorPolicy, ScoreLoweringContext, ScoreLoweringOutcome,
    compile_ddl_to_score_with_resources,
};
use inku_render::{
    compat_clip::ClipLimits,
    render::{CompatFillClipPolicy, render_with_resources},
    types::{CanvasSize, RenderOptions, RenderRequest, SvgProfile},
};
use inku_score::{
    Color, FillTargetAnchor, FillTargetGeometry, FillTargetOwner, HardResourcePolicy,
    OperationalResourceBudget, ResourceBudget, ResourceDemand, Score,
};

const LIMITS: MacroExpansionLimits = MacroExpansionLimits {
    max_invocations: 8,
    max_depth: 8,
    max_evaluation_steps: 128,
    max_nodes_per_invocation: 32,
    max_total_nodes: 64,
};

fn hard_policy() -> HardResourcePolicy {
    let budget = ResourceBudget {
        maximum: ResourceDemand {
            logical_objects: 4000,
            primitive_marks: 4000,
            object_templates: 64,
            maximum_per_template_primitive_marks: 240,
            maximum_resolved_count: 4000,
            template_nodes: 512,
            anchor_instances: 4000,
            transform_instances: 4000,
            placement_instances: 4000,
            fill_instances: 4000,
        },
    };
    HardResourcePolicy {
        identity: "fill-numeric-range-fixture.v1".into(),
        budget,
    }
}

fn compile(source: &str, language: ResolvedInstructionLanguage) -> CompilerResourceExecutionResult {
    let hard = hard_policy();
    compile_ddl_to_score_with_resources(
        NormalizedDdlDocument::new(source, language, vec![]).unwrap(),
        &[],
        Some(17),
        LIMITS,
        ScoreLoweringContext::resolve("square", Color::White).unwrap(),
        None,
        ScoreErrorPolicy::OmitAndContinue,
        hard.clone(),
        OperationalResourceBudget(hard.budget),
    )
}

fn complete_score(source: &str, language: ResolvedInstructionLanguage) -> Score {
    let compiled = compile(source, language);
    assert_eq!(
        compiled.outcome(),
        ScoreLoweringOutcome::Complete,
        "{source}: {:?}",
        compiled.downstream_diagnostics()
    );
    let score = compiled
        .score()
        .expect("a complete compile has a Score")
        .clone();
    // The saved form reads back and passes the Score checks.
    let bytes = inku_score::canonical_json_bytes(&score).unwrap();
    assert_eq!(inku_score::read_saved_score_json(&bytes).unwrap(), score);
    score
}

fn svg(score: &Score) -> String {
    let hard = hard_policy();
    let request = RenderRequest {
        score: score.clone(),
        options: RenderOptions {
            resolved_color_map: BTreeMap::new(),
            catalog_id: None,
            canvas: CanvasSize {
                width: 256.0,
                height: 256.0,
            },
            canvas_aspect_id: "square".into(),
            svg_profile: SvgProfile::Display,
            render_seed: Some(666010),
            composition_seed: Some(17),
            wild: false,
            error_policy: ScoreErrorPolicy::OmitAndContinue,
        },
    };
    let clip = CompatFillClipPolicy {
        tolerance_pixels: 0.1,
        limits: ClipLimits {
            max_nodes: 50_000,
            max_path_elements: 200_000,
            max_flattened_points: 200_000,
            max_work: 10_000_000,
            max_output_vertices: 200_000,
        },
    };
    render_with_resources(request, &hard, OperationalResourceBudget(hard.budget), clip)
        .unwrap()
        .svg
}

/// The Score of `numbers` with the word's record of where its fill range came
/// from, so that only that record and the edition it needs can differ.
fn as_word(numbers: &Score, word: &Score) -> Score {
    let mut score = numbers.clone();
    score.version.clone_from(&word.version);
    for (group, word_group) in score.fill_groups.iter_mut().zip(&word.fill_groups) {
        group.target.owner = word_group.target.owner.clone();
    }
    score
}

#[test]
fn a_fill_range_written_in_numbers_draws_as_the_position_word() {
    for (word, numbers, language) in [
        (
            "下に、赤い小さな円を埋める。",
            "下（横0〜1、縦2/3〜1）に、赤い小さな円を埋める。",
            ResolvedInstructionLanguage::Ja,
        ),
        (
            "fill small red circles at the bottom.",
            "fill small red circles at the bottom (horizontal 0 to 1, vertical 2/3 to 1).",
            ResolvedInstructionLanguage::En,
        ),
        // A fill run of colors or of tools reads the range the same way.
        (
            "下に、赤と青を交互にして、円を五つ埋める。",
            "下（横0〜1、縦2/3〜1）に、赤と青を交互にして、円を五つ埋める。",
            ResolvedInstructionLanguage::Ja,
        ),
        (
            "下に、鉛筆と太筆を交互にして、黒い線を五本埋める。",
            "下（横0〜1、縦2/3〜1）に、鉛筆と太筆を交互にして、黒い線を五本埋める。",
            ResolvedInstructionLanguage::Ja,
        ),
    ] {
        let word = complete_score(word, language);
        let numbers = complete_score(numbers, language);
        assert_eq!(numbers.fill_groups.len(), 1);
        let target = &numbers.fill_groups[0].target;
        assert!(
            matches!(target.owner, FillTargetOwner::NumericRange { .. }),
            "{:?}",
            target.owner
        );
        assert_eq!(numbers.version, "0.18.0");
        assert_eq!(
            target.geometry,
            FillTargetGeometry::Rectangle {
                bounds: [0.0, 2.0 / 3.0, 1.0, 1.0]
            }
        );
        assert_eq!(as_word(&numbers, &word), word);
        assert_eq!(svg(&numbers), svg(&word));

        // An earlier edition has no form for the record.
        let mut earlier = numbers.clone();
        earlier.version = "0.17.0".into();
        let error = inku_score::read_saved_score_json(&serde_json::to_vec(&earlier).unwrap())
            .unwrap_err()
            .to_string();
        assert!(
            error.contains("fill target numeric_range requires Score version 0.18.0"),
            "{error}"
        );
    }
}

#[test]
fn a_numeric_range_on_a_filled_shape_places_it_as_the_position_word() {
    for (word, numbers, language) in [
        (
            "下に、直径0.5の円を三つの赤い点で埋める。",
            "下（横0〜1、縦2/3〜1）に、直径0.5の円を三つの赤い点で埋める。",
            ResolvedInstructionLanguage::Ja,
        ),
        (
            "fill a circle diameter 0.5 at the bottom with 3 red points.",
            "fill a circle diameter 0.5 at the bottom (horizontal 0 to 1, vertical 2/3 to 1) with 3 red points.",
            ResolvedInstructionLanguage::En,
        ),
    ] {
        let word = complete_score(word, language);
        let numbers = complete_score(numbers, language);
        let FillTargetGeometry::Shape { anchor, .. } = &numbers.fill_groups[0].target.geometry
        else {
            panic!("{:?}", numbers.fill_groups[0].target);
        };
        assert_eq!(
            anchor,
            &FillTargetAnchor::Named {
                region: [0.0, 2.0 / 3.0, 1.0, 1.0]
            }
        );
        // The shape keeps its own owner; only its place came from the numbers.
        assert_eq!(numbers, word);
    }
}
