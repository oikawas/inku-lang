//! Compatibility reader for saved Score artifacts.
//!
//! This module is intentionally not a validator for new Score input. It applies
//! only the bounded migrations required to replay saved JSON artifacts before
//! deserializing the shared typed [`crate::Score`].

use std::io::{Error as IoError, ErrorKind};

use serde_json::Value;

use crate::Score;

/// Reads a saved Score JSON artifact through its bounded compatibility changes.
///
/// The reader rejects malformed JSON, non-object roots, unsupported explicit
/// editions, and payloads that do not deserialize as a typed [`Score`]. It does
/// not supply an empty Score or otherwise recover invalid saved artifacts.
pub fn read_saved_score_json(bytes: &[u8]) -> serde_json::Result<Score> {
    let mut value: Value = serde_json::from_slice(bytes)?;
    let object = value
        .as_object_mut()
        .ok_or_else(|| invalid_saved_score("saved Score JSON must be an object"))?;

    match object.get("version") {
        None => {
            object.insert("version".to_owned(), Value::String("0.1.0".to_owned()));
        }
        Some(Value::String(version)) if version == "0.1.0" => {}
        _ => return Err(invalid_saved_score("unsupported saved Score version")),
    }

    if matches!(object.get("canvas"), Some(Value::Null)) {
        object.insert("canvas".to_owned(), Value::String("square".to_owned()));
    }
    if let Some(Value::Object(canvas)) = object.get_mut("canvas") {
        if let Some(Value::Object(ground)) = canvas.get_mut("ground") {
            ground.remove("absorbency");
        }
    }

    if let Some(Value::Array(instructions)) = object.get_mut("instructions") {
        for instruction in instructions {
            let Some(instruction) = instruction.as_object_mut() else {
                continue;
            };
            if let Some(Value::Object(relation)) = instruction.get_mut("relation") {
                relation.remove("contact");
            }
            if let Some(Value::Object(variation)) = instruction.get_mut("variation") {
                if let Some(Value::Array(dimensions)) = variation.get_mut("dimensions") {
                    dimensions.retain(|dimension| {
                        !matches!(dimension, Value::String(value) if value == "thickness")
                    });
                }
            }
            if matches!(instruction.get("weight"), Some(Value::String(weight)) if weight == "hair")
            {
                instruction.insert("weight".to_owned(), Value::String("silverpoint".to_owned()));
            }
        }
    }

    serde_json::from_value(value)
}

fn invalid_saved_score(message: &'static str) -> serde_json::Error {
    serde_json::Error::io(IoError::new(ErrorKind::InvalidData, message))
}
