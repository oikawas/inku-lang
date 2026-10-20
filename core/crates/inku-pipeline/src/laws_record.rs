//! What the laws stage placed, kept with the work (the author's decisions of
//! 2026-10-20).
//!
//! The laws stage rewrites the layers it changed in numbers (SPEC §12.6.4), and
//! "change the layout" cannot tell those sentences from the ones the author
//! writes in the same forms. The record keeps the sentences of each layer the
//! laws placed, and of each layer a law placed another by (the main layer of a
//! balance or of a subordination), so that a recomposition keeps them where
//! they are and places only the other layers again.
//!
//! The record is matched by the sentences' text alone: a recorded layer applies
//! while every one of its sentences is in the instructions as written. A
//! sentence the author changed is no longer the laws', and a work without a
//! record is recomposed as before. The compiler never reads the record.
//!
//! Beside it a work keeps the basis of its laws ([`LawsBasis`], 2026-10-20):
//! the composed document the laws were applied to and the answer, so that the
//! AI refinement can apply other laws to the same composition.

use serde::{Deserialize, Serialize};

pub const LAWS_LAYERS_SCHEMA_ID: &str = "inku.laws-layers.v1";

/// The layers a work's laws stage placed, in the order they are printed.
#[derive(Clone, Debug, Default, Eq, PartialEq, Serialize, Deserialize)]
#[serde(try_from = "RecordWire", into = "RecordWire")]
pub struct LawsLayerRecord {
    pub layers: Vec<LawsLayer>,
}

impl LawsLayerRecord {
    #[must_use]
    pub fn is_empty(&self) -> bool {
        self.layers.is_empty()
    }
}

/// Why a recorded layer stays where it is.
#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum LawsLayerKind {
    /// The laws wrote it.
    Laws,
    /// A law placed another layer by it (B6, B7): it keeps its place so that
    /// the other keeps its meaning.
    Partner,
}

/// One recorded layer: its sentences as printed (one, or one for each mark of a
/// layer the laws opened into marks), why it stays, and the laws that name it.
#[derive(Clone, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct LawsLayer {
    pub sentences: Vec<String>,
    pub kind: LawsLayerKind,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub laws: Vec<String>,
}

#[derive(Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct RecordWire {
    schema: String,
    layers: Vec<LawsLayer>,
}

impl From<LawsLayerRecord> for RecordWire {
    fn from(record: LawsLayerRecord) -> Self {
        Self {
            schema: LAWS_LAYERS_SCHEMA_ID.to_owned(),
            layers: record.layers,
        }
    }
}

impl TryFrom<RecordWire> for LawsLayerRecord {
    type Error = String;

    fn try_from(wire: RecordWire) -> Result<Self, Self::Error> {
        if wire.schema != LAWS_LAYERS_SCHEMA_ID {
            return Err(format!("unknown laws layers schema {}", wire.schema));
        }
        if wire.layers.iter().any(|layer| {
            layer.sentences.is_empty() || layer.sentences.iter().any(|s| s.trim().is_empty())
        }) {
            return Err("a recorded laws layer has no sentence".to_owned());
        }
        Ok(Self {
            layers: wire.layers,
        })
    }
}

pub const LAWS_BASIS_SCHEMA_ID: &str = "inku.laws-basis.v1";

/// What a work's laws were applied to and what they were (the AI refinement's
/// laws move, 2026-10-20): the composed document before the laws, the digest
/// of the document the run committed (after the color stage when it ran, the
/// machine's `source_digest`), and the answer the laws were applied by. A host
/// keeps it with the work beside the layers record and brings it back with a
/// run from that work. The laws stage from a saved work reads the composed
/// document only while the work's DDL is still the committed one.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(try_from = "BasisWire", into = "BasisWire")]
pub struct LawsBasis {
    pub composed: String,
    pub committed_digest: String,
    pub main_layer: usize,
    pub main_law: String,
    /// The laws of the answer and their values, as the answer wrote them.
    pub laws: serde_json::Map<String, serde_json::Value>,
    pub reason: String,
}

impl LawsBasis {
    /// The laws the answer applied, the main one first.
    #[must_use]
    pub fn law_names(&self) -> Vec<&str> {
        let mut names = vec![self.main_law.as_str()];
        names.extend(
            self.laws
                .keys()
                .map(String::as_str)
                .filter(|law| *law != self.main_law),
        );
        names
    }
}

#[derive(Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct BasisWire {
    schema: String,
    composed: String,
    committed_digest: String,
    main_layer: usize,
    main_law: String,
    laws: serde_json::Map<String, serde_json::Value>,
    reason: String,
}

impl From<LawsBasis> for BasisWire {
    fn from(basis: LawsBasis) -> Self {
        Self {
            schema: LAWS_BASIS_SCHEMA_ID.to_owned(),
            composed: basis.composed,
            committed_digest: basis.committed_digest,
            main_layer: basis.main_layer,
            main_law: basis.main_law,
            laws: basis.laws,
            reason: basis.reason,
        }
    }
}

impl TryFrom<BasisWire> for LawsBasis {
    type Error = String;

    fn try_from(wire: BasisWire) -> Result<Self, Self::Error> {
        if wire.schema != LAWS_BASIS_SCHEMA_ID {
            return Err(format!("unknown laws basis schema {}", wire.schema));
        }
        if wire.composed.trim().is_empty() || wire.main_law.is_empty() {
            return Err("a laws basis has no composed document or main law".to_owned());
        }
        Ok(Self {
            composed: wire.composed,
            committed_digest: wire.committed_digest,
            main_layer: wire.main_layer,
            main_law: wire.main_law,
            laws: wire.laws,
            reason: wire.reason,
        })
    }
}

/// The byte ranges of the sentences of each recorded layer that applies to
/// `source` (every one of its sentences is in it, in order, and no sentence is
/// taken twice), with the layer's place in the record.
#[must_use]
pub fn applying(
    record: &LawsLayerRecord,
    source: &str,
) -> Vec<(usize, Vec<std::ops::Range<usize>>)> {
    let mut taken: Vec<std::ops::Range<usize>> = Vec::new();
    let mut found = Vec::new();
    for (index, layer) in record.layers.iter().enumerate() {
        let mut ranges = Vec::with_capacity(layer.sentences.len());
        let mut from = 0;
        for sentence in &layer.sentences {
            let sentence = sentence.trim();
            let Some(at) = source[from..]
                .match_indices(sentence)
                .map(|(offset, _)| from + offset)
                .find(|start| {
                    let range = *start..*start + sentence.len();
                    taken
                        .iter()
                        .chain(&ranges)
                        .all(|other: &std::ops::Range<usize>| {
                            other.end <= range.start || range.end <= other.start
                        })
                })
            else {
                ranges.clear();
                break;
            };
            ranges.push(at..at + sentence.len());
            from = at + sentence.len();
        }
        if ranges.len() == layer.sentences.len() {
            taken.extend(ranges.iter().cloned());
            found.push((index, ranges));
        }
    }
    found
}
