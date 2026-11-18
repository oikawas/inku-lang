//! The history strip's short name for a model: the provider's abbreviation and the
//! model's API name compacted word by word (`Cl Op4.7`, `SIWC GPT6.1So`).
//!
//! Moved from the Web (`web/src/lib/historyStripFields.ts` `abbreviateStripModel`,
//! `STRIP_MODEL_WORDS`) so every host prints the same name, with two rules added
//! when display names became API names (2026-11-18, the author): a one-digit word
//! after a word of digits joins it with "." (`claude-opus-4-7` → `Op4.7`), and the
//! words of a date (`2026-03-05`, `20260305`) are dropped.

/// Recognizable words and their short forms, matched case-insensitively.
const WORDS: &[(&str, &str)] = &[
    ("gpt", "GPT"),
    ("oss", "oss"),
    ("sol", "So"),
    ("luna", "Lu"),
    ("astra", "As"),
    ("terra", "Te"),
    ("claude", "Cl"),
    ("sonnet", "So"),
    ("opus", "Op"),
    ("haiku", "Ha"),
    ("fable", "Fa"),
    ("gemini", "Ge"),
    ("gemma", "Gm"),
    ("flash", "Fl"),
    ("lite", "L"),
    ("pro", "Pr"),
    ("mini", "Mi"),
    ("nano", "Na"),
    ("turbo", "T"),
    ("llama", "Ll"),
    ("qwen", "Qw"),
    ("deepseek", "DS"),
    ("minimax", "MM"),
    ("kimi", "Ki"),
    ("mistral", "Mi"),
    ("ministral", "Min"),
    ("mixtral", "Mx"),
    ("nemotron", "Nem"),
    ("granite", "Gr"),
    ("large", "Lg"),
    ("medium", "Md"),
    ("small", "Sm"),
    ("super", "Su"),
    ("ultra", "Ul"),
    ("instruct", "I"),
    ("it", "I"),
    ("vision", "V"),
    ("reasoning", "R"),
    ("thinking", "Th"),
    ("preview", "Pv"),
    ("latest", "Lt"),
    ("code", "Cd"),
    ("coder", "Cdr"),
    ("a", "A"),
    ("b", "B"),
    ("e", "E"),
];

fn is_word_char(c: char) -> bool {
    c.is_ascii_alphanumeric() || c == '_'
}

fn starts_with_ignore_case(text: &str, prefix: &str) -> bool {
    text.len() >= prefix.len()
        && text.is_char_boundary(prefix.len())
        && text[..prefix.len()].eq_ignore_ascii_case(prefix)
}

/// `^claude\b` / `^gemini\b` on the provider's name as given (not trimmed, as the Web read it).
fn names_brand(owner: &str, brand: &str) -> bool {
    starts_with_ignore_case(owner, brand)
        && owner[brand.len()..]
            .chars()
            .next()
            .is_none_or(|c| !is_word_char(c))
}

/// `^<brand>[\s-]+`.
fn strip_brand(model: &str, brand: &str) -> String {
    if !starts_with_ignore_case(model, brand) {
        return model.to_owned();
    }
    let rest = &model[brand.len()..];
    let trimmed = rest.trim_start_matches(|c: char| c.is_whitespace() || c == '-');
    if trimmed.len() == rest.len() {
        model.to_owned()
    } else {
        trimmed.to_owned()
    }
}

/// `^(?:anthropic|google|meta|mistral\s+ai)\s+`.
fn strip_vendor(model: &str) -> String {
    for vendor in ["anthropic", "google", "meta"] {
        if starts_with_ignore_case(model, vendor) {
            let rest = &model[vendor.len()..];
            let trimmed = rest.trim_start();
            if trimmed.len() != rest.len() {
                return trimmed.to_owned();
            }
        }
    }
    if starts_with_ignore_case(model, "mistral") {
        let rest = &model["mistral".len()..];
        let after_space = rest.trim_start();
        if after_space.len() != rest.len() && starts_with_ignore_case(after_space, "ai") {
            let tail = &after_space[2..];
            let trimmed = tail.trim_start();
            if trimmed.len() != tail.len() {
                return trimmed.to_owned();
            }
        }
    }
    model.to_owned()
}

/// `\s*\([\d.]+\s*[GM]B\)\s*$`: Ollama's size note.
fn strip_size_note(model: &str) -> String {
    let trimmed = model.trim_end();
    let Some(inner) = trimmed.strip_suffix(')') else {
        return model.to_owned();
    };
    let Some(open) = inner.rfind('(') else {
        return model.to_owned();
    };
    let note = &inner[open + 1..];
    let unit_ok = note.len() >= 2 && {
        let unit = &note[note.len() - 2..];
        unit.eq_ignore_ascii_case("GB") || unit.eq_ignore_ascii_case("MB")
    };
    if !unit_ok {
        return model.to_owned();
    }
    let number = note[..note.len() - 2].trim_end();
    if number.is_empty() || !number.chars().all(|c| c.is_ascii_digit() || c == '.') {
        return model.to_owned();
    }
    inner[..open].trim_end().to_owned()
}

/// `\bdeepseek[-\s]+v(?=\d)` → `deepseek-`.
fn deepseek_version(model: &str) -> String {
    let lower = model.to_ascii_lowercase();
    let mut out = String::new();
    let mut i = 0;
    while i < model.len() {
        let at_boundary = i == 0 || !model[..i].chars().next_back().is_some_and(is_word_char);
        if at_boundary && lower[i..].starts_with("deepseek") {
            let after = i + "deepseek".len();
            let gap = model[after..]
                .find(|c: char| !(c.is_whitespace() || c == '-'))
                .unwrap_or(model.len() - after);
            let v = after + gap;
            if gap > 0
                && model[v..].starts_with(['v', 'V'])
                && model[v + 1..].starts_with(|c: char| c.is_ascii_digit())
            {
                out.push_str("deepseek-");
                i = v + 1;
                continue;
            }
        }
        let c = model[i..].chars().next().unwrap();
        out.push(c);
        i += c.len_utf8();
    }
    out
}

/// `\bq(\d+)[_-]k[_-]([a-z])\b` → `Q<digits>K<LETTER>` (Ollama's quantization).
fn quantization(model: &str) -> String {
    let chars: Vec<char> = model.chars().collect();
    let mut out = String::new();
    let mut i = 0;
    while i < chars.len() {
        if matches!(chars[i], 'q' | 'Q') && (i == 0 || !is_word_char(chars[i - 1])) {
            let mut j = i + 1;
            while j < chars.len() && chars[j].is_ascii_digit() {
                j += 1;
            }
            if j > i + 1
                && j + 3 < chars.len()
                && matches!(chars[j], '_' | '-')
                && matches!(chars[j + 1], 'k' | 'K')
                && matches!(chars[j + 2], '_' | '-')
                && chars[j + 3].is_ascii_alphabetic()
                && chars.get(j + 4).is_none_or(|c| !is_word_char(*c))
            {
                out.push('Q');
                out.extend(&chars[i + 1..j]);
                out.push('K');
                out.push(chars[j + 3].to_ascii_uppercase());
                i = j + 4;
                continue;
            }
        }
        out.push(chars[i]);
        i += 1;
    }
    out
}

fn all_digits(token: &str) -> bool {
    !token.is_empty() && token.chars().all(|c| c.is_ascii_digit())
}

/// Drop a date's words: one word of 8 digits, or 4 digits, 2 digits, 2 digits in a row.
fn without_dates(tokens: Vec<String>) -> Vec<String> {
    let mut out = Vec::new();
    let mut i = 0;
    while i < tokens.len() {
        if all_digits(&tokens[i]) && tokens[i].len() == 8 {
            i += 1;
            continue;
        }
        if i + 2 < tokens.len()
            && all_digits(&tokens[i])
            && tokens[i].len() == 4
            && all_digits(&tokens[i + 1])
            && tokens[i + 1].len() == 2
            && all_digits(&tokens[i + 2])
            && tokens[i + 2].len() == 2
        {
            i += 3;
            continue;
        }
        out.push(tokens[i].clone());
        i += 1;
    }
    out
}

/// Replace each run of ASCII letters by its short form, when the word is known.
fn shorten(token: &str) -> String {
    let mut out = String::new();
    let mut letters = String::new();
    let flush = |letters: &mut String, out: &mut String| {
        if !letters.is_empty() {
            let lower = letters.to_ascii_lowercase();
            match WORDS.iter().find(|(word, _)| *word == lower) {
                Some((_, short)) => out.push_str(short),
                None => out.push_str(letters),
            }
            letters.clear();
        }
    };
    for c in token.chars() {
        if c.is_ascii_alphabetic() {
            letters.push(c);
        } else {
            flush(&mut letters, &mut out);
            out.push(c);
        }
    }
    flush(&mut letters, &mut out);
    out
}

/// The history strip's name: `<provider abbreviation> <compact model>`.
///
/// `owner` is the provider's display name; `owner_abbreviation` is a sign-in service's own
/// abbreviation (`SIWC`), which wins when present. `name` is the model's API name.
pub(crate) fn strip_label(owner: &str, owner_abbreviation: Option<&str>, name: &str) -> String {
    let provider = match owner_abbreviation.filter(|s| !s.is_empty()) {
        Some(abbreviation) => abbreviation.to_owned(),
        None => {
            let lower = owner.to_ascii_lowercase();
            if lower
                .find("ollama")
                .is_some_and(|at| lower[at..].contains("cloud"))
            {
                "Oc".to_owned()
            } else {
                owner.trim().chars().take(2).collect()
            }
        }
    };
    let name = name.trim();
    let mut model = name.rsplit('/').next().unwrap_or(name).to_owned();
    model = strip_vendor(&model);
    model = strip_size_note(&model);
    model = deepseek_version(&model);
    model = quantization(&model);
    // The provider already identifies these brands; Gemma still needs its name.
    if names_brand(owner, "claude") {
        model = strip_brand(&model, "claude");
    }
    if names_brand(owner, "gemini") {
        model = strip_brand(&model, "gemini");
    }
    let tokens: Vec<String> = model
        .split(|c: char| c.is_whitespace() || matches!(c, ':' | '_' | '-'))
        .filter(|t| !t.is_empty())
        .map(str::to_owned)
        .collect();
    let tokens: Vec<String> = without_dates(tokens).iter().map(|t| shorten(t)).collect();
    let mut compact = String::new();
    for (index, token) in tokens.iter().enumerate() {
        if index > 0 {
            let previous = &tokens[index - 1];
            if all_digits(previous) && all_digits(token) && token.len() == 1 {
                // A version's minor number: 4 + 7 is 4.7, not 47.
                compact.push('.');
            } else if previous.ends_with(|c: char| c.is_ascii_digit())
                && token.starts_with(|c: char| c.is_ascii_digit())
            {
                // Without a separator, version 4 + size 31B would read as version 431B.
                compact.push('·');
            }
        }
        compact.push_str(token);
    }
    [provider, compact]
        .into_iter()
        .filter(|part| !part.is_empty())
        .collect::<Vec<_>>()
        .join(" ")
}
