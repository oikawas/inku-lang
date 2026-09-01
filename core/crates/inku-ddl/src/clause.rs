//! Source-preserving clause stream over the accepted neutral and typed deliveries.

use std::fmt;

use crate::{
    CanonicalRelationIdentity, CoreModifierTerm, CoreRoleTerm, NeutralDiagnostic, NeutralToken,
    NeutralTokenKind, NormalizedDdlDocument, RemainingRoleTerm, SourceSpan, UnattachedExactNumber,
    compose_core_roles, compose_remaining_roles, parse_neutral_lexemes,
};

/// Stable identity for the runtime-disconnected clause-stream foundation.
pub const CLAUSE_STREAM_SCHEMA_ID: &str = "inku.clause-stream.v3";

/// A source separator that ends one clause fragment.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum ClauseSeparatorKind {
    LineBreak,
    SentenceEnd,
}

/// One exact source separator, including both bytes of a CRLF line ending.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct ClauseSeparator {
    pub kind: ClauseSeparatorKind,
    pub span: SourceSpan,
}

/// One delivery retained at its exact source location.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ClauseAtom {
    CoreRole(CoreRoleTerm),
    CoreModifier(CoreModifierTerm),
    RemainingRole(RemainingRoleTerm),
    UnattachedExactNumber(UnattachedExactNumber),
    FunctionWord {
        surface: String,
        span: SourceSpan,
    },
    SaijikiRelation {
        asset_id: String,
        relation_type: String,
        canonical_identity: CanonicalRelationIdentity,
        surface: String,
        span: SourceSpan,
    },
    UnresolvedDiagnostic(NeutralDiagnostic),
}

impl ClauseAtom {
    /// Return this atom's half-open UTF-8 byte span into the source document.
    pub const fn span(&self) -> SourceSpan {
        match self {
            Self::CoreRole(term) => term.span,
            Self::CoreModifier(term) => term.span,
            Self::RemainingRole(term) => term.span,
            Self::UnattachedExactNumber(number) => number.span,
            Self::FunctionWord { span, .. } | Self::SaijikiRelation { span, .. } => *span,
            Self::UnresolvedDiagnostic(diagnostic) => diagnostic.span,
        }
    }

    const fn contributes_to_delivery_conservation(&self) -> bool {
        !matches!(self, Self::UnresolvedDiagnostic(diagnostic) if !diagnostic.recognized)
    }
}

/// One non-empty semantic clause fragment. Its span excludes source separators.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ClauseSegment {
    pub span: SourceSpan,
    pub atoms: Vec<ClauseAtom>,
}

/// Source-ordered clauses and separators derived from one normalized document.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ClauseStream {
    pub clauses: Vec<ClauseSegment>,
    pub separators: Vec<ClauseSeparator>,
    pub delivery_conservation_count: usize,
}

/// Stable source-integrity failures that cannot be silently reordered or dropped.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ClauseStreamError {
    InvalidAtomSpan {
        atom_span: SourceSpan,
    },
    OverlappingAtoms {
        earlier_span: SourceSpan,
        later_span: SourceSpan,
    },
    AtomCrossesSeparator {
        atom_span: SourceSpan,
        separator_span: SourceSpan,
    },
    UnsupportedDeferredToken {
        atom_span: SourceSpan,
    },
    AtomOutsideClause {
        atom_span: SourceSpan,
    },
    MultipleClauseMembership {
        atom_span: SourceSpan,
    },
    DeliveryConservationMismatch {
        expected: usize,
        actual: usize,
    },
}

impl fmt::Display for ClauseStreamError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::InvalidAtomSpan { atom_span } => write!(
                formatter,
                "invalid atom span {}..{}",
                atom_span.start_byte, atom_span.end_byte
            ),
            Self::OverlappingAtoms {
                earlier_span,
                later_span,
            } => write!(
                formatter,
                "overlapping atom spans {}..{} and {}..{}",
                earlier_span.start_byte,
                earlier_span.end_byte,
                later_span.start_byte,
                later_span.end_byte
            ),
            Self::AtomCrossesSeparator {
                atom_span,
                separator_span,
            } => write!(
                formatter,
                "atom span {}..{} crosses separator {}..{}",
                atom_span.start_byte,
                atom_span.end_byte,
                separator_span.start_byte,
                separator_span.end_byte
            ),
            Self::UnsupportedDeferredToken { atom_span } => write!(
                formatter,
                "unsupported deferred token at {}..{}",
                atom_span.start_byte, atom_span.end_byte
            ),
            Self::AtomOutsideClause { atom_span } => write!(
                formatter,
                "atom span {}..{} is outside every clause",
                atom_span.start_byte, atom_span.end_byte
            ),
            Self::MultipleClauseMembership { atom_span } => write!(
                formatter,
                "atom span {}..{} belongs to multiple clauses",
                atom_span.start_byte, atom_span.end_byte
            ),
            Self::DeliveryConservationMismatch { expected, actual } => write!(
                formatter,
                "delivery conservation mismatch: expected {expected}, actual {actual}"
            ),
        }
    }
}

impl std::error::Error for ClauseStreamError {}

/// Parse and compose one document exactly once into a source-ordered clause stream.
pub fn parse_clause_stream(
    document: &NormalizedDdlDocument,
) -> Result<ClauseStream, ClauseStreamError> {
    let composition = compose_remaining_roles(compose_core_roles(parse_neutral_lexemes(document)));
    let delivery_conservation_count = composition.delivery_conservation_count;
    let mut atoms = Vec::new();

    atoms.extend(composition.core_roles.into_iter().map(ClauseAtom::CoreRole));
    atoms.extend(
        composition
            .core_modifiers
            .into_iter()
            .map(ClauseAtom::CoreModifier),
    );
    atoms.extend(
        composition
            .remaining_roles
            .into_iter()
            .map(ClauseAtom::RemainingRole),
    );
    atoms.extend(
        composition
            .unattached_exact_numbers
            .into_iter()
            .map(ClauseAtom::UnattachedExactNumber),
    );
    for token in composition.deferred_tokens {
        atoms.push(atom_from_deferred_token(token)?);
    }
    atoms.extend(
        composition
            .diagnostics
            .into_iter()
            .map(ClauseAtom::UnresolvedDiagnostic),
    );

    let source = document.source();
    for atom in &atoms {
        let span = atom.span();
        if span.start_byte >= span.end_byte
            || span.end_byte > source.len()
            || !source.is_char_boundary(span.start_byte)
            || !source.is_char_boundary(span.end_byte)
        {
            return Err(ClauseStreamError::InvalidAtomSpan { atom_span: span });
        }
    }

    // This is deliberately stable: an impossible same-start tie is reported below,
    // never resolved by inventing an atom-class precedence.
    atoms.sort_by_key(|atom| atom.span().start_byte);
    for pair in atoms.windows(2) {
        let earlier_span = pair[0].span();
        let later_span = pair[1].span();
        if earlier_span.end_byte > later_span.start_byte {
            return Err(ClauseStreamError::OverlappingAtoms {
                earlier_span,
                later_span,
            });
        }
    }

    let separators = collect_separators(source)
        .into_iter()
        .filter(|separator| {
            !atoms
                .iter()
                .any(|atom| contains(atom.span(), separator.span))
        })
        .collect::<Vec<_>>();
    for atom in &atoms {
        let atom_span = atom.span();
        if let Some(separator) = separators
            .iter()
            .find(|separator| spans_overlap(atom_span, separator.span))
        {
            return Err(ClauseStreamError::AtomCrossesSeparator {
                atom_span,
                separator_span: separator.span,
            });
        }
    }

    let actual_delivery_count = atoms
        .iter()
        .filter(|atom| atom.contributes_to_delivery_conservation())
        .count();
    if actual_delivery_count != delivery_conservation_count {
        return Err(ClauseStreamError::DeliveryConservationMismatch {
            expected: delivery_conservation_count,
            actual: actual_delivery_count,
        });
    }

    let fragments = clause_fragments(source.len(), &separators);
    for atom in &atoms {
        let atom_span = atom.span();
        let membership_count = fragments
            .iter()
            .filter(|fragment| contains(**fragment, atom_span))
            .count();
        match membership_count {
            0 => return Err(ClauseStreamError::AtomOutsideClause { atom_span }),
            1 => {}
            _ => return Err(ClauseStreamError::MultipleClauseMembership { atom_span }),
        }
    }

    let mut clauses = fragments
        .iter()
        .copied()
        .filter(|fragment| atoms.iter().any(|atom| contains(*fragment, atom.span())))
        .map(|span| ClauseSegment {
            span,
            atoms: Vec::new(),
        })
        .collect::<Vec<_>>();
    for atom in atoms {
        let clause = clauses
            .iter_mut()
            .find(|clause| contains(clause.span, atom.span()))
            .ok_or(ClauseStreamError::AtomOutsideClause {
                atom_span: atom.span(),
            })?;
        clause.atoms.push(atom);
    }

    Ok(ClauseStream {
        clauses,
        separators,
        delivery_conservation_count,
    })
}

fn atom_from_deferred_token(token: NeutralToken) -> Result<ClauseAtom, ClauseStreamError> {
    let NeutralToken {
        span,
        surface,
        kind,
    } = token;
    match kind {
        NeutralTokenKind::FunctionWord => Ok(ClauseAtom::FunctionWord { surface, span }),
        NeutralTokenKind::SaijikiRelation {
            asset_id,
            relation_type,
            canonical_identity,
        } => Ok(ClauseAtom::SaijikiRelation {
            asset_id,
            relation_type,
            canonical_identity,
            surface,
            span,
        }),
        NeutralTokenKind::CoreModifier(_)
        | NeutralTokenKind::SaijikiWord { .. }
        | NeutralTokenKind::ExactNumber { .. } => {
            Err(ClauseStreamError::UnsupportedDeferredToken { atom_span: span })
        }
    }
}

fn collect_separators(source: &str) -> Vec<ClauseSeparator> {
    let mut separators = Vec::new();
    let mut characters = source.char_indices().peekable();
    while let Some((start_byte, character)) = characters.next() {
        if character == '\r'
            && characters
                .peek()
                .is_some_and(|(_, next_character)| *next_character == '\n')
        {
            let (newline_start, newline) = characters.next().expect("peeked CRLF newline");
            separators.push(ClauseSeparator {
                kind: ClauseSeparatorKind::LineBreak,
                span: SourceSpan {
                    start_byte,
                    end_byte: newline_start + newline.len_utf8(),
                },
            });
            continue;
        }
        let kind = match character {
            '\n' => Some(ClauseSeparatorKind::LineBreak),
            '。' | '.' | '！' | '!' | '？' | '?' => Some(ClauseSeparatorKind::SentenceEnd),
            _ => None,
        };
        if let Some(kind) = kind {
            separators.push(ClauseSeparator {
                kind,
                span: SourceSpan {
                    start_byte,
                    end_byte: start_byte + character.len_utf8(),
                },
            });
        }
    }
    separators
}

fn clause_fragments(source_len: usize, separators: &[ClauseSeparator]) -> Vec<SourceSpan> {
    let mut fragments = Vec::new();
    let mut start_byte = 0;
    for separator in separators {
        if start_byte < separator.span.start_byte {
            fragments.push(SourceSpan {
                start_byte,
                end_byte: separator.span.start_byte,
            });
        }
        start_byte = separator.span.end_byte;
    }
    if start_byte < source_len {
        fragments.push(SourceSpan {
            start_byte,
            end_byte: source_len,
        });
    }
    fragments
}

const fn contains(container: SourceSpan, contained: SourceSpan) -> bool {
    container.start_byte <= contained.start_byte && contained.end_byte <= container.end_byte
}

const fn spans_overlap(left: SourceSpan, right: SourceSpan) -> bool {
    left.start_byte < right.end_byte && right.start_byte < left.end_byte
}
