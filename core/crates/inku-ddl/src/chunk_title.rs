//! Chunk titles (DDL 27): a line that is only a bracketed name, 「灯台」 /
//! `"lighthouse"` (or `“lighthouse”`), names the chunk of sentences after it.
//!
//! A chunk runs from its title line to the next title line. Blank lines are
//! decoration. Sentences before the first title belong to no chunk, and an
//! empty title (`「」` / `""`) ends a chunk for the sentences after it. A title
//! with a name already used goes on with that chunk. A title draws nothing: the
//! lexer reads each title line as a blank line of the same bytes, so it takes
//! no sentence number, stays out of the canonical semantic bytes and adds no
//! diagnostic, and a DDL draws the same Score with or without its titles.

use crate::{ResolvedInstructionLanguage, SemanticInstruction, SourceSpan};

/// The bracket pairs of a title line. Each name leaves out its own pair's
/// characters only, so an English name may quote with curly quotes inside
/// straight ones.
const TITLE_BRACKETS: [(char, char); 3] = [('「', '」'), ('"', '"'), ('“', '”')];

/// One title line, at the span of the line without its line break.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct DdlTitleLine {
    pub span: SourceSpan,
    /// The chunk's name; empty for a title that ends a chunk.
    pub name: String,
}

/// One named chunk of a compiled document: the instructions whose shape heads
/// stand after one of its titles, in source order.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct DdlChunk {
    pub name: String,
    pub instruction_indices: Vec<usize>,
}

/// The name a line gives when the whole line, without the spaces around it,
/// is a title; `None` for any other line.
#[must_use]
pub fn ddl_title_name(line: &str) -> Option<&str> {
    let line = line.trim();
    TITLE_BRACKETS.iter().find_map(|&(open, close)| {
        let inner = line.strip_prefix(open)?.strip_suffix(close)?;
        (!inner.contains([open, close, '\n'])).then(|| inner.trim())
    })
}

/// The title lines of a source, in source order.
#[must_use]
pub fn ddl_title_lines(source: &str) -> Vec<DdlTitleLine> {
    let mut titles = Vec::new();
    let mut start = 0;
    for line in source.split('\n') {
        let text = line.strip_suffix('\r').unwrap_or(line);
        if let Some(name) = ddl_title_name(text) {
            titles.push(DdlTitleLine {
                span: SourceSpan {
                    start_byte: start,
                    end_byte: start + text.len(),
                },
                name: name.to_owned(),
            });
        }
        start += line.len() + 1;
    }
    titles
}

/// The source with each title line blanked to spaces of the same bytes, so
/// every other span stays where it is and the lexer reads a blank line.
pub(crate) fn blank_title_lines(source: &str, titles: &[DdlTitleLine]) -> String {
    let mut bytes = source.as_bytes().to_vec();
    for title in titles {
        bytes[title.span.start_byte..title.span.end_byte].fill(b' ');
    }
    String::from_utf8(bytes).expect("a title line is blanked whole")
}

/// The source without its title lines: what decides the language of a DDL,
/// whose titles may quote words of another script.
#[must_use]
pub fn without_ddl_title_lines(source: &str) -> String {
    source
        .split('\n')
        .filter(|line| ddl_title_name(line).is_none())
        .collect::<Vec<_>>()
        .join("\n")
}

/// A name as a title prints it: without 「」 and `"`, and without the spaces
/// around it.
#[must_use]
pub fn ddl_title_text(name: &str) -> String {
    name.replace(['「', '」', '"'], "").trim().to_owned()
}

/// Print titles into lines of one sentence a line. `chunks` gives each line's
/// chunk name, `None` for a line of no chunk. Before the first line of each
/// chunk run come a blank line and its title; where lines of no chunk follow a
/// chunk come a blank line and the empty title. Lines before the first chunk
/// stay as they are.
#[must_use]
pub fn print_ddl_titles(
    lines: &[&str],
    chunks: &[Option<&str>],
    language: ResolvedInstructionLanguage,
) -> String {
    let (open, close) = match language {
        ResolvedInstructionLanguage::Ja => ("「", "」"),
        ResolvedInstructionLanguage::En => ("\"", "\""),
    };
    let mut printed = Vec::with_capacity(lines.len() * 2);
    let mut current: Option<Option<&str>> = None;
    for (line, chunk) in lines.iter().zip(chunks) {
        if current != Some(*chunk) {
            match chunk {
                Some(name) => printed.extend([String::new(), format!("{open}{name}{close}")]),
                None if current.is_some() => {
                    printed.extend([String::new(), format!("{open}{close}")]);
                }
                None => {}
            }
            current = Some(*chunk);
        }
        printed.push((*line).to_owned());
    }
    printed.join("\n")
}

/// The source's lines without its title lines and blank lines, each with the
/// chunk it belongs to: what [`print_ddl_titles`] prints titles into.
#[must_use]
pub fn split_ddl_titles(source: &str) -> (Vec<String>, Vec<Option<String>>) {
    let mut lines = Vec::new();
    let mut chunks = Vec::new();
    let mut current: Option<String> = None;
    for line in source.split('\n') {
        if let Some(name) = ddl_title_name(line) {
            current = (!name.is_empty()).then(|| name.to_owned());
        } else if !line.trim().is_empty() {
            lines.push(line.to_owned());
            chunks.push(current.clone());
        }
    }
    (lines, chunks)
}

/// The chunks of a document's instructions: each instruction belongs to the
/// last title before its shape head, unless that title is empty.
pub(crate) fn instruction_chunks(
    titles: &[DdlTitleLine],
    instructions: &[SemanticInstruction],
) -> Vec<DdlChunk> {
    let mut chunks: Vec<DdlChunk> = Vec::new();
    for (index, instruction) in instructions.iter().enumerate() {
        let head = instruction.entity.head.source().span.start_byte;
        let Some(title) = titles
            .iter()
            .take_while(|title| title.span.end_byte <= head)
            .last()
            .filter(|title| !title.name.is_empty())
        else {
            continue;
        };
        match chunks.iter_mut().find(|chunk| chunk.name == title.name) {
            Some(chunk) => chunk.instruction_indices.push(index),
            None => chunks.push(DdlChunk {
                name: title.name.clone(),
                instruction_indices: vec![index],
            }),
        }
    }
    chunks
}

/// Chunks after the instructions are renumbered: an index the map drops
/// leaves its chunk, and a chunk left with none is dropped.
pub(crate) fn remap_chunks(chunks: &[DdlChunk], index_map: &[Option<usize>]) -> Vec<DdlChunk> {
    chunks
        .iter()
        .filter_map(|chunk| {
            let instruction_indices = chunk
                .instruction_indices
                .iter()
                .filter_map(|index| index_map[*index])
                .collect::<Vec<_>>();
            (!instruction_indices.is_empty()).then(|| DdlChunk {
                name: chunk.name.clone(),
                instruction_indices,
            })
        })
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_title_is_a_whole_line_of_one_bracketed_name() {
        assert_eq!(ddl_title_name("「灯台」"), Some("灯台"));
        assert_eq!(ddl_title_name("　「 黒い水面 」 "), Some("黒い水面"));
        assert_eq!(
            ddl_title_name("「種から出た細い芽が、先端まで一本の線を伸ばしている。」"),
            Some("種から出た細い芽が、先端まで一本の線を伸ばしている。")
        );
        assert_eq!(ddl_title_name("\"lighthouse\""), Some("lighthouse"));
        assert_eq!(ddl_title_name("“lighthouse”"), Some("lighthouse"));
        assert_eq!(ddl_title_name("\"the “low” moon\""), Some("the “low” moon"));
        assert_eq!(ddl_title_name("「」"), Some(""));
        assert_eq!(ddl_title_name("\"\""), Some(""));
        for line in [
            "「赤い円」を中心に置く。",
            "画面の横0.5、縦0.5の位置に、赤の円を1個置く。",
            "「灯台」。",
            "「灯「台」",
            "「灯台",
            "\"",
            "“lighthouse\"",
            "",
            "画面比1:1。",
        ] {
            assert_eq!(ddl_title_name(line), None, "{line}");
        }
    }

    #[test]
    fn title_lines_keep_their_spans_and_blank_to_the_same_bytes() {
        let source = "画面比1:1。\n\n「灯台」\r\n白の円を1個置く。\n「」";
        let titles = ddl_title_lines(source);
        assert_eq!(
            titles
                .iter()
                .map(|title| (
                    &source[title.span.start_byte..title.span.end_byte],
                    title.name.as_str()
                ))
                .collect::<Vec<_>>(),
            [("「灯台」", "灯台"), ("「」", "")]
        );
        let blank = blank_title_lines(source, &titles);
        assert_eq!(blank.len(), source.len());
        assert_eq!(
            blank,
            format!(
                "画面比1:1。\n\n{}\r\n白の円を1個置く。\n{}",
                " ".repeat(12),
                " ".repeat(6)
            )
        );
    }

    #[test]
    fn printed_titles_split_back() {
        let ja = ResolvedInstructionLanguage::Ja;
        let lines = ["画面比1:1。", "背景を白で埋める。", "a", "b", "c", "d", "e"];
        let chunks = [
            None,
            None,
            Some("灯台"),
            Some("灯台"),
            Some("水面"),
            None,
            Some("灯台"),
        ];
        let printed = print_ddl_titles(&lines, &chunks, ja);
        assert_eq!(
            printed,
            "画面比1:1。\n背景を白で埋める。\n\n「灯台」\na\nb\n\n「水面」\nc\n\n「」\nd\n\n「灯台」\ne"
        );
        let (back, back_chunks) = split_ddl_titles(&printed);
        assert_eq!(back, lines);
        assert_eq!(back_chunks, chunks.map(|chunk| chunk.map(str::to_owned)));
        let en = ResolvedInstructionLanguage::En;
        assert_eq!(
            print_ddl_titles(
                &["Aspect ratio 1:1.", "x", "y"],
                &[None, Some("moon"), None],
                en
            ),
            "Aspect ratio 1:1.\n\n\"moon\"\nx\n\n\"\"\ny"
        );
    }

    #[test]
    fn a_name_prints_without_its_brackets() {
        assert_eq!(ddl_title_text(" 「灯台」 "), "灯台");
        assert_eq!(ddl_title_text("\"moon\""), "moon");
        assert_eq!(ddl_title_text("the “low” moon"), "the “low” moon");
    }

    #[test]
    fn the_language_is_read_without_the_titles() {
        assert_eq!(
            without_ddl_title_lines("\"灯台\"\nplace one red circle at center.\n「」"),
            "place one red circle at center."
        );
    }
}
