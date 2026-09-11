//! Sealed, runtime-disconnected object and placement recipes; never instances or Score.

use inku_score::{
    CanvasGroundSpec, Color, LineStyle, Primitive, SurfaceIntensity, SurfaceSpec, Thinness,
    Variation, Weight,
};

pub use crate::score_lowering::{Rational, ResolvedGeometryDimensions};
use crate::{
    CoreModifierValue, ScoreErrorPolicy, ScoreInstructionOrigin, ScoreLoweringContext,
    ScoreLoweringDiagnostic, SemanticExplicitGeometry, SemanticNumericPosition,
    VerifiedStage15EffectiveView,
};

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum PlacementAction {
    Place,
    LineUp,
    Tile,
    Scatter,
}

#[derive(Clone, Debug, PartialEq)]
pub struct ResolvedObjectAppearance {
    pub color: Color,
    pub touch: Weight,
    pub continuity: LineStyle,
    pub filled: bool,
    pub surface: Option<SurfaceSpec>,
    pub surface_intensity: SurfaceIntensity,
    pub thinness: Option<Thinness>,
    pub fluctuation: Option<Variation>,
}

#[derive(Clone, Debug, PartialEq)]
pub enum ObjectAnchor {
    /// Generated exact coordinates; the enclosing plan retains the MacroEmit owner.
    GeneratedNumeric(crate::geometry::ExactPosition),
    /// Original exact coordinates, basis and provenance, including must-fit authority.
    Numeric(SemanticNumericPosition),
    /// Existing finite named-region resolution; performance chooses the anchor.
    Named([f64; 4]),
}

#[derive(Clone, Debug, PartialEq)]
pub enum PlacementRecipe {
    Place,
    /// x(i) = (i + 1/2) * cell_width; y(i) = domain_height / 2.
    /// Translate the group centroid to the semantic anchor.
    HorizontalLine {
        cell_width: Rational,
    },
    VerticalLine {
        cell_height: Rational,
    },
    /// Physical 45-degree steps; the centroid is translated to the semantic anchor.
    DiagonalLine {
        step: [Rational; 2],
    },
    /// Row-major filled prefix. No instances or trailing empty cells are allocated.
    Grid {
        columns: u32,
        rows: u32,
        filled_count: u32,
        cell_width: Rational,
        cell_height: Rational,
        /// Exact filled-prefix centroid in domain coordinates; numeric anchors translate it.
        centroid: [Rational; 2],
        translate_to_numeric_anchor: bool,
    },
    /// Independently uniform X/Y sampling over the domain. Materialization reuses the
    /// renderer sampler and existing performance seed with this owner's instance ordinal,
    /// then translates the sampled centroid to the semantic anchor. No RNG runs here.
    ScatterUniformWithCentroidTranslation,
}

#[derive(Clone, Debug, PartialEq)]
pub struct ObjectPlacementPlan {
    pub(crate) generated_geometries: Vec<crate::geometry::ExactGeometry>,
    pub(crate) arc_form: Option<inku_score::ArcForm>,
    pub(crate) proportion_width_extent: Option<crate::SemanticIdentity>,
    pub(crate) additional_relative_scales: Vec<crate::SemanticRelativeScale>,
    pub(crate) additional_explicit_geometries: Vec<SemanticExplicitGeometry>,
    pub(crate) additional_width_extents: Vec<crate::SemanticTerm>,
    pub(crate) shape_constraint: Option<crate::ShapeConstraint>,
    pub(crate) proportion_aspect: Option<crate::SemanticIdentity>,
    pub(crate) origin: ScoreInstructionOrigin,
    pub(crate) primitive: Primitive,
    pub(crate) count: u32,
    pub(crate) count_was_omitted: bool,
    pub(crate) dimensions: ResolvedGeometryDimensions,
    pub(crate) explicit_geometry: Option<SemanticExplicitGeometry>,
    pub(crate) relative_scale: Option<CoreModifierValue>,
    pub(crate) appearance: ResolvedObjectAppearance,
    pub(crate) angle: Option<f64>,
    pub(crate) layout_direction: Option<ResolvedLayoutDirection>,
    pub(crate) anchor: ObjectAnchor,
    pub(crate) domain: [Rational; 2],
    pub(crate) recipe: PlacementRecipe,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ResolvedLayoutDirection {
    pub identity: crate::SemanticIdentity,
    /// Signed physical axes. Y increases downwards; rising is [1, -1].
    pub axis: [i8; 2],
}

impl ObjectPlacementPlan {
    pub fn generated_geometries(&self) -> &[crate::geometry::ExactGeometry] {
        &self.generated_geometries
    }
    pub fn arc_form(&self) -> Option<inku_score::ArcForm> {
        self.arc_form
    }
    pub fn proportion_width_extent(&self) -> Option<&crate::SemanticIdentity> {
        self.proportion_width_extent.as_ref()
    }
    pub fn additional_relative_scales(&self) -> &[crate::SemanticRelativeScale] {
        &self.additional_relative_scales
    }
    pub fn additional_explicit_geometries(&self) -> &[SemanticExplicitGeometry] {
        &self.additional_explicit_geometries
    }
    pub fn additional_width_extents(&self) -> &[crate::SemanticTerm] {
        &self.additional_width_extents
    }
    pub fn shape_constraint(&self) -> Option<crate::ShapeConstraint> {
        self.shape_constraint
    }
    pub fn proportion_aspect(&self) -> Option<&crate::SemanticIdentity> {
        self.proportion_aspect.as_ref()
    }
    pub fn origin(&self) -> &ScoreInstructionOrigin {
        &self.origin
    }
    pub fn primitive(&self) -> Primitive {
        self.primitive
    }
    pub fn count(&self) -> u32 {
        self.count
    }
    pub fn count_was_omitted(&self) -> bool {
        self.count_was_omitted
    }
    pub fn dimensions(&self) -> ResolvedGeometryDimensions {
        self.dimensions
    }
    pub fn explicit_geometry(&self) -> Option<&SemanticExplicitGeometry> {
        self.explicit_geometry.as_ref()
    }
    pub fn relative_scale(&self) -> Option<CoreModifierValue> {
        self.relative_scale
    }
    pub fn appearance(&self) -> &ResolvedObjectAppearance {
        &self.appearance
    }
    pub fn angle(&self) -> Option<f64> {
        self.angle
    }
    pub fn layout_direction(&self) -> Option<&ResolvedLayoutDirection> {
        self.layout_direction.as_ref()
    }
    pub fn anchor(&self) -> &ObjectAnchor {
        &self.anchor
    }
    /// Domain physical dimensions in canvas-short-edge units.
    pub fn domain(&self) -> [Rational; 2] {
        self.domain
    }
    pub fn recipe(&self) -> &PlacementRecipe {
        &self.recipe
    }
    pub fn requires_numeric_must_fit(&self) -> bool {
        matches!(
            self.anchor,
            ObjectAnchor::Numeric(_) | ObjectAnchor::GeneratedNumeric(_)
        )
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum CompositionPlanOutcome {
    Ready,
    ReadyWithOmissions,
    Stopped,
}

/// Construction is private: Ready can only come from the verified Stage 1.5 entrance.
pub struct CompositionPlanResult<'a> {
    pub(crate) view: VerifiedStage15EffectiveView<'a>,
    pub(crate) context: ScoreLoweringContext,
    pub(crate) policy_digest: String,
    pub(crate) error_policy: ScoreErrorPolicy,
    pub(crate) outcome: CompositionPlanOutcome,
    pub(crate) objects: Vec<ObjectPlacementPlan>,
    pub(crate) ground: Option<CanvasGroundSpec>,
    pub(crate) diagnostics: Vec<ScoreLoweringDiagnostic>,
}

impl<'a> CompositionPlanResult<'a> {
    pub fn verified_effective_view(&self) -> VerifiedStage15EffectiveView<'a> {
        self.view
    }
    pub fn context(&self) -> ScoreLoweringContext {
        self.context
    }
    pub fn policy_digest(&self) -> &str {
        &self.policy_digest
    }
    pub fn error_policy(&self) -> ScoreErrorPolicy {
        self.error_policy
    }
    pub fn outcome(&self) -> CompositionPlanOutcome {
        self.outcome
    }
    pub fn objects(&self) -> Option<&[ObjectPlacementPlan]> {
        (self.outcome != CompositionPlanOutcome::Stopped).then_some(&self.objects)
    }
    pub fn diagnostics(&self) -> &[ScoreLoweringDiagnostic] {
        &self.diagnostics
    }
    pub fn ground(&self) -> Option<&CanvasGroundSpec> {
        self.ground.as_ref()
    }
}

pub fn plan_verified_stage15<'a>(
    view: VerifiedStage15EffectiveView<'a>,
    context: ScoreLoweringContext,
) -> CompositionPlanResult<'a> {
    plan_verified_stage15_with_policy(view, context, ScoreErrorPolicy::Stop)
}

pub fn plan_verified_stage15_with_policy<'a>(
    view: VerifiedStage15EffectiveView<'a>,
    context: ScoreLoweringContext,
    policy: ScoreErrorPolicy,
) -> CompositionPlanResult<'a> {
    crate::score_lowering::resolve_composition_plan(view, context, policy)
}
