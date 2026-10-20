//! Autonomous refinement (AI自動推敲): moves a host makes on its own, one after
//! another, from a saved work. The author decided (2026-10-20) that a move is a
//! laws move (the laws stage again on the saved work, leaving out the laws its
//! parent used) or a juxtaposition move (a sentence from another of the
//! author's works added after the description). This module holds what the
//! three apps must agree on, and nothing they send, draw or save:
//!
//! - [`next`]: the next try, or why the run stops. A run has `moves` turns. A
//!   turn keeps at most one child, which the next turn starts from, and counts
//!   at most two tries.
//!   - A turn first tries the move its last kept child was not made by. The
//!     first turn starts with the juxtaposition: a laws move's child is held by
//!     its DDL (description-locked) and takes no juxtaposition after it.
//!   - A try that cannot start before anything is sent (`unavailable`) gives
//!     way to the other move in the same turn and is not counted.
//!   - A child that is not visibly different, or an answer that cannot be
//!     used, is followed once by the other move from the same parent, or by
//!     the same move with what it used left out when the other cannot start.
//!   - Two turns in a row that keep nothing stop the run.
//! - [`visible_count`]: stage 1b's visible-difference gate on two drawings.
//! - [`record`]: the `ai_move` a child keeps on its lineage edge.
//!
//! One JSON request with an `action`, one JSON answer
//! (`inku.autonomous-refine.v1`): `next` and `record` here. `measure` (the gate
//! on two SVGs) is answered by the bindings, which can draw; they lay each
//! drawing over white with [`gate_square`] and count it here.

use serde::{Deserialize, Serialize};
use serde_json::{Map, Value, json};

pub const AUTONOMOUS_REFINE_SCHEMA_ID: &str = "inku.autonomous-refine.v1";
pub const AI_MOVE_SCHEMA_ID: &str = "inku.ai-move.v1";

/// The most turns a run may ask for.
pub const MAX_MOVES: u32 = 10;
/// The tries a turn may count.
pub const TRIES_PER_TURN: usize = 2;
/// Turns in a row that keep nothing before the run stops.
pub const EMPTY_TURNS_TO_STOP: usize = 2;
/// The longest direction note, in characters (the laws stage's limit).
pub const NOTE_LIMIT: usize = 1_000;
/// The longest reason a record keeps, in characters.
const REASON_LIMIT: usize = 2_000;
/// The sentences a juxtaposition answer ranks.
const JUXTAPOSITION_CHOICES: usize = 4;
/// What a laws move asks of the cards: the author wants disruptive ideas
/// (2026-10-19), and a card rebuilds its layer.
const LAWS_CARDS: &str = "invite";

/// Stage 1b's gate (2026-10-19): each drawing fitted into a white square of
/// `GATE_SIZE` pixels and averaged into `GATE_GRID`² cells. A cell differs when
/// one of its colour channels moves by `GATE_LEVEL` or more, and the change is
/// visible when a fifth of the cells differ. The level was read from the
/// author's marks on stage 1's 48 cards; the fifth is the author's choice.
pub const GATE_SIZE: u32 = 384;
pub const GATE_GRID: u32 = 48;
pub const GATE_LEVEL: u8 = 12;
pub const GATE_THRESHOLD: f64 = 0.2;
const GATE_SHARE_NUMERATOR: u64 = 1;
const GATE_SHARE_DENOMINATOR: u64 = 5;

/// The two moves.
#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Kind {
    Laws,
    Juxtaposition,
}

impl Kind {
    #[must_use]
    pub const fn other(self) -> Self {
        match self {
            Self::Laws => Self::Juxtaposition,
            Self::Juxtaposition => Self::Laws,
        }
    }

    const fn name(self) -> &'static str {
        match self {
            Self::Laws => "laws",
            Self::Juxtaposition => "juxtaposition",
        }
    }
}

/// How a try ended, as the host reports it.
#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Outcome {
    /// The child passed the gate; the next turn starts from it.
    Kept,
    /// The child was drawn but did not pass the gate.
    NotVisible,
    /// The move could not start for this parent; nothing was sent.
    Unavailable,
    /// The move was sent but gave nothing to draw.
    Failed,
}

impl Outcome {
    const fn name(self) -> &'static str {
        match self {
            Self::Kept => "kept",
            Self::NotVisible => "not_visible",
            Self::Unavailable => "unavailable",
            Self::Failed => "failed",
        }
    }
}

/// One try the host made.
#[derive(Clone, Debug, PartialEq, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Attempt {
    pub kind: Kind,
    pub outcome: Outcome,
    #[serde(default)]
    pub reason: Option<String>,
    #[serde(default)]
    pub share: Option<f64>,
    /// The main law a laws move applied.
    #[serde(default)]
    pub main_law: Option<String>,
    /// The sentence a juxtaposition move added, and its rank among the four.
    #[serde(default)]
    pub sentence: Option<String>,
    #[serde(default)]
    pub rank: Option<usize>,
}

/// The tries of one turn, in order.
#[derive(Clone, Debug, Default, PartialEq, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Turn {
    pub attempts: Vec<Attempt>,
}

/// What the host knows of the work the next try starts from.
#[derive(Clone, Debug, Default, PartialEq, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Parent {
    /// Held by its DDL: drawing it again from its description is refused.
    #[serde(default)]
    pub description_locked: bool,
    /// Drawn straight from a DDL, with no description to add to.
    #[serde(default)]
    pub ddl_work: bool,
    /// The main law and every law of the parent's `laws_basis` answer.
    #[serde(default)]
    pub main_law: Option<String>,
    #[serde(default)]
    pub laws: Vec<String>,
}

/// What [`next`] reads.
#[derive(Clone, Debug, PartialEq, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct NextRequest {
    pub moves: u32,
    pub kinds: Vec<Kind>,
    #[serde(default)]
    pub parent: Parent,
    #[serde(default)]
    pub note: Option<String>,
    #[serde(default)]
    pub turns: Vec<Turn>,
}

/// The laws stage's direction for a laws move (the drawing session's entry,
/// `AuthoringInput::SavedLaws`).
#[derive(Clone, Debug, PartialEq, Serialize)]
pub struct LawsDirection {
    pub exclude: Vec<String>,
    pub cards: &'static str,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub note: Option<String>,
}

/// The next try, or why the run stops.
#[derive(Clone, Debug, PartialEq)]
pub enum Next {
    Laws {
        turn: usize,
        attempt: usize,
        direction: LawsDirection,
    },
    /// `rank` is the place in the answer to use. With `reuse`, it is the next
    /// place in the answer this turn already has; otherwise the host asks for
    /// four, leaving out `exclude`, and uses the first.
    Juxtaposition {
        turn: usize,
        attempt: usize,
        rank: usize,
        reuse: bool,
        exclude: Vec<String>,
    },
    Stop {
        reason: &'static str,
        turns: usize,
        kept: usize,
    },
}

/// Why a request cannot be answered: the host broke the shape or the order.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct Refusal {
    pub reason: &'static str,
    pub detail: String,
}

fn refuse(reason: &'static str, detail: impl Into<String>) -> Refusal {
    Refusal {
        reason,
        detail: detail.into(),
    }
}

/// Where a turn stands.
enum TurnState {
    Kept(Kind),
    Empty,
    Open,
}

fn read_turn(turn: &Turn, kinds: &[Kind]) -> Result<TurnState, Refusal> {
    let out_of_order = |detail: &str| refuse("turns_out_of_order", detail);
    let Some(last) = turn.attempts.last() else {
        return Err(out_of_order("a turn has no tries"));
    };
    let mut unavailable: Vec<Kind> = Vec::new();
    let mut counted = 0;
    for (place, attempt) in turn.attempts.iter().enumerate() {
        if !kinds.contains(&attempt.kind) {
            return Err(out_of_order("a try of a move the run does not use"));
        }
        if unavailable.contains(&attempt.kind) {
            return Err(out_of_order(
                "a try of a move that could not start in this turn",
            ));
        }
        if attempt
            .share
            .is_some_and(|share| !(0.0..=1.0).contains(&share))
        {
            return Err(refuse("share_out_of_range", "a share is between 0 and 1"));
        }
        if attempt
            .rank
            .is_some_and(|rank| !(1..=JUXTAPOSITION_CHOICES).contains(&rank))
        {
            return Err(refuse("rank_out_of_range", "a rank is 1 to 4"));
        }
        match attempt.outcome {
            Outcome::Unavailable => unavailable.push(attempt.kind),
            Outcome::Kept if place + 1 != turn.attempts.len() => {
                return Err(out_of_order("a try after the kept child"));
            }
            Outcome::Kept | Outcome::NotVisible | Outcome::Failed => counted += 1,
        }
        if counted > TRIES_PER_TURN {
            return Err(out_of_order("a turn counts at most two tries"));
        }
    }
    Ok(if last.outcome == Outcome::Kept {
        TurnState::Kept(last.kind)
    } else if counted == TRIES_PER_TURN {
        TurnState::Empty
    } else {
        TurnState::Open
    })
}

fn push_unique(list: &mut Vec<String>, value: &str) {
    let value = value.trim();
    if !value.is_empty() && !list.iter().any(|present| present == value) {
        list.push(value.to_owned());
    }
}

/// The next try of a run, or why it stops. The turns so far are checked for
/// order (each earlier turn finished, at most two counted tries, nothing after
/// a kept child); the parent is the work the next try starts from.
pub fn next(request: &NextRequest) -> Result<Next, Refusal> {
    if !(1..=MAX_MOVES).contains(&request.moves) {
        return Err(refuse(
            "moves_out_of_range",
            format!("moves is 1 to {MAX_MOVES}"),
        ));
    }
    let kinds = &request.kinds;
    if kinds.is_empty() || kinds.len() > 2 || (kinds.len() == 2 && kinds[0] == kinds[1]) {
        return Err(refuse(
            "kinds",
            "kinds names laws, juxtaposition or both, once each",
        ));
    }
    if request
        .note
        .as_ref()
        .is_some_and(|note| note.chars().count() > NOTE_LIMIT)
    {
        return Err(refuse(
            "note_too_long",
            format!("the note is at most {NOTE_LIMIT} characters"),
        ));
    }
    if request.turns.len() > request.moves as usize {
        return Err(refuse("turns_out_of_order", "more turns than moves"));
    }

    let mut last_kept: Option<Kind> = None;
    let mut kept = 0;
    let mut empty_in_a_row = 0;
    let mut finished = 0;
    let mut sentences: Vec<String> = Vec::new();
    let mut open: Option<&Turn> = None;
    for (place, turn) in request.turns.iter().enumerate() {
        let state = read_turn(turn, kinds)?;
        for attempt in &turn.attempts {
            if attempt.kind == Kind::Juxtaposition
                && let Some(sentence) = &attempt.sentence
            {
                push_unique(&mut sentences, sentence);
            }
        }
        match state {
            TurnState::Kept(kind) => {
                last_kept = Some(kind);
                kept += 1;
                empty_in_a_row = 0;
                finished += 1;
            }
            TurnState::Empty => {
                empty_in_a_row += 1;
                finished += 1;
            }
            TurnState::Open if place + 1 == request.turns.len() => open = Some(turn),
            TurnState::Open => {
                return Err(refuse(
                    "turns_out_of_order",
                    "an earlier turn is not finished",
                ));
            }
        }
    }
    let stop = |reason| Next::Stop {
        reason,
        turns: finished,
        kept,
    };
    if open.is_none() {
        if finished == request.moves as usize {
            return Ok(stop("moves_done"));
        }
        if empty_in_a_row >= EMPTY_TURNS_TO_STOP {
            return Ok(stop("stalled"));
        }
    }

    let attempts: &[Attempt] = open.map_or(&[], |turn| turn.attempts.as_slice());
    let parent = &request.parent;
    let blocked = |kind: Kind| {
        !kinds.contains(&kind)
            || (kind == Kind::Juxtaposition && (parent.description_locked || parent.ddl_work))
            || attempts
                .iter()
                .any(|attempt| attempt.kind == kind && attempt.outcome == Outcome::Unavailable)
    };
    let counted: Vec<&Attempt> = attempts
        .iter()
        .filter(|attempt| attempt.outcome != Outcome::Unavailable)
        .collect();
    let kind = match counted.as_slice() {
        [] => {
            let first = last_kept.map_or(Kind::Juxtaposition, Kind::other);
            if !blocked(first) {
                first
            } else if !blocked(first.other()) {
                first.other()
            } else {
                return Ok(stop("nothing_available"));
            }
        }
        [tried] => {
            if !blocked(tried.kind.other()) {
                tried.kind.other()
            } else if !blocked(tried.kind) {
                tried.kind
            } else {
                return Ok(stop("nothing_available"));
            }
        }
        _ => unreachable!("an open turn counts fewer than two tries"),
    };
    let turn = finished + 1;
    let attempt = attempts.len() + 1;
    Ok(match kind {
        Kind::Laws => {
            let mut exclude = Vec::new();
            if let Some(main_law) = &parent.main_law {
                push_unique(&mut exclude, main_law);
            }
            for law in &parent.laws {
                push_unique(&mut exclude, law);
            }
            for tried in &counted {
                if tried.kind == Kind::Laws
                    && let Some(main_law) = &tried.main_law
                {
                    push_unique(&mut exclude, main_law);
                }
            }
            Next::Laws {
                turn,
                attempt,
                direction: LawsDirection {
                    exclude,
                    cards: LAWS_CARDS,
                    note: request
                        .note
                        .as_deref()
                        .map(str::trim)
                        .filter(|note| !note.is_empty())
                        .map(str::to_owned),
                },
            }
        }
        Kind::Juxtaposition => {
            let (rank, reuse) = match counted.last() {
                Some(tried)
                    if tried.kind == Kind::Juxtaposition
                        && tried.outcome == Outcome::NotVisible =>
                {
                    match tried.rank {
                        Some(rank) if rank < JUXTAPOSITION_CHOICES => (rank + 1, true),
                        _ => (1, false),
                    }
                }
                _ => (1, false),
            };
            Next::Juxtaposition {
                turn,
                attempt,
                rank,
                reuse,
                exclude: sentences,
            }
        }
    })
}

fn next_json(next: &Next) -> Value {
    match next {
        Next::Laws {
            turn,
            attempt,
            direction,
        } => json!({"next": {
            "kind": "laws", "turn": turn, "attempt": attempt, "direction": direction,
        }}),
        Next::Juxtaposition {
            turn,
            attempt,
            rank,
            reuse,
            exclude,
        } => json!({"next": {
            "kind": "juxtaposition", "turn": turn, "attempt": attempt,
            "rank": rank, "reuse": reuse, "exclude": exclude,
        }}),
        Next::Stop {
            reason,
            turns,
            kept,
        } => json!({"stop": {"reason": reason, "turns": turns, "kept": kept}}),
    }
}

// ---------------------------------------------------------------------------
// The visible-difference gate
// ---------------------------------------------------------------------------

/// What stage 1b's gate counts on two drawings.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct GateCount {
    pub different: u32,
    pub cells: u32,
}

impl GateCount {
    /// The share of cells that differ, to four places.
    #[must_use]
    pub fn share(self) -> f64 {
        (f64::from(self.different) / f64::from(self.cells) * 10_000.0).round() / 10_000.0
    }

    /// Whether a fifth of the cells differ.
    #[must_use]
    pub const fn passes(self) -> bool {
        self.different as u64 * GATE_SHARE_DENOMINATOR >= self.cells as u64 * GATE_SHARE_NUMERATOR
    }
}

/// A drawing as the gate reads it: premultiplied RGBA8 (`stride` bytes a row)
/// laid over white and centred in a white square of `side` pixels, as RGB8.
/// `None` when the drawing does not fit the square or the buffer is short.
#[must_use]
pub fn gate_square(
    width: u32,
    height: u32,
    stride: u32,
    pixels: &[u8],
    side: u32,
) -> Option<Vec<u8>> {
    let (width, height, stride, side) = (
        width as usize,
        height as usize,
        stride as usize,
        side as usize,
    );
    if width > side || height > side || stride < width * 4 {
        return None;
    }
    if height > 0 && pixels.len() < stride * (height - 1) + width * 4 {
        return None;
    }
    let mut square = vec![u8::MAX; side * side * 3];
    let (left, top) = ((side - width) / 2, (side - height) / 2);
    for y in 0..height {
        for x in 0..width {
            let from = y * stride + x * 4;
            let to = ((top + y) * side + left + x) * 3;
            let uncovered = u8::MAX - pixels[from + 3];
            for channel in 0..3 {
                // A premultiplied colour over white: c + (255 − α).
                square[to + channel] = pixels[from + channel].saturating_add(uncovered);
            }
        }
    }
    Some(square)
}

/// Stage 1b's gate on two opaque RGB8 squares of `side` pixels (row-major,
/// three bytes a pixel, `side` a multiple of `GATE_GRID`). Each square is
/// averaged into `GATE_GRID`² cells, a cell's mean rounded half up, and a cell
/// differs when one channel's means are `GATE_LEVEL` or more apart. `None` when
/// the buffers do not have that shape.
#[must_use]
pub fn visible_count(before: &[u8], after: &[u8], side: u32) -> Option<GateCount> {
    if side == 0 || !side.is_multiple_of(GATE_GRID) {
        return None;
    }
    let side = side as usize;
    let expected = side * side * 3;
    if before.len() != expected || after.len() != expected {
        return None;
    }
    let grid = GATE_GRID as usize;
    let block = side / grid;
    let area = u32::try_from(block * block).ok()?;
    let mean = |sum: u32| (sum + area / 2) / area;
    let mut different = 0;
    for cell_y in 0..grid {
        for cell_x in 0..grid {
            let mut sums = [[0_u32; 3]; 2];
            for y in cell_y * block..(cell_y + 1) * block {
                for x in cell_x * block..(cell_x + 1) * block {
                    let at = (y * side + x) * 3;
                    for channel in 0..3 {
                        sums[0][channel] += u32::from(before[at + channel]);
                        sums[1][channel] += u32::from(after[at + channel]);
                    }
                }
            }
            if (0..3).any(|channel| {
                mean(sums[0][channel]).abs_diff(mean(sums[1][channel])) >= u32::from(GATE_LEVEL)
            }) {
                different += 1;
            }
        }
    }
    Some(GateCount {
        different,
        cells: GATE_GRID * GATE_GRID,
    })
}

/// The answer to `measure`, from the bindings that drew the two SVGs.
#[must_use]
pub fn measure_answer(count: GateCount) -> Vec<u8> {
    envelope(Ok(json!({
        "share": count.share(),
        "passes": count.passes(),
        "different": count.different,
        "cells": count.cells,
        "level": GATE_LEVEL,
        "threshold": GATE_THRESHOLD,
        "grid": GATE_GRID,
        "size": GATE_SIZE,
    })))
}

/// The refusal of `measure` when a drawing cannot be made.
#[must_use]
pub fn measure_refusal(reason: &'static str, detail: String) -> Vec<u8> {
    envelope(Err(Refusal { reason, detail }))
}

// ---------------------------------------------------------------------------
// The record a child keeps
// ---------------------------------------------------------------------------

/// What a laws move chose, as the laws stage answered (`laws_basis`).
#[derive(Clone, Debug, PartialEq, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct LawsMove {
    pub main_law: String,
    pub main_layer: Value,
    pub laws: Value,
    pub reason: String,
    #[serde(default)]
    pub excluded: Vec<String>,
    pub cards: String,
}

/// What a juxtaposition move added (the choice the core's check gave).
#[derive(Clone, Debug, PartialEq, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct JuxtapositionMove {
    pub sentence: String,
    pub history_ids: Vec<String>,
    pub rank: usize,
    pub position: f64,
    pub reason: String,
    pub candidates: usize,
}

/// What [`record`] reads: one drawn child of a run.
#[derive(Clone, Debug, PartialEq, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct RecordRequest {
    pub run: String,
    pub turn: usize,
    pub moves: u32,
    pub attempt: usize,
    pub kind: Kind,
    pub model: String,
    pub outcome: Outcome,
    pub share: f64,
    #[serde(default)]
    pub note: Option<String>,
    #[serde(default)]
    pub laws: Option<LawsMove>,
    #[serde(default)]
    pub juxtaposition: Option<JuxtapositionMove>,
}

fn clipped(text: &str, limit: usize) -> String {
    text.trim().chars().take(limit).collect()
}

/// The lineage metadata of a drawn child: `ai_move`, and for a juxtaposition
/// the `juxtaposition` record the description edit writes (the host reads the
/// sentences a lineage added from it, and leaves them out next time).
pub fn record(request: &RecordRequest) -> Result<Map<String, Value>, Refusal> {
    if request.run.trim().is_empty() || request.model.trim().is_empty() {
        return Err(refuse("record_shape", "a record names its run and model"));
    }
    if !(1..=MAX_MOVES).contains(&request.moves)
        || !(1..=request.moves as usize).contains(&request.turn)
        || !(1..=TRIES_PER_TURN + 1).contains(&request.attempt)
    {
        return Err(refuse(
            "record_shape",
            "turn is 1 to moves (at most 10), attempt 1 to 3",
        ));
    }
    if !(0.0..=1.0).contains(&request.share) {
        return Err(refuse("share_out_of_range", "a share is between 0 and 1"));
    }
    let passes = request.share >= GATE_THRESHOLD;
    match (request.outcome, passes) {
        (Outcome::Kept, true) | (Outcome::NotVisible, false) => {}
        (Outcome::Kept | Outcome::NotVisible, _) => {
            return Err(refuse(
                "outcome_disagrees_with_share",
                "a kept child passes the gate and a not-visible one does not",
            ));
        }
        (Outcome::Unavailable | Outcome::Failed, _) => {
            return Err(refuse(
                "record_shape",
                "a record is for a drawn child: kept or not_visible",
            ));
        }
    }
    let note = request
        .note
        .as_deref()
        .map(str::trim)
        .filter(|note| !note.is_empty());
    if note.is_some_and(|note| note.chars().count() > NOTE_LIMIT) {
        return Err(refuse(
            "note_too_long",
            format!("the note is at most {NOTE_LIMIT} characters"),
        ));
    }

    let mut ai_move = Map::new();
    ai_move.insert("schema".to_owned(), json!(AI_MOVE_SCHEMA_ID));
    ai_move.insert("run".to_owned(), json!(request.run.trim()));
    ai_move.insert("turn".to_owned(), json!(request.turn));
    ai_move.insert("moves".to_owned(), json!(request.moves));
    ai_move.insert("attempt".to_owned(), json!(request.attempt));
    ai_move.insert("kind".to_owned(), json!(request.kind.name()));
    ai_move.insert("model".to_owned(), json!(request.model.trim()));
    ai_move.insert("outcome".to_owned(), json!(request.outcome.name()));
    ai_move.insert(
        "visible".to_owned(),
        json!({
            "share": (request.share * 10_000.0).round() / 10_000.0,
            "passes": passes,
            "level": GATE_LEVEL,
            "threshold": GATE_THRESHOLD,
            "grid": GATE_GRID,
            "size": GATE_SIZE,
        }),
    );
    if let Some(note) = note {
        ai_move.insert("note".to_owned(), json!(note));
    }
    let mut metadata = Map::new();
    match (request.kind, &request.laws, &request.juxtaposition) {
        (Kind::Laws, Some(laws), None) => {
            if laws.main_law.trim().is_empty() {
                return Err(refuse("record_shape", "a laws move names its main law"));
            }
            ai_move.insert(
                "laws".to_owned(),
                json!({
                    "main_law": laws.main_law.trim(),
                    "main_layer": laws.main_layer,
                    "laws": laws.laws,
                    "reason": clipped(&laws.reason, REASON_LIMIT),
                    "excluded": laws.excluded,
                    "cards": laws.cards,
                }),
            );
        }
        (Kind::Juxtaposition, None, Some(added)) => {
            if added.sentence.trim().is_empty()
                || added.history_ids.is_empty()
                || !(1..=JUXTAPOSITION_CHOICES).contains(&added.rank)
                || !(0.0..=1.0).contains(&added.position)
                || added.candidates < JUXTAPOSITION_CHOICES
            {
                return Err(refuse(
                    "record_shape",
                    "a juxtaposition names its sentence, works, rank 1 to 4, position 0 to 1 and at least four candidates",
                ));
            }
            let reason = clipped(&added.reason, REASON_LIMIT);
            ai_move.insert(
                "juxtaposition".to_owned(),
                json!({
                    "sentence": added.sentence.trim(),
                    "history_ids": added.history_ids,
                    "rank": added.rank,
                    "position": added.position,
                    "reason": reason,
                    "candidates": added.candidates,
                }),
            );
            metadata.insert(
                "juxtaposition".to_owned(),
                json!({
                    "sentence": added.sentence.trim(),
                    "history_ids": added.history_ids,
                    "rank": added.rank,
                    "reason": reason,
                    "position": added.position,
                    "candidates": added.candidates,
                    "model": request.model.trim(),
                }),
            );
        }
        _ => {
            return Err(refuse(
                "record_shape",
                "a record carries the block of its own move and no other",
            ));
        }
    }
    metadata.insert("ai_move".to_owned(), Value::Object(ai_move));
    Ok(metadata)
}

// ---------------------------------------------------------------------------
// The JSON boundary
// ---------------------------------------------------------------------------

#[derive(Deserialize)]
#[serde(tag = "action", rename_all = "snake_case", deny_unknown_fields)]
enum Request {
    Next(NextRequest),
    Record(Box<RecordRequest>),
}

fn answer(request: Request) -> Result<Value, Refusal> {
    match request {
        Request::Next(request) => next(&request).map(|next| next_json(&next)),
        Request::Record(request) => record(&request).map(|metadata| json!({"metadata": metadata})),
    }
}

fn envelope(answer: Result<Value, Refusal>) -> Vec<u8> {
    let mut body = Map::new();
    match answer {
        Ok(Value::Object(fields)) => {
            body.insert("outcome".to_owned(), json!("ok"));
            body.extend(fields);
        }
        Ok(_) => return br#"{"error":"internal"}"#.to_vec(),
        Err(refusal) => {
            body.insert("outcome".to_owned(), json!("refused"));
            body.insert("reason".to_owned(), json!(refusal.reason));
            body.insert("detail".to_owned(), json!(refusal.detail));
        }
    }
    body.insert("schema".to_owned(), json!(AUTONOMOUS_REFINE_SCHEMA_ID));
    serde_json::to_vec(&Value::Object(body)).unwrap_or_else(|_| br#"{"error":"internal"}"#.to_vec())
}

/// JSON in, JSON out, for the hosts' bindings (`next` and `record`). An answer
/// is `{"schema", "outcome": "ok", ...}` or `{"schema", "outcome": "refused",
/// "reason", "detail"}`; a request that cannot be read answers
/// `{"error": "invalid_request"}`.
#[must_use]
pub fn autonomous_refine_json(input: &[u8]) -> Vec<u8> {
    let Ok(request) = serde_json::from_slice::<Request>(input) else {
        return br#"{"error":"invalid_request"}"#.to_vec();
    };
    envelope(answer(request))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn cases() -> Value {
        serde_json::from_str(include_str!(
            "../../../../server/tests/data/autonomous-refine-cases.json"
        ))
        .expect("the shared autonomous refinement cases")
    }

    fn ask(request: &Value) -> Value {
        serde_json::from_slice(&autonomous_refine_json(
            &serde_json::to_vec(request).unwrap(),
        ))
        .unwrap()
    }

    #[test]
    fn every_shared_case_answers_as_the_table_says() {
        let table = cases();
        let mut count = 0;
        for group in ["next", "record", "invalid"] {
            for row in table[group].as_array().unwrap() {
                assert_eq!(
                    ask(&row["request"]),
                    row["answer"],
                    "{group}: {}",
                    row["why"]
                );
                count += 1;
            }
        }
        // A refusal is matched by its reason; its detail is this module's wording.
        for row in table["refused"].as_array().unwrap() {
            let mut answer = ask(&row["request"]);
            let detail = answer.as_object_mut().unwrap().remove("detail");
            assert!(
                detail
                    .as_ref()
                    .and_then(Value::as_str)
                    .is_some_and(|text| !text.is_empty()),
                "refused: {}",
                row["why"]
            );
            assert_eq!(answer, row["answer"], "refused: {}", row["why"]);
            count += 1;
        }
        assert!(count >= 30, "the table holds {count} cases");
    }

    #[derive(Clone, Copy)]
    struct Walk {
        calls: usize,
        paths: usize,
    }

    /// Every outcome a host can report, after every try the run asks for: the
    /// run stops within its turns and counts at most two tries a turn. A kept
    /// laws child is held by its DDL, as the product holds it.
    fn walk(request: &mut NextRequest, walk_so_far: &mut Walk) {
        walk_so_far.calls += 1;
        let next = next(request)
            .unwrap_or_else(|refusal| panic!("refused {refusal:?} after {:?}", request.turns));
        let (kind, turn) = match next {
            Next::Stop { turns, kept, .. } => {
                assert!(turns <= request.moves as usize);
                assert!(kept <= turns);
                let counted: usize = request
                    .turns
                    .iter()
                    .map(|turn| {
                        turn.attempts
                            .iter()
                            .filter(|attempt| attempt.outcome != Outcome::Unavailable)
                            .count()
                    })
                    .sum();
                assert!(counted <= TRIES_PER_TURN * request.moves as usize);
                walk_so_far.paths += 1;
                return;
            }
            Next::Laws { turn, .. } => (Kind::Laws, turn),
            Next::Juxtaposition { turn, .. } => (Kind::Juxtaposition, turn),
        };
        assert!(turn <= request.moves as usize, "a try past the last turn");
        for outcome in [
            Outcome::Kept,
            Outcome::NotVisible,
            Outcome::Unavailable,
            Outcome::Failed,
        ] {
            let mut tried = request.clone();
            if tried.turns.len() < turn {
                tried.turns.push(Turn::default());
            }
            tried.turns[turn - 1].attempts.push(Attempt {
                kind,
                outcome,
                reason: None,
                share: None,
                main_law: (kind == Kind::Laws).then(|| format!("L{turn}")),
                sentence: (kind == Kind::Juxtaposition).then(|| format!("S{turn}")),
                rank: (kind == Kind::Juxtaposition).then_some(1),
            });
            if outcome == Outcome::Kept {
                tried.parent.description_locked = kind == Kind::Laws;
            }
            walk(&mut tried, walk_so_far);
        }
    }

    /// The plan's prediction R1 (one to six moves); slow without optimisation:
    /// `cargo test --release -p inku-pipeline every_run_of_one_to_six -- --ignored --nocapture`.
    #[test]
    #[ignore = "measured once for the plan's R1; the ordinary run walks four moves"]
    fn every_run_of_one_to_six_moves_stops_within_its_turns() {
        for moves in 1..=6 {
            let started = std::time::Instant::now();
            let mut counted = Walk { calls: 0, paths: 0 };
            for kinds in [
                vec![Kind::Laws, Kind::Juxtaposition],
                vec![Kind::Laws],
                vec![Kind::Juxtaposition],
            ] {
                let mut request = NextRequest {
                    moves,
                    kinds,
                    parent: Parent::default(),
                    note: None,
                    turns: Vec::new(),
                };
                walk(&mut request, &mut counted);
            }
            println!(
                "moves {moves}: {} runs, {} answers, {:.2?}",
                counted.paths,
                counted.calls,
                started.elapsed()
            );
        }
    }

    #[test]
    fn every_run_of_one_to_four_moves_stops_within_its_turns() {
        for moves in 1..=4 {
            for kinds in [
                vec![Kind::Laws, Kind::Juxtaposition],
                vec![Kind::Laws],
                vec![Kind::Juxtaposition],
            ] {
                let mut request = NextRequest {
                    moves,
                    kinds,
                    parent: Parent::default(),
                    note: None,
                    turns: Vec::new(),
                };
                let mut counted = Walk { calls: 0, paths: 0 };
                walk(&mut request, &mut counted);
                assert!(counted.paths > 0);
            }
        }
    }

    #[test]
    fn the_gate_counts_the_cells_a_drawing_moves() {
        let side = GATE_SIZE as usize;
        let white = vec![u8::MAX; side * side * 3];
        assert_eq!(
            visible_count(&white, &white, GATE_SIZE),
            Some(GateCount {
                different: 0,
                cells: 2304
            })
        );
        // The top 80 rows turned black: ten whole rows of cells.
        let mut after = white.clone();
        for y in 0..80 {
            for x in 0..side {
                let at = (y * side + x) * 3;
                after[at..at + 3].copy_from_slice(&[0, 0, 0]);
            }
        }
        let count = visible_count(&white, &after, GATE_SIZE).unwrap();
        assert_eq!(count.different, 10 * 48);
        assert_eq!(count.share(), 0.2083);
        assert!(count.passes());
        // A change of 11 in one channel is below the level; 12 reaches it.
        let mut faint = white.clone();
        for value in faint.iter_mut().step_by(3) {
            *value = u8::MAX - 11;
        }
        assert_eq!(
            visible_count(&white, &faint, GATE_SIZE).unwrap().different,
            0
        );
        for value in faint.iter_mut().step_by(3) {
            *value = u8::MAX - 12;
        }
        assert_eq!(
            visible_count(&white, &faint, GATE_SIZE).unwrap().different,
            2304
        );
        assert_eq!(visible_count(&white, &white[1..], GATE_SIZE), None);
        assert_eq!(visible_count(&white, &white, 383), None);
    }

    #[test]
    fn the_gate_passes_from_a_fifth_of_the_cells() {
        assert!(
            !GateCount {
                different: 460,
                cells: 2304
            }
            .passes()
        );
        assert!(
            GateCount {
                different: 461,
                cells: 2304
            }
            .passes()
        );
        assert_eq!(
            GateCount {
                different: 460,
                cells: 2304
            }
            .share(),
            0.1997
        );
        assert_eq!(
            GateCount {
                different: 461,
                cells: 2304
            }
            .share(),
            0.2001
        );
    }

    #[test]
    fn a_drawing_lies_over_white_in_the_middle_of_the_square() {
        // Two pixels: opaque red, and black at half cover (premultiplied).
        let pixels = [255, 0, 0, 255, 0, 0, 0, 128];
        let square = gate_square(2, 1, 8, &pixels, 4).unwrap();
        assert_eq!(square.len(), 4 * 4 * 3);
        // Row 1 (the drawing's one row is centred at top 1), columns 1 and 2.
        assert_eq!(&square[(4 + 1) * 3..(4 + 1) * 3 + 3], &[255, 0, 0]);
        assert_eq!(&square[(4 + 2) * 3..(4 + 2) * 3 + 3], &[127, 127, 127]);
        assert_eq!(&square[0..3], &[255, 255, 255]);
        assert_eq!(gate_square(5, 1, 20, &[0; 20], 4), None);
        assert_eq!(gate_square(2, 2, 8, &pixels, 4), None);
    }
}
