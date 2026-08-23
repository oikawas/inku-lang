//! Closed-shape surface textures rendered from portable geometry and stroke data.

use std::collections::BTreeSet;

use sha2::{Digest, Sha256};

use crate::cloudform::{CloudformRequest, generate_cloudform_contour, sample_closed_catmull_rom};
use crate::determinism::{hash_to_unit, hash01, instruction_seed};
use crate::geometry::{
    centerline_normals, circle_points, ellipse_perimeter, point_to_pixels, points_center,
    polygon_points, size_to_pixels, stroke_sample_count,
};
use crate::marks::{
    MarkContext, contour_stroke_path, grid_step, mark_width, rotate, uses_hand_stroke,
};
use crate::palette::resolve_color;
use crate::stroke::{ContourStrokeRequest, StrokeTerminal, synthesize_contour};
use crate::svg::{Element, format_number};
use crate::types::{
    Instruction, Point, Primitive, Seed, SurfaceDirection, SurfaceSpacingGradient, SurfaceTexture,
};

const SURFACE_MARK_MAX: usize = 90;
const HATCH_SPAN_SEED_STRIDE: i64 = 1_048_576;
const SURFACE_DAB_SAMPLES: usize = 5;
const SURFACE_WASH_LAYERS: usize = 2;
const SURFACE_WASH_WIDTH_BASE: f64 = 0.88;
const SURFACE_WASH_WIDTH_SPAN: f64 = 0.60;
const SURFACE_WASH_OPACITY: f64 = 0.22;
const SURFACE_BLEED_RINGS: usize = 3;

#[derive(Clone, Debug, PartialEq)]
pub struct SurfaceRender {
    pub group: Element,
    pub definitions: Vec<Element>,
}

#[derive(Clone, Copy)]
struct DabSpec<'a> {
    radius: f64,
    color: &'a str,
    opacity: f64,
    seed: Seed,
    index: i64,
    class_name: &'a str,
}

fn texture_name(texture: SurfaceTexture) -> &'static str {
    match texture {
        SurfaceTexture::None => "none",
        SurfaceTexture::Solid => "solid",
        SurfaceTexture::Stipple => "stipple",
        SurfaceTexture::Hatch => "hatch",
        SurfaceTexture::Crosshatch => "crosshatch",
        SurfaceTexture::Aquatint => "aquatint",
        SurfaceTexture::Grain => "grain",
        SurfaceTexture::Wash => "wash",
        SurfaceTexture::Bleed => "bleed",
        SurfaceTexture::PaperGrain => "paper_grain",
    }
}

fn owns_surface(primitive: Primitive) -> bool {
    matches!(
        primitive,
        Primitive::Circle
            | Primitive::Ellipse
            | Primitive::Square
            | Primitive::Triangle
            | Primitive::Polygon
            | Primitive::Cloudform
    )
}

fn surface_seed(instruction: &Instruction, context: MarkContext<'_>, grain: bool) -> Seed {
    let surface = instruction
        .surface
        .as_ref()
        .expect("surface checked by caller");
    if let Some(seed) = surface.seed {
        return seed;
    }
    let mut stable = instruction.clone();
    if grain {
        let stable_surface = stable.surface.as_mut().expect("surface cloned above");
        stable_surface.density = 0.5;
        stable_surface.scale = 0.5;
        stable_surface.opacity = 0.5;
    }
    let mut key = serde_json::to_vec(&stable).expect("surface seed payload is serializable");
    key.extend_from_slice(
        format!(
            ":surface:{}:{}:{:?}",
            context.instruction_index, context.mark_index, context.render_seed
        )
        .as_bytes(),
    );
    let digest = Sha256::digest(&key);
    i128::from(u64::from_le_bytes(
        digest[..8].try_into().expect("eight digest bytes"),
    ))
}

fn salted_seed(seed: Seed, label: &str, index: i64) -> Seed {
    let digest = Sha256::digest(format!("{seed}:{label}:{index}").as_bytes());
    i128::from(u64::from_le_bytes(
        digest[..8].try_into().expect("eight digest bytes"),
    ))
}

fn shape_bbox(instruction: &Instruction, context: MarkContext<'_>) -> Option<(f64, f64, f64, f64)> {
    let canvas = context.canvas;
    match instruction.primitive {
        Primitive::Circle => {
            let center = point_to_pixels(instruction.center?, canvas);
            let radius = instruction.radius? * canvas.unit();
            Some((
                center.x - radius,
                center.y - radius,
                radius * 2.0,
                radius * 2.0,
            ))
        }
        Primitive::Ellipse => {
            let center = point_to_pixels(instruction.center?, canvas);
            let size = size_to_pixels(instruction.size?, canvas);
            Some((
                center.x - size.x / 2.0,
                center.y - size.y / 2.0,
                size.x,
                size.y,
            ))
        }
        Primitive::Cloudform => {
            let center = point_to_pixels(instruction.center?, canvas);
            let size = size_to_pixels(instruction.size?, canvas);
            Some((
                center.x - size.x * 0.56,
                center.y - size.y * 0.56,
                size.x * 1.12,
                size.y * 1.12,
            ))
        }
        Primitive::Square | Primitive::Triangle => {
            let position = point_to_pixels(instruction.position?, canvas);
            let size = size_to_pixels(instruction.size?, canvas);
            Some((position.x, position.y, size.x, size.y))
        }
        Primitive::Polygon => {
            let center = point_to_pixels(instruction.center?, canvas);
            let radius = instruction.radius? * canvas.unit();
            Some((
                center.x - radius,
                center.y - radius,
                radius * 2.0,
                radius * 2.0,
            ))
        }
        Primitive::Line | Primitive::Arc => None,
    }
}

fn surface_contour(instruction: &Instruction, context: MarkContext<'_>) -> Option<Vec<Point>> {
    let canvas = context.canvas;
    match instruction.primitive {
        Primitive::Circle => {
            let center = point_to_pixels(instruction.center?, canvas);
            let radius = instruction.radius? * canvas.unit();
            Some(circle_points(
                center,
                radius,
                radius,
                stroke_sample_count(std::f64::consts::TAU * radius, canvas),
            ))
        }
        Primitive::Ellipse => {
            let center = point_to_pixels(instruction.center?, canvas);
            let size = size_to_pixels(instruction.size?, canvas);
            let rx = size.x / 2.0;
            let ry = size.y / 2.0;
            Some(circle_points(
                center,
                rx,
                ry,
                stroke_sample_count(ellipse_perimeter(rx, ry), canvas),
            ))
        }
        Primitive::Square | Primitive::Triangle => {
            let position = point_to_pixels(instruction.position?, canvas);
            let size = size_to_pixels(instruction.size?, canvas);
            if instruction.primitive == Primitive::Square {
                Some(vec![
                    position,
                    Point::new(position.x + size.x, position.y),
                    Point::new(position.x + size.x, position.y + size.y),
                    Point::new(position.x, position.y + size.y),
                ])
            } else {
                Some(vec![
                    Point::new(position.x + size.x / 2.0, position.y),
                    Point::new(position.x + size.x, position.y + size.y),
                    Point::new(position.x, position.y + size.y),
                ])
            }
        }
        Primitive::Polygon => {
            let center = point_to_pixels(instruction.center?, canvas);
            Some(polygon_points(
                center,
                instruction.radius? * canvas.unit(),
                usize::from(instruction.sides.unwrap_or(5)),
                0.0,
            ))
        }
        Primitive::Cloudform => {
            let controls = generate_cloudform_contour(CloudformRequest {
                center: point_to_pixels(instruction.center?, canvas),
                size: size_to_pixels(instruction.size?, canvas),
                performance_seed: Some(instruction_seed(instruction, context.render_seed)),
                instruction_index: context.instruction_index,
                mark_index: context.mark_index,
                variation: instruction.variation.as_ref(),
                weight: instruction.weight,
                point_count: 49,
            });
            Some(sample_closed_catmull_rom(&controls, 5))
        }
        Primitive::Line | Primitive::Arc => None,
    }
}

fn point_in_polygon(point: Point, contour: &[Point]) -> bool {
    let mut inside = false;
    for index in 0..contour.len() {
        let a = contour[index];
        let b = contour[(index + 1) % contour.len()];
        if (a.y > point.y) != (b.y > point.y) {
            let t = (point.y - a.y) / (b.y - a.y);
            if point.x < a.x + (b.x - a.x) * t {
                inside = !inside;
            }
        }
    }
    inside
}

fn scanline_segments(
    contour: &[Point],
    angle: f64,
    spacing: f64,
    seed: Seed,
) -> Vec<(usize, Point, Point)> {
    let direction = Point::new(angle.cos(), angle.sin());
    let normal = Point::new(-direction.y, direction.x);
    let projections = contour
        .iter()
        .map(|point| point.x * normal.x + point.y * normal.y)
        .collect::<Vec<_>>();
    let low = projections.iter().copied().fold(f64::INFINITY, f64::min);
    let high = projections
        .iter()
        .copied()
        .fold(f64::NEG_INFINITY, f64::max);
    let mut offset = low + spacing * 0.5;
    let mut index = 0_usize;
    let mut result = Vec::new();
    while offset < high && index < 4096 {
        let mut hits = Vec::new();
        for edge in 0..contour.len() {
            let a = contour[edge];
            let b = contour[(edge + 1) % contour.len()];
            let da = a.x * normal.x + a.y * normal.y - offset;
            let db = b.x * normal.x + b.y * normal.y - offset;
            if (da <= 0.0 && db > 0.0) || (db <= 0.0 && da > 0.0) {
                let t = da / (da - db);
                let point = Point::new(a.x + (b.x - a.x) * t, a.y + (b.y - a.y) * t);
                hits.push(point.x * direction.x + point.y * direction.y);
            }
        }
        hits.sort_by(f64::total_cmp);
        for pair in (0..hits.len().saturating_sub(1)).step_by(2) {
            let start = Point::new(
                normal.x * offset + direction.x * hits[pair],
                normal.y * offset + direction.y * hits[pair],
            );
            let end = Point::new(
                normal.x * offset + direction.x * hits[pair + 1],
                normal.y * offset + direction.y * hits[pair + 1],
            );
            result.push((index, start, end));
        }
        let step = 1.0 + (hash01(index as i64, seed, "fill-spacing") - 0.5) * 0.24;
        offset += spacing * step;
        index += 1;
    }
    result
}

fn line_spans(contour: &[Point], point: Point, direction: Point) -> Vec<(f64, f64)> {
    let mut hits = Vec::new();
    for edge in 0..contour.len() {
        let a = contour[edge];
        let b = contour[(edge + 1) % contour.len()];
        let edge_vector = Point::new(b.x - a.x, b.y - a.y);
        let denominator = direction.x * edge_vector.y - direction.y * edge_vector.x;
        if denominator.abs() < 1.0e-12 {
            continue;
        }
        let delta = Point::new(a.x - point.x, a.y - point.y);
        let edge_t = (delta.x * direction.y - delta.y * direction.x) / denominator;
        if !(0.0..1.0).contains(&edge_t) {
            continue;
        }
        hits.push(
            (delta.x + edge_vector.x * edge_t) * direction.x
                + (delta.y + edge_vector.y * edge_t) * direction.y,
        );
    }
    hits.sort_by(f64::total_cmp);
    (0..hits.len().saturating_sub(1))
        .step_by(2)
        .map(|index| (hits[index], hits[index + 1]))
        .collect()
}

fn scatter(contour: &[Point], count: usize, seed: Seed) -> Vec<Point> {
    if count == 0 || contour.len() < 3 {
        return Vec::new();
    }
    let angle = hash01(0, seed, "fill-angle") * std::f64::consts::PI;
    let min_x = contour
        .iter()
        .map(|point| point.x)
        .fold(f64::INFINITY, f64::min);
    let max_x = contour
        .iter()
        .map(|point| point.x)
        .fold(f64::NEG_INFINITY, f64::max);
    let min_y = contour
        .iter()
        .map(|point| point.y)
        .fold(f64::INFINITY, f64::min);
    let max_y = contour
        .iter()
        .map(|point| point.y)
        .fold(f64::NEG_INFINITY, f64::max);
    let diagonal = (max_x - min_x).hypot(max_y - min_y).max(1.0e-6);
    let rows = ((count as f64 * 1.6).sqrt().round_ties_even() as usize).max(2);
    let spacing = diagonal / rows as f64;
    let segments = scanline_segments(contour, angle, spacing, seed);
    let lengths = segments
        .iter()
        .map(|(_, start, end)| (end.x - start.x).hypot(end.y - start.y))
        .collect::<Vec<_>>();
    let total = lengths.iter().sum::<f64>();
    if total <= 0.0 {
        return Vec::new();
    }
    let normal = Point::new(-angle.sin(), angle.cos());
    let mut points = Vec::new();
    for (segment_index, ((_, start, end), length)) in segments.iter().zip(lengths).enumerate() {
        let share = count as f64 * length / total;
        let mut taken = share.floor() as usize;
        if hash01(segment_index as i64, seed, "surface-share") < share - taken as f64 {
            taken += 1;
        }
        for point_index in 0..taken {
            let salt_index = segment_index * 4096 + point_index;
            let u =
                (point_index as f64 + hash01(salt_index as i64, seed, "surface-u")) / taken as f64;
            let point = Point::new(
                start.x + (end.x - start.x) * u,
                start.y + (end.y - start.y) * u,
            );
            let drift = (hash01(salt_index as i64, seed, "surface-n") - 0.5) * spacing * 0.8;
            let shifted = Point::new(point.x + normal.x * drift, point.y + normal.y * drift);
            points.push(if point_in_polygon(shifted, contour) {
                shifted
            } else {
                point
            });
        }
    }
    points
}

fn closed_path(points: &[Point]) -> String {
    let Some(first) = points.first() else {
        return String::new();
    };
    let mut commands = vec![format!(
        "M {} {}",
        format_number(first.x),
        format_number(first.y)
    )];
    commands.extend(
        points
            .iter()
            .skip(1)
            .map(|point| format!("L {} {}", format_number(point.x), format_number(point.y))),
    );
    commands.push("Z".to_owned());
    commands.join(" ")
}

fn surface_color(instruction: &Instruction, context: MarkContext<'_>) -> String {
    resolve_color(
        instruction.color,
        instruction.color_hint.as_deref(),
        context.color_map,
        context.work_assignment,
    )
}

fn dab(
    instruction: &Instruction,
    context: MarkContext<'_>,
    point: Point,
    spec: DabSpec<'_>,
) -> Element {
    if !uses_hand_stroke(instruction.weight) {
        return Element::new("circle")
            .attr("cx", format_number(point.x))
            .attr("cy", format_number(point.y))
            .attr("r", format_number(spec.radius))
            .attr("fill", spec.color)
            .attr("fill-opacity", format_number(spec.opacity))
            .attr("stroke", "none")
            .attr("class", spec.class_name);
    }
    let angle = hash01(spec.index, spec.seed, "surface-dab-angle") * std::f64::consts::PI;
    let length = spec.radius * (1.9 + hash01(spec.index, spec.seed, "surface-dab-length") * 1.6);
    let axis = Point::new(angle.cos() * length / 2.0, angle.sin() * length / 2.0);
    let centerline = (0..SURFACE_DAB_SAMPLES)
        .map(|sample| {
            let t = sample as f64 / (SURFACE_DAB_SAMPLES - 1) as f64;
            Point::new(
                point.x - axis.x + 2.0 * axis.x * t,
                point.y - axis.y + 2.0 * axis.y * t,
            )
        })
        .collect::<Vec<_>>();
    stroke_element(
        instruction,
        context,
        &centerline,
        mark_width(instruction, context.canvas).max(spec.radius * 1.3),
        spec.color,
        spec.opacity,
        salted_seed(spec.seed, "surface-stroke", spec.index),
        false,
        spec.class_name,
    )
}

#[allow(clippy::too_many_arguments)]
fn stroke_element(
    instruction: &Instruction,
    context: MarkContext<'_>,
    centerline: &[Point],
    width: f64,
    color: &str,
    opacity: f64,
    seed: Seed,
    closed: bool,
    class_name: &str,
) -> Element {
    let stroke = synthesize_contour(ContourStrokeRequest {
        centerline,
        base_width: width,
        weight: instruction.weight,
        seed,
        closed,
        anchors: &BTreeSet::new(),
        grid_step: grid_step(instruction.weight, context.canvas),
        wild: context.wild,
        support: context.support,
        terminal: StrokeTerminal::Taper,
    });
    Element::new("path")
        .attr("d", contour_stroke_path(&stroke))
        .attr("fill", color)
        .attr("fill-opacity", format_number(opacity))
        .attr("fill-rule", if closed { "evenodd" } else { "nonzero" })
        .attr("stroke", "none")
        .attr("class", class_name)
}

#[allow(clippy::too_many_arguments)]
fn sweep(
    instruction: &Instruction,
    context: MarkContext<'_>,
    start: Point,
    end: Point,
    width: f64,
    color: &str,
    opacity: f64,
    seed: Seed,
    index: i64,
    class_name: &str,
) -> Option<Element> {
    let length = (end.x - start.x).hypot(end.y - start.y);
    if length <= 0.0 {
        return None;
    }
    if !uses_hand_stroke(instruction.weight) {
        return Some(
            Element::new("line")
                .attr("x1", format_number(start.x))
                .attr("y1", format_number(start.y))
                .attr("x2", format_number(end.x))
                .attr("y2", format_number(end.y))
                .attr("stroke", color)
                .attr("stroke-width", format_number(width))
                .attr("stroke-opacity", format_number(opacity))
                .attr("stroke-linecap", "round")
                .attr("class", class_name),
        );
    }
    let count = stroke_sample_count(length, context.canvas).max(2);
    let centerline = (0..count)
        .map(|sample| {
            let t = sample as f64 / (count - 1) as f64;
            Point::new(
                start.x + (end.x - start.x) * t,
                start.y + (end.y - start.y) * t,
            )
        })
        .collect::<Vec<_>>();
    Some(stroke_element(
        instruction,
        context,
        &centerline,
        width,
        color,
        opacity,
        salted_seed(seed, "surface-stroke", index),
        false,
        class_name,
    ))
}

fn grain_pattern(
    instruction: &Instruction,
    context: MarkContext<'_>,
    seed: Seed,
    color: &str,
    opacity: f64,
    pattern_id: &str,
) -> Element {
    let surface = instruction
        .surface
        .as_ref()
        .expect("surface checked by caller");
    let tile = context.canvas.unit() * 0.08;
    let radius = (context.canvas.unit() * (0.002 + surface.scale.max(0.04) * 0.004)).max(0.45);
    let tile_area = tile * tile;
    let reference_area = context.canvas.unit().powi(2) * 0.18;
    let count = (((22.0 + surface.density.max(0.02) * 120.0) * tile_area / reference_area).ceil()
        as usize)
        .max(1);
    let mut pattern = Element::new("pattern")
        .attr("id", pattern_id)
        .attr("patternUnits", "userSpaceOnUse")
        .attr("width", format_number(tile))
        .attr("height", format_number(tile))
        .attr("class", "surface-grain-pattern-v1");
    for index in 0..count {
        let point = Point::new(
            hash01(index as i64, seed, "surface-grain-x") * tile,
            hash01(index as i64, seed, "surface-grain-y") * tile,
        );
        let mark_radius = radius * (0.55 + hash01(index as i64, seed, "surface-r") * 1.1);
        let mark_opacity = opacity * (0.45 + hash01(index as i64, seed, "surface-o") * 0.55);
        let reach = (mark_radius * 2.0).max(mark_width(instruction, context.canvas) * 0.75);
        let mut x_offsets = vec![0.0];
        let mut y_offsets = vec![0.0];
        if point.x < reach {
            x_offsets.push(tile);
        }
        if point.x > tile - reach {
            x_offsets.push(-tile);
        }
        if point.y < reach {
            y_offsets.push(tile);
        }
        if point.y > tile - reach {
            y_offsets.push(-tile);
        }
        let mut logical = Element::new("g").attr("class", "surface-grain-mark");
        for dx in &x_offsets {
            for dy in &y_offsets {
                logical.push(dab(
                    instruction,
                    context,
                    Point::new(point.x + dx, point.y + dy),
                    DabSpec {
                        radius: mark_radius,
                        color,
                        opacity: mark_opacity,
                        seed,
                        index: index as i64,
                        class_name: "surface-grain-dab",
                    },
                ));
            }
        }
        pattern.push(logical);
    }
    pattern
}

fn line_angle(direction: SurfaceDirection) -> f64 {
    match direction {
        SurfaceDirection::Horizontal => 0.0,
        SurfaceDirection::Vertical => std::f64::consts::FRAC_PI_2,
        SurfaceDirection::DiagonalRising => -std::f64::consts::FRAC_PI_4,
        SurfaceDirection::DiagonalFalling | SurfaceDirection::None => std::f64::consts::FRAC_PI_4,
    }
}

fn render_vectors(
    group: &mut Element,
    instruction: &Instruction,
    context: MarkContext<'_>,
    contour: &[Point],
    seed: Seed,
) {
    let surface = instruction
        .surface
        .as_ref()
        .expect("surface checked by caller");
    let Some((x, y, width, height)) = shape_bbox(instruction, context) else {
        return;
    };
    let color = surface_color(instruction, context);
    let opacity = surface.opacity.min(0.75);
    let density = surface.density.max(0.02);
    let scale = surface.scale.max(0.04);
    let area_factor = ((width * height) / (context.canvas.unit().powi(2) * 0.18)).clamp(0.2, 1.8);
    match surface.texture {
        SurfaceTexture::Stipple | SurfaceTexture::PaperGrain => {
            let count = SURFACE_MARK_MAX.min(((22.0 + density * 120.0) * area_factor) as usize);
            let radius = (context.canvas.unit() * (0.002 + scale * 0.004)).max(0.45);
            for (index, point) in scatter(contour, count, seed).into_iter().enumerate() {
                group.push(dab(
                    instruction,
                    context,
                    point,
                    DabSpec {
                        radius: radius * (0.55 + hash01(index as i64, seed, "surface-r") * 1.1),
                        color: &color,
                        opacity: opacity * (0.45 + hash01(index as i64, seed, "surface-o") * 0.55),
                        seed,
                        index: index as i64,
                        class_name: "surface-stroke-v1",
                    },
                ));
            }
        }
        SurfaceTexture::Wash => {
            let spacing = (context.canvas.unit() * (0.052 - density * 0.024)).max(10.0);
            let base_angle = hash01(0, seed, "fill-angle") * std::f64::consts::PI;
            let mut stroke_index = 0_i64;
            for layer in 0..SURFACE_WASH_LAYERS {
                let layer_seed = seed + layer as i128 * 7919;
                let angle = base_angle
                    + (hash01(layer as i64, seed, "wash-angle") - 0.5) * 16_f64.to_radians();
                for (_, start, end) in scanline_segments(contour, angle, spacing, layer_seed) {
                    let sweep_width = mark_width(instruction, context.canvas).max(
                        spacing
                            * (SURFACE_WASH_WIDTH_BASE
                                + hash01(stroke_index, seed, "wash-width")
                                    * SURFACE_WASH_WIDTH_SPAN),
                    );
                    if let Some(element) = sweep(
                        instruction,
                        context,
                        start,
                        end,
                        sweep_width,
                        &color,
                        opacity * SURFACE_WASH_OPACITY,
                        seed,
                        stroke_index,
                        "surface-stroke-v1 surface-wash-sweep",
                    ) {
                        group.push(element);
                    }
                    stroke_index += 1;
                }
            }
        }
        SurfaceTexture::Hatch | SurfaceTexture::Crosshatch => {
            let base_angle = line_angle(surface.direction);
            let spacing = (context.canvas.unit() * (0.010 + (1.0 - density) * 0.025)).max(5.0);
            let center = Point::new(x + width / 2.0, y + height / 2.0);
            let count = ((width.hypot(height) * 1.3 / spacing) as i64).clamp(3, 80);
            let mut angles = vec![base_angle];
            if surface.texture == SurfaceTexture::Crosshatch {
                angles
                    .push(base_angle + (60.0 + hash01(8, seed, "cross-angle") * 30.0).to_radians());
            }
            for (layer, angle) in angles.into_iter().enumerate() {
                let direction = Point::new(angle.cos(), angle.sin());
                let normal = Point::new(-direction.y, direction.x);
                for row in -count / 2..=count / 2 {
                    let progress = (row as f64 + count as f64 / 2.0) / count.max(1) as f64;
                    let gradient = match surface.spacing_gradient {
                        SurfaceSpacingGradient::CoarseToDense => 1.35 - progress * 0.7,
                        SurfaceSpacingGradient::DenseToCoarse => 0.65 + progress * 0.7,
                        SurfaceSpacingGradient::None => 1.0,
                    };
                    let offset = row as f64 * spacing * gradient
                        + hash_to_unit(row + layer as i64 * 401 + 500, seed) * spacing * 0.12;
                    let row_point =
                        Point::new(center.x + normal.x * offset, center.y + normal.y * offset);
                    let stroke_index = row + layer as i64 * 4096;
                    for (span_index, (start_t, end_t)) in line_spans(contour, row_point, direction)
                        .into_iter()
                        .enumerate()
                    {
                        let start = Point::new(
                            row_point.x + direction.x * start_t,
                            row_point.y + direction.y * start_t,
                        );
                        let end = Point::new(
                            row_point.x + direction.x * end_t,
                            row_point.y + direction.y * end_t,
                        );
                        let line_width = (context.canvas.unit() * 0.0016).max(0.45);
                        if let Some(element) = sweep(
                            instruction,
                            context,
                            start,
                            end,
                            line_width,
                            &color,
                            opacity,
                            seed,
                            stroke_index + span_index as i64 * HATCH_SPAN_SEED_STRIDE,
                            &format!("surface-stroke-v1 hatch-spacing-{:.3}", spacing * gradient),
                        ) {
                            group.push(element);
                        }
                    }
                }
            }
        }
        SurfaceTexture::Aquatint => {
            let steps = usize::from(surface.tone_steps.max(1));
            let band = width / steps as f64;
            let radius = (context.canvas.unit() * (0.0015 + scale * 0.0025)).max(0.45);
            let count =
                SURFACE_MARK_MAX.min((((18.0 + density * 90.0) * area_factor) as usize).max(5));
            for (index, point) in scatter(contour, count, seed).into_iter().enumerate() {
                let step = if band > 0.0 {
                    (((point.x - x) / band) as isize).clamp(0, steps as isize - 1) as usize
                } else {
                    0
                };
                let jitter = (hash01(step as i64, seed, "aquatint-boundary") - 0.5) * band * 0.08;
                let shifted = Point::new(point.x + jitter, point.y);
                let target = if point_in_polygon(shifted, contour) {
                    shifted
                } else {
                    point
                };
                group.push(dab(
                    instruction,
                    context,
                    target,
                    DabSpec {
                        radius,
                        color: &color,
                        opacity: opacity * (0.35 + 0.65 * (step + 1) as f64 / steps as f64),
                        seed,
                        index: index as i64,
                        class_name: &format!("surface-stroke-v1 aquatint-step-{}", step + 1),
                    },
                ));
            }
        }
        SurfaceTexture::Bleed => {
            let blur = (context.canvas.unit() * (0.010 + surface.bleed * 0.030)).max(1.0);
            let normals = centerline_normals(contour, true);
            let center = points_center(contour);
            let outward = contour
                .iter()
                .zip(&normals)
                .map(|(point, normal)| {
                    (point.x - center.x) * normal.x + (point.y - center.y) * normal.y
                })
                .sum::<f64>();
            let sign = if outward >= 0.0 { 1.0 } else { -1.0 };
            for ring in 0..SURFACE_BLEED_RINGS {
                let level = ring as f64 / (SURFACE_BLEED_RINGS - 1) as f64;
                let pushed = contour
                    .iter()
                    .zip(&normals)
                    .enumerate()
                    .map(|(index, (point, normal))| {
                        let seep = sign
                            * blur
                            * level
                            * (0.55
                                + hash01((index + ring * 613) as i64, seed, "bleed-seep") * 0.9);
                        Point::new(point.x + normal.x * seep, point.y + normal.y * seep)
                    })
                    .collect::<Vec<_>>();
                let ring_opacity = (opacity * 0.55).min(0.30) * (1.0 - level * 0.55);
                let ring_width = (blur * (1.05 - level * 0.45)).max(1.2);
                if uses_hand_stroke(instruction.weight) {
                    group.push(stroke_element(
                        instruction,
                        context,
                        &pushed,
                        ring_width,
                        &color,
                        ring_opacity,
                        salted_seed(seed, "surface-stroke", 90_000 + ring as i64),
                        true,
                        &format!("surface-stroke-v1 bleed-ring-{}", ring + 1),
                    ));
                } else {
                    group.push(
                        Element::new("polygon")
                            .attr(
                                "points",
                                pushed
                                    .iter()
                                    .map(|point| {
                                        format!(
                                            "{},{}",
                                            format_number(point.x),
                                            format_number(point.y)
                                        )
                                    })
                                    .collect::<Vec<_>>()
                                    .join(" "),
                            )
                            .attr("fill", "none")
                            .attr("stroke", &color)
                            .attr("stroke-width", format_number(ring_width))
                            .attr("stroke-opacity", format_number(ring_opacity))
                            .attr("class", format!("bleed-ring-{}", ring + 1)),
                    );
                }
            }
        }
        SurfaceTexture::None | SurfaceTexture::Solid | SurfaceTexture::Grain => {}
    }
}

/// Render a closed-shape surface beside its owning mark.
#[must_use]
pub fn render_surface(
    instruction: &Instruction,
    context: MarkContext<'_>,
) -> Option<SurfaceRender> {
    let surface = instruction.surface.as_ref()?;
    if matches!(
        surface.texture,
        SurfaceTexture::None | SurfaceTexture::Solid
    ) || !owns_surface(instruction.primitive)
    {
        return None;
    }
    let contour = surface_contour(instruction, context)?;
    if contour.len() < 3 {
        return None;
    }
    let seed = surface_seed(
        instruction,
        context,
        surface.texture == SurfaceTexture::Grain,
    );
    let mut group = Element::new("g").attr(
        "id",
        format!(
            "surface_{:03}_{:03}_{}",
            context.instruction_index,
            context.mark_index,
            texture_name(surface.texture)
        ),
    );
    let mut definitions = Vec::new();
    if surface.texture == SurfaceTexture::Grain {
        let pattern_id = format!(
            "surface_pattern_{:03}_{:03}_grain",
            context.instruction_index, context.mark_index
        );
        let color = surface_color(instruction, context);
        definitions.push(grain_pattern(
            instruction,
            context,
            seed,
            &color,
            surface.opacity.min(0.75),
            &pattern_id,
        ));
        group.push(
            Element::new("path")
                .attr("d", closed_path(&contour))
                .attr("fill", format!("url(#{pattern_id})"))
                .attr("stroke", "none")
                .attr("class", "surface-grain-carrier-v1"),
        );
    } else {
        render_vectors(&mut group, instruction, context, &contour, seed);
    }
    Some(SurfaceRender {
        group: rotate(group, instruction, context.canvas),
        definitions,
    })
}

#[cfg(test)]
mod tests {
    use std::collections::BTreeMap;

    use super::*;
    use crate::support::DEFAULT_SUPPORT;
    use crate::types::{CanvasSize, Score};

    fn context<'a>(colors: &'a BTreeMap<String, String>) -> MarkContext<'a> {
        MarkContext {
            canvas: CanvasSize::new(1000.0, 1000.0),
            color_map: colors,
            work_assignment: colors,
            render_seed: Some(431),
            instruction_index: 2,
            mark_index: 3,
            wild: false,
            support: DEFAULT_SUPPORT,
        }
    }

    #[test]
    fn scatter_stays_inside_a_concave_contour() {
        let contour = vec![
            Point::new(0.0, 0.0),
            Point::new(10.0, 0.0),
            Point::new(10.0, 10.0),
            Point::new(5.0, 4.0),
            Point::new(0.0, 10.0),
        ];
        let points = scatter(&contour, 40, 17);
        assert!(!points.is_empty());
        assert!(
            points
                .into_iter()
                .all(|point| point_in_polygon(point, &contour))
        );
    }

    #[test]
    fn grain_uses_one_definition_and_a_portable_carrier() {
        let score: Score = serde_json::from_str(
            r#"{"instructions":[{"primitive":"circle","center":[0.5,0.5],"radius":0.2,"surface":{"texture":"grain"}}]}"#,
        )
        .unwrap();
        let colors = BTreeMap::new();
        let rendered = render_surface(&score.instructions[0], context(&colors)).unwrap();
        assert_eq!(rendered.definitions.len(), 1);
        let group = format!("{:?}", rendered.group);
        assert!(group.contains("surface-grain-carrier-v1"));
        assert!(!group.contains("clipPath"));
        assert!(!group.contains("filter"));
    }
}
