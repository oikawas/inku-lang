//! What a completion wrote into numeric ranges, kept with the work (A3, the
//! author's decisions of 2026-09-27 and 2026-10-11).
//!
//! A completion writes a place the position words cannot say as the author's
//! words and a numeric range (`右下（横2/3〜1、縦2/3〜1）`, A1). The record keeps
//! each such range's words, numbers and sentence, so that when the author later
//! edits the instructions each range can be told apart:
//!
//! - completed: the words and the numbers are as the completion wrote them;
//! - numbers changed: the author changed the numbers, which are drawn as written;
//! - words changed: the author changed only the words, and the range becomes a
//!   hole the completion writes the numbers of again.
//!
//! An instruction text alone carries no record: its numbers are drawn and its
//! words are only their origin, as before. The compiler never reads the record;
//! a words-changed range is a hole laid over a compilation, not a compiler hole,
//! so the compiler lock, its state and the Score stay those of the text alone.

use serde::{Deserialize, Serialize};

use crate::{
    ClauseAtom, ExactFraction, GeometryKeyword, SemanticDeliveryKind, SemanticDeliveryOwner,
    SourceSpan, TypedDdlCompilation, ValidatedVisibleDdlCandidate,
};

pub const COMPLETION_RANGES_SCHEMA_ID: &str = "inku.completion-ranges.v1";
/// The hole a range becomes when the author changed only its words.
pub const RANGE_WORDS_CHANGED_HOLE_KIND: &str = "range_words_changed";
/// Stands for the range itself in a recorded sentence.
pub const SENTENCE_RANGE_MARK: char = '\u{FFFC}';

/// The record a work keeps of the ranges its completions wrote, in the order
/// they were written.
#[derive(Clone, Debug, Default, Eq, PartialEq, Serialize, Deserialize)]
#[serde(try_from = "RecordWire", into = "RecordWire")]
pub struct CompletionRangeRecord {
    pub ranges: Vec<RecordedRange>,
}

impl CompletionRangeRecord {
    pub fn is_empty(&self) -> bool {
        self.ranges.is_empty()
    }
}

#[derive(Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct RecordWire {
    schema: String,
    ranges: Vec<RecordedRange>,
}

impl From<CompletionRangeRecord> for RecordWire {
    fn from(record: CompletionRangeRecord) -> Self {
        Self {
            schema: COMPLETION_RANGES_SCHEMA_ID.to_owned(),
            ranges: record.ranges,
        }
    }
}

impl TryFrom<RecordWire> for CompletionRangeRecord {
    type Error = String;

    fn try_from(wire: RecordWire) -> Result<Self, Self::Error> {
        if wire.schema != COMPLETION_RANGES_SCHEMA_ID {
            return Err(format!("unknown completion ranges schema {}", wire.schema));
        }
        Ok(Self {
            ranges: wire.ranges,
        })
    }
}

/// One range a completion wrote: the words before the parenthesis as written,
/// the numbers on each axis, and the sentence with the range replaced by
/// [`SENTENCE_RANGE_MARK`].
#[derive(Clone, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct RecordedRange {
    pub words: String,
    #[serde(with = "axis")]
    pub horizontal: [ExactFraction; 2],
    #[serde(with = "axis")]
    pub vertical: [ExactFraction; 2],
    pub sentence: String,
}

impl From<&WrittenRange> for RecordedRange {
    fn from(range: &WrittenRange) -> Self {
        Self {
            words: range.words.clone(),
            horizontal: range.horizontal,
            vertical: range.vertical,
            sentence: range.sentence.clone(),
        }
    }
}

/// A bound as text: a whole number, or a fraction in lowest terms (`2/3`).
pub fn fraction_text(value: ExactFraction) -> String {
    if value.denominator() == 1 {
        value.numerator().to_string()
    } else {
        format!("{}/{}", value.numerator(), value.denominator())
    }
}

fn parse_fraction(text: &str) -> Option<ExactFraction> {
    let digits = |part: &str| {
        (!part.is_empty() && part.bytes().all(|byte| byte.is_ascii_digit()))
            .then(|| part.parse::<u64>().ok())
            .flatten()
    };
    match text.split_once('/') {
        Some((numerator, denominator)) => {
            ExactFraction::new(digits(numerator)?, digits(denominator)?)
        }
        None => ExactFraction::new(digits(text)?, 1),
    }
}

mod axis {
    use serde::de::Error;
    use serde::{Deserialize, Deserializer, Serializer};

    use crate::ExactFraction;

    pub(super) fn serialize<S: Serializer>(
        value: &[ExactFraction; 2],
        serializer: S,
    ) -> Result<S::Ok, S::Error> {
        serializer.collect_seq(value.iter().map(|bound| super::fraction_text(*bound)))
    }

    pub(super) fn deserialize<'de, D: Deserializer<'de>>(
        deserializer: D,
    ) -> Result<[ExactFraction; 2], D::Error> {
        let [start, end] = <[String; 2]>::deserialize(deserializer)?;
        match (super::parse_fraction(&start), super::parse_fraction(&end)) {
            (Some(start), Some(end)) => Ok([start, end]),
            _ => Err(D::Error::custom("a bound is a whole number or a fraction")),
        }
    }
}

/// A numeric range with words, as the instructions have it now.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct WrittenRange {
    /// From the words to the closing parenthesis.
    pub span: SourceSpan,
    /// The author's words before the parenthesis.
    pub words_span: SourceSpan,
    pub words: String,
    pub horizontal: [ExactFraction; 2],
    pub vertical: [ExactFraction; 2],
    /// The sentence the range is in, with the range replaced by [`SENTENCE_RANGE_MARK`].
    pub sentence: String,
}

impl WrittenRange {
    fn same_numbers(&self, recorded: &RecordedRange) -> bool {
        self.horizontal == recorded.horizontal && self.vertical == recorded.vertical
    }

    /// The bounds in region order (horizontal start, vertical start, horizontal
    /// end, vertical end) as exact `(numerator, denominator)` pairs.
    pub fn rational_bounds(&self) -> [(u64, u64); 4] {
        [
            self.horizontal[0],
            self.vertical[0],
            self.horizontal[1],
            self.vertical[1],
        ]
        .map(|bound| (bound.numerator(), bound.denominator()))
    }
}

/// Every numeric range with words in the instructions, in source order. Ranges
/// are read from the clause stream, so a range in a sentence the compiler could
/// not read whole is still found.
pub fn written_ranges(compilation: &TypedDdlCompilation) -> Vec<WrittenRange> {
    let Some(semantic) = &compilation.semantic_document else {
        return Vec::new();
    };
    let source = compilation.document.source();
    let language = compilation.document.language();
    let mut ranges = Vec::new();
    for clause in &semantic
        .instruction_association
        .association
        .clause_stream
        .clauses
    {
        for atom in &clause.atoms {
            let ClauseAtom::FunctionWord {
                geometry_keyword: Some(GeometryKeyword::NumericRange),
                span,
                ..
            } = atom
            else {
                continue;
            };
            let Some(lexeme) =
                crate::numeric_range::numeric_range_at(source, span.start_byte, language)
                    .filter(|lexeme| lexeme.span == *span)
            else {
                continue;
            };
            let (Some(words_span), [Some(x0), Some(y0), Some(x1), Some(y1)]) =
                (lexeme.annotation, lexeme.bounds)
            else {
                continue;
            };
            let (Some(before), Some(after), Some(words)) = (
                source.get(clause.span.start_byte..span.start_byte),
                source.get(span.end_byte..clause.span.end_byte),
                source.get(words_span.start_byte..words_span.end_byte),
            ) else {
                continue;
            };
            ranges.push(WrittenRange {
                span: *span,
                words_span,
                words: words.to_owned(),
                horizontal: [x0, x1],
                vertical: [y0, y1],
                sentence: format!("{before}{SENTENCE_RANGE_MARK}{after}"),
            });
        }
    }
    ranges
}

/// How a range stands against the record.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum CompletionRangeState {
    /// The words and the numbers are as the completion wrote them.
    Completed,
    /// The author changed the numbers; they are drawn as written.
    NumbersChanged,
    /// The author changed only the words; the completion writes the numbers again.
    WordsChanged,
}

impl CompletionRangeState {
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::Completed => "completed",
            Self::NumbersChanged => "numbers_changed",
            Self::WordsChanged => "words_changed",
        }
    }
}

/// A range the record knows, with the recorded range it stands for.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct CompletionRangeMatch {
    pub range: WrittenRange,
    pub state: CompletionRangeState,
    /// The index of the recorded range in the record.
    pub recorded: usize,
}

/// Tie each range to at most one recorded range and each recorded range to at
/// most one range, pass by pass; within a pass ranges go in source order and
/// recorded ranges in record order, and the first that fits is taken:
///
/// 1. the same words and numbers: completed;
/// 2. the same sentence: words changed when the numbers are the same, else
///    numbers changed (the words may have changed too, as the hosts rename a
///    range whose numbers the author retyped);
/// 3. the same numbers: words changed (other words of the sentence changed too);
/// 4. the same words: numbers changed.
///
/// A range left over is not the completion's (the author's or the
/// composition's). A recorded range left over is no longer in the instructions.
pub fn match_completion_ranges(
    ranges: &[WrittenRange],
    record: &CompletionRangeRecord,
) -> Vec<CompletionRangeMatch> {
    type Pass = fn(&WrittenRange, &RecordedRange) -> Option<CompletionRangeState>;
    let passes: [Pass; 4] = [
        |range, recorded| {
            (range.words == recorded.words && range.same_numbers(recorded))
                .then_some(CompletionRangeState::Completed)
        },
        |range, recorded| {
            (range.sentence == recorded.sentence).then_some(if range.same_numbers(recorded) {
                CompletionRangeState::WordsChanged
            } else {
                CompletionRangeState::NumbersChanged
            })
        },
        |range, recorded| {
            range
                .same_numbers(recorded)
                .then_some(CompletionRangeState::WordsChanged)
        },
        |range, recorded| {
            (range.words == recorded.words).then_some(CompletionRangeState::NumbersChanged)
        },
    ];
    let mut taken = vec![false; record.ranges.len()];
    let mut found: Vec<Option<(usize, CompletionRangeState)>> = vec![None; ranges.len()];
    for pass in passes {
        for (index, range) in ranges.iter().enumerate() {
            if found[index].is_some() {
                continue;
            }
            if let Some((recorded, state)) =
                record
                    .ranges
                    .iter()
                    .enumerate()
                    .find_map(|(recorded, entry)| {
                        (!taken[recorded])
                            .then(|| pass(range, entry))
                            .flatten()
                            .map(|state| (recorded, state))
                    })
            {
                taken[recorded] = true;
                found[index] = Some((recorded, state));
            }
        }
    }
    ranges
        .iter()
        .zip(found)
        .filter_map(|(range, found)| {
            found.map(|(recorded, state)| CompletionRangeMatch {
                range: range.clone(),
                state,
                recorded,
            })
        })
        .collect()
}

/// The record kept with instructions just committed: a recorded range no range
/// matches is gone, and a matched one keeps its words and numbers with the
/// sentence it is in now, in record order.
pub fn settle_completion_record(
    compilation: &TypedDdlCompilation,
    record: &CompletionRangeRecord,
) -> CompletionRangeRecord {
    let mut kept = match_completion_ranges(&written_ranges(compilation), record)
        .into_iter()
        .map(|found| {
            let mut entry = record.ranges[found.recorded].clone();
            entry.sentence = found.range.sentence;
            (found.recorded, entry)
        })
        .collect::<Vec<_>>();
    kept.sort_by_key(|(recorded, _)| *recorded);
    CompletionRangeRecord {
        ranges: kept.into_iter().map(|(_, entry)| entry).collect(),
    }
}

/// Lay a record over a compilation. The compilation keeps the record, so a
/// patch's candidate is compiled against the same record, and each range whose
/// words alone changed becomes a `range_words_changed` hole over its source,
/// unless the range overlaps `skip` (the ranges a patch wrote), is not a placed
/// shape's range, or overlaps another hole, conflict or blocking diagnostic.
/// Nothing is laid when a diagnostic stops every execution.
pub fn with_completion_record(
    mut compilation: TypedDdlCompilation,
    record: &CompletionRangeRecord,
    skip: &[SourceSpan],
) -> TypedDdlCompilation {
    let stopped = compilation
        .blocking_diagnostics
        .iter()
        .any(crate::CompilerBlockingDiagnostic::stops_all_execution);
    let holes = if stopped {
        Vec::new()
    } else {
        match_completion_ranges(&written_ranges(&compilation), record)
            .into_iter()
            .filter(|found| found.state == CompletionRangeState::WordsChanged)
            .map(|found| found.range.span)
            .filter(|span| {
                let overlaps = |other: SourceSpan| {
                    other.start_byte < span.end_byte && span.start_byte < other.end_byte
                };
                !skip.iter().any(|other| overlaps(*other))
                    && !compilation.holes.iter().any(|hole| overlaps(hole.span))
                    && !compilation
                        .conflicts
                        .iter()
                        .any(|conflict| conflict.span.is_some_and(overlaps))
                    && !compilation
                        .blocking_diagnostics
                        .iter()
                        .any(|diagnostic| diagnostic.span.is_some_and(overlaps))
                    && compilation.deliveries.iter().any(|delivery| {
                        delivery.kind == SemanticDeliveryKind::Explicit
                            && delivery.identity.owner == SemanticDeliveryOwner::NumericRange
                            && delivery.span == Some(*span)
                    })
            })
            .map(|span| crate::compiler_lock::range_words_changed_hole(&compilation.document, span))
            .collect()
    };
    compilation.holes.extend(holes);
    compilation.completion_record = Some(record.clone());
    compilation
}

/// The record after a patch is approved, to keep once its candidate is
/// committed. A `range_words_changed` hole's recorded range takes the words,
/// numbers and sentence the patch wrote; any other hole adds the ranges with
/// words its patch wrote, except a range its sentence already had with the same
/// words and numbers (a completion keeps such a range as it is).
pub fn record_after_patch(
    base: &TypedDdlCompilation,
    candidate: &ValidatedVisibleDdlCandidate,
    record: &CompletionRangeRecord,
) -> CompletionRangeRecord {
    let within = |inner: SourceSpan, outer: SourceSpan| {
        outer.start_byte <= inner.start_byte && inner.end_byte <= outer.end_byte
    };
    let base_ranges = written_ranges(base);
    let tied = match_completion_ranges(&base_ranges, record);
    let written = written_ranges(&candidate.compilation);
    let mut ranges = record.ranges.clone();
    let mut added = Vec::new();
    for (hole_id, range) in candidate
        .resolved_hole_ids
        .iter()
        .zip(&candidate.resolved_ranges)
    {
        let Some(hole) = base.holes.iter().find(|hole| &hole.id == hole_id) else {
            continue;
        };
        if hole.kind == RANGE_WORDS_CHANGED_HOLE_KIND {
            if let (Some(found), Some(new)) = (
                tied.iter().find(|found| found.range.span == hole.span),
                written.iter().find(|new| new.span == *range),
            ) {
                ranges[found.recorded] = RecordedRange::from(new);
            }
            continue;
        }
        for new in written.iter().filter(|new| within(new.span, *range)) {
            let kept = base_ranges.iter().any(|old| {
                within(old.span, hole.allowed_span)
                    && old.words == new.words
                    && old.horizontal == new.horizontal
                    && old.vertical == new.vertical
            });
            if !kept {
                added.push(RecordedRange::from(new));
            }
        }
    }
    ranges.extend(added);
    CompletionRangeRecord { ranges }
}

/// The record after a completion kept the numbers of ranges whose words alone
/// changed (the new words say the same place): the text does not change, and
/// each such range's recorded range takes its words and sentence as they are
/// now. `spans` are the ranges in `base`.
pub fn record_keeping_numbers(
    base: &TypedDdlCompilation,
    record: &CompletionRangeRecord,
    spans: &[SourceSpan],
) -> CompletionRangeRecord {
    let mut ranges = record.ranges.clone();
    for found in match_completion_ranges(&written_ranges(base), record) {
        if spans.contains(&found.range.span) {
            ranges[found.recorded] = RecordedRange::from(&found.range);
        }
    }
    CompletionRangeRecord { ranges }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_record_reads_and_writes_its_schema_and_fractions() {
        let text = r#"{"schema":"inku.completion-ranges.v1","ranges":[{"words":"右下","horizontal":["2/3","1"],"vertical":["4/6","1"],"sentence":"￼に、円を置く。"}]}"#;
        let record: CompletionRangeRecord = serde_json::from_str(text).expect("a record");
        assert_eq!(record.ranges[0].vertical, record.ranges[0].horizontal);
        assert_eq!(
            serde_json::to_string(&record).expect("JSON"),
            text.replace("4/6", "2/3")
        );
        for refused in [
            text.replace("completion-ranges.v1", "completion-ranges.v2"),
            text.replace("\"2/3\"", "\"0.67\""),
            text.replace("\"2/3\"", "\"2/0\""),
            text.replace(",\"sentence\"", ",\"extra\":1,\"sentence\""),
        ] {
            assert!(serde_json::from_str::<CompletionRangeRecord>(&refused).is_err());
        }
    }
}
