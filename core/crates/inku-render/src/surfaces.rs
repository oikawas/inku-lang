//! Closed-shape surface textures rendered from portable geometry and stroke data.

use std::collections::BTreeSet;

use inku_score::math::DetFloat;
use sha2::{Digest, Sha256};

use crate::determinism::{hash_to_unit, hash01, seed_salt_index_digest};
use crate::flat_brush::{FlatBandRequest, FlatHold, flat_band, flat_band_element, lays_flat_face};
use crate::geometry::{centerline_normals, points_center, stroke_sample_count};
use crate::mark_geometry::MarkGeometry;
use crate::mark_paths::{contour_stroke_path, grid_step, rotate, uses_hand_stroke};
use crate::marks::{
    MarkContext, intensity_factor, mark_style, mark_width, reaches_canvas, sweep_band_width,
};
use crate::materials::{texture_filter_id, with_texture_filter};
use crate::palette::resolve_color;
use crate::stroke::{ContourStrokeRequest, StrokeTerminal, synthesize_contour};
use crate::surface_geometry::{
    line_spans, scanline_segments, scatter, shape_bbox, surface_contour,
};
use crate::svg::{Element, Node, format_number};
use crate::types::{
    ArcForm, Arrangement, AtRegion, CarveDepth, Color, InkSpread, Instruction, InstructionMode,
    LineStyle, Point, Primitive, Relation, Seed, SurfaceDirection, SurfaceIntensity,
    SurfaceSpacingGradient, SurfaceSpec, SurfaceTexture, SvgProfile, Thinness, Variation, Weight,
};
use serde::Serialize;

/// Stipple and aquatint marks follow a shape's area up to eight times the
/// reference area, at most 400 (render engine 88; 90 and 1.8 before).
const SURFACE_MARK_MAX: usize = 400;
const SURFACE_AREA_FACTOR_MAX: f64 = 8.0;
/// The thin wash under a named texture of a closed shape without a fill
/// (render engine 88): normal, dense, faint.
const SURFACE_BASE_WASH: [f64; 3] = [0.12, 0.18, 0.072];
const HATCH_SPAN_SEED_STRIDE: i64 = 1_048_576;
const SURFACE_DAB_SAMPLES: usize = 5;
const SURFACE_WASH_LAYERS: usize = 2;
const SURFACE_WASH_WIDTH_BASE: f64 = 0.88;
const SURFACE_WASH_WIDTH_SPAN: f64 = 0.60;
const SURFACE_WASH_OPACITY: f64 = 0.22;
/// One sweep of 刷き: the wash sweeps without their own paleness, at the value the
/// author chose on the comparison sheet (2026-09-29). 薄い (faint, ×0.55) makes
/// it 0.275, a little darker than the wash's 0.22. Each band of 刷毛目 carries it
/// on its own (render engine 91).
const SURFACE_SWEEP_OPACITY: f64 = 0.5;
/// The bands of one pass of 刷き are laid wet into each other, as one film
/// (render engine 90): overlapping bands no longer build up. The film carries
/// 1.2 of one band's opacity, which keeps a face's mean tone (calibrated on the
/// author's batch of Build 1309).
const SURFACE_SWEEP_PASS_FACTOR: f64 = 1.2;
/// The dab shapes one grain face places, its sizes split evenly over 0.55 to
/// 1.65 of the grain radius (render engine 90).
const SURFACE_GRAIN_SHAPES: usize = 12;
const SURFACE_BLEED_RINGS: usize = 3;
/// A surface's default density and scale (the Score's `SurfaceSpec`). The
/// fineness words (DDL 24) move a named texture away from them, and the units'
/// own formulas read these (render engine 89).
const SURFACE_DEFAULT_DENSITY: f64 = 0.35;
const SURFACE_DEFAULT_SCALE: f64 = 0.35;

/// Prototype parameters for distinct point surfaces (render engine 104).
const STIPPLE_RADIUS_FACTOR: f64 = 2.4;
const STIPPLE_COUNT_FACTOR: f64 = 1.5;
const STIPPLE_MAX: usize = 2400;
const STIPPLE_OPACITY_MIN: f64 = 0.8;
const GRAIN_RADIUS_FACTOR: f64 = 0.55;
const GRAIN_COUNT_FACTOR: f64 = 38.0;
const GRAIN_OPACITY_FACTOR: f64 = 0.8;
/// The grain lies on three repeating tiles whose sides do not divide one
/// another, each carrying a third of the points, so the face's SVG stays the
/// same size however large the face is and no single repeat shows as a
/// lattice (render engine 104; one face-sized tile grew with the face).
const GRAIN_TILE_SIDE: f64 = 0.19;
const GRAIN_TILE_SCALES: [f64; 3] = [1.0, 1.31, 1.73];
const AQUATINT_DARKEN_FRACTION: f64 = -0.30;
const AQUATINT_DARKEN_LIMIT: f64 = 0.15;
const AQUATINT_LIGHT_OPACITY: f64 = 0.18;
const AQUATINT_DARK_OPACITY: f64 = 0.97;
const AQUATINT_TEXTURE_OPACITY: f64 = 0.85;
const AQUATINT_RADIUS_BASE: f64 = 0.95;
const AQUATINT_RADIUS_DENSITY: f64 = 0.55;
const AQUATINT_STOPS_PER_STEP: usize = 4;
const AQUATINT_MIN_LIGHTNESS: f64 = 0.15;
const AQUATINT_LIFT_LIGHTNESS: f64 = 0.16;

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
    use_filters: bool,
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
    } else if is_named_texture(surface.texture) {
        // The fineness words (DDL 24) change how a face is laid, not which
        // face it is: their fields seed as the defaults, so a word does not
        // turn the face's strokes around (render engine 89). Saved wash, bleed
        // and paper grain seed from their own fields, as they did.
        let stable_surface = stable.surface.as_mut().expect("surface cloned above");
        stable_surface.density = SURFACE_DEFAULT_DENSITY;
        stable_surface.scale = SURFACE_DEFAULT_SCALE;
    }
    // Nor does the underlayer word (下塗り) turn them.
    if is_named_texture(surface.texture) {
        stable.filled = false;
    }
    // 刷毛目 lays the bands 刷き lays, each on its own (render engine 91): it
    // seeds as 刷き, so writing one for the other turns no band.
    if surface.texture == SurfaceTexture::Brushmarks {
        stable
            .surface
            .as_mut()
            .expect("surface cloned above")
            .texture = SurfaceTexture::Sweep;
    }
    let mut key = surface_seed_payload(stable);
    key.extend_from_slice(
        format!(
            ":surface:{}:{}:{}",
            context.instruction_index,
            context.mark_index,
            seed_debug_text(context.render_seed)
        )
        .as_bytes(),
    );
    let digest = Sha256::digest(&key);
    i128::from(u64::from_le_bytes(
        digest[..8].try_into().expect("eight digest bytes"),
    ))
}

/// The bytes a surface seeds from, frozen as the Instruction serialized them
/// at render engine 100 (I-733 RND-9): the same field names, order and
/// omissions. Every field is named, so a field added to Instruction stops the
/// build here until it is decided whether it turns the surface.
fn surface_seed_payload(stable: Instruction) -> Vec<u8> {
    let Instruction {
        primitive,
        note,
        from_,
        to,
        center,
        radius,
        sides,
        position,
        size,
        angle_start,
        angle_end,
        rotation,
        arc_form,
        filled,
        style,
        weight,
        mode_,
        carve_depth,
        color,
        color_hint,
        variation,
        ink_spread,
        arrangement,
        at,
        relation,
        surface_intensity,
        thinness,
        surface,
    } = stable;
    serde_json::to_vec(&SurfaceSeedPayload {
        primitive,
        note,
        from_,
        to,
        center,
        radius,
        sides,
        position,
        size,
        angle_start,
        angle_end,
        rotation,
        arc_form,
        filled,
        style,
        weight,
        mode_,
        carve_depth,
        color,
        color_hint,
        variation,
        ink_spread,
        arrangement,
        at,
        relation,
        surface_intensity,
        thinness,
        surface,
    })
    .expect("surface seed payload is serializable")
}

/// `{:?}` of an `Option<Seed>` as the seeds were made with it.
fn seed_debug_text(seed: Option<Seed>) -> String {
    match seed {
        Some(seed) => format!("Some({seed})"),
        None => "None".to_owned(),
    }
}

fn intensity_is_normal(intensity: &SurfaceIntensity) -> bool {
    *intensity == SurfaceIntensity::Normal
}

#[derive(Serialize)]
struct SurfaceSeedPayload {
    primitive: Primitive,
    note: Option<String>,
    #[serde(rename = "from")]
    from_: Option<Point>,
    to: Option<Point>,
    center: Option<Point>,
    radius: Option<f64>,
    sides: Option<u8>,
    position: Option<Point>,
    size: Option<Point>,
    angle_start: Option<f64>,
    angle_end: Option<f64>,
    rotation: Option<f64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    arc_form: Option<ArcForm>,
    filled: bool,
    style: LineStyle,
    weight: Weight,
    #[serde(rename = "mode")]
    mode_: InstructionMode,
    carve_depth: Option<CarveDepth>,
    color: Color,
    color_hint: Option<String>,
    variation: Option<Variation>,
    #[serde(skip_serializing_if = "Option::is_none")]
    ink_spread: Option<InkSpread>,
    arrangement: Option<Arrangement>,
    at: Option<AtRegion>,
    relation: Option<Relation>,
    #[serde(skip_serializing_if = "intensity_is_normal")]
    surface_intensity: SurfaceIntensity,
    thinness: Option<Thinness>,
    surface: Option<SurfaceSpec>,
}

fn salted_seed(seed: Seed, label: &str, index: i64) -> Seed {
    let digest = seed_salt_index_digest(seed, label, i128::from(index));
    i128::from(u64::from_le_bytes(
        digest[..8].try_into().expect("eight digest bytes"),
    ))
}

fn closed_path(points: &[Point]) -> String {
    crate::svg::closed_polyline_path(points)
}

/// How far a pass of 刷き bleeds at its edges, per 1,000 units of the short
/// side (render engine 90): the tool's displacement and this blur.
fn sweep_bleed(weight: Weight) -> f64 {
    match crate::marks::drawn_as(weight) {
        Weight::BrushThick => 3.0,
        Weight::BrushThin => 1.5,
        _ => 2.0,
    }
}

fn sweep_bleed_filter_id(context: MarkContext<'_>) -> String {
    format!(
        "surface_soft_{:03}_{:03}",
        context.instruction_index, context.mark_index
    )
}

/// The filter of a pass of 刷き: the tool's displacement and a wider blur,
/// computed in sRGB as the tool's texture filter is (render engine 92).
fn sweep_bleed_filter(instruction: &Instruction, context: MarkContext<'_>) -> Element {
    let mut filter = Element::new("filter")
        .attr("id", sweep_bleed_filter_id(context))
        .attr("x", "-20%")
        .attr("y", "-20%")
        .attr("width", "140%")
        .attr("height", "140%")
        .attr("color-interpolation-filters", "sRGB");
    if let Some(base) = crate::materials::texture_filter(instruction.weight, context.canvas) {
        for child in base.children() {
            if let Node::Element(element) = child
                && matches!(element.name(), "feTurbulence" | "feDisplacementMap")
            {
                filter.push(element.clone());
            }
        }
    }
    filter.push(Element::new("feGaussianBlur").attr(
        "stdDeviation",
        format_number(sweep_bleed(instruction.weight) * context.canvas.unit() / 1000.0),
    ));
    filter
}

/// Hundredths are enough for a placed grain point.
fn hundredths(value: f64) -> String {
    format_number((value * 100.0).round() / 100.0)
}

fn surface_color(instruction: &Instruction, context: MarkContext<'_>) -> String {
    resolve_color(
        instruction.color,
        instruction.color_hint.as_deref(),
        context.color_map,
        context.work_assignment,
    )
}

/// A texture the DDL can write (刷き・刷毛目・粒・点描・平行線・交差線・アクアチント).
/// Saved wash, bleed and paper grain keep their own path under a fill.
pub(crate) fn is_named_texture(texture: SurfaceTexture) -> bool {
    matches!(
        texture,
        SurfaceTexture::Sweep
            | SurfaceTexture::Brushmarks
            | SurfaceTexture::Grain
            | SurfaceTexture::Stipple
            | SurfaceTexture::Hatch
            | SurfaceTexture::Crosshatch
            | SurfaceTexture::Aquatint
    )
}

/// A named texture over the tool's paint: a filled closed shape's texture
/// (下塗り, DDL 24; render engine 89).
fn underpainted(instruction: &Instruction) -> bool {
    instruction.filled
        && instruction
            .surface
            .as_ref()
            .is_some_and(|surface| is_named_texture(surface.texture))
}

/// The colour a texture is laid in. Over an underpainting it turns against
/// the fill, so that it shows on it (render engine 89): 45% toward white over
/// a colour of relative luminance under 0.45, ×0.62 darker over a lighter one.
fn texture_color(instruction: &Instruction, context: MarkContext<'_>) -> String {
    let color = surface_color(instruction, context);
    if !underpainted(instruction) {
        return color;
    }
    match relative_luminance(&color) {
        Some(luminance) if luminance < 0.45 => toward_white(&color, 0.45),
        Some(_) => crate::accepted_fills::darker(&color, 0.62),
        None => color,
    }
}

/// A texture over an underpainting is laid twice as strong (render engine 89).
fn underpaint_boost(instruction: &Instruction) -> f64 {
    if underpainted(instruction) { 2.0 } else { 1.0 }
}

fn hex_rgb(color: &str) -> Option<[u8; 3]> {
    let hex = color.strip_prefix('#').filter(|hex| hex.len() == 6)?;
    let channel = |index: usize| u8::from_str_radix(&hex[index * 2..index * 2 + 2], 16).ok();
    Some([channel(0)?, channel(1)?, channel(2)?])
}

fn relative_luminance(color: &str) -> Option<f64> {
    let linear = |channel: u8| {
        let value = f64::from(channel) / 255.0;
        if value <= 0.04045 {
            value / 12.92
        } else {
            ((value + 0.055) / 1.055).dpowf(2.4)
        }
    };
    let [r, g, b] = hex_rgb(color)?;
    Some(0.2126 * linear(r) + 0.7152 * linear(g) + 0.0722 * linear(b))
}

fn toward_white(color: &str, share: f64) -> String {
    let Some(channels) = hex_rgb(color) else {
        return color.to_owned();
    };
    let lift = |channel: u8| {
        (f64::from(channel) + (255.0 - f64::from(channel)) * share)
            .round()
            .clamp(0.0, 255.0) as u8
    };
    format!(
        "#{:02x}{:02x}{:02x}",
        lift(channels[0]),
        lift(channels[1]),
        lift(channels[2])
    )
}

/// How many texture units the density lays against the default density's
/// (render engine 89): 1 at 0.35, 4 at 0.85 (密な) and 0.25 at 0.05 (疎な),
/// exponential between.
fn texture_count_ratio(density: f64) -> f64 {
    let delta = density - SURFACE_DEFAULT_DENSITY;
    if delta >= 0.0 {
        4_f64.dpowf(delta / 0.5)
    } else {
        4_f64.dpowf(delta / 0.30)
    }
}

/// One texture unit's size against the default scale's (render engine 89): 1
/// at 0.35, 0.5 at 0.05 (細かい) and 2 at 0.90 (粗い), exponential between. The
/// units cover the same area, so their count goes by the inverse square.
fn texture_size_factor(scale: f64) -> f64 {
    let delta = scale - SURFACE_DEFAULT_SCALE;
    if delta >= 0.0 {
        2_f64.dpowf(delta / 0.55)
    } else {
        2_f64.dpowf(delta / 0.30)
    }
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
    let axis = Point::new(angle.dcos() * length / 2.0, angle.dsin() * length / 2.0);
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
        spec.use_filters,
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
    use_filters: bool,
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
    with_texture_filter(
        Element::new("path")
            .attr("d", contour_stroke_path(&stroke))
            .attr("fill", color)
            .attr("fill-opacity", format_number(opacity))
            .attr("fill-rule", if closed { "evenodd" } else { "nonzero" })
            .attr("stroke", "none")
            .attr("class", class_name),
        instruction.weight,
        use_filters,
    )
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
    let length = (end.x - start.x).dhypot(end.y - start.y);
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
    if lays_flat_face(instruction) {
        // The flat brush passes straight across: its tip stays square to the pass.
        let stroke_seed = salted_seed(seed, "surface-stroke", index);
        let stroke = synthesize_contour(ContourStrokeRequest {
            centerline: &centerline,
            base_width: width,
            weight: instruction.weight,
            seed: stroke_seed,
            closed: false,
            anchors: &BTreeSet::new(),
            grid_step: grid_step(instruction.weight, context.canvas),
            wild: context.wild,
            support: context.support,
            terminal: StrokeTerminal::Taper,
        });
        let points = stroke
            .samples
            .iter()
            .map(|sample| sample.point)
            .collect::<Vec<_>>();
        let energies = stroke
            .samples
            .iter()
            .map(|sample| sample.energy)
            .collect::<Vec<_>>();
        if let Some(band) = flat_band(FlatBandRequest {
            centerline: &points,
            energies: &energies,
            hold: FlatHold::Fixed,
            base_width: width,
            weight: instruction.weight,
            seed: stroke_seed,
            support: context.support,
            scale: context.canvas.unit() / 1000.0,
            brush_size: sweep_band_width(instruction, context.canvas),
            fine_streaks: false,
        }) {
            return Some(with_texture_filter(
                flat_band_element(&band, color, &format!("{class_name} flat-brush-v1"))
                    .attr("opacity", format_number(opacity)),
                instruction.weight,
                context.use_filters,
            ));
        }
    }
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
        context.use_filters,
    ))
}

/// One band of a pass of 刷き, opaque and without a filter of its own, as its
/// body and its streaks: the pass carries the opacity and the filter (render
/// engine 90).
#[allow(clippy::too_many_arguments)]
fn sweep_parts(
    instruction: &Instruction,
    context: MarkContext<'_>,
    start: Point,
    end: Point,
    width: f64,
    color: &str,
    seed: Seed,
    index: i64,
    class_name: &str,
) -> Option<(Vec<Node>, Vec<Node>)> {
    let length = (end.x - start.x).dhypot(end.y - start.y);
    if length <= 0.0 {
        return None;
    }
    if !uses_hand_stroke(instruction.weight) {
        let line = Element::new("line")
            .attr("x1", format_number(start.x))
            .attr("y1", format_number(start.y))
            .attr("x2", format_number(end.x))
            .attr("y2", format_number(end.y))
            .attr("stroke", color)
            .attr("stroke-width", format_number(width))
            .attr("stroke-linecap", "round")
            .attr("class", class_name);
        return Some((vec![line.into()], Vec::new()));
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
    if lays_flat_face(instruction) {
        // The flat brush passes straight across: its tip stays square to the pass.
        let stroke_seed = salted_seed(seed, "surface-stroke", index);
        let stroke = synthesize_contour(ContourStrokeRequest {
            centerline: &centerline,
            base_width: width,
            weight: instruction.weight,
            seed: stroke_seed,
            closed: false,
            anchors: &BTreeSet::new(),
            grid_step: grid_step(instruction.weight, context.canvas),
            wild: context.wild,
            support: context.support,
            terminal: StrokeTerminal::Taper,
        });
        let points = stroke
            .samples
            .iter()
            .map(|sample| sample.point)
            .collect::<Vec<_>>();
        let energies = stroke
            .samples
            .iter()
            .map(|sample| sample.energy)
            .collect::<Vec<_>>();
        if let Some(band) = flat_band(FlatBandRequest {
            centerline: &points,
            energies: &energies,
            hold: FlatHold::Fixed,
            base_width: width,
            weight: instruction.weight,
            seed: stroke_seed,
            support: context.support,
            scale: context.canvas.unit() / 1000.0,
            brush_size: sweep_band_width(instruction, context.canvas),
            fine_streaks: false,
        }) {
            let element = flat_band_element(&band, color, &format!("{class_name} flat-brush-v1"));
            let mut children = element.children().to_vec();
            if children.is_empty() {
                return None;
            }
            let body = children.remove(0);
            return Some((vec![body], children));
        }
    }
    let body = stroke_element(
        instruction,
        context,
        &centerline,
        width,
        color,
        1.0,
        salted_seed(seed, "surface-stroke", index),
        false,
        class_name,
        false,
    );
    Some((vec![body.into()], Vec::new()))
}

/// The grain of one face, laid on `GRAIN_TILE_SCALES.len()` repeating tiles.
/// Each tile carries a third of the points at the density the 0.08-unit tile
/// once set (render engine 89; a finer grain sets more, smaller points at the
/// same cover, and the density multiplies them). The tiles' sides do not divide
/// one another and their origins move with the seed, so the repeats never line
/// up into the lattice one small tile showed (render engine 90). A point near a
/// tile's edge is drawn again across the opposite edge, so the tile has no
/// seam. The face places `SURFACE_GRAIN_SHAPES` dab shapes, turned, by `use`.
///
/// The tiles hang from the canvas origin, not from the face, and their ids
/// name their content, so every face of one instruction (a row of copies, a
/// scatter) fills from the same tiles: the document carries each set once
/// (`extend_definitions`), and its size no longer grows with the faces or their
/// area (render engine 104). Returns the definitions and the ids of the
/// patterns, lowest layer first.
fn grain_pattern(
    instruction: &Instruction,
    context: MarkContext<'_>,
    color: &str,
    opacity: f64,
) -> (Vec<Element>, Vec<String>) {
    let surface = instruction
        .surface
        .as_ref()
        .expect("surface checked by caller");
    // A hand's pressure turns each face's opacity a little; the tiles take it
    // in steps of 0.02, so the faces of one instruction share a few sets.
    let opacity = ((opacity * 50.0).round() / 50.0).max(0.02);
    // The tiles seed from what every face of the instruction shares (its
    // index, tool, texture and the render seed), not from a face's place, so
    // the copies of a row fill from one set; each face's own seed
    // (`surface_seed`) is unchanged.
    let seed = {
        let digest = Sha256::digest(
            format!(
                "surface-grain-tiles:{}:{:?}:{}:{}",
                context.instruction_index,
                instruction.weight,
                surface.texture.as_str(),
                seed_debug_text(context.render_seed)
            )
            .as_bytes(),
        );
        i128::from(u64::from_le_bytes(
            digest[..8].try_into().expect("eight digest bytes"),
        ))
    };
    let tile = context.canvas.unit() * 0.08;
    let size = texture_size_factor(surface.scale.max(0.04));
    let radius = (context.canvas.unit() * (0.002 + SURFACE_DEFAULT_SCALE * 0.004)).max(0.45)
        * size
        * GRAIN_RADIUS_FACTOR;
    let tile_area = tile * tile;
    let reference_area = context.canvas.unit().powi(2) * 0.18;
    let cover = 1.0 / (size * size);
    let per_tile = (((22.0 + SURFACE_DEFAULT_DENSITY * 120.0) * tile_area / reference_area
        * cover
        * texture_count_ratio(surface.density.max(0.02))
        * GRAIN_COUNT_FACTOR)
        .ceil() as usize)
        .max(1);
    let density = per_tile as f64 / tile_area;
    let width = mark_width(instruction, context.canvas);
    let reach = (radius * 1.65 * 2.0).max(width * 0.75);
    let base = context.canvas.unit() * GRAIN_TILE_SIDE;
    let payload = format!(
        "{color}|{opacity:.6}|{radius:.6}|{density:.9}|{width:.6}|{base:.6}|{:?}|{}|{:?}",
        instruction.weight,
        seed_debug_text(Some(seed)),
        context.profile
    );
    let digest = Sha256::digest(payload.as_bytes());
    let pattern_id = format!(
        "surface_grain_{}",
        digest[..6]
            .iter()
            .map(|byte| format!("{byte:02x}"))
            .collect::<String>()
    );
    let mut definitions = Vec::new();
    for shape in 0..SURFACE_GRAIN_SHAPES {
        let factor = 0.55 + 1.1 * (shape as f64 + 0.5) / SURFACE_GRAIN_SHAPES as f64;
        definitions.push(
            dab(
                instruction,
                context,
                Point::new(0.0, 0.0),
                DabSpec {
                    radius: radius * factor,
                    color,
                    opacity,
                    seed,
                    index: shape as i64,
                    class_name: "surface-grain-dab",
                    use_filters: false,
                },
            )
            .attr("id", format!("{pattern_id}_dab_{shape}")),
        );
    }
    let layers = GRAIN_TILE_SCALES.len();
    let mut ids = Vec::with_capacity(layers);
    for (layer, scale) in GRAIN_TILE_SCALES.iter().enumerate() {
        let side = base * scale;
        let id = format!("{pattern_id}_{layer}");
        let shift_x = hash01(layer as i64, seed, "surface-grain-tile-x") * side;
        let shift_y = hash01(layer as i64, seed, "surface-grain-tile-y") * side;
        let mut pattern = Element::new("pattern")
            .attr("id", &id)
            .attr("patternUnits", "userSpaceOnUse")
            .attr("x", format_number(-shift_x))
            .attr("y", format_number(-shift_y))
            .attr("width", format_number(side))
            .attr("height", format_number(side));
        if context.profile != SvgProfile::Compat {
            pattern.set_attr("class", "surface-grain-pattern-v3");
        }
        let count = ((density * side * side / layers as f64).round() as usize).max(1);
        for point_index in 0..count {
            let index = (layer * 1_000_000 + point_index) as i64;
            let point = Point::new(
                hash01(index, seed, "surface-grain-x") * side,
                hash01(index, seed, "surface-grain-y") * side,
            );
            let shape = ((hash01(index, seed, "surface-r") * SURFACE_GRAIN_SHAPES as f64) as usize)
                .min(SURFACE_GRAIN_SHAPES - 1);
            let turn =
                format_number((hash01(index, seed, "surface-grain-turn") * 3600.0).round() / 10.0);
            let mark_opacity = hundredths(0.45 + hash01(index, seed, "surface-o") * 0.55);
            for dx in [-side, 0.0, side] {
                for dy in [-side, 0.0, side] {
                    let (x, y) = (point.x + dx, point.y + dy);
                    if x < -reach || x > side + reach || y < -reach || y > side + reach {
                        continue;
                    }
                    pattern.push(
                        Element::new("use")
                            .attr("href", format!("#{pattern_id}_dab_{shape}"))
                            .attr(
                                "transform",
                                format!(
                                    "translate({} {}) rotate({turn})",
                                    hundredths(x),
                                    hundredths(y)
                                ),
                            )
                            .attr("opacity", &mark_opacity),
                    );
                }
            }
        }
        definitions.push(pattern);
        ids.push(id);
    }
    (definitions, ids)
}

/// Add a face's definitions to the document's, leaving out any whose id the
/// document already carries: the grain tiles of one instruction's faces are
/// one set, named by their content (render engine 104).
pub(crate) fn extend_definitions(target: &mut Vec<Element>, definitions: Vec<Element>) {
    for definition in definitions {
        let known = definition.attribute("id").is_some_and(|id| {
            target
                .iter()
                .any(|existing| existing.attribute("id") == Some(id))
        });
        if !known {
            target.push(definition);
        }
    }
}

/// A colored mezzotint holds one pigment, letting the paper show in the light.
fn aquatint_pigment(color: &str) -> String {
    let Some(rgb) = hex_rgb(color) else {
        return color.to_owned();
    };
    if rgb == [0, 0, 0] || rgb == [17, 17, 17] {
        return color.to_owned();
    }
    let [lightness, a, b] = inku_score::oklab_from_srgb(rgb.map(|v| f64::from(v) / 255.0));
    if lightness < AQUATINT_MIN_LIGHTNESS {
        let lifted =
            crate::materials::adjust_pigment(color, |_, c, h| (AQUATINT_LIFT_LIGHTNESS, c, h));
        let center = hex_rgb(&lifted).expect("pigment is hexadecimal");
        let chroma = a.dhypot(b);
        let mut best = None;
        for dr in -4_i16..=4 {
            for dg in -4_i16..=4 {
                for db in -4_i16..=4 {
                    let candidate: [u8; 3] = std::array::from_fn(|i| {
                        (i16::from(center[i]) + [dr, dg, db][i]).clamp(0, 255) as u8
                    });
                    let [l, ca, cb] =
                        inku_score::oklab_from_srgb(candidate.map(|v| f64::from(v) / 255.0));
                    let candidate_chroma = ca.dhypot(cb);
                    if l < AQUATINT_MIN_LIGHTNESS
                        || (chroma > 1e-5
                            && ca * a + cb * b
                                < candidate_chroma * chroma * 2_f64.to_radians().dcos())
                    {
                        continue;
                    }
                    let error = (l - AQUATINT_LIFT_LIGHTNESS).abs() + (ca - a).dhypot(cb - b);
                    if best.as_ref().is_none_or(|(old, _)| error < *old) {
                        best = Some((error, candidate));
                    }
                }
            }
        }
        let selected = best.map_or(center, |(_, rgb)| rgb);
        return format!("#{:02x}{:02x}{:02x}", selected[0], selected[1], selected[2]);
    }
    let fraction = AQUATINT_DARKEN_FRACTION.max(AQUATINT_MIN_LIGHTNESS / lightness - 1.0);
    crate::materials::layered_pigment(color, fraction, AQUATINT_DARKEN_LIMIT)
}

/// Lay a smooth light from the upper left, then faint ink-texture over it.
fn aquatint_surface(
    instruction: &Instruction,
    context: MarkContext<'_>,
    contour: &[Point],
    group: &mut Element,
    definitions: &mut Vec<Element>,
) {
    let surface = instruction
        .surface
        .as_ref()
        .expect("surface checked by caller");
    let pigment = aquatint_pigment(&texture_color(instruction, context));
    let id = format!(
        "surface_aquatint_{:03}_{:03}",
        context.instruction_index, context.mark_index
    );
    let radius =
        (AQUATINT_RADIUS_BASE - AQUATINT_RADIUS_DENSITY * surface.density).clamp(0.35, 0.94);
    let count = usize::from(surface.tone_steps.clamp(1, 16)) * AQUATINT_STOPS_PER_STEP;
    let strength = intensity_factor(instruction.surface_intensity);
    let mut gradient = Element::new("radialGradient")
        .attr("id", &id)
        .attr("cx", "25%")
        .attr("cy", "25%")
        .attr("r", format!("{}%", format_number(radius * 100.0)));
    for i in 0..=count {
        let t = i as f64 / count as f64;
        let smooth = t * t * (3.0 - 2.0 * t);
        let opacity = ((AQUATINT_LIGHT_OPACITY
            + (AQUATINT_DARK_OPACITY - AQUATINT_LIGHT_OPACITY) * smooth)
            * strength)
            .clamp(0.0, 1.0);
        gradient.push(
            Element::new("stop")
                .attr("offset", format_number(t))
                .attr("stop-color", &pigment)
                .attr("stop-opacity", format_number(opacity)),
        );
    }
    definitions.push(gradient);
    group.push(
        Element::new("path")
            .attr("d", closed_path(contour))
            .attr("fill", format!("url(#{id})"))
            .attr("stroke", "none")
            .attr("class", "surface-aquatint-tone-v1"),
    );
    let (rocker, ids) = grain_pattern(
        instruction,
        context,
        &pigment,
        (AQUATINT_TEXTURE_OPACITY * strength * underpaint_boost(instruction)).min(1.0),
    );
    definitions.extend(rocker);
    for pattern in ids {
        group.push(
            Element::new("path")
                .attr("d", closed_path(contour))
                .attr("fill", format!("url(#{pattern})"))
                .attr("stroke", "none")
                .attr("class", "surface-aquatint-rocker-v1"),
        );
    }
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
    geometry: MarkGeometry,
    context: MarkContext<'_>,
    contour: &[Point],
    seed: Seed,
) {
    let surface = instruction
        .surface
        .as_ref()
        .expect("surface checked by caller");
    let Some((x, y, width, height)) = shape_bbox(geometry, instruction, context) else {
        return;
    };
    let color = texture_color(instruction, context);
    let opacity = (surface.opacity
        * intensity_factor(instruction.surface_intensity)
        * underpaint_boost(instruction))
    .min(0.75);
    // A named texture's units follow their formulas at the default density
    // and scale, and its own density multiplies them and its scale sizes one
    // at the same cover (render engine 89). Saved wash and paper grain, which
    // no DDL word writes, read their own fields in the formulas, as they did.
    let (density, scale, count_ratio, size) = if is_named_texture(surface.texture) {
        (
            SURFACE_DEFAULT_DENSITY,
            SURFACE_DEFAULT_SCALE,
            texture_count_ratio(surface.density.max(0.02)),
            texture_size_factor(surface.scale.max(0.04)),
        )
    } else {
        (surface.density.max(0.02), surface.scale.max(0.04), 1.0, 1.0)
    };
    let cover = 1.0 / (size * size);
    let area_factor = ((width * height) / (context.canvas.unit().powi(2) * 0.18))
        .clamp(0.2, SURFACE_AREA_FACTOR_MAX);
    match surface.texture {
        SurfaceTexture::Stipple | SurfaceTexture::PaperGrain => {
            let stipple = surface.texture == SurfaceTexture::Stipple;
            let count_factor = if stipple { STIPPLE_COUNT_FACTOR } else { 1.0 };
            let maximum = if stipple {
                STIPPLE_MAX
            } else {
                SURFACE_MARK_MAX
            };
            let count = ((maximum as f64 * cover * count_ratio) as usize).min(
                ((22.0 + density * 120.0) * area_factor * cover * count_ratio * count_factor)
                    as usize,
            );
            let radius = (context.canvas.unit() * (0.002 + scale * 0.004)).max(0.45)
                * size
                * if stipple { STIPPLE_RADIUS_FACTOR } else { 1.0 };
            let opacity = if stipple {
                (mark_style(instruction, context).stroke_opacity * underpaint_boost(instruction))
                    .min(1.0)
            } else {
                opacity
            };
            for (index, point) in scatter(contour, count, seed).into_iter().enumerate() {
                // A dab is at most 1.65 `radius` round, and its stroke runs at
                // most 1.75 of that from its point.
                if !reaches_canvas(instruction, context, point, point, radius * 3.0) {
                    continue;
                }
                group.push(dab(
                    instruction,
                    context,
                    point,
                    DabSpec {
                        radius: radius * (0.55 + hash01(index as i64, seed, "surface-r") * 1.1),
                        color: &color,
                        opacity: opacity
                            * if stipple {
                                STIPPLE_OPACITY_MIN
                                    + hash01(index as i64, seed, "surface-o")
                                        * (1.0 - STIPPLE_OPACITY_MIN)
                            } else {
                                0.45 + hash01(index as i64, seed, "surface-o") * 0.55
                            },
                        seed,
                        index: index as i64,
                        class_name: "surface-stroke-v1",
                        use_filters: context.use_filters,
                    },
                ));
            }
        }
        SurfaceTexture::Wash | SurfaceTexture::Sweep | SurfaceTexture::Brushmarks => {
            let (sweep_opacity, class_name) = match surface.texture {
                SurfaceTexture::Wash => {
                    (SURFACE_WASH_OPACITY, "surface-stroke-v1 surface-wash-sweep")
                }
                SurfaceTexture::Brushmarks => (
                    SURFACE_SWEEP_OPACITY,
                    "surface-stroke-v1 surface-brushmarks",
                ),
                _ => (SURFACE_SWEEP_OPACITY, "surface-stroke-v1 surface-sweep"),
            };
            // The bands lie closer as the density rises (never under 6 px) and
            // wider apart as the scale does, but a band stays one unit wide
            // however close the density lays them (render engine 89).
            let band_spacing = (context.canvas.unit() * (0.052 - density * 0.024)).max(10.0) * size;
            let spacing = (band_spacing / count_ratio).max(6.0);
            let base_angle = hash01(0, seed, "fill-angle") * std::f64::consts::PI;
            // The bands of one pass of 刷き are laid wet into each other: opaque
            // inside the pass, with the opacity and the filter once on it
            // (render engine 90). A saved wash keeps a band per sweep, and so
            // does 刷毛目, whose overlapping bands build up (render engine 91).
            let merge = surface.texture == SurfaceTexture::Sweep;
            let mut stroke_index = 0_i64;
            for layer in 0..SURFACE_WASH_LAYERS {
                let layer_seed = seed + layer as i128 * 7919;
                let angle = base_angle
                    + (hash01(layer as i64, seed, "wash-angle") - 0.5) * 16_f64.to_radians();
                let mut bodies = Vec::new();
                let mut streaks = Vec::new();
                for (_, start, end) in scanline_segments(contour, angle, spacing, layer_seed) {
                    let sweep_width = mark_width(instruction, context.canvas).max(
                        band_spacing
                            * (SURFACE_WASH_WIDTH_BASE
                                + hash01(stroke_index, seed, "wash-width")
                                    * SURFACE_WASH_WIDTH_SPAN),
                    );
                    if reaches_canvas(instruction, context, start, end, sweep_width) {
                        if merge {
                            if let Some((body, streak)) = sweep_parts(
                                instruction,
                                context,
                                start,
                                end,
                                sweep_width,
                                &color,
                                seed,
                                stroke_index,
                                class_name,
                            ) {
                                bodies.extend(body);
                                streaks.extend(streak);
                            }
                        } else if let Some(element) = sweep(
                            instruction,
                            context,
                            start,
                            end,
                            sweep_width,
                            &color,
                            opacity * sweep_opacity,
                            seed,
                            stroke_index,
                            class_name,
                        ) {
                            group.push(element);
                        }
                    }
                    stroke_index += 1;
                }
                if merge && !bodies.is_empty() {
                    let mut pass = Element::new("g")
                        .attr("class", "surface-sweep-pass-v1")
                        .attr(
                            "opacity",
                            format_number(
                                (opacity * sweep_opacity * SURFACE_SWEEP_PASS_FACTOR).min(1.0),
                            ),
                        );
                    // A mechanical pen lays its passes as lines, which Skia gives no
                    // bounds for a filter; they stay unfiltered, as its sweeps were.
                    if context.use_filters && uses_hand_stroke(instruction.weight) {
                        pass.set_attr(
                            "filter",
                            format!("url(#{})", sweep_bleed_filter_id(context)),
                        );
                    }
                    bodies.extend(streaks);
                    group.push(pass.with_children(bodies));
                }
            }
        }
        SurfaceTexture::Hatch | SurfaceTexture::Crosshatch => {
            let base_angle = line_angle(surface.direction);
            // The lines lie closer as the density rises, and grow thicker and
            // wider apart as the scale does, never closer than 2.2 line widths
            // (render engine 89).
            let line_width = ((context.canvas.unit() * 0.0016).max(0.45) * size).max(0.45);
            let spacing = ((context.canvas.unit() * (0.010 + (1.0 - density) * 0.025)).max(5.0)
                * size
                / count_ratio)
                .max(line_width * 2.2);
            let center = Point::new(x + width / 2.0, y + height / 2.0);
            let count = ((width.dhypot(height) * 1.3 / spacing) as i64)
                .clamp(3, (80.0 * (count_ratio / size).max(1.0)) as i64);
            let mut angles = vec![base_angle];
            if surface.texture == SurfaceTexture::Crosshatch {
                angles
                    .push(base_angle + (60.0 + hash01(8, seed, "cross-angle") * 30.0).to_radians());
            }
            for (layer, angle) in angles.into_iter().enumerate() {
                let direction = Point::new(angle.dcos(), angle.dsin());
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
                        if reaches_canvas(instruction, context, start, end, line_width)
                            && let Some(element) = sweep(
                                instruction,
                                context,
                                start,
                                end,
                                line_width,
                                &color,
                                opacity,
                                seed,
                                stroke_index + span_index as i64 * HATCH_SPAN_SEED_STRIDE,
                                &format!(
                                    "surface-stroke-v1 hatch-spacing-{:.3}",
                                    spacing * gradient
                                ),
                            )
                        {
                            group.push(element);
                        }
                    }
                }
            }
        }
        SurfaceTexture::Aquatint => {}
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
                        context.use_filters,
                    ));
                } else {
                    group.push(
                        Element::new("polygon")
                            .attr("points", crate::svg::points_list(&pushed))
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

/// Render a closed-shape surface beside its owning mark of `geometry`.
#[must_use]
pub(crate) fn render_surface(
    instruction: &Instruction,
    geometry: MarkGeometry,
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
    let contour = surface_contour(geometry, instruction, context)?;
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
            surface.texture.as_str()
        ),
    );
    // A named texture without a fill sits on a thin wash of its own colour,
    // so the shape reads as a face (render engine 88).
    if !instruction.filled {
        let wash = SURFACE_BASE_WASH[match instruction.surface_intensity {
            SurfaceIntensity::Normal => 0,
            SurfaceIntensity::Dense => 1,
            SurfaceIntensity::Faint => 2,
        }];
        group.push(
            Element::new("path")
                .attr("d", closed_path(&contour))
                .attr("fill", surface_color(instruction, context))
                .attr("fill-opacity", format_number(wash))
                .attr("stroke", "none")
                .attr("class", "surface-base-wash-v1"),
        );
    }
    let mut definitions = Vec::new();
    if surface.texture == SurfaceTexture::Grain {
        let color = texture_color(instruction, context);
        let (grain, ids) = grain_pattern(
            instruction,
            context,
            &color,
            (mark_style(instruction, context).stroke_opacity
                * GRAIN_OPACITY_FACTOR
                * underpaint_boost(instruction))
            .min(1.0),
        );
        definitions.extend(grain);
        for pattern in ids {
            group.push(
                Element::new("path")
                    .attr("d", closed_path(&contour))
                    .attr("fill", format!("url(#{pattern})"))
                    .attr("stroke", "none")
                    .attr("class", "surface-grain-carrier-v1"),
            );
        }
    } else if surface.texture == SurfaceTexture::Aquatint {
        aquatint_surface(instruction, context, &contour, &mut group, &mut definitions);
    } else if matches!(
        surface.texture,
        SurfaceTexture::Sweep | SurfaceTexture::Brushmarks
    ) {
        // 刷き stays inside its contour, cut as roughly as the tool's own edge
        // (render engine 90; its bands crossed the outline), and so does 刷毛目
        // (render engine 91), whose bands bleed no further than the tool's.
        let sweep = surface.texture == SurfaceTexture::Sweep;
        if sweep && context.use_filters && uses_hand_stroke(instruction.weight) {
            definitions.push(sweep_bleed_filter(instruction, context));
        }
        let mut inside = Element::new("g").attr(
            "class",
            if sweep {
                "surface-sweep-inside-v1"
            } else {
                "surface-brushmarks-inside-v1"
            },
        );
        render_vectors(&mut inside, instruction, geometry, context, &contour, seed);
        if context.profile != SvgProfile::Compat {
            let mask_id = format!(
                "surface_mask_{:03}_{:03}",
                context.instruction_index, context.mark_index
            );
            let mut path = Element::new("path")
                .attr("d", closed_path(&contour))
                .attr("fill", "white")
                .attr("stroke", "none");
            if context.use_filters
                && crate::marks::drawn_as(instruction.weight) != Weight::Drypoint
                && let Some(id) = texture_filter_id(instruction.weight)
            {
                path.set_attr("filter", format!("url(#{id})"));
            }
            // A fitted frame's region covers its paper (render engine 93).
            let paper = context.clip_canvas.unwrap_or(context.canvas).paper();
            let mut mask = Element::new("mask")
                .attr("id", &mask_id)
                .attr("maskUnits", "userSpaceOnUse")
                .attr("x", format_number(paper[0] - (paper[2] - paper[0])))
                .attr("y", format_number(paper[1] - (paper[3] - paper[1])))
                .attr("width", format_number((paper[2] - paper[0]) * 3.0))
                .attr("height", format_number((paper[3] - paper[1]) * 3.0));
            mask.push(path);
            definitions.push(mask);
            inside.set_attr("mask", format!("url(#{mask_id})"));
        }
        group.push(inside);
    } else {
        render_vectors(&mut group, instruction, geometry, context, &contour, seed);
    }
    Some(SurfaceRender {
        group: if context.geometry_transform.is_identity() {
            rotate(group, instruction, context.canvas)
        } else {
            group
        },
        definitions,
    })
}

#[cfg(test)]
mod tests {
    use std::collections::BTreeMap;

    use super::*;
    use crate::support::DEFAULT_SUPPORT;
    use crate::surface_geometry::point_in_polygon;
    use crate::types::{CanvasSize, Score};

    fn context<'a>(colors: &'a BTreeMap<String, String>) -> MarkContext<'a> {
        MarkContext {
            canvas: CanvasSize::new(1000.0, 1000.0),
            clip_canvas: None,
            color_map: colors,
            work_assignment: colors,
            render_seed: Some(431),
            instruction_seed_override: None,
            instruction_index: 2,
            mark_index: 3,
            wild: false,
            use_filters: false,
            profile: crate::types::SvgProfile::Editable,
            support: DEFAULT_SUPPORT,
            geometry_transform: crate::affine::AffineTransform::identity(),
            oil_fill_pass_limit: crate::fills::MAX_OIL_FILL_PASSES,
            effects: crate::effects::MarkEffects::default(),
        }
    }

    #[test]
    fn a_surface_seeds_from_the_bytes_frozen_at_render_engine_100() {
        // I-733 RND-9: the payload and the seed of a mark with every optional
        // field the Instruction writes, so a drift in a field's form is found.
        let instruction: Instruction = serde_json::from_str(
            r#"{"primitive":"circle","note":"月","center":[0.25,0.5],"radius":0.125,
            "arc_form":"crescent","filled":true,"style":"dashed","weight":"pencil",
            "mode":"carve","carve_depth":"half","color":"red","color_hint":"朱",
            "ink_spread":"bleed","surface_intensity":"dense","thinness":"fine",
            "surface":{"texture":"hatch","density":0.75,"scale":0.25,"opacity":0.5,
            "bleed":0.125,"tone_steps":3}}"#,
        )
        .unwrap();
        assert_eq!(
            String::from_utf8(surface_seed_payload(instruction.clone())).unwrap(),
            concat!(
                r#"{"primitive":"circle","note":"月","from":null,"to":null,"#,
                r#""center":[0.25,0.5],"radius":0.125,"sides":null,"position":null,"#,
                r#""size":null,"angle_start":null,"angle_end":null,"rotation":null,"#,
                r#""arc_form":"crescent","filled":true,"style":"dashed","weight":"pencil","#,
                r#""mode":"carve","carve_depth":"half","color":"red","color_hint":"朱","#,
                r#""variation":null,"ink_spread":"bleed","arrangement":null,"at":null,"#,
                r#""relation":null,"surface_intensity":"dense","thinness":"fine","#,
                r#""surface":{"texture":"hatch","density":0.75,"scale":0.25,"opacity":0.5,"#,
                r#""bleed":0.125,"direction":"none","spacing_gradient":"none","tone_steps":3,"#,
                r#""seed":null}}"#
            )
        );
        let colors = BTreeMap::new();
        assert_eq!(
            surface_seed(&instruction, context(&colors), false),
            3_805_096_259_888_174_028
        );
        assert_eq!(seed_debug_text(Some(-7)), "Some(-7)");
        assert_eq!(seed_debug_text(None), "None");
    }

    #[test]
    fn point_surfaces_and_their_fineness_and_underpainting_differ() {
        let colors = BTreeMap::new();
        let draw = |texture: &str, scale: f64, density: f64, filled: bool| {
            let instruction: Instruction = serde_json::from_value(serde_json::json!({
                "primitive":"circle", "center":[0.5,0.5], "radius":0.2,
                "weight":"pen", "filled":filled,
                "surface":{"texture":texture, "scale":scale, "density":density}
            }))
            .unwrap();
            let rendered = render_surface(
                &instruction,
                MarkGeometry::of(&instruction).unwrap(),
                context(&colors),
            )
            .unwrap();
            let mut svg = crate::svg::Document::new(context(&colors).canvas);
            for definition in rendered.definitions {
                svg.push_definition(definition);
            }
            svg.push(rendered.group);
            svg.serialize()
        };
        let textures = ["stipple", "grain", "aquatint"];
        let defaults: Vec<_> = textures
            .iter()
            .map(|t| draw(t, 0.35, 0.35, false))
            .collect();
        assert_ne!(defaults[0], defaults[1]);
        assert_ne!(defaults[0], defaults[2]);
        assert_ne!(defaults[1], defaults[2]);
        for (texture, default) in textures.iter().zip(defaults) {
            for (scale, density, filled) in [
                (0.05, 0.35, false),
                (0.90, 0.35, false),
                (0.35, 0.85, false),
                (0.35, 0.05, false),
                (0.35, 0.35, true),
            ] {
                assert_ne!(
                    default,
                    draw(texture, scale, density, filled),
                    "{texture} {scale} {density} {filled}"
                );
            }
        }
    }

    #[test]
    fn aquatint_dark_pigment_preserves_hue_and_avoids_black_mixing() {
        for color in [
            "#2c3e91", "#a2342a", "#2f6b3a", "#010000", "#020104", "#000010",
        ] {
            let lab = |c: &str| {
                inku_score::oklab_from_srgb(hex_rgb(c).unwrap().map(|v| f64::from(v) / 255.0))
            };
            let original = lab(color);
            let dark = aquatint_pigment(color);
            let result = lab(&dark);
            let hue = |x: [f64; 3]| x[2].datan2(x[1]).to_degrees();
            let delta = (hue(original) - hue(result)).abs().rem_euclid(360.0);
            assert!(delta.min(360.0 - delta) <= 2.0, "{color} {dark}");
            assert!(
                result[0] >= 0.15 && (original[0] < 0.15 || result[0] <= original[0]),
                "{color} {dark}"
            );
        }
        assert_eq!(aquatint_pigment("#000000"), "#000000");
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

    fn drawn_lines(element: &Element, out: &mut Vec<(String, String, Option<f64>)>) {
        for child in element.children() {
            if let crate::svg::Node::Element(child) = child {
                if child.name() == "line" {
                    out.push((
                        child.attribute("class").unwrap().to_owned(),
                        child.attribute("stroke-width").unwrap().to_owned(),
                        child
                            .attribute("stroke-opacity")
                            .map(|value| value.parse().unwrap()),
                    ));
                }
                drawn_lines(child, out);
            }
        }
    }

    fn with_class<'e>(element: &'e Element, class: &str, out: &mut Vec<&'e Element>) {
        for child in element.children() {
            if let crate::svg::Node::Element(child) = child {
                if child
                    .attribute("class")
                    .is_some_and(|value| value.split(' ').any(|name| name == class))
                {
                    out.push(child);
                }
                with_class(child, class, out);
            }
        }
    }

    #[test]
    fn sweep_lays_each_pass_as_one_film_inside_its_contour() {
        let colors = BTreeMap::new();
        let drawn = |texture: &str, intensity: &str, profile: SvgProfile| {
            let score: Score = serde_json::from_str(&format!(
                r#"{{"version":"0.17.0","instructions":[{{"primitive":"square","position":[0.3,0.3],"size":[0.4,0.4],"weight":"rotring","surface_intensity":"{intensity}","surface":{{"texture":"{texture}","seed":7}}}}]}}"#
            ))
            .unwrap();
            let instruction = &score.instructions[0];
            let geometry = MarkGeometry::of(instruction).unwrap();
            render_surface(
                instruction,
                geometry,
                MarkContext {
                    profile,
                    ..context(&colors)
                },
            )
            .unwrap()
        };
        // A saved wash keeps a band per sweep, at its own paleness.
        let wash = drawn("wash", "normal", SvgProfile::Editable);
        let mut wash_lines = Vec::new();
        drawn_lines(&wash.group, &mut wash_lines);
        assert!(wash_lines.len() > 10);
        assert!(wash_lines.iter().all(|(class, _, opacity)| {
            class == "surface-stroke-v1 surface-wash-sweep" && opacity.is_some()
        }));
        assert!(wash.definitions.is_empty());
        // 刷き lays the same bands, opaque inside one film per pass; the film
        // carries 0.28 × 0.5 × 1.2 of the tool, and 薄い (×0.55) makes it paler.
        for (intensity, factor) in [("normal", 1.0), ("faint", 0.55)] {
            let sweep = drawn("sweep", intensity, SvgProfile::Editable);
            let mut passes = Vec::new();
            with_class(&sweep.group, "surface-sweep-pass-v1", &mut passes);
            assert_eq!(passes.len(), SURFACE_WASH_LAYERS);
            let mut sweep_lines = Vec::new();
            for pass in &passes {
                let opacity: f64 = pass.attribute("opacity").unwrap().parse().unwrap();
                assert!((opacity - 0.28 * 0.5 * 1.2 * factor).abs() < 1e-6);
                drawn_lines(pass, &mut sweep_lines);
            }
            assert_eq!(sweep_lines.len(), wash_lines.len());
            for ((_, wash_width, _), (class, width, opacity)) in wash_lines.iter().zip(&sweep_lines)
            {
                assert_eq!(class, "surface-stroke-v1 surface-sweep");
                assert_eq!(wash_width, width);
                assert_eq!(*opacity, None);
            }
            // The passes stay inside the face: a mask of its own contour.
            let mut inside = Vec::new();
            with_class(&sweep.group, "surface-sweep-inside-v1", &mut inside);
            assert_eq!(inside.len(), 1);
            assert_eq!(
                inside[0].attribute("mask"),
                Some("url(#surface_mask_002_003)")
            );
            let mut washes = Vec::new();
            with_class(&sweep.group, "surface-base-wash-v1", &mut washes);
            let contour = washes[0].attribute("d").unwrap();
            let mask = sweep
                .definitions
                .iter()
                .find(|definition| definition.attribute("id") == Some("surface_mask_002_003"))
                .unwrap();
            let Some(crate::svg::Node::Element(path)) = mask.children().first() else {
                panic!("the mask holds the contour");
            };
            assert_eq!(path.attribute("d"), Some(contour));
        }
        // Compat lays the same passes without a mask.
        let compat = drawn("sweep", "normal", SvgProfile::Compat);
        assert!(compat.definitions.is_empty());
        let mut passes = Vec::new();
        with_class(&compat.group, "surface-sweep-pass-v1", &mut passes);
        assert_eq!(passes.len(), SURFACE_WASH_LAYERS);
        assert!(!format!("{:?}", compat.group).contains("mask"));
    }

    /// Every drawn line as its ends and width.
    fn line_places(element: &Element, out: &mut Vec<[String; 5]>) {
        for child in element.children() {
            if let crate::svg::Node::Element(child) = child {
                if child.name() == "line" {
                    out.push(
                        ["x1", "y1", "x2", "y2", "stroke-width"]
                            .map(|name| child.attribute(name).unwrap().to_owned()),
                    );
                }
                line_places(child, out);
            }
        }
    }

    #[test]
    fn brushmarks_lays_the_bands_of_a_sweep_each_on_its_own() {
        let colors = BTreeMap::new();
        let drawn = |texture: &str, weight: &str, profile: SvgProfile, use_filters: bool| {
            let score: Score = serde_json::from_str(&format!(
                r#"{{"version":"0.22.0","instructions":[{{"primitive":"square","position":[0.3,0.3],"size":[0.4,0.4],"weight":"{weight}","surface":{{"texture":"{texture}"}}}}]}}"#
            ))
            .unwrap();
            let instruction = &score.instructions[0];
            let geometry = MarkGeometry::of(instruction).unwrap();
            render_surface(
                instruction,
                geometry,
                MarkContext {
                    profile,
                    use_filters,
                    ..context(&colors)
                },
            )
            .unwrap()
        };
        // Each band carries the sweep's 0.28 × 0.5 of the tool on its own, so
        // overlapping bands build up; no film is laid over a pass.
        let brushmarks = drawn("brushmarks", "rotring", SvgProfile::Editable, false);
        assert_eq!(
            brushmarks.group.attribute("id"),
            Some("surface_002_003_brushmarks")
        );
        let mut films = Vec::new();
        with_class(&brushmarks.group, "surface-sweep-pass-v1", &mut films);
        assert!(films.is_empty());
        let mut lines = Vec::new();
        drawn_lines(&brushmarks.group, &mut lines);
        assert!(lines.len() > 10);
        assert!(lines.iter().all(|(class, _, opacity)| {
            class == "surface-stroke-v1 surface-brushmarks"
                && opacity.is_some_and(|opacity| (opacity - 0.28 * 0.5).abs() < 1e-6)
        }));
        // Seeded as the sweep, it lays the same bands in the same places.
        let sweep = drawn("sweep", "rotring", SvgProfile::Editable, false);
        let (mut ours, mut theirs) = (Vec::new(), Vec::new());
        line_places(&brushmarks.group, &mut ours);
        line_places(&sweep.group, &mut theirs);
        assert_eq!(ours, theirs);
        // It stays inside the face by the sweep's contour mask.
        let mut inside = Vec::new();
        with_class(
            &brushmarks.group,
            "surface-brushmarks-inside-v1",
            &mut inside,
        );
        assert_eq!(inside.len(), 1);
        assert_eq!(
            inside[0].attribute("mask"),
            Some("url(#surface_mask_002_003)")
        );
        // The thick brush lays them as flat bands, each with its opacity, and
        // defines no film blur of its own.
        let brush = drawn("brushmarks", "brush_thick", SvgProfile::Display, true);
        let mut flat = Vec::new();
        with_class(&brush.group, "flat-brush-v1", &mut flat);
        assert!(!flat.is_empty());
        assert!(flat.iter().all(|band| band.attribute("opacity").is_some()));
        let soft = |rendered: &SurfaceRender| {
            rendered.definitions.iter().any(|definition| {
                definition
                    .attribute("id")
                    .is_some_and(|id| id.starts_with("surface_soft_"))
            })
        };
        assert!(!soft(&brush));
        assert!(soft(&drawn(
            "sweep",
            "brush_thick",
            SvgProfile::Display,
            true
        )));
    }

    #[test]
    fn grain_lays_one_unrepeated_tile_through_a_portable_carrier() {
        let score: Score = serde_json::from_str(
            r#"{"instructions":[{"primitive":"circle","center":[0.5,0.5],"radius":0.2,"surface":{"texture":"grain"}}]}"#,
        )
        .unwrap();
        let colors = BTreeMap::new();
        let instruction = &score.instructions[0];
        let geometry = MarkGeometry::of(instruction).unwrap();
        let rendered = render_surface(instruction, geometry, context(&colors)).unwrap();
        // Twelve dab shapes, and the tile that places them.
        assert_eq!(rendered.definitions.len(), SURFACE_GRAIN_SHAPES + 1);
        let pattern = rendered.definitions.last().unwrap();
        assert_eq!(pattern.name(), "pattern");
        // The tile covers the whole face (400 px across), so nothing repeats.
        for side in ["width", "height"] {
            let length: f64 = pattern.attribute(side).unwrap().parse().unwrap();
            assert!(length >= 400.0);
        }
        // The finer grain densely covers the face in one unrepeated tile.
        let placed = pattern
            .children()
            .iter()
            .filter(|node| matches!(node, Node::Element(element) if element.name() == "use"))
            .count();
        assert!((500..=5000).contains(&placed));
        let group = format!("{:?}", rendered.group);
        assert!(group.contains("surface-grain-carrier-v1"));
        assert!(!group.contains("clipPath"));
        assert!(!group.contains("filter"));
    }
}
