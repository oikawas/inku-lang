//! Runtime-disconnected Score-field candidates from a verified Stage 1.5 result.

use inku_score::{Point, Primitive};

use crate::{
    CoreModifierValue, SemanticHead, SemanticIdentity, SemanticInstruction,
    VerifiedStage15EffectiveView,
};

/// Stable identity for the non-serializable Score-field candidate boundary.
pub const SCORE_FIELD_CANDIDATE_SCHEMA_ID: &str = "inku.score-field-candidate.v1";

/// A canonical semantic primitive identity that cannot be represented by Score.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ScorePrimitiveMappingError {
    category: String,
    id: String,
}

impl ScorePrimitiveMappingError {
    pub fn category(&self) -> &str {
        &self.category
    }

    pub fn id(&self) -> &str {
        &self.id
    }
}

/// Map only the closed canonical eight-shape identity into the shared Score type.
pub fn score_primitive_from_semantic_identity(
    identity: &SemanticIdentity,
) -> Result<Primitive, ScorePrimitiveMappingError> {
    let primitive = match (identity.category.as_str(), identity.id.as_str()) {
        ("shape", "line") => Primitive::Line,
        ("shape", "circle") => Primitive::Circle,
        ("shape", "ellipse") => Primitive::Ellipse,
        ("shape", "triangle") => Primitive::Triangle,
        ("shape", "square") => Primitive::Square,
        ("shape", "polygon") => Primitive::Polygon,
        ("shape", "arc") => Primitive::Arc,
        ("shape", "cloudform") => Primitive::Cloudform,
        _ => {
            return Err(ScorePrimitiveMappingError {
                category: identity.category.clone(),
                id: identity.id.clone(),
            });
        }
    };
    Ok(primitive)
}

/// Lossless exact-count intent before layout and final limits are selected.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum ExactCountFieldCandidate {
    Single,
    Repeated(u32),
}

impl ExactCountFieldCandidate {
    pub const fn value(self) -> u32 {
        match self {
            Self::Single => 1,
            Self::Repeated(value) => value,
        }
    }
}

/// The only explicit-small Score fields with authoritatively fixed values.
#[derive(Clone, Copy, Debug, PartialEq)]
pub enum ExplicitSmallSizeFieldCandidate {
    CircleRadius(f64),
    EllipseSize(Point),
}

/// Closed gaps that preserve unsupported source meaning without a fallback or clamp.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ScoreFieldGap {
    UnsupportedPrimitiveIdentity { category: String, id: String },
    MacroInvocationHead,
    ExactCountZero { value: u64 },
    ExactCountExceedsScoreRange { value: u64 },
    UnsupportedRelativeScalePrimitive { primitive: Primitive },
    UnsupportedRelativeScaleValue { value: CoreModifierValue },
}

/// Score fields owned by one source instruction; all other Score fields remain absent.
#[derive(Clone, Debug, PartialEq)]
pub struct ScoreInstructionFieldCandidate {
    source_instruction_index: usize,
    primitive: Option<Primitive>,
    exact_count: Option<ExactCountFieldCandidate>,
    explicit_small_size: Option<ExplicitSmallSizeFieldCandidate>,
    gaps: Vec<ScoreFieldGap>,
}

impl ScoreInstructionFieldCandidate {
    pub const fn source_instruction_index(&self) -> usize {
        self.source_instruction_index
    }

    pub const fn primitive(&self) -> Option<Primitive> {
        self.primitive
    }

    pub const fn exact_count(&self) -> Option<ExactCountFieldCandidate> {
        self.exact_count
    }

    pub const fn explicit_small_size(&self) -> Option<ExplicitSmallSizeFieldCandidate> {
        self.explicit_small_size
    }

    pub fn gaps(&self) -> &[ScoreFieldGap] {
        &self.gaps
    }
}

/// Non-serializable candidate that keeps the verified view and pending focus overlay intact.
#[derive(Clone, Debug)]
pub struct ScoreLoweringCandidate<'a> {
    verified_effective_view: VerifiedStage15EffectiveView<'a>,
    instructions: Vec<ScoreInstructionFieldCandidate>,
}

impl<'a> ScoreLoweringCandidate<'a> {
    pub const fn schema_id(&self) -> &'static str {
        SCORE_FIELD_CANDIDATE_SCHEMA_ID
    }

    pub const fn verified_effective_view(&self) -> VerifiedStage15EffectiveView<'a> {
        self.verified_effective_view
    }

    pub fn instructions(&self) -> &[ScoreInstructionFieldCandidate] {
        &self.instructions
    }
}

/// Lower only primitive, exact count, and authoritatively explicit-small fields.
pub fn lower_verified_stage15_view<'a>(
    view: VerifiedStage15EffectiveView<'a>,
) -> ScoreLoweringCandidate<'a> {
    let instructions = view
        .original_semantic_document()
        .instructions
        .iter()
        .enumerate()
        .map(|(instruction_index, instruction)| {
            lower_source_instruction(instruction_index, instruction)
        })
        .collect();
    ScoreLoweringCandidate {
        verified_effective_view: view,
        instructions,
    }
}

fn lower_source_instruction(
    source_instruction_index: usize,
    instruction: &SemanticInstruction,
) -> ScoreInstructionFieldCandidate {
    let mut gaps = Vec::new();
    let primitive = match &instruction.entity.head {
        SemanticHead::Primitive(term) => {
            match score_primitive_from_semantic_identity(&term.identity) {
                Ok(primitive) => Some(primitive),
                Err(error) => {
                    gaps.push(ScoreFieldGap::UnsupportedPrimitiveIdentity {
                        category: error.category,
                        id: error.id,
                    });
                    None
                }
            }
        }
        SemanticHead::MacroInvocation(_) => {
            gaps.push(ScoreFieldGap::MacroInvocationHead);
            return ScoreInstructionFieldCandidate {
                source_instruction_index,
                primitive: None,
                exact_count: None,
                explicit_small_size: None,
                gaps,
            };
        }
    };

    let exact_count =
        instruction
            .entity
            .quantity
            .as_ref()
            .and_then(|quantity| match quantity.value {
                0 => {
                    gaps.push(ScoreFieldGap::ExactCountZero { value: 0 });
                    None
                }
                1 => Some(ExactCountFieldCandidate::Single),
                value if value <= u64::from(u32::MAX) => {
                    Some(ExactCountFieldCandidate::Repeated(value as u32))
                }
                value => {
                    gaps.push(ScoreFieldGap::ExactCountExceedsScoreRange { value });
                    None
                }
            });

    let explicit_small_size = instruction
        .entity
        .relative_scale
        .as_ref()
        .and_then(|scale| match (scale.value, primitive) {
            (CoreModifierValue::Small, Some(Primitive::Circle)) => {
                Some(ExplicitSmallSizeFieldCandidate::CircleRadius(0.038))
            }
            (CoreModifierValue::Small, Some(Primitive::Ellipse)) => Some(
                ExplicitSmallSizeFieldCandidate::EllipseSize(Point::new(0.06, 0.032)),
            ),
            (CoreModifierValue::Small, Some(primitive)) => {
                gaps.push(ScoreFieldGap::UnsupportedRelativeScalePrimitive { primitive });
                None
            }
            (CoreModifierValue::Small, None) => None,
            (value, _) => {
                gaps.push(ScoreFieldGap::UnsupportedRelativeScaleValue { value });
                None
            }
        });

    ScoreInstructionFieldCandidate {
        source_instruction_index,
        primitive,
        exact_count,
        explicit_small_size,
        gaps,
    }
}
