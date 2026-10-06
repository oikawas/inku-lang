//! The display-time compatibility rewrite (Skia display stage 1, 2026-10-06).
//!
//! It runs in memory just before Skia reads a work; the stored SVG never changes.
//! Each rewrite makes Skia draw what Chrome draws:
//!
//! 1. `href` on `pattern` and `use` becomes `xlink:href` (Skia reads only the latter).
//! 2. `<ellipse>` becomes the same shape as a `<path>`: Skia computes no bounds for an
//!    ellipse, so a default-unit gradient, filter or mask on it collapses.
//! 3. An integer feTurbulence `seed` becomes the integer Blink reads. Blink adds the
//!    digits up as `f32` from the last one, so a large seed lands on another float
//!    than the correctly rounded one Skia parses, and the noise changes. It shows
//!    between 2^24 and 2^31; above that both readings drew the same noise.

use std::ops::Range;

use roxmltree::{Document, Node};

use crate::check::Unsupported;

const XLINK_NAMESPACE: &str = "http://www.w3.org/1999/xlink";

/// How many places each rewrite changed, for the host's diagnostics.
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub struct Rewrites {
    pub href: usize,
    pub ellipse: usize,
    pub seed: usize,
}

struct Edit {
    range: Range<usize>,
    text: String,
}

/// Rewrite a document that passed the support check.
pub(crate) fn rewrite(
    document: &Document<'_>,
    source: &str,
) -> Result<(String, Rewrites), Unsupported> {
    let mut edits = Vec::new();
    let mut rewrites = Rewrites::default();
    for node in document.descendants().filter(Node::is_element) {
        match node.tag_name().name() {
            "pattern" | "use" => {
                if let Some(href) = node
                    .attributes()
                    .find(|attribute| attribute.name() == "href")
                {
                    edits.push(Edit {
                        range: href.range_qname(),
                        text: "xlink:href".to_owned(),
                    });
                    rewrites.href += 1;
                }
            }
            "ellipse" => {
                ellipse_edits(node, source, &mut edits)?;
                rewrites.ellipse += 1;
            }
            "feTurbulence" => {
                if let Some(seed) = node
                    .attributes()
                    .find(|attribute| attribute.name() == "seed")
                {
                    let blink = blink_seed(seed.value())?;
                    if blink != seed.value() {
                        edits.push(Edit {
                            range: seed.range_value(),
                            text: blink,
                        });
                        rewrites.seed += 1;
                    }
                }
            }
            _ => {}
        }
    }
    if rewrites.href > 0 {
        let root = document.root_element();
        if root.lookup_prefix(XLINK_NAMESPACE) != Some("xlink") {
            let at = root.range().start + "<svg".len();
            edits.push(Edit {
                range: at..at,
                text: format!(" xmlns:xlink=\"{XLINK_NAMESPACE}\""),
            });
        }
    }
    edits.sort_by_key(|edit| (edit.range.start, edit.range.end));
    let mut output = String::with_capacity(source.len() + edits.len() * 8);
    let mut at = 0;
    for edit in edits {
        debug_assert!(edit.range.start >= at, "rewrite edits overlap");
        output.push_str(&source[at..edit.range.start]);
        output.push_str(&edit.text);
        at = edit.range.end;
    }
    output.push_str(&source[at..]);
    Ok((output, rewrites))
}

/// `<ellipse cx cy rx ry …>` → `<path d="M cx-rx cy A rx ry 0 1 0 cx+rx cy A rx ry 0 1 0 cx-rx cy Z" …>`,
/// keeping every other attribute.
fn ellipse_edits(
    node: Node<'_, '_>,
    source: &str,
    edits: &mut Vec<Edit>,
) -> Result<(), Unsupported> {
    let number = |name: &str, default: Option<f64>| -> Result<f64, Unsupported> {
        match node.attribute(name) {
            Some(value) => plain_number(value),
            None => default,
        }
        .ok_or_else(|| {
            Unsupported::new(
                "ellipse_geometry",
                format!("{name}={:?}", node.attribute(name)),
            )
        })
    };
    let (cx, cy) = (number("cx", Some(0.0))?, number("cy", Some(0.0))?);
    let (rx, ry) = (number("rx", None)?, number("ry", None)?);
    // A zero radius draws nothing in Chrome, but an arc with one draws a line.
    if rx <= 0.0 || ry <= 0.0 {
        return Err(Unsupported::new(
            "ellipse_geometry",
            format!("rx={rx} ry={ry}"),
        ));
    }
    let start = node.range().start + 1;
    edits.push(Edit {
        range: start..start + "ellipse".len(),
        text: "path".to_owned(),
    });
    let mut geometry: Vec<Range<usize>> = node
        .attributes()
        .filter(|attribute| matches!(attribute.name(), "cx" | "cy" | "rx" | "ry"))
        .map(|attribute| attribute.range())
        .collect();
    geometry.sort_by_key(|range| range.start);
    let d = format!(
        "d=\"M {} {cy} A {rx} {ry} 0 1 0 {} {cy} A {rx} {ry} 0 1 0 {} {cy} Z\"",
        cx - rx,
        cx + rx,
        cx - rx
    );
    for (index, range) in geometry.into_iter().enumerate() {
        edits.push(Edit {
            range,
            text: if index == 0 { d.clone() } else { String::new() },
        });
    }
    let element = &source[node.range()];
    if !element.ends_with("/>") {
        let close = element
            .rfind("</")
            .filter(|at| element[at + 2..].starts_with("ellipse"))
            .ok_or_else(|| Unsupported::new("ellipse_geometry", "unreadable end tag"))?;
        let at = node.range().start + close + 2;
        edits.push(Edit {
            range: at..at + "ellipse".len(),
            text: "path".to_owned(),
        });
    }
    Ok(())
}

/// A number written without units, as the core writes geometry.
fn plain_number(value: &str) -> Option<f64> {
    let value = value.trim();
    let digits = value.trim_start_matches(['+', '-']);
    if digits.is_empty() || !digits.starts_with(|c: char| c.is_ascii_digit() || c == '.') {
        return None;
    }
    value
        .parse::<f64>()
        .ok()
        .filter(|number| number.is_finite())
}

/// Blink's reading of a non-negative integer (`svg_parser_utilities.cc`): the digits
/// are added as `f32` from the last one, `integer += multiplier * digit; multiplier *= 10`.
fn blink_seed(value: &str) -> Result<String, Unsupported> {
    if value.is_empty() || !value.bytes().all(|byte| byte.is_ascii_digit()) {
        return Err(Unsupported::new("seed", value));
    }
    let (mut integer, mut multiplier) = (0f32, 1f32);
    for digit in value.bytes().rev() {
        integer += multiplier * f32::from(digit - b'0');
        multiplier *= 10.0;
    }
    if !integer.is_finite() {
        return Err(Unsupported::new("seed", value));
    }
    // Every f32 integer is exact in f64, and Skia parses the decimal back to the same f32.
    Ok(format!("{:.0}", f64::from(integer)))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn blink_reads_a_large_seed_as_another_float() {
        // A seed of the public work p02: Blink reads 4294312448, Skia 4294312192.
        assert_eq!(blink_seed("4294312311").unwrap(), "4294312448");
        assert_eq!("4294312311".parse::<f32>().unwrap(), 4294312192.0);
        assert_eq!(blink_seed("73").unwrap(), "73");
        assert_eq!(blink_seed("0").unwrap(), "0");
        assert!(blink_seed("1.5").is_err());
        assert!(blink_seed("-3").is_err());
    }

    #[test]
    fn plain_numbers_only() {
        assert_eq!(plain_number("12.5"), Some(12.5));
        assert_eq!(plain_number("-3e2"), Some(-300.0));
        assert_eq!(plain_number("50%"), None);
        assert_eq!(plain_number("inf"), None);
        assert_eq!(plain_number("NaN"), None);
    }
}
