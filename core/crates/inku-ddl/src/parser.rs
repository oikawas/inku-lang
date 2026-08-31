//! Meaning-neutral lexeme recognition over a source-preserving DDL document.

use std::collections::HashSet;

use crate::{NormalizedDdlDocument, ResolvedInstructionLanguage, SAIJIKI_ASSET_ID, saijiki_asset};

/// Stable identity for the runtime-disconnected neutral parser foundation.
pub const NEUTRAL_LEXEME_PARSER_SCHEMA_ID: &str = "inku.neutral-lexeme-parser.v1";

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

/// The lexical identity of a recognized item, before typed composition.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum NeutralTokenKind {
    SaijikiWord {
        asset_id: String,
        category_key: String,
        canonical_surface_ja: String,
    },
    SaijikiRelation {
        asset_id: String,
        relation_type: String,
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
const FUNCTION_WORDS_EN: &[&str] = &[
    "a", "an", "the", "with", "in", "at", "on", "to", "of", "and",
];
const EXACT_NUMBERS_JA: &[(&str, u64)] = &[("八つ", 8), ("十二", 12)];
const EXACT_NUMBERS_EN: &[(&str, u64)] = &[("eight", 8), ("twelve", 12)];
const QUALITATIVE_QUANTITIES_JA: &[&str] =
    &["少し", "数個", "いくつか", "たくさん", "多数", "無数"];
const QUALITATIVE_QUANTITIES_EN: &[&str] = &["a few", "several", "many", "numerous", "countless"];

const PRIORITY_FUNCTION: u8 = 1;
const PRIORITY_NUMBER: u8 = 2;
const PRIORITY_ASSET: u8 = 3;

/// Recognize source lexemes without rewriting source or completing their meaning.
pub fn parse_neutral_lexemes(document: &NormalizedDdlDocument) -> NeutralParseResult {
    let source = document.source();
    let language = document.language();
    let mut tokens = Vec::new();
    let mut diagnostics = Vec::new();
    let mut recognized_delivery_count = 0;
    let mut cursor = 0;

    while cursor < source.len() {
        if let Some(end_byte) = unsupported_numeric_end(source, cursor) {
            diagnostics.push(diagnostic(
                source,
                cursor,
                end_byte,
                NeutralDiagnosticKind::Hole,
                true,
            ));
            recognized_delivery_count += 1;
            cursor = end_byte;
            continue;
        }

        if let Some(macro_match) = qualified_macro_match(document, cursor) {
            let (end_byte, kind, recognized) = match macro_match {
                QualifiedMacroMatch::Unlocked { end_byte }
                | QualifiedMacroMatch::ExactLock { end_byte, .. } => {
                    (end_byte, NeutralDiagnosticKind::Unknown, false)
                }
                QualifiedMacroMatch::AmbiguousLocks { end_byte, .. } => {
                    (end_byte, NeutralDiagnosticKind::Conflict, true)
                }
            };
            diagnostics.push(diagnostic(source, cursor, end_byte, kind, recognized));
            recognized_delivery_count += usize::from(recognized);
            cursor = end_byte;
            continue;
        }

        match select_candidate(candidates_at_with_locked_macro_boundary(
            document, cursor, language,
        )) {
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
            None => {
                let character = source[cursor..]
                    .chars()
                    .next()
                    .expect("cursor is inside source");
                if is_separator(character) {
                    cursor += character.len_utf8();
                    continue;
                }

                let end_byte = unknown_end(source, cursor);
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

    for category in &asset.categories {
        for word in &category.words {
            let surface = match language {
                ResolvedInstructionLanguage::Ja => Some(word.surface_ja.as_str()),
                ResolvedInstructionLanguage::En => word.surface_en.as_deref(),
            };
            let Some(surface) = surface else {
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
        }
    }

    for relation in &asset.relations {
        let surface = match language {
            ResolvedInstructionLanguage::Ja => relation.surface_ja.as_str(),
            ResolvedInstructionLanguage::En => relation.surface_en.as_str(),
        };
        push_surface_candidate(
            &mut candidates,
            source,
            start_byte,
            language,
            require_boundary,
            surface,
            PRIORITY_ASSET,
            format!("relation:{}", relation.relation_type),
            CandidateDelivery::Token(NeutralTokenKind::SaijikiRelation {
                asset_id: SAIJIKI_ASSET_ID.to_owned(),
                relation_type: relation.relation_type.clone(),
            }),
        );
    }

    let function_words = match language {
        ResolvedInstructionLanguage::Ja => FUNCTION_WORDS_JA,
        ResolvedInstructionLanguage::En => FUNCTION_WORDS_EN,
    };
    for surface in function_words {
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

    let exact_numbers = match language {
        ResolvedInstructionLanguage::Ja => EXACT_NUMBERS_JA,
        ResolvedInstructionLanguage::En => EXACT_NUMBERS_EN,
    };
    for (surface, value) in exact_numbers {
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

fn unknown_end(source: &str, start_byte: usize) -> usize {
    let mut end_byte = start_byte;
    for (offset, character) in source[start_byte..].char_indices() {
        if is_separator(character) {
            break;
        }
        end_byte = start_byte + offset + character.len_utf8();
    }
    if end_byte == start_byte {
        start_byte
            + source[start_byte..]
                .chars()
                .next()
                .expect("unknown starts inside source")
                .len_utf8()
    } else {
        end_byte
    }
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
