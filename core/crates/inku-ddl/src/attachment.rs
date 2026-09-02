//! Meaning-neutral JA/EN attachment-marker evidence over the accepted clause stream.

use crate::{
    ClauseAtom, ClauseStreamError, EnglishNounPhraseEvidenceResult, NormalizedDdlDocument,
    ResolvedInstructionLanguage, SourceSpan, collect_english_noun_phrase_evidence,
};

/// Stable identity for the runtime-disconnected attachment evidence foundation.
pub const ATTACHMENT_EVIDENCE_SCHEMA_ID: &str = "inku.attachment-evidence.v2";

/// Language-independent identity of an explicit coordinated-head marker candidate.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum CoordinationMarkerKind {
    HeadConjunction,
}

/// One accepted FunctionWord projected to language-independent coordination evidence.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct CoordinationMarkerEvidence {
    pub kind: CoordinationMarkerKind,
    pub source: SourceSpan,
    pub clause_index: usize,
    pub clause_span: SourceSpan,
    pub left_atom_spans: Vec<SourceSpan>,
    pub right_atom_spans: Vec<SourceSpan>,
}

impl CoordinationMarkerKind {
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::HeadConjunction => "head_conjunction",
        }
    }
}

/// Canonical identity of one accepted Japanese attachment-marker function word.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum JapaneseAttachmentMarkerKind {
    Wo,
    Ni,
    De,
    No,
    Wa,
    Ga,
    He,
    To,
}

impl JapaneseAttachmentMarkerKind {
    fn from_surface(surface: &str) -> Option<Self> {
        match surface {
            "を" => Some(Self::Wo),
            "に" => Some(Self::Ni),
            "で" => Some(Self::De),
            "の" => Some(Self::No),
            "は" => Some(Self::Wa),
            "が" => Some(Self::Ga),
            "へ" => Some(Self::He),
            "と" => Some(Self::To),
            _ => None,
        }
    }
}

/// Canonical identity of one accepted English attachment-marker function word.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum EnglishAttachmentMarkerKind {
    With,
    In,
    At,
    On,
    To,
    Of,
}

impl EnglishAttachmentMarkerKind {
    fn from_ascii_case_insensitive_surface(surface: &str) -> Option<Self> {
        if surface.eq_ignore_ascii_case("with") {
            Some(Self::With)
        } else if surface.eq_ignore_ascii_case("in") {
            Some(Self::In)
        } else if surface.eq_ignore_ascii_case("at") {
            Some(Self::At)
        } else if surface.eq_ignore_ascii_case("on") {
            Some(Self::On)
        } else if surface.eq_ignore_ascii_case("to") {
            Some(Self::To)
        } else if surface.eq_ignore_ascii_case("of") {
            Some(Self::Of)
        } else {
            None
        }
    }
}

/// Language-specific attachment-marker identity without relation semantics.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum AttachmentMarkerKind {
    Japanese(JapaneseAttachmentMarkerKind),
    English(EnglishAttachmentMarkerKind),
}

/// One recognized marker and its complete same-clause mechanical context.
///
/// Noun-phrase indexes record containment only. This type does not select a
/// relation, attachment target, subject, object, location, instrument, or path.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct AttachmentMarkerEvidence {
    pub language: ResolvedInstructionLanguage,
    pub marker: AttachmentMarkerKind,
    pub surface: String,
    pub span: SourceSpan,
    pub clause_index: usize,
    pub clause_span: SourceSpan,
    pub left_context_span: Option<SourceSpan>,
    pub right_context_span: Option<SourceSpan>,
    pub left_atom_spans: Vec<SourceSpan>,
    pub right_atom_spans: Vec<SourceSpan>,
    pub left_noun_phrase_evidence_indices: Vec<usize>,
    pub right_noun_phrase_evidence_indices: Vec<usize>,
    pub left_noun_phrase_diagnostic_indices: Vec<usize>,
    pub right_noun_phrase_diagnostic_indices: Vec<usize>,
}

/// Stable evidence-availability diagnostics without semantic defaults.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum AttachmentEvidenceDiagnosticKind {
    MissingLeftContext,
    MissingRightContext,
}

/// One unavailable side of one attachment marker's mechanical context.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct AttachmentEvidenceDiagnostic {
    pub kind: AttachmentEvidenceDiagnosticKind,
    pub evidence_index: usize,
}

/// The accepted I-568 result plus a non-delivery attachment evidence overlay.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct AttachmentEvidenceResult {
    pub noun_phrase: EnglishNounPhraseEvidenceResult,
    pub evidence: Vec<AttachmentMarkerEvidence>,
    pub coordination_evidence: Vec<CoordinationMarkerEvidence>,
    pub diagnostics: Vec<AttachmentEvidenceDiagnostic>,
}

/// Collect meaning-neutral JA/EN attachment-marker evidence from one document.
///
/// The I-568 entrypoint runs exactly once. Its owned result and clause stream are
/// retained unchanged while this function records source spans and containment.
pub fn collect_attachment_evidence(
    document: &NormalizedDdlDocument,
) -> Result<AttachmentEvidenceResult, ClauseStreamError> {
    let noun_phrase = collect_english_noun_phrase_evidence(document)?;
    let language = document.language();
    let source = document.source();
    let mut evidence = Vec::new();
    let mut diagnostics = Vec::new();

    for (clause_index, clause) in noun_phrase.clause_stream.clauses.iter().enumerate() {
        for atom in &clause.atoms {
            let ClauseAtom::FunctionWord { span, .. } = atom else {
                continue;
            };
            let surface = &source[span.start_byte..span.end_byte];
            let Some(marker) = marker_from_surface(language, surface) else {
                continue;
            };

            let left_context_span =
                (clause.span.start_byte < span.start_byte).then_some(SourceSpan {
                    start_byte: clause.span.start_byte,
                    end_byte: span.start_byte,
                });
            let right_context_span = (span.end_byte < clause.span.end_byte).then_some(SourceSpan {
                start_byte: span.end_byte,
                end_byte: clause.span.end_byte,
            });
            let left_atom_spans = clause
                .atoms
                .iter()
                .filter(|candidate| candidate.span().end_byte <= span.start_byte)
                .map(ClauseAtom::span)
                .collect::<Vec<_>>();
            let right_atom_spans = clause
                .atoms
                .iter()
                .filter(|candidate| span.end_byte <= candidate.span().start_byte)
                .map(ClauseAtom::span)
                .collect::<Vec<_>>();

            let evidence_index = evidence.len();
            if left_atom_spans.is_empty() {
                diagnostics.push(AttachmentEvidenceDiagnostic {
                    kind: AttachmentEvidenceDiagnosticKind::MissingLeftContext,
                    evidence_index,
                });
            }
            if right_atom_spans.is_empty() {
                diagnostics.push(AttachmentEvidenceDiagnostic {
                    kind: AttachmentEvidenceDiagnosticKind::MissingRightContext,
                    evidence_index,
                });
            }

            evidence.push(AttachmentMarkerEvidence {
                language,
                marker,
                surface: surface.to_owned(),
                span: *span,
                clause_index,
                clause_span: clause.span,
                left_context_span,
                right_context_span,
                left_atom_spans,
                right_atom_spans,
                left_noun_phrase_evidence_indices: noun_phrase_evidence_indices(
                    &noun_phrase,
                    clause_index,
                    left_context_span,
                ),
                right_noun_phrase_evidence_indices: noun_phrase_evidence_indices(
                    &noun_phrase,
                    clause_index,
                    right_context_span,
                ),
                left_noun_phrase_diagnostic_indices: noun_phrase_diagnostic_indices(
                    &noun_phrase,
                    clause_index,
                    left_context_span,
                ),
                right_noun_phrase_diagnostic_indices: noun_phrase_diagnostic_indices(
                    &noun_phrase,
                    clause_index,
                    right_context_span,
                ),
            });
        }
    }

    let coordination_evidence =
        collect_coordination_marker_evidence(document, &noun_phrase.clause_stream);
    Ok(AttachmentEvidenceResult {
        noun_phrase,
        evidence,
        coordination_evidence,
        diagnostics,
    })
}

pub(crate) fn collect_coordination_marker_evidence(
    document: &NormalizedDdlDocument,
    clause_stream: &crate::ClauseStream,
) -> Vec<CoordinationMarkerEvidence> {
    let mut evidence = Vec::new();
    for (clause_index, clause) in clause_stream.clauses.iter().enumerate() {
        for atom in &clause.atoms {
            let ClauseAtom::FunctionWord { span, .. } = atom else {
                continue;
            };
            let surface = &document.source()[span.start_byte..span.end_byte];
            let recognized = match document.language() {
                ResolvedInstructionLanguage::Ja => surface == "と",
                ResolvedInstructionLanguage::En => surface.eq_ignore_ascii_case("and"),
            };
            if !recognized {
                continue;
            }
            evidence.push(CoordinationMarkerEvidence {
                kind: CoordinationMarkerKind::HeadConjunction,
                source: *span,
                clause_index,
                clause_span: clause.span,
                left_atom_spans: clause
                    .atoms
                    .iter()
                    .filter(|candidate| candidate.span().end_byte <= span.start_byte)
                    .map(ClauseAtom::span)
                    .collect(),
                right_atom_spans: clause
                    .atoms
                    .iter()
                    .filter(|candidate| span.end_byte <= candidate.span().start_byte)
                    .map(ClauseAtom::span)
                    .collect(),
            });
        }
    }
    evidence
}

fn marker_from_surface(
    language: ResolvedInstructionLanguage,
    surface: &str,
) -> Option<AttachmentMarkerKind> {
    match language {
        ResolvedInstructionLanguage::Ja => {
            JapaneseAttachmentMarkerKind::from_surface(surface).map(AttachmentMarkerKind::Japanese)
        }
        ResolvedInstructionLanguage::En => {
            EnglishAttachmentMarkerKind::from_ascii_case_insensitive_surface(surface)
                .map(AttachmentMarkerKind::English)
        }
    }
}

fn noun_phrase_evidence_indices(
    noun_phrase: &EnglishNounPhraseEvidenceResult,
    clause_index: usize,
    context_span: Option<SourceSpan>,
) -> Vec<usize> {
    let Some(context_span) = context_span else {
        return Vec::new();
    };
    noun_phrase
        .evidence
        .iter()
        .enumerate()
        .filter(|(_, candidate)| {
            candidate.clause_index == clause_index
                && contains(context_span, candidate.candidate_region_span)
        })
        .map(|(index, _)| index)
        .collect()
}

fn noun_phrase_diagnostic_indices(
    noun_phrase: &EnglishNounPhraseEvidenceResult,
    clause_index: usize,
    context_span: Option<SourceSpan>,
) -> Vec<usize> {
    let Some(context_span) = context_span else {
        return Vec::new();
    };
    noun_phrase
        .diagnostics
        .iter()
        .enumerate()
        .filter(|(_, diagnostic)| {
            diagnostic.clause_index == clause_index
                && contains(context_span, diagnostic.candidate_region_span)
        })
        .map(|(index, _)| index)
        .collect()
}

const fn contains(container: SourceSpan, contained: SourceSpan) -> bool {
    container.start_byte <= contained.start_byte && contained.end_byte <= container.end_byte
}
