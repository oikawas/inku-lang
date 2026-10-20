//! Numeric position ranges and numeric segments written into a DDL position phrase,
//! numeric angles written into a noun phrase, and fades written in words.
//!
//! A segment (stage B-2a, the author's decision of 2026-10-19) gives the two
//! points a row or a line runs between, read as one lexeme in its own language:
//! Japanese `（画面の）横0.118、縦0.5から横0.882、縦0.5まで` and English
//! `from horizontal 0.118, vertical 0.5 to horizontal 0.882, vertical 0.5`.
//! Its values are read as a range's are, and whether its points lie on the
//! canvas and differ is checked by the geometry analysis.
//!
//! An angle (stage B-4a) turns the marks by a number of degrees, read as one
//! lexeme so that its whole number is not read as a count: Japanese `回転30度`
//! and English `rotated 30 degrees`. Its value is a whole or decimal number
//! without a sign or a fraction, and whether it is below 360 is checked by the
//! geometry analysis.
//!
//! A fade (DDL 23, the author's decision of 2026-10-20) makes the marks of a
//! row fade from one named end to the other, or the marks of a row or a scatter
//! fade outward from their center. It is a grammar form, not a Saijiki word,
//! read as one lexeme so that the place words inside it (`上`, `中心`) are not
//! read alone: Japanese `左から右へ薄れさせて` (and `右から左へ`, `上から下へ`,
//! `下から上へ`, `中心から外へ`) and English `fading from left to right` (and
//! `right to left`, `top to bottom`, `bottom to top`) or
//! `fading outward from the center`. Which marks may fade is checked when the
//! instruction is lowered.
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

/// One numeric segment lexeme. `ends` holds the first point and then the second,
/// each horizontal then vertical. A value is `None` when its spelling cannot be
/// represented within the value limits.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct NumericSegmentLexeme {
    pub span: SourceSpan,
    pub ends: [Option<ExactFraction>; 4],
    pub end_spans: [SourceSpan; 4],
}

/// Read a numeric segment that starts exactly at `start`, or return `None`.
pub(crate) fn numeric_segment_at(
    source: &str,
    start: usize,
    language: ResolvedInstructionLanguage,
) -> Option<NumericSegmentLexeme> {
    if !source.is_char_boundary(start) || start >= source.len() {
        return None;
    }
    match language {
        ResolvedInstructionLanguage::Ja => japanese_segment(source, start),
        ResolvedInstructionLanguage::En => english_segment(source, start),
    }
}

/// One point of a segment: its values and their spans, horizontal then vertical.
struct SegmentPoint {
    values: [Option<ExactFraction>; 2],
    spans: [SourceSpan; 2],
}

fn segment_lexeme(
    start: usize,
    end: usize,
    from: SegmentPoint,
    to: SegmentPoint,
) -> NumericSegmentLexeme {
    NumericSegmentLexeme {
        span: SourceSpan {
            start_byte: start,
            end_byte: end,
        },
        ends: [from.values[0], from.values[1], to.values[0], to.values[1]],
        end_spans: [from.spans[0], from.spans[1], to.spans[0], to.spans[1]],
    }
}

/// One numeric angle lexeme: the degrees the marks turn (clockwise, as the
/// Score's rotation). `degrees` is `None` when its spelling cannot be
/// represented within the value limits.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct NumericAngleLexeme {
    pub span: SourceSpan,
    pub degrees: Option<ExactFraction>,
    pub degrees_span: SourceSpan,
}

/// Read a numeric angle that starts exactly at `start`, or return `None`.
pub(crate) fn numeric_angle_at(
    source: &str,
    start: usize,
    language: ResolvedInstructionLanguage,
) -> Option<NumericAngleLexeme> {
    if !source.is_char_boundary(start) || start >= source.len() {
        return None;
    }
    match language {
        ResolvedInstructionLanguage::Ja => japanese_angle(source, start),
        ResolvedInstructionLanguage::En => english_angle(source, start),
    }
}

fn angle_lexeme(
    start: usize,
    end: usize,
    degrees: Option<ExactFraction>,
    degrees_span: SourceSpan,
) -> NumericAngleLexeme {
    NumericAngleLexeme {
        span: SourceSpan {
            start_byte: start,
            end_byte: end,
        },
        degrees,
        degrees_span,
    }
}

/// The way a fade runs: from one named end of a row to the other, or outward
/// from the center of a row or a scatter.
#[derive(Clone, Copy, Debug, Eq, Hash, PartialEq, serde::Serialize, serde::Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum FadeDirection {
    LeftToRight,
    RightToLeft,
    TopToBottom,
    BottomToTop,
    Outward,
}

impl FadeDirection {
    pub const ALL: [Self; 5] = [
        Self::LeftToRight,
        Self::RightToLeft,
        Self::TopToBottom,
        Self::BottomToTop,
        Self::Outward,
    ];

    pub const fn as_str(self) -> &'static str {
        match self {
            Self::LeftToRight => "left_to_right",
            Self::RightToLeft => "right_to_left",
            Self::TopToBottom => "top_to_bottom",
            Self::BottomToTop => "bottom_to_top",
            Self::Outward => "outward",
        }
    }

    /// The Japanese words, as the lexeme reads them and a work plan prints them.
    pub const fn written_ja(self) -> &'static str {
        match self {
            Self::LeftToRight => "左から右へ薄れさせて",
            Self::RightToLeft => "右から左へ薄れさせて",
            Self::TopToBottom => "上から下へ薄れさせて",
            Self::BottomToTop => "下から上へ薄れさせて",
            Self::Outward => "中心から外へ薄れさせて",
        }
    }

    /// The English words after `fading`, one space apart.
    const fn words_en(self) -> &'static [&'static str] {
        match self {
            Self::LeftToRight => &["from", "left", "to", "right"],
            Self::RightToLeft => &["from", "right", "to", "left"],
            Self::TopToBottom => &["from", "top", "to", "bottom"],
            Self::BottomToTop => &["from", "bottom", "to", "top"],
            Self::Outward => &["outward", "from", "the", "center"],
        }
    }

    /// The English words, as a work plan prints them.
    pub const fn written_en(self) -> &'static str {
        match self {
            Self::LeftToRight => "fading from left to right",
            Self::RightToLeft => "fading from right to left",
            Self::TopToBottom => "fading from top to bottom",
            Self::BottomToTop => "fading from bottom to top",
            Self::Outward => "fading outward from the center",
        }
    }
}

/// One fade lexeme and the way it runs.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct FadeLexeme {
    pub span: SourceSpan,
    pub direction: FadeDirection,
}

/// Read a fade that starts exactly at `start`, or return `None`.
pub(crate) fn fade_at(
    source: &str,
    start: usize,
    language: ResolvedInstructionLanguage,
) -> Option<FadeLexeme> {
    if !source.is_char_boundary(start) || start >= source.len() {
        return None;
    }
    match language {
        ResolvedInstructionLanguage::Ja => japanese_fade(source, start),
        ResolvedInstructionLanguage::En => english_fade(source, start),
    }
}

fn fade_lexeme(start: usize, end: usize, direction: FadeDirection) -> FadeLexeme {
    FadeLexeme {
        span: SourceSpan {
            start_byte: start,
            end_byte: end,
        },
        direction,
    }
}

// ----- Japanese -------------------------------------------------------------

// `左から右へ薄れさせて` and the other four, written as they are.
fn japanese_fade(source: &str, start: usize) -> Option<FadeLexeme> {
    if !japanese_keyword_left_boundary(source, start) {
        return None;
    }
    FadeDirection::ALL.into_iter().find_map(|direction| {
        literal(source, start, direction.written_ja()).map(|end| fade_lexeme(start, end, direction))
    })
}

// `回転A度`, with optional spaces between the parts. The number has no sign and
// no fraction.
fn japanese_angle(source: &str, start: usize) -> Option<NumericAngleLexeme> {
    if !japanese_keyword_left_boundary(source, start) {
        return None;
    }
    let cursor = literal(source, start, "回転")?;
    let (cursor, degrees, degrees_span) = number(
        source,
        skip_japanese_space(source, cursor),
        japanese_digit,
        |character| matches!(character, '.' | '．'),
        |_| false,
    )?;
    let end = literal(source, skip_japanese_space(source, cursor), "度")?;
    Some(angle_lexeme(start, end, degrees, degrees_span))
}

// `（画面の）横A、縦Bから横C、縦Dまで`, with optional spaces between the parts.
fn japanese_segment(source: &str, start: usize) -> Option<NumericSegmentLexeme> {
    if !japanese_keyword_left_boundary(source, start) {
        return None;
    }
    let cursor = source[start..]
        .strip_prefix("画面の")
        .map_or(start, |_| start + "画面の".len());
    let (cursor, from) = japanese_point(source, cursor)?;
    let cursor = literal(source, skip_japanese_space(source, cursor), "から")?;
    let (cursor, to) = japanese_point(source, cursor)?;
    let end = literal(source, skip_japanese_space(source, cursor), "まで")?;
    Some(segment_lexeme(start, end, from, to))
}

// `横A、縦B`.
fn japanese_point(source: &str, start: usize) -> Option<(usize, SegmentPoint)> {
    let cursor = literal(source, skip_japanese_space(source, start), "横")?;
    let (cursor, x, x_span) = japanese_number(source, skip_japanese_space(source, cursor))?;
    let cursor = japanese_axis_separator(source, skip_japanese_space(source, cursor))?;
    let cursor = literal(source, skip_japanese_space(source, cursor), "縦")?;
    let (cursor, y, y_span) = japanese_number(source, skip_japanese_space(source, cursor))?;
    Some((
        cursor,
        SegmentPoint {
            values: [x, y],
            spans: [x_span, y_span],
        },
    ))
}

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

// `fading from left to right` and the other four, in any letter case, with one
// or more spaces between the words.
fn english_fade(source: &str, start: usize) -> Option<FadeLexeme> {
    let after_fading = english_word(source, start, "fading")?;
    FadeDirection::ALL.into_iter().find_map(|direction| {
        let mut cursor = after_fading;
        for word in direction.words_en() {
            cursor = english_word(source, skip_english_space_required(source, cursor)?, word)?;
        }
        Some(fade_lexeme(start, cursor, direction))
    })
}

// `rotated A degrees` (or `degree`), in any letter case. The number has no sign
// and no fraction.
fn english_angle(source: &str, start: usize) -> Option<NumericAngleLexeme> {
    let cursor = english_word(source, start, "rotated")?;
    let (cursor, degrees, degrees_span) = number(
        source,
        skip_english_space_required(source, cursor)?,
        |character| {
            character
                .to_digit(10)
                .filter(|_| character.is_ascii_digit())
                .map(u64::from)
        },
        |character| character == '.',
        |_| false,
    )?;
    let cursor = skip_english_space_required(source, cursor)?;
    let end = english_word(source, cursor, "degrees")
        .or_else(|| english_word(source, cursor, "degree"))?;
    Some(angle_lexeme(start, end, degrees, degrees_span))
}

// `from horizontal A, vertical B to horizontal C, vertical D`.
fn english_segment(source: &str, start: usize) -> Option<NumericSegmentLexeme> {
    let cursor = english_word(source, start, "from")?;
    let (cursor, from) = english_point(source, skip_english_space_required(source, cursor)?)?;
    let cursor = english_word(source, skip_english_space_required(source, cursor)?, "to")?;
    let (end, to) = english_point(source, skip_english_space_required(source, cursor)?)?;
    Some(segment_lexeme(start, end, from, to))
}

// `horizontal A, vertical B`; the comma is optional, as in a numeric point.
fn english_point(source: &str, start: usize) -> Option<(usize, SegmentPoint)> {
    let cursor = english_word(source, start, "horizontal")?;
    let (cursor, x, x_span) = english_number(source, skip_english_space_required(source, cursor)?)?;
    let mut cursor = skip_english_space(source, cursor);
    if source[cursor..].starts_with(',') {
        cursor = skip_english_space(source, cursor + 1);
    }
    let cursor = english_word(source, cursor, "vertical")?;
    let (cursor, y, y_span) = english_number(source, skip_english_space_required(source, cursor)?)?;
    Some((
        cursor,
        SegmentPoint {
            values: [x, y],
            spans: [x_span, y_span],
        },
    ))
}

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

    fn segment(
        source: &str,
        start_text: &str,
        language: ResolvedInstructionLanguage,
    ) -> Option<NumericSegmentLexeme> {
        let start = source
            .find(start_text)
            .expect("the start text is in the source");
        numeric_segment_at(source, start, language)
    }

    /// Stage B-2a: a segment gives the two points a row or a line runs between,
    /// with or without the canvas, with any axis separator, full-width digits,
    /// fractions and spaces, as a range does. It ends at まで.
    #[test]
    fn a_japanese_segment_reads_its_two_points() {
        let source = "画面の横0.118、縦0.5から横0.882、縦0.5まで、半径0.03の青の円を5個並べる。";
        let lexeme = segment(source, "画面の", ResolvedInstructionLanguage::Ja).unwrap();
        assert_eq!(
            lexeme.ends,
            [
                fraction(118, 1000),
                fraction(1, 2),
                fraction(882, 1000),
                fraction(1, 2)
            ]
        );
        assert_eq!(
            &source[..lexeme.span.end_byte],
            "画面の横0.118、縦0.5から横0.882、縦0.5まで"
        );
        assert_eq!(
            &source[lexeme.end_spans[2].start_byte..lexeme.end_spans[2].end_byte],
            "0.882"
        );
        assert_eq!(
            segment(source, "画面の", ResolvedInstructionLanguage::En),
            None
        );
        let bare = "横１／３, 縦0 から 横2/3，縦１まで、灰の鉛筆の線を1本引く。";
        let lexeme = segment(bare, "横", ResolvedInstructionLanguage::Ja).unwrap();
        assert_eq!(
            lexeme.ends,
            [
                fraction(1, 3),
                fraction(0, 1),
                fraction(2, 3),
                fraction(1, 1)
            ]
        );
        assert!(bare[lexeme.span.end_byte..].starts_with('、'));
    }

    /// A point, a range, a segment without its second point or its まで, and a
    /// segment in the middle of a word are not segments.
    #[test]
    fn a_japanese_point_or_range_is_not_a_segment() {
        let ja = ResolvedInstructionLanguage::Ja;
        for (source, start) in [
            ("画面の横0.5、縦0.5の位置に、赤い円を1個置く。", "画面の"),
            (
                "画面の横0.2〜0.8、縦0.3〜0.6の範囲に、円を5個並べる。",
                "画面の",
            ),
            ("画面の横0.1、縦0.5から右へ、円を5個並べる。", "画面の"),
            (
                "画面の横0.1、縦0.5から横0.9、縦0.5、円を5個並べる。",
                "画面の",
            ),
            (
                "赤い横0.1、縦0.5から横0.9、縦0.5まで、円を5個並べる。",
                "横",
            ),
        ] {
            assert_eq!(segment(source, start, ja), None, "{source}");
        }
    }

    /// English: `from horizontal A, vertical B to horizontal C, vertical D`, in
    /// any letter case, with the comma between the axes optional as in a point.
    #[test]
    fn an_english_segment_reads_its_two_points() {
        let en = ResolvedInstructionLanguage::En;
        let source = "Line up 5 blue circles radius 0.03 from horizontal 0.118, vertical 0.5 to horizontal 0.882, vertical 0.5.";
        let lexeme = segment(source, "from", en).unwrap();
        assert_eq!(
            lexeme.ends,
            [
                fraction(118, 1000),
                fraction(1, 2),
                fraction(882, 1000),
                fraction(1, 2)
            ]
        );
        assert!(source[lexeme.span.end_byte..].starts_with('.'));
        assert_eq!(
            segment(source, "from", ResolvedInstructionLanguage::Ja),
            None
        );
        let loose =
            "Draw one gray line From Horizontal 1/10 vertical 0.1 TO horizontal 0.9 vertical 0.9.";
        let lexeme = segment(loose, "From", en).unwrap();
        assert_eq!(
            lexeme.ends,
            [
                fraction(1, 10),
                fraction(1, 10),
                fraction(9, 10),
                fraction(9, 10)
            ]
        );
        for (source, start) in [
            (
                "Place one red circle at horizontal 0.5, vertical 0.3.",
                "at",
            ),
            ("Draw smoke from the chimney to the sky.", "from"),
            (
                "Draw one line from horizontal 0.1, vertical 0.5 to the edge.",
                "from",
            ),
            (
                "Draw one line fromhorizontal 0.1, vertical 0.5 to horizontal 0.9, vertical 0.5.",
                "from",
            ),
        ] {
            assert_eq!(segment(source, start, en), None, "{source}");
        }
    }

    fn angle(
        source: &str,
        start_text: &str,
        language: ResolvedInstructionLanguage,
    ) -> Option<NumericAngleLexeme> {
        let start = source
            .find(start_text)
            .expect("the start text is in the source");
        numeric_angle_at(source, start, language)
    }

    /// Stage B-4a: `回転A度` turns the marks; a whole number is part of the angle,
    /// not a count. Spaces, full-width digits and a decimal point are read as a
    /// range's are, and a value past the limits is kept as `None`.
    #[test]
    fn a_japanese_angle_reads_its_degrees() {
        let ja = ResolvedInstructionLanguage::Ja;
        let source = "画面の横0.5、縦0.5の位置に、一辺0.1の回転30度の赤い四角を1個置く。";
        let lexeme = angle(source, "回転", ja).unwrap();
        assert_eq!(lexeme.degrees, fraction(30, 1));
        assert_eq!(
            &source[lexeme.span.start_byte..lexeme.span.end_byte],
            "回転30度"
        );
        assert_eq!(
            &source[lexeme.degrees_span.start_byte..lexeme.degrees_span.end_byte],
            "30"
        );
        assert!(source[lexeme.span.end_byte..].starts_with('の'));
        assert_eq!(angle(source, "回転", ResolvedInstructionLanguage::En), None);
        let loose = "回転 ３５９．５ 度の弧を1個置く。";
        assert_eq!(
            angle(loose, "回転", ja).unwrap().degrees,
            fraction(7_190, 20)
        );
        let fine = "、回転12.3456789度の円を1個置く。";
        assert_eq!(angle(fine, "回転", ja).unwrap().degrees, None);
    }

    /// The seeded angle word alone, a fraction, a sign, a missing 度 and an angle
    /// in the middle of a word are not numeric angles.
    #[test]
    fn a_japanese_angle_word_without_degrees_is_not_a_numeric_angle() {
        let ja = ResolvedInstructionLanguage::Ja;
        for source in [
            "回転の四角を1個置く。",
            "回転1/3度の四角を1個置く。",
            "回転-30度の四角を1個置く。",
            "回転30の四角を1個置く。",
            "赤い回転30度の四角を1個置く。",
        ] {
            assert_eq!(angle(source, "回転", ja), None, "{source}");
        }
    }

    /// English: `rotated A degrees` or `rotated A degree`, in any letter case,
    /// after the noun as a numeric size is.
    #[test]
    fn an_english_angle_reads_its_degrees() {
        let en = ResolvedInstructionLanguage::En;
        let source = "Place one red square side length 0.1 rotated 30 degrees at horizontal 0.5, vertical 0.5.";
        let lexeme = angle(source, "rotated", en).unwrap();
        assert_eq!(lexeme.degrees, fraction(30, 1));
        assert!(source[lexeme.span.end_byte..].starts_with(" at"));
        assert_eq!(
            angle(source, "rotated", ResolvedInstructionLanguage::Ja),
            None
        );
        let one = "Place one arc Rotated 1 Degree at horizontal 0.5, vertical 0.5.";
        assert_eq!(angle(one, "Rotated", en).unwrap().degrees, fraction(1, 1));
        let decimal = "Place one ellipse rotated 22.5 degrees at horizontal 0.5, vertical 0.5.";
        assert_eq!(
            angle(decimal, "rotated", en).unwrap().degrees,
            fraction(45, 2)
        );
        for source in [
            "Place one rotated square at horizontal 0.5, vertical 0.5.",
            "Place one square rotated 30 at horizontal 0.5, vertical 0.5.",
            "Place one square rotated 1/3 degrees at horizontal 0.5, vertical 0.5.",
            "Place one square rotated 30degrees at horizontal 0.5, vertical 0.5.",
            "Place one square unrotated 30 degrees at horizontal 0.5, vertical 0.5.",
        ] {
            assert_eq!(angle(source, "rotated", en), None, "{source}");
        }
    }

    fn fade(
        source: &str,
        start_text: &str,
        language: ResolvedInstructionLanguage,
    ) -> Option<FadeLexeme> {
        let start = source
            .find(start_text)
            .expect("the start text is in the source");
        fade_at(source, start, language)
    }

    /// DDL 23: each of the five Japanese fades is one lexeme, read only in
    /// Japanese and only from a word boundary.
    #[test]
    fn a_japanese_fade_reads_its_direction() {
        let ja = ResolvedInstructionLanguage::Ja;
        for direction in FadeDirection::ALL {
            let source = format!(
                "中央の縦（横1/3〜2/3、縦0〜1）に、{}、赤い小さな円を9個並べる。",
                direction.written_ja()
            );
            let lexeme = fade(&source, direction.written_ja(), ja).unwrap();
            assert_eq!(lexeme.direction, direction);
            assert_eq!(
                &source[lexeme.span.start_byte..lexeme.span.end_byte],
                direction.written_ja()
            );
            assert!(source[lexeme.span.end_byte..].starts_with('、'));
            assert_eq!(
                fade(
                    &source,
                    direction.written_ja(),
                    ResolvedInstructionLanguage::En
                ),
                None
            );
        }
        for source in [
            "左から右へ薄くして、赤い円を9個並べる。",
            "左から右へ薄れる赤い円を9個並べる。",
            "赤い左から右へ薄れさせて、円を9個並べる。",
        ] {
            assert_eq!(fade(source, "左", ja), None, "{source}");
        }
    }

    /// English: `fading` and its direction words, in any letter case, at the
    /// end of the sentence as an alternation is.
    #[test]
    fn an_english_fade_reads_its_direction() {
        let en = ResolvedInstructionLanguage::En;
        for direction in FadeDirection::ALL {
            let source = format!(
                "Line up 9 small red circles in the range horizontal 0.1 to 0.9, vertical 0.45 to 0.55, {}.",
                direction.written_en()
            );
            let lexeme = fade(&source, "fading", en).unwrap();
            assert_eq!(lexeme.direction, direction);
            assert_eq!(
                &source[lexeme.span.start_byte..lexeme.span.end_byte],
                direction.written_en()
            );
            assert_eq!(
                fade(&source, "fading", ResolvedInstructionLanguage::Ja),
                None
            );
        }
        let loose = "Scatter 30 points, Fading  Outward from THE center.";
        assert_eq!(
            fade(loose, "Fading", en).unwrap().direction,
            FadeDirection::Outward
        );
        for source in [
            "Scatter five thin black fading lines across the whole canvas.",
            "Line up 9 circles, fading from left.",
            "Line up 9 circles, fading from left to the right.",
            "Line up 9 circles, unfading from left to right.",
        ] {
            assert_eq!(fade(source, "fading", en), None, "{source}");
        }
    }
}
