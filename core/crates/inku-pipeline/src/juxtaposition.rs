//! Juxtaposition (取り合わせ, the author, 2026-10-19): a sentence from the
//! author's other works, added after a work's description. A model picks four
//! candidates, the author chooses one, and the work is drawn again from the
//! longer description through the ordinary description fork.
//!
//! The rules were Server's (`juxtaposition.py`) and Web's (how the sentence is
//! joined); they are moved here (2026-10-20) so that macOS and Android ask this
//! one copy, as the author decided when both apps waited for the core. They
//! follow the prototype that measured this (step 1d of the autonomous
//! refinement study):
//!
//! - A candidate is the first sentence of another work's description, in the
//!   description's language.
//! - One sentence counts once: spacing, the "(AI)" mark and the kana or kanji
//!   spelling of one poem do not make a new sentence ([`same_text`]).
//! - The candidates are shuffled for every request, because the prototype's
//!   models leaned to the head of a long list. The host passes the seed; the
//!   core holds no randomness.
//! - At most the host's limit goes out; above it, each request draws that many.
//! - The work's own descriptions, sentences its lineage already added and those
//!   shown before are left out.
//!
//! One JSON request with an `action`, one JSON answer
//! (`inku.juxtaposition.v1`): `gather` the candidates, the `prompt` to send,
//! `check` an answer against the candidates, `join` a sentence to a
//! description, and whether two sentences are the `same`. Nothing is sent or
//! saved here: the host collects the sources (leaving out the works it must),
//! draws the image, sends the request and draws the child.

use std::collections::{BTreeSet, HashMap, HashSet};

use serde::{Deserialize, Serialize};
use serde_json::{Map, Value, json};

use crate::identity::{is_python_space, python_strip};
use crate::saved_variants::Draw;

pub const JUXTAPOSITION_SCHEMA_ID: &str = "inku.juxtaposition.v1";

/// How many sentences the model picks.
pub const CHOICES: usize = 4;
/// The share of two-character pieces at which two sentences are the same one.
const SAME_NUMERATOR: usize = 4;
const SAME_DENOMINATOR: usize = 5;
/// The longest reason kept, in characters.
const REASON_LIMIT: usize = 2000;

/// One sentence offered to the model: its id in this request, the sentence, and
/// every work it came from.
#[derive(Clone, Debug, Eq, PartialEq, Serialize, Deserialize)]
pub struct Candidate {
    pub id: String,
    pub sentence: String,
    pub history_ids: Vec<String>,
}

/// One of the model's picks, in its order, with the description it makes.
#[derive(Clone, Debug, PartialEq, Serialize)]
pub struct Choice {
    pub sentence: String,
    pub reason: String,
    pub history_ids: Vec<String>,
    pub rank: usize,
    /// Where the sentence stood in the shuffled list the model read: 0 the
    /// head, 1 the tail, to three places.
    pub position: f64,
    /// The description with the sentence after it ([`join`]).
    pub joined: String,
}

/// The first sentence of a text: from its start, on its first line, up to the
/// first `。！？`, or `.!?` before a space or the end. A text with none is
/// itself (Python's `(.+?(?:[。！？]|[.!?](?=\s|$)))` from the start).
#[must_use]
pub fn first_sentence(text: &str) -> String {
    let stripped = python_strip(text);
    let characters: Vec<(usize, char)> = stripped.char_indices().collect();
    for (place, &(at, character)) in characters.iter().enumerate() {
        if character == '\n' {
            break;
        }
        if place == 0 {
            continue;
        }
        let ends = match character {
            '。' | '！' | '？' => true,
            '.' | '!' | '?' => characters
                .get(place + 1)
                .is_none_or(|&(_, next)| is_python_space(next)),
            _ => false,
        };
        if ends {
            return python_strip(&stripped[..at + character.len_utf8()]).to_owned();
        }
    }
    stripped.to_owned()
}

/// The form two sentences are compared in: no spacing, no "(AI)" mark.
#[must_use]
pub fn text_key(text: &str) -> String {
    let characters: Vec<char> = text.chars().collect();
    let mut key = String::with_capacity(text.len());
    let mut place = 0;
    while place < characters.len() {
        let mark = characters.get(place..place + 4).is_some_and(|four| {
            matches!(four[0], '(' | '（')
                && four[1] == 'A'
                && four[2] == 'I'
                && matches!(four[3], ')' | '）')
        });
        if mark {
            place += 4;
            continue;
        }
        if !is_python_space(characters[place]) {
            key.push(characters[place]);
        }
        place += 1;
    }
    key
}

/// The two-character pieces of a key (the key itself when it is shorter).
fn pieces(key: &str) -> HashSet<String> {
    let characters: Vec<char> = key.chars().collect();
    if characters.len() < 2 {
        return HashSet::from([key.to_owned()]);
    }
    characters
        .windows(2)
        .map(|pair| pair.iter().collect())
        .collect()
}

fn alike(key: &str, pieces: &HashSet<String>, other_key: &str, other: &HashSet<String>) -> bool {
    if key == other_key {
        return true;
    }
    let shared = pieces.intersection(other).count();
    let union = pieces.len() + other.len() - shared;
    shared * SAME_DENOMINATOR >= union * SAME_NUMERATOR
}

/// Whether two sentences are one: the same poem spelt with kana or kanji, with
/// other spacing or with the "(AI)" mark counts once.
#[must_use]
pub fn same_text(a: &str, b: &str) -> bool {
    let (key_a, key_b) = (text_key(a), text_key(b));
    alike(&key_a, &pieces(&key_a), &key_b, &pieces(&key_b))
}

/// `ja` when the text holds kana or kanji, else `en`.
#[must_use]
pub fn language_of(text: &str) -> &'static str {
    if text
        .chars()
        .any(|character| matches!(character, '\u{3040}'..='\u{30ff}' | '\u{3400}'..='\u{9fff}'))
    {
        "ja"
    } else {
        "en"
    }
}

/// One work that may lend a sentence: its id and its description, labels
/// already removed.
#[derive(Clone, Debug, Deserialize)]
pub struct Source {
    pub id: String,
    pub text: String,
}

struct Kept {
    sentence: String,
    key: String,
    pieces: HashSet<String>,
    history_ids: Vec<String>,
}

/// The kept sentence this one repeats, if any. Counting the pieces each kept
/// sentence shares with this one finds the likely twins without comparing every
/// pair; the share can only fall as the count falls, so the search stops at the
/// first count too small to reach the line.
fn twin(
    kept: &[Kept],
    index: &HashMap<String, Vec<usize>>,
    key: &str,
    pieces: &HashSet<String>,
) -> Option<usize> {
    let mut shared: HashMap<usize, usize> = HashMap::new();
    for piece in pieces {
        for &place in index.get(piece).into_iter().flatten() {
            *shared.entry(place).or_default() += 1;
        }
    }
    let mut counted: Vec<(usize, usize)> = shared.into_iter().collect();
    counted.sort_by(|a, b| b.1.cmp(&a.1).then(a.0.cmp(&b.0)));
    for (place, count) in counted {
        if count * SAME_DENOMINATOR < pieces.len() * SAME_NUMERATOR {
            return None;
        }
        let other = &kept[place];
        if alike(key, pieces, &other.key, &other.pieces) {
            return Some(place);
        }
    }
    None
}

/// What [`gather`] reads.
#[derive(Clone, Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct GatherRequest {
    pub sources: Vec<Source>,
    pub description: String,
    #[serde(default)]
    pub lineage: Vec<String>,
    #[serde(default)]
    pub added: Vec<String>,
    #[serde(default)]
    pub exclude: Vec<String>,
    pub seed: Seed,
    pub limit: usize,
}

/// A seed as a JSON number or a decimal string (a JavaScript or Swift host may
/// not carry 64 bits in a number).
#[derive(Clone, Copy, Debug, Deserialize)]
#[serde(try_from = "Value")]
pub struct Seed(pub u64);

impl TryFrom<Value> for Seed {
    type Error = String;

    fn try_from(value: Value) -> Result<Self, Self::Error> {
        match &value {
            Value::Number(number) => number.as_u64(),
            Value::String(text) => text.parse().ok(),
            _ => None,
        }
        .map(Seed)
        .ok_or_else(|| "a seed is a nonnegative 64-bit integer".to_owned())
    }
}

/// At most `limit` candidate sentences, in an order drawn from the seed.
///
/// Only sentences in the description's language are offered. A sentence is
/// left out when it is the work's description, a description of its lineage
/// (or the first sentence of one), a sentence the lineage already added, or
/// one shown before. Each candidate carries the ids of every work it came
/// from; its id (`c0001` and on) names its place among the sentences kept.
#[must_use]
pub fn gather(request: &GatherRequest) -> Vec<Candidate> {
    let language = language_of(&request.description);
    let mut by_sentence: Vec<(String, Vec<String>)> = Vec::new();
    let mut found: HashMap<String, usize> = HashMap::new();
    for source in &request.sources {
        let sentence = first_sentence(&source.text);
        if sentence.is_empty() || language_of(&sentence) != language {
            continue;
        }
        match found.get(&sentence) {
            Some(&place) => by_sentence[place].1.push(source.id.clone()),
            None => {
                found.insert(sentence.clone(), by_sentence.len());
                by_sentence.push((sentence, vec![source.id.clone()]));
            }
        }
    }
    let mut avoid: Vec<String> = std::iter::once(&request.description)
        .chain(&request.lineage)
        .filter(|text| !text.is_empty())
        .cloned()
        .collect();
    let firsts: Vec<String> = avoid.iter().map(|text| first_sentence(text)).collect();
    avoid.extend(firsts);
    avoid.extend(
        request
            .added
            .iter()
            .chain(&request.exclude)
            .filter(|text| !text.is_empty())
            .cloned(),
    );
    let avoid_keys: Vec<(String, HashSet<String>)> = avoid
        .iter()
        .map(|text| text_key(text))
        .collect::<BTreeSet<String>>()
        .into_iter()
        .map(|key| {
            let pieces = pieces(&key);
            (key, pieces)
        })
        .collect();
    // A sentence opening with a number such as "#25 " is looked at last, so that
    // the same sentence without the number is the one that stays.
    by_sentence.sort_by(|a, b| (a.0.starts_with('#'), &a.0).cmp(&(b.0.starts_with('#'), &b.0)));
    let mut kept: Vec<Kept> = Vec::new();
    let mut index: HashMap<String, Vec<usize>> = HashMap::new();
    for (sentence, history_ids) in by_sentence {
        let key = text_key(&sentence);
        let pieces = pieces(&key);
        if avoid_keys
            .iter()
            .any(|(other_key, other)| alike(&key, &pieces, other_key, other))
        {
            continue;
        }
        if let Some(place) = twin(&kept, &index, &key, &pieces) {
            kept[place].history_ids.extend(history_ids);
            continue;
        }
        for piece in &pieces {
            index.entry(piece.clone()).or_default().push(kept.len());
        }
        kept.push(Kept {
            sentence,
            key,
            pieces,
            history_ids,
        });
    }
    let mut order: Vec<usize> = (0..kept.len()).collect();
    let mut draw = Draw(request.seed.0);
    for last in (1..order.len()).rev() {
        order.swap(last, draw.below(last + 1));
    }
    order.truncate(request.limit);
    order
        .into_iter()
        .map(|place| {
            let mut history_ids = kept[place].history_ids.clone();
            history_ids.sort();
            Candidate {
                id: format!("c{:04}", place + 1),
                sentence: kept[place].sentence.clone(),
                history_ids,
            }
        })
        .collect()
}

fn english(language: &str) -> bool {
    language == "en"
}

/// The system prompt, in the language the author reads (`en`, else Japanese).
#[must_use]
pub fn system_prompt(language: &str) -> &'static str {
    if english(language) {
        concat!(
            "You help an author take their own work further. The author creates; everything you offer is a proposal. ",
            "You never score, praise or condemn, and never use evaluative words such as better, improved, beautiful, ",
            "appealing or balanced. ",
            "The aim is to shake the work loose: the author is stuck with it. Choose a sentence from the author's other ",
            "works to be added, unchanged, after this work's description. Neither the description nor the chosen ",
            "sentence is rewritten. As a juxtaposition, two things set side by side to make a new meaning, choose a ",
            "sentence that moves the idea of the work itself in a direction the author would not think of. Choose four ",
            "candidates in the order you would pick them, and for each write in one sentence how adding it moves the ",
            "idea of the work. Return JSON only: {\"choices\": [{\"id\": \"...\", \"reason\": \"...\"}]} with exactly four items."
        )
    } else {
        concat!(
            "あなたは、作者が自分の作品をさらに深めるのを手伝う助手です。創作の主体は作者で、あなたの手はすべて提案です。",
            "良し悪し・点数・好み・称賛・否定は書きません。「良くなる」「改善」「美しい」「魅力的」「バランスが良い」などの評価の語を",
            "使いません。",
            "目的は「揺さぶり」です。作者は、この作品で煮詰まっています。作者のほかの作品の記述から一文を選び、この作品の記述の",
            "後ろに、そのまま足します。元の記述も、選んだ一文も書き換えません。二つのものを並べて新しい意味を生む「取り合わせ」",
            "として、作者が自分では思いつかない方向へ、作品の考えそのものを動かす一文を選びます。候補から4つを、選びたい順に",
            "並べます。それぞれに、足すと作品の考えがどう動くかを1文で書きます。",
            "答えは JSON だけを返します：{\"choices\": [{\"id\": \"…\", \"reason\": \"…\"}]}（choices はちょうど4つ）。"
        )
    }
}

/// The message beside the image: the description, the lineage, the
/// candidates by id, and what to answer. `resend` is why the previous answer
/// could not be used, for the one resend.
#[must_use]
pub fn message(
    language: &str,
    description: &str,
    lineage: &[String],
    candidates: &[Candidate],
    resend: Option<&str>,
) -> String {
    let colon = if english(language) { ": " } else { "：" };
    let listed = candidates
        .iter()
        .map(|candidate| format!("{}{colon}{}", candidate.id, candidate.sentence))
        .collect::<Vec<_>>()
        .join("\n");
    let steps = lineage
        .iter()
        .enumerate()
        .map(|(number, text)| format!("{}. {text}", number + 1))
        .collect::<Vec<_>>()
        .join("\n");
    let count = candidates.len();
    let mut text = if english(language) {
        let steps = if steps.is_empty() {
            "(the work is its own root)".to_owned()
        } else {
            steps
        };
        format!(
            "## The picture\nThe attached image.\n\n## The description\n{description}\n\n\
             ## The lineage's descriptions (root to this work)\n{steps}\n\n\
             ## Candidate sentences (the first sentence of the author's other works; {count}; \
             each line starts with its id)\n{listed}\n\n\
             ## Answer\n- choices: four, in the order you would pick them. For each:\n\
             \x20 - id: the candidate's id, copied from the head of its line.\n\
             \x20 - reason: how adding this sentence moves the idea of the work (one sentence, no evaluative words).\n\
             - The four ids differ."
        )
    } else {
        let steps = if steps.is_empty() {
            "（系譜は今の作品だけ）".to_owned()
        } else {
            steps
        };
        format!(
            "## 今の画\n添えた画像のとおり。\n\n## 今の記述\n{description}\n\n## 系譜の記述（根から今の作品まで）\n{steps}\n\n\
             ## 候補の一文（作者のほかの作品の記述の、最初の一文。{count}件。行の頭は番号）\n{listed}\n\n\
             ## 答えること\n- choices：4つ。選びたい順に並べる。各項に次を書く。\n\
             \x20 - id：候補の番号（行の頭の番号をそのまま写す）。\n\
             \x20 - reason：この一文を足すと、作品の考えがどう動くか（1文。評価の語を使わない）。\n\
             - 4つの id は互いに違う。"
        )
    };
    if let Some(reason) = resend {
        text.push_str(&if english(language) {
            format!(
                "\n\n## About the previous answer\nIt could not be used: {reason}. Answer again by the rules above."
            )
        } else {
            format!(
                "\n\n## 前の答えについて\n前の答えは使えなかった：{reason}。上の決まりどおりに答え直してください。"
            )
        });
    }
    text
}

/// The object an answer carries, with whatever a chat model wrapped it in: the
/// first brace to the last (Server's `_json_body`).
fn json_body(raw: &str) -> &str {
    let text = python_strip(raw);
    match (text.find('{'), text.rfind('}')) {
        (Some(start), Some(end)) if end > start => &text[start..=end],
        _ => text,
    }
}

/// A field read as Python's `str(value or "").strip()` reads it.
fn field_text(value: Option<&Value>) -> String {
    let text = match value {
        None | Some(Value::Null | Value::Bool(false)) => String::new(),
        Some(Value::String(text)) => text.clone(),
        Some(Value::Bool(true)) => "True".to_owned(),
        Some(Value::Number(number)) => {
            if number.as_f64() == Some(0.0) {
                String::new()
            } else {
                number.to_string()
            }
        }
        Some(Value::Array(items)) if items.is_empty() => String::new(),
        Some(Value::Object(fields)) if fields.is_empty() => String::new(),
        Some(other) => other.to_string(),
    };
    python_strip(&text).to_owned()
}

/// Why an answer cannot be used, in the language the prompt was sent in.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct Refusal {
    pub reason: &'static str,
    pub detail: String,
}

/// The four picks of an answer, in its order, or why it cannot be used: not
/// JSON, not exactly four, an id that was not offered, an id named twice, or
/// an empty reason. `description` is the description as the work keeps it,
/// labels and all (the author's document): each pick is joined to it.
pub fn check(
    language: &str,
    answer: &str,
    candidates: &[Candidate],
    description: &str,
) -> Result<Vec<Choice>, Refusal> {
    let en = english(language);
    let refuse = |reason, english_detail: String, japanese_detail: String| Refusal {
        reason,
        detail: if en { english_detail } else { japanese_detail },
    };
    let Ok(parsed) = serde_json::from_str::<Value>(json_body(answer)) else {
        return Err(refuse(
            "not_json",
            "the answer is not JSON".to_owned(),
            "答えが JSON でない".to_owned(),
        ));
    };
    let Some(choices) = parsed
        .get("choices")
        .and_then(Value::as_array)
        .filter(|choices| choices.len() == CHOICES)
    else {
        return Err(refuse(
            "choice_count",
            format!("choices does not hold exactly {CHOICES} items"),
            format!("choices がちょうど{CHOICES}つでない"),
        ));
    };
    let pairs: Vec<(String, String)> = choices
        .iter()
        .map(|choice| match choice {
            Value::Object(fields) => (
                field_text(fields.get("id")),
                field_text(fields.get("reason")),
            ),
            _ => (String::new(), String::new()),
        })
        .collect();
    let offered: HashMap<&str, (usize, &Candidate)> = candidates
        .iter()
        .enumerate()
        .map(|(place, candidate)| (candidate.id.as_str(), (place, candidate)))
        .collect();
    let missing: Vec<&str> = pairs
        .iter()
        .filter(|(id, _)| !offered.contains_key(id.as_str()))
        .map(|(id, _)| if id.is_empty() { "—" } else { id.as_str() })
        .collect();
    if !missing.is_empty() {
        return Err(refuse(
            "not_offered",
            format!(
                "ids that were not offered ({}); copy the id at the head of a line",
                missing.join(", ")
            ),
            format!(
                "候補に無い番号（{}。行の頭の番号をそのまま写す）",
                missing.join("・")
            ),
        ));
    }
    if pairs.iter().map(|(id, _)| id).collect::<HashSet<_>>().len() != CHOICES {
        return Err(refuse(
            "repeated",
            "an id appears more than once".to_owned(),
            "同じ番号が2回以上ある（4つは互いに違う番号にする）".to_owned(),
        ));
    }
    if pairs.iter().any(|(_, reason)| reason.is_empty()) {
        return Err(refuse(
            "empty_reason",
            "a reason is empty".to_owned(),
            "理由が空の項がある".to_owned(),
        ));
    }
    let last = candidates.len().saturating_sub(1).max(1);
    Ok(pairs
        .into_iter()
        .enumerate()
        .map(|(rank, (id, reason))| {
            let (place, candidate) = offered[id.as_str()];
            Choice {
                sentence: candidate.sentence.clone(),
                reason: reason.chars().take(REASON_LIMIT).collect(),
                history_ids: candidate.history_ids.clone(),
                rank: rank + 1,
                position: thousandths(place, last),
                joined: join(description, &candidate.sentence),
            }
        })
        .collect())
}

/// `place / last` to three places, a half rounded up.
fn thousandths(place: usize, last: usize) -> f64 {
    let scaled = (place * 2000 + last) / (last * 2);
    scaled as f64 / 1000.0
}

/// The description with the sentence after it. A description that ends
/// without a stop (a poem, or one ending in a label) gets one, so that the two
/// do not run on and Stage 1 does not read them as one clause.
#[must_use]
pub fn join(description: &str, sentence: &str) -> String {
    let base = python_strip(description);
    let added = python_strip(sentence);
    if base.is_empty() || added.is_empty() {
        return if base.is_empty() { added } else { base }.to_owned();
    }
    let japanese = language_of(base) == "ja";
    let stopped = base
        .chars()
        .next_back()
        .is_some_and(|last| matches!(last, '。' | '！' | '？' | '」' | '』' | '.' | '!' | '?'));
    match (stopped, japanese) {
        (true, true) => format!("{base}{added}"),
        (true, false) => format!("{base} {added}"),
        (false, true) => format!("{base}。{added}"),
        (false, false) => format!("{base}. {added}"),
    }
}

// ---------------------------------------------------------------------------
// The JSON boundary
// ---------------------------------------------------------------------------

#[derive(Deserialize)]
#[serde(tag = "action", rename_all = "snake_case", deny_unknown_fields)]
enum Request {
    Gather(GatherRequest),
    Prompt {
        language: String,
        description: String,
        #[serde(default)]
        lineage: Vec<String>,
        candidates: Vec<Candidate>,
        #[serde(default)]
        resend: Option<String>,
    },
    Check {
        language: String,
        answer: String,
        candidates: Vec<Candidate>,
        description: String,
    },
    Join {
        description: String,
        sentence: String,
    },
    Same {
        a: String,
        b: String,
    },
}

fn answer(request: Request) -> Result<Value, Refusal> {
    match request {
        Request::Gather(request) => Ok(json!({"candidates": gather(&request), "choices": CHOICES})),
        Request::Prompt {
            language,
            description,
            lineage,
            candidates,
            resend,
        } => Ok(json!({
            "system": system_prompt(&language),
            "text": message(&language, &description, &lineage, &candidates, resend.as_deref()),
        })),
        Request::Check {
            language,
            answer,
            candidates,
            description,
        } => check(&language, &answer, &candidates, &description)
            .map(|choices| json!({"choices": choices, "candidates": candidates.len()})),
        Request::Join {
            description,
            sentence,
        } => Ok(json!({"joined": join(&description, &sentence)})),
        Request::Same { a, b } => Ok(json!({"same": same_text(&a, &b)})),
    }
}

/// JSON in, JSON out, for the hosts' bindings. An answer is
/// `{"schema", "outcome": "ok", ...}` or `{"schema", "outcome": "refused",
/// "reason", "detail"}`; a request that cannot be read answers
/// `{"error": "invalid_request"}`.
#[must_use]
pub fn juxtaposition_json(input: &[u8]) -> Vec<u8> {
    let Ok(request) = serde_json::from_slice::<Request>(input) else {
        return br#"{"error":"invalid_request"}"#.to_vec();
    };
    let mut body = match answer(request) {
        Ok(Value::Object(fields)) => {
            let mut body = Map::new();
            body.insert("outcome".to_owned(), json!("ok"));
            body.extend(fields);
            body
        }
        Ok(_) => return br#"{"error":"internal"}"#.to_vec(),
        Err(refusal) => {
            let mut body = Map::new();
            body.insert("outcome".to_owned(), json!("refused"));
            body.insert("reason".to_owned(), json!(refusal.reason));
            body.insert("detail".to_owned(), json!(refusal.detail));
            body
        }
    };
    body.insert("schema".to_owned(), json!(JUXTAPOSITION_SCHEMA_ID));
    serde_json::to_vec(&Value::Object(body)).unwrap_or_else(|_| br#"{"error":"internal"}"#.to_vec())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn cases() -> Value {
        serde_json::from_str(include_str!(
            "../../../../server/tests/data/juxtaposition-cases.json"
        ))
        .expect("the shared juxtaposition cases")
    }

    fn ask(request: Value) -> Value {
        serde_json::from_slice(&juxtaposition_json(&serde_json::to_vec(&request).unwrap())).unwrap()
    }

    #[test]
    fn every_shared_sentence_rule_answers_as_server_and_web_did() {
        let table = cases();
        assert_eq!(table["choices"], CHOICES);
        for row in table["same"].as_array().unwrap() {
            let a = row["a"].as_str().unwrap();
            let b = row["b"].as_str().unwrap();
            assert_eq!(same_text(a, b), row["same"], "{}", row["why"]);
            assert_eq!(
                ask(json!({"action": "same", "a": a, "b": b}))["same"],
                row["same"]
            );
        }
        for row in table["first_sentence"].as_array().unwrap() {
            assert_eq!(
                first_sentence(row["text"].as_str().unwrap()),
                row["sentence"],
                "{}",
                row["why"]
            );
        }
        for row in table["language"].as_array().unwrap() {
            assert_eq!(language_of(row["text"].as_str().unwrap()), row["language"]);
        }
        for row in table["join"].as_array().unwrap() {
            let answer = ask(
                json!({"action": "join", "description": row["description"], "sentence": row["sentence"]}),
            );
            assert_eq!(answer["joined"], row["joined"], "{row}");
        }
    }

    #[test]
    fn every_shared_gathering_keeps_the_sentences_server_kept() {
        for row in cases()["gather"].as_array().unwrap() {
            let mut request = row["request"].clone();
            request["action"] = json!("gather");
            request["seed"] = json!(7);
            let answer = ask(request.clone());
            assert_eq!(answer["outcome"], "ok", "{answer}");
            let drawn = answer["candidates"].as_array().unwrap();
            assert_eq!(
                drawn.len(),
                row["count"].as_u64().unwrap() as usize,
                "{}",
                row["why"]
            );
            for candidate in drawn {
                let sentence = candidate["sentence"].as_str().unwrap();
                assert_eq!(
                    candidate["history_ids"], row["kept"][sentence],
                    "{}: {sentence}",
                    row["why"]
                );
            }
            request["limit"] = json!(10_000);
            let everything = ask(request);
            let kept: Map<String, Value> = everything["candidates"]
                .as_array()
                .unwrap()
                .iter()
                .map(|candidate| {
                    (
                        candidate["sentence"].as_str().unwrap().to_owned(),
                        candidate["history_ids"].clone(),
                    )
                })
                .collect();
            assert_eq!(Value::Object(kept), row["kept"], "{}", row["why"]);
        }
    }

    #[test]
    fn the_seed_decides_the_order_and_the_draw() {
        let row = &cases()["gather"][2];
        let mut request = row["request"].clone();
        request["action"] = json!("gather");
        let order = |seed: u64| -> Vec<String> {
            let mut request = request.clone();
            request["seed"] = json!(seed.to_string());
            ask(request)["candidates"]
                .as_array()
                .unwrap()
                .iter()
                .map(|candidate| candidate["id"].as_str().unwrap().to_owned())
                .collect()
        };
        assert_eq!(order(1), order(1));
        assert_ne!(order(1), order(2));
        assert_eq!(order(1).iter().collect::<HashSet<_>>().len(), 10);
    }

    #[test]
    fn every_shared_answer_is_checked_as_server_checked_it() {
        for row in cases()["check"].as_array().unwrap() {
            let mut request = row["request"].clone();
            request["action"] = json!("check");
            let answer = ask(request);
            match row.get("choices") {
                Some(choices) => {
                    assert_eq!(answer["outcome"], "ok", "{}: {answer}", row["why"]);
                    assert_eq!(&answer["choices"], choices, "{}", row["why"]);
                }
                None => {
                    assert_eq!(answer["outcome"], "refused", "{}: {answer}", row["why"]);
                    assert_eq!(answer["detail"], row["detail"], "{}", row["why"]);
                }
            }
        }
    }

    #[test]
    fn every_shared_prompt_is_the_text_server_sent() {
        for row in cases()["prompt"].as_array().unwrap() {
            let mut request = row["request"].clone();
            request["action"] = json!("prompt");
            let answer = ask(request);
            assert_eq!(answer["system"], row["system"], "{}", row["why"]);
            assert_eq!(answer["text"], row["text"], "{}", row["why"]);
        }
    }

    #[test]
    fn an_unreadable_request_says_so() {
        assert_eq!(juxtaposition_json(b"{}"), br#"{"error":"invalid_request"}"#);
        assert_eq!(
            juxtaposition_json(br#"{"action": "gather", "sources": [], "description": "x", "seed": -1, "limit": 1}"#),
            br#"{"error":"invalid_request"}"#
        );
    }
}
