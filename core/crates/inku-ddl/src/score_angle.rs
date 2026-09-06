//! Deterministic Score rotation selection for typed angle meaning.

use std::fmt::Write as _;

use sha2::{Digest, Sha256};

use crate::{ExpansionPathSegment, typed_expansion_path_bytes};

pub(crate) const SCORE_ANGLE_SELECTION_SCHEME_ID: &str = "inku.score-angle-selection.v1";

const HORIZONTAL_DEGREES: i16 = 0;
const VERTICAL_DEGREES: i16 = 90;
const DIAGONAL_DEGREES: [i16; 4] = [45, 135, 225, 315];
const RISING_DEGREES: (i16, i16) = (-37, -23);
const FALLING_DEGREES: (i16, i16) = (23, 37);
const LEFT_RISING_DEGREES: (i16, i16) = (203, 217);
const LEFT_FALLING_DEGREES: (i16, i16) = (143, 157);
const ROTATED_SECTOR_DEGREES: i16 = 45;
const ROTATED_SECTOR_MIN_OFFSET: i16 = 6;
const ROTATED_SECTOR_MAX_OFFSET: i16 = 39;
const ROTATED_SECTOR_WIDTH: u64 =
    (ROTATED_SECTOR_MAX_OFFSET - ROTATED_SECTOR_MIN_OFFSET + 1) as u64;
const ROTATED_SECTOR_COUNT: u64 = 8;

#[derive(Clone, Copy, Debug)]
pub(crate) enum ScoreAngleOccurrence<'a> {
    Direct {
        logical_ordinal: u64,
    },
    MacroEmit {
        macro_semantic_ordinal: u64,
        expansion_path: &'a [ExpansionPathSegment],
        generated_ordinal: u64,
    },
}

#[derive(Clone, Copy, Debug)]
pub(crate) struct ScoreAngleContext<'a> {
    pub(crate) composition_seed: Option<u64>,
    pub(crate) original_pre_expansion_digest: &'a str,
    pub(crate) original_expanded_meaning_digest: &'a str,
    pub(crate) occurrence: ScoreAngleOccurrence<'a>,
}

pub(crate) fn resolve_score_angle(angle_id: &str, context: ScoreAngleContext<'_>) -> Option<f64> {
    let input = angle_hash_input(angle_id, context);
    let degrees = match angle_id {
        "horizontal" => HORIZONTAL_DEGREES,
        "vertical" => VERTICAL_DEGREES,
        "diagonal" => DIAGONAL_DEGREES[uniform_index(&input, DIAGONAL_DEGREES.len() as u64)],
        "rising" => select_integer_range(&input, RISING_DEGREES),
        "falling" => select_integer_range(&input, FALLING_DEGREES),
        "left_rising" => select_integer_range(&input, LEFT_RISING_DEGREES),
        "left_falling" => select_integer_range(&input, LEFT_FALLING_DEGREES),
        "rotated" => {
            let selected =
                uniform_index(&input, ROTATED_SECTOR_WIDTH * ROTATED_SECTOR_COUNT) as u64;
            let sector = selected / ROTATED_SECTOR_WIDTH;
            let offset = selected % ROTATED_SECTOR_WIDTH;
            (sector * ROTATED_SECTOR_DEGREES as u64 + ROTATED_SECTOR_MIN_OFFSET as u64 + offset)
                as i16
        }
        _ => return None,
    };
    Some(f64::from(degrees))
}

fn select_integer_range(input: &[u8], inclusive: (i16, i16)) -> i16 {
    let width = i64::from(inclusive.1) - i64::from(inclusive.0) + 1;
    inclusive.0 + uniform_index(input, width as u64) as i16
}

fn uniform_index(input: &[u8], upper: u64) -> usize {
    debug_assert!(upper > 0);
    let acceptance_limit = u64::MAX - (u64::MAX % upper);
    for attempt in 0_u64.. {
        let mut hasher = Sha256::new();
        hasher.update(input);
        hasher.update(attempt.to_be_bytes());
        let digest = hasher.finalize();
        let candidate = u64::from_be_bytes(digest[..8].try_into().expect("SHA-256 prefix length"));
        if candidate < acceptance_limit {
            return (candidate % upper) as usize;
        }
    }
    unreachable!("finite rejection sampling eventually accepts a SHA-256 draw")
}

pub(crate) fn angle_hash_input(angle_id: &str, context: ScoreAngleContext<'_>) -> Vec<u8> {
    let mut input = Vec::new();
    push_frame(
        &mut input,
        b"scheme",
        SCORE_ANGLE_SELECTION_SCHEME_ID.as_bytes(),
    );
    push_frame(
        &mut input,
        b"original_pre_expansion_digest",
        context.original_pre_expansion_digest.as_bytes(),
    );
    push_frame(
        &mut input,
        b"original_expanded_meaning_digest",
        context.original_expanded_meaning_digest.as_bytes(),
    );
    match context.composition_seed {
        None => push_frame(&mut input, b"composition_seed", &[0]),
        Some(seed) => {
            let mut tagged = Vec::with_capacity(9);
            tagged.push(1);
            tagged.extend_from_slice(&seed.to_be_bytes());
            push_frame(&mut input, b"composition_seed", &tagged);
        }
    }
    match context.occurrence {
        ScoreAngleOccurrence::Direct { logical_ordinal } => {
            push_frame(&mut input, b"occurrence_kind", b"direct");
            push_frame(
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
            push_frame(&mut input, b"occurrence_kind", b"macro_emit");
            push_frame(
                &mut input,
                b"macro_semantic_ordinal",
                &macro_semantic_ordinal.to_be_bytes(),
            );
            push_frame(
                &mut input,
                b"expansion_path",
                &typed_expansion_path_bytes(expansion_path),
            );
            push_frame(
                &mut input,
                b"generated_ordinal",
                &generated_ordinal.to_be_bytes(),
            );
        }
    }
    push_frame(&mut input, b"angle_id", angle_id.as_bytes());
    input
}

fn push_frame(output: &mut Vec<u8>, label: &[u8], value: &[u8]) {
    output.extend_from_slice(&(label.len() as u64).to_be_bytes());
    output.extend_from_slice(label);
    output.extend_from_slice(&(value.len() as u64).to_be_bytes());
    output.extend_from_slice(value);
}

pub(crate) fn write_angle_policy_json(output: &mut String) {
    output.push_str(concat!(
        "\"angle\":{\"bounds\":{\"circle\":\"radius\",",
        "\"cloudform\":\"rotated_declared_rectangle\",",
        "\"ellipse\":\"rotated_ideal_ellipse\",\"named\":\"not_must_fit\",",
        "\"numeric\":\"must_fit\",",
        "\"physical_units\":\"short_edge_then_canvas_axes\",",
        "\"square\":\"unsupported_when_angle_present\"},",
        "\"choices\":{\"diagonal\":["
    ));
    for (index, degrees) in DIAGONAL_DEGREES.iter().enumerate() {
        if index > 0 {
            output.push(',');
        }
        write!(output, "{degrees}").expect("writing canonical angle policy to String");
    }
    write!(
        output,
        concat!(
            "],\"falling\":{{\"integer_degrees\":[{},{}]}},",
            "\"horizontal\":{},",
            "\"left_falling\":{{\"integer_degrees\":[{},{}]}},",
            "\"left_rising\":{{\"integer_degrees\":[{},{}]}},",
            "\"rising\":{{\"integer_degrees\":[{},{}]}},",
            "\"rotated\":{{\"integer_degrees_per_sector\":[{},{}],",
            "\"sector_degrees\":{}}},\"vertical\":{}}},",
            "\"seed\":{{\"fields\":[\"tagged_composition_seed\",",
            "\"original_pre_expansion_digest\",\"original_expanded_meaning_digest\",",
            "\"logical_occurrence\",\"angle_id\"],\"scheme\":\"{}\",",
            "\"selection\":\"sha256_rejection_uniform\"}}}},"
        ),
        FALLING_DEGREES.0,
        FALLING_DEGREES.1,
        HORIZONTAL_DEGREES,
        LEFT_FALLING_DEGREES.0,
        LEFT_FALLING_DEGREES.1,
        LEFT_RISING_DEGREES.0,
        LEFT_RISING_DEGREES.1,
        RISING_DEGREES.0,
        RISING_DEGREES.1,
        ROTATED_SECTOR_MIN_OFFSET,
        ROTATED_SECTOR_MAX_OFFSET,
        ROTATED_SECTOR_DEGREES,
        VERTICAL_DEGREES,
        SCORE_ANGLE_SELECTION_SCHEME_ID,
    )
    .expect("writing canonical angle policy to String");
}

#[cfg(test)]
mod tests {
    use super::*;

    fn context(seed: Option<u64>, ordinal: u64) -> ScoreAngleContext<'static> {
        ScoreAngleContext {
            composition_seed: seed,
            original_pre_expansion_digest: "pre",
            original_expanded_meaning_digest: "expanded",
            occurrence: ScoreAngleOccurrence::Direct {
                logical_ordinal: ordinal,
            },
        }
    }

    #[test]
    fn fixed_and_seeded_angle_sets_follow_the_author_ranges() {
        assert_eq!(
            resolve_score_angle("horizontal", context(None, 0)),
            Some(0.0)
        );
        assert_eq!(
            resolve_score_angle("vertical", context(Some(7), 0)),
            Some(90.0)
        );
        for seed in [None, Some(0), Some(1), Some(19), Some(u64::MAX)] {
            let diagonal = resolve_score_angle("diagonal", context(seed, 0)).unwrap();
            assert!([45.0, 135.0, 225.0, 315.0].contains(&diagonal));
            let rising = resolve_score_angle("rising", context(seed, 1)).unwrap();
            assert!((-37.0..=-23.0).contains(&rising));
            let falling = resolve_score_angle("falling", context(seed, 2)).unwrap();
            assert!((23.0..=37.0).contains(&falling));
            let left_rising = resolve_score_angle("left_rising", context(seed, 3)).unwrap();
            assert!((203.0..=217.0).contains(&left_rising));
            let left_falling = resolve_score_angle("left_falling", context(seed, 4)).unwrap();
            assert!((143.0..=157.0).contains(&left_falling));
            let rotated = resolve_score_angle("rotated", context(seed, 5)).unwrap();
            let circular_distance = (0..8)
                .map(|multiple| (rotated - f64::from(multiple * 45)).abs())
                .map(|distance| distance.min(360.0 - distance))
                .fold(f64::INFINITY, f64::min);
            assert!(circular_distance > 5.0);
        }
    }

    #[test]
    fn framed_identity_distinguishes_tagged_seed_and_occurrence() {
        assert_ne!(
            angle_hash_input("rotated", context(None, 0)),
            angle_hash_input("rotated", context(Some(0), 0))
        );
        assert_ne!(
            angle_hash_input("rotated", context(Some(0), 0)),
            angle_hash_input("rotated", context(Some(0), 1))
        );
    }

    #[test]
    fn identical_selection_context_is_reproducible() {
        let selected = resolve_score_angle("rotated", context(Some(42), 7));
        assert_eq!(
            selected,
            resolve_score_angle("rotated", context(Some(42), 7))
        );
        assert_eq!(resolve_score_angle("unknown", context(None, 0)), None);
    }
}
