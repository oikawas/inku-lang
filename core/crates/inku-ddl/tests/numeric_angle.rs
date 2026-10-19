//! An angle written in numbers (stage B-4a): `回転30度` / `rotated 30 degrees`
//! turns every mark of its instruction by that many degrees, clockwise on the
//! canvas, as the Score's rotation.

use inku_ddl::{
    CompositionPlanOutcome, MacroDefinition, MacroExpansionLimits, MacroLock,
    NormalizedDdlDocument, ResolvedInstructionLanguage, ScoreErrorPolicy, ScoreFieldGap,
    ScoreLoweringContext, ScoreLoweringOutcome, compile_ddl_to_score_with_resources,
    compile_typed_ddl, plan_verified_stage15_with_policy, stage15_transformation_input,
    transform_stage15,
};
use inku_score::{
    Color, HardResourcePolicy, Instruction, OperationalResourceBudget, Primitive, ResourceBudget,
    ResourceDemand, Score,
};
use serde_json::json;

const LIMITS: MacroExpansionLimits = MacroExpansionLimits {
    max_invocations: 8,
    max_depth: 8,
    max_evaluation_steps: 128,
    max_nodes_per_invocation: 32,
    max_total_nodes: 64,
};

fn policy() -> HardResourcePolicy {
    HardResourcePolicy {
        identity: "numeric-angle-test.v1".into(),
        budget: ResourceBudget {
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
        },
    }
}

fn language(source: &str) -> ResolvedInstructionLanguage {
    if source.is_ascii() {
        ResolvedInstructionLanguage::En
    } else {
        ResolvedInstructionLanguage::Ja
    }
}

struct Compiled {
    outcome: ScoreLoweringOutcome,
    /// None when every instruction was left out.
    score: Option<Score>,
    gaps: Vec<ScoreFieldGap>,
    upstream: Vec<String>,
}

fn compile(source: &str, canvas: &str) -> Compiled {
    let hard = policy();
    let result = compile_ddl_to_score_with_resources(
        NormalizedDdlDocument::new(source, language(source), Vec::new()).unwrap(),
        &[],
        Some(19),
        LIMITS,
        ScoreLoweringContext::resolve(canvas, Color::White).unwrap(),
        ScoreErrorPolicy::OmitAndContinue,
        hard.clone(),
        OperationalResourceBudget(hard.budget),
    );
    Compiled {
        outcome: result.outcome(),
        score: result.score().cloned(),
        gaps: result
            .downstream_diagnostics()
            .iter()
            .map(|diagnostic| diagnostic.reason.clone())
            .collect(),
        upstream: result
            .upstream_diagnostics()
            .iter()
            .map(|diagnostic| diagnostic.reason.clone())
            .collect(),
    }
}

/// The Score of a document that compiles whole.
fn score(source: &str, canvas: &str) -> Score {
    let compiled = compile(source, canvas);
    assert!(
        compiled.upstream.is_empty(),
        "{source}: {:?}",
        compiled.upstream
    );
    assert!(compiled.gaps.is_empty(), "{source}: {:?}", compiled.gaps);
    assert_eq!(compiled.outcome, ScoreLoweringOutcome::Complete, "{source}");
    compiled.score.unwrap_or_else(|| panic!("{source}"))
}

fn only(score: &Score) -> &Instruction {
    assert_eq!(score.instructions.len(), 1, "{:?}", score.instructions);
    &score.instructions[0]
}

#[test]
fn a_numeric_angle_turns_a_placed_mark() {
    let square = score(
        "画面の横0.5、縦0.5の位置に、一辺0.1の回転30度の赤い四角を1個置く。",
        "square",
    );
    let instruction = only(&square);
    assert_eq!(instruction.primitive, Primitive::Square);
    assert_eq!(instruction.rotation, Some(30.0));
    // English writes it after the noun, as a numeric size.
    for english in [
        "Place one red square side length 0.1 rotated 30 degrees at horizontal 0.5, vertical 0.5.",
        "place one red square side length 0.1 Rotated 30 Degrees at horizontal 0.5, vertical 0.5.",
    ] {
        assert_eq!(
            score(english, "square").instructions,
            square.instructions,
            "{english}"
        );
    }
    // Full-width digits, a decimal and one degree.
    for (source, degrees) in [
        (
            "画面の横0.5、縦0.5の位置に、回転３０度の赤い四角を1個置く。",
            30.0,
        ),
        (
            "画面の横0.5、縦0.5の位置に、回転22.5度の赤い楕円を1個置く。",
            22.5,
        ),
        (
            "画面の横0.5、縦0.5の位置に、回転359.999999度の赤い三角を1個置く。",
            359.999999,
        ),
        (
            "Place one red ellipse rotated 1 degree at horizontal 0.5, vertical 0.5.",
            1.0,
        ),
        (
            "Place one red cloudform rotated 0 degrees at horizontal 0.5, vertical 0.5.",
            0.0,
        ),
    ] {
        assert_eq!(
            only(&score(source, "square")).rotation,
            Some(degrees),
            "{source}"
        );
    }
    // A wide canvas keeps the degrees: the rotation is turned in short-edge units.
    assert_eq!(
        only(&score(
            "画面の横0.5、縦0.5の位置に、回転30度の赤い四角を1個置く。",
            "wide"
        ))
        .rotation,
        Some(30.0)
    );
}

#[test]
fn every_mark_of_a_row_a_tile_and_a_scatter_turns() {
    for (source, count) in [
        (
            "画面の横0.1、縦0.5から横0.9、縦0.5まで、回転45度の黒い四角を5個並べる。",
            5,
        ),
        (
            "画面の横0.1〜0.9、縦0.1〜0.9の範囲に、回転45度の黒い四角を9個敷き詰める。",
            9,
        ),
        (
            "画面の横0.1〜0.9、縦0.1〜0.9の範囲に、回転45度の黒い四角を9個散らす。",
            9,
        ),
        (
            "Tile 9 black squares rotated 45 degrees in the range horizontal 0.1 to 0.9, vertical 0.1 to 0.9.",
            9,
        ),
    ] {
        let score = score(source, "square");
        assert_eq!(only(&score).rotation, Some(45.0), "{source}");
        assert_eq!(
            only(&score).arrangement.as_ref().unwrap().count,
            count,
            "{source}"
        );
    }
}

#[test]
fn an_arc_turns_and_waxing_adds_its_quarter_turn() {
    assert_eq!(
        only(&score(
            "画面の横0.5、縦0.5の位置に、回転30度の青い弧を1個置く。",
            "square"
        ))
        .rotation,
        Some(30.0)
    );
    assert_eq!(
        only(&score(
            "画面の横0.5、縦0.5の位置に、回転30度の上弦の青い弧を1個置く。",
            "square"
        ))
        .rotation,
        Some(120.0)
    );
}

#[test]
fn a_line_turns_by_its_numeric_angle() {
    let line = score(
        "画面の横0.5、縦0.5の位置に、長さ0.5の回転30度の黒い線を1本引く。",
        "square",
    );
    assert_eq!(only(&line).primitive, Primitive::Line);
    assert_eq!(only(&line).rotation, Some(30.0));
}

#[test]
fn the_seeded_angle_word_alone_is_still_an_angle_word() {
    let seeded = score(
        "画面の横0.5、縦0.5の位置に、回転の黒い四角を1個置く。",
        "square",
    );
    let rotation = only(&seeded).rotation.expect("a seeded rotation");
    // Away from the multiples of 45 degrees, by the word's own rule.
    assert!(
        (rotation.rem_euclid(45.0) - 22.5).abs() <= 17.0,
        "{rotation}"
    );
}

#[test]
fn what_a_numeric_angle_cannot_do_is_left_out_with_its_reason() {
    // A point takes no angle.
    let point = compile(
        "画面の横0.5、縦0.5の位置に、回転30度の白い点を1個置く。",
        "square",
    );
    assert_eq!(
        point.gaps,
        vec![ScoreFieldGap::UnsupportedAngleForPrimitive {
            primitive: Primitive::Point
        }]
    );
    // One line between two points has its direction from them.
    let segment = compile(
        "画面の横0.1、縦0.1から横0.9、縦0.9まで、回転30度の黒い線を1本引く。",
        "square",
    );
    assert_eq!(segment.gaps, vec![ScoreFieldGap::NumericSegmentConflict]);
    // An angle word and a numeric angle are two angles.
    for source in [
        "画面の横0.5、縦0.5の位置に、回転30度の斜めの黒い四角を1個置く。",
        "画面の横0.5、縦0.5の位置に、回転30度の回転45度の黒い四角を1個置く。",
        "Place one black diagonal square rotated 30 degrees at horizontal 0.5, vertical 0.5.",
    ] {
        let compilation = compile_typed_ddl(
            NormalizedDdlDocument::new(source, language(source), Vec::new()).unwrap(),
            &[],
            Some(19),
            LIMITS,
        );
        assert!(
            compilation
                .conflicts
                .iter()
                .any(|conflict| conflict.kind == "conflicting_angles"),
            "{source}: {:?} {:?}",
            compilation.conflicts,
            compilation.blocking_diagnostics
        );
    }
}

#[test]
fn an_angle_of_a_full_turn_or_more_is_not_an_angle() {
    for source in [
        "画面の横0.5、縦0.5の位置に、回転360度の四角を1個置く。",
        "画面の横0.5、縦0.5の位置に、回転12.3456789度の四角を1個置く。",
        "Place one square rotated 400 degrees at horizontal 0.5, vertical 0.5.",
    ] {
        let compilation = compile_typed_ddl(
            NormalizedDdlDocument::new(source, language(source), Vec::new()).unwrap(),
            &[],
            Some(19),
            LIMITS,
        );
        assert!(
            compilation
                .blocking_diagnostics
                .iter()
                .any(|diagnostic| diagnostic.kind == "invalid_numeric_angle"),
            "{source}: {:?}",
            compilation.blocking_diagnostics
        );
    }
}

#[test]
fn a_mirror_follower_takes_its_numeric_angle_as_an_angle_word() {
    let worded = compile(
        "左端に斜めの赤い弧を置く。右端に前の形と鏡写しの青い弧を置く。",
        "square",
    );
    let numeric = compile(
        "左端に回転45度の赤い弧を置く。右端に前の形と鏡写しの青い弧を置く。",
        "square",
    );
    assert!(numeric.upstream.is_empty(), "{:?}", numeric.upstream);
    assert_eq!(numeric.gaps, worded.gaps);
    let numeric = numeric.score.unwrap();
    assert_eq!(numeric.instructions[0].rotation, Some(45.0));
    assert_eq!(
        numeric.instructions.len(),
        worded.score.unwrap().instructions.len()
    );
    // Written on the mirrored sentence itself, as an angle word would be.
    let worded = compile(
        "左端に赤い弧を置く。右端に前の形と鏡写しの斜めの青い弧を置く。",
        "square",
    );
    let numeric = compile(
        "左端に赤い弧を置く。右端に前の形と鏡写しの回転45度の青い弧を置く。",
        "square",
    );
    assert_eq!(numeric.upstream, worded.upstream);
    assert_eq!(numeric.gaps, worded.gaps);
    assert_eq!(
        numeric.score.map(|score| score.instructions.len()),
        worded.score.map(|score| score.instructions.len())
    );
}

#[test]
fn a_macro_caller_has_nowhere_to_bind_an_angle() {
    let definition = MacroDefinition::from_json(
        &json!({
            "schema":"inku.macro-definition.v1", "namespace":"Draw", "heading":"Row", "version":"1.0.0",
            "parameters":{}, "components":{}, "body":[{"op":"emit","binding":null,"fields":{
                "shape":{"expr":"semantic_ref","category":"shape","id":"circle"},
                "movement":{"expr":"semantic_ref","category":"movement","id":"line_up"},
                "place":{"expr":"semantic_ref","category":"place","id":"center"},
                "count":{"expr":"integer","value":3}
            }}]
        })
        .to_string(),
    )
    .unwrap();
    let identity = definition.identity().unwrap();
    let lock = MacroLock::new(
        identity.qualified_name(),
        identity.version(),
        format!("sha256:{}", identity.full_digest_hex()),
    )
    .unwrap();
    let compilation = compile_typed_ddl(
        NormalizedDdlDocument::new(
            "Draw.Row rotated 30 degrees",
            ResolvedInstructionLanguage::En,
            vec![lock],
        )
        .unwrap(),
        std::slice::from_ref(&definition),
        Some(19),
        LIMITS,
    );
    let transformed = transform_stage15(
        stage15_transformation_input(&compilation)
            .unwrap_or_else(|error| panic!("{error:?}: {:?}", compilation.blocking_diagnostics)),
    )
    .unwrap();
    let result = plan_verified_stage15_with_policy(
        transformed.verified_effective_view(),
        ScoreLoweringContext::resolve("square", Color::White).unwrap(),
        ScoreErrorPolicy::OmitAndContinue,
    );
    assert_eq!(result.outcome(), CompositionPlanOutcome::Stopped);
    assert!(
        result
            .diagnostics()
            .iter()
            .any(|diagnostic| diagnostic.reason == ScoreFieldGap::UnboundMacroCallerMeaning),
        "{:?}",
        result.diagnostics()
    );
}
