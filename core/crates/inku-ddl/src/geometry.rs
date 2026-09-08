//! Structured explicit geometry meaning and the shared resolution policy.

use std::collections::BTreeSet;
use std::fmt::Write;
use std::sync::OnceLock;

use sha2::{Digest, Sha256};

use crate::{
    ClauseAtom, ClauseSegment, ExactDecimal, NormalizedDdlDocument, SourceOccurrence, SourceSpan,
    stage15_transform::FocusRegion,
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
    "\"bounds\":{\"named\":{\"anchor\":\"performance_seed_in_region\",",
    "\"extent\":\"not_must_fit\",\"region\":\"unclipped\"},",
    "\"numeric\":{\"anchor\":\"declared_unit_interval\",\"extent\":\"must_fit\"}},",
    "\"capability\":[\"circle_radius_or_diameter\",\"ellipse_width_height\",",
    "\"cloudform_width_height\",\"square_side\",\"square_rotated_declared_rectangle\",",
    "\"line_length\",\"arc_chord_sagitta\",\"point_radius_or_diameter\",",
    "\"endpoint_rotated_finite_extent\",\"axis_position\",\"triangle_width_height\",\"regular_triangle_exact_side\",\"square_width_height\",\"polygon_circumradius_sides\"],",
    "\"decimal\":{\"canonical\":\"signed_base10_coefficient_scale\",",
    "\"score_conversion\":\"single_final_f64_boundary\"},\"focus_regions\":{"
);
const GEOMETRY_RESOLUTION_POLICY_SUFFIX: &str = concat!(
    "},",
    "\"normal_geometry\":{\"aspect\":{\"cloudform\":\"5:3\",\"ellipse\":\"5:3\"},",
    "\"basis\":\"canvas_short_edge\",\"count_dependency\":\"none\",",
    "\"endpoint_family\":{\"arc\":{\"chord\":\"6/25\",\"sagitta\":\"3/50\"},",
    "\"line\":{\"length\":\"6/25\"},\"point\":{\"diameter\":\"3/250\"}},",
    "\"width_or_diameter\":\"6/25\"},",
    "\"numeric_basis\":{\"position\":\"canvas_axes\",\"size\":\"canvas_short_edge\"},",
    "\"policy\":\"inku.geometry-resolution-policy.v1\",",
    "\"shape_constraints\":{\"aspect\":{\"long_to_short\":\"2:1\",\"explicit_dimensions\":\"retain_and_check_order\"},\"regular_triangle\":\"height=side*sqrt(3)/2_at_final_f64_boundary\",\"polygon\":{\"default_sides\":5,\"sides\":[5,6,7,8],\"radius\":\"circumradius\"},\"triangle_anchor\":\"bbox_center\"},",
    "\"relative_scale\":{\"large\":\"3/2\",\"normal\":\"1/1\",",
    "\"slightly_large\":\"5/4\",\"slightly_small\":\"3/4\",\"small\":\"1/2\",",
    "\"very_large\":\"7/4\",\"very_small\":\"3/8\"},\"unimplemented\":[]}"
);

const FOCUS_REGION_BOUNDS_HUNDREDTHS: [(FocusRegion, [u8; 4]); 6] = [
    (FocusRegion::UpperRight, [60, 18, 82, 40]),
    (FocusRegion::UpperLeft, [18, 18, 40, 40]),
    (FocusRegion::LowerRight, [60, 60, 82, 82]),
    (FocusRegion::LowerLeft, [18, 60, 40, 82]),
    (FocusRegion::UpperEdge, [39, 7, 61, 29]),
    (FocusRegion::RightHalf, [61, 39, 83, 61]),
];

pub(crate) const NORMAL_SHORT_EDGE_RATIO: (i128, i128) = (6, 25);
pub(crate) const NORMAL_ELLIPTICAL_ASPECT_RATIO: (i128, i128) = (3, 5);

// One exact rational table feeds both policy bytes and the final Score boundary.
const NAMED_REGIONS: [(&str, [(u8, u8); 4]); 6] = [
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
    matches!(id, "center" | "corner") || NAMED_REGIONS.iter().any(|(name, _)| *name == id)
}

pub(crate) fn named_region_bounds(
    id: &str,
    focus: Option<FocusRegion>,
    context: crate::score_angle::ScoreAngleContext<'_>,
) -> Option<[f64; 4]> {
    if id == "center" {
        return focus.map(focus_region_bounds);
    }
    named_region_rational_bounds(id, focus, context)
        .map(|bounds| bounds.map(|(n, d)| f64::from(n) / f64::from(d)))
}

pub(crate) fn named_region_rational_bounds(
    id: &str,
    focus: Option<FocusRegion>,
    context: crate::score_angle::ScoreAngleContext<'_>,
) -> Option<[(u8, u8); 4]> {
    if id == "center" {
        let focus = focus?;
        return FOCUS_REGION_BOUNDS_HUNDREDTHS
            .iter()
            .find(|(candidate, _)| *candidate == focus)
            .map(|(_, bounds)| bounds.map(|value| (value, 100)));
    }
    let bounds = if id == "corner" {
        CORNER_REGIONS[corner_index(context)]
    } else {
        NAMED_REGIONS.iter().find(|(name, _)| *name == id)?.1
    };
    Some(bounds)
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

pub(crate) fn focus_region_bounds(focus: FocusRegion) -> [f64; 4] {
    let bounds = FOCUS_REGION_BOUNDS_HUNDREDTHS
        .iter()
        .find_map(|(candidate, bounds)| (*candidate == focus).then_some(*bounds))
        .expect("the closed focus vocabulary has one geometry-policy region");
    bounds.map(|coordinate| f64::from(coordinate) / 100.0)
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
        crate::CoreModifierValue::Fine
        | crate::CoreModifierValue::ExtraFine
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
            for (index, (focus, bounds)) in FOCUS_REGION_BOUNDS_HUNDREDTHS.iter().enumerate() {
                if index > 0 {
                    canonical.push(',');
                }
                write!(
                    canonical,
                    "\"{}\":[{}.{:02},{}.{:02},{}.{:02},{}.{:02}]",
                    focus.as_str(),
                    bounds[0] / 100,
                    bounds[0] % 100,
                    bounds[1] / 100,
                    bounds[1] % 100,
                    bounds[2] / 100,
                    bounds[2] % 100,
                    bounds[3] / 100,
                    bounds[3] % 100,
                )
                .expect("writing canonical geometry policy to a String cannot fail");
            }
            canonical.push_str(GEOMETRY_RESOLUTION_POLICY_SUFFIX);
            // Preserve the existing policy byte layout outside the added member.
            canonical = canonical.replacen(
                "\"author_resolved_omission\":{",
                &format!(
                    "\"author_resolved_omission\":{{\"fluctuation\":{},",
                    crate::fluctuation::policy()
                ),
                1,
            );
            canonical = canonical.replacen(
                "\"numeric_basis\":",
                concat!(
                    "\"object_placement\":{\"repeated_default_count\":8,",
                    "\"size_basis\":\"canvas_short_edge_independent_of_count\",",
                    "\"supported_geometry\":[\"line\",\"circle\",\"ellipse\",\"square\",\"arc\",\"cloudform\",\"point\"],",
                    "\"geometry_gap\":[\"triangle\",\"polygon\"],",
                    "\"line_up\":\"horizontal_domain_width_equal_cell_centers\",",
                    "\"layout_direction\":{\"owner\":\"instruction_or_emit\",\"default\":\"horizontal\",",
                    "\"horizontal\":\"tW,0\",\"vertical\":\"0,tH\",\"rising\":\"ts,-ts\",\"falling\":\"ts,ts\",",
                    "\"t\":\"(i+1/2)/n-1/2\",\"s\":\"min(W,H)\",\"diagonal\":\"seeded_rising_or_falling\",",
                    "\"seed_role\":\"inku.layout-direction-selection.v1\",\"seed\":\"attested_optional_composition_seed_original_meaning_logical_occurrence\",",
                    "\"shape_angle\":\"independent_unchanged\",\"supported_action\":\"line_up\"},",
                    "\"tile\":\"long_axis_min_n_ceil_sqrt_n_aspect_short_axis_ceil_n_long_axis_row_major\",",
                    "\"tile_numeric_anchor\":\"translate_exact_filled_prefix_centroid\",",
                    "\"tile_named_anchor\":\"stay_in_named_domain_no_centroid_translation\",",
                    "\"scatter\":\"uniform_xy_then_translate_sample_centroid_at_materialization\",",
                    "\"scatter_seed\":\"existing_performance_seed_owner_instance_ordinal\",",
                    "\"non_grid_domain\":\"canvas_axes_group_centroid_at_semantic_anchor\",",
                    "\"overlap\":\"allowed_no_resize_no_fit_no_count_change\",",
                    "\"materialization\":\"deferred\",\"score_success\":false},",
                    "\"numeric_basis\":"
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

impl SemanticNumericPosition {
    pub const fn source(&self) -> &SourceOccurrence {
        &self.x.keyword_provenance
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub(crate) enum GeometrySyntaxIssueKind {
    IncompleteGeometry,
    IncompletePosition,
    UnownedDecimal,
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
            Some(ClauseAtom::FunctionWord {
                surface,
                geometry_keyword: None,
                exact_decimal: None,
                ..
            }) if surface == "の"
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
        assert_eq!(fluctuation["words"].as_object().unwrap().len(), 8);
        assert_eq!(fluctuation["words"]["large"]["value"], "broad");
        assert_eq!(fluctuation["words"]["trembling"]["dimension"], "quality");
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
                named_region_bounds("corner", None, context),
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
                named_region_bounds(id, None, context),
                Some(bounds.map(|(n, d)| f64::from(n) / f64::from(d)))
            );
        }
        assert_eq!(named_region_bounds("unknown", None, context), None);
        assert_eq!(named_region_bounds("center", None, context), None);
        for (focus, expected) in [
            (FocusRegion::UpperRight, [0.60, 0.18, 0.82, 0.40]),
            (FocusRegion::UpperLeft, [0.18, 0.18, 0.40, 0.40]),
            (FocusRegion::LowerRight, [0.60, 0.60, 0.82, 0.82]),
            (FocusRegion::LowerLeft, [0.18, 0.60, 0.40, 0.82]),
            (FocusRegion::UpperEdge, [0.39, 0.07, 0.61, 0.29]),
            (FocusRegion::RightHalf, [0.61, 0.39, 0.83, 0.61]),
        ] {
            let actual = focus_region_bounds(focus);
            assert_eq!(actual, expected);
            assert!(actual.into_iter().all(f64::is_finite));
            assert_eq!(
                payload["focus_regions"][focus.as_str()],
                serde_json::json!(expected)
            );
        }
        assert_eq!(
            geometry_resolution_policy_digest(),
            "0fde6e2082b9adcb17ca0ab5a36888cb884eb3e0225f5d35c7ccdc44bba736f0"
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
