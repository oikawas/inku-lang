//! Meaning-neutral lexeme recognition over a source-preserving DDL document.

use std::collections::HashSet;

use serde::Serialize;

use crate::{
    CanonicalRelationForm, CanonicalRelationIdentity, ExactDecimal, GeometryKeyword, MarkerId,
    NormalizedDdlDocument, ResolvedInstructionLanguage, SAIJIKI_ASSET_ID,
    grammar_markers::{MarkerMatchKind, grammar_marker_definitions},
    saijiki::{canonical_relation_identity, parser_candidate_surfaces},
    saijiki_asset,
};

/// Stable identity for the runtime-disconnected neutral parser foundation.
pub const NEUTRAL_LEXEME_PARSER_SCHEMA_ID: &str = "inku.neutral-lexeme-parser.v12";

/// A half-open UTF-8 byte span into the source document.
#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize)]
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
    ShapeForm,
    ShapeSides,
    Thinness,
    RelativeScale,
}

impl CoreModifierDimension {
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::ShapeForm => "shape_form",
            Self::ShapeSides => "shape_sides",
            Self::Thinness => "thinness",
            Self::RelativeScale => "relative_scale",
        }
    }
}

/// Closed core modifier value independent of localized source spelling.
#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize)]
#[serde(tag = "kind", content = "value", rename_all = "snake_case")]
pub enum CoreModifierValue {
    Regular,
    Sides(u64),
    Fine,
    ExtraFine,
    SlightlySmall,
    Small,
    VerySmall,
    Normal,
    SlightlyLarge,
    Large,
    VeryLarge,
}

impl CoreModifierValue {
    pub const fn dimension(self) -> CoreModifierDimension {
        match self {
            Self::Regular => CoreModifierDimension::ShapeForm,
            Self::Sides(_) => CoreModifierDimension::ShapeSides,
            Self::Fine | Self::ExtraFine => CoreModifierDimension::Thinness,
            _ => CoreModifierDimension::RelativeScale,
        }
    }

    pub fn from_semantic_ref(category: &str, id: &str) -> Option<Self> {
        let value = match id {
            "regular" => Self::Regular,
            "fine" => Self::Fine,
            "extra_fine" => Self::ExtraFine,
            "slightly_small" => Self::SlightlySmall,
            "small" => Self::Small,
            "very_small" => Self::VerySmall,
            "normal" => Self::Normal,
            "slightly_large" => Self::SlightlyLarge,
            "large" => Self::Large,
            "very_large" => Self::VeryLarge,
            _ => return None,
        };
        (value.dimension().as_str() == category).then_some(value)
    }

    pub const fn as_str(self) -> &'static str {
        match self {
            Self::Regular => "regular",
            Self::Sides(_) => "sides",
            Self::Fine => "fine",
            Self::ExtraFine => "extra_fine",
            Self::SlightlySmall => "slightly_small",
            Self::Small => "small",
            Self::VerySmall => "very_small",
            Self::Normal => "normal",
            Self::SlightlyLarge => "slightly_large",
            Self::Large => "large",
            Self::VeryLarge => "very_large",
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
    ConstrainedShape {
        canonical_surface_ja: String,
        constraint: crate::ShapeConstraint,
    },
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
    GrammarMarker(MarkerId),
    FunctionWord,
    GeometryKeyword {
        keyword: GeometryKeyword,
    },
    ExactNumber {
        value: u64,
    },
    ExactDecimal {
        value: ExactDecimal,
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

// V1 closed Japanese morphology classes. These are grammatical classes over accepted
// canonical rows, not aliases or independent semantic vocabulary.
const JAPANESE_COLOR_I_ADJECTIVE_STEMS_V1: &[&str] = &["白", "黒", "青", "赤"];
const JAPANESE_COUNTERS_V1: &[&str] = &["本", "個", "枚"];

pub(crate) fn is_japanese_counter_surface(surface: &str) -> bool {
    JAPANESE_COUNTERS_V1.contains(&surface) || surface == "つ"
}
const GROUP_LAYOUT_FUNCTION_WORDS_JA: &[&str] = &["重ねて", "並べて"];
const GROUP_LAYOUT_FUNCTION_WORDS_EN: &[&str] = &["overlapping", "side by side"];
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
const THINNESS_SURFACES_JA: &[(&str, CoreModifierValue)] = &[
    ("ごく細い", CoreModifierValue::ExtraFine),
    ("細い", CoreModifierValue::Fine),
];
const THINNESS_SURFACES_EN: &[(&str, CoreModifierValue)] = &[
    ("extra-fine", CoreModifierValue::ExtraFine),
    ("thin", CoreModifierValue::Fine),
];
const RELATIVE_SCALE_SURFACES_JA: &[(&str, CoreModifierValue)] = &[
    ("とても小さな", CoreModifierValue::VerySmall),
    ("とても小さい", CoreModifierValue::VerySmall),
    ("普通の大きさ", CoreModifierValue::Normal),
    ("とても大きな", CoreModifierValue::VeryLarge),
    ("とても大きい", CoreModifierValue::VeryLarge),
    ("小さめ", CoreModifierValue::SlightlySmall),
    ("小さな", CoreModifierValue::Small),
    ("小さい", CoreModifierValue::Small),
    ("大きめ", CoreModifierValue::SlightlyLarge),
    ("大きな", CoreModifierValue::Large),
    ("大きい", CoreModifierValue::Large),
];
const RELATIVE_SCALE_SURFACES_EN: &[(&str, CoreModifierValue)] = &[
    ("slightly small", CoreModifierValue::SlightlySmall),
    ("very small", CoreModifierValue::VerySmall),
    ("normal-sized", CoreModifierValue::Normal),
    ("slightly large", CoreModifierValue::SlightlyLarge),
    ("very large", CoreModifierValue::VeryLarge),
    ("small", CoreModifierValue::Small),
    ("large", CoreModifierValue::Large),
];

/// A read-only projection of the existing non-Saijiki modifier forms.
/// Recognition still requires the parser's original boundary and head context.
pub struct CoreModifierSurfaceForms {
    pub regular: &'static str,
    pub sides_prefix: &'static str,
    pub thinness: &'static [(&'static str, CoreModifierValue)],
    pub relative_scale: &'static [(&'static str, CoreModifierValue)],
}

pub fn core_modifier_surface_forms(
    language: ResolvedInstructionLanguage,
) -> CoreModifierSurfaceForms {
    match language {
        ResolvedInstructionLanguage::Ja => CoreModifierSurfaceForms {
            regular: "正形",
            sides_prefix: "辺数",
            thinness: THINNESS_SURFACES_JA,
            relative_scale: RELATIVE_SCALE_SURFACES_JA,
        },
        ResolvedInstructionLanguage::En => CoreModifierSurfaceForms {
            regular: "regular",
            sides_prefix: "sides ",
            thinness: THINNESS_SURFACES_EN,
            relative_scale: RELATIVE_SCALE_SURFACES_EN,
        },
    }
}

const PRIORITY_FUNCTION: u8 = 1;
const PRIORITY_NUMBER: u8 = 2;
const PRIORITY_ASSET: u8 = 3;
const PRIORITY_CORE_MODIFIER: u8 = 3;
const PRIORITY_RELATIVE_SCALE: u8 = 4;

pub(crate) fn is_reserved_english_non_asset_surface(surface: &str) -> bool {
    THINNESS_SURFACES_EN
        .iter()
        .map(|(surface, _)| *surface)
        .chain(["slightly", "very", "normal-sized", "small"])
        .chain(
            grammar_marker_definitions(ResolvedInstructionLanguage::En)
                .map(|definition| definition.id.surface()),
        )
        .chain(QUALITATIVE_QUANTITIES_EN.iter().copied())
        .any(|reserved| reserved.eq_ignore_ascii_case(surface))
        || (!surface.is_empty() && surface.bytes().all(|byte| byte.is_ascii_digit()))
        || english_cardinal_at(surface, 0).is_some_and(|(end_byte, _)| end_byte == surface.len())
}

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
    if let Some((end_byte, keyword)) = geometry_keyword_at(source, start_byte, language) {
        return Some(Selection::Token {
            end_byte,
            kind: NeutralTokenKind::GeometryKeyword { keyword },
        });
    }
    if let Some(end_byte) = exact_decimal_end(source, start_byte, language) {
        return Some(match ExactDecimal::parse(&source[start_byte..end_byte]) {
            Ok(value) => Selection::Token {
                end_byte,
                kind: NeutralTokenKind::ExactDecimal { value },
            },
            Err(_) => Selection::Hole { end_byte },
        });
    }
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
    let candidates = candidates_at_with_locked_macro_boundary(document, start_byte, language);
    select_candidate(resolve_declared_point_homograph(
        document, start_byte, language, candidates,
    ))
}

fn resolve_declared_point_homograph(
    document: &NormalizedDdlDocument,
    start_byte: usize,
    language: ResolvedInstructionLanguage,
    candidates: Vec<Candidate>,
) -> Vec<Candidate> {
    if language != ResolvedInstructionLanguage::Ja
        || document.source()[start_byte..].starts_with("点描")
    {
        return candidates;
    }
    let has_point_head = candidates
        .iter()
        .any(|candidate| candidate.identity == "word:katachi:点");
    let has_stipple = candidates
        .iter()
        .any(|candidate| candidate.identity == "word:omote:点描");
    if !has_point_head || !has_stipple {
        return candidates;
    }

    let source = document.source();
    let end_byte = start_byte + '点'.len_utf8();
    let prefix = source[..start_byte].trim_end();
    let explicit_surface_predicate = prefix.ends_with("面:") || prefix.ends_with("面：");
    let suffix = source[end_byte..].trim_start();
    let modifier_of_other_shape = suffix.strip_prefix('の').is_some_and(|after_particle| {
        let after_particle = after_particle.trim_start();
        saijiki_asset()
            .categories
            .iter()
            .find(|category| category.key == "katachi")
            .is_some_and(|category| {
                category
                    .words
                    .iter()
                    .any(|word| after_particle.starts_with(&word.surface_ja))
            })
    });
    let selected = if explicit_surface_predicate || modifier_of_other_shape {
        "word:omote:点描"
    } else {
        "word:katachi:点"
    };
    candidates
        .into_iter()
        .filter(|candidate| {
            candidate.identity != "word:katachi:点" && candidate.identity != "word:omote:点描"
                || candidate.identity == selected
        })
        .collect()
}

fn candidates_at_with_locked_macro_boundary(
    document: &NormalizedDdlDocument,
    start_byte: usize,
    language: ResolvedInstructionLanguage,
) -> Vec<Candidate> {
    let source = document.source();
    let mut candidates = candidates_at(source, start_byte, language, true);
    // A sidecar-locked Macro is also a recognized left boundary for Japanese
    // particles. The ordinary asset-only boundary scan cannot see that head.
    let left_end = source[..start_byte].trim_end_matches(is_separator).len();
    let preceded_by_locked_macro = language == ResolvedInstructionLanguage::Ja
        && document.macro_locks().iter().any(|macro_lock| {
            macro_lock.visible_names().any(|name| {
                left_end
                    .checked_sub(name.len())
                    .filter(|left_start| source.is_char_boundary(*left_start))
                    .and_then(|left_start| qualified_macro_match(document, left_start))
                    .is_some_and(|matched| {
                        matches!(matched, QualifiedMacroMatch::ExactLock { end_byte, .. }
                            if end_byte == left_end)
                    })
            })
        });
    for candidate in candidates_at(source, start_byte, language, false) {
        let followed_by_locked_macro = matches!(
            qualified_macro_match(document, candidate.end_byte),
            Some(QualifiedMacroMatch::ExactLock { .. })
                | Some(QualifiedMacroMatch::AmbiguousLocks { .. })
        );
        let already_present = candidates.iter().any(|existing| existing == &candidate);
        if (followed_by_locked_macro || preceded_by_locked_macro) && !already_present {
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
    // A lock is invoked by its canonical name or by any of its aliases; the
    // longest visible name that starts here decides the invocation's extent.
    let matched = document
        .macro_locks()
        .iter()
        .enumerate()
        .filter_map(|(index, macro_lock)| {
            macro_lock
                .visible_names()
                .filter(|name| {
                    is_visible_qualified_name(name)
                        && source.get(start_byte..start_byte + name.len()) == Some(*name)
                })
                .map(str::len)
                .max()
                .map(|length| (index, length))
        })
        .collect::<Vec<_>>();
    let lock_indices = matched.iter().map(|(index, _)| *index).collect::<Vec<_>>();

    match matched.as_slice() {
        [] => Some(QualifiedMacroMatch::Unlocked {
            end_byte: unlocked_end,
        }),
        [(lock_index, length)] => Some(QualifiedMacroMatch::ExactLock {
            end_byte: start_byte + length,
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

    match language {
        ResolvedInstructionLanguage::Ja => {
            for surface in GROUP_LAYOUT_FUNCTION_WORDS_JA {
                push_japanese_function_candidate(
                    &mut candidates,
                    source,
                    start_byte,
                    require_boundary,
                    surface,
                    format!("function:group_layout:{surface}"),
                );
            }
        }
        ResolvedInstructionLanguage::En => {
            for surface in GROUP_LAYOUT_FUNCTION_WORDS_EN {
                push_surface_candidate(
                    &mut candidates,
                    source,
                    start_byte,
                    language,
                    require_boundary,
                    surface,
                    PRIORITY_FUNCTION,
                    format!("function:group_layout:{surface}"),
                    CandidateDelivery::Token(NeutralTokenKind::FunctionWord),
                );
            }
        }
    }

    let shape_heads = match language {
        ResolvedInstructionLanguage::Ja => crate::shape_constraint::SHAPE_HEADS_JA,
        ResolvedInstructionLanguage::En => crate::shape_constraint::SHAPE_HEADS_EN,
    };
    let modifier_forms = core_modifier_surface_forms(language);
    for surface in [modifier_forms.regular] {
        push_surface_candidate(
            &mut candidates,
            source,
            start_byte,
            language,
            require_boundary,
            surface,
            PRIORITY_CORE_MODIFIER,
            "shape_form:regular".to_owned(),
            CandidateDelivery::Token(NeutralTokenKind::CoreModifier(CoreModifierIdentity {
                dimension: CoreModifierDimension::ShapeForm,
                value: CoreModifierValue::Regular,
            })),
        );
    }
    let sides_prefix = modifier_forms.sides_prefix;
    if let Some(rest) = source[start_byte..].strip_prefix(sides_prefix) {
        let number = rest.trim_start();
        let digits = number.bytes().take_while(u8::is_ascii_digit).count();
        if digits > 0
            && let Ok(value) = number[..digits].parse::<u64>()
        {
            let surface = &source
                [start_byte..start_byte + sides_prefix.len() + rest.len() - number.len() + digits];
            push_surface_candidate(
                &mut candidates,
                source,
                start_byte,
                language,
                require_boundary,
                surface,
                PRIORITY_CORE_MODIFIER,
                format!("shape_sides:{value}"),
                CandidateDelivery::Token(NeutralTokenKind::CoreModifier(CoreModifierIdentity {
                    dimension: CoreModifierDimension::ShapeSides,
                    value: CoreModifierValue::Sides(value),
                })),
            );
        }
    }
    for (surface, base, constraint) in shape_heads {
        push_surface_candidate(
            &mut candidates,
            source,
            start_byte,
            language,
            require_boundary,
            surface,
            PRIORITY_CORE_MODIFIER,
            format!("shape_constraint:{surface}"),
            CandidateDelivery::Token(NeutralTokenKind::ConstrainedShape {
                canonical_surface_ja: (*base).to_owned(),
                constraint: *constraint,
            }),
        );
    }

    for (surface, value) in modifier_forms.thinness {
        if language == ResolvedInstructionLanguage::Ja
            && require_boundary
            && !has_japanese_recognized_left_boundary(source, start_byte)
        {
            continue;
        }
        push_surface_candidate(
            &mut candidates,
            source,
            start_byte,
            language,
            require_boundary,
            surface,
            PRIORITY_CORE_MODIFIER,
            format!("core_modifier:thinness:{}", value.as_str()),
            CandidateDelivery::Token(NeutralTokenKind::CoreModifier(CoreModifierIdentity {
                dimension: CoreModifierDimension::Thinness,
                value: *value,
            })),
        );
    }

    for (relative_scale_surface, value) in modifier_forms.relative_scale {
        let relative_scale_end = start_byte + relative_scale_surface.len();
        let surface_matches = source
            .get(start_byte..relative_scale_end)
            .is_some_and(|actual| match language {
                ResolvedInstructionLanguage::Ja => actual == *relative_scale_surface,
                ResolvedInstructionLanguage::En => {
                    actual.eq_ignore_ascii_case(relative_scale_surface)
                }
            });
        if !surface_matches
            || (language == ResolvedInstructionLanguage::Ja
                && require_boundary
                && !has_japanese_typed_left_boundary(source, start_byte))
            || !has_relative_scale_head_context(source, relative_scale_end, language)
        {
            continue;
        }
        push_surface_candidate(
            &mut candidates,
            source,
            start_byte,
            language,
            require_boundary,
            relative_scale_surface,
            PRIORITY_RELATIVE_SCALE,
            format!("core_modifier:relative_scale:{}", value.as_str()),
            CandidateDelivery::Token(NeutralTokenKind::CoreModifier(CoreModifierIdentity {
                dimension: CoreModifierDimension::RelativeScale,
                value: *value,
            })),
        );
    }

    for category in &asset.categories {
        for word in &category.words {
            let surfaces = parser_candidate_surfaces(word, language);
            for surface in &surfaces {
                push_surface_candidate(
                    &mut candidates,
                    source,
                    start_byte,
                    language,
                    require_boundary,
                    surface.as_ref(),
                    PRIORITY_ASSET,
                    format!("word:{}:{}", category.key, word.surface_ja),
                    CandidateDelivery::Token(NeutralTokenKind::SaijikiWord {
                        asset_id: SAIJIKI_ASSET_ID.to_owned(),
                        category_key: category.key.clone(),
                        canonical_surface_ja: word.surface_ja.clone(),
                    }),
                );
            }
            let Some(surface) = surfaces.first().map(|surface| surface.as_ref()) else {
                continue;
            };
            if language == ResolvedInstructionLanguage::En && category.key == "katachi" {
                // Registered primitive heads use regular English noun plurals.
                // Number agreement changes spelling, never quantity or identity.
                push_surface_candidate(
                    &mut candidates,
                    source,
                    start_byte,
                    language,
                    require_boundary,
                    &format!("{surface}s"),
                    PRIORITY_ASSET,
                    format!("word:{}:{}", category.key, word.surface_ja),
                    CandidateDelivery::Token(NeutralTokenKind::SaijikiWord {
                        asset_id: SAIJIKI_ASSET_ID.to_owned(),
                        category_key: category.key.clone(),
                        canonical_surface_ja: word.surface_ja.clone(),
                    }),
                );
            }
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

    if let Some((length, canonical_identity)) =
        crate::saijiki::connected_endpoint_phrase(&source[start_byte..])
            .or_else(|| crate::saijiki::connected_path_phrase(&source[start_byte..]))
    {
        push_surface_candidate(
            &mut candidates,
            source,
            start_byte,
            language,
            require_boundary,
            &source[start_byte..start_byte + length],
            PRIORITY_ASSET,
            format!(
                "relation:connected:target:{:?}:{:?}",
                canonical_identity.target_endpoint, canonical_identity.target_path_selection
            ),
            CandidateDelivery::Token(NeutralTokenKind::SaijikiRelation {
                asset_id: SAIJIKI_ASSET_ID.to_owned(),
                relation_type: "connected".to_owned(),
                canonical_identity,
            }),
        );
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
                .map(|mut canonical_identity| {
                    canonical_identity.target = relation.literal_targets.get(surface).copied();
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

    for definition in grammar_marker_definitions(language) {
        let candidate_identity = if definition.id == MarkerId::JaBackground {
            "document:background".to_owned()
        } else {
            format!("function:{}", definition.id.surface())
        };
        match definition.match_kind {
            MarkerMatchKind::JapaneseAttached => push_japanese_grammar_marker_candidate(
                &mut candidates,
                source,
                start_byte,
                require_boundary,
                definition.id,
                candidate_identity,
            ),
            MarkerMatchKind::JapaneseDocumentHead | MarkerMatchKind::EnglishWord => {
                push_surface_candidate(
                    &mut candidates,
                    source,
                    start_byte,
                    language,
                    require_boundary,
                    definition.id.surface(),
                    definition.priority,
                    candidate_identity,
                    CandidateDelivery::Token(NeutralTokenKind::GrammarMarker(definition.id)),
                )
            }
        }
    }
    if language == ResolvedInstructionLanguage::Ja {
        for counter in JAPANESE_COUNTERS_V1 {
            push_japanese_counter_candidate(&mut candidates, source, start_byte, counter);
        }
        push_japanese_native_tsu_counter_candidate(&mut candidates, source, start_byte);
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
    } else if language == ResolvedInstructionLanguage::Ja
        && let Some((end_byte, value)) = japanese_fullwidth_decimal_at(source, start_byte)
        && (!require_boundary || has_candidate_boundary(source, start_byte, end_byte, language))
    {
        let surface = &source[start_byte..end_byte];
        candidates.push(Candidate {
            end_byte,
            priority: PRIORITY_NUMBER,
            identity: format!("decimal:{surface}"),
            delivery: value.map_or(CandidateDelivery::Hole, |value| {
                CandidateDelivery::Token(NeutralTokenKind::ExactNumber { value })
            }),
        });
    }

    candidates
}

pub(crate) fn is_group_layout_function_word(surface: &str) -> bool {
    GROUP_LAYOUT_FUNCTION_WORDS_JA.contains(&surface)
        || GROUP_LAYOUT_FUNCTION_WORDS_EN
            .iter()
            .any(|candidate| surface.eq_ignore_ascii_case(candidate))
}

fn geometry_keyword_at(
    source: &str,
    start_byte: usize,
    language: ResolvedInstructionLanguage,
) -> Option<(usize, GeometryKeyword)> {
    let candidates: &[(&str, GeometryKeyword)] = match language {
        ResolvedInstructionLanguage::Ja => &[
            ("画面の", GeometryKeyword::Canvas),
            ("位置に", GeometryKeyword::Position),
            ("半径", GeometryKeyword::Radius),
            ("直径", GeometryKeyword::Diameter),
            ("弦長", GeometryKeyword::Chord),
            ("矢高", GeometryKeyword::Sagitta),
            ("高さ", GeometryKeyword::Height),
            ("一辺", GeometryKeyword::Side),
            ("長さ", GeometryKeyword::Length),
            ("画面", GeometryKeyword::Canvas),
            ("位置", GeometryKeyword::Position),
            ("幅", GeometryKeyword::Width),
            ("横", GeometryKeyword::AxisX),
            ("縦", GeometryKeyword::AxisY),
        ],
        ResolvedInstructionLanguage::En => &[
            ("side length", GeometryKeyword::Side),
            ("horizontal", GeometryKeyword::AxisX),
            ("vertical", GeometryKeyword::AxisY),
            ("diameter", GeometryKeyword::Diameter),
            ("sagitta", GeometryKeyword::Sagitta),
            ("position", GeometryKeyword::Position),
            ("radius", GeometryKeyword::Radius),
            ("length", GeometryKeyword::Length),
            ("height", GeometryKeyword::Height),
            ("chord", GeometryKeyword::Chord),
            ("canvas", GeometryKeyword::Canvas),
            ("width", GeometryKeyword::Width),
        ],
    };
    for (surface, keyword) in candidates {
        let end_byte = start_byte.checked_add(surface.len())?;
        let Some(actual) = source.get(start_byte..end_byte) else {
            continue;
        };
        let matches = match language {
            ResolvedInstructionLanguage::Ja => actual == *surface,
            ResolvedInstructionLanguage::En => actual.eq_ignore_ascii_case(surface),
        };
        if !matches || !geometry_keyword_left_boundary(source, start_byte, language) {
            continue;
        }
        if language == ResolvedInstructionLanguage::En
            && source[end_byte..]
                .chars()
                .next()
                .is_some_and(|character| character.is_ascii_alphanumeric())
        {
            continue;
        }
        if (*keyword == GeometryKeyword::Canvas
            && axis_x_follows_context(source, end_byte, language))
            || *keyword == GeometryKeyword::Position
            || numeric_follows_keyword(source, end_byte)
        {
            return Some((end_byte, *keyword));
        }
    }
    None
}

fn axis_x_follows_context(
    source: &str,
    end_byte: usize,
    language: ResolvedInstructionLanguage,
) -> bool {
    let remainder = source[end_byte..].trim_start_matches(is_separator);
    match language {
        ResolvedInstructionLanguage::Ja => remainder.starts_with('横'),
        ResolvedInstructionLanguage::En => remainder
            .get(.."horizontal".len())
            .is_some_and(|surface| surface.eq_ignore_ascii_case("horizontal")),
    }
}

fn geometry_keyword_left_boundary(
    source: &str,
    start_byte: usize,
    language: ResolvedInstructionLanguage,
) -> bool {
    let Some(previous) = source[..start_byte].chars().next_back() else {
        return true;
    };
    match language {
        ResolvedInstructionLanguage::En => !previous.is_ascii_alphanumeric(),
        ResolvedInstructionLanguage::Ja => {
            is_separator(previous)
                || matches!(
                    previous,
                    'を' | 'に' | 'で' | 'の' | 'は' | 'が' | 'へ' | 'と'
                )
        }
    }
}

fn numeric_follows_keyword(source: &str, end_byte: usize) -> bool {
    source[end_byte..]
        .char_indices()
        .find(|(_, character)| !character.is_whitespace())
        .and_then(|(offset, _)| source.as_bytes().get(end_byte + offset))
        .is_some_and(|byte| byte.is_ascii_digit() || matches!(byte, b'+' | b'-'))
}

fn exact_decimal_end(
    source: &str,
    start_byte: usize,
    language: ResolvedInstructionLanguage,
) -> Option<usize> {
    let bytes = source.as_bytes();
    let mut cursor = start_byte;
    let mut signed = false;
    if matches!(bytes.get(cursor), Some(b'+' | b'-')) {
        signed = true;
        cursor += 1;
    }
    let integer_start = cursor;
    while bytes.get(cursor).is_some_and(u8::is_ascii_digit) {
        cursor += 1;
    }
    if cursor == integer_start {
        return None;
    }
    let mut decimal = false;
    if bytes.get(cursor) == Some(&b'.') && bytes.get(cursor + 1).is_some_and(u8::is_ascii_digit) {
        decimal = true;
        cursor += 2;
        while bytes.get(cursor).is_some_and(u8::is_ascii_digit) {
            cursor += 1;
        }
    }
    (decimal || (signed && signed_integer_has_geometry_prefix(source, start_byte, language)))
        .then_some(cursor)
}

fn signed_integer_has_geometry_prefix(
    source: &str,
    start_byte: usize,
    language: ResolvedInstructionLanguage,
) -> bool {
    let prefix = source[..start_byte].trim_end();
    let surfaces: &[&str] = match language {
        ResolvedInstructionLanguage::Ja => &["半径", "直径", "高さ", "一辺", "幅", "横", "縦"],
        ResolvedInstructionLanguage::En => &[
            "side length",
            "horizontal",
            "vertical",
            "diameter",
            "radius",
            "height",
            "width",
        ],
    };
    surfaces.iter().any(|surface| prefix.ends_with(surface))
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

fn has_japanese_recognized_left_candidate_across_separators(
    source: &str,
    start_byte: usize,
) -> bool {
    let mut candidate_end = start_byte;
    while let Some(character) = source[..candidate_end].chars().next_back() {
        if !is_separator(character) {
            break;
        }
        candidate_end -= character.len_utf8();
    }
    candidate_end < start_byte && has_japanese_recognized_left_candidate(source, candidate_end)
}

fn has_japanese_typed_left_boundary(source: &str, start_byte: usize) -> bool {
    start_byte == 0
        || has_japanese_recognized_left_candidate(source, start_byte)
        || has_japanese_recognized_left_candidate_across_separators(source, start_byte)
}

fn has_primitive_candidate_at(
    source: &str,
    start_byte: usize,
    language: ResolvedInstructionLanguage,
) -> bool {
    start_byte < source.len()
        && candidates_at(source, start_byte, language, false)
            .iter()
            .any(|candidate| {
                matches!(
                    &candidate.delivery,
                    CandidateDelivery::Token(NeutralTokenKind::ConstrainedShape { .. })
                ) || matches!(
                    &candidate.delivery,
                    CandidateDelivery::Token(NeutralTokenKind::SaijikiWord {
                        category_key,
                        ..
                    }) if category_key == "katachi"
                )
            })
}

fn has_relative_scale_head_context(
    source: &str,
    start_byte: usize,
    language: ResolvedInstructionLanguage,
) -> bool {
    let mut cursor = start_byte;
    loop {
        while let Some(character) = source[cursor..].chars().next() {
            if !character.is_whitespace() {
                break;
            }
            cursor += character.len_utf8();
        }
        if has_primitive_candidate_at(source, cursor, language)
            || qualified_macro_end(source, cursor).is_some()
        {
            return true;
        }
        if cursor >= source.len() {
            return false;
        }
        let next = candidates_at(source, cursor, language, false)
            .into_iter()
            .filter(|candidate| match &candidate.delivery {
                CandidateDelivery::Token(
                    NeutralTokenKind::GrammarMarker(_) | NeutralTokenKind::FunctionWord,
                ) => true,
                CandidateDelivery::Token(NeutralTokenKind::CoreModifier(_)) => true,
                // A count between the scale and its head keeps the phrase, e.g.
                // `大きな 四つ の 円`.
                CandidateDelivery::Token(NeutralTokenKind::ExactNumber { .. }) => true,
                CandidateDelivery::Token(NeutralTokenKind::SaijikiWord {
                    category_key, ..
                }) => category_key != "katachi",
                _ => false,
            })
            .max_by_key(|candidate| candidate.end_byte);
        let Some(next) = next else {
            return false;
        };
        if next.end_byte <= cursor {
            return false;
        }
        cursor = next.end_byte;
    }
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
        || (require_boundary
            && !has_japanese_recognized_left_candidate(source, start_byte)
            && !has_japanese_recognized_left_candidate_across_separators(source, start_byte))
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

fn push_japanese_grammar_marker_candidate(
    candidates: &mut Vec<Candidate>,
    source: &str,
    start_byte: usize,
    require_boundary: bool,
    marker_id: MarkerId,
    identity: String,
) {
    let surface = marker_id.surface();
    let end_byte = start_byte + surface.len();
    if source.get(start_byte..end_byte) != Some(surface)
        || (marker_id == MarkerId::JaTo
            && !has_japanese_coordination_right_boundary(source, end_byte))
        || (require_boundary
            && !has_japanese_recognized_left_candidate(source, start_byte)
            && !has_japanese_recognized_left_candidate_across_separators(source, start_byte))
    {
        return;
    }
    candidates.push(Candidate {
        end_byte,
        priority: crate::grammar_markers::GRAMMAR_MARKER_PRIORITY,
        identity,
        delivery: CandidateDelivery::Token(NeutralTokenKind::GrammarMarker(marker_id)),
    });
}

fn has_japanese_coordination_right_boundary(source: &str, start_byte: usize) -> bool {
    if start_byte == source.len() {
        return true;
    }
    let Some(character) = source[start_byte..].chars().next() else {
        return true;
    };
    if is_separator(character)
        || character == 'と'
        || qualified_macro_end(source, start_byte).is_some()
    {
        return true;
    }
    !candidates_at(source, start_byte, ResolvedInstructionLanguage::Ja, false).is_empty()
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

fn push_japanese_native_tsu_counter_candidate(
    candidates: &mut Vec<Candidate>,
    source: &str,
    start_byte: usize,
) {
    let end_byte = start_byte + 'つ'.len_utf8();
    if source.get(start_byte..end_byte) != Some("つ") {
        return;
    }
    let Some(value) = japanese_exact_number_before(source, start_byte) else {
        return;
    };
    if !(1..=9).contains(&value) {
        return;
    }
    candidates.push(Candidate {
        end_byte,
        priority: PRIORITY_FUNCTION,
        identity: "function:counter:つ".to_owned(),
        delivery: CandidateDelivery::Token(NeutralTokenKind::FunctionWord),
    });
}

fn japanese_exact_number_before(source: &str, end_byte: usize) -> Option<u64> {
    source[..end_byte]
        .char_indices()
        .find_map(|(start_byte, _)| {
            NATIVE_TSU_CARDINALS_JA
                .iter()
                .find_map(|(surface, value)| {
                    (start_byte + surface.len() == end_byte
                        && source.get(start_byte..end_byte) == Some(*surface))
                    .then_some(*value)
                })
                .or_else(|| {
                    japanese_kanji_cardinal_at(source, start_byte)
                        .filter(|(candidate_end, _)| *candidate_end == end_byte)
                        .map(|(_, value)| value)
                })
                .or_else(|| {
                    let candidate = source.get(start_byte..end_byte)?;
                    (!candidate.is_empty() && candidate.bytes().all(|byte| byte.is_ascii_digit()))
                        .then(|| candidate.parse::<u64>().ok())
                        .flatten()
                })
                .or_else(|| {
                    japanese_fullwidth_decimal_at(source, start_byte)
                        .filter(|(candidate_end, _)| *candidate_end == end_byte)
                        .and_then(|(_, value)| value)
                })
        })
}

fn japanese_exact_number_ends_at(source: &str, end_byte: usize) -> bool {
    source[..end_byte].char_indices().any(|(start_byte, _)| {
        NATIVE_TSU_CARDINALS_JA.iter().any(|(surface, _)| {
            start_byte + surface.len() == end_byte
                && source.get(start_byte..end_byte) == Some(*surface)
        }) || japanese_kanji_cardinal_at(source, start_byte)
            .is_some_and(|(candidate_end, _)| candidate_end == end_byte)
            || japanese_fullwidth_decimal_at(source, start_byte)
                .is_some_and(|(candidate_end, value)| candidate_end == end_byte && value.is_some())
            || (source.as_bytes()[start_byte].is_ascii_digit()
                && source.as_bytes()[start_byte..end_byte]
                    .iter()
                    .all(u8::is_ascii_digit)
                && source[start_byte..end_byte].parse::<u64>().is_ok())
    })
}

fn japanese_fullwidth_decimal_at(source: &str, start_byte: usize) -> Option<(usize, Option<u64>)> {
    let mut end_byte = start_byte;
    let mut value = Some(0_u64);
    let mut found = false;
    for (offset, character) in source[start_byte..].char_indices() {
        let digit = match character {
            '０'..='９' => u64::from(character as u32 - '０' as u32),
            _ => break,
        };
        found = true;
        end_byte = start_byte + offset + character.len_utf8();
        value = value.and_then(|value| value.checked_mul(10)?.checked_add(digit));
    }
    found.then_some((end_byte, value))
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
    // A single sentence-final period is a clause boundary, not an empty
    // qualified-name segment. Keep the Macro's exact spelling for lock lookup.
    if source.as_bytes()[end_byte - 1] == b'.' {
        end_byte -= 1;
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

    #[test]
    fn ja_to_requires_a_recognized_right_operand() {
        let embedded_source = "黒い線にとばらして置く。";
        let embedded = parse_neutral_lexemes(
            &NormalizedDdlDocument::new(
                embedded_source,
                ResolvedInstructionLanguage::Ja,
                Vec::new(),
            )
            .unwrap(),
        );
        assert!(!embedded.tokens.iter().any(|token| {
            matches!(token.kind, NeutralTokenKind::GrammarMarker(MarkerId::JaTo))
        }));
        let unknown = embedded
            .diagnostics
            .iter()
            .find(|diagnostic| diagnostic.surface.starts_with("とばら"))
            .expect("the unsupported fragment remains one source diagnostic");
        assert!(
            embedded_source[unknown.span.start_byte..unknown.span.end_byte].starts_with("とばら")
        );

        for coordinated_source in ["黒い線と赤い円を置く。", "黒い線と 赤い円を置く。"]
        {
            let coordinated = parse_neutral_lexemes(
                &NormalizedDdlDocument::new(
                    coordinated_source,
                    ResolvedInstructionLanguage::Ja,
                    Vec::new(),
                )
                .unwrap(),
            );
            assert_eq!(
                coordinated
                    .tokens
                    .iter()
                    .filter(|token| {
                        matches!(token.kind, NeutralTokenKind::GrammarMarker(MarkerId::JaTo))
                    })
                    .count(),
                1,
                "{coordinated_source}"
            );
        }
    }
}
