//! Small SVG-specific document tree serialized exactly once at the render boundary.

use std::fmt::Write as _;

use crate::types::{CanvasSize, Point};

#[derive(Clone, Debug, PartialEq)]
pub enum Node {
    Element(Element),
    Text(String),
}

impl From<Element> for Node {
    fn from(value: Element) -> Self {
        Self::Element(value)
    }
}

#[derive(Clone, Debug, PartialEq)]
pub struct Element {
    name: String,
    attributes: Vec<(String, String)>,
    children: Vec<Node>,
}

impl Element {
    pub(crate) fn name(&self) -> &str {
        &self.name
    }

    pub(crate) fn attributes(&self) -> &[(String, String)] {
        &self.attributes
    }

    pub(crate) fn attribute(&self, name: &str) -> Option<&str> {
        self.attributes
            .iter()
            .find(|(key, _)| key == name)
            .map(|(_, value)| value.as_str())
    }

    pub(crate) fn children(&self) -> &[Node] {
        &self.children
    }

    pub(crate) fn with_children(mut self, children: Vec<Node>) -> Self {
        self.children = children;
        self
    }

    #[must_use]
    pub fn new(name: impl Into<String>) -> Self {
        Self {
            name: name.into(),
            attributes: Vec::new(),
            children: Vec::new(),
        }
    }

    #[must_use]
    pub fn attr(mut self, name: impl Into<String>, value: impl Into<String>) -> Self {
        self.set_attr(name, value);
        self
    }

    /// Set or replace one attribute. An owned value is moved, not copied,
    /// which matters for path data of tens of kilobytes.
    pub fn set_attr(&mut self, name: impl Into<String>, value: impl Into<String>) {
        let name = name.into();
        let value = value.into();
        if let Some((_, current)) = self
            .attributes
            .iter_mut()
            .find(|(current, _)| *current == name)
        {
            *current = value;
        } else {
            self.attributes.push((name, value));
        }
    }

    pub fn push(&mut self, child: impl Into<Node>) {
        self.children.push(child.into());
    }

    pub fn push_text(&mut self, text: impl Into<String>) {
        self.children.push(Node::Text(text.into()));
    }

    /// Bytes [`Self::write`] produces before escaping, which only adds bytes.
    pub(crate) fn unescaped_len(&self) -> usize {
        let attributes = self
            .attributes
            .iter()
            .map(|(name, value)| name.len() + value.len() + 4)
            .sum::<usize>();
        let open = 1 + self.name.len() + attributes;
        if self.children.is_empty() {
            return open + 2;
        }
        let children = self
            .children
            .iter()
            .map(|child| match child {
                Node::Element(element) => element.unescaped_len(),
                Node::Text(text) => text.len(),
            })
            .sum::<usize>();
        open + 1 + children + 3 + self.name.len()
    }

    fn write(&self, output: &mut String) {
        output.push('<');
        output.push_str(&self.name);
        for (name, value) in &self.attributes {
            output.push(' ');
            output.push_str(name);
            output.push_str("=\"");
            escape_attribute(value, output);
            output.push('"');
        }
        if self.children.is_empty() {
            output.push_str("/>");
            return;
        }
        output.push('>');
        for child in &self.children {
            match child {
                Node::Element(element) => element.write(output),
                Node::Text(text) => escape_text(text, output),
            }
        }
        output.push_str("</");
        output.push_str(&self.name);
        output.push('>');
    }
}

#[derive(Clone, Debug, PartialEq)]
pub struct Document {
    root: Element,
}

impl Document {
    #[must_use]
    pub fn new(canvas: CanvasSize) -> Self {
        let mut root = Element::new("svg")
            .attr("xmlns", "http://www.w3.org/2000/svg")
            .attr("version", "1.1")
            .attr("width", format_number(canvas.width))
            .attr("height", format_number(canvas.height))
            .attr(
                "viewBox",
                format!(
                    "0 0 {} {}",
                    format_number(canvas.width),
                    format_number(canvas.height)
                ),
            );
        root.push(Element::new("defs"));
        Self { root }
    }

    pub fn push(&mut self, child: impl Into<Node>) {
        self.root.push(child);
    }

    /// Add one reusable SVG definition without exposing document-tree internals.
    pub fn push_definition(&mut self, definition: Element) {
        match self.root.children.first_mut() {
            Some(Node::Element(defs)) if defs.name == "defs" => defs.push(definition),
            _ => {
                let mut defs = Element::new("defs");
                defs.push(definition);
                self.root.children.insert(0, defs.into());
            }
        }
    }

    #[must_use]
    pub fn serialize(&self) -> String {
        let mut output = String::with_capacity(4096);
        self.root.write(&mut output);
        output
    }
}

#[must_use]
pub fn format_number(value: f64) -> String {
    let mut formatted = String::new();
    write_number(&mut formatted, value);
    formatted
}

/// Append the text of [`format_number`] to `output`.
///
/// Six decimals, then trailing zeros and a bare point removed. Path data
/// writes thousands of numbers, so they go straight into one buffer.
pub(crate) fn write_number(output: &mut String, value: f64) {
    let start = output.len();
    let rounded = if value == -0.0 { 0.0 } else { value };
    write!(output, "{rounded:.6}").expect("writing to a String cannot fail");
    // Non-finite values print without a point and are kept as they are; the
    // render boundary refuses them afterwards.
    if output[start..].contains('.') {
        let trimmed = output.trim_end_matches('0').len();
        output.truncate(trimmed);
        if output.ends_with('.') {
            output.pop();
        }
    }
}

fn write_point(output: &mut String, point: Point, separator: char) {
    write_number(output, point.x);
    output.push(separator);
    write_number(output, point.y);
}

/// `M x y L x y ... Z`, or an empty string for no points.
#[must_use]
pub(crate) fn closed_polyline_path(points: &[Point]) -> String {
    if points.is_empty() {
        return String::new();
    }
    let mut path = String::with_capacity(points.len() * 24 + 4);
    path.push_str("M ");
    for (index, point) in points.iter().enumerate() {
        if index > 0 {
            path.push_str(" L ");
        }
        write_point(&mut path, *point, ' ');
    }
    path.push_str(" Z");
    path
}

/// `M x y L x y ...`, or an empty string for no points.
#[must_use]
pub(crate) fn open_polyline_path(points: &[Point]) -> String {
    let mut path = String::with_capacity(points.len() * 24);
    for (index, point) in points.iter().enumerate() {
        path.push_str(if index == 0 { "M " } else { " L " });
        write_point(&mut path, *point, ' ');
    }
    path
}

/// `x,y x,y ...` for a `points` attribute.
#[must_use]
pub(crate) fn points_list(points: &[Point]) -> String {
    let mut list = String::with_capacity(points.len() * 22);
    for (index, point) in points.iter().enumerate() {
        if index > 0 {
            list.push(' ');
        }
        write_point(&mut list, *point, ',');
    }
    list
}

fn escape_attribute(value: &str, output: &mut String) {
    for character in value.chars() {
        match character {
            '&' => output.push_str("&amp;"),
            '<' => output.push_str("&lt;"),
            '>' => output.push_str("&gt;"),
            '"' => output.push_str("&quot;"),
            '\'' => output.push_str("&apos;"),
            _ => output.push(character),
        }
    }
}

fn escape_text(value: &str, output: &mut String) {
    for character in value.chars() {
        match character {
            '&' => output.push_str("&amp;"),
            '<' => output.push_str("&lt;"),
            '>' => output.push_str("&gt;"),
            _ => output.push(character),
        }
    }
}
