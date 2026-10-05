//! Dictionary-backed Server description counts, with no model or Python runtime.

use std::collections::HashMap;
use std::path::Path;
use std::sync::{Arc, Mutex, OnceLock};

use regex::Regex;
use sudachi::analysis::{Mode, Tokenize, stateless_tokenizer::StatelessTokenizer};
use sudachi::config::Config;
use sudachi::dic::dictionary::JapaneseDictionary;

type JapaneseCache = Option<(String, Arc<JapaneseDictionary>)>;
type EnglishCache = Option<(String, Arc<HashMap<String, usize>>)>;
static JAPANESE: OnceLock<Mutex<JapaneseCache>> = OnceLock::new();
static ENGLISH: OnceLock<Mutex<EnglishCache>> = OnceLock::new();

fn regex(pattern: &str) -> Regex {
    Regex::new(pattern).expect("static Server meter pattern")
}

/// Labels are retained in saved source, but are never read by the meter.
fn pipeline_description(text: &str) -> String {
    let number = regex(r"^[ \t]*[0-9０-９]+[.．、)）:：　][ \t　]*");
    let comment = regex(r"\[[^\[\]\n]*\]|［[^［］\n]*］");
    let mut spans = Vec::new();
    let mut offset = 0;
    for line in text.split_inclusive('\n') {
        if let Some(found) = number.find(line) {
            spans.push((offset + found.start(), offset + found.end()));
        }
        spans.extend(
            comment
                .find_iter(line)
                .map(|m| (offset + m.start(), offset + m.end())),
        );
        offset += line.len();
    }
    if spans.is_empty() {
        return text.to_owned();
    }
    spans.sort_unstable();
    let mut kept = String::new();
    let mut at = 0;
    for (start, end) in spans {
        kept.push_str(&text[at..start]);
        at = end;
    }
    kept.push_str(&text[at..]);
    let spaces = regex(r"[ \t　]{2,}");
    kept.split('\n')
        .map(|line| {
            spaces
                .replace_all(line, " ")
                .trim_matches([' ', '\t', '　'])
                .to_owned()
        })
        .collect::<Vec<_>>()
        .join("\n")
}

fn japanese_dictionary(directory: &str) -> Result<Arc<JapaneseDictionary>, String> {
    let mut cache = JAPANESE
        .get_or_init(|| Mutex::new(None))
        .lock()
        .map_err(|_| "meter_internal_invariant")?;
    if let Some((path, dictionary)) = cache.as_ref()
        && path == directory
    {
        return Ok(dictionary.clone());
    }
    let root = Path::new(directory);
    let config = Config::new(
        Some(root.join("sudachi.json")),
        Some(root.to_path_buf()),
        Some(root.join("system.dic")),
    )
    .map_err(|_| "meter_dictionary_configuration_unavailable")?;
    let dictionary = Arc::new(
        JapaneseDictionary::from_cfg(&config)
            .map_err(|_| "meter_japanese_dictionary_unavailable")?,
    );
    *cache = Some((directory.to_owned(), dictionary.clone()));
    Ok(dictionary)
}

fn kana_mora(reading: &str) -> usize {
    reading
        .chars()
        .filter(|ch| {
            *ch == 'ー' || (('ァ'..='ヺ').contains(ch) && !"ァィゥェォャュョヮ".contains(*ch))
        })
        .count()
}

fn katakana(reading: &str) -> String {
    reading
        .chars()
        .map(|ch| {
            if ('ぁ'..='ゖ').contains(&ch) {
                char::from_u32(ch as u32 + 0x60).unwrap()
            } else {
                ch
            }
        })
        .collect()
}

fn japanese(source: &str, directory: &str) -> Result<serde_json::Value, String> {
    let dictionary = japanese_dictionary(directory)?;
    let tokenizer = StatelessTokenizer::new(dictionary);
    let breaks = regex(r"[\s、。，．,.!！?？・]+");
    let unread_category = regex(r"[\p{L}\p{N}]");
    let kanji = regex(r"[㐀-䶿一-鿿豈-﫿々〆〇]");
    let mut phrases = Vec::new();
    let mut unread = Vec::new();
    for phrase in breaks.split(source).filter(|phrase| !phrase.is_empty()) {
        let morphemes = tokenizer
            .tokenize(phrase, Mode::C, false)
            .map_err(|_| "meter_tokenization_failed")?;
        let mut count = 0;
        for morpheme in morphemes.iter() {
            let reading = morpheme.reading_form();
            let reading = if reading.is_empty() {
                katakana(&morpheme.surface())
            } else {
                katakana(reading)
            };
            count += kana_mora(&reading);
            for ch in reading.chars() {
                if ch == 'ー' || ('ァ'..='ヺ').contains(&ch) {
                    continue;
                }
                let single = ch.to_string();
                if unread_category.is_match(&single) {
                    count += if kanji.is_match(&single) { 2 } else { 1 };
                    unread.push(single);
                }
            }
        }
        phrases.push(count);
    }
    Ok(
        serde_json::json!({"mora": phrases.iter().sum::<usize>(), "phrases": phrases, "unread": unread}),
    )
}

fn english_dictionary(directory: &str) -> Result<Arc<HashMap<String, usize>>, String> {
    let mut cache = ENGLISH
        .get_or_init(|| Mutex::new(None))
        .lock()
        .map_err(|_| "meter_internal_invariant")?;
    if let Some((path, dictionary)) = cache.as_ref()
        && path == directory
    {
        return Ok(dictionary.clone());
    }
    let text = std::fs::read_to_string(Path::new(directory).join("cmudict.dict"))
        .map_err(|_| "meter_english_dictionary_unavailable")?;
    let mut entries = HashMap::new();
    for line in text.lines() {
        let mut pieces = line.split('#').next().unwrap_or("").split_whitespace();
        if let Some(word) = pieces.next()
            && !word.contains('(')
        {
            entries.insert(
                word.to_owned(),
                pieces
                    .filter(|phoneme| phoneme.chars().last().is_some_and(|ch| ch.is_ascii_digit()))
                    .count(),
            );
        }
    }
    let entries = Arc::new(entries);
    *cache = Some((directory.to_owned(), entries.clone()));
    Ok(entries)
}

fn estimated_syllables(word: &str) -> usize {
    let mut word = word.to_lowercase().replace('\'', "");
    if word.len() > 2 && word.ends_with('e') && !regex(r"[^aeiouy]le$").is_match(&word) {
        word.pop();
    }
    regex(r"[aeiouy]+").find_iter(&word).count().max(1)
}

fn english(source: &str, directory: &str) -> Result<serde_json::Value, String> {
    let dictionary = english_dictionary(directory)?;
    let words = regex(r"[A-Za-z]+(?:'[A-Za-z]+)*");
    let mut lines = Vec::new();
    let mut unknown = Vec::new();
    for line in source.split('\n').filter(|line| !line.trim().is_empty()) {
        let mut count = 0;
        for word in words.find_iter(line).map(|word| word.as_str()) {
            count += match dictionary.get(&word.to_lowercase()) {
                Some(count) => *count,
                None => {
                    unknown.push(word.to_owned());
                    estimated_syllables(word)
                }
            };
        }
        lines.push(count);
    }
    Ok(
        serde_json::json!({"syllables": lines.iter().sum::<usize>(), "lines": lines, "unknown": unknown}),
    )
}

/// A missing dictionary is an explicit failure, never a character-count reading.
#[uniffi::export]
pub fn count_description_meter(
    text: String,
    language_code: String,
    dictionary_directory: String,
) -> Vec<u8> {
    let result = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
        if text.chars().count() > 4000 {
            return Err("meter_text_too_long".to_owned());
        }
        let source = pipeline_description(&text);
        match language_code.as_str() {
            "ja" => japanese(source.trim(), &dictionary_directory),
            "en" => english(source.trim(), &dictionary_directory),
            _ => Err("meter_language_invalid".to_owned()),
        }
    }))
    .unwrap_or_else(|_| Err("meter_internal_invariant".to_owned()));
    serde_json::to_vec(&result.unwrap_or_else(|code| serde_json::json!({"error": code})))
        .unwrap_or_default()
}

#[cfg(test)]
mod tests {
    use super::*;

    // Concrete failure: character counts misname a kanji haiku, and vowel-group
    // estimates miss CMU's pronunciation. One fixture checks both native dictionaries.
    #[test]
    fn counts_match_server_dictionary_readings() {
        let directory = std::env::var("INKU_METER_TEST_RESOURCES")
            .expect("explicit prepared dictionary fixture");
        let count = |text: &str, language: &str| {
            serde_json::from_slice::<serde_json::Value>(&count_description_meter(
                text.to_owned(),
                language.to_owned(),
                directory.clone(),
            ))
            .unwrap()
        };
        assert_eq!(
            count("１．古池や[季語は蛙]\n蛙飛び込む\n水の音", "ja"),
            serde_json::json!({"mora":17,"phrases":[5,7,5],"unread":[]})
        );
        assert_eq!(count("今日は東京で雨", "ja")["mora"], 10);
        assert_eq!(
            count("濡", "ja"),
            serde_json::json!({"mora":2,"phrases":[2],"unread":["濡"]})
        );
        assert_eq!(
            count(
                "1. An old silent pond[not read]\nA frog jumps into the pond\nSplash! Silence again.",
                "en"
            ),
            serde_json::json!({"syllables":17,"lines":[5,7,5],"unknown":[]})
        );
        assert_eq!(
            count("zzqvblat", "en"),
            serde_json::json!({"syllables":1,"lines":[1],"unknown":["zzqvblat"]})
        );
        assert_eq!(kana_mora(&katakana("きゃっとラーメン")), 7);
        let missing = count_description_meter(
            "古池や".to_owned(),
            "ja".to_owned(),
            "/missing-inku-meter-resource".to_owned(),
        );
        assert!(
            serde_json::from_slice::<serde_json::Value>(&missing)
                .unwrap()
                .get("error")
                .is_some()
        );
    }
}
