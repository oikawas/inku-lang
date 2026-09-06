//! Structured explicit geometry meaning and the shared resolution policy.

use std::collections::BTreeSet;

use sha2::{Digest, Sha256};

use crate::{
    ClauseAtom, ClauseSegment, ExactDecimal, NormalizedDdlDocument, SourceOccurrence, SourceSpan,
};

pub const GEOMETRY_RESOLUTION_POLICY_ID: &str = "inku.geometry-resolution-policy.v1";

const GEOMETRY_RESOLUTION_POLICY_CANONICAL_JSON: &str = concat!(
    "{\"anchor\":{\"closed_primitive\":\"center\",\"square_score\":\"top_left_from_center\"},",
    "\"author_resolved_omission\":{\"color\":{\"choice\":\"max_oklch_lightness_distance\",",
    "\"tie\":\"black\"},\"continuity\":\"solid\",\"count\":1,",
    "\"surface\":\"filled\",\"touch\":\"pen\"},",
    "\"bounds\":{\"anchor\":\"closed_unit_interval\",\"extent\":\"must_fit\"},",
    "\"capability\":[\"circle_radius_or_diameter\",\"ellipse_width_height\",",
    "\"cloudform_width_height\",\"square_side\",\"axis_position\"],",
    "\"decimal\":{\"canonical\":\"signed_base10_coefficient_scale\",",
    "\"score_conversion\":\"single_final_f64_boundary\"},",
    "\"normal_geometry\":{\"aspect\":{\"cloudform\":\"5:3\",\"ellipse\":\"5:3\"},",
    "\"basis\":\"canvas_short_edge\",\"count\":1,\"width_or_diameter\":\"6/25\"},",
    "\"numeric_basis\":{\"position\":\"canvas_axes\",\"size\":\"canvas_short_edge\"},",
    "\"policy\":\"inku.geometry-resolution-policy.v1\",",
    "\"relative_scale\":{\"large\":\"3/2\",\"normal\":\"1/1\",",
    "\"slightly_large\":\"5/4\",\"slightly_small\":\"3/4\",\"small\":\"1/2\",",
    "\"very_large\":\"7/4\",\"very_small\":\"3/8\"},\"unimplemented\":[]}"
);

pub(crate) const NORMAL_SHORT_EDGE_RATIO: (i128, i128) = (6, 25);
pub(crate) const NORMAL_ELLIPTICAL_ASPECT_RATIO: (i128, i128) = (3, 5);

pub(crate) const fn relative_scale_factor(value: crate::CoreModifierValue) -> Option<(i128, i128)> {
    match value {
        crate::CoreModifierValue::SlightlySmall => Some((3, 4)),
        crate::CoreModifierValue::Small => Some((1, 2)),
        crate::CoreModifierValue::VerySmall => Some((3, 8)),
        crate::CoreModifierValue::Normal => Some((1, 1)),
        crate::CoreModifierValue::SlightlyLarge => Some((5, 4)),
        crate::CoreModifierValue::Large => Some((3, 2)),
        crate::CoreModifierValue::VeryLarge => Some((7, 4)),
        crate::CoreModifierValue::Fine => None,
    }
}

pub fn geometry_resolution_policy_canonical_bytes() -> &'static [u8] {
    GEOMETRY_RESOLUTION_POLICY_CANONICAL_JSON.as_bytes()
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
    WidthHeight {
        width: SemanticGeometryValue,
        height: SemanticGeometryValue,
    },
    Side(SemanticGeometryValue),
}

impl SemanticExplicitGeometry {
    pub const fn source(&self) -> &SourceOccurrence {
        match self {
            Self::Radius(value) | Self::Diameter(value) | Self::Side(value) => {
                &value.keyword_provenance
            }
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
            GeometryKeyword::Radius | GeometryKeyword::Diameter | GeometryKeyword::Side => {
                if let Some(value) =
                    geometry_value(document, atoms, clause_index, region_index, index, keyword)
                {
                    result
                        .consumed_numeric_spans
                        .insert(span_key(value.decimal.provenance.span));
                    result.geometries.push(match keyword {
                        GeometryKeyword::Radius => SemanticExplicitGeometry::Radius(value),
                        GeometryKeyword::Diameter => SemanticExplicitGeometry::Diameter(value),
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
        assert_eq!(payload["numeric_basis"]["size"], "canvas_short_edge");
        assert_eq!(payload["numeric_basis"]["position"], "canvas_axes");
        assert_eq!(payload["anchor"]["square_score"], "top_left_from_center");
        assert_eq!(
            payload["unimplemented"],
            serde_json::json!(["normal_geometry", "qualitative_factors"])
        );
        assert_eq!(
            geometry_resolution_policy_digest(),
            "53f34ed5674f60f1d39c1e8cd31d32426be58c4b9c8e6eb06303b5b4b8612117"
        );
    }
}
