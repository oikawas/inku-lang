//! Tool-specific solid surfaces, built directly from portable SVG elements.

use sha2::{Digest, Sha256};

use crate::geometry::{point_to_pixels, size_to_pixels};
use crate::mark_paths::polygon_path;
use crate::marks::{MarkContext, MarkStyle, mark_style, weight_opacity};
use crate::surface_geometry::shape_bbox;
use crate::svg::{Element, format_number};
use crate::types::{
    ArcForm, Instruction, Point, Primitive, SurfaceIntensity, SurfaceTexture, SvgProfile, Weight,
};

fn level(instruction: &Instruction, values: [f64; 3]) -> f64 {
    values[match instruction.surface_intensity {
        SurfaceIntensity::Normal => 0,
        SurfaceIntensity::Dense => 1,
        SurfaceIntensity::Faint => 2,
    }]
}

pub(crate) fn solid_fill(instruction: &Instruction) -> bool {
    instruction.surface.as_ref().is_none_or(|surface| {
        matches!(
            surface.texture,
            SurfaceTexture::None | SurfaceTexture::Solid
        )
    }) && (instruction.filled
        || instruction
            .surface
            .as_ref()
            .is_some_and(|surface| surface.texture == SurfaceTexture::Solid))
}

fn active_for_closed_contour(instruction: &Instruction, closed_contour: bool) -> bool {
    instruction.weight != Weight::OilPaint
        && solid_fill(instruction)
        && (closed_contour
            || matches!(
                instruction.primitive,
                Primitive::Circle
                    | Primitive::Ellipse
                    | Primitive::Square
                    | Primitive::Triangle
                    | Primitive::Polygon
                    | Primitive::Cloudform
                    | Primitive::Point
            )
            || instruction.primitive == Primitive::Arc
                && instruction.arc_form == Some(ArcForm::Crescent))
}

pub(crate) fn active(instruction: &Instruction) -> bool {
    active_for_closed_contour(instruction, false)
}

fn identifier(context: MarkContext<'_>) -> String {
    format!(
        "tool-fill-{}-{}",
        context.instruction_index, context.mark_index
    )
}

fn seed(base: u32, context: MarkContext<'_>) -> u32 {
    base.wrapping_add((context.render_seed.unwrap_or(0) as u32).wrapping_sub(666_010))
        .wrapping_add((context.instruction_index as u32).wrapping_mul(101))
        .wrapping_add((context.mark_index as u32).wrapping_mul(211))
}

pub(crate) fn prepare_style(instruction: &Instruction, style: &mut MarkStyle) {
    prepare_style_for_closed_contour(instruction, style, false);
}

pub(crate) fn prepare_closed_contour_style(instruction: &Instruction, style: &mut MarkStyle) {
    prepare_style_for_closed_contour(instruction, style, true);
}

fn prepare_style_for_closed_contour(
    instruction: &Instruction,
    style: &mut MarkStyle,
    closed_contour: bool,
) {
    if active_for_closed_contour(instruction, closed_contour)
        && instruction.weight != Weight::Computer
    {
        let baseline = weight_opacity(instruction.weight);
        style.stroke_opacity = (style.stroke_opacity / baseline).min(1.0);
        style.fill_opacity = style.fill_opacity.map(|alpha| (alpha / baseline).min(1.0));
    }
}

pub(crate) fn group(instruction: &Instruction, context: MarkContext<'_>) -> Element {
    group_for_closed_contour(instruction, context, false)
}

pub(crate) fn closed_contour_group(instruction: &Instruction, context: MarkContext<'_>) -> Element {
    group_for_closed_contour(instruction, context, true)
}

fn group_for_closed_contour(
    instruction: &Instruction,
    context: MarkContext<'_>,
    closed_contour: bool,
) -> Element {
    let group = Element::new("g");
    if !active_for_closed_contour(instruction, closed_contour)
        || instruction.weight == Weight::Computer
    {
        return group;
    }
    if instruction.weight == Weight::Rotring {
        return group.attr(
            "opacity",
            format_number(level(instruction, [0.9, 1.0, 0.55])),
        );
    }
    if context.profile == SvgProfile::Compat {
        // Compatibility exports keep intensity through coverage, without claiming filter parity.
        return group.attr("class", "tool-fill-compat-v1").attr(
            "opacity",
            format_number(level(instruction, [0.65, 1.0, 0.35])),
        );
    }
    if matches!(
        instruction.weight,
        Weight::Burin | Weight::Drypoint | Weight::BrushThin | Weight::BrushThick
    ) {
        group.attr("mask", format!("url(#{}-mask)", identifier(context)))
    } else {
        group.attr("filter", format!("url(#{})", identifier(context)))
    }
}

pub(crate) fn interior(
    instruction: &Instruction,
    contour: &[Point],
    style: &MarkStyle,
    context: MarkContext<'_>,
) -> Option<Element> {
    interior_for_closed_contour(instruction, contour, style, context, false)
}

pub(crate) fn closed_contour_interior(
    instruction: &Instruction,
    contour: &[Point],
    style: &MarkStyle,
    context: MarkContext<'_>,
) -> Option<Element> {
    interior_for_closed_contour(instruction, contour, style, context, true)
}

fn interior_for_closed_contour(
    instruction: &Instruction,
    contour: &[Point],
    style: &MarkStyle,
    context: MarkContext<'_>,
    closed_contour: bool,
) -> Option<Element> {
    if !active_for_closed_contour(instruction, closed_contour) || !style.fill || contour.len() < 3 {
        return None;
    }
    let path = polygon_path(contour);
    if instruction.weight == Weight::Computer {
        let id = identifier(context);
        let mut fill = Element::new("g")
            .attr("class", "computer-crt-fill-v1")
            .attr(
                "opacity",
                format_number(style.fill_opacity.unwrap_or(style.stroke_opacity)),
            );
        if context.profile == SvgProfile::Compat {
            fill.push(
                Element::new("path")
                    .attr("d", &path)
                    .attr("fill", format!("url(#{id}-field)"))
                    .attr("stroke", "none"),
            );
            for (pattern, alpha) in [("grille", 0.28), ("scanlines", 1.0)] {
                fill.push(
                    Element::new("path")
                        .attr("d", &path)
                        .attr("fill", format!("url(#{id}-{pattern})"))
                        .attr("opacity", format_number(alpha))
                        .attr("stroke", "none"),
                );
            }
            return Some(fill);
        }
        let mut clip = Element::new("clipPath")
            .attr("id", format!("{id}-clip"))
            .attr("clipPathUnits", "userSpaceOnUse");
        clip.push(Element::new("path").attr("d", &path));
        let mut defs = Element::new("defs");
        defs.push(clip);
        fill.push(defs);
        fill.push(
            Element::new("path")
                .attr("d", &path)
                .attr("fill", format!("url(#{id}-field)"))
                .attr("stroke", "none"),
        );
        let mut surface = Element::new("g").attr("clip-path", format!("url(#{id}-clip)"));
        for (pattern, alpha, blurred) in [
            ("grille", 0.24, true),
            ("grille", 0.28, false),
            ("scanlines", 1.0, false),
        ] {
            if blurred && context.profile == SvgProfile::Compat {
                continue;
            }
            let mut rect = Element::new("rect")
                .attr("width", format_number(context.canvas.width))
                .attr("height", format_number(context.canvas.height))
                .attr("fill", format!("url(#{id}-{pattern})"))
                .attr("opacity", format_number(alpha));
            if blurred {
                rect.set_attr("filter", format!("url(#{id}-glow)"));
            }
            surface.push(rect);
        }
        fill.push(surface);
        return Some(fill);
    }
    let mut fill = Element::new("g").attr("class", "solid-fill-v1");
    fill.push(
        Element::new("path")
            .attr("d", path)
            .attr("class", "solid-base-fill-v1")
            .attr("fill", &style.color)
            .attr(
                "fill-opacity",
                format_number(style.fill_opacity.unwrap_or(style.stroke_opacity)),
            )
            .attr("stroke", "none"),
    );
    Some(fill)
}

struct Grain {
    fine: (f64, f64),
    coarse: (f64, f64),
    seed: u32,
    mix: f64,
    slope: f64,
    intercept: f64,
}

fn grain(instruction: &Instruction) -> Grain {
    let (fine, coarse, seed, mix, slope, intercepts) = match instruction.weight {
        Weight::Chalk => (
            (0.22, 0.30),
            (0.026, 0.036),
            23,
            0.78,
            9.0,
            [-4.0, -3.37, -4.63],
        ),
        Weight::Crayon => (
            (0.18, 0.42),
            (0.010, 0.055),
            17,
            0.82,
            9.0,
            [-3.2, -2.65, -3.83],
        ),
        Weight::Pen => ((0.28, 0.34), (0.28, 0.34), 37, 1.0, 0.8, [0.53, 0.66, 0.16]),
        Weight::Silverpoint => (
            (0.11, 0.68),
            (0.004, 0.085),
            47,
            0.78,
            3.0,
            [-1.1, -0.8, -1.35],
        ),
        Weight::Pencil => (
            (0.42, 0.56),
            (0.0035, 0.065),
            53,
            0.36,
            if instruction.surface_intensity == SurfaceIntensity::Faint {
                0.6
            } else {
                6.0
            },
            [-1.85, -1.55, -0.12],
        ),
        _ => unreachable!("grain called only for grain tools"),
    };
    Grain {
        fine,
        coarse,
        seed,
        mix,
        slope,
        intercept: level(instruction, intercepts),
    }
}

fn grain_filter(instruction: &Instruction, context: MarkContext<'_>) -> Element {
    let recipe = grain(instruction);
    let unit = context.canvas.unit() / 1000.0;
    let mut filter = Element::new("filter")
        .attr("id", identifier(context))
        .attr("x", "-2%")
        .attr("y", "-2%")
        .attr("width", "104%")
        .attr("height", "104%")
        .attr("color-interpolation-filters", "sRGB");
    let pen = instruction.weight == Weight::Pen;
    for (frequency, field_seed, result) in [
        (recipe.fine, recipe.seed, "fine"),
        (recipe.coarse, 7792, "coarse"),
    ] {
        if pen && result == "coarse" {
            continue;
        }
        filter.push(
            Element::new("feTurbulence")
                .attr("type", "fractalNoise")
                .attr(
                    "baseFrequency",
                    format!(
                        "{} {}",
                        format_number(frequency.0 / unit),
                        format_number(frequency.1 / unit)
                    ),
                )
                .attr("numOctaves", "2")
                .attr("seed", seed(field_seed, context))
                .attr("result", result),
        );
    }
    if instruction.weight == Weight::Pencil {
        filter.push(
            Element::new("feMorphology")
                .attr("in", "coarse")
                .attr("operator", "dilate")
                .attr(
                    "radius",
                    format!(
                        "{} {}",
                        format_number(0.6 * unit),
                        format_number(level(instruction, [3.0, 4.5, 3.0]) * unit)
                    ),
                )
                .attr("result", "broadBands"),
        );
    }
    if !pen {
        filter.push(
            Element::new("feComposite")
                .attr("in", "fine")
                .attr(
                    "in2",
                    if instruction.weight == Weight::Pencil {
                        "broadBands"
                    } else {
                        "coarse"
                    },
                )
                .attr("operator", "arithmetic")
                .attr("k1", "0")
                .attr("k2", format_number(recipe.mix))
                .attr("k3", format_number(1.0 - recipe.mix))
                .attr("k4", "0")
                .attr("result", "grain"),
        );
    }
    filter.push(
        Element::new("feColorMatrix")
            .attr("in", if pen { "fine" } else { "grain" })
            .attr("type", "matrix")
            .attr("values", "0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 1 0 0 0 0")
            .attr("result", "grainAlpha"),
    );
    let mut transfer = Element::new("feComponentTransfer")
        .attr("in", "grainAlpha")
        .attr("result", "deposit");
    transfer.push(
        Element::new("feFuncA")
            .attr("type", "linear")
            .attr("slope", format_number(recipe.slope))
            .attr("intercept", format_number(recipe.intercept)),
    );
    filter.push(transfer);
    filter.push(
        Element::new("feComposite")
            .attr("in", "SourceGraphic")
            .attr("in2", "deposit")
            .attr("operator", "in"),
    );
    filter
}

fn engraving_unit(weight: &str, index: usize, slot: usize, context: MarkContext<'_>) -> f64 {
    let base = format!("engraving:{weight}:{index}:{slot}");
    let payload = if context.render_seed == Some(666_010)
        && context.instruction_index == 0
        && context.mark_index == 0
    {
        base
    } else {
        format!(
            "{base}:{}:{}:{}",
            context.render_seed.unwrap_or(0),
            context.instruction_index,
            context.mark_index
        )
    };
    let digest = Sha256::digest(payload.as_bytes());
    f64::from(u32::from_be_bytes(
        digest[..4].try_into().expect("four bytes"),
    )) / 4_294_967_296.0
}

fn engraving(instruction: &Instruction, context: MarkContext<'_>) -> Vec<Element> {
    let dry = instruction.weight == Weight::Drypoint;
    let weight = if dry { "drypoint" } else { "burin" };
    let id = identifier(context);
    let half = level(
        instruction,
        if dry {
            [1.6, 2.05, 0.65]
        } else {
            [2.35, 3.0, 0.75]
        },
    );
    let floor = level(
        instruction,
        if dry {
            [0.15, 0.22, 0.025]
        } else {
            [0.13, 0.18, 0.035]
        },
    );
    let unit = context.canvas.unit() / 1000.0;
    let mut definitions = Vec::new();
    let mut lengths = Vec::new();
    for (index, (end, shoulder)) in [
        (151.0_f64, 41.0),
        (148.0, 73.0),
        (164.0, 67.0),
        (156.0, 69.0),
        (172.0, 95.0),
        (153.0, 58.0),
    ]
    .into_iter()
    .enumerate()
    {
        let end = end * 4.0;
        lengths.push(end);
        let path = if dry {
            let fractions = [0.0, 0.16, 0.33, 0.51, 0.7, 0.88, 1.0];
            let drift = [0.0, 0.2, -0.35, 0.45, -0.2, 0.15, 0.0];
            let widths = [0.0, 0.62, 0.95, 1.0, 0.82, 0.45, 0.0];
            let direction = if index % 2 == 0 { -1.0 } else { 1.0 };
            let mut points = (0..7)
                .map(|i| {
                    Point::new(
                        (end * fractions[i] * 10.0).round() / 10.0,
                        direction * drift[i] - widths[i],
                    )
                })
                .collect::<Vec<_>>();
            points.extend((1..6).rev().map(|i| {
                Point::new(
                    (end * fractions[i] * 10.0).round() / 10.0,
                    direction * drift[i] + widths[i],
                )
            }));
            polygon_path(&points)
        } else {
            format!(
                "M0 0 Q{} -1.7 {} 0 Q{} 1.7 0 0Z",
                shoulder * 4.0,
                end,
                shoulder * 4.0
            )
        };
        definitions.push(
            Element::new("path")
                .attr("id", format!("{id}-cut-{index}"))
                .attr("d", path),
        );
    }
    let mut cuts = Element::new("g").attr("id", format!("{id}-cuts"));
    // Anchor the bounded incision field to the mark, retaining the reference circle's geometry.
    let (x, y0, width, height) = shape_bbox(instruction, context)
        .or_else(|| {
            if instruction.arc_form != Some(ArcForm::Crescent) {
                return None;
            }
            let center = point_to_pixels(instruction.center?, context.canvas);
            let size = size_to_pixels(instruction.size?, context.canvas);
            Some((
                center.x - size.x / 2.0,
                center.y - size.y / 2.0,
                size.x,
                size.y,
            ))
        })
        .unwrap_or((0.0, 0.0, context.canvas.width, context.canvas.height));
    let field_scale = (width.max(height) / 600.0).max(unit * 0.001);
    let center_x = x + width / 2.0;
    let center_y = y0 + height / 2.0;
    let curved = matches!(
        instruction.primitive,
        Primitive::Circle | Primitive::Ellipse | Primitive::Point
    );
    let mut y = if curved { 174.0 } else { -210.0 };
    let last_y = if curved { 826.0 } else { 1210.0 };
    let mut index = 0;
    while y <= last_y && index < 256 {
        let sample = |slot| engraving_unit(weight, index, slot, context);
        let shape = (sample(0) * 6.0) as usize;
        let length = 610.0 + 300.0 * sample(1);
        let center = 500.0 + 180.0 * (sample(2) - 0.5);
        let slope = ((if dry { 0.7_f64 } else { 0.25_f64 }) * (2.0 * sample(3) - 1.0))
            .to_radians()
            .tan();
        let sx = length / lengths[shape];
        let matrix = [
            sx,
            slope * sx,
            0.0,
            half,
            center - length / 2.0,
            y - slope * length / 2.0,
        ];
        cuts.push(
            Element::new("use")
                .attr("href", format!("#{id}-cut-{shape}"))
                .attr(
                    "transform",
                    format!(
                        "matrix({})",
                        matrix
                            .into_iter()
                            .map(format_number)
                            .collect::<Vec<_>>()
                            .join(" ")
                    ),
                ),
        );
        y += (if dry { 8.0 } else { 6.0 }) * (0.8 + 0.4 * sample(4));
        index += 1;
    }
    definitions.push(cuts);
    if dry {
        let mut burr = Element::new("filter")
            .attr("id", format!("{id}-burr"))
            .attr("x", "-5%")
            .attr("y", "-20%")
            .attr("width", "110%")
            .attr("height", "140%");
        burr.push(
            Element::new("feTurbulence")
                .attr("type", "turbulence")
                .attr("baseFrequency", "0.55 0.19")
                .attr("numOctaves", "2")
                .attr("seed", seed(73, context))
                .attr("result", "fibers"),
        );
        burr.push(
            Element::new("feDisplacementMap")
                .attr("in", "SourceGraphic")
                .attr("in2", "fibers")
                .attr("scale", "2.2")
                .attr("xChannelSelector", "R")
                .attr("yChannelSelector", "G"),
        );
        burr.push(Element::new("feGaussianBlur").attr("stdDeviation", "0.28"));
        definitions.push(burr);
    }
    let mut marks = Element::new("g").attr("id", format!("{id}-marks"));
    if dry {
        let mut burr = Element::new("g")
            .attr("fill", "none")
            .attr("stroke", "white")
            .attr(
                "stroke-width",
                format_number(level(instruction, [1.65, 2.1, 0.65])),
            )
            .attr("stroke-dasharray", "0.7 1.3 0.5 2.1")
            .attr("stroke-linecap", "round")
            .attr(
                "opacity",
                format_number(level(instruction, [1.0, 1.0, 0.55])),
            )
            .attr("filter", format!("url(#{id}-burr)"));
        let offset = level(instruction, [0.9, 1.15, 0.35]);
        for y in [-offset, offset] {
            burr.push(
                Element::new("use")
                    .attr("href", format!("#{id}-cuts"))
                    .attr("y", format_number(y)),
            );
        }
        marks.push(burr);
    }
    marks.push(
        Element::new("use")
            .attr("href", format!("#{id}-cuts"))
            .attr("fill", "white"),
    );
    definitions.push(marks);
    let mut mask = Element::new("mask")
        .attr("id", format!("{id}-mask"))
        .attr("maskUnits", "userSpaceOnUse")
        .attr("x", "0")
        .attr("y", "0")
        .attr("width", format_number(context.canvas.width))
        .attr("height", format_number(context.canvas.height))
        .attr("style", "mask-type:alpha");
    mask.push(
        Element::new("rect")
            .attr("width", format_number(context.canvas.width))
            .attr("height", format_number(context.canvas.height))
            .attr("fill", "white")
            .attr("opacity", format_number(floor)),
    );
    mask.push(
        Element::new("use")
            .attr("href", format!("#{id}-marks"))
            .attr(
                "transform",
                format!(
                    "translate({} {}) scale({}) rotate(-27 500 500)",
                    format_number(center_x - 500.0 * field_scale),
                    format_number(center_y - 500.0 * field_scale),
                    format_number(field_scale)
                ),
            ),
    );
    definitions.push(mask);
    definitions
}

fn tint(color: &str, accent: [f64; 3], mix: f64, intensity: SurfaceIntensity) -> String {
    let channels = (0..3)
        .map(|index| {
            let channel = color
                .get(1 + index * 2..3 + index * 2)
                .and_then(|value| u8::from_str_radix(value, 16).ok())
                .unwrap_or(17);
            let normal = 12.0 + 0.9 * ((1.0 - mix) * f64::from(channel) + mix * accent[index]);
            match intensity {
                SurfaceIntensity::Normal => normal,
                SurfaceIntensity::Dense => normal * 0.58,
                SurfaceIntensity::Faint => normal * 0.5 + 127.5,
            }
            .round()
            .clamp(0.0, 255.0) as u8
        })
        .collect::<Vec<_>>();
    format!("#{:02x}{:02x}{:02x}", channels[0], channels[1], channels[2])
}

fn computer(instruction: &Instruction, context: MarkContext<'_>) -> Vec<Element> {
    let id = identifier(context);
    let style = mark_style(instruction, context);
    let unit = context.canvas.unit() / 1000.0;
    let mut gradient = Element::new("linearGradient")
        .attr("id", format!("{id}-field"))
        .attr("x1", "0")
        .attr("y1", "0")
        .attr("x2", "0.2")
        .attr("y2", "1")
        .attr("color-interpolation", "sRGB");
    for (offset, accent, mix) in [
        ("0", [50.0, 230.0, 245.0], 0.24),
        ("0.48", [255.0; 3], 0.12),
        ("1", [245.0, 65.0, 220.0], 0.24),
    ] {
        gradient.push(Element::new("stop").attr("offset", offset).attr(
            "stop-color",
            tint(&style.color, accent, mix, instruction.surface_intensity),
        ));
    }
    let mut grille = Element::new("pattern")
        .attr("id", format!("{id}-grille"))
        .attr("patternUnits", "userSpaceOnUse")
        .attr("width", format_number(3.0 * unit))
        .attr("height", format_number(8.0 * unit));
    for (x, accent) in [
        [255.0, 40.0, 60.0],
        [40.0, 255.0, 120.0],
        [70.0, 100.0, 255.0],
    ]
    .into_iter()
    .enumerate()
    {
        grille.push(
            Element::new("rect")
                .attr("x", format_number(x as f64 * unit))
                .attr("y", "0")
                .attr("width", format_number(0.78 * unit))
                .attr("height", format_number(8.0 * unit))
                .attr(
                    "fill",
                    tint(&style.color, accent, 0.32, instruction.surface_intensity),
                ),
        );
    }
    let mut scanlines = Element::new("pattern")
        .attr("id", format!("{id}-scanlines"))
        .attr("patternUnits", "userSpaceOnUse")
        .attr("width", format_number(3.0 * unit))
        .attr("height", format_number(8.0 * unit));
    for (y, alpha) in [(2.8, "0.82"), (6.8, "0.62")] {
        scanlines.push(
            Element::new("rect")
                .attr("x", "0")
                .attr("y", format_number(y * unit))
                .attr("width", format_number(3.0 * unit))
                .attr("height", format_number(1.2 * unit))
                .attr("fill", "#000000")
                .attr("fill-opacity", alpha),
        );
    }
    let mut definitions = vec![gradient, grille, scanlines];
    if context.profile != SvgProfile::Compat {
        let mut glow = Element::new("filter")
            .attr("id", format!("{id}-glow"))
            .attr("x", "-2%")
            .attr("y", "-2%")
            .attr("width", "104%")
            .attr("height", "104%")
            .attr("color-interpolation-filters", "sRGB");
        glow.push(Element::new("feGaussianBlur").attr("stdDeviation", format_number(0.65 * unit)));
        definitions.push(glow);
    }
    definitions
}

/// Brush band recipe on a 1000-unit canvas: tile size, band width, segment lengths.
fn brush_recipe(weight: Weight) -> Option<(&'static str, f64, f64, (f64, f64))> {
    match weight {
        Weight::BrushThin => Some(("brush_thin", 320.0, 11.0, (90.0, 200.0))),
        Weight::BrushThick => Some(("brush_thick", 512.0, 34.0, (200.0, 420.0))),
        _ => None,
    }
}

const BRUSH_BAND_ALPHAS: [f64; 3] = [0.3, 0.45, 0.6];

fn brush_unit(payload: &str) -> f64 {
    let digest = Sha256::digest(payload.as_bytes());
    f64::from(u32::from_be_bytes(
        digest[..4].try_into().expect("four bytes"),
    )) / 4_294_967_296.0
}

fn brush_tile_id(name: &str) -> String {
    format!("brush-tile-{name}")
}

/// The shared, seamless band tile for one brush, defined once per document.
///
/// Rows of short, slightly bowed bands run horizontally; each mark rotates the
/// tile, so the stroke direction varies without a per-mark band set. Bands
/// leaving an edge reappear on the opposite edge, and neighbours on a row keep
/// a small lift instead of overlapping round caps.
pub(crate) fn brush_tile_definition(weight: Weight) -> Option<Element> {
    let (name, size, width, (short, long)) = brush_recipe(weight)?;
    let rows = (size / (width * 0.6)).round();
    let pitch = size / rows;
    let widths = [(width * 0.8).round(), width.round(), (width * 1.2).round()];
    let mut classes: std::collections::BTreeMap<(usize, usize), String> =
        std::collections::BTreeMap::new();
    for row in 0..rows as usize {
        let row_unit = |slot: usize| brush_unit(&format!("brush-strokes:{name}:tile:{row}:{slot}"));
        let y = row as f64 * pitch + (row_unit(1) - 0.5) * pitch * 0.5;
        let mut x = -row_unit(0) * long;
        let mut segment = 0;
        while x < size {
            let part = |slot: usize| {
                brush_unit(&format!("brush-strokes:{name}:tile:{row}:{segment}:{slot}"))
            };
            let length = short + (long - short) * part(0);
            let bow = (part(1) - 0.5) * width * 1.6;
            let stroke = width * (0.75 + 0.5 * part(2));
            let alpha = 0.25 + 0.45 * part(3);
            let nearest = |values: &[f64], target: f64| {
                (0..values.len())
                    .min_by(|a, b| {
                        (values[*a] - target)
                            .abs()
                            .total_cmp(&(values[*b] - target).abs())
                    })
                    .expect("non-empty")
            };
            let key = (nearest(&widths, stroke), nearest(&BRUSH_BAND_ALPHAS, alpha));
            let mut shifts_x = vec![0.0];
            if x + length > size {
                shifts_x.push(-size);
            }
            if x < 0.0 {
                shifts_x.push(size);
            }
            for shift_x in shifts_x {
                for shift_y in [-size, 0.0, size] {
                    let top = y + shift_y;
                    if -width < top && top < size + width {
                        classes.entry(key).or_default().push_str(&format!(
                            "M{} {}q{} {} {} 0",
                            (x + shift_x).round(),
                            top.round(),
                            (length / 2.0).round(),
                            bow.round(),
                            length.round()
                        ));
                    }
                }
            }
            x += length + width * (0.2 + 0.6 * part(4));
            segment += 1;
        }
    }
    let mut bands = Element::new("g")
        .attr("fill", "none")
        .attr("stroke", "white")
        .attr("stroke-linecap", "round");
    for ((width_index, alpha_index), path) in classes {
        bands.push(
            Element::new("path")
                .attr("d", path)
                .attr("stroke-width", format_number(widths[width_index]))
                .attr(
                    "stroke-opacity",
                    format_number(BRUSH_BAND_ALPHAS[alpha_index]),
                ),
        );
    }
    let mut tile = Element::new("pattern")
        .attr("id", brush_tile_id(name))
        .attr("patternUnits", "userSpaceOnUse")
        .attr("width", format_number(size))
        .attr("height", format_number(size));
    tile.push(bands);
    Some(tile)
}

/// Whether a brush weight needs the shared tile in a non-compat document.
pub(crate) fn uses_brush_tile(instruction: &Instruction, weight: Weight) -> bool {
    instruction.weight == weight && solid_fill(instruction)
}

pub(crate) const BRUSH_TILE_WEIGHTS: [Weight; 2] = [Weight::BrushThin, Weight::BrushThick];

fn brush_mark_unit(name: &str, slot: usize, context: MarkContext<'_>) -> f64 {
    brush_unit(&format!(
        "brush-strokes:{name}:mark:{slot}:{}:{}:{}",
        context.render_seed.unwrap_or(0),
        context.instruction_index,
        context.mark_index
    ))
}

/// Per-mark mask: an even deposit floor plus the shared tile, rotated about the mark.
fn brush_mask(instruction: &Instruction, context: MarkContext<'_>) -> Vec<Element> {
    let Some((name, size, _, _)) = brush_recipe(instruction.weight) else {
        return Vec::new();
    };
    let id = identifier(context);
    let unit = context.canvas.unit() / 1000.0;
    let (x, y, width, height) = shape_bbox(instruction, context).unwrap_or((
        0.0,
        0.0,
        context.canvas.width,
        context.canvas.height,
    ));
    let angle = (2.0 * brush_mark_unit(name, 0, context) - 1.0) * 60.0;
    let shift = [
        (brush_mark_unit(name, 1, context) * size).round(),
        (brush_mark_unit(name, 2, context) * size).round(),
    ];
    let bands = Element::new("pattern")
        .attr("id", format!("{id}-bands"))
        .attr("href", format!("#{}", brush_tile_id(name)))
        .attr(
            "patternTransform",
            format!(
                "translate({} {}) rotate({}) scale({}) translate({} {})",
                format_number(x + width / 2.0),
                format_number(y + height / 2.0),
                format_number((angle * 10.0).round() / 10.0),
                format_number(unit),
                format_number(shift[0]),
                format_number(shift[1])
            ),
        );
    // Normal keeps an 8% lift between bands; dense closes it further; faint thins the whole deposit.
    let (floor, deposit) = match instruction.surface_intensity {
        SurfaceIntensity::Normal => (0.92, 1.0),
        SurfaceIntensity::Dense => (0.96, 1.0),
        SurfaceIntensity::Faint => (0.92, 0.55),
    };
    // Cover the canvas generously: marks may be rotated or displaced after masking.
    let region = |element: Element| {
        element
            .attr("x", format_number(-context.canvas.width))
            .attr("y", format_number(-context.canvas.height))
            .attr("width", format_number(context.canvas.width * 3.0))
            .attr("height", format_number(context.canvas.height * 3.0))
    };
    let mut deposit_group = Element::new("g");
    if deposit < 1.0 {
        deposit_group.set_attr("opacity", format_number(deposit));
    }
    deposit_group.push(
        region(Element::new("rect"))
            .attr("fill", "white")
            .attr("opacity", format_number(floor)),
    );
    deposit_group.push(region(Element::new("rect")).attr("fill", format!("url(#{id}-bands)")));
    let mut mask = region(Element::new("mask"))
        .attr("id", format!("{id}-mask"))
        .attr("maskUnits", "userSpaceOnUse");
    mask.push(deposit_group);
    vec![bands, mask]
}

pub(crate) fn definitions(instruction: &Instruction, context: MarkContext<'_>) -> Vec<Element> {
    definitions_for_closed_contour(instruction, context, false)
}

pub(crate) fn closed_contour_definitions(
    instruction: &Instruction,
    context: MarkContext<'_>,
) -> Vec<Element> {
    definitions_for_closed_contour(instruction, context, true)
}

fn definitions_for_closed_contour(
    instruction: &Instruction,
    context: MarkContext<'_>,
    closed_contour: bool,
) -> Vec<Element> {
    if !active_for_closed_contour(instruction, closed_contour) {
        return Vec::new();
    }
    if instruction.weight == Weight::Computer {
        return computer(instruction, context);
    }
    if context.profile == SvgProfile::Compat || instruction.weight == Weight::Rotring {
        return Vec::new();
    }
    match instruction.weight {
        Weight::Burin | Weight::Drypoint => engraving(instruction, context),
        Weight::BrushThin | Weight::BrushThick => brush_mask(instruction, context),
        _ => vec![grain_filter(instruction, context)],
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::determinism::instruction_seed;

    #[test]
    fn accepted_tool_recipe_table_keeps_geometry_seed_and_orders_tones() {
        let mut instruction: Instruction = serde_json::from_str(
            r#"{"primitive":"circle","center":[0.5,0.5],"radius":0.3,"filled":true,"surface":{"texture":"solid"}}"#,
        ).unwrap();
        for weight in [
            Weight::Chalk,
            Weight::Crayon,
            Weight::BrushThin,
            Weight::BrushThick,
            Weight::Pen,
            Weight::Rotring,
            Weight::Silverpoint,
            Weight::Pencil,
            Weight::Burin,
            Weight::Drypoint,
            Weight::Computer,
        ] {
            instruction.weight = weight;
            instruction.surface_intensity = SurfaceIntensity::Normal;
            assert!(active(&instruction));
            let expected_seed = instruction_seed(&instruction, Some(666_010));
            for intensity in [
                SurfaceIntensity::Faint,
                SurfaceIntensity::Normal,
                SurfaceIntensity::Dense,
            ] {
                instruction.surface_intensity = intensity;
                assert_eq!(instruction_seed(&instruction, Some(666_010)), expected_seed);
            }
            if matches!(
                weight,
                Weight::Rotring
                    | Weight::Burin
                    | Weight::Drypoint
                    | Weight::Computer
                    | Weight::BrushThin
                    | Weight::BrushThick
            ) {
                continue;
            }
            instruction.surface_intensity = SurfaceIntensity::Normal;
            let normal = grain(&instruction);
            instruction.surface_intensity = SurfaceIntensity::Dense;
            let dense = grain(&instruction);
            instruction.surface_intensity = SurfaceIntensity::Faint;
            let faint = grain(&instruction);
            assert_eq!(normal.fine, dense.fine);
            assert_eq!(normal.coarse, faint.coarse);
            assert_eq!(normal.seed, faint.seed);
            assert!(dense.intercept > normal.intercept);
            if weight != Weight::Pencil {
                assert!(normal.intercept > faint.intercept);
            } else {
                assert_eq!(faint.slope, 0.6);
                assert_eq!(normal.slope, 6.0);
            }
        }
        for color in ["#111111", "#a56de2", "#2468ac", "#ffffff"] {
            let tones = [
                SurfaceIntensity::Dense,
                SurfaceIntensity::Normal,
                SurfaceIntensity::Faint,
            ]
            .map(|intensity| tint(color, [50.0, 230.0, 245.0], 0.24, intensity));
            for channel in [1, 3, 5] {
                let values = tones
                    .each_ref()
                    .map(|tone| u8::from_str_radix(&tone[channel..channel + 2], 16).unwrap());
                assert!(values[0] < values[1] && values[1] < values[2]);
            }
        }
        instruction.surface.as_mut().unwrap().texture = SurfaceTexture::Wash;
        instruction.surface_intensity = SurfaceIntensity::Normal;
        assert!(!active(&instruction));
    }
}
