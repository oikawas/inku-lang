//! The canvas ratio declaration (DDL 26): 「画面比W:H。」 / `Aspect ratio W:H.`
//!
//! The sentence says which width:height ratio a DDL was written for. It creates
//! no instruction, takes no sentence number, and stays out of the canonical
//! semantic bytes, so a DDL draws the same Score with or without it except for
//! `canvas.declared_ratio`.

use inku_score::{CANVAS_RATIO_MAX_UNITS, CanvasRatio};

use crate::{ResolvedInstructionLanguage, SourceSpan};

/// Japanese head of the declaration.
pub const CANVAS_RATIO_HEAD_JA: &str = "画面比";
/// English head of the declaration; matched without regard to case.
pub const CANVAS_RATIO_HEAD_EN: &str = "Aspect ratio";

/// One declaration sentence, at the source span of its clause fragment.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct CanvasRatioDeclaration {
    pub ratio: CanvasRatio,
    pub span: SourceSpan,
}

/// The ratio declared by one clause fragment's text, if the whole fragment is
/// a declaration in the document's language. Terms are ASCII or full-width
/// digits joined by `:` or `：`; a term of zero or above 10,000 makes the
/// fragment an ordinary sentence.
#[must_use]
pub fn declared_canvas_ratio(
    text: &str,
    language: ResolvedInstructionLanguage,
) -> Option<CanvasRatio> {
    let text = text.trim();
    let rest = match language {
        ResolvedInstructionLanguage::Ja => text.strip_prefix(CANVAS_RATIO_HEAD_JA)?,
        ResolvedInstructionLanguage::En => strip_english_head(text)?,
    };
    let (width_units, rest) = term(rest.trim_start())?;
    let rest = rest.trim_start();
    let rest = rest.strip_prefix(':').or_else(|| rest.strip_prefix('：'))?;
    let (height_units, rest) = term(rest.trim_start())?;
    if !rest.trim().is_empty() {
        return None;
    }
    CanvasRatio::reduced(width_units, height_units)
}

/// The visible sentence a host writes for a ratio.
#[must_use]
pub fn canvas_ratio_sentence(ratio: CanvasRatio, language: ResolvedInstructionLanguage) -> String {
    match language {
        ResolvedInstructionLanguage::Ja => format!(
            "{CANVAS_RATIO_HEAD_JA}{}:{}。",
            ratio.width_units, ratio.height_units
        ),
        ResolvedInstructionLanguage::En => format!(
            "{CANVAS_RATIO_HEAD_EN} {}:{}.",
            ratio.width_units, ratio.height_units
        ),
    }
}

/// How a host writes the paper's ratio into a new DDL.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum CanvasRatioWriting {
    /// A DDL that already declares a ratio keeps it (a DDL the author wrote).
    KeepDeclared,
    /// Any declaration is replaced by the paper's (a DDL Stage 1 wrote).
    ReplaceDeclared,
}

/// The source with the paper's ratio declared as its first sentence. Each
/// sentence of the source is a fragment between sentence ends and line
/// breaks; a removed declaration takes its sentence end and line break with it.
#[must_use]
pub fn declare_canvas_ratio(
    source: &str,
    ratio: CanvasRatio,
    language: ResolvedInstructionLanguage,
    writing: CanvasRatioWriting,
) -> String {
    if writing == CanvasRatioWriting::KeepDeclared
        && !declaration_sentences(source, language).is_empty()
    {
        return source.to_owned();
    }
    let rest = without_canvas_ratio(source, language);
    let mut declared = canvas_ratio_sentence(ratio, language);
    if !rest.is_empty() {
        declared.push('\n');
    }
    declared.push_str(&rest);
    declared
}

/// The ratio of the source's first whole declaration sentence.
#[must_use]
pub fn source_canvas_ratio(
    source: &str,
    language: ResolvedInstructionLanguage,
) -> Option<CanvasRatio> {
    source
        .split(['。', '.', '！', '!', '？', '?', '\n'])
        .find_map(|sentence| declared_canvas_ratio(sentence, language))
}

/// The source without its declaration sentences: what is left of a DDL to
/// plan and draw when its ratio is carried apart.
#[must_use]
pub fn without_canvas_ratio(source: &str, language: ResolvedInstructionLanguage) -> String {
    let mut rest = String::with_capacity(source.len());
    let mut start = 0;
    for span in declaration_sentences(source, language) {
        rest.push_str(&source[start..span.start_byte]);
        start = span.end_byte;
    }
    rest.push_str(&source[start..]);
    rest
}

/// The spans of the whole declaration sentences, each with its sentence end
/// and the line break after it.
fn declaration_sentences(source: &str, language: ResolvedInstructionLanguage) -> Vec<SourceSpan> {
    let is_end = |character: char| matches!(character, '。' | '.' | '！' | '!' | '？' | '?');
    let mut spans = Vec::new();
    let mut start = 0;
    let mut characters = source.char_indices().peekable();
    while let Some((index, character)) = characters.next() {
        if character != '\n' && !is_end(character) {
            continue;
        }
        let mut end = index + character.len_utf8();
        if is_end(character) && declared_canvas_ratio(&source[start..index], language).is_some() {
            if let Some(&(next, '\n')) = characters.peek() {
                characters.next();
                end = next + 1;
            }
            spans.push(SourceSpan {
                start_byte: start,
                end_byte: end,
            });
        } else if character == '\n'
            && declared_canvas_ratio(&source[start..index], language).is_some()
        {
            spans.push(SourceSpan {
                start_byte: start,
                end_byte: end,
            });
        }
        start = end;
    }
    if declared_canvas_ratio(&source[start..], language).is_some() {
        spans.push(SourceSpan {
            start_byte: start,
            end_byte: source.len(),
        });
    }
    spans
}

fn strip_english_head(text: &str) -> Option<&str> {
    let (first, rest) = text.split_at_checked("aspect".len())?;
    if !first.eq_ignore_ascii_case("aspect") {
        return None;
    }
    let trimmed = rest.trim_start();
    if trimmed.len() == rest.len() {
        return None;
    }
    let (second, rest) = trimmed.split_at_checked("ratio".len())?;
    second.eq_ignore_ascii_case("ratio").then_some(rest)
}

/// Leading decimal digits as one term. More digits than the largest term
/// has are not a term.
fn term(text: &str) -> Option<(u32, &str)> {
    let max_digits = CANVAS_RATIO_MAX_UNITS.to_string().len();
    let mut value = 0_u32;
    let mut digits = 0;
    let mut end = 0;
    for (index, character) in text.char_indices() {
        let digit = match character {
            '0'..='9' => u32::from(character) - u32::from('0'),
            '０'..='９' => u32::from(character) - u32::from('０'),
            _ => break,
        };
        digits += 1;
        if digits > max_digits {
            return None;
        }
        value = value * 10 + digit;
        end = index + character.len_utf8();
    }
    (digits > 0).then(|| (value, &text[end..]))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn ratio(width_units: u32, height_units: u32) -> Option<CanvasRatio> {
        Some(CanvasRatio {
            width_units,
            height_units,
        })
    }

    #[test]
    fn reads_both_languages_and_reduces() {
        let ja = ResolvedInstructionLanguage::Ja;
        let en = ResolvedInstructionLanguage::En;
        assert_eq!(declared_canvas_ratio("画面比16:9", ja), ratio(16, 9));
        assert_eq!(declared_canvas_ratio(" 画面比 １６：９ ", ja), ratio(16, 9));
        assert_eq!(declared_canvas_ratio("画面比32:18", ja), ratio(16, 9));
        assert_eq!(declared_canvas_ratio("画面比809:500", ja), ratio(809, 500));
        assert_eq!(declared_canvas_ratio("Aspect ratio 9:16", en), ratio(9, 16));
        assert_eq!(
            declared_canvas_ratio("aspect  RATIO 500:707", en),
            ratio(500, 707)
        );
    }

    #[test]
    fn other_text_is_an_ordinary_sentence() {
        let ja = ResolvedInstructionLanguage::Ja;
        let en = ResolvedInstructionLanguage::En;
        for text in [
            "画面比0:9",
            "画面比16:0",
            "画面比10001:1",
            "画面比1.618:1",
            "画面比16対9",
            "画面比16:9の円",
            "画面の比は16:9",
            "画面比",
        ] {
            assert_eq!(declared_canvas_ratio(text, ja), None, "{text}");
        }
        assert_eq!(declared_canvas_ratio("Aspect ratio 16:9", ja), None);
        assert_eq!(declared_canvas_ratio("画面比16:9", en), None);
        assert_eq!(declared_canvas_ratio("Aspectratio 16:9", en), None);
        assert_eq!(declared_canvas_ratio("Canvas ratio 16:9", en), None);
    }

    #[test]
    fn host_writes_the_paper_ratio_first() {
        let ja = ResolvedInstructionLanguage::Ja;
        let wide = CanvasRatio {
            width_units: 16,
            height_units: 9,
        };
        let body = "和紙。\n赤い円を置く。";
        let declared = declare_canvas_ratio(body, wide, ja, CanvasRatioWriting::KeepDeclared);
        assert_eq!(declared, "画面比16:9。\n和紙。\n赤い円を置く。");
        // A declaration the author wrote is kept; one Stage 1 wrote is replaced.
        let own = "画面比1:1。\n和紙。\n赤い円を置く。";
        assert_eq!(
            declare_canvas_ratio(own, wide, ja, CanvasRatioWriting::KeepDeclared),
            own
        );
        assert_eq!(
            declare_canvas_ratio(
                "和紙。\n画面比1:1。\n赤い円を置く。画面比4:3",
                wide,
                ja,
                CanvasRatioWriting::ReplaceDeclared
            ),
            "画面比16:9。\n和紙。\n赤い円を置く。"
        );
        assert_eq!(
            declare_canvas_ratio("", wide, ja, CanvasRatioWriting::KeepDeclared),
            "画面比16:9。"
        );
        let en = ResolvedInstructionLanguage::En;
        assert_eq!(
            declare_canvas_ratio(
                "Washi.\nplace one red circle radius 0.1 at horizontal 0.5, vertical 0.5.",
                wide,
                en,
                CanvasRatioWriting::KeepDeclared
            ),
            "Aspect ratio 16:9.\nWashi.\nplace one red circle radius 0.1 at horizontal 0.5, vertical 0.5."
        );
    }

    #[test]
    fn host_sentence_reads_back() {
        for language in [
            ResolvedInstructionLanguage::Ja,
            ResolvedInstructionLanguage::En,
        ] {
            let declared = CanvasRatio {
                width_units: 47,
                height_units: 20,
            };
            let sentence = canvas_ratio_sentence(declared, language);
            let body = sentence.trim_end_matches(['。', '.']);
            assert_eq!(declared_canvas_ratio(body, language), Some(declared));
        }
    }
}
