//! Numeric position ranges written into a DDL position phrase.
//!
//! A range is read as one lexeme, and only in its own instruction language:
//!
//! - Japanese, with the author's words: `右下（横0.67〜1、縦0.67〜1）に`
//! - Japanese, numbers only: `画面の横0.2〜0.5、縦0〜0.3の範囲に`
//! - English, with the author's words:
//!   `at the bottom right (horizontal 0.67 to 1, vertical 0.67 to 1)`
//! - English, numbers only: `in the range horizontal 0.2 to 0.5, vertical 0 to 0.3`
//!
//! The words before the parenthesis are the author's original words. They are
//! kept as a span and never read, so no vocabulary grows. A Japanese range must
//! be followed by `に`, and an English range must follow `at`, `in`, or `on`,
//! so the words cannot swallow the head of an instruction.
//!
//! Japanese accepts the wave dash, the full-width tilde, the ASCII tilde, and the
//! ASCII and full-width hyphens (the author's decision of 2026-10-05) as the range
//! mark, full-width digits, periods, and slashes, and full-width or
//! ASCII parentheses. English accepts `to`, and the ASCII hyphen and the en dash
//! (the author's decision of 2026-10-05), ASCII digits, and ASCII parentheses. A value is a decimal or a fraction. Whether a range lies on the
//! canvas and has a width is checked by the geometry analysis, not here.

use crate::{ResolvedInstructionLanguage, SourceSpan};

/// The largest denominator a range value may have: six decimal places, or a
/// fraction whose parts stay within one million.
const MAX_DENOMINATOR: u64 = 1_000_000;
const MAX_DECIMAL_PLACES: u32 = 6;

/// An exact non-negative fraction in lowest terms.
#[derive(Clone, Copy, Debug, Eq, PartialEq, Hash)]
pub struct ExactFraction {
    numerator: u64,
    denominator: u64,
}

impl ExactFraction {
    pub(crate) fn new(numerator: u64, denominator: u64) -> Option<Self> {
        if denominator == 0 {
            return None;
        }
        let divisor = gcd(numerator, denominator).max(1);
        Some(Self {
            numerator: numerator / divisor,
            denominator: denominator / divisor,
        })
    }

    pub const fn numerator(self) -> u64 {
        self.numerator
    }

    pub const fn denominator(self) -> u64 {
        self.denominator
    }

    /// Whether `self` is strictly below `other`, compared exactly.
    pub fn is_below(self, other: Self) -> bool {
        u128::from(self.numerator) * u128::from(other.denominator)
            < u128::from(other.numerator) * u128::from(self.denominator)
    }

    pub const fn is_at_most_one(self) -> bool {
        self.numerator <= self.denominator
    }
}

const fn gcd(a: u64, b: u64) -> u64 {
    let (mut a, mut b) = (a, b);
    while b != 0 {
        let remainder = a % b;
        a = b;
        b = remainder;
    }
    a
}

/// One numeric range lexeme. `bounds` is in region order: horizontal start,
/// vertical start, horizontal end, vertical end. A bound is `None` when its
/// spelling cannot be represented within the value limits.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct NumericRangeLexeme {
    pub span: SourceSpan,
    pub bounds: [Option<ExactFraction>; 4],
    pub bound_spans: [SourceSpan; 4],
    /// The author's original words before the parenthesis, when there are any.
    pub annotation: Option<SourceSpan>,
}

/// Read a numeric range that starts exactly at `start`, or return `None`.
pub(crate) fn numeric_range_at(
    source: &str,
    start: usize,
    language: ResolvedInstructionLanguage,
) -> Option<NumericRangeLexeme> {
    if !source.is_char_boundary(start) || start >= source.len() {
        return None;
    }
    match language {
        ResolvedInstructionLanguage::Ja => {
            japanese_numbers_only(source, start).or_else(|| japanese_with_words(source, start))
        }
        ResolvedInstructionLanguage::En => {
            english_numbers_only(source, start).or_else(|| english_with_words(source, start))
        }
    }
}

// ----- Japanese -------------------------------------------------------------

fn japanese_numbers_only(source: &str, start: usize) -> Option<NumericRangeLexeme> {
    if !japanese_keyword_left_boundary(source, start) {
        return None;
    }
    let cursor = source[start..]
        .strip_prefix("画面の")
        .map_or(start, |_| start + "画面の".len());
    let body = japanese_body(source, cursor)?;
    let end = literal(source, skip_japanese_space(source, body.end), "の範囲")?;
    followed_by_ni(source, end).then_some(NumericRangeLexeme {
        span: SourceSpan {
            start_byte: start,
            end_byte: end,
        },
        bounds: body.bounds,
        bound_spans: body.bound_spans,
        annotation: None,
    })
}

fn japanese_with_words(source: &str, start: usize) -> Option<NumericRangeLexeme> {
    if !japanese_words_left_boundary(source, start) {
        return None;
    }
    let mut cursor = start;
    let open = loop {
        let character = source[cursor..].chars().next()?;
        if matches!(character, '（' | '(') {
            break cursor;
        }
        if japanese_words_stop(character) {
            return None;
        }
        cursor += character.len_utf8();
    };
    let body = japanese_body(source, open + source[open..].chars().next()?.len_utf8())?;
    let close = skip_japanese_space(source, body.end);
    let closing = source[close..].chars().next()?;
    if !matches!(closing, '）' | ')') {
        return None;
    }
    let end = close + closing.len_utf8();
    followed_by_ni(source, end).then(|| NumericRangeLexeme {
        span: SourceSpan {
            start_byte: start,
            end_byte: end,
        },
        bounds: body.bounds,
        bound_spans: body.bound_spans,
        annotation: words_span(source, start, open, is_japanese_space),
    })
}

struct Body {
    end: usize,
    bounds: [Option<ExactFraction>; 4],
    bound_spans: [SourceSpan; 4],
}

// `横A〜B、縦C〜D`, with optional spaces between the parts.
fn japanese_body(source: &str, start: usize) -> Option<Body> {
    let mut cursor = skip_japanese_space(source, start);
    cursor = literal(source, cursor, "横")?;
    let (cursor, x0, x0_span) = japanese_number(source, skip_japanese_space(source, cursor))?;
    let cursor = japanese_range_mark(source, skip_japanese_space(source, cursor))?;
    let (cursor, x1, x1_span) = japanese_number(source, skip_japanese_space(source, cursor))?;
    let cursor = japanese_axis_separator(source, skip_japanese_space(source, cursor))?;
    let cursor = literal(source, skip_japanese_space(source, cursor), "縦")?;
    let (cursor, y0, y0_span) = japanese_number(source, skip_japanese_space(source, cursor))?;
    let cursor = japanese_range_mark(source, skip_japanese_space(source, cursor))?;
    let (cursor, y1, y1_span) = japanese_number(source, skip_japanese_space(source, cursor))?;
    Some(Body {
        end: cursor,
        bounds: [x0, y0, x1, y1],
        bound_spans: [x0_span, y0_span, x1_span, y1_span],
    })
}

fn japanese_number(
    source: &str,
    start: usize,
) -> Option<(usize, Option<ExactFraction>, SourceSpan)> {
    number(
        source,
        start,
        japanese_digit,
        |character| matches!(character, '.' | '．'),
        |character| matches!(character, '/' | '／'),
    )
}

fn japanese_digit(character: char) -> Option<u64> {
    match character {
        '0'..='9' => Some(u64::from(character as u32 - '0' as u32)),
        '０'..='９' => Some(u64::from(character as u32 - '０' as u32)),
        _ => None,
    }
}

// Wave dash U+301C, full-width tilde U+FF5E, ASCII tilde U+007E, hyphen-minus
// U+002D and full-width hyphen-minus U+FF0D. A bound is never negative, so a hyphen
// between two numbers can only join them.
fn japanese_range_mark(source: &str, start: usize) -> Option<usize> {
    let character = source[start..].chars().next()?;
    matches!(character, '〜' | '～' | '~' | '-' | '－').then(|| start + character.len_utf8())
}

// Ideographic comma U+3001, full-width comma U+FF0C, ASCII comma U+002C.
fn japanese_axis_separator(source: &str, start: usize) -> Option<usize> {
    let character = source[start..].chars().next()?;
    matches!(character, '、' | '，' | ',').then(|| start + character.len_utf8())
}

fn is_japanese_space(character: char) -> bool {
    matches!(character, ' ' | '\t' | '\u{3000}')
}

fn skip_japanese_space(source: &str, start: usize) -> usize {
    skip(source, start, is_japanese_space)
}

// The author's words cannot cross a clause, a comma, the object particle, or
// another parenthesis.
fn japanese_words_stop(character: char) -> bool {
    matches!(
        character,
        '、' | '，'
            | ','
            | 'を'
            | '。'
            | '．'
            | '.'
            | '！'
            | '!'
            | '？'
            | '?'
            | '\n'
            | '\r'
            | '）'
            | ')'
    )
}

// The words start a clause, or follow a comma or the object particle.
fn japanese_words_left_boundary(source: &str, start: usize) -> bool {
    let first = source[start..].chars().next();
    if first.is_some_and(is_japanese_space) {
        return false;
    }
    let before = source[..start].trim_end_matches(is_japanese_space);
    match before.chars().next_back() {
        None => true,
        Some(previous) => matches!(
            previous,
            '、' | '，' | ',' | 'を' | '。' | '．' | '.' | '！' | '!' | '？' | '?' | '\n' | '\r'
        ),
    }
}

// The same left boundary a Japanese geometry keyword uses.
fn japanese_keyword_left_boundary(source: &str, start: usize) -> bool {
    match source[..start].chars().next_back() {
        None => true,
        Some(previous) => {
            previous.is_whitespace()
                || previous.is_ascii_punctuation()
                || matches!(
                    previous,
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
                        | 'を'
                        | 'に'
                        | 'で'
                        | 'の'
                        | 'は'
                        | 'が'
                        | 'へ'
                        | 'と'
                )
        }
    }
}

fn followed_by_ni(source: &str, end: usize) -> bool {
    source[skip_japanese_space(source, end)..].starts_with('に')
}

// ----- English --------------------------------------------------------------

fn english_numbers_only(source: &str, start: usize) -> Option<NumericRangeLexeme> {
    if !english_follows_place_preposition(source, start) {
        return None;
    }
    let mut cursor = start;
    if let Some(after_the) = english_word(source, cursor, "the") {
        cursor = skip_english_space_required(source, after_the)?;
    }
    let cursor = english_word(source, cursor, "range")?;
    let body = english_body(source, skip_english_space_required(source, cursor)?)?;
    Some(NumericRangeLexeme {
        span: SourceSpan {
            start_byte: start,
            end_byte: body.end,
        },
        bounds: body.bounds,
        bound_spans: body.bound_spans,
        annotation: None,
    })
}

fn english_with_words(source: &str, start: usize) -> Option<NumericRangeLexeme> {
    if !english_follows_place_preposition(source, start) {
        return None;
    }
    let mut cursor = start;
    let open = loop {
        let character = source[cursor..].chars().next()?;
        if character == '(' {
            break cursor;
        }
        if english_words_stop(character)
            || (english_word_start(source, cursor) && english_place_preposition_at(source, cursor))
        {
            return None;
        }
        cursor += character.len_utf8();
    };
    let body = english_body(source, open + 1)?;
    let close = skip_english_space(source, body.end);
    if !source[close..].starts_with(')') {
        return None;
    }
    let end = close + 1;
    Some(NumericRangeLexeme {
        span: SourceSpan {
            start_byte: start,
            end_byte: end,
        },
        bounds: body.bounds,
        bound_spans: body.bound_spans,
        annotation: words_span(source, start, open, is_english_space),
    })
}

// Between two English bounds: `to` between spaces, or a hyphen U+002D or an en
// dash U+2013 with optional spaces (2026-10-05). A bound is never negative, so a
// dash between two numbers can only join them. Returns where the second starts.
fn english_range_join(source: &str, after_number: usize) -> Option<usize> {
    let cursor = skip_english_space(source, after_number);
    if let Some(dash) = source[cursor..]
        .chars()
        .next()
        .filter(|character| matches!(character, '-' | '–'))
    {
        return Some(skip_english_space(source, cursor + dash.len_utf8()));
    }
    let after_to = english_word(
        source,
        skip_english_space_required(source, after_number)?,
        "to",
    )?;
    skip_english_space_required(source, after_to)
}

// `horizontal A to B, vertical C to D` (or `A-B`, `A–B`).
fn english_body(source: &str, start: usize) -> Option<Body> {
    let cursor = english_word(source, skip_english_space(source, start), "horizontal")?;
    let (cursor, x0, x0_span) =
        english_number(source, skip_english_space_required(source, cursor)?)?;
    let (cursor, x1, x1_span) = english_number(source, english_range_join(source, cursor)?)?;
    let cursor = skip_english_space(source, cursor);
    let cursor = source[cursor..].starts_with(',').then_some(cursor + 1)?;
    let cursor = english_word(source, skip_english_space(source, cursor), "vertical")?;
    let (cursor, y0, y0_span) =
        english_number(source, skip_english_space_required(source, cursor)?)?;
    let (cursor, y1, y1_span) = english_number(source, english_range_join(source, cursor)?)?;
    Some(Body {
        end: cursor,
        bounds: [x0, y0, x1, y1],
        bound_spans: [x0_span, y0_span, x1_span, y1_span],
    })
}

fn english_number(
    source: &str,
    start: usize,
) -> Option<(usize, Option<ExactFraction>, SourceSpan)> {
    let (end, value, span) = number(
        source,
        start,
        |character| {
            character
                .to_digit(10)
                .filter(|_| character.is_ascii_digit())
                .map(u64::from)
        },
        |character| character == '.',
        |character| character == '/',
    )?;
    // A number is a whole word in English.
    (!source[end..]
        .chars()
        .next()
        .is_some_and(|character| character.is_ascii_alphanumeric()))
    .then_some((end, value, span))
}

fn is_english_space(character: char) -> bool {
    matches!(character, ' ' | '\t')
}

fn skip_english_space(source: &str, start: usize) -> usize {
    skip(source, start, is_english_space)
}

fn skip_english_space_required(source: &str, start: usize) -> Option<usize> {
    let end = skip_english_space(source, start);
    (end > start).then_some(end)
}

// Match one ASCII word case-insensitively, as a whole word.
fn english_word(source: &str, start: usize, word: &str) -> Option<usize> {
    let end = start.checked_add(word.len())?;
    let actual = source.get(start..end)?;
    if !actual.eq_ignore_ascii_case(word) || !english_word_start(source, start) {
        return None;
    }
    (!source[end..]
        .chars()
        .next()
        .is_some_and(|character| character.is_ascii_alphanumeric()))
    .then_some(end)
}

fn english_word_start(source: &str, start: usize) -> bool {
    !source[..start]
        .chars()
        .next_back()
        .is_some_and(|character| character.is_ascii_alphanumeric())
}

fn english_place_preposition_at(source: &str, start: usize) -> bool {
    ["at", "in", "on"]
        .iter()
        .any(|word| english_word(source, start, word).is_some())
}

// The words follow `at`, `in`, or `on` and one or more spaces.
fn english_follows_place_preposition(source: &str, start: usize) -> bool {
    if source[start..].chars().next().is_none_or(is_english_space) {
        return false;
    }
    let before = source[..start].trim_end_matches(is_english_space);
    if before.len() == start {
        return false;
    }
    ["at", "in", "on"].iter().any(|word| {
        before.len() >= word.len()
            && before.is_char_boundary(before.len() - word.len())
            && english_word(source, before.len() - word.len(), word) == Some(before.len())
    })
}

// The author's words cannot cross a clause, a comma, or another parenthesis.
fn english_words_stop(character: char) -> bool {
    matches!(
        character,
        ',' | ';' | '.' | '!' | '?' | '\n' | '\r' | ')' | '（' | '）'
    )
}

// ----- Shared ---------------------------------------------------------------

// Digits, then optionally a decimal point and digits, or a slash and digits.
fn number(
    source: &str,
    start: usize,
    digit: impl Fn(char) -> Option<u64>,
    is_point: impl Fn(char) -> bool,
    is_slash: impl Fn(char) -> bool,
) -> Option<(usize, Option<ExactFraction>, SourceSpan)> {
    let (after_whole, whole, whole_digits) = digits(source, start, &digit);
    if whole_digits == 0 {
        return None;
    }
    let next = source[after_whole..].chars().next();
    let (end, value) = match next {
        Some(point) if is_point(point) => {
            let after_point = after_whole + point.len_utf8();
            let (end, fraction, places) = digits(source, after_point, &digit);
            if places == 0 {
                return None;
            }
            let value = (places <= MAX_DECIMAL_PLACES)
                .then(|| 10_u64.checked_pow(places))
                .flatten()
                .and_then(|scale| {
                    whole?
                        .checked_mul(scale)?
                        .checked_add(fraction?)
                        .and_then(|numerator| ExactFraction::new(numerator, scale))
                });
            (end, value)
        }
        Some(slash) if is_slash(slash) => {
            let after_slash = after_whole + slash.len_utf8();
            let (end, denominator, denominator_digits) = digits(source, after_slash, &digit);
            if denominator_digits == 0 {
                return None;
            }
            let value = whole
                .zip(denominator)
                .filter(|(numerator, denominator)| {
                    *numerator <= MAX_DENOMINATOR && (1..=MAX_DENOMINATOR).contains(denominator)
                })
                .and_then(|(numerator, denominator)| ExactFraction::new(numerator, denominator));
            (end, value)
        }
        _ => (
            after_whole,
            whole
                .filter(|value| *value <= MAX_DENOMINATOR)
                .and_then(|value| ExactFraction::new(value, 1)),
        ),
    };
    Some((
        end,
        value,
        SourceSpan {
            start_byte: start,
            end_byte: end,
        },
    ))
}

// Returns the end, the value when it fits in u64, and the digit count.
fn digits(
    source: &str,
    start: usize,
    digit: &impl Fn(char) -> Option<u64>,
) -> (usize, Option<u64>, u32) {
    let mut cursor = start;
    let mut value = Some(0_u64);
    let mut count = 0_u32;
    for character in source[start..].chars() {
        let Some(next) = digit(character) else {
            break;
        };
        value = value.and_then(|value| value.checked_mul(10)?.checked_add(next));
        count = count.saturating_add(1);
        cursor += character.len_utf8();
    }
    (cursor, value, count)
}

fn literal(source: &str, start: usize, expected: &str) -> Option<usize> {
    source[start..]
        .starts_with(expected)
        .then(|| start + expected.len())
}

fn skip(source: &str, start: usize, is_space: impl Fn(char) -> bool) -> usize {
    start
        + source[start..]
            .chars()
            .take_while(|character| is_space(*character))
            .map(char::len_utf8)
            .sum::<usize>()
}

fn words_span(
    source: &str,
    start: usize,
    open: usize,
    is_space: impl Fn(char) -> bool,
) -> Option<SourceSpan> {
    let end = start + source[start..open].trim_end_matches(is_space).len();
    (end > start).then_some(SourceSpan {
        start_byte: start,
        end_byte: end,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    fn fraction(numerator: u64, denominator: u64) -> Option<ExactFraction> {
        ExactFraction::new(numerator, denominator)
    }

    fn read(
        source: &str,
        start_text: &str,
        language: ResolvedInstructionLanguage,
    ) -> Option<NumericRangeLexeme> {
        let start = source
            .find(start_text)
            .expect("the start text is in the source");
        numeric_range_at(source, start, language)
    }

    #[test]
    fn japanese_words_and_numbers_read_in_japanese_only() {
        let source = "右下（横0.67〜1、縦２／３～１）に、橙色の小さな円を十個散らす。";
        let lexeme = read(source, "右下", ResolvedInstructionLanguage::Ja).unwrap();
        assert_eq!(
            lexeme.bounds,
            [
                fraction(67, 100),
                fraction(2, 3),
                fraction(1, 1),
                fraction(1, 1)
            ]
        );
        assert_eq!(
            &source[lexeme.annotation.unwrap().start_byte..lexeme.annotation.unwrap().end_byte],
            "右下"
        );
        assert!(source[lexeme.span.end_byte..].starts_with('に'));
        assert_eq!(read(source, "右下", ResolvedInstructionLanguage::En), None);
    }

    #[test]
    fn japanese_words_follow_the_object_particle_and_need_ni() {
        let source = "橙色の小さな円を右下(横0.5~1, 縦0.5~1)に散らす。";
        assert_eq!(read(source, "橙色", ResolvedInstructionLanguage::Ja), None);
        let lexeme = read(source, "右下", ResolvedInstructionLanguage::Ja).unwrap();
        assert_eq!(lexeme.bounds[0], fraction(1, 2));
        assert_eq!(
            read(
                "赤い円（横0〜1、縦0〜1）を置く。",
                "赤い円",
                ResolvedInstructionLanguage::Ja
            ),
            None
        );
    }

    /// An author joins a range with a hyphen as often as with a wave dash or `to`
    /// (2026-10-05): `横1/3-2/3` reads as `横1/3〜2/3` in either width, and
    /// `horizontal 1/3-2/3` as `horizontal 1/3 to 2/3`, with an en dash too.
    #[test]
    fn a_hyphen_joins_a_range() {
        let source = "下中央（横1/3-2/3、縦2/3－1）に、橙色の小さな円を十個散らす。";
        let lexeme = read(source, "下中央", ResolvedInstructionLanguage::Ja).unwrap();
        assert_eq!(
            lexeme.bounds,
            [
                fraction(1, 3),
                fraction(2, 3),
                fraction(2, 3),
                fraction(1, 1)
            ]
        );
        let english =
            "Scatter circles at the bottom center (horizontal 1/3-2/3, vertical 2/3 – 1).";
        assert_eq!(
            read(english, "the bottom", ResolvedInstructionLanguage::En)
                .unwrap()
                .bounds,
            lexeme.bounds
        );
    }

    #[test]
    fn japanese_numbers_only_and_empty_words() {
        let bare = "画面の横0.2〜0.5、縦0〜0.3の範囲に、赤い円を置く。";
        let lexeme = read(bare, "画面の", ResolvedInstructionLanguage::Ja).unwrap();
        assert_eq!(
            &bare[lexeme.span.start_byte..lexeme.span.end_byte],
            "画面の横0.2〜0.5、縦0〜0.3の範囲"
        );
        assert_eq!(lexeme.annotation, None);
        let empty = "赤い円を（横0.2〜0.5、縦0〜0.3）に置く。";
        assert_eq!(
            read(empty, "（", ResolvedInstructionLanguage::Ja)
                .unwrap()
                .annotation,
            None
        );
    }

    #[test]
    fn english_reads_to_and_ascii_only() {
        let source = "Scatter ten small orange circles at the bottom right (horizontal 0.67 to 1, vertical 2/3 to 1).";
        assert_eq!(
            read(source, "Scatter", ResolvedInstructionLanguage::En),
            None
        );
        let lexeme = read(source, "the bottom", ResolvedInstructionLanguage::En).unwrap();
        assert_eq!(lexeme.bounds[1], fraction(2, 3));
        assert_eq!(
            &source[lexeme.annotation.unwrap().start_byte..lexeme.annotation.unwrap().end_byte],
            "the bottom right"
        );
        assert_eq!(
            read(source, "the bottom", ResolvedInstructionLanguage::Ja),
            None
        );
        let tilde = "Scatter circles at the bottom right (horizontal 0.67~1, vertical 0.67~1).";
        assert_eq!(
            read(tilde, "the bottom", ResolvedInstructionLanguage::En),
            None
        );
        let wide =
            "Scatter circles at the bottom right (horizontal ０.67 to 1, vertical 0.67 to 1).";
        assert_eq!(
            read(wide, "the bottom", ResolvedInstructionLanguage::En),
            None
        );
        let bare = "In the range horizontal 0.2 to 0.5, vertical 0 to 0.3, place a red circle.";
        let lexeme = read(bare, "the range", ResolvedInstructionLanguage::En).unwrap();
        assert_eq!(
            lexeme.bounds,
            [
                fraction(1, 5),
                fraction(0, 1),
                fraction(1, 2),
                fraction(3, 10)
            ]
        );
    }

    #[test]
    fn unrepresentable_values_are_kept_as_absent_bounds() {
        let source = "右下（横0.1234567〜1、縦0〜1/0）に置く。";
        let lexeme = read(source, "右下", ResolvedInstructionLanguage::Ja).unwrap();
        assert_eq!(lexeme.bounds[0], None);
        assert_eq!(lexeme.bounds[3], None);
    }
}
