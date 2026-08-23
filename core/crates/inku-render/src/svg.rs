//! Small SVG-specific document tree serialized exactly once at the render boundary.

use crate::types::CanvasSize;

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
    #[must_use]
    pub fn new(name: impl Into<String>) -> Self {
        Self {
            name: name.into(),
            attributes: Vec::new(),
            children: Vec::new(),
        }
    }

    #[must_use]
    pub fn attr(mut self, name: impl Into<String>, value: impl ToString) -> Self {
        self.set_attr(name, value);
        self
    }

    pub fn set_attr(&mut self, name: impl Into<String>, value: impl ToString) {
        let name = name.into();
        let value = value.to_string();
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
    let rounded = if value == -0.0 { 0.0 } else { value };
    let mut formatted = format!("{rounded:.6}");
    while formatted.contains('.') && formatted.ends_with('0') {
        formatted.pop();
    }
    if formatted.ends_with('.') {
        formatted.pop();
    }
    formatted
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
