//! Sealed, runtime-disconnected object and placement recipes; never instances or Score.

use inku_score::{
    AnchorPoint, CanvasGroundSpec, Color, ConnectedPositionAuthority, LineStyle, Primitive,
    RelationGap, RelationType, SurfaceIntensity, SurfaceSpec, Thinness, TouchingConstraints,
    Variation, Weight,
};

pub use crate::score_lowering::{Rational, ResolvedGeometryDimensions};
use crate::{
    CoreModifierValue, ScoreAnchorOrigin, ScoreErrorPolicy, ScoreInstructionOrigin,
    ScoreLoweringContext, ScoreLoweringDiagnostic, SemanticExplicitGeometry,
    SemanticNumericPosition, VerifiedStage15EffectiveView,
};

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum PlacementAction {
    Place,
    LineUp,
    Tile,
    Scatter,
    Fill,
}

#[derive(Clone, Debug, PartialEq)]
pub struct PlacementGroupPlan {
    pub(crate) group_index: usize,
    pub(crate) placement: inku_score::PlacementGroup,
    pub(crate) logical_count: u64,
    pub(crate) domain: [Rational; 2],
    pub(crate) recipe: PlacementRecipe,
    pub(crate) members: Vec<PlacementMemberPlan>,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum PlacementMemberKind {
    Primitive,
    Macro,
}

/// Source-head occurrence count is distinct from the body's internal Emit counts.
#[derive(Clone, Debug, PartialEq)]
pub struct PlacementMemberPlan {
    pub(crate) source_instruction_index: usize,
    pub(crate) member: inku_score::PlacementMember,
    pub(crate) kind: PlacementMemberKind,
    pub(crate) source_count: u32,
    pub(crate) count_was_omitted: bool,
}

impl PlacementMemberPlan {
    pub const fn source_instruction_index(&self) -> usize {
        self.source_instruction_index
    }
    pub const fn member(&self) -> &inku_score::PlacementMember {
        &self.member
    }
    pub const fn kind(&self) -> PlacementMemberKind {
        self.kind
    }
    pub const fn logical_count(&self) -> u32 {
        self.source_count
    }
    /// Primitive object.count already supplies its independent slots. A Macro body
    /// supplies one slot per whole-body repetition, retaining every internal count.
    pub const fn body_repeat_count(&self) -> u32 {
        match self.kind {
            PlacementMemberKind::Primitive => 1,
            PlacementMemberKind::Macro => self.source_count,
        }
    }
    pub const fn count_was_omitted(&self) -> bool {
        self.count_was_omitted
    }
}

impl PlacementGroupPlan {
    pub const fn group_index(&self) -> usize {
        self.group_index
    }
    pub fn members(&self) -> &[PlacementMemberPlan] {
        &self.members
    }
    pub const fn placement(&self) -> &inku_score::PlacementGroup {
        &self.placement
    }
    pub const fn logical_count(&self) -> u64 {
        self.logical_count
    }
    pub const fn domain(&self) -> [Rational; 2] {
        self.domain
    }
    /// Apply once over source-ordered logical members. Primitive recipes are local Place;
    /// Macro bodies retain their own recipes and finish before outer member placement.
    /// After layout, translate the group's bounds center to `placement.at`, including
    /// Scatter: the ordinary object's sampled-centroid pivot does not apply here.
    pub const fn recipe(&self) -> &PlacementRecipe {
        &self.recipe
    }
}

/// A deferred Macro rotation over the half-open object range it owns.
///
/// The renderer materializes members and resolves named placement before it computes this
/// group's pre-rotation bounds and applies the rigid rotation. `provenance` keeps the generated
/// Transform node that declared the group distinct from its member Emit owners.
#[derive(Clone, Debug, PartialEq)]
pub struct TransformGroupPlan {
    pub(crate) start: usize,
    pub(crate) end: usize,
    pub(crate) rotation_degrees: f64,
    pub(crate) scale_x: f64,
    pub(crate) scale_y: f64,
    pub(crate) translate_x: f64,
    pub(crate) translate_y: f64,
    pub(crate) fixed_position_indices: Vec<usize>,
    pub(crate) anchor_indices: Vec<usize>,
    pub(crate) provenance: crate::GeneratedNodeProvenance,
}

/// Deferred relation intent between symbolic objects.
#[derive(Clone, Debug, PartialEq)]
pub struct PlanRelation {
    pub(crate) kind: RelationType,
    pub(crate) gap: RelationGap,
    pub(crate) target_object_index: Option<usize>,
    pub(crate) target_anchor_index: Option<usize>,
    pub(crate) position_authority: Option<ConnectedPositionAuthority>,
    pub(crate) touching_constraints: Option<TouchingConstraints>,
}

impl PlanRelation {
    pub const fn kind(&self) -> RelationType {
        self.kind
    }

    pub const fn gap(&self) -> RelationGap {
        self.gap
    }

    pub const fn target_object_index(&self) -> Option<usize> {
        self.target_object_index
    }

    pub const fn target_anchor_index(&self) -> Option<usize> {
        self.target_anchor_index
    }

    pub const fn position_authority(&self) -> Option<ConnectedPositionAuthority> {
        self.position_authority
    }

    pub const fn touching_constraints(&self) -> Option<TouchingConstraints> {
        self.touching_constraints
    }
}

impl TransformGroupPlan {
    pub const fn start(&self) -> usize {
        self.start
    }

    pub const fn end(&self) -> usize {
        self.end
    }

    pub const fn rotation_degrees(&self) -> f64 {
        self.rotation_degrees
    }

    pub const fn scale_x(&self) -> f64 {
        self.scale_x
    }

    pub const fn scale_y(&self) -> f64 {
        self.scale_y
    }

    pub const fn translate_x(&self) -> f64 {
        self.translate_x
    }

    pub const fn translate_y(&self) -> f64 {
        self.translate_y
    }

    pub fn fixed_position_indices(&self) -> &[usize] {
        &self.fixed_position_indices
    }

    pub fn anchor_indices(&self) -> &[usize] {
        &self.anchor_indices
    }

    pub const fn provenance(&self) -> &crate::GeneratedNodeProvenance {
        &self.provenance
    }
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

/// Region authority is distinct from the placement anchor of a repeated object.
#[derive(Clone, Debug, PartialEq)]
pub enum FillRegionOwner {
    OmittedCanvas,
    ExplicitCanvas(crate::SourceOccurrence),
    Named(crate::SemanticIdentity),
    InlineShape {
        source_instruction_index: usize,
        source: crate::SourceOccurrence,
    },
}

#[derive(Clone, Debug, PartialEq)]
pub enum FillRegionGeometry {
    /// Exact normalized canvas axes, not an anchor sampling box.
    Rectangle { bounds: [Rational; 4] },
    /// The target's own geometry and placement. Performance resolves its contour
    /// once, then uses that same contour for sampling and clipping all members.
    Shape {
        primitive: Primitive,
        dimensions: ResolvedGeometryDimensions,
        arc_form: Option<inku_score::ArcForm>,
        anchor: ObjectAnchor,
        rotation_degrees: Option<f64>,
        /// Declared contour variation never changes reference_area. The target
        /// is geometry, so it requires no color, surface or drawing tool.
        contour_variation: Option<Variation>,
    },
}

#[derive(Clone, Debug, PartialEq)]
pub struct ResolvedFillRegion {
    pub owner: FillRegionOwner,
    pub geometry: FillRegionGeometry,
    /// Canvas-short-edge units squared. Cloudform uses its declared reference
    /// envelope, never the performance-dependent ink/contour area.
    pub reference_area: Rational,
}

#[derive(Clone, Debug, PartialEq)]
pub enum FillCountResolution {
    Explicit,
    /// ceil(reference_area / reference_extent²), with a minimum of one.
    /// Extent is resolved geometry, independent of ink, tool and opacity.
    FromRegionAndExtent {
        reference_extent: Rational,
    },
    /// One density budget across source-ordered kinds. Explicit counts survive;
    /// omitted kinds share the remaining footprint budget equally, at least one
    /// each, with source-order remainders.
    BalancedGroup {
        reference_extents: Vec<Rational>,
        explicit_counts: Vec<Option<u32>>,
    },
}

#[derive(Clone, Debug, PartialEq)]
pub struct FillGroupPlan {
    pub owner: FillPlanOwner,
    pub logical_count: u64,
    pub members: Vec<PlacementMemberPlan>,
    /// One region/clip for all members; local Place anchors are not sampled a
    /// second time. External relations preserve the region or only the relation
    /// is omitted. The region and contents share every outer Transform.
    pub recipe: PlacementRecipe,
}

#[derive(Clone, Copy, Debug, Eq, Ord, PartialEq, PartialOrd)]
pub enum FillPlanOwner {
    CoordinatedGroup { group_index: usize },
    Instruction { source_instruction_index: usize },
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
        columns: u64,
        rows: u64,
        filled_count: u64,
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
    /// Exactly object.count independent uniform centers in the target region;
    /// clip each complete drawable at the target contour. No centroid translation,
    /// fit, resizing, grid or materialization occurs in Step 10. The enclosing
    /// Transform applies to the region and its contents together in Step 11.
    /// This region is authoritative; the object's ordinary placement domain and
    /// anchor must not translate the sampled centers out of it.
    FillUniformInRegionAndClip {
        region: Box<ResolvedFillRegion>,
        count_resolution: FillCountResolution,
    },
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
    pub(crate) relation: Option<PlanRelation>,
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
    pub fn relation(&self) -> Option<&PlanRelation> {
        self.relation.as_ref()
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
    pub(crate) anchors: Vec<AnchorPoint>,
    pub(crate) anchor_origins: Vec<ScoreAnchorOrigin>,
    pub(crate) transform_groups: Vec<TransformGroupPlan>,
    pub(crate) placement_groups: Vec<PlacementGroupPlan>,
    pub(crate) fill_groups: Vec<FillGroupPlan>,
    pub(crate) standalone_macro_repetitions: Vec<PlacementMemberPlan>,
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
    pub fn transform_groups(&self) -> &[TransformGroupPlan] {
        &self.transform_groups
    }
    pub fn placement_groups(&self) -> &[PlacementGroupPlan] {
        &self.placement_groups
    }
    pub fn fill_groups(&self) -> &[FillGroupPlan] {
        &self.fill_groups
    }
    /// Repeat each complete body symbolically with its existing positions. These
    /// ranges are outside coordinated placement, and add no layout or anchor.
    pub fn standalone_macro_repetitions(&self) -> &[PlacementMemberPlan] {
        &self.standalone_macro_repetitions
    }
    pub fn anchors(&self) -> &[AnchorPoint] {
        &self.anchors
    }
    pub fn anchor_origins(&self) -> &[ScoreAnchorOrigin] {
        &self.anchor_origins
    }
    pub fn ground(&self) -> Option<&CanvasGroundSpec> {
        self.ground.as_ref()
    }
}

pub fn plan_verified_stage15<'a>(
    view: VerifiedStage15EffectiveView<'a>,
    context: ScoreLoweringContext,
) -> CompositionPlanResult<'a> {
    plan_verified_stage15_with_policy(view, context, ScoreErrorPolicy::default())
}

pub fn plan_verified_stage15_with_policy<'a>(
    view: VerifiedStage15EffectiveView<'a>,
    context: ScoreLoweringContext,
    policy: ScoreErrorPolicy,
) -> CompositionPlanResult<'a> {
    crate::score_lowering::resolve_composition_plan(view, context, policy)
}
