//! Groups of copies keep their joints (I-711 C3). Renders SVG; run on the
//! Linux rendering lane only.

use std::collections::BTreeMap;

use inku_ddl::{
    MacroExpansionLimits, NormalizedDdlDocument, ResolvedInstructionLanguage, ScoreErrorPolicy,
    ScoreLoweringContext, compile_ddl_to_score_with_resources,
};
use inku_render::{
    compat_clip::ClipLimits,
    render::{CompatFillClipPolicy, render_with_resources},
    types::{CanvasSize, RenderOptions, RenderRequest, SvgProfile},
};
use inku_score::{
    Color, HardResourcePolicy, OperationalResourceBudget, ResourceBudget, ResourceDemand,
    ScoreExecutionReason,
};

const LIMITS: MacroExpansionLimits = MacroExpansionLimits {
    max_invocations: 64,
    max_depth: 16,
    max_evaluation_steps: 8192,
    max_nodes_per_invocation: 128,
    max_total_nodes: 128,
};

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
        identity: "joint-group-test.v1".into(),
        budget,
    }
}

/// The C3 drawings whose later copies lost the relation: twenty-four circles
/// and eight lines resting on a filled square, forty points inside one.
#[test]
fn every_copy_of_a_group_keeps_its_joint() {
    for source in [
        "画用紙。\n背景を白で埋める。\n中ほど（横0〜1、縦1/3〜2/3）に、灰の太筆の薄い塗りの横長の特大のの四角を1個埋める。\n細かく小刻みに波打つ黄のクレヨンの濃い塗りの小さな円を24個散らす、前の形に載る。\n左中央（横0〜1/3、縦1/3〜2/3）に、細かく小刻みに揺れる黒の太いロットリングの実線の濃い粒の垂直の大きな線を6個引く。\n中心（横1/3〜2/3、縦1/3〜2/3）に、細かくゆるやかに揺れる黄の細い細筆の実線の程よい粒の回転の小さめの弧を40個引く。",
        "カンバス。\n背景を黒で埋める。\n下（横0〜1、縦2/3〜1）に、細かくゆるやかに波打つ青の太筆の薄い塗りの水平の横長の大きな四角を1個埋める。\n細かく小刻みに波打つ白のごく太いクレヨンの濃い粒の斜めの普通の大きさの線を8個引く、前の形に載る。\n左中央（横0〜1/3、縦1/3〜2/3）に、白の太筆の濃い塗りの大きな円を1個置く。\n左下（横0〜1/3、縦2/3〜1）に、大きくゆるやかに揺れる白の細い鉛筆の程よい刷きの斜めの小さな線を12個引く。",
        "背景を黒で埋める。\n右の3分の2（横1/3〜1、縦0〜1）に、細かくゆるやかに波打つ黄の太筆の薄い刷きの垂直の縦長の特大のの四角を1個埋める。\n白の鉛筆の濃いとても小さな点を40個散らす、前の形の中に。",
    ] {
        let hard = hard_policy();
        let result = compile_ddl_to_score_with_resources(
            NormalizedDdlDocument::new(source, ResolvedInstructionLanguage::Ja, Vec::new())
                .unwrap(),
            &[],
            Some(1),
            LIMITS,
            ScoreLoweringContext::resolve("square", Color::White).unwrap(),
            ScoreErrorPolicy::OmitAndContinue,
            hard.clone(),
            OperationalResourceBudget(hard.budget),
        );
        assert!(
            result.failure().is_none(),
            "{source}: {:?}",
            result.failure()
        );
        let score = result.score().expect("Score").clone();
        assert!(
            score.instructions.iter().any(|instruction| instruction
                .relation
                .as_ref()
                .is_some_and(|relation| relation.kind.is_joint())),
            "{source}: the joint reaches the Score"
        );
        let output = render_with_resources(
            RenderRequest {
                score,
                options: RenderOptions {
                    resolved_color_map: BTreeMap::new(),
                    catalog_id: None,
                    canvas: CanvasSize {
                        width: 256.0,
                        height: 256.0,
                    },
                    canvas_aspect_id: "square".into(),
                    svg_profile: SvgProfile::Display,
                    render_seed: Some(1),
                    composition_seed: Some(1),
                    wild: false,
                    error_policy: ScoreErrorPolicy::OmitAndContinue,
                },
            },
            &hard,
            OperationalResourceBudget(hard.budget),
            CompatFillClipPolicy {
                tolerance_pixels: 0.1,
                limits: ClipLimits {
                    max_nodes: 50_000,
                    max_path_elements: 200_000,
                    max_flattened_points: 200_000,
                    max_work: 10_000_000,
                    max_output_vertices: 200_000,
                },
            },
        )
        .unwrap();
        let joint_failures = output
            .metadata
            .execution
            .iter()
            .flat_map(|summary| &summary.diagnostics)
            .filter(|diagnostic| {
                matches!(
                    diagnostic.reason,
                    ScoreExecutionReason::MissingJointReference
                        | ScoreExecutionReason::JointReferenceOmitted
                        | ScoreExecutionReason::UnsupportedJointGeometry
                        | ScoreExecutionReason::NumericJointPositionConflict
                )
            })
            .count();
        assert_eq!(
            joint_failures, 0,
            "{source}: {:?}",
            output.metadata.execution
        );
    }
}
