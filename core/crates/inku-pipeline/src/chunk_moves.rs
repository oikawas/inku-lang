//! Titled chunks, their boxes, and author-directed placement.
//! JSON actions `units`, `boxes`, and `place` use `inku.chunk-moves.v1`.

use std::collections::BTreeMap;

use inku_ddl::{
    MacroDefinition, ResolvedInstructionLanguage, ddl_title_lines, ddl_title_name,
    print_ddl_titles, split_ddl_titles,
};
use inku_score::CanvasRatio;
use serde::{Deserialize, Serialize};
use serde_json::{Map, Value, json};

use crate::description_composition::{
    CompositionThing, GOLDEN, composed_thing_titles, titled_composed_source,
};
use crate::description_laws::{
    Numbers, center, inside, moved_values, parse_with_definitions, rewritten, scene_word,
    sentence_box, union,
};
use crate::image_ddl::{ImageDdlProblem, check_image_document};
use crate::machine::PipelineConfig;
use crate::recompose;

pub const CHUNK_MOVES_SCHEMA_ID: &str = "inku.chunk-moves.v1";

/// Where `place` moves a chunk: a point, or a line where one coordinate is
/// kept (`None`).
pub(crate) const AT: [(&str, Option<f64>, Option<f64>); 10] = [
    ("golden_ul", Some(GOLDEN.0), Some(GOLDEN.0)),
    ("golden_ur", Some(GOLDEN.1), Some(GOLDEN.0)),
    ("golden_ll", Some(GOLDEN.0), Some(GOLDEN.1)),
    ("golden_lr", Some(GOLDEN.1), Some(GOLDEN.1)),
    ("third_left", Some(1.0 / 3.0), None),
    ("third_right", Some(2.0 / 3.0), None),
    ("third_top", None, Some(1.0 / 3.0)),
    ("third_bottom", None, Some(2.0 / 3.0)),
    ("center", Some(0.5), Some(0.5)),
    ("keep", None, None),
];
// ---------------------------------------------------------------------------
// The titled DDL
// ---------------------------------------------------------------------------

/// A titled DDL as lines: every sentence, the ratio declaration and the
/// sentences of no chunk too, with the chunk it belongs to.
#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Doc {
    pub lines: Vec<String>,
    pub chunks: Vec<Option<String>>,
}

impl Doc {
    #[must_use]
    pub fn of(source: &str) -> Self {
        let (lines, chunks) = split_ddl_titles(source);
        Self { lines, chunks }
    }

    #[must_use]
    pub fn titled(&self, language: ResolvedInstructionLanguage) -> String {
        let lines: Vec<&str> = self.lines.iter().map(String::as_str).collect();
        let chunks: Vec<Option<&str>> = self.chunks.iter().map(Option::as_deref).collect();
        print_ddl_titles(&lines, &chunks, language)
    }

    /// The chunks in the order their first sentences come.
    #[must_use]
    pub fn units(&self) -> Vec<String> {
        let mut order: Vec<String> = Vec::new();
        for chunk in self.chunks.iter().flatten() {
            if !order.contains(chunk) {
                order.push(chunk.clone());
            }
        }
        order
    }

    fn members(&self, chunk: &str) -> Vec<usize> {
        self.chunks
            .iter()
            .enumerate()
            .filter(|(_, owner)| owner.as_deref() == Some(chunk))
            .map(|(index, _)| index)
            .collect()
    }
}

/// The work's language and its canvas in short-edge units, which every
/// reading and rewriting of numbers needs.
#[derive(Clone, Copy, Debug)]
struct Paper<'a> {
    language: ResolvedInstructionLanguage,
    units: [f64; 2],
    definitions: &'a [MacroDefinition],
}

impl Paper<'_> {
    fn say(self, ja: impl Into<String>, en: impl Into<String>) -> String {
        match self.language {
            ResolvedInstructionLanguage::Ja => ja.into(),
            ResolvedInstructionLanguage::En => en.into(),
        }
    }

    fn numbers(self, line: &str) -> Result<Numbers, String> {
        parse_with_definitions(line, self.language, self.definitions).ok_or_else(|| {
            let head: String = line.chars().take(40).collect();
            self.say(
                format!("数の位置の無い文: {head}"),
                format!("a sentence with no numeric place: {head}"),
            )
        })
    }

    fn box_of<S: AsRef<str>>(self, lines: &[S]) -> Result<[f64; 4], String> {
        let boxes = lines
            .iter()
            .map(|line| {
                self.numbers(line.as_ref())
                    .map(|numbers| sentence_box(&numbers, self.units))
            })
            .collect::<Result<Vec<_>, _>>()?;
        union(boxes).ok_or_else(|| self.say("文が無い", "no sentence"))
    }

    /// Whether a moved sentence's marks stay on the canvas. One the parser
    /// cannot read (a number below zero) does not: the prototype read it and
    /// found it off the canvas.
    fn fits(self, line: &str) -> bool {
        parse_with_definitions(line, self.language, self.definitions)
            .is_some_and(|numbers| inside(sentence_box(&numbers, self.units)))
    }

    /// The sentence moved by `(dx, dy)` (canvas fractions) and scaled by `s`
    /// about a point: only its numbers change.
    fn transformed(
        self,
        line: &str,
        dx: f64,
        dy: f64,
        s: f64,
        about: [f64; 2],
    ) -> Result<String, String> {
        let numbers = self.numbers(line)?;
        let values = moved_values(&numbers, dx, dy, s, about);
        let scale = ((s - 1.0).abs() > f64::EPSILON).then_some(s);
        Ok(rewritten(line, &numbers, Some(&values), scale))
    }
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Composition {
    pub owners: Vec<u64>,
    pub things: Vec<CompositionThing>,
}

/// Why a request cannot be answered.
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

fn paper_of(config: &PipelineConfig) -> Result<(Paper<'_>, CanvasRatio), Refusal> {
    let format = inku_score::lookup_canvas_format(config.compiler.host.canvas_format_id())
        .map_err(|_| refuse("paper", "the configuration names no known paper"))?;
    let ratio = CanvasRatio::reduced(format.width_units, format.height_units)
        .ok_or_else(|| refuse("paper", "the paper has no ratio"))?;
    let short = f64::from(ratio.width_units.min(ratio.height_units));
    Ok((
        Paper {
            language: config.language,
            units: [
                f64::from(ratio.width_units) / short,
                f64::from(ratio.height_units) / short,
            ],
            definitions: &config.definitions,
        },
        ratio,
    ))
}

/// The parent's DDL with its titles: as it is when it has title lines, else
/// titled from its composition record.
#[must_use]
pub fn titled_source(
    ddl: &str,
    composition: Option<&Composition>,
    language: ResolvedInstructionLanguage,
) -> String {
    if !ddl_title_lines(ddl).is_empty() {
        return ddl.to_owned();
    }
    composition.map_or_else(
        || ddl.to_owned(),
        |composition| {
            titled_composed_source(ddl, &composition.owners, &composition.things, language)
        },
    )
}

/// One chunk of a work, for a host to tie a composition record's thing, the
/// DDL's title and the picture together.
#[derive(Clone, Debug, PartialEq, Serialize)]
pub struct UnitBox {
    pub title: String,
    /// The record's thing whose title is this chunk's, when there is one.
    pub thing: Option<u64>,
    /// The chunk's lines in the DDL as the host gave it, from 0, its title
    /// line among them when it has one.
    pub lines: Vec<usize>,
    pub sentences: usize,
    /// The chunk's sentences with no numeric place the parser can read.
    pub unplaced: usize,
    /// The union of the boxes of the sentences that have one, as canvas
    /// fractions `[x0, y0, x1, y1]`; `None` when no sentence has one.
    #[serde(rename = "box")]
    pub area: Option<[f64; 4]>,
    /// The named place nearest the center of the box, when there is one.
    pub at: Option<String>,
    /// Each of the nine places' outcome for this chunk (`place_at`): `ok`,
    /// `clamped` or the reason it is refused (step 3).
    pub places: BTreeMap<String, String>,
}

/// A work's chunks with their things and boxes. Unlike `Paper::box_of`, a
/// sentence with no readable place (a plugin word alone) is counted and left
/// out instead of refusing the chunk.
pub fn boxes(
    config: &PipelineConfig,
    ddl: &str,
    composition: Option<&Composition>,
) -> Result<Vec<UnitBox>, Refusal> {
    let (paper, _) = paper_of(config)?;
    let doc = Doc::of(&titled_source(ddl, composition, paper.language));
    let titles = composition.map(|composition| {
        composed_thing_titles(&composition.owners, &composition.things, paper.language)
    });
    let owners = source_line_chunks(ddl, composition, titles.as_ref());
    Ok(doc
        .units()
        .into_iter()
        .map(|title| {
            let members = doc.members(&title);
            let placed: Vec<[f64; 4]> = members
                .iter()
                .filter_map(|index| {
                    parse_with_definitions(&doc.lines[*index], paper.language, paper.definitions)
                })
                .map(|numbers| sentence_box(&numbers, paper.units))
                .collect();
            let thing = titles.as_ref().and_then(|titles| {
                titles
                    .iter()
                    .find(|(_, name)| **name == title)
                    .map(|(number, _)| *number)
            });
            let lines = owners
                .iter()
                .enumerate()
                .filter(|(_, owner)| owner.as_deref() == Some(title.as_str()))
                .map(|(index, _)| index)
                .collect();
            let unplaced = members.len() - placed.len();
            let area = union(placed);
            UnitBox {
                thing,
                lines,
                sentences: members.len(),
                unplaced,
                area,
                at: area.and_then(|bounds| place_of(center(bounds))),
                places: places_of(&doc, paper, &title),
                title,
            }
        })
        .collect())
}

/// The places an author can move a chunk to (step 3, 2026-11-13): `AT`
/// without `keep`.
pub const PLACES: [&str; 9] = [
    "golden_ul",
    "golden_ur",
    "golden_ll",
    "golden_lr",
    "third_left",
    "third_right",
    "third_top",
    "third_bottom",
    "center",
];
/// How near a chunk's center is to a place for the place to be its own
/// (canvas fractions).
const AT_FROM_NEAR: f64 = 0.02;

/// What `place_at` did: the chunk, where it was and where it went.
#[derive(Clone, Debug, PartialEq, Serialize)]
pub struct Placed {
    pub title: String,
    /// The record's thing whose title is this chunk's, when there is one.
    pub thing: Option<u64>,
    pub at: String,
    /// The place the chunk's center was at (within 0.02), if any.
    pub at_from: Option<String>,
    pub from: [f64; 2],
    pub to: [f64; 2],
    /// Whether the chunk stopped short of the place to stay on the canvas.
    pub clamped: bool,
}

/// The place a center is at: a point (both coordinates within 0.02) before a
/// line (its one coordinate within 0.02).
fn place_of(center: [f64; 2]) -> Option<String> {
    let near =
        |value: Option<f64>, at: f64| value.is_none_or(|place| (place - at).abs() <= AT_FROM_NEAR);
    let mut found = None;
    for (name, x, y) in AT.iter().filter(|(name, _, _)| PLACES.contains(name)) {
        if near(*x, center[0]) && near(*y, center[1]) {
            if x.is_some() && y.is_some() {
                return Some((*name).to_owned());
            }
            found.get_or_insert_with(|| (*name).to_owned());
        }
    }
    found
}

/// Problems in the child whose lines were not already problematic in the parent.
fn new_problems(config: &PipelineConfig, parent: &Doc, child: &Doc) -> Vec<ImageDdlProblem> {
    let problems = |doc: &Doc| {
        recompose::document(
            &doc.titled(config.language),
            config.language,
            &config.definitions,
        )
        .and_then(|document| {
            check_image_document(&document, &config.definitions, &config.compiler).ok()
        })
        .map(|check| check.problems)
    };
    let Some(found) = problems(child).filter(|found| !found.is_empty()) else {
        return Vec::new();
    };
    let known: Vec<String> = problems(parent)
        .unwrap_or_default()
        .into_iter()
        .map(|problem| problem.line)
        .collect();
    found
        .into_iter()
        .filter(|problem| !known.contains(&problem.line))
        .collect()
}

/// Why a child with such lines was not drawn: how many lines (a line may
/// have more than one finding).
fn undrawn(paper: Paper, problems: &[ImageDdlProblem]) -> String {
    let mut lines: Vec<&str> = problems
        .iter()
        .map(|problem| problem.line.as_str())
        .collect();
    lines.sort_unstable();
    lines.dedup();
    paper.say(
        format!("描かれない行が出た（{} 行）", lines.len()),
        format!("lines that would not be drawn ({})", lines.len()),
    )
}

/// Move one chunk without resizing it; refuse chunks larger than the canvas.
fn move_chunk(
    doc: &Doc,
    paper: Paper,
    chunk: &str,
    at: &str,
) -> Result<(Doc, [f64; 2], [f64; 2], bool), Refusal> {
    let Some((_, to_x, to_y)) = AT
        .iter()
        .find(|(name, _, _)| *name == at && PLACES.contains(name))
        .copied()
    else {
        return Err(refuse("unknown_place", at.to_owned()));
    };
    let indexes = doc.members(chunk);
    if indexes.is_empty() {
        return Err(refuse("no_chunk", chunk.to_owned()));
    }
    let lines: Vec<String> = indexes
        .iter()
        .map(|index| doc.lines[*index].clone())
        .collect();
    if lines
        .iter()
        .any(|line| scene_word(line, paper.language, paper.definitions))
    {
        return Err(refuse(
            "scene_word",
            paper.say("情景の語のまとまり", "a chunk of a scene word"),
        ));
    }
    let b = paper
        .box_of(&lines)
        .map_err(|detail| refuse("no_numeric_place", detail))?;
    let (half_w, half_h) = ((b[2] - b[0]) / 2.0, (b[3] - b[1]) / 2.0);
    if half_w * 2.0 > 1.0 || half_h * 2.0 > 1.0 {
        return Err(refuse(
            "too_large",
            paper.say(
                "画面より大きい物は動かせない",
                "a thing larger than the canvas cannot move",
            ),
        ));
    }
    let c = center(b);
    let (want_x, want_y) = (to_x.unwrap_or(c[0]), to_y.unwrap_or(c[1]));
    let tx = want_x.max(half_w).min(1.0 - half_w);
    let ty = want_y.max(half_h).min(1.0 - half_h);
    let clamped = (tx - want_x).abs() > 1e-9 || (ty - want_y).abs() > 1e-9;
    let new = lines
        .iter()
        .map(|line| paper.transformed(line, tx - c[0], ty - c[1], 1.0, c))
        .collect::<Result<Vec<_>, _>>()
        .map_err(|detail| refuse("no_numeric_place", detail))?;
    if !new.iter().all(|line| paper.fits(line)) {
        return Err(refuse(
            "leaves_canvas",
            paper.say("動かすと画面からはみ出す", "moving it leaves the canvas"),
        ));
    }
    if new == lines {
        return Err(refuse(
            "unchanged",
            paper.say("置き場が変わらない", "its place does not change"),
        ));
    }
    let mut child = doc.clone();
    for (index, line) in indexes.iter().zip(new) {
        child.lines[*index] = line;
    }
    Ok((child, c, [tx, ty], clamped))
}

/// The child DDL (titled) with one chunk moved to a place, and what moved
/// (step 3, the refinement "Change the layout" on a work written in words).
pub fn place_at(
    config: &PipelineConfig,
    ddl: &str,
    composition: Option<&Composition>,
    chunk: &str,
    at: &str,
) -> Result<(String, Placed), Refusal> {
    let (paper, _) = paper_of(config)?;
    let doc = Doc::of(&titled_source(ddl, composition, paper.language));
    let (child, from, to, clamped) = move_chunk(&doc, paper, chunk, at)?;
    // A moved sentence the compiler would not draw (an arc stopped right at
    // the edge was left out without a word, step 3a's measure) is refused.
    let problems = new_problems(config, &doc, &child);
    if !problems.is_empty() {
        return Err(refuse("undrawable", undrawn(paper, &problems)));
    }
    let thing = composition.and_then(|composition| {
        composed_thing_titles(&composition.owners, &composition.things, paper.language)
            .iter()
            .find(|(_, name)| name.as_str() == chunk)
            .map(|(number, _)| *number)
    });
    Ok((
        child.titled(paper.language),
        Placed {
            title: chunk.to_owned(),
            thing,
            at: at.to_owned(),
            at_from: place_of(from),
            from,
            to,
            clamped,
        },
    ))
}

/// Each place's outcome for a chunk: `ok`, `clamped`, or the reason it is
/// refused (`unchanged` among them), so a screen can show it before it asks.
fn places_of(doc: &Doc, paper: Paper, chunk: &str) -> BTreeMap<String, String> {
    PLACES
        .iter()
        .map(|at| {
            let outcome = match move_chunk(doc, paper, chunk, at) {
                Ok((_, _, _, true)) => "clamped".to_owned(),
                Ok(_) => "ok".to_owned(),
                Err(refusal) => refusal.reason.to_owned(),
            };
            ((*at).to_owned(), outcome)
        })
        .collect()
}

/// The chunk of each line of the DDL as the host gave it (not as titled
/// here): with title lines, a title line and the sentences after it are its
/// chunk's; without, line `n` is the record's `owners[n - 1]`'s, as
/// `titled_composed_source` titles it. Blank lines are no chunk's.
fn source_line_chunks(
    ddl: &str,
    composition: Option<&Composition>,
    titles: Option<&BTreeMap<u64, String>>,
) -> Vec<Option<String>> {
    let lines: Vec<&str> = ddl
        .split('\n')
        .map(|line| line.strip_suffix('\r').unwrap_or(line))
        .collect();
    if !ddl_title_lines(ddl).is_empty() {
        let mut current: Option<String> = None;
        return lines
            .iter()
            .map(|line| {
                if let Some(name) = ddl_title_name(line) {
                    current = (!name.is_empty()).then(|| name.to_owned());
                    current.clone()
                } else if line.trim().is_empty() {
                    None
                } else {
                    current.clone()
                }
            })
            .collect();
    }
    let (Some(composition), Some(titles)) = (composition, titles) else {
        return vec![None; lines.len()];
    };
    if lines.len() != composition.owners.len() + 1 {
        return vec![None; lines.len()];
    }
    lines
        .iter()
        .enumerate()
        .map(|(index, line)| {
            if index == 0 || line.trim().is_empty() {
                return None;
            }
            titles.get(&composition.owners[index - 1]).cloned()
        })
        .collect()
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct UnitsRequest {
    ddl: String,
    #[serde(default)]
    composition: Option<Composition>,
    language: ResolvedInstructionLanguage,
}

/// A work's chunks with the record's thing and the box of each: its DDL, the
/// configuration it is drawn with (paper, language, definitions) and its
/// composition record.
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct BoxesRequest {
    config: PipelineConfig,
    ddl: String,
    #[serde(default)]
    composition: Option<Composition>,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct WorkBoxesRequest {
    config: PipelineConfig,
    ddl: String,
    #[serde(default)]
    own_record: Option<Value>,
    #[serde(default)]
    inherited_record: Option<Value>,
    #[serde(default)]
    derivation_kind: Option<String>,
    #[serde(default)]
    score: Value,
}

fn composition_record(record: Option<&Value>) -> Result<Option<Composition>, Refusal> {
    let Some(record) = record else {
        return Ok(None);
    };
    let (Some(owners), Some(things)) = (
        record.get("things").and_then(Value::as_array),
        record
            .get("answer")
            .and_then(|a| a.get("things"))
            .and_then(Value::as_array),
    ) else {
        return Ok(None);
    };
    serde_json::from_value(json!({"owners": owners, "things": things}))
        .map(Some)
        .map_err(|_| refuse("invalid_request", "invalid composition record"))
}

fn fitted(derivation_kind: Option<&str>, score: &Value) -> bool {
    if derivation_kind == Some("canvas_fit") {
        return true;
    }
    let Some(canvas) = score.get("canvas").and_then(Value::as_object) else {
        return false;
    };
    if canvas.get("fit").is_none_or(Value::is_null) {
        return false;
    }
    let declared = canvas.get("declared_ratio").unwrap_or(&Value::Null);
    let integer = |v: &Value| -> Option<i128> {
        if let Some(i) = v.as_i64() {
            return Some(i128::from(i));
        }
        if let Some(s) = v.as_str() {
            return s.trim().parse().ok();
        }
        if let Some(b) = v.as_bool() {
            return Some(i128::from(b));
        }
        v.as_f64()
            .filter(|x| x.is_finite())
            .map(|x| x.trunc() as i128)
    };
    let Some(w) = declared.get("width_units").and_then(integer) else {
        return true;
    };
    let Some(h) = declared.get("height_units").and_then(integer) else {
        return true;
    };
    let Some(format) = canvas
        .get("aspect")
        .and_then(Value::as_str)
        .and_then(|a| inku_score::lookup_canvas_format(a).ok())
    else {
        return true;
    };
    match (
        w.checked_mul(i128::from(format.height_units)),
        h.checked_mul(i128::from(format.width_units)),
    ) {
        (Some(left), Some(right)) => left != right,
        _ => true,
    }
}

/// One chunk moved to one place by the author (step 3).
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct PlaceRequest {
    config: PipelineConfig,
    ddl: String,
    #[serde(default)]
    composition: Option<Composition>,
    #[serde(default)]
    derivation_kind: Option<String>,
    #[serde(default)]
    score: Value,
    chunk: String,
    at: String,
}

#[derive(Deserialize)]
#[serde(tag = "action", rename_all = "snake_case")]
enum Request {
    Units(Box<UnitsRequest>),
    Boxes(Box<BoxesRequest>),
    WorkBoxes(Box<WorkBoxesRequest>),
    Place(Box<PlaceRequest>),
}

fn respond(request: Request) -> Result<Value, Refusal> {
    match request {
        Request::Units(request) => {
            let source =
                titled_source(&request.ddl, request.composition.as_ref(), request.language);
            Ok(json!({"units": Doc::of(&source).units()}))
        }
        Request::Boxes(request) => {
            let units = boxes(&request.config, &request.ddl, request.composition.as_ref())?;
            let (paper, _) = paper_of(&request.config)?;
            // A work with free lines says so: moving a thing may draw them again.
            let free_lines = request.ddl.lines().any(|line| {
                crate::description_laws::draws_free_line(line, paper.language, paper.definitions)
            });
            Ok(json!({"units": units, "free_lines": free_lines}))
        }
        Request::WorkBoxes(request) => {
            let composition = match composition_record(request.own_record.as_ref())? {
                Some(composition) => Some(composition),
                None => composition_record(request.inherited_record.as_ref())?,
            };
            let mut units = boxes(&request.config, &request.ddl, composition.as_ref())?;
            let (paper, _) = paper_of(&request.config)?;
            let free_lines = request.ddl.lines().any(|line| {
                crate::description_laws::draws_free_line(line, paper.language, paper.definitions)
            });
            if fitted(request.derivation_kind.as_deref(), &request.score) {
                for unit in &mut units {
                    unit.area = None;
                    unit.at = None;
                    for value in unit.places.values_mut() {
                        *value = "fitted".to_owned();
                    }
                }
            }
            Ok(json!({"units": units, "free_lines": free_lines}))
        }
        Request::Place(request) => {
            if fitted(request.derivation_kind.as_deref(), &request.score) {
                return Err(refuse("fitted", "the work is fitted onto another paper"));
            }
            let (ddl, place) = place_at(
                &request.config,
                &request.ddl,
                request.composition.as_ref(),
                &request.chunk,
                &request.at,
            )?;
            Ok(json!({"ddl": ddl, "place": place}))
        }
    }
}

/// JSON in, JSON out, for the hosts' bindings. An answer is `{"schema",
/// "outcome": "ok", ...}` or `{"schema", "outcome":
/// "refused", "reason", "detail"}`; a request that cannot be read answers
/// `{"error": "invalid_request"}`.
#[must_use]
pub fn chunk_moves_json(input: &[u8]) -> Vec<u8> {
    let Ok(request) = serde_json::from_slice::<Request>(input) else {
        return br#"{"error":"invalid_request"}"#.to_vec();
    };
    let mut body = Map::new();
    match respond(request) {
        Ok(Value::Object(fields)) => {
            body.insert("outcome".to_owned(), json!("ok"));
            body.extend(fields);
        }
        Ok(_) => return br#"{"error":"internal"}"#.to_vec(),
        Err(refusal) => {
            if refusal.reason == "invalid_request" {
                return br#"{"error":"invalid_request"}"#.to_vec();
            }
            body.insert("outcome".to_owned(), json!("refused"));
            body.insert("reason".to_owned(), json!(refusal.reason));
            body.insert("detail".to_owned(), json!(refusal.detail));
        }
    }
    body.insert("schema".to_owned(), json!(CHUNK_MOVES_SCHEMA_ID));
    serde_json::to_vec(&Value::Object(body)).unwrap_or_else(|_| br#"{"error":"internal"}"#.to_vec())
}

#[cfg(test)]
mod tests {
    use super::*;

    const LIGHTHOUSE: &str = "画面比1:1。\n背景を白で埋める。\n\n「灯台」\n\
        画面の横0.6、縦0.4の位置に、幅0.1、高さ0.3の白の塗りの四角を1個置く。\n\
        画面の横0.6、縦0.22の位置に、直径0.08の黄の塗りの円を1個置く。\n\n「波の筋」\n\
        画面の横0.1、縦0.8から横0.9、縦0.8まで、灰の細い線を1本引く。";

    fn config() -> PipelineConfig {
        let mut config = crate::focused_flow::config();
        config.language = ResolvedInstructionLanguage::Ja;
        config
    }

    #[test]
    fn chunks_come_in_order_and_a_composition_titles_an_untitled_ddl() {
        let doc = Doc::of(LIGHTHOUSE);
        assert_eq!(doc.units(), ["灯台", "波の筋"]);
        assert_eq!(doc.titled(ResolvedInstructionLanguage::Ja), LIGHTHOUSE);
        let plain = Doc {
            lines: doc.lines.clone(),
            chunks: vec![None; doc.lines.len()],
        }
        .titled(ResolvedInstructionLanguage::Ja);
        let thing = |thing, quote: &str| CompositionThing {
            thing,
            what: String::new(),
            role: "main".to_owned(),
            kind: "cluster".to_owned(),
            quote: quote.to_owned(),
            word: String::new(),
        };
        let composition = Composition {
            owners: vec![0, 1, 1, 2],
            things: vec![thing(1, "灯台"), thing(2, "波の筋")],
        };
        assert_eq!(
            titled_source(&plain, Some(&composition), ResolvedInstructionLanguage::Ja),
            LIGHTHOUSE
        );
        assert_eq!(
            titled_source(&plain, None, ResolvedInstructionLanguage::Ja),
            plain
        );
    }

    #[test]
    fn new_problems_excludes_lines_already_problematic_in_the_parent() {
        let child = format!(
            "{LIGHTHOUSE}\n画面の横0.5、縦0.9の位置に、幅0.6、高さ0.08の赤と緑の太いガッシュの刷きの雲形を1個置く。"
        );
        let found = new_problems(&config(), &Doc::of(LIGHTHOUSE), &Doc::of(&child));
        assert!(
            !found.is_empty() && found.iter().all(|problem| problem.line.contains("赤と緑")),
            "{found:?}"
        );
        assert!(new_problems(&config(), &Doc::of(&child), &Doc::of(&child)).is_empty());
    }

    #[test]
    fn json_boundary_refuses_untitled_chunks_and_invalid_requests() {
        let plain = "画面比1:1。\n画面の横0.5、縦0.5の位置に、直径0.1の赤の塗りの円を1個置く。";
        let request = json!({"action": "place", "config": config(), "ddl": plain, "chunk": "円", "at": "center"});
        let answer: Value =
            serde_json::from_slice(&chunk_moves_json(&serde_json::to_vec(&request).unwrap()))
                .unwrap();
        assert_eq!(answer["schema"], CHUNK_MOVES_SCHEMA_ID);
        assert_eq!(answer["outcome"], "refused");
        assert_eq!(answer["reason"], "no_chunk");
        assert_eq!(
            chunk_moves_json(br#"{"action":"place"}"#),
            br#"{"error":"invalid_request"}"#
        );
        let units = json!({"action": "units", "ddl": LIGHTHOUSE, "language": "ja"});
        let answer: Value =
            serde_json::from_slice(&chunk_moves_json(&serde_json::to_vec(&units).unwrap()))
                .unwrap();
        assert_eq!(answer["units"], json!(["灯台", "波の筋"]));
    }

    #[test]
    fn place_rewrites_only_the_numbers_of_the_chunk() {
        let (moved, _) = place_at(&config(), LIGHTHOUSE, None, "灯台", "center").unwrap();
        let parent: Vec<_> = LIGHTHOUSE.lines().collect();
        let child: Vec<_> = moved.lines().collect();
        assert_eq!(parent.len(), child.len());
        assert_eq!(child.iter().zip(&parent).filter(|(a, b)| a != b).count(), 2);
        assert_eq!(
            child[4],
            "画面の横0.5、縦0.535の位置に、幅0.1、高さ0.3の白の塗りの四角を1個置く。"
        );
        assert_eq!(
            child[5],
            "画面の横0.5、縦0.355の位置に、直径0.08の黄の塗りの円を1個置く。"
        );
    }

    #[test]
    fn the_author_places_one_chunk_without_resizing_it() {
        let ask = |request: Value| -> Value {
            serde_json::from_slice(&chunk_moves_json(&serde_json::to_vec(&request).unwrap()))
                .unwrap()
        };
        let place = |ddl: &str, chunk: &str, at: &str| {
            ask(
                json!({"action": "place", "config": config(), "ddl": ddl, "chunk": chunk, "at": at}),
            )
        };
        // The lighthouse (its box 0.55..0.65 × 0.18..0.55) to the center:
        // only its two sentences' numbers change, by the same move.
        let moved = place(LIGHTHOUSE, "灯台", "center");
        assert_eq!(moved["schema"], CHUNK_MOVES_SCHEMA_ID);
        assert_eq!(moved["outcome"], "ok", "{moved}");
        let child: Vec<&str> = moved["ddl"].as_str().unwrap().lines().collect();
        let parent: Vec<&str> = LIGHTHOUSE.lines().collect();
        assert_eq!(child.len(), parent.len());
        let changed: Vec<usize> = (0..parent.len())
            .filter(|at| child[*at] != parent[*at])
            .collect();
        assert_eq!(changed, [4, 5]);
        assert_eq!(
            child[4],
            "画面の横0.5、縦0.535の位置に、幅0.1、高さ0.3の白の塗りの四角を1個置く。"
        );
        assert_eq!(
            child[5],
            "画面の横0.5、縦0.355の位置に、直径0.08の黄の塗りの円を1個置く。"
        );
        assert_eq!(moved["place"]["title"], "灯台");
        assert_eq!(moved["place"]["at"], "center");
        // Its center (0.6, 0.365) is within 0.02 of the golden upper right
        // (0.618, 0.382).
        assert_eq!(moved["place"]["at_from"], "golden_ur");
        assert_eq!(moved["place"]["clamped"], false);
        assert_eq!(moved["place"]["to"], json!([0.5, 0.5]));
        // The waves (0.8 wide) cannot reach the golden line at 0.382: they stop
        // at 0.4 (clamped). Going to the top third keeps x; their center
        // (0.5, 0.8) is at no place.
        let waves = place(LIGHTHOUSE, "波の筋", "golden_ul");
        assert_eq!(waves["place"]["clamped"], true, "{waves}");
        assert_eq!(waves["place"]["to"][0], 0.4);
        let top = place(LIGHTHOUSE, "波の筋", "third_top");
        assert_eq!(top["place"]["clamped"], false);
        assert_eq!(top["place"]["at_from"], Value::Null);
        // A chunk at a place names it as where it was, and placing it there
        // again changes nothing.
        let centered = moved["ddl"].as_str().unwrap();
        let again = place(centered, "灯台", "golden_ul");
        assert_eq!(again["place"]["at_from"], "center");
        let refused = |answer: Value| {
            (
                answer["outcome"].as_str().map(str::to_owned),
                answer["reason"].as_str().map(str::to_owned),
            )
        };
        assert_eq!(
            refused(place(centered, "灯台", "center")),
            (Some("refused".into()), Some("unchanged".into()))
        );
        assert_eq!(
            refused(place(LIGHTHOUSE, "月", "center")).1.as_deref(),
            Some("no_chunk")
        );
        assert_eq!(
            refused(place(LIGHTHOUSE, "灯台", "keep")).1.as_deref(),
            Some("unknown_place")
        );
        let wide = "画面比1:1。\n\n「帯」\n画面の横0.5、縦0.5の位置に、幅1.2、高さ0.1の青の塗りの四角を1個置く。";
        assert_eq!(
            refused(place(wide, "帯", "center")).1.as_deref(),
            Some("too_large")
        );
        let unplaced = "画面比1:1。\n\n「地」\n背景を白で埋める。";
        assert_eq!(
            refused(place(unplaced, "地", "center")).1.as_deref(),
            Some("no_numeric_place")
        );
        // Two arcs (step 3a's measure, work 0082c231): stopped at the left edge,
        // the grey one would be left out by the compiler without a word, so
        // that place is refused; the center draws.
        let arcs = "画面比1:1。\n\n「山里」\n\
            画面の横0.33、縦0.618034の位置に、弦長0.424、矢高0.045の灰の水彩の薄い細いゆるやかに揺れる弧を1本引く。\n\
            画面の横0.67、縦0.618034の位置に、弦長0.424、矢高0.055の青の水彩の薄い細いゆるやかに揺れる弧を1本引く。";
        assert_eq!(
            refused(place(arcs, "山里", "golden_ul")).1.as_deref(),
            Some("undrawable")
        );
        assert_eq!(place(arcs, "山里", "center")["outcome"], "ok");
        // boxes tell each place's outcome before it is asked.
        let boxes = ask(json!({"action": "boxes", "config": config(), "ddl": centered}));
        let lighthouse = &boxes["units"][0]["places"];
        assert_eq!(lighthouse["center"], "unchanged");
        assert_eq!(lighthouse["golden_ul"], "ok");
        assert_eq!(boxes["units"][1]["places"]["golden_ul"], "clamped");
        assert_eq!(boxes["units"][1]["places"].as_object().unwrap().len(), 9);
    }

    #[test]
    fn boxes_tie_each_chunk_to_its_thing_lines_and_box() {
        let ask = |request: Value| -> Value {
            serde_json::from_slice(&chunk_moves_json(&serde_json::to_vec(&request).unwrap()))
                .unwrap()
        };
        let thing = |thing: u64, what: &str, quote: &str| CompositionThing {
            thing,
            what: what.to_owned(),
            role: "main".to_owned(),
            kind: "object".to_owned(),
            quote: quote.to_owned(),
            word: String::new(),
        };
        // A short made-up DDL: the second chunk is the mock work's (76ba66d8)
        // 「磯もとどろに」, whose box the work's evidence measured.
        let titled = "画面比1:1。\n背景を青で埋める。\n\n「大海の」\n\
            画面の横0.12、縦0.24から横0.89、縦0.32まで、白の水彩の細いゆるやかに波打つ線を1本引く。\n\n\
            「磯もとどろに」\n\
            画面の横0.618034、縦0.618034の位置に、幅0.36、高さ0.3の回転20.0度の黒のガッシュの塗りの楕円を1個置く。\n\
            画面の横0.66、縦0.61の位置に、幅0.16、高さ0.2の回転25.0度の灰のガッシュの刷毛目の三角を1個置く。\n\
            画面の横0.58、縦0.69から横0.72、縦0.58まで、紫の鉛筆の細い線を1本引く。";
        let composition = json!({
            "owners": [0, 1, 2, 2, 2],
            "things": [thing(1, "海", "大海の"), thing(2, "岩", "磯もとどろに")],
        });
        let answer = ask(json!({
            "action": "boxes", "config": config(), "ddl": titled, "composition": composition,
        }));
        assert_eq!(answer["schema"], CHUNK_MOVES_SCHEMA_ID);
        assert_eq!(answer["outcome"], "ok");
        let units = answer["units"].as_array().unwrap();
        assert_eq!(units.len(), 2);
        assert_eq!(units[0]["title"], "大海の");
        assert_eq!(units[0]["thing"], 1);
        assert_eq!(units[0]["lines"], json!([3, 4]));
        assert_eq!(units[0]["box"], json!([0.12, 0.24, 0.89, 0.32]));
        assert_eq!(units[0]["at"], Value::Null);
        assert_eq!(units[1]["title"], "磯もとどろに");
        assert_eq!(units[1]["thing"], 2);
        assert_eq!(units[1]["at"], "golden_lr");
        assert_eq!(units[1]["lines"], json!([6, 7, 8, 9]));
        assert_eq!(
            (
                units[1]["sentences"].as_u64(),
                units[1]["unplaced"].as_u64()
            ),
            (Some(3), Some(0))
        );
        let area: Vec<f64> = serde_json::from_value(units[1]["box"].clone()).unwrap();
        let expected = [
            0.397_586_306_759_686_2,
            0.415_516_481_083_493_37,
            0.838_481_693_240_313_7,
            0.820_551_518_916_506_6,
        ];
        for (got, want) in area.iter().zip(expected) {
            assert!((got - want).abs() < 1e-9, "{area:?}");
        }

        // No title lines: the record titles the chunks here, and the lines
        // are the given DDL's.
        let plain = "画面比1:1。\n背景を青で埋める。\n\
            画面の横0.12、縦0.24から横0.89、縦0.32まで、白の水彩の細いゆるやかに波打つ線を1本引く。\n\
            画面の横0.58、縦0.69から横0.72、縦0.58まで、紫の鉛筆の細い線を1本引く。";
        let composition = json!({
            "owners": [0, 1, 2],
            "things": [thing(1, "海", "大海の"), thing(2, "岩", "")],
        });
        let recorded = ask(json!({
            "action": "boxes", "config": config(), "ddl": plain, "composition": composition,
        }));
        let units = recorded["units"].as_array().unwrap();
        assert_eq!(units.len(), 2);
        assert_eq!(
            (&units[0]["title"], &units[0]["thing"], &units[0]["lines"]),
            (&json!("大海の"), &json!(1), &json!([2]))
        );
        assert_eq!(
            (&units[1]["title"], &units[1]["thing"], &units[1]["lines"]),
            (&json!("岩"), &json!(2), &json!([3]))
        );
        let without = ask(json!({"action": "boxes", "config": config(), "ddl": plain}));
        assert_eq!(without["units"], json!([]));
        // A work with a free line says so (step 3); one without does not.
        assert_eq!(recorded["free_lines"], false);
        let free = format!(
            "{plain}\n画面の横0.1、縦0.1から横0.3、縦0.2まで、赤の水彩のごく細い細かく揺れる自由線を1本引く。"
        );
        let with_free = ask(json!({"action": "boxes", "config": config(), "ddl": free}));
        assert_eq!(with_free["free_lines"], true, "{with_free}");

        // A chunk of a plugin word alone has no box.
        let package: Value = serde_json::from_str(include_str!(
            "../../inku-ddl/tests/fixtures/nature-leaves-2.1-v1.json"
        ))
        .unwrap();
        let mut config = config();
        config.definitions.push(
            MacroDefinition::from_json(&package["entries"][0]["definition"].to_string()).unwrap(),
        );
        let scene = ask(json!({
            "action": "boxes", "config": config, "ddl": "画面比1:1。\n\n「葉」\n｛若葉｝。",
        }));
        assert_eq!(
            scene["units"],
            json!([{"title": "葉", "thing": null, "lines": [2, 3], "sentences": 1, "unplaced": 1, "box": null, "at": null,
                "places": {"golden_ul": "scene_word", "golden_ur": "scene_word", "golden_ll": "scene_word",
                    "golden_lr": "scene_word", "third_left": "scene_word", "third_right": "scene_word",
                    "third_top": "scene_word", "third_bottom": "scene_word", "center": "scene_word"}}])
        );
    }
}
