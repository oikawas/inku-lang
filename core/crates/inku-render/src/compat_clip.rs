//! Geometry clipping of the renderer's own Compat element tree.
//!
//! This is not an arbitrary SVG importer. Unsupported painted nodes/effects fail
//! explicitly. Curves and physical stroke silhouettes use portable kurbo math;
//! compound fills retain their winding rule. Existing fully-contained elements
//! are returned intact. All clipped pieces of one paint share one compound path.

use std::collections::BTreeMap;

use kurbo::{Affine, BezPath, Cap, Join, PathEl, Shape, Stroke};

use crate::fill_geometry::{PreparedRegion, RegionError};
use crate::svg::{Element, Node, format_number};
use crate::types::Point;

/// Limits apply cumulatively across a whole call. Callers own shipment budgets.
#[derive(Clone, Copy, Debug)]
pub struct ClipLimits {
    pub max_nodes: usize,
    pub max_path_elements: usize,
    pub max_flattened_points: usize,
    pub max_work: usize,
    pub max_output_vertices: usize,
}

#[derive(Clone, Copy, Debug)]
pub struct ClipOptions<'a> {
    /// Error tolerance in final canvas pixels, finite and strictly positive.
    pub tolerance: f64,
    /// Unique within the document, for paint-server clones of clipped elements.
    pub id_prefix: &'a str,
    pub limits: ClipLimits,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub enum ClipError {
    Unsupported(String),
    Invalid(String),
    LimitExceeded(&'static str),
    Region(RegionError),
}

impl std::fmt::Display for ClipError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::Unsupported(v) => write!(f, "unsupported Compat clip geometry: {v}"),
            Self::Invalid(v) => write!(f, "invalid Compat clip geometry: {v}"),
            Self::LimitExceeded(v) => write!(f, "Compat clip {v} limit exceeded"),
            Self::Region(v) => v.fmt(f),
        }
    }
}
impl std::error::Error for ClipError {}
impl From<RegionError> for ClipError {
    fn from(value: RegionError) -> Self {
        Self::Region(value)
    }
}

#[derive(Clone)]
struct Style {
    fill: String,
    stroke: String,
    fill_opacity: String,
    stroke_opacity: String,
    evenodd: bool,
    pen: Stroke,
}
impl Default for Style {
    fn default() -> Self {
        Self {
            fill: "black".into(),
            stroke: "none".into(),
            fill_opacity: "1".into(),
            stroke_opacity: "1".into(),
            evenodd: false,
            pen: Stroke::new(1.0).with_join(Join::Miter).with_caps(Cap::Butt),
        }
    }
}
impl Style {
    fn inherit(&self, element: &Element) -> Result<Self, ClipError> {
        let mut result = self.clone();
        for (key, value) in element.attributes() {
            match key.as_str() {
                "fill" => result.fill = value.clone(),
                "stroke" => result.stroke = value.clone(),
                "fill-opacity" => {
                    number(value)?;
                    result.fill_opacity = value.clone();
                }
                "stroke-opacity" => {
                    number(value)?;
                    result.stroke_opacity = value.clone();
                }
                "fill-rule" => {
                    result.evenodd = match value.as_str() {
                        "evenodd" => true,
                        "nonzero" => false,
                        _ => return Err(unsupported(key)),
                    }
                }
                "stroke-width" => {
                    result.pen.width = number(value)?;
                    if result.pen.width < 0.0 {
                        return Err(invalid(key));
                    }
                }
                "stroke-miterlimit" => {
                    result.pen.miter_limit = number(value)?;
                    if result.pen.miter_limit < 1.0 {
                        return Err(invalid(key));
                    }
                }
                "stroke-linecap" => {
                    let cap = match value.as_str() {
                        "butt" => Cap::Butt,
                        "round" => Cap::Round,
                        "square" => Cap::Square,
                        _ => return Err(unsupported(key)),
                    };
                    result.pen.start_cap = cap;
                    result.pen.end_cap = cap;
                }
                "stroke-linejoin" => {
                    result.pen.join = match value.as_str() {
                        "miter" => Join::Miter,
                        "round" => Join::Round,
                        "bevel" => Join::Bevel,
                        _ => return Err(unsupported(key)),
                    }
                }
                "stroke-dashoffset" => result.pen.dash_offset = number(value)?,
                "stroke-dasharray" => {
                    let mut values = if value == "none" {
                        vec![]
                    } else {
                        numbers(value)?
                    };
                    if values.iter().any(|&v| v < 0.0) {
                        return Err(invalid(key));
                    }
                    if values.iter().all(|&v| v == 0.0) {
                        values.clear();
                    }
                    if values.len() % 2 != 0 {
                        values.extend(values.clone());
                    }
                    result.pen.dash_pattern = values.into_iter().collect();
                }
                _ => {}
            }
        }
        Ok(result)
    }
}

struct Context<'a> {
    region: &'a PreparedRegion,
    definitions: BTreeMap<String, Element>,
    options: ClipOptions<'a>,
    remaining: ClipLimits,
    serial: usize,
}

/// Clip one performed mark/group before insertion into the Compat SVG tree.
/// Definitions are the existing document paint servers; no serialization occurs.
/// Display filters belong to an outer clip and must not pass through this API.
pub fn clip_element(
    element: &Element,
    region: &PreparedRegion,
    definitions: &[Element],
    options: ClipOptions<'_>,
) -> Result<Element, ClipError> {
    if !options.tolerance.is_finite() || options.tolerance <= 0.0 || options.id_prefix.is_empty() {
        return Err(invalid("clip options"));
    }
    let mut context = Context {
        region,
        definitions: BTreeMap::new(),
        options,
        remaining: options.limits,
        serial: 0,
    };
    for definition in definitions {
        collect_definitions(
            definition,
            &mut context.definitions,
            &mut context.remaining.max_work,
            0,
        )?;
    }
    collect_definitions(
        element,
        &mut context.definitions,
        &mut context.remaining.max_work,
        0,
    )?;
    context.visit(element, &Style::default(), Affine::IDENTITY, 0)
}

fn collect_definitions(
    element: &Element,
    result: &mut BTreeMap<String, Element>,
    work: &mut usize,
    depth: usize,
) -> Result<(), ClipError> {
    take(work, 1, "definition work")?;
    if depth > 128 {
        return Err(ClipError::LimitExceeded("tree depth"));
    }
    if matches!(element.name(), "linearGradient" | "pattern")
        && let Some(id) = element.attribute("id")
    {
        result.insert(id.to_owned(), element.clone());
    }
    for node in element.children() {
        if let Node::Element(child) = node {
            collect_definitions(child, result, work, depth + 1)?;
        }
    }
    Ok(())
}

impl Context<'_> {
    fn visit(
        &mut self,
        element: &Element,
        inherited: &Style,
        outer: Affine,
        depth: usize,
    ) -> Result<Element, ClipError> {
        take(&mut self.remaining.max_nodes, 1, "nodes")?;
        if depth > 128 {
            return Err(ClipError::LimitExceeded("tree depth"));
        }
        if element.name() == "defs" {
            return Ok(element.clone());
        }
        validate_attributes(element)?;
        let style = inherited.inherit(element)?;
        let transform = outer * transform(element.attribute("transform"))?;
        if !transform.as_coeffs().iter().all(|v| v.is_finite()) || transform.determinant() == 0.0 {
            return Err(invalid("singular or non-finite transform"));
        }
        if element.name() == "g" {
            let children = element
                .children()
                .iter()
                .map(|node| match node {
                    Node::Element(child) => self
                        .visit(child, &style, transform, depth + 1)
                        .map(Node::Element),
                    Node::Text(_) => Err(unsupported("painted text")),
                })
                .collect::<Result<Vec<_>, _>>()?;
            return Ok(element.clone().with_children(children));
        }
        if !element.children().is_empty() {
            return Err(unsupported("shape children"));
        }
        let path = shape_path(element, self.options.tolerance)?;
        take(
            &mut self.remaining.max_path_elements,
            path.elements().len(),
            "path elements",
        )?;
        if !path.elements().iter().all(PathEl::is_finite) {
            return Err(invalid("non-finite path"));
        }
        if path.elements().is_empty() {
            return Ok(element.clone());
        }
        let bounds = path.control_box();
        let painted_stroke = style.stroke != "none" && style.pen.width > 0.0;
        let expansion = if painted_stroke {
            style.pen.width * style.pen.miter_limit.max(1.0) / 2.0
        } else {
            0.0
        };
        let conservative = bounds.inflate(expansion, expansion);
        let corners = [
            (conservative.x0, conservative.y0),
            (conservative.x1, conservative.y0),
            (conservative.x1, conservative.y1),
            (conservative.x0, conservative.y1),
        ]
        .map(|p| to_point(transform * kurbo::Point::from(p)));
        if inside_contour(self.region, &corners)? {
            return Ok(element.clone());
        }

        let [a, b, c, d, _, _] = transform.as_coeffs();
        let scale = (a.abs() + c.abs())
            .max(b.abs() + d.abs())
            .max(f64::MIN_POSITIVE);
        let local_tolerance = self.options.tolerance / scale;
        if !local_tolerance.is_finite() || local_tolerance <= 0.0 {
            return Err(invalid("transform tolerance"));
        }
        // Bound curve/dash expansion before invoking the library algorithms.
        let extent = bounds
            .width()
            .abs()
            .max(bounds.height().abs())
            .max(expansion);
        let estimate = path.elements().len() as f64 * (1.0 + (extent / local_tolerance).sqrt());
        if !estimate.is_finite() || estimate > self.remaining.max_work as f64 {
            return Err(ClipError::LimitExceeded("curve work"));
        }
        take(
            &mut self.remaining.max_work,
            estimate.ceil() as usize,
            "curve work",
        )?;
        if !style.pen.dash_pattern.is_empty() {
            let dash = style.pen.dash_pattern.iter().sum::<f64>();
            let estimate = path.elements().len() as f64 * extent * 8.0 / dash;
            if !estimate.is_finite() || estimate > self.remaining.max_work as f64 {
                return Err(ClipError::LimitExceeded("dash work"));
            }
            take(
                &mut self.remaining.max_work,
                estimate.ceil() as usize,
                "dash work",
            )?;
        }
        let mut paints = Vec::new();
        if style.fill != "none" {
            paints.push((
                path.clone(),
                style.fill.as_str(),
                style.fill_opacity.as_str(),
                style.evenodd,
            ));
        }
        if painted_stroke {
            let outline = kurbo::stroke(
                path.iter(),
                &style.pen,
                &kurbo::StrokeOpts::default(),
                local_tolerance,
            );
            take(
                &mut self.remaining.max_path_elements,
                outline.elements().len(),
                "stroke elements",
            )?;
            paints.push((
                outline,
                style.stroke.as_str(),
                style.stroke_opacity.as_str(),
                false,
            ));
        }
        let inverse = transform.inverse();
        let mut output = wrapper(element);
        let mut all_inside = true;
        for (mut painted, paint, alpha, evenodd) in paints {
            painted.apply_affine(transform);
            let contours = flatten(&painted, self.options.tolerance, &mut self.remaining)?;
            let mut paint_inside = path_controls_inside(self.region, &painted)?;
            // SVG fills implicitly close open subpaths, including polylines.
            if paint_inside {
                for contour in &contours {
                    if !inside_contour(self.region, contour)? {
                        paint_inside = false;
                        break;
                    }
                }
            }
            if paint_inside {
                // Preserve this paint's exact original path if another paint crosses.
                let mut exact = painted;
                exact.apply_affine(inverse);
                let paint = self.preserve_paint(paint, path.bounding_box(), &mut output)?;
                output.push(
                    Element::new("path")
                        .attr("d", exact.to_svg())
                        .attr("fill", paint)
                        .attr("fill-opacity", alpha)
                        .attr("fill-rule", if evenodd { "evenodd" } else { "nonzero" })
                        .attr("stroke", "none"),
                );
                continue;
            }
            all_inside = false;
            let fragments = clip_compound(self.region, &contours, evenodd, &mut self.remaining)?;
            if fragments.is_empty() {
                continue;
            }
            let mut clipped = BezPath::new();
            for fragment in fragments {
                clipped.move_to(inverse * kurbo::Point::new(fragment[0].x, fragment[0].y));
                for point in &fragment[1..] {
                    clipped.line_to(inverse * kurbo::Point::new(point.x, point.y));
                }
                clipped.close_path();
            }
            let paint = self.preserve_paint(paint, path.bounding_box(), &mut output)?;
            output.push(
                Element::new("path")
                    .attr("d", clipped.to_svg())
                    .attr("fill", paint)
                    .attr("fill-opacity", alpha)
                    .attr("fill-rule", "nonzero")
                    .attr("stroke", "none"),
            );
        }
        if all_inside {
            Ok(element.clone())
        } else {
            Ok(output)
        }
    }

    fn preserve_paint(
        &mut self,
        paint: &str,
        bounds: kurbo::Rect,
        output: &mut Element,
    ) -> Result<String, ClipError> {
        let Some(id) = paint
            .strip_prefix("url(#")
            .and_then(|p| p.strip_suffix(')'))
        else {
            if paint.starts_with("url(") {
                return Err(unsupported("external paint server"));
            }
            return Ok(paint.to_owned());
        };
        let definition = self
            .definitions
            .get(id)
            .ok_or_else(|| invalid("missing paint server"))?;
        match definition.name() {
            "pattern" if definition.attribute("patternUnits") == Some("userSpaceOnUse") => {
                Ok(paint.to_owned())
            }
            "linearGradient" if definition.attribute("gradientUnits") == Some("userSpaceOnUse") => {
                Ok(paint.to_owned())
            }
            "linearGradient" => {
                if bounds.width() <= 0.0 || bounds.height() <= 0.0 {
                    return Err(invalid("paint server bounds"));
                }
                let mut definition = definition.clone();
                let matrix = Affine::new([
                    bounds.width(),
                    0.0,
                    0.0,
                    bounds.height(),
                    bounds.x0,
                    bounds.y0,
                ]) * transform(definition.attribute("gradientTransform"))?;
                let id = format!("{}-paint-{}", self.options.id_prefix, self.serial);
                self.serial += 1;
                definition.set_attr("id", &id);
                definition.set_attr("gradientUnits", "userSpaceOnUse");
                definition.set_attr("gradientTransform", matrix_attribute(matrix));
                for (key, fallback) in [("x1", "0"), ("y1", "0"), ("x2", "1"), ("y2", "0")] {
                    let value = definition.attribute(key).unwrap_or(fallback);
                    let parsed = if let Some(value) = value.strip_suffix('%') {
                        number(value)? / 100.0
                    } else {
                        number(value)?
                    };
                    definition.set_attr(key, format_number(parsed));
                }
                let mut defs = Element::new("defs");
                defs.push(definition);
                output.push(defs);
                Ok(format!("url(#{id})"))
            }
            _ => Err(unsupported("paint server coordinate mode")),
        }
    }
}

fn wrapper(element: &Element) -> Element {
    let mut group = Element::new("g");
    for (key, value) in element.attributes() {
        if matches!(
            key.as_str(),
            "id" | "class" | "transform" | "opacity" | "color-interpolation" | "shape-rendering"
        ) || key.starts_with("data-")
        {
            group.set_attr(key, value);
        }
    }
    group
}
fn validate_attributes(element: &Element) -> Result<(), ClipError> {
    for (key, value) in element.attributes() {
        if key.starts_with("data-") {
            continue;
        }
        match key.as_str() {
            "id"
            | "class"
            | "transform"
            | "opacity"
            | "fill"
            | "fill-opacity"
            | "fill-rule"
            | "stroke"
            | "stroke-opacity"
            | "stroke-width"
            | "stroke-linecap"
            | "stroke-linejoin"
            | "stroke-miterlimit"
            | "stroke-dasharray"
            | "stroke-dashoffset"
            | "d"
            | "points"
            | "x"
            | "y"
            | "x1"
            | "y1"
            | "x2"
            | "y2"
            | "width"
            | "height"
            | "cx"
            | "cy"
            | "r"
            | "rx"
            | "ry"
            | "color-interpolation"
            | "shape-rendering" => {}
            "filter" | "mask" | "clip-path" if value == "none" => {}
            _ => return Err(unsupported(key)),
        }
    }
    Ok(())
}
fn shape_path(element: &Element, tolerance: f64) -> Result<BezPath, ClipError> {
    let value = |key, default: Option<f64>| -> Result<f64, ClipError> {
        element
            .attribute(key)
            .map(number)
            .unwrap_or_else(|| default.ok_or_else(|| invalid(key)))
    };
    let mut path = BezPath::new();
    match element.name() {
        "path" => {
            path = BezPath::from_svg(element.attribute("d").ok_or_else(|| invalid("path d"))?)
                .map_err(|_| invalid("path d"))?
        }
        "polygon" | "polyline" => {
            let coordinates = numbers(
                element
                    .attribute("points")
                    .ok_or_else(|| invalid("points"))?,
            )?;
            if coordinates.len() % 2 != 0 {
                return Err(invalid("points"));
            }
            for (i, point) in coordinates.chunks_exact(2).enumerate() {
                if i == 0 {
                    path.move_to((point[0], point[1]));
                } else {
                    path.line_to((point[0], point[1]));
                }
            }
            if !coordinates.is_empty() && element.name() == "polygon" {
                path.close_path();
            }
        }
        "line" => {
            path.move_to((value("x1", Some(0.))?, value("y1", Some(0.))?));
            path.line_to((value("x2", Some(0.))?, value("y2", Some(0.))?));
        }
        "rect" => {
            if value("rx", Some(0.))? != 0.0 || value("ry", Some(0.))? != 0.0 {
                return Err(unsupported("rounded rect"));
            }
            let (x, y, width, height) = (
                value("x", Some(0.))?,
                value("y", Some(0.))?,
                value("width", None)?,
                value("height", None)?,
            );
            if width < 0.0 || height < 0.0 {
                return Err(invalid("rect size"));
            }
            if width > 0.0 && height > 0.0 {
                path = kurbo::Rect::new(x, y, x + width, y + height).to_path(tolerance);
            }
        }
        "circle" | "ellipse" => {
            let (cx, cy) = (value("cx", Some(0.))?, value("cy", Some(0.))?);
            let (rx, ry) = if element.name() == "circle" {
                let r = value("r", None)?;
                (r, r)
            } else {
                (value("rx", None)?, value("ry", None)?)
            };
            if rx < 0.0 || ry < 0.0 {
                return Err(invalid("ellipse radius"));
            }
            if rx > 0.0 && ry > 0.0 {
                path = kurbo::Ellipse::new((cx, cy), (rx, ry), 0.0).to_path(tolerance);
            }
        }
        _ => return Err(unsupported(element.name())),
    }
    Ok(path)
}
fn transform(value: Option<&str>) -> Result<Affine, ClipError> {
    let Some(value) = value else {
        return Ok(Affine::IDENTITY);
    };
    let t: svgtypes::Transform = value.parse().map_err(|_| invalid("transform"))?;
    Ok(Affine::new([t.a, t.b, t.c, t.d, t.e, t.f]))
}
fn matrix_attribute(value: Affine) -> String {
    format!(
        "matrix({})",
        value
            .as_coeffs()
            .iter()
            .map(|v| format_number(*v))
            .collect::<Vec<_>>()
            .join(" ")
    )
}
fn number(value: &str) -> Result<f64, ClipError> {
    let number: f64 = value.parse().map_err(|_| invalid("number"))?;
    if !number.is_finite() {
        return Err(invalid("non-finite number"));
    }
    Ok(number)
}
fn numbers(value: &str) -> Result<Vec<f64>, ClipError> {
    svgtypes::NumberListParser::from(value)
        .map(|n| {
            n.map_err(|_| invalid("number list")).and_then(|v| {
                if v.is_finite() {
                    Ok(v)
                } else {
                    Err(invalid("non-finite number"))
                }
            })
        })
        .collect()
}
fn to_point(point: kurbo::Point) -> Point {
    Point::new(point.x, point.y)
}
fn invalid(value: &str) -> ClipError {
    ClipError::Invalid(value.to_owned())
}
fn unsupported(value: &str) -> ClipError {
    ClipError::Unsupported(value.to_owned())
}
fn take(remaining: &mut usize, count: usize, name: &'static str) -> Result<(), ClipError> {
    *remaining = remaining
        .checked_sub(count)
        .ok_or(ClipError::LimitExceeded(name))?;
    Ok(())
}
fn inside_contour(region: &PreparedRegion, contour: &[Point]) -> Result<bool, ClipError> {
    if contour.is_empty() {
        return Ok(true);
    }
    for i in 0..contour.len() {
        let (a, b) = (contour[i], contour[(i + 1) % contour.len()]);
        if region.clip_line(a, b)? != vec![[a, b]] {
            return Ok(false);
        }
    }
    Ok(true)
}
// A flattened curve alone cannot prove containment near the boundary. A Bezier
// lies inside its control hull; test every hull chord before preserving curves.
fn path_controls_inside(region: &PreparedRegion, path: &BezPath) -> Result<bool, ClipError> {
    let mut previous = Point::new(0.0, 0.0);
    let mut first = previous;
    for element in path.elements() {
        let controls = match *element {
            PathEl::MoveTo(p) => {
                previous = to_point(p);
                first = previous;
                vec![previous]
            }
            PathEl::LineTo(p) => vec![previous, to_point(p)],
            PathEl::QuadTo(a, b) => vec![previous, to_point(a), to_point(b)],
            PathEl::CurveTo(a, b, c) => vec![previous, to_point(a), to_point(b), to_point(c)],
            PathEl::ClosePath => vec![previous, first],
        };
        for (i, &a) in controls.iter().enumerate() {
            if !region.contains(a) {
                return Ok(false);
            }
            for &b in &controls[i + 1..] {
                if region.clip_line(a, b)? != vec![[a, b]] {
                    return Ok(false);
                }
            }
        }
        previous = *controls.last().expect("a path element has a control point");
    }
    Ok(true)
}
fn flatten(
    path: &BezPath,
    tolerance: f64,
    remaining: &mut ClipLimits,
) -> Result<Vec<Vec<Point>>, ClipError> {
    let mut contours = Vec::new();
    let mut current = Vec::new();
    let mut exceeded = false;
    kurbo::flatten(path.iter(), tolerance, |element| {
        if take(&mut remaining.max_flattened_points, 1, "flattened points").is_err() {
            exceeded = true;
            return;
        }
        match element {
            PathEl::MoveTo(point) => {
                if !current.is_empty() {
                    contours.push(std::mem::take(&mut current));
                }
                current.push(to_point(point));
            }
            PathEl::LineTo(point) => current.push(to_point(point)),
            PathEl::ClosePath => {
                if !current.is_empty() {
                    contours.push(std::mem::take(&mut current));
                }
            }
            _ => unreachable!("kurbo flatten produces lines"),
        }
    });
    if exceeded {
        return Err(ClipError::LimitExceeded("flattened points"));
    }
    if !current.is_empty() {
        contours.push(current);
    }
    for contour in &mut contours {
        contour.dedup();
        if contour.len() > 1 && contour.first() == contour.last() {
            contour.pop();
        }
    }
    contours.retain(|c| c.len() >= 3);
    if contours
        .iter()
        .flatten()
        .any(|p| !p.x.is_finite() || !p.y.is_finite())
    {
        return Err(invalid("flattened point"));
    }
    Ok(contours)
}

#[derive(Clone, Copy)]
struct Edge {
    a: Point,
    b: Point,
    target: bool,
}
impl Edge {
    fn x(self, y: f64) -> f64 {
        self.a.x + (self.b.x - self.a.x) * ((y - self.a.y) / (self.b.y - self.a.y))
    }
    fn winding(self) -> i32 {
        if self.b.y > self.a.y { 1 } else { -1 }
    }
}

/// Horizontal trapezoid decomposition handles compound holes and self-overlap.
/// Every vertex and edge intersection is a band boundary, so edge ordering is
/// constant inside a band. Target and source winding are evaluated together.
fn clip_compound(
    region: &PreparedRegion,
    contours: &[Vec<Point>],
    evenodd: bool,
    limits: &mut ClipLimits,
) -> Result<Vec<Vec<Point>>, ClipError> {
    let mut edges = Vec::new();
    let mut levels = Vec::new();
    for (contour, target) in contours
        .iter()
        .map(|c| (c.as_slice(), false))
        .chain(std::iter::once((region.contour(), true)))
    {
        for i in 0..contour.len() {
            let (a, b) = (contour[i], contour[(i + 1) % contour.len()]);
            levels.push(a.y);
            if a.y != b.y {
                edges.push(Edge { a, b, target });
            }
        }
    }
    let pairs = edges
        .len()
        .checked_mul(edges.len().saturating_sub(1))
        .ok_or(ClipError::LimitExceeded("intersection work"))?
        / 2;
    take(&mut limits.max_work, pairs, "intersection work")?;
    for (i, first) in edges.iter().enumerate() {
        for second in &edges[i + 1..] {
            let (dx, dy) = (first.b.x - first.a.x, first.b.y - first.a.y);
            let (ex, ey) = (second.b.x - second.a.x, second.b.y - second.a.y);
            let den = dx * ey - dy * ex;
            if !den.is_finite() {
                return Err(invalid("intersection range"));
            }
            if den == 0.0 {
                continue;
            }
            let (x, y) = (second.a.x - first.a.x, second.a.y - first.a.y);
            let t = (x * ey - y * ex) / den;
            let u = (x * dy - y * dx) / den;
            if (0.0..1.0).contains(&t) && (0.0..1.0).contains(&u) {
                levels.push(first.a.y + t * dy);
            }
        }
    }
    levels.sort_by(f64::total_cmp);
    levels.dedup();
    let mut output = Vec::new();
    for band in levels.windows(2) {
        take(&mut limits.max_work, edges.len(), "scan work")?;
        let y = band[0] + (band[1] - band[0]) / 2.0;
        if y == band[0] || y == band[1] {
            continue;
        }
        let mut active = edges
            .iter()
            .copied()
            .filter(|e| y > e.a.y.min(e.b.y) && y < e.a.y.max(e.b.y))
            .collect::<Vec<_>>();
        active.sort_by(|a, b| a.x(y).total_cmp(&b.x(y)));
        let (mut source, mut target) = (0_i32, 0_i32);
        for pair in active.windows(2) {
            let left = pair[0];
            let right = pair[1];
            if left.target {
                target += left.winding();
            } else {
                source += left.winding();
            }
            let painted = if evenodd {
                source % 2 != 0
            } else {
                source != 0
            };
            if painted && target != 0 && left.x(y) < right.x(y) {
                take(&mut limits.max_output_vertices, 4, "output vertices")?;
                output.push(vec![
                    Point::new(left.x(band[0]), band[0]),
                    Point::new(right.x(band[0]), band[0]),
                    Point::new(right.x(band[1]), band[1]),
                    Point::new(left.x(band[1]), band[1]),
                ]);
            }
        }
    }
    Ok(output)
}

#[cfg(test)]
mod tests {
    use super::*;
    fn p(x: f64, y: f64) -> Point {
        Point::new(x, y)
    }
    fn region() -> PreparedRegion {
        PreparedRegion::new(&[p(0., 0.), p(10., 0.), p(10., 10.), p(0., 10.)]).unwrap()
    }
    fn options() -> ClipOptions<'static> {
        ClipOptions {
            tolerance: 0.001,
            id_prefix: "clip-test",
            limits: ClipLimits {
                max_nodes: 1000,
                max_path_elements: 100_000,
                max_flattened_points: 100_000,
                max_work: 10_000_000,
                max_output_vertices: 100_000,
            },
        }
    }
    fn paths(element: &Element, outer: Affine, result: &mut Vec<BezPath>) {
        let transform = outer * transform(element.attribute("transform")).unwrap();
        if element.name() == "path" {
            let mut path = BezPath::from_svg(element.attribute("d").unwrap()).unwrap();
            path.apply_affine(transform);
            result.push(path);
        }
        if element.name() != "defs" {
            for node in element.children() {
                if let Node::Element(child) = node {
                    paths(child, transform, result);
                }
            }
        }
    }
    fn output_paths(element: &Element) -> Vec<BezPath> {
        let mut result = vec![];
        paths(element, Affine::IDENTITY, &mut result);
        result
    }
    #[test]
    fn crossing_compound_hole_keeps_evenodd_and_nonzero_semantics() {
        for (rule, inside_winding) in [
            ("evenodd", "M2 2L8 2L8 8L2 8Z"),
            ("nonzero", "M2 2L2 8L8 8L8 2Z"),
        ] {
            let element = Element::new("path")
                .attr("d", format!("M-2 -2L12 -2L12 12L-2 12Z {inside_winding}"))
                .attr("fill", "#123456")
                .attr("fill-rule", rule)
                .attr("fill-opacity", "0.4");
            let clipped = clip_element(&element, &region(), &[], options()).unwrap();
            let paths = output_paths(&clipped);
            assert_eq!(paths.len(), 1);
            assert!((paths[0].area().abs() - 64.0).abs() < 1e-8);
            assert_eq!(paths[0].winding(kurbo::Point::new(5., 5.)), 0);
            assert_ne!(paths[0].winding(kurbo::Point::new(1., 1.)), 0);
        }
        let self_cross = Element::new("path")
            .attr("d", "M-2 -2L12 12L-2 12L12 -2Z")
            .attr("fill", "red");
        let clipped = clip_element(&self_cross, &region(), &[], options()).unwrap();
        assert!((output_paths(&clipped)[0].area().abs() - 50.0).abs() < 1e-8);
        let concave = PreparedRegion::new(&[
            p(0., 0.),
            p(4., 0.),
            p(4., 1.),
            p(1., 1.),
            p(1., 4.),
            p(0., 4.),
        ])
        .unwrap();
        let cover = Element::new("rect")
            .attr("x", "-1")
            .attr("y", "-1")
            .attr("width", "6")
            .attr("height", "6");
        let clipped = output_paths(&clip_element(&cover, &concave, &[], options()).unwrap());
        assert!((clipped[0].area().abs() - 7.0).abs() < 1e-8);
        assert_eq!(clipped[0].winding(kurbo::Point::new(2., 2.)), 0);
        let open = Element::new("path").attr("d", "M3.5 0.5L0.5 0.5L0.5 3.5");
        let clipped = output_paths(&clip_element(&open, &concave, &[], options()).unwrap());
        assert!((clipped[0].area().abs() - 2.5).abs() < 1e-8);
    }
    #[test]
    fn stroke_caps_dashes_and_curves_clip_the_painted_silhouette() {
        let line = Element::new("path")
            .attr("d", "M-2 5 L12 5")
            .attr("fill", "none")
            .attr("stroke", "red")
            .attr("stroke-width", "2")
            .attr("stroke-linecap", "round");
        let clipped = clip_element(&line, &region(), &[], options()).unwrap();
        let paths = output_paths(&clipped);
        assert!((paths[0].area().abs() - 20.0).abs() < 0.01);
        let dashed = line.clone().attr("stroke-dasharray", "2 2");
        let dashed = output_paths(&clip_element(&dashed, &region(), &[], options()).unwrap());
        assert!(dashed[0].area().abs() < 20.0);
        let curve = Element::new("path")
            .attr("d", "M-2 3 Q5 -3 12 3 C15 5 8 12 5 8 A3 3 0 0 1 -2 3Z")
            .attr("fill", "blue");
        let curves = output_paths(&clip_element(&curve, &region(), &[], options()).unwrap());
        assert!(!curves.is_empty());
        for path in curves {
            let points = flatten(&path, 0.001, &mut options().limits).unwrap();
            assert!(points.iter().flatten().all(|&p| region().contains(p)));
        }
    }
    #[test]
    fn inside_tree_is_unchanged_and_transformed_paint_keeps_original_gradient_box() {
        let mut inside = Element::new("g")
            .attr("opacity", "0.6")
            .attr("transform", "translate(1 1)");
        inside.push(
            Element::new("circle")
                .attr("cx", "3")
                .attr("cy", "3")
                .attr("r", "1")
                .attr("fill", "red"),
        );
        assert_eq!(
            clip_element(&inside, &region(), &[], options()).unwrap(),
            inside
        );
        let gradient = Element::new("linearGradient")
            .attr("id", "field")
            .attr("x2", "0.2")
            .attr("y2", "1");
        let mut group = Element::new("g")
            .attr("transform", "translate(1 1)")
            .attr("opacity", "0.7");
        group.push(
            Element::new("rect")
                .attr("x", "-2")
                .attr("y", "-2")
                .attr("width", "10")
                .attr("height", "10")
                .attr("transform", "scale(2)")
                .attr("fill", "url(#field)"),
        );
        let clipped = clip_element(&group, &region(), &[gradient], options()).unwrap();
        let paths = output_paths(&clipped);
        assert!((paths[0].area().abs() - 100.0).abs() < 1e-8);
        let mut definitions = BTreeMap::new();
        collect_definitions(&clipped, &mut definitions, &mut 1000, 0).unwrap();
        let gradient = definitions.get("clip-test-paint-0").unwrap();
        assert_eq!(gradient.attribute("gradientUnits"), Some("userSpaceOnUse"));
        assert_eq!(
            gradient.attribute("gradientTransform"),
            Some("matrix(10 0 0 10 -2 -2)")
        );
        assert_eq!(clipped.attribute("opacity"), Some("0.7"));
    }
    #[test]
    fn unsupported_geometry_and_exhausted_work_are_diagnostics() {
        let bad = Element::new("use").attr("href", "#missing");
        assert!(matches!(
            clip_element(&bad, &region(), &[], options()),
            Err(ClipError::Unsupported(_))
        ));
        let shape = Element::new("circle")
            .attr("cx", "0")
            .attr("cy", "0")
            .attr("r", "4");
        assert!(matches!(
            clip_element(
                &shape.clone().attr("filter", "url(#noise)"),
                &region(),
                &[],
                options()
            ),
            Err(ClipError::Unsupported(_))
        ));
        let mut limited = options();
        limited.limits.max_work = 0;
        assert!(matches!(
            clip_element(&shape, &region(), &[], limited),
            Err(ClipError::LimitExceeded(_))
        ));
        assert!(matches!(
            clip_element(
                &shape.attr("transform", "scale(0)"),
                &region(),
                &[],
                options()
            ),
            Err(ClipError::Invalid(_))
        ));
    }
}
