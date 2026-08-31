//! Single-head semantic association over the accepted source-preserving clause stream.

use std::collections::BTreeMap;

use serde_json::{Number, Value};

use crate::{
    ClauseAtom, ClauseSeparatorKind, ClauseStream, ClauseStreamError, CoreRoleKind,
    NeutralDiagnostic, NeutralDiagnosticKind, NormalizedDdlDocument, RemainingRoleKind,
    ResolvedInstructionLanguage, SourceSpan, parse_clause_stream, project_macro_semantic_ref,
};

/// Stable identity for the runtime-disconnected single-head semantic AST.
pub const SEMANTIC_ENTITY_ASSOCIATION_SCHEMA_ID: &str = "inku.semantic-entity-association.v2";

/// Source-independent semantic identity projected from one accepted Saijiki row.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct SemanticIdentity {
    pub category: String,
    pub id: String,
}

/// Exact source location for one association-owned occurrence.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct SourceOccurrence {
    pub span: SourceSpan,
    pub surface: String,
    pub language: ResolvedInstructionLanguage,
    pub region_index: usize,
    pub clause_index: usize,
    pub atom_index: usize,
}

/// Saijiki identity and localized label retained only as source provenance.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct SemanticTermProvenance {
    pub source: SourceOccurrence,
    pub asset_id: String,
    pub category_key: String,
    pub canonical_surface_ja: String,
}

/// One source-independent Saijiki meaning with its separate source provenance.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct SemanticTerm {
    pub identity: SemanticIdentity,
    pub provenance: SemanticTermProvenance,
}

/// One checked, explicit, non-negative numeric quantity and its source provenance.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct SemanticQuantity {
    pub value: u64,
    pub provenance: SourceOccurrence,
}

/// One single-head entity. A field is absent only when it was not explicitly and uniquely stated.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct SemanticEntity {
    pub head: SemanticTerm,
    pub color: Option<SemanticTerm>,
    pub quantity: Option<SemanticQuantity>,
    pub touch: Option<SemanticTerm>,
    pub continuity: Option<SemanticTerm>,
    pub angle: Option<SemanticTerm>,
}

/// Partial or complete semantic entity sequence in sentence-region source order.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct SemanticEntityAssociationAst {
    pub entities: Vec<SemanticEntity>,
    pub complete: bool,
}

/// An association-owned occurrence delivered to a typed issue rather than an AST field.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum OwnedSemanticOccurrence {
    Head(SemanticTerm),
    Color(SemanticTerm),
    Quantity(SemanticQuantity),
    Touch(SemanticTerm),
    Continuity(SemanticTerm),
    Angle(SemanticTerm),
}

impl OwnedSemanticOccurrence {
    /// Return the byte-exact source occurrence delivered by this issue.
    pub const fn source(&self) -> &SourceOccurrence {
        match self {
            Self::Head(term)
            | Self::Color(term)
            | Self::Touch(term)
            | Self::Continuity(term)
            | Self::Angle(term) => &term.provenance.source,
            Self::Quantity(quantity) => &quantity.provenance,
        }
    }
}

/// Stable, expected association issue classes for this single-head slice.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum SemanticAssociationIssueKind {
    AmbiguousEntityOwnership,
    MissingEntityHead,
    ConflictingColors,
    ConflictingQuantities,
    ConflictingTouches,
    ConflictingContinuities,
    ConflictingAngles,
    UpstreamHole,
    UpstreamConflict,
    UpstreamUnknown,
}

impl SemanticAssociationIssueKind {
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::AmbiguousEntityOwnership => "ambiguous_entity_ownership",
            Self::MissingEntityHead => "missing_entity_head",
            Self::ConflictingColors => "conflicting_colors",
            Self::ConflictingQuantities => "conflicting_quantities",
            Self::ConflictingTouches => "conflicting_touches",
            Self::ConflictingContinuities => "conflicting_continuities",
            Self::ConflictingAngles => "conflicting_angles",
            Self::UpstreamHole => "upstream_hole",
            Self::UpstreamConflict => "upstream_conflict",
            Self::UpstreamUnknown => "upstream_unknown",
        }
    }
}

/// One typed issue with either its owned occurrences or its unchanged upstream diagnostic.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct SemanticAssociationIssue {
    pub kind: SemanticAssociationIssueKind,
    pub region_index: usize,
    pub occurrences: Vec<OwnedSemanticOccurrence>,
    pub upstream_diagnostic: Option<NeutralDiagnostic>,
}

/// Source-preserving association result. Counts refer only to the closed entity roles and exact
/// numbers owned by this slice, not the wider clause-stream delivery overlay.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct SemanticAssociationResult {
    pub schema_id: &'static str,
    pub clause_stream: ClauseStream,
    pub ast: SemanticEntityAssociationAst,
    pub issues: Vec<SemanticAssociationIssue>,
    pub canonical_bytes: Option<Vec<u8>>,
    pub owned_occurrence_count: usize,
    pub delivered_occurrence_count: usize,
}

#[derive(Default)]
struct AssociationRegion {
    heads: Vec<SemanticTerm>,
    colors: Vec<SemanticTerm>,
    quantities: Vec<SemanticQuantity>,
    touches: Vec<SemanticTerm>,
    continuities: Vec<SemanticTerm>,
    angles: Vec<SemanticTerm>,
    diagnostics: Vec<NeutralDiagnostic>,
}

/// Associate the closed single-entity roles and explicit numeric quantity within sentence regions.
///
/// The accepted clause parser is invoked exactly once. Sentence endings close a region, while line
/// breaks only create source-formatting clause boundaries inside the same region.
pub fn associate_semantic_entities(
    document: &NormalizedDdlDocument,
) -> Result<SemanticAssociationResult, ClauseStreamError> {
    let clause_stream = parse_clause_stream(document)?;
    let mut regions = BTreeMap::<usize, AssociationRegion>::new();
    let mut owned_occurrence_count = 0;

    for (clause_index, clause) in clause_stream.clauses.iter().enumerate() {
        for (atom_index, atom) in clause.atoms.iter().enumerate() {
            let region_index = sentence_region_index(&clause_stream, atom.span());
            let region = regions.entry(region_index).or_default();
            match atom {
                ClauseAtom::CoreRole(term) if term.role == CoreRoleKind::Primitive => {
                    region.heads.push(project_term(
                        document,
                        term,
                        region_index,
                        clause_index,
                        atom_index,
                    ));
                    owned_occurrence_count += 1;
                }
                ClauseAtom::CoreRole(term) if term.role == CoreRoleKind::Color => {
                    region.colors.push(project_term(
                        document,
                        term,
                        region_index,
                        clause_index,
                        atom_index,
                    ));
                    owned_occurrence_count += 1;
                }
                ClauseAtom::CoreRole(term) if term.role == CoreRoleKind::Touch => {
                    region.touches.push(project_term(
                        document,
                        term,
                        region_index,
                        clause_index,
                        atom_index,
                    ));
                    owned_occurrence_count += 1;
                }
                ClauseAtom::RemainingRole(term) if term.role == RemainingRoleKind::Continuity => {
                    region.continuities.push(project_remaining_term(
                        document,
                        term,
                        region_index,
                        clause_index,
                        atom_index,
                    ));
                    owned_occurrence_count += 1;
                }
                ClauseAtom::RemainingRole(term) if term.role == RemainingRoleKind::Angle => {
                    region.angles.push(project_remaining_term(
                        document,
                        term,
                        region_index,
                        clause_index,
                        atom_index,
                    ));
                    owned_occurrence_count += 1;
                }
                ClauseAtom::UnattachedExactNumber(quantity) => {
                    region.quantities.push(SemanticQuantity {
                        value: quantity.value,
                        provenance: source_occurrence(
                            document,
                            quantity.span,
                            region_index,
                            clause_index,
                            atom_index,
                        ),
                    });
                    owned_occurrence_count += 1;
                }
                ClauseAtom::UnresolvedDiagnostic(diagnostic) => {
                    region.diagnostics.push(diagnostic.clone());
                }
                ClauseAtom::CoreRole(_)
                | ClauseAtom::RemainingRole(_)
                | ClauseAtom::FunctionWord { .. }
                | ClauseAtom::SaijikiRelation { .. } => {}
            }
        }
    }

    let mut entities = Vec::new();
    let mut issues = Vec::new();
    for (region_index, region) in regions {
        associate_region(region_index, region, &mut entities, &mut issues);
    }

    let delivered_occurrence_count = entities.iter().map(entity_occurrence_count).sum::<usize>()
        + issues
            .iter()
            .map(|issue| issue.occurrences.len())
            .sum::<usize>();
    assert_eq!(
        delivered_occurrence_count, owned_occurrence_count,
        "semantic association must deliver every owned occurrence exactly once"
    );

    let ast = SemanticEntityAssociationAst {
        entities,
        complete: issues.is_empty(),
    };
    let canonical_bytes = ast.complete.then(|| canonical_ast_bytes(&ast));

    Ok(SemanticAssociationResult {
        schema_id: SEMANTIC_ENTITY_ASSOCIATION_SCHEMA_ID,
        clause_stream,
        ast,
        issues,
        canonical_bytes,
        owned_occurrence_count,
        delivered_occurrence_count,
    })
}

pub(crate) fn sentence_region_index(stream: &ClauseStream, span: SourceSpan) -> usize {
    stream
        .separators
        .iter()
        .filter(|separator| {
            separator.kind == ClauseSeparatorKind::SentenceEnd
                && separator.span.end_byte <= span.start_byte
        })
        .count()
}

fn project_term(
    document: &NormalizedDdlDocument,
    term: &crate::CoreRoleTerm,
    region_index: usize,
    clause_index: usize,
    atom_index: usize,
) -> SemanticTerm {
    let projected = project_macro_semantic_ref(&term.category_key, &term.canonical_surface_ja)
        .expect("accepted typed Saijiki term has a canonical semantic identity");
    SemanticTerm {
        identity: SemanticIdentity {
            category: projected.category,
            id: projected.canonical_id,
        },
        provenance: SemanticTermProvenance {
            source: source_occurrence(document, term.span, region_index, clause_index, atom_index),
            asset_id: term.asset_id.clone(),
            category_key: term.category_key.clone(),
            canonical_surface_ja: term.canonical_surface_ja.clone(),
        },
    }
}

fn project_remaining_term(
    document: &NormalizedDdlDocument,
    term: &crate::RemainingRoleTerm,
    region_index: usize,
    clause_index: usize,
    atom_index: usize,
) -> SemanticTerm {
    let projected = project_macro_semantic_ref(&term.category_key, &term.canonical_surface_ja)
        .expect("accepted typed Saijiki term has a canonical semantic identity");
    SemanticTerm {
        identity: SemanticIdentity {
            category: projected.category,
            id: projected.canonical_id,
        },
        provenance: SemanticTermProvenance {
            source: source_occurrence(document, term.span, region_index, clause_index, atom_index),
            asset_id: term.asset_id.clone(),
            category_key: term.category_key.clone(),
            canonical_surface_ja: term.canonical_surface_ja.clone(),
        },
    }
}

fn source_occurrence(
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

fn associate_region(
    region_index: usize,
    mut region: AssociationRegion,
    entities: &mut Vec<SemanticEntity>,
    issues: &mut Vec<SemanticAssociationIssue>,
) {
    if region.heads.len() > 1 {
        let mut occurrences = region
            .heads
            .drain(..)
            .map(OwnedSemanticOccurrence::Head)
            .chain(region.colors.drain(..).map(OwnedSemanticOccurrence::Color))
            .chain(
                region
                    .quantities
                    .drain(..)
                    .map(OwnedSemanticOccurrence::Quantity),
            )
            .chain(region.touches.drain(..).map(OwnedSemanticOccurrence::Touch))
            .chain(
                region
                    .continuities
                    .drain(..)
                    .map(OwnedSemanticOccurrence::Continuity),
            )
            .chain(region.angles.drain(..).map(OwnedSemanticOccurrence::Angle))
            .collect::<Vec<_>>();
        occurrences.sort_by_key(|occurrence| occurrence.source().span.start_byte);
        issues.push(SemanticAssociationIssue {
            kind: SemanticAssociationIssueKind::AmbiguousEntityOwnership,
            region_index,
            occurrences,
            upstream_diagnostic: None,
        });
        append_upstream_issues(region_index, region.diagnostics, issues);
        return;
    }

    if region.heads.is_empty() {
        let mut occurrences = region
            .colors
            .drain(..)
            .map(OwnedSemanticOccurrence::Color)
            .chain(
                region
                    .quantities
                    .drain(..)
                    .map(OwnedSemanticOccurrence::Quantity),
            )
            .chain(region.touches.drain(..).map(OwnedSemanticOccurrence::Touch))
            .chain(
                region
                    .continuities
                    .drain(..)
                    .map(OwnedSemanticOccurrence::Continuity),
            )
            .chain(region.angles.drain(..).map(OwnedSemanticOccurrence::Angle))
            .collect::<Vec<_>>();
        occurrences.sort_by_key(|occurrence| occurrence.source().span.start_byte);
        if !occurrences.is_empty() {
            issues.push(SemanticAssociationIssue {
                kind: SemanticAssociationIssueKind::MissingEntityHead,
                region_index,
                occurrences,
                upstream_diagnostic: None,
            });
        }
        append_upstream_issues(region_index, region.diagnostics, issues);
        return;
    }

    let head = region.heads.pop().expect("single head was checked");
    let color = select_term(
        region.colors,
        OwnedSemanticOccurrence::Color,
        SemanticAssociationIssueKind::ConflictingColors,
        region_index,
        issues,
    );
    let quantity = match region.quantities.len() {
        0 => None,
        1 => region.quantities.pop(),
        _ => {
            let occurrences = region
                .quantities
                .drain(..)
                .map(OwnedSemanticOccurrence::Quantity)
                .collect();
            issues.push(SemanticAssociationIssue {
                kind: SemanticAssociationIssueKind::ConflictingQuantities,
                region_index,
                occurrences,
                upstream_diagnostic: None,
            });
            None
        }
    };
    let touch = select_term(
        region.touches,
        OwnedSemanticOccurrence::Touch,
        SemanticAssociationIssueKind::ConflictingTouches,
        region_index,
        issues,
    );
    let continuity = select_term(
        region.continuities,
        OwnedSemanticOccurrence::Continuity,
        SemanticAssociationIssueKind::ConflictingContinuities,
        region_index,
        issues,
    );
    let angle = select_term(
        region.angles,
        OwnedSemanticOccurrence::Angle,
        SemanticAssociationIssueKind::ConflictingAngles,
        region_index,
        issues,
    );
    entities.push(SemanticEntity {
        head,
        color,
        quantity,
        touch,
        continuity,
        angle,
    });
    append_upstream_issues(region_index, region.diagnostics, issues);
}

fn select_term(
    mut terms: Vec<SemanticTerm>,
    into_occurrence: fn(SemanticTerm) -> OwnedSemanticOccurrence,
    conflict_kind: SemanticAssociationIssueKind,
    region_index: usize,
    issues: &mut Vec<SemanticAssociationIssue>,
) -> Option<SemanticTerm> {
    match terms.len() {
        0 => None,
        1 => terms.pop(),
        _ => {
            issues.push(SemanticAssociationIssue {
                kind: conflict_kind,
                region_index,
                occurrences: terms.into_iter().map(into_occurrence).collect(),
                upstream_diagnostic: None,
            });
            None
        }
    }
}

fn append_upstream_issues(
    region_index: usize,
    mut diagnostics: Vec<NeutralDiagnostic>,
    issues: &mut Vec<SemanticAssociationIssue>,
) {
    diagnostics.sort_by_key(|diagnostic| diagnostic.span.start_byte);
    issues.extend(
        diagnostics
            .into_iter()
            .map(|diagnostic| SemanticAssociationIssue {
                kind: match diagnostic.kind {
                    NeutralDiagnosticKind::Hole => SemanticAssociationIssueKind::UpstreamHole,
                    NeutralDiagnosticKind::Conflict => {
                        SemanticAssociationIssueKind::UpstreamConflict
                    }
                    NeutralDiagnosticKind::Unknown => SemanticAssociationIssueKind::UpstreamUnknown,
                },
                region_index,
                occurrences: Vec::new(),
                upstream_diagnostic: Some(diagnostic),
            }),
    );
}

fn entity_occurrence_count(entity: &SemanticEntity) -> usize {
    1 + usize::from(entity.color.is_some())
        + usize::from(entity.quantity.is_some())
        + usize::from(entity.touch.is_some())
        + usize::from(entity.continuity.is_some())
        + usize::from(entity.angle.is_some())
}

fn canonical_ast_bytes(ast: &SemanticEntityAssociationAst) -> Vec<u8> {
    let entities = ast
        .entities
        .iter()
        .map(semantic_entity_value)
        .collect::<Vec<_>>();
    let mut root = BTreeMap::new();
    root.insert("entities".to_owned(), Value::Array(entities));
    root.insert(
        "schema".to_owned(),
        Value::String(SEMANTIC_ENTITY_ASSOCIATION_SCHEMA_ID.to_owned()),
    );
    serde_json::to_vec(&root).expect("closed semantic association AST serializes")
}

pub(crate) fn semantic_entity_value(entity: &SemanticEntity) -> Value {
    let mut record = BTreeMap::new();
    record.insert(
        "angle".to_owned(),
        entity
            .angle
            .as_ref()
            .map(|angle| semantic_identity_value(&angle.identity))
            .unwrap_or(Value::Null),
    );
    record.insert(
        "color".to_owned(),
        entity
            .color
            .as_ref()
            .map(|color| semantic_identity_value(&color.identity))
            .unwrap_or(Value::Null),
    );
    record.insert(
        "continuity".to_owned(),
        entity
            .continuity
            .as_ref()
            .map(|continuity| semantic_identity_value(&continuity.identity))
            .unwrap_or(Value::Null),
    );
    record.insert(
        "head".to_owned(),
        semantic_identity_value(&entity.head.identity),
    );
    record.insert(
        "touch".to_owned(),
        entity
            .touch
            .as_ref()
            .map(|touch| semantic_identity_value(&touch.identity))
            .unwrap_or(Value::Null),
    );
    record.insert(
        "quantity".to_owned(),
        entity
            .quantity
            .as_ref()
            .map(|quantity| Value::Number(Number::from(quantity.value)))
            .unwrap_or(Value::Null),
    );
    Value::Object(record.into_iter().collect())
}

pub(crate) fn semantic_identity_value(identity: &SemanticIdentity) -> Value {
    let mut record = BTreeMap::new();
    record.insert(
        "category".to_owned(),
        Value::String(identity.category.clone()),
    );
    record.insert("id".to_owned(), Value::String(identity.id.clone()));
    Value::Object(record.into_iter().collect())
}
