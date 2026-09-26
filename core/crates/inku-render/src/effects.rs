//! What a mark's opacity reads besides its tool: the fade its arrangement
//! gives it, typed, and the author's effect words in its color hint.
//!
//! Arrangement expansion still writes `density=`, `fade=`, `preserve_space`
//! and `fade_level=` notes into each copy's `color_hint`, because the seed of
//! a surface without its own seed hashes the whole performed instruction,
//! hint included. Those notes are seed material only: marks read the fade
//! from `MarkEffects`, never from the hint text.

use crate::types::Fade;

/// The way a group's opacity falls off across its members.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum FadeKind {
    /// From the first member to the last.
    Directional,
    /// From the group's center outward.
    Outward,
}

impl FadeKind {
    /// The kind an arrangement's `fade` asks for, if any.
    #[must_use]
    pub const fn of(fade: Fade) -> Option<Self> {
        match fade {
            Fade::None => None,
            Fade::Directional => Some(Self::Directional),
            Fade::Outward => Some(Self::Outward),
        }
    }

    /// Stroke opacity ceiling and fill opacity of a member at `level`, or of
    /// a member its group could not rank.
    fn opacity(self, level: Option<f64>) -> (f64, f64) {
        let (unranked_stroke, unranked_fill, fill_ratio) = match self {
            Self::Directional => (0.48, 0.30, 0.625),
            Self::Outward => (0.40, 0.22, 0.55),
        };
        level.map_or((unranked_stroke, unranked_fill), |level| {
            (level, (level * fill_ratio * 10_000.0).round() / 10_000.0)
        })
    }
}

/// A performed member's fade within its group.
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct FadeEffect {
    pub kind: FadeKind,
    /// The member's opacity ceiling from `group::fade_levels`, at the four
    /// decimals its seed note records. `None` when the group could not rank
    /// its members (fewer than two, or all equally far out); the kind's fixed
    /// ceiling applies then.
    pub level: Option<f64>,
}

/// What a performed mark inherits from the arrangement that made it.
#[derive(Clone, Copy, Debug, Default, PartialEq)]
pub struct MarkEffects {
    pub fade: Option<FadeEffect>,
}

/// An atmosphere an author's color hint may name.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum Atmosphere {
    Haze,
    SoftLight,
    Scent,
    Buds,
    FiveSenses,
}

impl Atmosphere {
    /// Stroke opacity ceiling and fill opacity.
    const fn opacity(self) -> (f64, f64) {
        match self {
            Self::Haze => (0.26, 0.12),
            Self::SoftLight => (0.30, 0.14),
            Self::Scent => (0.38, 0.20),
            Self::Buds => (0.72, 0.58),
            Self::FiveSenses => (0.44, 0.18),
        }
    }
}

#[derive(Clone, Copy)]
enum HintWord {
    Atmosphere(Atmosphere),
    Fade(FadeKind),
    Reflection,
}

/// The effect words an author's color hint may carry, in the order their
/// effects take precedence and `render_effect_hint` keeps them.
const HINT_WORDS: [(HintWord, &[&str]); 8] = [
    (
        HintWord::Atmosphere(Atmosphere::Haze),
        &[
            "membrane",
            "haze",
            "fog",
            "mist",
            "atmosphere",
            "膜",
            "霞",
            "霧",
            "靄",
        ],
    ),
    (
        HintWord::Atmosphere(Atmosphere::SoftLight),
        &["soft light", "柔らかな光", "陽光", "日差し"],
    ),
    (
        HintWord::Atmosphere(Atmosphere::Scent),
        &["scent", "fragrance", "香り", "匂"],
    ),
    (
        HintWord::Atmosphere(Atmosphere::Buds),
        &["waiting buds", "開花を待つ蕾", "蕾", "つぼみ"],
    ),
    (
        HintWord::Atmosphere(Atmosphere::FiveSenses),
        &["five-sense", "五感"],
    ),
    (
        HintWord::Fade(FadeKind::Directional),
        &["fade directional", "fade=directional"],
    ),
    (
        HintWord::Fade(FadeKind::Outward),
        &["fade outward", "fade=outward"],
    ),
    (HintWord::Reflection, &["reflection", "反射", "映り"]),
];

/// Stroke opacity ceiling of a reflection.
const REFLECTION_OPACITY: f64 = 0.52;

/// The effects an author's color hint names.
#[derive(Clone, Copy, Debug, Default, PartialEq)]
pub(crate) struct HintWords {
    /// The first atmosphere `HINT_WORDS` lists among the hint's words.
    atmosphere: Option<Atmosphere>,
    /// A fade word, directional before outward. Older Scores wrote the fade
    /// into the hint themselves.
    fade: Option<FadeKind>,
    reflection: bool,
}

impl HintWords {
    /// Match the words in the lowercased hint as written. The color-cycle
    /// filter, `render_effect_hint`, matches a normalized hint instead, so a
    /// cycled "soft-light" reads as soft light and an uncycled one does not.
    pub(crate) fn read(hint: Option<&str>) -> Self {
        let hint = hint.unwrap_or_default().to_lowercase();
        let mut words = Self::default();
        for (word, tokens) in HINT_WORDS {
            if !tokens.iter().any(|token| hint.contains(token)) {
                continue;
            }
            match word {
                HintWord::Atmosphere(atmosphere) => {
                    words.atmosphere.get_or_insert(atmosphere);
                }
                HintWord::Fade(kind) => {
                    words.fade.get_or_insert(kind);
                }
                HintWord::Reflection => words.reflection = true,
            }
        }
        words
    }
}

/// Cap a tool's stroke opacity by the mark's effects, and give a filled mark
/// the fill opacity its effect sets.
///
/// An atmosphere word overrides any fade. The arrangement's fade overrides a
/// fade word in the hint, whose level the hint cannot set. A reflection caps
/// the stroke on top of either.
pub(crate) fn effect_opacity(
    words: HintWords,
    effects: MarkEffects,
    tool_stroke_opacity: f64,
    filled: bool,
) -> (f64, Option<f64>) {
    let fade = effects
        .fade
        .or_else(|| words.fade.map(|kind| FadeEffect { kind, level: None }));
    let capped = match (words.atmosphere, fade) {
        (Some(atmosphere), _) => Some(atmosphere.opacity()),
        (None, Some(fade)) => Some(fade.kind.opacity(fade.level)),
        (None, None) => None,
    };
    let (mut stroke_opacity, fill_opacity) =
        capped.map_or((tool_stroke_opacity, None), |(ceiling, fill_opacity)| {
            (
                tool_stroke_opacity.min(ceiling),
                filled.then_some(fill_opacity),
            )
        });
    if words.reflection {
        stroke_opacity = stroke_opacity.min(REFLECTION_OPACITY);
    }
    (stroke_opacity, fill_opacity)
}

/// Keep only a hint's effect words, as a color cycle does: the cycle's color
/// replaces the hint's hues, and its effects stay. The words are matched in
/// the normalized hint and kept in `HINT_WORDS` order. Normalizing turns
/// hyphens into spaces, so a cycled hint loses "five-sense" and keeps 五感.
#[must_use]
pub fn render_effect_hint(color_hint: Option<&str>) -> Option<String> {
    let normalized = crate::palette::normalized_label(color_hint.filter(|hint| !hint.is_empty())?);
    let kept = HINT_WORDS
        .iter()
        .flat_map(|(_, tokens)| tokens.iter().copied())
        .filter(|token| normalized.contains(token))
        .collect::<Vec<_>>();
    (!kept.is_empty()).then(|| kept.join("; "))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn an_author_hint_cannot_set_the_fade_level() {
        // The hint once carried the level for marks to parse back, so an
        // author's "fade_level=0" beside a fade word hid the mark entirely.
        let words = HintWords::read(Some("fade directional; fade_level=0"));
        assert_eq!(
            effect_opacity(words, MarkEffects::default(), 0.9, true),
            (0.48, Some(0.30))
        );
    }
}
