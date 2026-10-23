//! A joint to a fill holds to the part of the fill that is seen inside the
//! target it is clipped to (I-711 C4c). Performs the Score; draws no SVG.

use inku_ddl::{
    MacroExpansionLimits, NormalizedDdlDocument, ResolvedInstructionLanguage, ScoreErrorPolicy,
    ScoreLoweringContext, compile_ddl_to_score_with_resources,
};
use inku_render::checked_performance::resolve_checked_performance_with_resources;
use inku_render::performance::{PerformancePlan, PerformanceRequest};
use inku_render::planning::{Bounds, performed_instruction_bounds_on_canvas};
use inku_render::types::{CanvasSize, Point};
use inku_score::{
    Color, HardResourcePolicy, OperationalResourceBudget, ResourceBudget, ResourceDemand,
};

const LIMITS: MacroExpansionLimits = MacroExpansionLimits {
    max_invocations: 64,
    max_depth: 16,
    max_evaluation_steps: 8192,
    max_nodes_per_invocation: 128,
    max_total_nodes: 128,
};

const SEEDS: [i128; 4] = [1, 7, 23, 42];

const CANVAS: CanvasSize = CanvasSize::new(1000.0, 1000.0);

fn hard_policy() -> HardResourcePolicy {
    let budget = ResourceBudget {
        maximum: ResourceDemand {
            logical_objects: 4096,
            primitive_marks: 400,
            object_templates: 64,
            maximum_per_template_primitive_marks: 240,
            maximum_resolved_count: 2000,
            template_nodes: 128,
            anchor_instances: 4096,
            transform_instances: 4096,
            placement_instances: 64,
            fill_instances: 64,
        },
    };
    HardResourcePolicy {
        identity: "joint-fill-test.v1".into(),
        budget,
    }
}

fn perform(source: &str, seed: i128) -> PerformancePlan {
    let hard = hard_policy();
    let result = compile_ddl_to_score_with_resources(
        NormalizedDdlDocument::new(source, ResolvedInstructionLanguage::Ja, Vec::new()).unwrap(),
        &[],
        Some(1),
        LIMITS,
        ScoreLoweringContext::resolve("square", Color::White).unwrap(),
        ScoreErrorPolicy::OmitAndContinue,
        hard.clone(),
        OperationalResourceBudget(hard.budget),
    );
    let score = result.score().expect("Score").clone();
    assert!(
        !score.fill_groups.is_empty(),
        "{source}: the partner is a fill"
    );
    resolve_checked_performance_with_resources(
        PerformanceRequest {
            score: &score,
            performance_seed: Some(seed),
            composition_seed: None,
            canvas: Some(CANVAS),
        },
        ScoreErrorPolicy::OmitAndContinue,
        &hard,
        OperationalResourceBudget(hard.budget),
    )
    .unwrap()
}

/// The performed bounds of each instruction of the source instruction `owner`.
fn boxes(plan: &PerformancePlan, seed: i128, owner: usize) -> Vec<Bounds> {
    let transforms = plan.instruction_transforms();
    let owners = plan.original_instruction_indices();
    plan.score
        .instructions
        .iter()
        .enumerate()
        .filter(|(index, _)| owners[*index] == owner)
        .map(|(index, instruction)| {
            let bounds = performed_instruction_bounds_on_canvas(
                instruction,
                Some(seed),
                index,
                Some(CANVAS),
            )
            .expect("bounds");
            Bounds {
                min: transforms[index].apply(bounds.min),
                max: transforms[index].apply(bounds.max),
            }
        })
        .collect()
}

fn union(boxes: &[Bounds]) -> Bounds {
    boxes.iter().fold(boxes[0], |union, bounds| Bounds {
        min: Point::new(union.min.x.min(bounds.min.x), union.min.y.min(bounds.min.y)),
        max: Point::new(union.max.x.max(bounds.max.x), union.max.y.max(bounds.max.y)),
    })
}

fn no_diagnostics(plan: &PerformancePlan) -> bool {
    plan.execution
        .as_ref()
        .is_none_or(|execution| execution.diagnostics.is_empty())
}

/// ja-06 of I-711 C4b: a building filled in the bottom band is taller than the
/// band, and the nest rests on the top of the building that is seen.
#[test]
fn a_group_resting_on_a_fill_rests_on_the_top_that_is_seen() {
    let source = "画用紙。\n背景を白で埋める。\n下（横0〜1、縦2/3〜1）に、灰の太筆の薄い塗りの垂直の横長の特大の四角を1個埋める。\n左上の四半分（横0〜1/2、縦0〜1/2）に、細かく小刻みに波打つ黒の細いペンの実線の濃い粒の小さな線を12個引く、前の形に載る。";
    let band_top = 2.0 / 3.0;
    let mut cut = 0;
    for seed in SEEDS {
        let plan = perform(source, seed);
        assert!(no_diagnostics(&plan), "seed {seed}: {:?}", plan.execution);
        let building = union(&boxes(&plan, seed, 0));
        let nest = union(&boxes(&plan, seed, 1));
        let seen_top = building.min.y.max(band_top);
        assert!(
            (nest.max.y - seen_top).abs() <= 1e-6,
            "seed {seed}: nest {nest:?} building {building:?}"
        );
        if building.min.y < band_top - 0.01 {
            cut += 1;
        }
    }
    // The band cuts the top of the building for some seed, so the test sees
    // the seen top differ from the top before the clip.
    assert!(cut > 0, "the band never cut the building");
}

/// A tall square filled in the middle band runs above and below it; the
/// points inside the square stay in the part of it the band shows.
#[test]
fn shapes_inside_a_fill_stay_in_the_part_that_is_seen() {
    let source = "画用紙。\n背景を白で埋める。\n中ほど（横0〜1、縦1/3〜2/3）に、細かくゆるやかに波打つ黄の太筆の薄い刷きの垂直の横長の特大の四角を1個埋める。\n白の鉛筆の濃いとても小さな点を20個散らす、前の形の中に。";
    let band = (1.0 / 3.0, 2.0 / 3.0);
    let mut cut = 0;
    for seed in SEEDS {
        let plan = perform(source, seed);
        assert!(no_diagnostics(&plan), "seed {seed}: {:?}", plan.execution);
        let square = union(&boxes(&plan, seed, 0));
        let seen = (square.min.y.max(band.0), square.max.y.min(band.1));
        let points = boxes(&plan, seed, 1);
        assert_eq!(points.len(), 20, "seed {seed}");
        for point in points {
            assert!(
                point.min.y >= seen.0 - 1e-6
                    && point.max.y <= seen.1 + 1e-6
                    && point.min.x >= square.min.x - 1e-6
                    && point.max.x <= square.max.x + 1e-6,
                "seed {seed}: point {point:?} square {square:?}"
            );
        }
        if square.min.y < band.0 - 0.01 || square.max.y > band.1 + 0.01 {
            cut += 1;
        }
    }
    assert!(cut > 0, "the band never cut the square");
}
