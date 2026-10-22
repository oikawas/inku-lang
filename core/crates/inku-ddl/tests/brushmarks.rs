//! Brushmarks (刷毛目, DDL 25). A surface word for the face of a closed shape:
//! the bands a sweep lays, each on its own, so that they darken where they
//! overlap. It lowers to the Score texture `brushmarks`, which only Score
//! 0.22.0 holds, and takes the fineness and underlayer words as a sweep does.
//! On a line, an open arc or a free line only the word is left out, with its
//! own reason, and the mark lowers as it does without it.

use inku_ddl::work_plan::{
    WorkPlan, WorkPlanLayer, WorkPlanSlot, normalize_work_plan, print_work_plan,
    work_plan_capabilities, work_plan_response_schema, work_plan_source_compiles_cleanly,
};
use inku_ddl::{
    MacroExpansionLimits, NormalizedDdlDocument, ResolvedInstructionLanguage,
    ScoreAppearanceResolution, ScoreDiagnosticDisposition, ScoreErrorPolicy, ScoreFieldGap,
    ScoreLoweringContext, ScoreLoweringOutcome, compile_ddl_to_score_with_resources,
};
use inku_score::{
    Color, HardResourcePolicy, Instruction, OperationalResourceBudget, ResourceBudget,
    ResourceDemand, Score, SurfaceIntensity, SurfaceTexture,
};
use serde_json::json;

const LIMITS: MacroExpansionLimits = MacroExpansionLimits {
    max_invocations: 8,
    max_depth: 8,
    max_evaluation_steps: 64,
    max_nodes_per_invocation: 32,
    max_total_nodes: 64,
};

const JA: ResolvedInstructionLanguage = ResolvedInstructionLanguage::Ja;
const EN: ResolvedInstructionLanguage = ResolvedInstructionLanguage::En;

fn hard_policy() -> HardResourcePolicy {
    HardResourcePolicy {
        identity: "brushmarks-test.v1".into(),
        budget: ResourceBudget {
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
        },
    }
}

struct Compiled {
    outcome: ScoreLoweringOutcome,
    score: Score,
    gaps: Vec<ScoreFieldGap>,
    resolutions: Vec<Option<ScoreAppearanceResolution>>,
    upstream: usize,
}

fn compile(source: &str, language: ResolvedInstructionLanguage) -> Compiled {
    let hard = hard_policy();
    let result = compile_ddl_to_score_with_resources(
        NormalizedDdlDocument::new(source, language, Vec::new()).unwrap(),
        &[],
        Some(1),
        LIMITS,
        ScoreLoweringContext::resolve("square", Color::White).unwrap(),
        ScoreErrorPolicy::OmitAndContinue,
        hard.clone(),
        OperationalResourceBudget(hard.budget),
    );
    Compiled {
        outcome: result.outcome(),
        score: result.score().expect(source).clone(),
        gaps: result
            .downstream_diagnostics()
            .iter()
            .map(|diagnostic| diagnostic.reason.clone())
            .collect(),
        resolutions: result
            .downstream_diagnostics()
            .iter()
            .map(|diagnostic| match &diagnostic.disposition {
                ScoreDiagnosticDisposition::Omitted {
                    appearance_resolution,
                    ..
                } => *appearance_resolution,
                _ => None,
            })
            .collect(),
        upstream: result.upstream_diagnostics().len(),
    }
}

fn only_instruction<'a>(compiled: &'a Compiled, source: &str) -> &'a Instruction {
    let [instruction] = compiled.score.instructions.as_slice() else {
        panic!(
            "{source}: {} instructions",
            compiled.score.instructions.len()
        );
    };
    instruction
}

#[test]
fn brushmarks_lays_a_closed_shapes_face_in_score_0_22() {
    // (source, language, scale, filled, intensity)
    for (source, language, scale, filled, intensity) in [
        (
            "中心に、白の太筆の刷毛目の四角を1個置く。",
            JA,
            0.35,
            false,
            SurfaceIntensity::Normal,
        ),
        (
            "Place one white thick-brush brushmarks square at the center.",
            EN,
            0.35,
            false,
            SurfaceIntensity::Normal,
        ),
        (
            "中心に、赤のペンの刷毛目の円を1個置く。",
            JA,
            0.35,
            false,
            SurfaceIntensity::Normal,
        ),
        (
            "中心に、赤のロットリングの刷毛目の楕円を1個置く。",
            JA,
            0.35,
            false,
            SurfaceIntensity::Normal,
        ),
        (
            "中心に、赤の太筆の細かい刷毛目の円を1個置く。",
            JA,
            0.05,
            false,
            SurfaceIntensity::Normal,
        ),
        (
            "中心に、赤の太筆の下塗りの刷毛目の薄い三角を1個置く。",
            JA,
            0.35,
            true,
            SurfaceIntensity::Faint,
        ),
        (
            "Place one red thick-brush faint underpainted brushmarks triangle at the center.",
            EN,
            0.35,
            true,
            SurfaceIntensity::Faint,
        ),
        (
            "中心に、刷毛目の白の太筆の雲形を1個置く。",
            JA,
            0.35,
            false,
            SurfaceIntensity::Normal,
        ),
    ] {
        let compiled = compile(source, language);
        assert_eq!(compiled.outcome, ScoreLoweringOutcome::Complete, "{source}");
        assert!(compiled.gaps.is_empty(), "{source}: {:?}", compiled.gaps);
        assert_eq!(compiled.upstream, 0, "{source}");
        assert_eq!(compiled.score.version, "0.22.0", "{source}");
        let mark = only_instruction(&compiled, source);
        let surface = mark.surface.as_ref().expect(source);
        assert_eq!(surface.texture, SurfaceTexture::Brushmarks, "{source}");
        assert_eq!(surface.scale, scale, "{source}");
        assert_eq!(mark.filled, filled, "{source}");
        assert_eq!(mark.surface_intensity, intensity, "{source}");
    }
}

#[test]
fn brushmarks_without_a_face_is_left_out_alone() {
    let brushmarks = || ScoreFieldGap::UnsupportedSurfaceBrushmarks {
        category: "surface".into(),
        id: "brushmarks".into(),
    };
    for (source, without, language, gaps) in [
        (
            "中心に、白の太筆の刷毛目の線を1本引く。",
            "中心に、白の太筆の線を1本引く。",
            JA,
            vec![brushmarks()],
        ),
        (
            "Draw one white thick-brush brushmarks line at the center.",
            "Draw one white thick-brush line at the center.",
            EN,
            vec![brushmarks()],
        ),
        (
            "中心に、白の太筆の刷毛目の弧を1本引く。",
            "中心に、白の太筆の弧を1本引く。",
            JA,
            vec![brushmarks()],
        ),
        (
            "中心に、白の太筆の刷毛目の自由線を1本引く。",
            "中心に、白の太筆の自由線を1本引く。",
            JA,
            vec![brushmarks()],
        ),
        (
            "中心に、白の太筆の細かい刷毛目の線を1本引く。",
            "中心に、白の太筆の線を1本引く。",
            JA,
            vec![
                brushmarks(),
                ScoreFieldGap::UnsupportedSurfaceFineness {
                    category: "fineness".into(),
                    id: "fine_grained".into(),
                },
            ],
        ),
        // A point takes no surface word, brushmarks included.
        (
            "中心に、白の太筆の刷毛目の点を1個置く。",
            "中心に、白の太筆の点を1個置く。",
            JA,
            vec![ScoreFieldGap::UnsupportedSurfaceIdentity {
                category: "surface".into(),
                id: "brushmarks".into(),
            }],
        ),
    ] {
        let compiled = compile(source, language);
        let reference = compile(without, language);
        assert_eq!(
            compiled.outcome,
            ScoreLoweringOutcome::CompleteWithOmissions,
            "{source}"
        );
        let mut sorted = compiled.gaps.clone();
        sorted.sort_by_key(|gap| format!("{gap:?}"));
        let mut expected = gaps;
        expected.sort_by_key(|gap| format!("{gap:?}"));
        assert_eq!(sorted, expected, "{source}");
        assert_eq!(
            compiled.score.instructions, reference.score.instructions,
            "{source}"
        );
        assert_eq!(compiled.score.version, reference.score.version, "{source}");
    }
    // Nothing takes the left-out word's place on the line.
    let compiled = compile("中心に、白の太筆の刷毛目の線を1本引く。", JA);
    assert_eq!(
        compiled.resolutions,
        vec![Some(ScoreAppearanceResolution::Unchanged)]
    );
}

/// One mark takes one surface word: a sweep and brushmarks conflict as any
/// two surface words do, and both are left out.
#[test]
fn a_sweep_and_brushmarks_on_one_mark_conflict() {
    let compiled = compile("中心に、白の太筆の刷きの刷毛目の円を1個置く。", JA);
    let reference = compile("中心に、白の太筆の円を1個置く。", JA);
    assert_eq!(compiled.upstream, 1);
    assert!(compiled.gaps.is_empty(), "{:?}", compiled.gaps);
    assert_eq!(compiled.score.instructions, reference.score.instructions);
}

/// Writing brushmarks for a sweep (the author's work 15bc0923…) changes the
/// texture and the edition, and nothing else of the Score.
#[test]
fn brushmarks_for_a_sweep_changes_only_the_texture_and_the_edition() {
    let sweep = "背景を黒で埋める。\n\
                 画面の横0.5、縦0.5の位置に、白の太い太筆の薄い刷きの全幅の四角を1個置く。\n\
                 画面の横0.5、縦0.5の位置に、白の太い太筆の薄い刷きの全幅の四角を1個置く。";
    let brushmarks = sweep.replace("刷き", "刷毛目");
    let before = compile(sweep, JA);
    let after = compile(&brushmarks, JA);
    assert_eq!(before.score.version, "0.17.0");
    assert_eq!(after.score.version, "0.22.0");
    assert_eq!(after.score.instructions.len(), 2);
    let mut rewritten = before.score.clone();
    for instruction in &mut rewritten.instructions {
        let surface = instruction.surface.as_mut().expect("a sweep face");
        assert_eq!(surface.texture, SurfaceTexture::Sweep);
        surface.texture = SurfaceTexture::Brushmarks;
    }
    rewritten.version = "0.22.0".into();
    assert_eq!(after.score, rewritten);
}

const CLOSED: [&str; 5] = ["circle", "ellipse", "triangle", "square", "cloudform"];

/// The plan offers brushmarks next to sweep, and only the closed shapes take
/// it; a line's brushmarks is dropped as a value its form does not take.
#[test]
fn the_plan_offers_brushmarks_on_closed_shapes_only() {
    let schema = work_plan_response_schema();
    let surfaces = &schema["properties"]["layers"]["items"]["properties"]["surface"]["enum"];
    assert_eq!(
        surfaces,
        &json!([
            "unspecified",
            "empty",
            "flat",
            "sweep",
            "brushmarks",
            "grain",
            "stipple",
            "hatch",
            "crosshatch",
            "aquatint"
        ])
    );
    let capabilities = work_plan_capabilities();
    let mut closed = 0;
    for (form, slots) in &capabilities.forms {
        let shape = form.split('/').next().unwrap();
        let takes = capabilities.accepts(form, WorkPlanSlot::Surface, "brushmarks");
        assert_eq!(takes, CLOSED.contains(&shape), "{form}");
        if takes {
            closed += 1;
            // Brushmarks is a named texture: the fineness and underlayer words
            // stay offered where it is.
            assert!(!slots[&WorkPlanSlot::Fineness].is_empty(), "{form}");
        }
    }
    assert_eq!(closed, 23);

    let (plan, diagnostics) = normalize_work_plan(&json!({"layers": [
        {"shape": "square", "action": "place", "count": 1, "surface": "brushmarks",
         "fineness": "packed", "underlayer": "underpainted"},
        {"shape": "line", "action": "draw", "count": 1, "surface": "brushmarks"},
    ]}));
    let attribute = |layer: usize, slot: WorkPlanSlot| {
        plan.layers[layer].attributes.get(&slot).map(String::as_str)
    };
    assert_eq!(attribute(0, WorkPlanSlot::Surface), Some("brushmarks"));
    assert_eq!(attribute(0, WorkPlanSlot::Fineness), Some("packed"));
    assert_eq!(attribute(0, WorkPlanSlot::Underlayer), Some("underpainted"));
    assert_eq!(attribute(1, WorkPlanSlot::Surface), None);
    let reasons: Vec<(Option<usize>, &str, &str)> = diagnostics
        .iter()
        .map(|diagnostic| {
            (
                diagnostic.layer,
                diagnostic.field.as_str(),
                diagnostic.reason,
            )
        })
        .collect();
    assert_eq!(reasons, vec![(Some(1), "surface", "unsupported_for_form")]);
}

/// A brushmarks layer prints where a sweep prints, in both languages, and
/// compiles with no diagnostic on every closed shape.
#[test]
fn a_brushmarks_layer_prints_and_compiles_cleanly() {
    let layer_of = |shape: &str| WorkPlanLayer {
        shape: shape.to_owned(),
        action: "place".to_owned(),
        count: 1,
        attributes: [
            (WorkPlanSlot::Color, "red"),
            (WorkPlanSlot::Tool, "pen"),
            (WorkPlanSlot::Handling, "faint"),
            (WorkPlanSlot::Surface, "brushmarks"),
        ]
        .iter()
        .map(|(slot, value)| (*slot, (*value).to_owned()))
        .collect(),
        ..WorkPlanLayer::default()
    };
    for shape in CLOSED {
        for language in [JA, EN] {
            let plan = WorkPlan {
                layers: vec![layer_of(shape)],
                ..WorkPlan::default()
            };
            let source = print_work_plan(&plan, language);
            assert!(
                work_plan_source_compiles_cleanly(&source, language),
                "{language:?}: {source}"
            );
        }
    }
    let plan = WorkPlan {
        layers: vec![layer_of("circle")],
        ..WorkPlan::default()
    };
    assert_eq!(
        print_work_plan(&plan, JA),
        "赤のペンの薄い刷毛目の円を1個置く。"
    );
    assert_eq!(
        print_work_plan(&plan, EN),
        "Place one red pen faint brushmarks circle."
    );
}
