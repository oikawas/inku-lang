//! The support table: what the core writes and Skia's SVG module draws as Chrome does.
//!
//! The table was taken from the actual output of the core (the author's 124 works,
//! 17 public works and 3 heavy works; Skia display stage 1, 2026-10-06), and each entry
//! was checked against Skia's SVG source. A work outside it is shown with resvg, as
//! before, and the host counts the reason.

use std::collections::HashMap;

use roxmltree::{Document, Node};

pub(crate) const SVG_NAMESPACE: &str = "http://www.w3.org/2000/svg";

/// Every element name the core was seen to write. `title`, `desc` and `metadata`
/// (the editable profile) draw nothing.
const ELEMENTS: &[&str] = &[
    "svg",
    "title",
    "desc",
    "metadata",
    "defs",
    "g",
    "path",
    "circle",
    "ellipse",
    "rect",
    "line",
    "polygon",
    "polyline",
    "clipPath",
    "mask",
    "pattern",
    "radialGradient",
    "stop",
    "use",
    "filter",
    "feTurbulence",
    "feColorMatrix",
    "feComponentTransfer",
    "feFuncA",
    "feComposite",
    "feDisplacementMap",
    "feFlood",
    "feGaussianBlur",
    "feMerge",
    "feMergeNode",
    "feMorphology",
];

/// Every attribute name the core was seen to write, on any element. Skia reads
/// each where the element defines it; the rules below cover the ones it does not.
const ATTRIBUTES: &[&str] = &[
    "baseFrequency",
    "baseProfile",
    "class",
    "clip-path",
    "clipPathUnits",
    "color-interpolation-filters",
    "cx",
    "cy",
    "d",
    "fill",
    "fill-opacity",
    "fill-rule",
    "filter",
    "filterUnits",
    "flood-color",
    "flood-opacity",
    "height",
    "href",
    "id",
    "in",
    "in2",
    "intercept",
    "k1",
    "k2",
    "k3",
    "k4",
    "mask",
    "maskUnits",
    "numOctaves",
    "offset",
    "opacity",
    "operator",
    "patternTransform",
    "patternUnits",
    "points",
    "primitiveUnits",
    "r",
    "radius",
    "result",
    "rx",
    "ry",
    "scale",
    "seed",
    "slope",
    "stdDeviation",
    "stitchTiles",
    "stop-color",
    "stop-opacity",
    "stroke",
    "stroke-dasharray",
    "stroke-linecap",
    "stroke-opacity",
    "stroke-width",
    "style",
    "transform",
    "type",
    "values",
    "version",
    "viewBox",
    "width",
    "x",
    "x1",
    "x2",
    "xChannelSelector",
    "y",
    "y1",
    "y2",
    "yChannelSelector",
];

/// Shapes whose paint decides what an alpha mask keeps.
const SHAPES: &[&str] = &[
    "path", "circle", "ellipse", "rect", "line", "polygon", "polyline",
];

/// Filter primitives that move or soften white content without changing its colour.
const COLOUR_KEEPING_PRIMITIVES: &[&str] = &["feTurbulence", "feDisplacementMap", "feGaussianBlur"];

/// Attributes that may carry `url(#…)`; Skia sizes their default
/// objectBoundingBox units from the element's bounds.
const PAINT_REFERENCES: &[&str] = &["fill", "stroke", "filter", "mask", "clip-path"];

/// How deep `use` and `href` chains are followed before the work is left to resvg.
const MAX_REFERENCE_DEPTH: usize = 32;

/// Why a work is shown with resvg instead of Skia. `code` is stable for the host's count.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Unsupported {
    pub code: &'static str,
    pub detail: String,
}

impl Unsupported {
    pub(crate) fn new(code: &'static str, detail: impl Into<String>) -> Self {
        Self {
            code,
            detail: detail.into(),
        }
    }
}

/// Check the whole document against the table and the rules.
pub(crate) fn check(document: &Document<'_>, source: &str) -> Result<(), Unsupported> {
    let ids: HashMap<&str, Node<'_, '_>> = document
        .descendants()
        .filter(Node::is_element)
        .filter_map(|node| node.attribute("id").map(|id| (id, node)))
        .collect();
    for node in document.descendants().filter(Node::is_element) {
        check_element(node, source)?;
        for attribute in node.attributes() {
            check_attribute(node, attribute)?;
        }
        match node.tag_name().name() {
            "pattern" => check_pattern_units(node, &ids)?,
            "mask" if node.attribute("style").is_some() => check_alpha_mask(node, &ids)?,
            "line" => check_line(node)?,
            "use" => {
                check_reference(node, &ids, None)?;
            }
            _ => {}
        }
    }
    Ok(())
}

fn check_element(node: Node<'_, '_>, source: &str) -> Result<(), Unsupported> {
    let name = node.tag_name().name();
    if node.tag_name().namespace() != Some(SVG_NAMESPACE) || !ELEMENTS.contains(&name) {
        return Err(Unsupported::new("element", name));
    }
    // The rewrite edits the tag by its text, so the element must be written unprefixed.
    let start = node.range().start;
    if !source[start..].starts_with('<') || !source[start + 1..].starts_with(name) {
        return Err(Unsupported::new("element", format!("prefixed {name}")));
    }
    Ok(())
}

fn check_attribute(
    node: Node<'_, '_>,
    attribute: roxmltree::Attribute<'_, '_>,
) -> Result<(), Unsupported> {
    let element = node.tag_name().name();
    let name = attribute.name();
    if attribute.namespace().is_some() || !ATTRIBUTES.contains(&name) {
        return Err(Unsupported::new("attribute", format!("{element}@{name}")));
    }
    match name {
        // Skia reads only `xlink:href`; the rewrite covers these two.
        "href" if !matches!(element, "pattern" | "use") => {
            Err(Unsupported::new("attribute", format!("{element}@href")))
        }
        // Skia has no CSS; the one declaration the core writes is `mask-type:alpha`,
        // which Skia ignores (always luminance). That is the same for white content.
        "style" => {
            if element != "mask" || !style_is_mask_type_alpha(attribute.value()) {
                return Err(Unsupported::new(
                    "style",
                    format!("{element} style=\"{}\"", attribute.value()),
                ));
            }
            Ok(())
        }
        _ => Ok(()),
    }
}

fn style_is_mask_type_alpha(style: &str) -> bool {
    let declarations: Vec<(&str, &str)> = style
        .split(';')
        .map(str::trim)
        .filter(|declaration| !declaration.is_empty())
        .filter_map(|declaration| declaration.split_once(':'))
        .map(|(property, value)| (property.trim(), value.trim()))
        .collect();
    declarations == [("mask-type", "alpha")]
}

/// Skia treats every pattern as `userSpaceOnUse` (`patternUnits` is not read). The
/// default is objectBoundingBox, so each pattern must say `userSpaceOnUse`, itself
/// or through the patterns it inherits from.
fn check_pattern_units(
    node: Node<'_, '_>,
    ids: &HashMap<&str, Node<'_, '_>>,
) -> Result<(), Unsupported> {
    let mut current = node;
    for _ in 0..MAX_REFERENCE_DEPTH {
        if let Some(units) = current.attribute("patternUnits") {
            return if units == "userSpaceOnUse" {
                Ok(())
            } else {
                Err(Unsupported::new("pattern_units", units))
            };
        }
        current = match current.attribute("href") {
            Some(_) => check_reference(current, ids, Some("pattern"))?,
            None => return Err(Unsupported::new("pattern_units", "objectBoundingBox")),
        };
    }
    Err(Unsupported::new("reference_depth", "pattern href"))
}

/// A local `href` to an element that exists (and is a `kind`, when given).
fn check_reference<'a, 'input>(
    node: Node<'a, 'input>,
    ids: &HashMap<&str, Node<'a, 'input>>,
    kind: Option<&str>,
) -> Result<Node<'a, 'input>, Unsupported> {
    let href = node.attribute("href").unwrap_or_default();
    let target = href
        .strip_prefix('#')
        .and_then(|id| ids.get(id))
        .filter(|target| kind.is_none_or(|kind| target.tag_name().name() == kind));
    target.copied().ok_or_else(|| {
        Unsupported::new(
            "reference",
            format!("{} href=\"{href}\"", node.tag_name().name()),
        )
    })
}

/// Skia computes no bounds for `<line>`, so a default-unit gradient, filter or mask
/// on it would collapse. The core's lines carry none.
fn check_line(node: Node<'_, '_>) -> Result<(), Unsupported> {
    for name in PAINT_REFERENCES {
        if node
            .attribute(*name)
            .is_some_and(|value| value.contains("url("))
        {
            return Err(Unsupported::new("bounding_box", format!("line@{name}")));
        }
    }
    Ok(())
}

#[derive(Clone, Copy, PartialEq, Eq)]
enum Paint {
    White,
    None,
    Other,
}

fn paint(value: &str) -> Paint {
    match value.trim().to_ascii_lowercase().as_str() {
        "white" | "#fff" | "#ffffff" => Paint::White,
        "none" => Paint::None,
        _ => Paint::Other,
    }
}

/// An alpha mask equals Skia's luminance mask only if everything it draws is white.
fn check_alpha_mask(
    mask: Node<'_, '_>,
    ids: &HashMap<&str, Node<'_, '_>>,
) -> Result<(), Unsupported> {
    for child in mask.children().filter(Node::is_element) {
        check_white(child, Paint::Other, Paint::None, ids, 0)?;
    }
    Ok(())
}

fn check_white(
    node: Node<'_, '_>,
    fill: Paint,
    stroke: Paint,
    ids: &HashMap<&str, Node<'_, '_>>,
    depth: usize,
) -> Result<(), Unsupported> {
    if depth > MAX_REFERENCE_DEPTH {
        return Err(Unsupported::new("reference_depth", "alpha mask content"));
    }
    let fill = node.attribute("fill").map_or(fill, paint);
    let stroke = node.attribute("stroke").map_or(stroke, paint);
    if let Some(filter) = node.attribute("filter") {
        check_colour_keeping_filter(filter, ids)?;
    }
    let name = node.tag_name().name();
    if SHAPES.contains(&name) && (fill == Paint::Other || stroke == Paint::Other) {
        let id = node.attribute("id").unwrap_or_default();
        return Err(Unsupported::new(
            "alpha_mask_content",
            format!("{name} id=\"{id}\" is not white"),
        ));
    }
    if name == "use" {
        let target = check_reference(node, ids, None)?;
        return check_white(target, fill, stroke, ids, depth + 1);
    }
    for child in node.children().filter(Node::is_element) {
        check_white(child, fill, stroke, ids, depth + 1)?;
    }
    Ok(())
}

fn check_colour_keeping_filter(
    reference: &str,
    ids: &HashMap<&str, Node<'_, '_>>,
) -> Result<(), Unsupported> {
    let filter = reference
        .trim()
        .strip_prefix("url(#")
        .and_then(|rest| rest.strip_suffix(')'))
        .and_then(|id| ids.get(id))
        .filter(|node| node.tag_name().name() == "filter")
        .ok_or_else(|| Unsupported::new("reference", format!("filter=\"{reference}\"")))?;
    for primitive in filter.children().filter(Node::is_element) {
        let name = primitive.tag_name().name();
        if !COLOUR_KEEPING_PRIMITIVES.contains(&name) {
            return Err(Unsupported::new(
                "alpha_mask_content",
                format!("filter primitive {name}"),
            ));
        }
    }
    Ok(())
}
