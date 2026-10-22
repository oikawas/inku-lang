//! Texture words (DDL 24). A fineness word (きめ: 細かい・粗い・密な・疎な) sets
//! the scale or the density of a named texture on a closed shape, and the
//! underlayer word (したじ: 下塗り) lays the tool's paint under it. On any other
//! mark the word says nothing: only that word is left out, with its own
//! reason, and the rest of the sentence lowers as it does without it. An
//! amplitude word (細かく・大きく) without a sway word (揺れる・波打つ) makes no
//! sway, and is left out the same way.

use inku_ddl::{
    MacroExpansionLimits, NormalizedDdlDocument, ResolvedInstructionLanguage, ScoreErrorPolicy,
    ScoreFieldGap, ScoreLoweringContext, ScoreLoweringOutcome, compile_ddl_to_score_with_resources,
};
use inku_score::{
    Amplitude, Color, HardResourcePolicy, Instruction, OperationalResourceBudget, Quality,
    ResourceBudget, ResourceDemand, Score, SurfaceIntensity, SurfaceTexture,
};

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
        identity: "texture-words-test.v1".into(),
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

/// What a sample sentence's one mark is lowered to.
struct Expected {
    texture: SurfaceTexture,
    scale: f64,
    density: f64,
    filled: bool,
    intensity: SurfaceIntensity,
}

const DEFAULT_SCALE: f64 = 0.35;
const DEFAULT_DENSITY: f64 = 0.35;

fn texture(texture: SurfaceTexture) -> Expected {
    Expected {
        texture,
        scale: DEFAULT_SCALE,
        density: DEFAULT_DENSITY,
        filled: false,
        intensity: SurfaceIntensity::Normal,
    }
}

#[test]
fn a_texture_word_sets_its_field_on_a_closed_shapes_named_texture() {
    let samples = [
        (
            "中心に、赤のペンの細かい点描の円を1個置く。",
            JA,
            Expected {
                scale: 0.05,
                ..texture(SurfaceTexture::Stipple)
            },
        ),
        (
            "Place one red pen fine-grained stipple circle at the center.",
            EN,
            Expected {
                scale: 0.05,
                ..texture(SurfaceTexture::Stipple)
            },
        ),
        (
            "中心に、赤のペンの粗い粒の楕円を1個置く。",
            JA,
            Expected {
                scale: 0.90,
                ..texture(SurfaceTexture::Grain)
            },
        ),
        (
            "Place one red pen coarse-grained grain ellipse at the center.",
            EN,
            Expected {
                scale: 0.90,
                ..texture(SurfaceTexture::Grain)
            },
        ),
        (
            "中心に、赤のペンの密な平行線の四角を1個置く。",
            JA,
            Expected {
                density: 0.85,
                ..texture(SurfaceTexture::Hatch)
            },
        ),
        (
            "Place one red pen packed hatch square at the center.",
            EN,
            Expected {
                density: 0.85,
                ..texture(SurfaceTexture::Hatch)
            },
        ),
        (
            "中心に、赤のペンの疎なアクアチントの雲形を1個置く。",
            JA,
            Expected {
                density: 0.05,
                ..texture(SurfaceTexture::Aquatint)
            },
        ),
        (
            "Place one red pen sparse aquatint cloudform at the center.",
            EN,
            Expected {
                density: 0.05,
                ..texture(SurfaceTexture::Aquatint)
            },
        ),
        (
            "中心に、赤のペンの下塗りの点描の円を1個置く。",
            JA,
            Expected {
                filled: true,
                ..texture(SurfaceTexture::Stipple)
            },
        ),
        (
            "Place one red pen underpainted stipple circle at the center.",
            EN,
            Expected {
                filled: true,
                ..texture(SurfaceTexture::Stipple)
            },
        ),
        (
            "中心に、赤の太筆の下塗りの密な交差線の薄い四角を1個置く。",
            JA,
            Expected {
                density: 0.85,
                filled: true,
                intensity: SurfaceIntensity::Faint,
                ..texture(SurfaceTexture::Crosshatch)
            },
        ),
        (
            "Place one red thick-brush faint underpainted packed crosshatch square at the center.",
            EN,
            Expected {
                density: 0.85,
                filled: true,
                intensity: SurfaceIntensity::Faint,
                ..texture(SurfaceTexture::Crosshatch)
            },
        ),
    ];
    for (source, language, expected) in samples {
        let compiled = compile(source, language);
        assert_eq!(compiled.outcome, ScoreLoweringOutcome::Complete, "{source}");
        assert!(compiled.gaps.is_empty(), "{source}: {:?}", compiled.gaps);
        assert_eq!(compiled.upstream, 0, "{source}");
        let mark = only_instruction(&compiled, source);
        let surface = mark.surface.as_ref().expect(source);
        assert_eq!(surface.texture, expected.texture, "{source}");
        assert_eq!(surface.scale, expected.scale, "{source}");
        assert_eq!(surface.density, expected.density, "{source}");
        assert_eq!(mark.filled, expected.filled, "{source}");
        assert_eq!(mark.surface_intensity, expected.intensity, "{source}");
    }
}

#[test]
fn a_texture_word_without_a_named_texture_is_left_out_alone() {
    for (source, without, language, reason) in [
        (
            "中心に、赤の太筆の細かい刷きの線を1本引く。",
            "中心に、赤の太筆の刷きの線を1本引く。",
            JA,
            "fine_grained",
        ),
        (
            "Draw one red thick-brush fine-grained sweep line at the center.",
            "Draw one red thick-brush sweep line at the center.",
            EN,
            "fine_grained",
        ),
        (
            "中心に、赤のペンの細かい塗りの円を1個置く。",
            "中心に、赤のペンの塗りの円を1個置く。",
            JA,
            "fine_grained",
        ),
        (
            "中心に、赤のペンの疎な空の四角を1個置く。",
            "中心に、赤のペンの空の四角を1個置く。",
            JA,
            "sparse",
        ),
        (
            "中心に、赤のペンの粗い点を1個置く。",
            "中心に、赤のペンの点を1個置く。",
            JA,
            "coarse_grained",
        ),
        (
            "中心に、赤のペンの下塗りの円を1個置く。",
            "中心に、赤のペンの円を1個置く。",
            JA,
            "underpainted",
        ),
        (
            "Place one red pen underpainted flat circle at the center.",
            "Place one red pen flat circle at the center.",
            EN,
            "underpainted",
        ),
    ] {
        let compiled = compile(source, language);
        let reference = compile(without, language);
        assert_eq!(
            compiled.outcome,
            ScoreLoweringOutcome::CompleteWithOmissions,
            "{source}"
        );
        let expected = if reason == "underpainted" {
            ScoreFieldGap::UnsupportedSurfaceUnderlayer {
                category: "underlayer".into(),
                id: reason.into(),
            }
        } else {
            ScoreFieldGap::UnsupportedSurfaceFineness {
                category: "fineness".into(),
                id: reason.into(),
            }
        };
        assert_eq!(compiled.gaps, vec![expected], "{source}");
        assert_eq!(
            compiled.score.instructions, reference.score.instructions,
            "{source}"
        );
    }
}

/// One mark takes one word of each class: two conflict, and both are left out
/// as two handling words are.
#[test]
fn two_words_of_one_class_conflict_and_both_are_left_out() {
    for (source, without) in [
        (
            "中心に、赤のペンの細かい密な点描の円を1個置く。",
            "中心に、赤のペンの点描の円を1個置く。",
        ),
        (
            "中心に、赤のペンの下塗りの下塗りの点描の円を1個置く。",
            "中心に、赤のペンの点描の円を1個置く。",
        ),
    ] {
        let compiled = compile(source, JA);
        let reference = compile(without, JA);
        assert_eq!(
            compiled.outcome,
            ScoreLoweringOutcome::CompleteWithOmissions,
            "{source}"
        );
        assert_eq!(compiled.upstream, 1, "{source}");
        assert!(compiled.gaps.is_empty(), "{source}: {:?}", compiled.gaps);
        assert_eq!(
            compiled.score.instructions, reference.score.instructions,
            "{source}"
        );
    }
}

#[test]
fn an_amplitude_word_without_a_sway_word_makes_no_sway() {
    for (source, without, language, id) in [
        (
            "中心に、赤のペンの細かく点描の円を1個置く。",
            "中心に、赤のペンの点描の円を1個置く。",
            JA,
            "narrowly",
        ),
        (
            "中心に、赤のペンの大きく線を1本引く。",
            "中心に、赤のペンの線を1本引く。",
            JA,
            "broadly",
        ),
        (
            "Place one red pen narrowly stipple circle at the center.",
            "Place one red pen stipple circle at the center.",
            EN,
            "narrowly",
        ),
    ] {
        let compiled = compile(source, language);
        let reference = compile(without, language);
        assert_eq!(
            compiled.outcome,
            ScoreLoweringOutcome::CompleteWithOmissions,
            "{source}"
        );
        assert_eq!(
            compiled.gaps,
            vec![ScoreFieldGap::FluctuationAmplitudeWithoutQuality {
                category: "variation".into(),
                id: id.into(),
            }],
            "{source}"
        );
        assert!(
            only_instruction(&compiled, source).variation.is_none(),
            "{source}"
        );
        assert_eq!(
            compiled.score.instructions, reference.score.instructions,
            "{source}"
        );
    }
}

#[test]
fn an_amplitude_word_with_a_sway_word_sways_as_before() {
    for (source, language, amplitude, quality) in [
        (
            "中心に、赤のペンの細かく揺れる点描の円を1個置く。",
            JA,
            Amplitude::Fine,
            Quality::Perlin,
        ),
        (
            "中心に、赤のペンの大きく波打つ線を1本引く。",
            JA,
            Amplitude::Broad,
            Quality::Wave,
        ),
        (
            "Place one red pen narrowly swaying stipple circle at the center.",
            EN,
            Amplitude::Fine,
            Quality::Perlin,
        ),
    ] {
        let compiled = compile(source, language);
        assert_eq!(compiled.outcome, ScoreLoweringOutcome::Complete, "{source}");
        assert!(compiled.gaps.is_empty(), "{source}: {:?}", compiled.gaps);
        let variation = only_instruction(&compiled, source)
            .variation
            .as_ref()
            .expect(source);
        assert_eq!(variation.amplitude, amplitude, "{source}");
        assert_eq!(variation.quality, quality, "{source}");
    }
}
