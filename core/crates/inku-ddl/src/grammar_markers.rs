//! Closed, built-in identities for grammar markers accepted by the DDL parser.

use crate::language::ResolvedInstructionLanguage;

/// Stable identity of one accepted grammar marker.
#[derive(Clone, Copy, Debug, Eq, Hash, PartialEq)]
pub enum MarkerId {
    JaRepeat,
    JaGroup,
    JaSequenceTe,
    JaWo,
    JaNi,
    JaDe,
    JaNo,
    JaWa,
    JaGa,
    JaHe,
    JaTo,
    JaBackground,
    EnGroupOf,
    EnBackground,
    EnA,
    EnAn,
    EnThe,
    EnWith,
    EnIn,
    EnAt,
    EnOn,
    EnTo,
    EnOf,
    EnAnd,
    EnRepeating,
}

/// Existing consumer roles associated with one marker identity.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
#[repr(u16)]
pub enum MarkerCapability {
    Attachment = 1 << 0,
    Determiner = 1 << 1,
    Coordination = 1 << 2,
    Background = 1 << 3,
    Group = 1 << 4,
    Sequence = 1 << 5,
    Fill = 1 << 6,
    Geometry = 1 << 7,
}

#[derive(Clone, Copy)]
struct MarkerCapabilities(u16);

impl MarkerCapabilities {
    const fn contains(self, capability: MarkerCapability) -> bool {
        self.0 & capability as u16 != 0
    }
}

const ATTACHMENT: u16 = MarkerCapability::Attachment as u16;
const DETERMINER: u16 = MarkerCapability::Determiner as u16;
const COORDINATION: u16 = MarkerCapability::Coordination as u16;
const BACKGROUND: u16 = MarkerCapability::Background as u16;
const GROUP: u16 = MarkerCapability::Group as u16;
const SEQUENCE: u16 = MarkerCapability::Sequence as u16;
const FILL: u16 = MarkerCapability::Fill as u16;
const GEOMETRY: u16 = MarkerCapability::Geometry as u16;

impl MarkerId {
    /// Return the canonical accepted source spelling for this identity.
    pub const fn surface(self) -> &'static str {
        match self {
            Self::JaRepeat => "繰り返して",
            Self::JaGroup => "組",
            Self::JaSequenceTe => "して",
            Self::JaWo => "を",
            Self::JaNi => "に",
            Self::JaDe => "で",
            Self::JaNo => "の",
            Self::JaWa => "は",
            Self::JaGa => "が",
            Self::JaHe => "へ",
            Self::JaTo => "と",
            Self::JaBackground => "背景",
            Self::EnGroupOf => "group of",
            Self::EnBackground => "background",
            Self::EnA => "a",
            Self::EnAn => "an",
            Self::EnThe => "the",
            Self::EnWith => "with",
            Self::EnIn => "in",
            Self::EnAt => "at",
            Self::EnOn => "on",
            Self::EnTo => "to",
            Self::EnOf => "of",
            Self::EnAnd => "and",
            Self::EnRepeating => "repeating",
        }
    }

    /// Return the instruction language that owns this marker identity.
    pub const fn language(self) -> ResolvedInstructionLanguage {
        match self {
            Self::JaRepeat
            | Self::JaGroup
            | Self::JaSequenceTe
            | Self::JaWo
            | Self::JaNi
            | Self::JaDe
            | Self::JaNo
            | Self::JaWa
            | Self::JaGa
            | Self::JaHe
            | Self::JaTo
            | Self::JaBackground => ResolvedInstructionLanguage::Ja,
            Self::EnGroupOf
            | Self::EnBackground
            | Self::EnA
            | Self::EnAn
            | Self::EnThe
            | Self::EnWith
            | Self::EnIn
            | Self::EnAt
            | Self::EnOn
            | Self::EnTo
            | Self::EnOf
            | Self::EnAnd
            | Self::EnRepeating => ResolvedInstructionLanguage::En,
        }
    }

    /// Report whether this identity participates in an existing consumer role.
    pub const fn has_capability(self, capability: MarkerCapability) -> bool {
        self.capabilities().contains(capability)
    }

    const fn capabilities(self) -> MarkerCapabilities {
        MarkerCapabilities(match self {
            Self::JaRepeat | Self::JaSequenceTe | Self::EnRepeating => SEQUENCE,
            Self::JaGroup | Self::EnGroupOf => GROUP,
            Self::JaWo => ATTACHMENT | FILL | SEQUENCE,
            Self::JaNi | Self::JaHe | Self::EnIn | Self::EnAt | Self::EnOn | Self::EnTo => {
                ATTACHMENT
            }
            Self::JaDe => ATTACHMENT | FILL,
            Self::JaNo => ATTACHMENT | GROUP | SEQUENCE | GEOMETRY,
            Self::JaWa | Self::JaGa => ATTACHMENT,
            Self::JaTo => ATTACHMENT | COORDINATION | SEQUENCE,
            Self::JaBackground | Self::EnBackground => BACKGROUND,
            Self::EnA | Self::EnAn | Self::EnThe => DETERMINER,
            Self::EnWith => ATTACHMENT | FILL | GROUP,
            Self::EnOf => ATTACHMENT | GROUP,
            Self::EnAnd => COORDINATION | SEQUENCE,
        })
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub(crate) enum MarkerMatchKind {
    JapaneseAttached,
    JapaneseDocumentHead,
    EnglishWord,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub(crate) struct GrammarMarkerDefinition {
    pub id: MarkerId,
    pub match_kind: MarkerMatchKind,
    pub priority: u8,
}

pub(crate) const GRAMMAR_MARKER_PRIORITY: u8 = 1;

const GRAMMAR_MARKERS: &[GrammarMarkerDefinition] = &[
    GrammarMarkerDefinition { id: MarkerId::JaRepeat, match_kind: MarkerMatchKind::JapaneseAttached, priority: GRAMMAR_MARKER_PRIORITY },
    GrammarMarkerDefinition { id: MarkerId::JaGroup, match_kind: MarkerMatchKind::JapaneseAttached, priority: GRAMMAR_MARKER_PRIORITY },
    GrammarMarkerDefinition { id: MarkerId::JaSequenceTe, match_kind: MarkerMatchKind::JapaneseAttached, priority: GRAMMAR_MARKER_PRIORITY },
    GrammarMarkerDefinition { id: MarkerId::JaWo, match_kind: MarkerMatchKind::JapaneseAttached, priority: GRAMMAR_MARKER_PRIORITY },
    GrammarMarkerDefinition { id: MarkerId::JaNi, match_kind: MarkerMatchKind::JapaneseAttached, priority: GRAMMAR_MARKER_PRIORITY },
    GrammarMarkerDefinition { id: MarkerId::JaDe, match_kind: MarkerMatchKind::JapaneseAttached, priority: GRAMMAR_MARKER_PRIORITY },
    GrammarMarkerDefinition { id: MarkerId::JaNo, match_kind: MarkerMatchKind::JapaneseAttached, priority: GRAMMAR_MARKER_PRIORITY },
    GrammarMarkerDefinition { id: MarkerId::JaWa, match_kind: MarkerMatchKind::JapaneseAttached, priority: GRAMMAR_MARKER_PRIORITY },
    GrammarMarkerDefinition { id: MarkerId::JaGa, match_kind: MarkerMatchKind::JapaneseAttached, priority: GRAMMAR_MARKER_PRIORITY },
    GrammarMarkerDefinition { id: MarkerId::JaHe, match_kind: MarkerMatchKind::JapaneseAttached, priority: GRAMMAR_MARKER_PRIORITY },
    GrammarMarkerDefinition { id: MarkerId::JaTo, match_kind: MarkerMatchKind::JapaneseAttached, priority: GRAMMAR_MARKER_PRIORITY },
    GrammarMarkerDefinition { id: MarkerId::JaBackground, match_kind: MarkerMatchKind::JapaneseDocumentHead, priority: GRAMMAR_MARKER_PRIORITY },
    GrammarMarkerDefinition { id: MarkerId::EnGroupOf, match_kind: MarkerMatchKind::EnglishWord, priority: GRAMMAR_MARKER_PRIORITY },
    GrammarMarkerDefinition { id: MarkerId::EnBackground, match_kind: MarkerMatchKind::EnglishWord, priority: GRAMMAR_MARKER_PRIORITY },
    GrammarMarkerDefinition { id: MarkerId::EnA, match_kind: MarkerMatchKind::EnglishWord, priority: GRAMMAR_MARKER_PRIORITY },
    GrammarMarkerDefinition { id: MarkerId::EnAn, match_kind: MarkerMatchKind::EnglishWord, priority: GRAMMAR_MARKER_PRIORITY },
    GrammarMarkerDefinition { id: MarkerId::EnThe, match_kind: MarkerMatchKind::EnglishWord, priority: GRAMMAR_MARKER_PRIORITY },
    GrammarMarkerDefinition { id: MarkerId::EnWith, match_kind: MarkerMatchKind::EnglishWord, priority: GRAMMAR_MARKER_PRIORITY },
    GrammarMarkerDefinition { id: MarkerId::EnIn, match_kind: MarkerMatchKind::EnglishWord, priority: GRAMMAR_MARKER_PRIORITY },
    GrammarMarkerDefinition { id: MarkerId::EnAt, match_kind: MarkerMatchKind::EnglishWord, priority: GRAMMAR_MARKER_PRIORITY },
    GrammarMarkerDefinition { id: MarkerId::EnOn, match_kind: MarkerMatchKind::EnglishWord, priority: GRAMMAR_MARKER_PRIORITY },
    GrammarMarkerDefinition { id: MarkerId::EnTo, match_kind: MarkerMatchKind::EnglishWord, priority: GRAMMAR_MARKER_PRIORITY },
    GrammarMarkerDefinition { id: MarkerId::EnOf, match_kind: MarkerMatchKind::EnglishWord, priority: GRAMMAR_MARKER_PRIORITY },
    GrammarMarkerDefinition { id: MarkerId::EnAnd, match_kind: MarkerMatchKind::EnglishWord, priority: GRAMMAR_MARKER_PRIORITY },
    GrammarMarkerDefinition { id: MarkerId::EnRepeating, match_kind: MarkerMatchKind::EnglishWord, priority: GRAMMAR_MARKER_PRIORITY },
];

pub(crate) fn grammar_marker_definitions(
    language: ResolvedInstructionLanguage,
) -> impl Iterator<Item = &'static GrammarMarkerDefinition> {
    GRAMMAR_MARKERS
        .iter()
        .filter(move |definition| definition.id.language() == language)
}

#[cfg(test)]
mod tests {
    use std::collections::HashSet;

    use super::*;

    #[test]
    fn registry_has_unique_language_surface_and_identity_rows() {
        assert_eq!(GRAMMAR_MARKERS.len(), 25);
        assert_eq!(
            GRAMMAR_MARKERS
                .iter()
                .map(|definition| definition.id)
                .collect::<HashSet<_>>()
                .len(),
            GRAMMAR_MARKERS.len()
        );
        assert_eq!(
            GRAMMAR_MARKERS
                .iter()
                .map(|definition| {
                    (
                        matches!(definition.id.language(), ResolvedInstructionLanguage::Ja),
                        definition.id.surface(),
                    )
                })
                .collect::<HashSet<_>>()
                .len(),
            GRAMMAR_MARKERS.len()
        );
    }
}
