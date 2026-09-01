//! Meaning-neutral lexeme recognition over a source-preserving DDL document.

use std::collections::HashSet;

use crate::{
    CanonicalRelationForm, CanonicalRelationIdentity, NormalizedDdlDocument,
    ResolvedInstructionLanguage, SAIJIKI_ASSET_ID,
    saijiki::{canonical_relation_identity, parser_candidate_surface},
    saijiki_asset,
};

/// Stable identity for the runtime-disconnected neutral parser foundation.
pub const NEUTRAL_LEXEME_PARSER_SCHEMA_ID: &str = "inku.neutral-lexeme-parser.v4";

/// A half-open UTF-8 byte span into the source document.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct SourceSpan {
    pub start_byte: usize,
    pub end_byte: usize,
}

/// One meaning-neutral recognized lexical item.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct NeutralToken {
    pub span: SourceSpan,
    pub surface: String,
    pub kind: NeutralTokenKind,
}

/// Closed core modifier dimension independent of the Saijiki asset.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum CoreModifierDimension {
    Thinness,
}

impl CoreModifierDimension {
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::Thinness => "thinness",
        }
    }
}

/// Closed core modifier value independent of localized source spelling.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum CoreModifierValue {
    Fine,
}

impl CoreModifierValue {
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::Fine => "fine",
        }
    }
}

/// Language-independent identity of one recognized core modifier.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct CoreModifierIdentity {
    pub dimension: CoreModifierDimension,
    pub value: CoreModifierValue,
}

/// The lexical identity of a recognized item, before typed composition.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum NeutralTokenKind {
    CoreModifier(CoreModifierIdentity),
    SaijikiWord {
        asset_id: String,
        category_key: String,
        canonical_surface_ja: String,
    },
    SaijikiRelation {
        asset_id: String,
        relation_type: String,
        canonical_identity: CanonicalRelationIdentity,
    },
    FunctionWord,
    ExactNumber {
        value: u64,
    },
}

/// Stable parser diagnostic classes without an aggregate resolution policy.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum NeutralDiagnosticKind {
    Hole,
    Conflict,
    Unknown,
}

/// One source-preserving parser diagnostic.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct NeutralDiagnostic {
    pub span: SourceSpan,
    pub surface: String,
    pub kind: NeutralDiagnosticKind,
    /// Whether the surface was recognized but deliberately delivered as a diagnostic.
    pub recognized: bool,
}

/// Ordered, partial lexical recognition without defaults or typed composition.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct NeutralParseResult {
    pub tokens: Vec<NeutralToken>,
    pub diagnostics: Vec<NeutralDiagnostic>,
    pub recognized_delivery_count: usize,
}

const FUNCTION_WORDS_JA: &[&str] = &["を", "に", "で", "の", "は", "が", "へ", "と"];
// V1 closed Japanese morphology classes. These are grammatical classes over accepted
// canonical rows, not aliases or independent semantic vocabulary.
const JAPANESE_COLOR_I_ADJECTIVE_STEMS_V1: &[&str] = &["白", "黒", "青", "赤"];
const JAPANESE_COUNTERS_V1: &[&str] = &["本", "個", "枚"];
const FUNCTION_WORDS_EN: &[&str] = &[
    "a", "an", "the", "with", "in", "at", "on", "to", "of", "and",
];
const NATIVE_TSU_CARDINALS_JA: &[(&str, u64)] = &[
    ("ひとつ", 1),
    ("ふたつ", 2),
    ("みっつ", 3),
    ("よっつ", 4),
    ("いつつ", 5),
    ("むっつ", 6),
    ("ななつ", 7),
    ("やっつ", 8),
    ("ここのつ", 9),
    ("とお", 10),
];
const QUALITATIVE_QUANTITIES_JA: &[&str] =
    &["少し", "数個", "いくつか", "たくさん", "多数", "無数"];
const QUALITATIVE_QUANTITIES_EN: &[&str] = &["a few", "several", "many", "numerous", "countless"];

const PRIORITY_FUNCTION: u8 = 1;
const PRIORITY_NUMBER: u8 = 2;
const PRIORITY_ASSET: u8 = 3;
const PRIORITY_CORE_MODIFIER: u8 = 3;

/// Recognize source lexemes without rewriting source or completing their meaning.
pub fn parse_neutral_lexemes(document: &NormalizedDdlDocument) -> NeutralParseResult {
    let source = document.source();
    let language = document.language();
    let mut tokens = Vec::new();
    let mut diagnostics = Vec::new();
    let mut recognized_delivery_count = 0;
    let mut cursor = 0;

    while cursor < source.len() {
        match selection_at(document, cursor, language) {
            Some(Selection::Token { end_byte, kind }) => {
                tokens.push(NeutralToken {
                    span: SourceSpan {
                        start_byte: cursor,
                        end_byte,
                    },
                    surface: source[cursor..end_byte].to_owned(),
                    kind,
                });
                recognized_delivery_count += 1;
                cursor = end_byte;
            }
            Some(Selection::Hole { end_byte }) => {
                diagnostics.push(diagnostic(
                    source,
                    cursor,
                    end_byte,
                    NeutralDiagnosticKind::Hole,
                    true,
                ));
                recognized_delivery_count += 1;
                cursor = end_byte;
            }
            Some(Selection::Conflict { end_byte }) => {
                diagnostics.push(diagnostic(
                    source,
                    cursor,
                    end_byte,
                    NeutralDiagnosticKind::Conflict,
                    true,
                ));
                recognized_delivery_count += 1;
                cursor = end_byte;
            }
            Some(Selection::Unknown { end_byte }) => {
                diagnostics.push(diagnostic(
                    source,
                    cursor,
                    end_byte,
                    NeutralDiagnosticKind::Unknown,
                    false,
                ));
                cursor = end_byte;
            }
            None => {
                let character = source[cursor..]
                    .chars()
                    .next()
                    .expect("cursor is inside source");
                if is_separator(character) {
                    cursor += character.len_utf8();
                    continue;
                }

                let end_byte = unknown_end(document, cursor, language);
                diagnostics.push(diagnostic(
                    source,
                    cursor,
                    end_byte,
                    NeutralDiagnosticKind::Unknown,
                    false,
                ));
                cursor = end_byte;
            }
        }
    }

    NeutralParseResult {
        tokens,
        diagnostics,
        recognized_delivery_count,
    }
}

fn selection_at(
    document: &NormalizedDdlDocument,
    start_byte: usize,
    language: ResolvedInstructionLanguage,
) -> Option<Selection> {
    let source = document.source();
    if let Some(end_byte) = unsupported_numeric_end(source, start_byte) {
        return Some(Selection::Hole { end_byte });
    }
    if let Some(macro_match) = qualified_macro_match(document, start_byte) {
        return Some(match macro_match {
            QualifiedMacroMatch::Unlocked { end_byte }
            | QualifiedMacroMatch::ExactLock { end_byte, .. } => Selection::Unknown { end_byte },
            QualifiedMacroMatch::AmbiguousLocks { end_byte, .. } => {
                Selection::Conflict { end_byte }
            }
        });
    }
    select_candidate(candidates_at_with_locked_macro_boundary(
        document, start_byte, language,
    ))
}

fn candidates_at_with_locked_macro_boundary(
    document: &NormalizedDdlDocument,
    start_byte: usize,
    language: ResolvedInstructionLanguage,
) -> Vec<Candidate> {
    let source = document.source();
    let mut candidates = candidates_at(source, start_byte, language, true);
    for candidate in candidates_at(source, start_byte, language, false) {
        let followed_by_locked_macro = matches!(
            qualified_macro_match(document, candidate.end_byte),
            Some(QualifiedMacroMatch::ExactLock { .. })
                | Some(QualifiedMacroMatch::AmbiguousLocks { .. })
        );
        let already_present = candidates.iter().any(|existing| existing == &candidate);
        if followed_by_locked_macro && !already_present {
            candidates.push(candidate);
        }
    }
    candidates
}

#[derive(Clone, Debug, Eq, PartialEq)]
enum CandidateDelivery {
    Token(NeutralTokenKind),
    Hole,
}

#[derive(Clone, Debug, Eq, PartialEq)]
struct Candidate {
    end_byte: usize,
    priority: u8,
    identity: String,
    delivery: CandidateDelivery,
}

#[derive(Clone, Debug, Eq, PartialEq)]
enum Selection {
    Token {
        end_byte: usize,
        kind: NeutralTokenKind,
    },
    Hole {
        end_byte: usize,
    },
    Conflict {
        end_byte: usize,
    },
    Unknown {
        end_byte: usize,
    },
}

/// A visible qualified term and the byte-exact sidecar locks that start at its cursor.
#[derive(Clone, Debug, Eq, PartialEq)]
pub(crate) enum QualifiedMacroMatch {
    Unlocked {
        end_byte: usize,
    },
    ExactLock {
        end_byte: usize,
        lock_index: usize,
    },
    AmbiguousLocks {
        end_byte: usize,
        lock_indices: Vec<usize>,
    },
}

/// Return only current-cursor, byte-exact lock prefixes without normalization or precedence.
pub(crate) fn qualified_macro_match(
    document: &NormalizedDdlDocument,
    start_byte: usize,
) -> Option<QualifiedMacroMatch> {
    let source = document.source();
    let unlocked_end = qualified_macro_end(source, start_byte)?;
    let lock_indices = document
        .macro_locks()
        .iter()
        .enumerate()
        .filter(|(_, macro_lock)| {
            let qualified_name = macro_lock.qualified_name();
            is_visible_qualified_name(qualified_name)
                && source.get(start_byte..start_byte + qualified_name.len()) == Some(qualified_name)
        })
        .map(|(index, _)| index)
        .collect::<Vec<_>>();

    match lock_indices.as_slice() {
        [] => Some(QualifiedMacroMatch::Unlocked {
            end_byte: unlocked_end,
        }),
        [lock_index] => Some(QualifiedMacroMatch::ExactLock {
            end_byte: start_byte + document.macro_locks()[*lock_index].qualified_name().len(),
            lock_index: *lock_index,
        }),
        _ => Some(QualifiedMacroMatch::AmbiguousLocks {
            end_byte: unlocked_end,
            lock_indices,
        }),
    }
}

fn candidates_at(
    source: &str,
    start_byte: usize,
    language: ResolvedInstructionLanguage,
    require_boundary: bool,
) -> Vec<Candidate> {
    let mut candidates = Vec::new();
    let asset = saijiki_asset();

    let core_modifier_surface = match language {
        ResolvedInstructionLanguage::Ja => "細い",
        ResolvedInstructionLanguage::En => "thin",
    };
    if language != ResolvedInstructionLanguage::Ja
        || !require_boundary
        || has_japanese_recognized_left_boundary(source, start_byte)
    {
        push_surface_candidate(
            &mut candidates,
            source,
            start_byte,
            language,
            require_boundary,
            core_modifier_surface,
            PRIORITY_CORE_MODIFIER,
            "core_modifier:thinness:fine".to_owned(),
            CandidateDelivery::Token(NeutralTokenKind::CoreModifier(CoreModifierIdentity {
                dimension: CoreModifierDimension::Thinness,
                value: CoreModifierValue::Fine,
            })),
        );
    }

    for category in &asset.categories {
        for word in &category.words {
            let Some(surface) = parser_candidate_surface(word, language) else {
                continue;
            };
            push_surface_candidate(
                &mut candidates,
                source,
                start_byte,
                language,
                require_boundary,
                surface,
                PRIORITY_ASSET,
                format!("word:{}:{}", category.key, word.surface_ja),
                CandidateDelivery::Token(NeutralTokenKind::SaijikiWord {
                    asset_id: SAIJIKI_ASSET_ID.to_owned(),
                    category_key: category.key.clone(),
                    canonical_surface_ja: word.surface_ja.clone(),
                }),
            );
            if language == ResolvedInstructionLanguage::Ja && category.key == "iro" {
                if JAPANESE_COLOR_I_ADJECTIVE_STEMS_V1.contains(&word.surface_ja.as_str()) {
                    push_japanese_derived_surface_candidate(
                        &mut candidates,
                        source,
                        start_byte,
                        require_boundary,
                        surface,
                        "い",
                        PRIORITY_ASSET,
                        format!("word:{}:{}", category.key, word.surface_ja),
                        CandidateDelivery::Token(NeutralTokenKind::SaijikiWord {
                            asset_id: SAIJIKI_ASSET_ID.to_owned(),
                            category_key: category.key.clone(),
                            canonical_surface_ja: word.surface_ja.clone(),
                        }),
                    );
                }
                push_japanese_derived_surface_candidate(
                    &mut candidates,
                    source,
                    start_byte,
                    require_boundary,
                    surface,
                    "色",
                    PRIORITY_ASSET,
                    format!("word:{}:{}", category.key, word.surface_ja),
                    CandidateDelivery::Token(NeutralTokenKind::SaijikiWord {
                        asset_id: SAIJIKI_ASSET_ID.to_owned(),
                        category_key: category.key.clone(),
                        canonical_surface_ja: word.surface_ja.clone(),
                    }),
                );
            }
        }
    }

    for relation in &asset.relations {
        let (surface, full_literals) = match language {
            ResolvedInstructionLanguage::Ja => {
                (relation.surface_ja.as_str(), &relation.literals_ja)
            }
            ResolvedInstructionLanguage::En => {
                (relation.surface_en.as_str(), &relation.literals_en)
            }
        };
        for (surface, form) in std::iter::once((surface, CanonicalRelationForm::Short)).chain(
            full_literals
                .iter()
                .map(|literal| (literal.as_str(), CanonicalRelationForm::FullLiteral)),
        ) {
            let delivery = canonical_relation_identity(&relation.relation_type, form)
                .map(|canonical_identity| {
                    CandidateDelivery::Token(NeutralTokenKind::SaijikiRelation {
                        asset_id: SAIJIKI_ASSET_ID.to_owned(),
                        relation_type: relation.relation_type.clone(),
                        canonical_identity,
                    })
                })
                .unwrap_or(CandidateDelivery::Hole);
            push_surface_candidate(
                &mut candidates,
                source,
                start_byte,
                language,
                require_boundary,
                surface,
                PRIORITY_ASSET,
                format!("relation:{}:{}", relation.relation_type, form.as_str()),
                delivery,
            );
        }
    }

    let function_words = match language {
        ResolvedInstructionLanguage::Ja => FUNCTION_WORDS_JA,
        ResolvedInstructionLanguage::En => FUNCTION_WORDS_EN,
    };
    for surface in function_words {
        if language == ResolvedInstructionLanguage::Ja {
            push_japanese_function_candidate(
                &mut candidates,
                source,
                start_byte,
                require_boundary,
                surface,
                format!("function:{surface}"),
            );
        } else {
            push_surface_candidate(
                &mut candidates,
                source,
                start_byte,
                language,
                require_boundary,
                surface,
                PRIORITY_FUNCTION,
                format!("function:{surface}"),
                CandidateDelivery::Token(NeutralTokenKind::FunctionWord),
            );
        }
    }
    if language == ResolvedInstructionLanguage::Ja {
        for counter in JAPANESE_COUNTERS_V1 {
            push_japanese_counter_candidate(&mut candidates, source, start_byte, counter);
        }
    }

    if language == ResolvedInstructionLanguage::Ja {
        for (surface, value) in NATIVE_TSU_CARDINALS_JA {
            push_surface_candidate(
                &mut candidates,
                source,
                start_byte,
                language,
                require_boundary,
                surface,
                PRIORITY_NUMBER,
                format!("number:{value}"),
                CandidateDelivery::Token(NeutralTokenKind::ExactNumber { value: *value }),
            );
        }
    }
    let word_cardinal = match language {
        ResolvedInstructionLanguage::Ja => japanese_kanji_cardinal_at(source, start_byte),
        ResolvedInstructionLanguage::En => english_cardinal_at(source, start_byte),
    };
    if let Some((end_byte, value)) = word_cardinal {
        if !require_boundary || has_candidate_boundary(source, start_byte, end_byte, language) {
            candidates.push(Candidate {
                end_byte,
                priority: PRIORITY_NUMBER,
                identity: format!("number:{value}"),
                delivery: CandidateDelivery::Token(NeutralTokenKind::ExactNumber { value }),
            });
        }
    }

    let qualitative_quantities = match language {
        ResolvedInstructionLanguage::Ja => QUALITATIVE_QUANTITIES_JA,
        ResolvedInstructionLanguage::En => QUALITATIVE_QUANTITIES_EN,
    };
    for surface in qualitative_quantities {
        push_surface_candidate(
            &mut candidates,
            source,
            start_byte,
            language,
            require_boundary,
            surface,
            PRIORITY_NUMBER,
            format!("qualitative:{surface}"),
            CandidateDelivery::Hole,
        );
    }

    if source.as_bytes()[start_byte].is_ascii_digit() {
        let end_byte = source.as_bytes()[start_byte..]
            .iter()
            .take_while(|byte| byte.is_ascii_digit())
            .count()
            + start_byte;
        if !require_boundary || has_candidate_boundary(source, start_byte, end_byte, language) {
            let surface = &source[start_byte..end_byte];
            let delivery = match surface.parse::<u64>() {
                Ok(value) => CandidateDelivery::Token(NeutralTokenKind::ExactNumber { value }),
                Err(_) => CandidateDelivery::Hole,
            };
            candidates.push(Candidate {
                end_byte,
                priority: PRIORITY_NUMBER,
                identity: format!("decimal:{surface}"),
                delivery,
            });
        }
    }

    candidates
}

fn has_japanese_recognized_left_boundary(source: &str, start_byte: usize) -> bool {
    start_byte == 0
        || source[..start_byte]
            .chars()
            .next_back()
            .is_some_and(is_separator)
        || has_japanese_recognized_left_candidate(source, start_byte)
}

fn has_japanese_recognized_left_candidate(source: &str, start_byte: usize) -> bool {
    source[..start_byte]
        .char_indices()
        .any(|(candidate_start, _)| {
            candidates_at(
                source,
                candidate_start,
                ResolvedInstructionLanguage::Ja,
                false,
            )
            .iter()
            .any(|candidate| candidate.end_byte == start_byte)
        })
}

#[allow(clippy::too_many_arguments)]
fn push_surface_candidate(
    candidates: &mut Vec<Candidate>,
    source: &str,
    start_byte: usize,
    language: ResolvedInstructionLanguage,
    require_boundary: bool,
    surface: &str,
    priority: u8,
    identity: String,
    delivery: CandidateDelivery,
) {
    let end_byte = start_byte + surface.len();
    let Some(actual) = source.get(start_byte..end_byte) else {
        return;
    };
    let matches = match language {
        ResolvedInstructionLanguage::Ja => actual == surface,
        ResolvedInstructionLanguage::En => actual.eq_ignore_ascii_case(surface),
    };
    if !matches
        || (require_boundary && !has_candidate_boundary(source, start_byte, end_byte, language))
    {
        return;
    }
    candidates.push(Candidate {
        end_byte,
        priority,
        identity,
        delivery,
    });
}

#[allow(clippy::too_many_arguments)]
fn push_japanese_derived_surface_candidate(
    candidates: &mut Vec<Candidate>,
    source: &str,
    start_byte: usize,
    require_boundary: bool,
    stem: &str,
    suffix: &str,
    priority: u8,
    identity: String,
    delivery: CandidateDelivery,
) {
    let end_byte = start_byte + stem.len() + suffix.len();
    let Some(actual) = source.get(start_byte..end_byte) else {
        return;
    };
    if !actual.starts_with(stem)
        || &actual[stem.len()..] != suffix
        || (require_boundary && !has_japanese_recognized_left_boundary(source, start_byte))
    {
        return;
    }
    candidates.push(Candidate {
        end_byte,
        priority,
        identity,
        delivery,
    });
}

fn push_japanese_function_candidate(
    candidates: &mut Vec<Candidate>,
    source: &str,
    start_byte: usize,
    require_boundary: bool,
    surface: &str,
    identity: String,
) {
    let end_byte = start_byte + surface.len();
    if source.get(start_byte..end_byte) != Some(surface)
        || (require_boundary && !has_japanese_recognized_left_candidate(source, start_byte))
    {
        return;
    }
    candidates.push(Candidate {
        end_byte,
        priority: PRIORITY_FUNCTION,
        identity,
        delivery: CandidateDelivery::Token(NeutralTokenKind::FunctionWord),
    });
}

fn push_japanese_counter_candidate(
    candidates: &mut Vec<Candidate>,
    source: &str,
    start_byte: usize,
    surface: &str,
) {
    let end_byte = start_byte + surface.len();
    if source.get(start_byte..end_byte) != Some(surface)
        || !japanese_exact_number_ends_at(source, start_byte)
    {
        return;
    }
    candidates.push(Candidate {
        end_byte,
        priority: PRIORITY_FUNCTION,
        identity: format!("function:counter:{surface}"),
        delivery: CandidateDelivery::Token(NeutralTokenKind::FunctionWord),
    });
}

fn japanese_exact_number_ends_at(source: &str, end_byte: usize) -> bool {
    source[..end_byte].char_indices().any(|(start_byte, _)| {
        NATIVE_TSU_CARDINALS_JA.iter().any(|(surface, _)| {
            start_byte + surface.len() == end_byte
                && source.get(start_byte..end_byte) == Some(*surface)
        }) || japanese_kanji_cardinal_at(source, start_byte)
            .is_some_and(|(candidate_end, _)| candidate_end == end_byte)
            || (source.as_bytes()[start_byte].is_ascii_digit()
                && source.as_bytes()[start_byte..end_byte]
                    .iter()
                    .all(u8::is_ascii_digit)
                && source[start_byte..end_byte].parse::<u64>().is_ok())
    })
}

fn has_candidate_boundary(
    source: &str,
    start_byte: usize,
    end_byte: usize,
    language: ResolvedInstructionLanguage,
) -> bool {
    match language {
        ResolvedInstructionLanguage::En => {
            let left_ok = start_byte == 0
                || source[..start_byte]
                    .chars()
                    .next_back()
                    .is_none_or(|character| !character.is_ascii_alphanumeric());
            let right_ok = end_byte == source.len()
                || source[end_byte..]
                    .chars()
                    .next()
                    .is_none_or(|character| !character.is_ascii_alphanumeric());
            left_ok && right_ok
        }
        ResolvedInstructionLanguage::Ja => {
            end_byte == source.len()
                || source[end_byte..].chars().next().is_some_and(is_separator)
                || !candidates_at(source, end_byte, language, false).is_empty()
        }
    }
}

fn select_candidate(candidates: Vec<Candidate>) -> Option<Selection> {
    let longest_end = candidates
        .iter()
        .map(|candidate| candidate.end_byte)
        .max()?;
    let highest_priority = candidates
        .iter()
        .filter(|candidate| candidate.end_byte == longest_end)
        .map(|candidate| candidate.priority)
        .max()
        .expect("longest candidate exists");
    let finalists = candidates
        .into_iter()
        .filter(|candidate| {
            candidate.end_byte == longest_end && candidate.priority == highest_priority
        })
        .collect::<Vec<_>>();
    let identities = finalists
        .iter()
        .map(|candidate| candidate.identity.as_str())
        .collect::<HashSet<_>>();
    if identities.len() > 1 {
        return Some(Selection::Conflict {
            end_byte: longest_end,
        });
    }

    match finalists
        .into_iter()
        .next()
        .expect("selected candidate exists")
        .delivery
    {
        CandidateDelivery::Token(kind) => Some(Selection::Token {
            end_byte: longest_end,
            kind,
        }),
        CandidateDelivery::Hole => Some(Selection::Hole {
            end_byte: longest_end,
        }),
    }
}

fn diagnostic(
    source: &str,
    start_byte: usize,
    end_byte: usize,
    kind: NeutralDiagnosticKind,
    recognized: bool,
) -> NeutralDiagnostic {
    NeutralDiagnostic {
        span: SourceSpan {
            start_byte,
            end_byte,
        },
        surface: source[start_byte..end_byte].to_owned(),
        kind,
        recognized,
    }
}

fn japanese_kanji_cardinal_at(source: &str, start_byte: usize) -> Option<(usize, u64)> {
    let mut end_byte = start_byte;
    for (offset, character) in source[start_byte..].char_indices() {
        if japanese_digit(character).is_none()
            && japanese_small_unit(character).is_none()
            && japanese_large_unit(character).is_none()
        {
            break;
        }
        end_byte = start_byte + offset + character.len_utf8();
    }
    if end_byte == start_byte {
        return None;
    }
    let value = parse_japanese_kanji_cardinal(&source[start_byte..end_byte])?;
    if source[end_byte..].starts_with('つ') {
        if value == 0 {
            return None;
        }
        end_byte += 'つ'.len_utf8();
    }
    Some((end_byte, value))
}

fn parse_japanese_kanji_cardinal(surface: &str) -> Option<u64> {
    if matches!(surface, "零" | "〇") {
        return Some(0);
    }

    let mut total = 0_u64;
    let mut section = 0_u64;
    let mut pending_digit = None;
    let mut last_small_unit = u64::MAX;
    let mut last_large_unit = u64::MAX;

    for character in surface.chars() {
        if let Some(digit) = japanese_digit(character) {
            if digit == 0 || pending_digit.replace(digit).is_some() {
                return None;
            }
            continue;
        }
        if let Some(unit) = japanese_small_unit(character) {
            if unit >= last_small_unit {
                return None;
            }
            let factor = pending_digit.take().unwrap_or(1);
            section = section.checked_add(factor.checked_mul(unit)?)?;
            last_small_unit = unit;
            continue;
        }
        let unit = japanese_large_unit(character)?;
        if unit >= last_large_unit {
            return None;
        }
        section = section.checked_add(pending_digit.take().unwrap_or(0))?;
        let factor = if section == 0 { 1 } else { section };
        total = total.checked_add(factor.checked_mul(unit)?)?;
        section = 0;
        last_small_unit = u64::MAX;
        last_large_unit = unit;
    }

    section = section.checked_add(pending_digit.unwrap_or(0))?;
    let value = total.checked_add(section)?;
    (value > 0).then_some(value)
}

fn japanese_digit(character: char) -> Option<u64> {
    match character {
        '零' | '〇' => Some(0),
        '一' => Some(1),
        '二' => Some(2),
        '三' => Some(3),
        '四' => Some(4),
        '五' => Some(5),
        '六' => Some(6),
        '七' => Some(7),
        '八' => Some(8),
        '九' => Some(9),
        _ => None,
    }
}

fn japanese_small_unit(character: char) -> Option<u64> {
    match character {
        '十' => Some(10),
        '百' => Some(100),
        '千' => Some(1_000),
        _ => None,
    }
}

fn japanese_large_unit(character: char) -> Option<u64> {
    match character {
        '万' => Some(10_000),
        '億' => Some(100_000_000),
        '兆' => Some(1_000_000_000_000),
        '京' => Some(10_000_000_000_000_000),
        _ => None,
    }
}

fn english_cardinal_at(source: &str, start_byte: usize) -> Option<(usize, u64)> {
    let bytes = source.as_bytes();
    if !bytes.get(start_byte).is_some_and(u8::is_ascii_alphabetic) {
        return None;
    }

    let mut cursor = start_byte;
    let mut words = Vec::new();
    let mut best = None;
    for _ in 0..5 {
        let word_start = cursor;
        while bytes.get(cursor).is_some_and(u8::is_ascii_alphabetic) {
            cursor += 1;
        }
        if cursor == word_start {
            break;
        }
        words.push(source[word_start..cursor].to_ascii_lowercase());
        if let Some(value) = parse_english_cardinal(&words) {
            let hyphen_continues_word = bytes.get(cursor) == Some(&b'-')
                && bytes.get(cursor + 1).is_some_and(u8::is_ascii_alphabetic);
            if !hyphen_continues_word {
                best = Some((cursor, value));
            }
        }

        let Some(next_word) = english_number_separator_end(source, cursor) else {
            break;
        };
        cursor = next_word;
    }
    best
}

fn english_number_separator_end(source: &str, start_byte: usize) -> Option<usize> {
    let bytes = source.as_bytes();
    let mut cursor = start_byte;
    match bytes.get(cursor) {
        Some(b'-') => cursor += 1,
        Some(b' ') => {
            while bytes.get(cursor) == Some(&b' ') {
                cursor += 1;
            }
        }
        _ => return None,
    }
    bytes
        .get(cursor)
        .is_some_and(u8::is_ascii_alphabetic)
        .then_some(cursor)
}

fn parse_english_cardinal(words: &[String]) -> Option<u64> {
    if let Some(value) = english_under_hundred(words) {
        return Some(value);
    }
    let multiplier = english_one_to_nine(words.first()?)?;
    if words.get(1).map(String::as_str) != Some("hundred") {
        return None;
    }
    let hundreds = multiplier.checked_mul(100)?;
    match words.len() {
        2 => Some(hundreds),
        3 | 4 if words.get(2).map(String::as_str) != Some("and") => {
            hundreds.checked_add(english_under_hundred(&words[2..])?)
        }
        4 | 5 if words.get(2).map(String::as_str) == Some("and") => {
            hundreds.checked_add(english_under_hundred(&words[3..])?)
        }
        _ => None,
    }
}

fn english_under_hundred(words: &[String]) -> Option<u64> {
    match words {
        [single] => english_zero_to_nineteen(single).or_else(|| english_tens(single)),
        [tens, ones] => english_tens(tens)?.checked_add(english_one_to_nine(ones)?),
        _ => None,
    }
}

fn english_zero_to_nineteen(word: &str) -> Option<u64> {
    match word {
        "zero" => Some(0),
        "one" => Some(1),
        "two" => Some(2),
        "three" => Some(3),
        "four" => Some(4),
        "five" => Some(5),
        "six" => Some(6),
        "seven" => Some(7),
        "eight" => Some(8),
        "nine" => Some(9),
        "ten" => Some(10),
        "eleven" => Some(11),
        "twelve" => Some(12),
        "thirteen" => Some(13),
        "fourteen" => Some(14),
        "fifteen" => Some(15),
        "sixteen" => Some(16),
        "seventeen" => Some(17),
        "eighteen" => Some(18),
        "nineteen" => Some(19),
        _ => None,
    }
}

fn english_one_to_nine(word: &str) -> Option<u64> {
    english_zero_to_nineteen(word).filter(|value| (1..=9).contains(value))
}

fn english_tens(word: &str) -> Option<u64> {
    match word {
        "twenty" => Some(20),
        "thirty" => Some(30),
        "forty" => Some(40),
        "fifty" => Some(50),
        "sixty" => Some(60),
        "seventy" => Some(70),
        "eighty" => Some(80),
        "ninety" => Some(90),
        _ => None,
    }
}

fn unsupported_numeric_end(source: &str, start_byte: usize) -> Option<usize> {
    let bytes = source.as_bytes();
    let mut cursor = start_byte;
    if matches!(bytes[cursor], b'+' | b'-') {
        cursor += 1;
        if cursor == bytes.len() || !bytes[cursor].is_ascii_digit() {
            return None;
        }
    } else if !bytes[cursor].is_ascii_digit() {
        return None;
    }

    while cursor < bytes.len() && bytes[cursor].is_ascii_digit() {
        cursor += 1;
    }
    if start_byte != cursor && matches!(bytes[start_byte], b'+' | b'-') {
        return Some(cursor);
    }
    if cursor < bytes.len() && matches!(bytes[cursor], b'.' | b'-') {
        let separator = cursor;
        cursor += 1;
        let digit_start = cursor;
        while cursor < bytes.len() && bytes[cursor].is_ascii_digit() {
            cursor += 1;
        }
        if cursor > digit_start {
            return Some(cursor);
        }
        cursor = separator;
    }
    let _ = cursor;
    None
}

fn qualified_macro_end(source: &str, start_byte: usize) -> Option<usize> {
    let mut end_byte = start_byte;
    for (offset, character) in source[start_byte..].char_indices() {
        if is_macro_segment_character(character) || character == '.' {
            end_byte = start_byte + offset + character.len_utf8();
        } else {
            break;
        }
    }
    if end_byte == start_byte {
        return None;
    }
    let candidate = &source[start_byte..end_byte];
    is_visible_qualified_name(candidate).then_some(end_byte)
}

fn is_visible_qualified_name(candidate: &str) -> bool {
    let Some((namespace, heading)) = candidate.split_once('.') else {
        return false;
    };
    !namespace.is_empty()
        && namespace
            .chars()
            .next()
            .is_some_and(|character| character.is_ascii_alphabetic())
        && namespace.chars().all(is_macro_namespace_character)
        && heading
            .split('.')
            .all(|segment| !segment.is_empty() && segment.chars().all(is_macro_segment_character))
}

fn is_macro_namespace_character(character: char) -> bool {
    character.is_ascii_alphanumeric() || matches!(character, '_' | '-')
}

fn is_macro_segment_character(character: char) -> bool {
    character.is_alphanumeric() || matches!(character, '_' | '-')
}

fn unknown_end(
    document: &NormalizedDdlDocument,
    start_byte: usize,
    language: ResolvedInstructionLanguage,
) -> usize {
    let source = document.source();
    let first = source[start_byte..]
        .chars()
        .next()
        .expect("unknown starts inside source");
    let mut end_byte = start_byte + first.len_utf8();
    while end_byte < source.len() {
        let character = source[end_byte..]
            .chars()
            .next()
            .expect("unknown resynchronization remains inside source");
        if is_separator(character) || selection_at(document, end_byte, language).is_some() {
            break;
        }
        end_byte += character.len_utf8();
    }
    end_byte
}

fn is_separator(character: char) -> bool {
    character.is_whitespace()
        || character.is_ascii_punctuation()
        || matches!(
            character,
            '、' | '。'
                | '，'
                | '．'
                | '・'
                | '：'
                | '；'
                | '！'
                | '？'
                | '（'
                | '）'
                | '［'
                | '］'
                | '「'
                | '」'
                | '『'
                | '』'
        )
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn same_span_collision_is_conflict() {
        let candidates = vec![
            Candidate {
                end_byte: 6,
                priority: PRIORITY_ASSET,
                identity: "word:iro:白".to_owned(),
                delivery: CandidateDelivery::Token(NeutralTokenKind::SaijikiWord {
                    asset_id: SAIJIKI_ASSET_ID.to_owned(),
                    category_key: "iro".to_owned(),
                    canonical_surface_ja: "白".to_owned(),
                }),
            },
            Candidate {
                end_byte: 6,
                priority: PRIORITY_ASSET,
                identity: "word:synthetic:白".to_owned(),
                delivery: CandidateDelivery::Token(NeutralTokenKind::SaijikiWord {
                    asset_id: SAIJIKI_ASSET_ID.to_owned(),
                    category_key: "synthetic".to_owned(),
                    canonical_surface_ja: "白".to_owned(),
                }),
            },
        ];

        assert_eq!(
            select_candidate(candidates),
            Some(Selection::Conflict { end_byte: 6 })
        );
    }
}
