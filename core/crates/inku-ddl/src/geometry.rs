//! Structured explicit geometry meaning and the shared resolution policy.

use std::collections::BTreeSet;
use std::fmt::Write;
use std::sync::OnceLock;

use sha2::{Digest, Sha256};

use crate::{
    ClauseAtom, ClauseSegment, ExactDecimal, NormalizedDdlDocument, SourceOccurrence, SourceSpan,
};

pub const GEOMETRY_RESOLUTION_POLICY_ID: &str = "inku.geometry-resolution-policy.v1";

const GEOMETRY_RESOLUTION_POLICY_PREFIX: &str = concat!(
    "{\"anchor\":{\"arc_legacy\":\"circle_center\",\"arc_typed\":\"chord_midpoint\",",
    "\"closed_primitive\":\"center\",\"line\":\"endpoint_midpoint\",\"point\":\"center\",",
    "\"square_score\":\"top_left_from_center\"},"
);
const GEOMETRY_RESOLUTION_POLICY_MIDDLE: &str = concat!(
    "\"author_resolved_omission\":{\"color\":{\"choice\":\"max_oklch_lightness_distance\",",
    "\"tie\":\"black\"},\"continuity\":\"solid\",\"count\":1,",
    "\"surface\":{\"closed_and_point\":\"filled\",\"line_and_arc\":\"unfilled\"},",
    "\"touch\":\"pen\"},",
    "\"bounds\":{\"named\":{\"anchor\":\"performance_seed_in_range_shrunk_two_thirds_about_center\",",
    "\"extent\":\"not_must_fit\",\"region\":\"unclipped\"},",
    "\"numeric\":{\"anchor\":\"declared_unit_interval\",\"extent\":\"must_fit\"},",
    "\"numeric_range\":{\"anchor\":\"same_as_named_range\",\"extent\":\"not_must_fit\",",
    "\"fill_target\":\"unsupported\",\"region\":\"unclipped\",",
    "\"values\":\"exact_decimal_or_fraction_unit_interval_nonzero_width\",\"words\":\"kept_unread\"}},",
    "\"capability\":[\"circle_radius_or_diameter\",\"ellipse_width_height\",",
    "\"cloudform_width_height\",\"square_side\",\"square_rotated_declared_rectangle\",",
    "\"line_length\",\"arc_chord_sagitta\",\"point_radius_or_diameter\",",
    "\"endpoint_rotated_finite_extent\",\"axis_position\",\"triangle_width_height\",\"regular_triangle_exact_side\",\"square_width_height\",\"polygon_circumradius_sides\"],",
    "\"decimal\":{\"canonical\":\"signed_base10_coefficient_scale\",",
    "\"score_conversion\":\"single_final_f64_boundary\"},"
);
const GEOMETRY_RESOLUTION_POLICY_SUFFIX: &str = concat!(
    "\"normal_geometry\":{\"aspect\":{\"cloudform\":\"5:3\",\"ellipse\":\"5:3\"},",
    "\"basis\":\"canvas_short_edge\",\"count_dependency\":\"none\",",
    "\"endpoint_family\":{\"arc\":{\"chord\":\"6/25\",\"sagitta\":\"3/50\"},",
    "\"line\":{\"length\":\"6/25\"},\"point\":{\"diameter\":\"3/250\"}},",
    "\"width_or_diameter\":\"6/25\"},",
    "\"numeric_basis\":{\"position\":\"canvas_axes\",\"size\":\"canvas_short_edge\"},",
    "\"policy\":\"inku.geometry-resolution-policy.v1\",",
    "\"shape_constraints\":{\"aspect\":{\"long_to_short\":\"2:1\",\"explicit_dimensions\":\"retain_and_check_order\"},\"regular_triangle\":\"height=side*sqrt(3)/2_at_final_f64_boundary\",\"polygon\":{\"default_sides\":5,\"sides\":[5,6,7,8],\"radius\":\"circumradius\"},\"triangle_anchor\":\"bbox_center\"},",
    "\"relative_scale\":{\"extra_large\":\"2/1\",\"huge\":\"8/3\",\"large\":\"3/2\",\"normal\":\"1/1\",",
    "\"slightly_large\":\"5/4\",\"slightly_small\":\"3/4\",\"small\":\"1/2\",",
    "\"very_large\":\"7/4\",\"very_small\":\"3/8\"},\"unimplemented\":[]}"
);

// Each canvas axis is divided into three equal bands (0..1/3, 1/3..2/3,
// 2/3..1), and a position word names a range made of them: `top` and `bottom`
// are the upper and lower thirds across the width, and `center` (中心) is the
// middle cell on both axes. The edges (a tenth) and the
// corners (a fifth) keep their own narrower ranges.
const CENTER_RANGE: [(u8, u8); 4] = [(1, 3), (1, 3), (2, 3), (2, 3)];
// An omitted position lets a line-up, scatter, or tile use the whole canvas.
const CANVAS_RANGE: [(u8, u8); 4] = [(0, 1), (0, 1), (1, 1), (1, 1)];

/// Exact range bounds in region order, widened so an author's numeric range
/// and its two-thirds shrink stay exact.
pub(crate) type RationalRange = [(u64, u64); 4];

const fn widen(range: [(u8, u8); 4]) -> RationalRange {
    [
        (range[0].0 as u64, range[0].1 as u64),
        (range[1].0 as u64, range[1].1 as u64),
        (range[2].0 as u64, range[2].1 as u64),
        (range[3].0 as u64, range[3].1 as u64),
    ]
}

/// Where a position range comes from: a position word, a range written in
/// numbers, or nothing at all.
#[derive(Clone, Copy, Debug)]
pub(crate) enum RangeSource<'a> {
    Named(&'a str),
    Numeric(&'a SemanticNumericRange),
    Omitted,
}

impl<'a> RangeSource<'a> {
    pub(crate) fn from_named(named_position: Option<&'a str>) -> Self {
        named_position.map_or(Self::Omitted, Self::Named)
    }
}

/// How a placement uses the range of its position.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub(crate) enum RangeUse {
    /// One mark, or several gathered at one spot. The anchor is chosen inside
    /// the range shrunk to two thirds about its center.
    Place,
    /// A line-up, scatter, or tile over the whole range. A scatter or tile
    /// stays inside it; a line-up runs through its center.
    Distribute,
}

/// The anchor region of a mark placed with its position omitted: the middle
/// cell shrunk to two thirds, 7/18..11/18 on both axes.
pub(crate) fn omitted_position_bounds() -> [f64; 4] {
    rational_bounds_as_f64(place_anchor_bounds(widen(CENTER_RANGE)))
}

pub(crate) const NORMAL_SHORT_EDGE_RATIO: (i128, i128) = (6, 25);
pub(crate) const NORMAL_ELLIPTICAL_ASPECT_RATIO: (i128, i128) = (3, 5);

// One exact rational table feeds both policy bytes and the final Score boundary.
const NAMED_REGIONS: [(&str, [(u8, u8); 4]); 7] = [
    ("center", CENTER_RANGE),
    ("top", [(0, 1), (0, 1), (1, 1), (1, 3)]),
    ("bottom", [(0, 1), (2, 3), (1, 1), (1, 1)]),
    ("left_edge", [(0, 1), (0, 1), (1, 10), (1, 1)]),
    ("right_edge", [(9, 10), (0, 1), (1, 1), (1, 1)]),
    ("top_edge", [(0, 1), (0, 1), (1, 1), (1, 10)]),
    ("bottom_edge", [(0, 1), (9, 10), (1, 1), (1, 1)]),
];
const CORNER_REGIONS: [[(u8, u8); 4]; 4] = [
    [(0, 1), (0, 1), (1, 5), (1, 5)],
    [(4, 5), (0, 1), (1, 1), (1, 5)],
    [(0, 1), (4, 5), (1, 5), (1, 1)],
    [(4, 5), (4, 5), (1, 1), (1, 1)],
];
const PLACE_SELECTION_SCHEME: &str = "inku.score-place-selection.v1";

pub(crate) fn supports_named_position(id: &str) -> bool {
    id == "corner" || NAMED_REGIONS.iter().any(|(name, _)| *name == id)
}

pub(crate) fn named_region_bounds(
    id: &str,
    context: crate::score_angle::ScoreAngleContext<'_>,
) -> Option<[f64; 4]> {
    named_region_rational_bounds(id, context)
        .map(widen)
        .map(rational_bounds_as_f64)
}

pub(crate) fn named_region_rational_bounds(
    id: &str,
    context: crate::score_angle::ScoreAngleContext<'_>,
) -> Option<[(u8, u8); 4]> {
    let bounds = if id == "corner" {
        CORNER_REGIONS[corner_index(context)]
    } else {
        NAMED_REGIONS.iter().find(|(name, _)| *name == id)?.1
    };
    Some(bounds)
}

/// The range a source position denotes: a position word's range, a range
/// written in numbers, or the adopted range when the position is omitted (the
/// middle cell for a placed mark and the whole canvas for a line-up, scatter,
/// or tile). The caller retains source authority; this helper only supplies
/// the exact range used by every consumer, so a word and the same numbers draw
/// alike.
pub(crate) fn position_range(
    source: RangeSource<'_>,
    range_use: RangeUse,
    context: crate::score_angle::ScoreAngleContext<'_>,
) -> Option<RationalRange> {
    match source {
        RangeSource::Named(id) => named_region_rational_bounds(id, context).map(widen),
        RangeSource::Numeric(range) => Some(range.rational_bounds()),
        RangeSource::Omitted => Some(widen(match range_use {
            RangeUse::Place => CENTER_RANGE,
            RangeUse::Distribute => CANVAS_RANGE,
        })),
    }
}

/// The region a placement anchors in: the shrunk range for a placed mark, and
/// the whole range for a line-up, scatter, or tile.
pub(crate) fn anchor_rational_bounds(
    source: RangeSource<'_>,
    range_use: RangeUse,
    context: crate::score_angle::ScoreAngleContext<'_>,
) -> Option<RationalRange> {
    position_range(source, range_use, context).map(|range| match range_use {
        RangeUse::Place => place_anchor_bounds(range),
        RangeUse::Distribute => range,
    })
}

pub(crate) fn anchor_bounds(
    source: RangeSource<'_>,
    range_use: RangeUse,
    context: crate::score_angle::ScoreAngleContext<'_>,
) -> Option<[f64; 4]> {
    anchor_rational_bounds(source, range_use, context).map(rational_bounds_as_f64)
}

/// Shrink a range to two thirds about its center on both axes, exactly. A mark
/// anchored in a corner cell then stays mostly on the canvas, and the middle
/// cell gives 7/18..11/18, close to the earlier center region 0.39..0.61.
pub(crate) fn place_anchor_bounds(range: RationalRange) -> RationalRange {
    let (x0, x1) = shrink_two_thirds(range[0], range[2]);
    let (y0, y1) = shrink_two_thirds(range[1], range[3]);
    [x0, y0, x1, y1]
}

// start + (end - start) / 6 and end - (end - start) / 6, reduced. A range
// written in numbers has denominators of at most one million, so the shrunk
// denominator stays below 6e12 and fits u64 exactly.
fn shrink_two_thirds(start: (u64, u64), end: (u64, u64)) -> ((u64, u64), (u64, u64)) {
    let (a, b) = (i128::from(start.0), i128::from(start.1));
    let (c, d) = (i128::from(end.0), i128::from(end.1));
    let denominator = 6 * b * d;
    let width = c * b - a * d;
    (
        reduced(6 * a * d + width, denominator),
        reduced(6 * c * b - width, denominator),
    )
}

fn reduced(numerator: i128, denominator: i128) -> (u64, u64) {
    fn gcd(a: i128, b: i128) -> i128 {
        if b == 0 { a.abs() } else { gcd(b, a % b) }
    }
    let divisor = gcd(numerator, denominator).max(1);
    (
        u64::try_from(numerator / divisor).expect("a shrunk range is non-negative and fits u64"),
        u64::try_from(denominator / divisor).expect("a shrunk range denominator fits u64"),
    )
}

fn rational_bounds_as_f64(bounds: RationalRange) -> [f64; 4] {
    bounds.map(|(n, d)| n as f64 / d as f64)
}

// Reuses the already-attested occurrence value, never the angle resolver or its bytes.
fn place_hash_input(context: crate::score_angle::ScoreAngleContext<'_>) -> Vec<u8> {
    use crate::score_angle::ScoreAngleOccurrence;
    fn frame(output: &mut Vec<u8>, label: &[u8], value: &[u8]) {
        output.extend_from_slice(&(label.len() as u64).to_be_bytes());
        output.extend_from_slice(label);
        output.extend_from_slice(&(value.len() as u64).to_be_bytes());
        output.extend_from_slice(value);
    }
    let mut input = Vec::new();
    frame(&mut input, b"scheme", PLACE_SELECTION_SCHEME.as_bytes());
    frame(
        &mut input,
        b"original_pre_expansion_digest",
        context.original_pre_expansion_digest.as_bytes(),
    );
    frame(
        &mut input,
        b"original_expanded_meaning_digest",
        context.original_expanded_meaning_digest.as_bytes(),
    );
    let mut seed = vec![u8::from(context.composition_seed.is_some())];
    if let Some(value) = context.composition_seed {
        seed.extend_from_slice(&value.to_be_bytes());
    }
    frame(&mut input, b"composition_seed", &seed);
    match context.occurrence {
        ScoreAngleOccurrence::Direct { logical_ordinal } => {
            frame(&mut input, b"occurrence_kind", b"direct");
            frame(
                &mut input,
                b"logical_ordinal",
                &logical_ordinal.to_be_bytes(),
            );
        }
        ScoreAngleOccurrence::MacroEmit {
            macro_semantic_ordinal,
            expansion_path,
            generated_ordinal,
        } => {
            frame(&mut input, b"occurrence_kind", b"macro_emit");
            frame(
                &mut input,
                b"macro_semantic_ordinal",
                &macro_semantic_ordinal.to_be_bytes(),
            );
            frame(
                &mut input,
                b"expansion_path",
                &crate::typed_expansion_path_bytes(expansion_path),
            );
            frame(
                &mut input,
                b"generated_ordinal",
                &generated_ordinal.to_be_bytes(),
            );
        }
    }
    frame(&mut input, b"place_id", b"corner");
    input
}

fn corner_index(context: crate::score_angle::ScoreAngleContext<'_>) -> usize {
    // Four divides 256 exactly: the first digest byte gives an unbiased finite choice.
    usize::from(Sha256::digest(place_hash_input(context))[0] % 4)
}

fn write_place_policy(output: &mut String) {
    fn bounds(output: &mut String, values: [(u8, u8); 4]) {
        output.push('[');
        for (index, (n, d)) in values.into_iter().enumerate() {
            if index > 0 {
                output.push(',');
            }
            write!(output, "\"{n}/{d}\"").expect("policy String");
        }
        output.push(']');
    }
    output.push_str("\"named_regions\":{");
    for (id, values) in NAMED_REGIONS {
        write!(output, "\"{id}\":").expect("policy String");
        bounds(output, values);
        output.push(',');
    }
    output.push_str("\"corner\":[");
    for (index, values) in CORNER_REGIONS.into_iter().enumerate() {
        if index > 0 {
            output.push(',');
        }
        bounds(output, values);
    }
    write!(output, "],\"selection\":{{\"scheme\":\"{PLACE_SELECTION_SCHEME}\",\"draw\":\"sha256_first_byte_modulo_four\",\"order\":[\"upper_left\",\"upper_right\",\"lower_left\",\"lower_right\"],\"fields\":[\"original_pre_expansion_digest\",\"original_expanded_meaning_digest\",\"tagged_composition_seed\",\"logical_occurrence\",\"place_id\"]}}}},").expect("policy String");
}

pub(crate) const fn relative_scale_factor(value: crate::CoreModifierValue) -> Option<(i128, i128)> {
    match value {
        crate::CoreModifierValue::SlightlySmall => Some((3, 4)),
        crate::CoreModifierValue::Small => Some((1, 2)),
        crate::CoreModifierValue::VerySmall => Some((3, 8)),
        crate::CoreModifierValue::Normal => Some((1, 1)),
        crate::CoreModifierValue::SlightlyLarge => Some((5, 4)),
        crate::CoreModifierValue::Large => Some((3, 2)),
        crate::CoreModifierValue::VeryLarge => Some((7, 4)),
        // The two steps above mirror the two lowest ones (3/8 and 1/2) about normal.
        crate::CoreModifierValue::ExtraLarge => Some((2, 1)),
        crate::CoreModifierValue::Huge => Some((8, 3)),
        crate::CoreModifierValue::Fine
        | crate::CoreModifierValue::ExtraFine
        | crate::CoreModifierValue::Thick
        | crate::CoreModifierValue::ExtraThick
        | crate::CoreModifierValue::Regular
        | crate::CoreModifierValue::Sides(_) => None,
    }
}

pub fn geometry_resolution_policy_canonical_bytes() -> &'static [u8] {
    static CANONICAL_JSON: OnceLock<String> = OnceLock::new();
    CANONICAL_JSON
        .get_or_init(|| {
            let mut canonical = String::from(GEOMETRY_RESOLUTION_POLICY_PREFIX);
            crate::score_angle::write_angle_policy_json(&mut canonical);
            write_place_policy(&mut canonical);
            canonical.push_str(GEOMETRY_RESOLUTION_POLICY_MIDDLE);
            canonical.push_str(GEOMETRY_RESOLUTION_POLICY_SUFFIX);
            // Preserve the existing policy byte layout outside the added member.
            canonical = canonical.replacen(
                "\"author_resolved_omission\":{",
                &format!(
                    "\"author_resolved_omission\":{{\"position\":{{\"place_region\":{},\"distribute_range\":{},\"anchor\":\"performance_seed_in_region\",\"source_position\":\"absent\"}},\"fluctuation\":{},",
                    serde_json::to_string(&omitted_position_bounds()).expect("finite default bounds"),
                    serde_json::to_string(&rational_bounds_as_f64(widen(CANVAS_RANGE))).expect("finite canvas range"),
                    crate::fluctuation::policy()
                ),
                1,
            );
            canonical = canonical.replacen(
                "\"numeric_basis\":",
                concat!(
                    "\"object_placement\":{\"repeated_default_count\":8,",
                    "\"coordinated_group\":{\"place_line_up_omitted_per_member\":1,",
                    "\"scatter_tile_omitted_fill_total\":8,\"omitted_member_minimum\":1,\"allocation\":\"balanced_source_order_remainder_first\",",
                    "\"explicit_counts\":\"preserved\",\"scatter_tile_mixed_counts\":\"explicit_preserved_omissions_fill_total\",",
                    "\"omitted_members_exceed_total\":\"each_one_higher_total\",",
                    "\"target\":\"resolve_once_first_original_member_occurrence\",\"pivot\":\"combined_geometry_bbox_center\",",
                    "\"repetition\":\"symbolic_plan_materialization_deferred\"},",
                    "\"placement_members\":{\"source_head\":\"atomic_logical_slot\",\"primitive\":{\"logical_count\":\"object_count\",\"body_repeat_count\":1,\"recipe\":\"local_place_only\"},\"macro\":{\"logical_count\":\"outer_count\",\"body_repeat_count\":\"outer_count\",\"internal\":\"emit_counts_positions_recipes_preserved\"},\"bbox\":\"drawables_else_anchor_points\",\"owned_internal_transforms\":\"before_member_placement\",\"unowned_outer_transforms\":\"after_placement_including_equal_range\",\"standalone_repeats\":\"body_scopes_preserved_no_group_layout_target\"},",
                    "\"size_basis\":\"canvas_short_edge_independent_of_count\",",
                    "\"supported_geometry\":[\"line\",\"circle\",\"ellipse\",\"square\",\"arc\",\"cloudform\",\"point\"],",
                    "\"geometry_gap\":[\"triangle\",\"polygon\"],",
                    "\"line_up\":\"horizontal_domain_width_equal_cell_centers\",",
                    "\"layout_direction\":{\"owner\":\"instruction_or_emit\",\"default\":\"named_range_long_side_in_canvas_fractions_else_horizontal\",",
                    "\"horizontal\":\"tW,0\",\"vertical\":\"0,tH\",\"rising\":\"ts,-ts\",\"falling\":\"ts,ts\",",
                    "\"t\":\"(i+1/2)/n-1/2\",\"s\":\"min(W,H)\",\"diagonal\":\"seeded_rising_or_falling\",",
                    "\"seed_role\":\"inku.layout-direction-selection.v1\",\"seed\":\"attested_optional_composition_seed_original_meaning_logical_occurrence\",",
                    "\"shape_angle\":\"independent_unchanged\",\"supported_action\":\"line_up\"},",
                    "\"tile\":\"long_axis_min_n_ceil_sqrt_n_aspect_short_axis_ceil_n_long_axis_row_major\",",
                    "\"tile_numeric_anchor\":\"translate_exact_filled_prefix_centroid\",",
                    "\"tile_named_anchor\":\"stay_in_named_domain_no_centroid_translation\",",
                    "\"scatter\":\"uniform_xy_then_translate_sample_centroid_at_materialization\",",
                    "\"scatter_seed\":\"existing_performance_seed_owner_instance_ordinal\",",
                    "\"fill\":{\"omitted_target\":\"canvas\",\"target\":\"area_not_anchor\",\"distribution\":\"independent_uniform_in_target\",\"boundary\":\"clip_to_same_target_contour\",\"target_transform\":\"with_contents\",\"centroid_translation\":false,\"omitted_count\":\"max_1_ceil_reference_area_over_reference_extent_squared\",\"explicit_count_size\":\"preserved\",\"count_appearance_dependency\":false,\"cloudform_count_area\":\"declared_envelope\",\"crescent_count_area\":\"shared_cubic_analytic_integral\",\"numeric_motif_position\":\"invalid_not_area\",\"all_counts\":\"same_region_clip\",\"mixed_omission\":\"max_k_ceil_k_times_nonnegative_remaining_area_over_sum_omitted_extent_squared\",\"mixed_explicit_area\":\"sum_count_times_extent_squared\",\"mixed_allocation\":\"equal_omitted_counts_source_order_remainder_minimum_one\",\"macro_reference_extent\":\"max_declared_center_envelope_axis_span_plus_twice_max_primitive_reference_radius\",\"macro_reference_transform\":\"rotate_centers_scale_radius_by_max_absolute_axis\",\"macro_reference_positions\":\"declared_numeric_or_named_center_and_internal_recipe_envelope\",\"macro_reference_exclusions\":[\"outer_count\",\"ink_bounds\",\"instruction_angle\",\"performance_seed\",\"performed_relation_movement\"]},",
                    "\"non_grid_domain\":{\"named_scatter\":\"range_extent_group_centroid_at_range_center\",\"named_line_up\":\"canvas_axes_row_centroid_at_range_center\",\"numeric\":\"canvas_axes_group_centroid_at_numeric_anchor\"},",
                    "\"overlap\":\"allowed_no_resize_no_fit_no_count_change\",",
                    "\"materialization\":\"deferred\",\"score_success\":false},",
                    "\"numeric_basis\":"
                ),
                1,
            );
            canonical = canonical.replacen(
                "\"unimplemented\":[]",
                concat!(
                    "\"width_extent\":{\"basis\":\"canvas_width_before_rotation\",\"full_width\":\"1\",\"half_width\":\"1/2\",",
                    "\"closed\":\"reference_contour_width\",\"cloudform\":\"declared_width\",\"line\":\"length\",\"open_arc\":\"chord\",\"aspect\":\"preserved\"},",
                    "\"arc_form\":{\"semicircle\":\"upper_open_180\",\"waxing\":\"right_open_180\",\"waning\":\"left_open_180\",",
                    "\"crescent\":\"filled_saijiki_three_cubic_contour\",\"crescent_anchor\":\"reference_bbox_center\"},",
                    "\"size_conflict\":{\"diagnostic\":\"error\",\"recovery\":\"minimum_independent_reference_extent\",\"policies\":[\"stop\",\"continue\"],\"originals\":\"preserved\",\"scale_applications\":1},",
                    "\"unimplemented\":[]"
                ),
                1,
            );
            canonical
        })
        .as_bytes()
}

pub fn geometry_resolution_policy_digest() -> String {
    hex_lower(&Sha256::digest(geometry_resolution_policy_canonical_bytes()))
}

fn hex_lower(bytes: &[u8]) -> String {
    const HEX: &[u8; 16] = b"0123456789abcdef";
    let mut output = String::with_capacity(bytes.len() * 2);
    for byte in bytes {
        output.push(char::from(HEX[usize::from(byte >> 4)]));
        output.push(char::from(HEX[usize::from(byte & 0x0f)]));
    }
    output
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum GeometryKeyword {
    Radius,
    Diameter,
    Length,
    Chord,
    Sagitta,
    Width,
    Height,
    Side,
    Canvas,
    AxisX,
    AxisY,
    Position,
    /// A whole numeric range, read again from its source span.
    NumericRange,
}

impl GeometryKeyword {
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::Radius => "radius",
            Self::Diameter => "diameter",
            Self::Length => "length",
            Self::Chord => "chord",
            Self::Sagitta => "sagitta",
            Self::Width => "width",
            Self::Height => "height",
            Self::Side => "side",
            Self::Canvas => "canvas",
            Self::AxisX => "axis_x",
            Self::AxisY => "axis_y",
            Self::Position => "position",
            Self::NumericRange => "numeric_range",
        }
    }
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct SemanticExactDecimal {
    pub value: ExactDecimal,
    pub provenance: SourceOccurrence,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct SemanticGeometryValue {
    pub keyword: GeometryKeyword,
    pub keyword_provenance: SourceOccurrence,
    pub decimal: SemanticExactDecimal,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub enum SemanticExplicitGeometry {
    Radius(SemanticGeometryValue),
    Diameter(SemanticGeometryValue),
    Length(SemanticGeometryValue),
    ChordSagitta {
        chord: SemanticGeometryValue,
        sagitta: SemanticGeometryValue,
    },
    WidthHeight {
        width: SemanticGeometryValue,
        height: SemanticGeometryValue,
    },
    Side(SemanticGeometryValue),
}

impl SemanticExplicitGeometry {
    pub const fn source(&self) -> &SourceOccurrence {
        match self {
            Self::Radius(value)
            | Self::Diameter(value)
            | Self::Length(value)
            | Self::Side(value) => &value.keyword_provenance,
            Self::ChordSagitta { chord, .. } => &chord.keyword_provenance,
            Self::WidthHeight { width, .. } => &width.keyword_provenance,
        }
    }
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct SemanticNumericPosition {
    pub x: SemanticGeometryValue,
    pub y: SemanticGeometryValue,
}

/// Exact geometry meaning shared by source-owned and generated instructions.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum ExactGeometry {
    Radius(ExactDecimal),
    Diameter(ExactDecimal),
    Length(ExactDecimal),
    Side(ExactDecimal),
    WidthHeight {
        width: ExactDecimal,
        height: ExactDecimal,
    },
    ChordSagitta {
        chord: ExactDecimal,
        sagitta: ExactDecimal,
    },
}

impl From<&SemanticExplicitGeometry> for ExactGeometry {
    fn from(value: &SemanticExplicitGeometry) -> Self {
        match value {
            SemanticExplicitGeometry::Radius(value) => Self::Radius(value.decimal.value),
            SemanticExplicitGeometry::Diameter(value) => Self::Diameter(value.decimal.value),
            SemanticExplicitGeometry::Length(value) => Self::Length(value.decimal.value),
            SemanticExplicitGeometry::Side(value) => Self::Side(value.decimal.value),
            SemanticExplicitGeometry::WidthHeight { width, height } => Self::WidthHeight {
                width: width.decimal.value,
                height: height.decimal.value,
            },
            SemanticExplicitGeometry::ChordSagitta { chord, sagitta } => Self::ChordSagitta {
                chord: chord.decimal.value,
                sagitta: sagitta.decimal.value,
            },
        }
    }
}

/// Axis-normalized semantic anchor; provenance stays with the source or generated owner.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct ExactPosition {
    pub x: ExactDecimal,
    pub y: ExactDecimal,
}

impl From<&SemanticNumericPosition> for ExactPosition {
    fn from(value: &SemanticNumericPosition) -> Self {
        Self {
            x: value.x.decimal.value,
            y: value.y.decimal.value,
        }
    }
}

impl SemanticNumericPosition {
    pub const fn source(&self) -> &SourceOccurrence {
        &self.x.keyword_provenance
    }
}

/// A position range written in numbers: horizontal start, vertical start,
/// horizontal end, vertical end, as exact canvas fractions. The author's
/// original words before the parenthesis are kept as a span and never read.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct SemanticNumericRange {
    pub bounds: [crate::ExactFraction; 4],
    pub provenance: SourceOccurrence,
    pub bound_spans: [SourceSpan; 4],
    pub annotation: Option<SourceSpan>,
}

impl SemanticNumericRange {
    pub const fn source(&self) -> &SourceOccurrence {
        &self.provenance
    }

    /// The range as exact `(numerator, denominator)` pairs in region order.
    pub(crate) fn rational_bounds(&self) -> [(u64, u64); 4] {
        self.bounds
            .map(|bound| (bound.numerator(), bound.denominator()))
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub(crate) enum GeometrySyntaxIssueKind {
    IncompleteGeometry,
    IncompletePosition,
    UnownedDecimal,
    /// A numeric range off the canvas, without width, or beyond the value limits.
    InvalidRange,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub(crate) struct GeometrySyntaxIssue {
    pub kind: GeometrySyntaxIssueKind,
    pub span: SourceSpan,
}

#[derive(Clone, Debug, Default)]
pub(crate) struct ClauseGeometryAnalysis {
    pub geometries: Vec<SemanticExplicitGeometry>,
    pub positions: Vec<SemanticNumericPosition>,
    pub ranges: Vec<SemanticNumericRange>,
    pub consumed_numeric_spans: BTreeSet<(usize, usize)>,
    pub issues: Vec<GeometrySyntaxIssue>,
}

pub(crate) fn analyze_clause_geometry(
    document: &NormalizedDdlDocument,
    clause: &ClauseSegment,
    clause_index: usize,
    region_index: usize,
) -> ClauseGeometryAnalysis {
    let mut result = ClauseGeometryAnalysis::default();
    let mut consumed_keywords = BTreeSet::new();
    let atoms = &clause.atoms;
    for index in 0..atoms.len() {
        let Some(keyword) = keyword_atom(&atoms[index]) else {
            continue;
        };
        if consumed_keywords.contains(&index) {
            continue;
        }
        match keyword {
            GeometryKeyword::Radius
            | GeometryKeyword::Diameter
            | GeometryKeyword::Length
            | GeometryKeyword::Side => {
                if let Some(value) =
                    geometry_value(document, atoms, clause_index, region_index, index, keyword)
                {
                    result
                        .consumed_numeric_spans
                        .insert(span_key(value.decimal.provenance.span));
                    result.geometries.push(match keyword {
                        GeometryKeyword::Radius => SemanticExplicitGeometry::Radius(value),
                        GeometryKeyword::Diameter => SemanticExplicitGeometry::Diameter(value),
                        GeometryKeyword::Length => SemanticExplicitGeometry::Length(value),
                        GeometryKeyword::Side => SemanticExplicitGeometry::Side(value),
                        _ => unreachable!(),
                    });
                } else {
                    result.issues.push(issue(
                        GeometrySyntaxIssueKind::IncompleteGeometry,
                        atoms,
                        index,
                        index + 1,
                    ));
                }
            }
            GeometryKeyword::Width => {
                let pair =
                    geometry_value(document, atoms, clause_index, region_index, index, keyword)
                        .zip(
                            keyword_at(atoms, index + 2, GeometryKeyword::Height)
                                .then(|| index + 2),
                        )
                        .and_then(|(width, height_index)| {
                            geometry_value(
                                document,
                                atoms,
                                clause_index,
                                region_index,
                                height_index,
                                GeometryKeyword::Height,
                            )
                            .map(|height| (width, height_index, height))
                        });
                if let Some((width, height_index, height)) = pair {
                    consumed_keywords.insert(height_index);
                    result
                        .consumed_numeric_spans
                        .insert(span_key(width.decimal.provenance.span));
                    result
                        .consumed_numeric_spans
                        .insert(span_key(height.decimal.provenance.span));
                    result
                        .geometries
                        .push(SemanticExplicitGeometry::WidthHeight { width, height });
                } else {
                    result.issues.push(issue(
                        GeometrySyntaxIssueKind::IncompleteGeometry,
                        atoms,
                        index,
                        index + 3,
                    ));
                }
            }
            GeometryKeyword::Chord => {
                let pair =
                    geometry_value(document, atoms, clause_index, region_index, index, keyword)
                        .zip(
                            keyword_at(atoms, index + 2, GeometryKeyword::Sagitta)
                                .then(|| index + 2),
                        )
                        .and_then(|(chord, sagitta_index)| {
                            geometry_value(
                                document,
                                atoms,
                                clause_index,
                                region_index,
                                sagitta_index,
                                GeometryKeyword::Sagitta,
                            )
                            .map(|sagitta| (chord, sagitta_index, sagitta))
                        });
                if let Some((chord, sagitta_index, sagitta)) = pair {
                    consumed_keywords.insert(sagitta_index);
                    result
                        .consumed_numeric_spans
                        .insert(span_key(chord.decimal.provenance.span));
                    result
                        .consumed_numeric_spans
                        .insert(span_key(sagitta.decimal.provenance.span));
                    result
                        .geometries
                        .push(SemanticExplicitGeometry::ChordSagitta { chord, sagitta });
                } else {
                    result.issues.push(issue(
                        GeometrySyntaxIssueKind::IncompleteGeometry,
                        atoms,
                        index,
                        index + 3,
                    ));
                }
            }
            GeometryKeyword::Sagitta => result.issues.push(issue(
                GeometrySyntaxIssueKind::IncompleteGeometry,
                atoms,
                index,
                index + 1,
            )),
            GeometryKeyword::Height => result.issues.push(issue(
                GeometrySyntaxIssueKind::IncompleteGeometry,
                atoms,
                index,
                index + 1,
            )),
            GeometryKeyword::AxisX => {
                let pair =
                    geometry_value(document, atoms, clause_index, region_index, index, keyword)
                        .filter(|_| {
                            document.language() == crate::ResolvedInstructionLanguage::En
                                || (index > 0
                                    && keyword_at(atoms, index - 1, GeometryKeyword::Canvas)
                                    && japanese_position_context_closes(atoms, index))
                        })
                        .zip(
                            keyword_at(atoms, index + 2, GeometryKeyword::AxisY).then(|| index + 2),
                        )
                        .and_then(|(x, y_index)| {
                            geometry_value(
                                document,
                                atoms,
                                clause_index,
                                region_index,
                                y_index,
                                GeometryKeyword::AxisY,
                            )
                            .map(|y| (x, y_index, y))
                        });
                if let Some((x, y_index, y)) = pair {
                    consumed_keywords.insert(y_index);
                    result
                        .consumed_numeric_spans
                        .insert(span_key(x.decimal.provenance.span));
                    result
                        .consumed_numeric_spans
                        .insert(span_key(y.decimal.provenance.span));
                    result.positions.push(SemanticNumericPosition { x, y });
                } else {
                    result.issues.push(issue(
                        GeometrySyntaxIssueKind::IncompletePosition,
                        atoms,
                        index,
                        index + 3,
                    ));
                }
            }
            GeometryKeyword::AxisY => result.issues.push(issue(
                GeometrySyntaxIssueKind::IncompletePosition,
                atoms,
                index,
                index + 1,
            )),
            GeometryKeyword::NumericRange => {
                let span = atoms[index].span();
                let lexeme = crate::numeric_range::numeric_range_at(
                    document.source(),
                    span.start_byte,
                    document.language(),
                )
                .filter(|lexeme| lexeme.span == span);
                match lexeme
                    .and_then(|lexeme| valid_range_bounds(&lexeme).map(|bounds| (lexeme, bounds)))
                {
                    Some((lexeme, bounds)) => result.ranges.push(SemanticNumericRange {
                        bounds,
                        provenance: occurrence(document, span, region_index, clause_index, index),
                        bound_spans: lexeme.bound_spans,
                        annotation: lexeme.annotation,
                    }),
                    None => result.issues.push(issue(
                        GeometrySyntaxIssueKind::InvalidRange,
                        atoms,
                        index,
                        index + 1,
                    )),
                }
            }
            GeometryKeyword::Canvas | GeometryKeyword::Position => {}
        }
    }
    for atom in atoms {
        if matches!(
            atom,
            ClauseAtom::FunctionWord {
                exact_decimal: Some(_),
                ..
            }
        ) && !result
            .consumed_numeric_spans
            .contains(&span_key(atom.span()))
        {
            result.issues.push(GeometrySyntaxIssue {
                kind: GeometrySyntaxIssueKind::UnownedDecimal,
                span: atom.span(),
            });
        }
    }
    result
}

// Every bound is on the canvas and each axis has a width.
fn valid_range_bounds(lexeme: &crate::NumericRangeLexeme) -> Option<[crate::ExactFraction; 4]> {
    let [x0, y0, x1, y1] = lexeme.bounds;
    let bounds = [x0?, y0?, x1?, y1?];
    (bounds.iter().all(|bound| bound.is_at_most_one())
        && bounds[0].is_below(bounds[2])
        && bounds[1].is_below(bounds[3]))
    .then_some(bounds)
}

fn geometry_value(
    document: &NormalizedDdlDocument,
    atoms: &[ClauseAtom],
    clause_index: usize,
    region_index: usize,
    keyword_index: usize,
    keyword: GeometryKeyword,
) -> Option<SemanticGeometryValue> {
    let keyword_span = atoms.get(keyword_index)?.span();
    let (value, value_span) = decimal_atom(atoms.get(keyword_index + 1)?)?;
    Some(SemanticGeometryValue {
        keyword,
        keyword_provenance: occurrence(
            document,
            keyword_span,
            region_index,
            clause_index,
            keyword_index,
        ),
        decimal: SemanticExactDecimal {
            value,
            provenance: occurrence(
                document,
                value_span,
                region_index,
                clause_index,
                keyword_index + 1,
            ),
        },
    })
}

fn decimal_atom(atom: &ClauseAtom) -> Option<(ExactDecimal, SourceSpan)> {
    match atom {
        ClauseAtom::FunctionWord {
            exact_decimal: Some(value),
            span,
            ..
        } => Some((*value, *span)),
        ClauseAtom::UnattachedExactNumber(number) => {
            Some((ExactDecimal::from_u64(number.value), number.span))
        }
        _ => None,
    }
}

fn keyword_atom(atom: &ClauseAtom) -> Option<GeometryKeyword> {
    match atom {
        ClauseAtom::FunctionWord {
            geometry_keyword: Some(keyword),
            ..
        } => Some(*keyword),
        _ => None,
    }
}

fn keyword_at(atoms: &[ClauseAtom], index: usize, expected: GeometryKeyword) -> bool {
    atoms.get(index).and_then(keyword_atom) == Some(expected)
}

fn japanese_position_context_closes(atoms: &[ClauseAtom], axis_x_index: usize) -> bool {
    keyword_at(atoms, axis_x_index + 4, GeometryKeyword::Position)
        || (matches!(
            atoms.get(axis_x_index + 4),
            Some(ClauseAtom::GrammarMarker {
                marker_id: crate::MarkerId::JaNo,
                ..
            })
        ) && keyword_at(atoms, axis_x_index + 5, GeometryKeyword::Position))
}

fn issue(
    kind: GeometrySyntaxIssueKind,
    atoms: &[ClauseAtom],
    start: usize,
    desired_end: usize,
) -> GeometrySyntaxIssue {
    let first = atoms[start].span();
    let last = atoms[desired_end.min(atoms.len()).saturating_sub(1).max(start)].span();
    GeometrySyntaxIssue {
        kind,
        span: SourceSpan {
            start_byte: first.start_byte,
            end_byte: last.end_byte,
        },
    }
}

fn occurrence(
    document: &NormalizedDdlDocument,
    span: SourceSpan,
    region_index: usize,
    clause_index: usize,
    atom_index: usize,
) -> SourceOccurrence {
    SourceOccurrence {
        span,
        surface: document.source()[span.start_byte..span.end_byte].to_owned(),
        language: document.language(),
        region_index,
        clause_index,
        atom_index,
    }
}

const fn span_key(span: SourceSpan) -> (usize, usize) {
    (span.start_byte, span.end_byte)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn policy_payload_and_digest_are_closed_known_answers() {
        let payload: serde_json::Value =
            serde_json::from_slice(geometry_resolution_policy_canonical_bytes()).unwrap();
        assert_eq!(payload["policy"], GEOMETRY_RESOLUTION_POLICY_ID);
        let fluctuation = &payload["author_resolved_omission"]["fluctuation"];
        assert_eq!(fluctuation["words"].as_object().unwrap().len(), 7);
        assert_eq!(fluctuation["words"]["broadly"]["value"], "broad");
        assert_eq!(fluctuation["words"]["bleeding"]["dimension"], "spread");
        assert_eq!(fluctuation["words"]["swaying"]["dimension"], "quality");
        assert_eq!(fluctuation["absent"], "none");
        assert_eq!(
            fluctuation["partial"],
            serde_json::json!({"amplitude":"medium","frequency":"medium","quality":"perlin","dimensions":["position_x","position_y"]})
        );
        assert_eq!(payload["numeric_basis"]["size"], "canvas_short_edge");
        assert_eq!(payload["numeric_basis"]["position"], "canvas_axes");
        assert_eq!(payload["anchor"]["square_score"], "top_left_from_center");
        assert_eq!(payload["bounds"]["numeric"]["extent"], "must_fit");
        assert_eq!(payload["bounds"]["named"]["extent"], "not_must_fit");
        assert_eq!(payload["angle"]["choices"]["horizontal"], 0);
        assert_eq!(payload["angle"]["choices"]["vertical"], 90);
        assert_eq!(
            payload["angle"]["choices"]["diagonal"],
            serde_json::json!([45, 135, 225, 315])
        );
        assert_eq!(
            payload["angle"]["seed"]["scheme"],
            crate::score_angle::SCORE_ANGLE_SELECTION_SCHEME_ID
        );
        assert_eq!(
            payload["angle"]["bounds"]["square"],
            "rotated_declared_rectangle"
        );
        assert_eq!(payload["angle"]["bounds"]["circle"], "radius");
        assert_eq!(
            payload["angle"]["bounds"]["ellipse"],
            "rotated_ideal_ellipse"
        );
        assert_eq!(
            payload["angle"]["bounds"]["cloudform"],
            "rotated_declared_rectangle"
        );
        assert_eq!(payload["unimplemented"], serde_json::json!([]));
        assert_eq!(
            payload["width_extent"]["basis"],
            "canvas_width_before_rotation"
        );
        assert_eq!(payload["width_extent"]["open_arc"], "chord");
        assert_eq!(
            payload["arc_form"]["crescent"],
            "filled_saijiki_three_cubic_contour"
        );
        assert_eq!(payload["size_conflict"]["diagnostic"], "error");
        assert_eq!(
            payload["size_conflict"]["policies"],
            serde_json::json!(["stop", "continue"])
        );
        assert_eq!(
            payload["named_regions"]["top"],
            serde_json::json!(["0/1", "0/1", "1/1", "1/3"])
        );
        assert_eq!(
            payload["named_regions"]["selection"]["scheme"],
            PLACE_SELECTION_SCHEME
        );
        let context = crate::score_angle::ScoreAngleContext {
            composition_seed: None,
            original_pre_expansion_digest: "pre",
            original_expanded_meaning_digest: "expanded",
            occurrence: crate::score_angle::ScoreAngleOccurrence::Direct { logical_ordinal: 7 },
        };
        assert_ne!(
            place_hash_input(context),
            place_hash_input(crate::score_angle::ScoreAngleContext {
                composition_seed: Some(0),
                ..context
            })
        );
        assert_ne!(
            place_hash_input(context),
            place_hash_input(crate::score_angle::ScoreAngleContext {
                occurrence: crate::score_angle::ScoreAngleOccurrence::Direct { logical_ordinal: 0 },
                ..context
            })
        );
        assert_ne!(
            place_hash_input(context),
            place_hash_input(crate::score_angle::ScoreAngleContext {
                occurrence: crate::score_angle::ScoreAngleOccurrence::MacroEmit {
                    macro_semantic_ordinal: 7,
                    expansion_path: &[],
                    generated_ordinal: 0
                },
                ..context
            })
        );
        let mut selected = BTreeSet::new();
        for seed in 0..64 {
            let context = crate::score_angle::ScoreAngleContext {
                composition_seed: Some(seed),
                ..context
            };
            let index = corner_index(context);
            selected.insert(index);
            assert_eq!(
                named_region_bounds("corner", context),
                Some(CORNER_REGIONS[index].map(|(n, d)| f64::from(n) / f64::from(d)))
            );
        }
        assert_eq!(selected, BTreeSet::from([0, 1, 2, 3]));
        for (id, bounds) in NAMED_REGIONS {
            assert_eq!(
                payload["named_regions"][id],
                serde_json::json!(bounds.map(|(n, d)| format!("{n}/{d}")))
            );
            assert_eq!(
                named_region_bounds(id, context),
                Some(bounds.map(|(n, d)| f64::from(n) / f64::from(d)))
            );
        }
        assert_eq!(named_region_bounds("unknown", context), None);
        // `center` is the middle cell of the thirds. A mark placed there, or
        // placed with its position omitted, anchors in the cell shrunk to two
        // thirds; a distribution with its position omitted uses the canvas.
        assert_eq!(
            named_region_bounds("center", context),
            Some([1.0 / 3.0, 1.0 / 3.0, 2.0 / 3.0, 2.0 / 3.0])
        );
        assert_eq!(
            place_anchor_bounds(widen(CENTER_RANGE)),
            [(7, 18), (7, 18), (11, 18), (11, 18)]
        );
        assert_eq!(
            anchor_rational_bounds(RangeSource::Omitted, RangeUse::Place, context),
            Some(place_anchor_bounds(widen(CENTER_RANGE)))
        );
        assert_eq!(
            anchor_rational_bounds(RangeSource::Omitted, RangeUse::Distribute, context),
            Some(widen(CANVAS_RANGE))
        );
        // The shrink is exact for every closed range, including the edges and
        // the corners, whose denominators are the largest.
        assert_eq!(
            place_anchor_bounds(widen([(9, 10), (0, 1), (1, 1), (1, 1)])),
            [(11, 12), (1, 6), (59, 60), (5, 6)]
        );
        // A range written in numbers shrinks the same way, beyond u8.
        assert_eq!(
            place_anchor_bounds([(67, 100), (67, 100), (1, 1), (1, 1)]),
            [(29, 40), (29, 40), (189, 200), (189, 200)]
        );
        assert_eq!(
            place_anchor_bounds(widen(CORNER_REGIONS[0])),
            [(1, 30), (1, 30), (1, 6), (1, 6)]
        );
        assert_eq!(
            payload["author_resolved_omission"]["position"]["place_region"],
            serde_json::json!(omitted_position_bounds())
        );
        assert_eq!(
            payload["object_placement"]["non_grid_domain"]["named_scatter"],
            "range_extent_group_centroid_at_range_center"
        );
        assert!(payload.get("focus_regions").is_none());
        assert_eq!(
            payload["object_placement"]["placement_members"]["source_head"],
            "atomic_logical_slot"
        );
        assert_eq!(
            payload["object_placement"]["placement_members"]["macro"]["body_repeat_count"],
            "outer_count"
        );
        assert_eq!(
            payload["bounds"]["numeric_range"]["anchor"],
            "same_as_named_range"
        );
        assert_eq!(
            geometry_resolution_policy_digest(),
            "0567c999cfa0c5d25e8bfe65a3bd50808c7cad550273a9bb2461c0e74380d4da"
        );
        assert_eq!(
            payload["object_placement"]["layout_direction"]["vertical"],
            "0,tH"
        );
        assert_eq!(
            payload["object_placement"]["layout_direction"]["rising"],
            "ts,-ts"
        );
    }
}
