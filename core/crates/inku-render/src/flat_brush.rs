//! The flat brush (平筆): the band a sweep (刷き) of the thin and thick brushes
//! lays, with a square entry, a dry end that narrows without parting, and faint
//! bristle streaks along it.
//!
//! The band follows the same performed centerline the round stroke did; only
//! its shape and the streaks inside it are the flat brush's own.

use crate::determinism::hash01;
use crate::geometry::centerline_normals;
use crate::materials::bristle_tone;
use crate::support::{Support, support_response};
use crate::svg::{Element, format_number, write_number};
use crate::types::{Instruction, Point, Seed, SurfaceTexture, Weight};

/// How the flat tip is held along the centerline.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub(crate) enum FlatHold {
    /// Square to the direction of travel: a curved line or arc keeps its width
    /// round the curve (the author's choice, 2026-10-14).
    Turning,
    /// Square to the whole mark's direction, from its start to its end: a
    /// straight line, and a closed shape's straight pass.
    Fixed,
}

/// How far the brush's pressure moves the width, as a share of it.
const PRESSURE: f64 = 0.10;
/// The share of the paper's response (bleed and tooth) a flat band takes. The
/// whole response would swell the band by up to 70% where the paper bleeds.
const SUPPORT_SHARE: f64 = 0.25;

/// How a brush's band dries and how many streaks it carries: the dry end's
/// length in brush sizes (the shortest, and the seeded span above it), and the
/// streak count's root, so that two fewer streaks than the rounded root of the
/// band's width (in 1,000-unit short-side units) times it run along the band.
struct DryEnd {
    streak_root: f64,
    shortest: f64,
    span: f64,
}

const fn dry_end(weight: Weight) -> DryEnd {
    match weight {
        Weight::BrushThin => DryEnd {
            streak_root: 0.9,
            shortest: 1.0,
            span: 1.0,
        },
        _ => DryEnd {
            streak_root: 1.3,
            shortest: 1.0,
            span: 1.0,
        },
    }
}

/// The band's width where it ends, as a share of its width where it starts to
/// dry: the narrowest, and the seeded span above it. A band that parted into
/// bundles read as a fringe or a fork rather than a brush (the author, 2026-10-16).
const DRY_NARROWEST: f64 = 0.55;
const DRY_NARROW_SPAN: f64 = 0.10;
const DARK_SHARE: f64 = 0.6;
/// The streaks' OKLCH lightness steps, a quarter of the first flat brush's;
/// hue and chroma are kept.
const DARK_STEP: f64 = -0.0175;
const LIGHT_STEP: f64 = 0.015;
/// The streaks' widths, as shares of the band's.
const DARK_WIDTH: f64 = 0.025;
const LIGHT_WIDTH: f64 = 0.02;

const fn flat_weight(weight: Weight) -> bool {
    matches!(weight, Weight::BrushThin | Weight::BrushThick)
}

/// Whether the mark's brush lays a flat band: a sweep of the thin or thick brush.
pub(crate) fn sweeps_flat(instruction: &Instruction) -> bool {
    flat_weight(instruction.weight)
        && instruction
            .surface
            .as_ref()
            .is_some_and(|surface| surface.texture == SurfaceTexture::Sweep)
}

pub(crate) struct FlatBandRequest<'a> {
    /// The performed centerline, in pixels.
    pub centerline: &'a [Point],
    /// The latent energy of each centerline point.
    pub energies: &'a [f64],
    pub hold: FlatHold,
    pub base_width: f64,
    pub weight: Weight,
    pub seed: Seed,
    pub support: Support,
    /// Pixels per unit of a 1,000-unit short side.
    pub scale: f64,
    /// The width of the band the brush sweeps as a line: its size. The dry end
    /// runs one to two sizes on every mark, however long the mark is.
    pub brush_size: f64,
}

pub(crate) struct FlatBand {
    /// The band, one closed path.
    pub body: String,
    pub dark: String,
    pub light: String,
    pub dark_width: f64,
    pub light_width: f64,
}

/// A point at `fraction` of the way from the left bank to the right one.
fn across(left: Point, right: Point, fraction: f64) -> Point {
    Point::new(
        left.x + (right.x - left.x) * fraction,
        left.y + (right.y - left.y) * fraction,
    )
}

/// Bundles and streaks keep hundredths of a pixel.
fn hundredths(point: Point) -> Point {
    let round = |value: f64| (value * 100.0).round() / 100.0;
    Point::new(round(point.x), round(point.y))
}

fn push_point(path: &mut String, point: Point) {
    write_number(path, point.x);
    path.push(' ');
    write_number(path, point.y);
}

fn push_points(path: &mut String, points: &[Point]) {
    if !path.is_empty() {
        path.push(' ');
    }
    path.push_str("M ");
    for (index, point) in points.iter().enumerate() {
        if index > 0 {
            path.push_str(" L ");
        }
        push_point(path, *point);
    }
}

fn push_polygon(path: &mut String, points: &[Point]) {
    if points.len() >= 3 {
        push_points(path, points);
        path.push_str(" Z");
    }
}

fn push_polyline(path: &mut String, points: &[Point]) {
    if points.len() >= 2 {
        push_points(path, points);
    }
}

struct Banks<'a> {
    parameters: &'a [f64],
    left: &'a [Point],
    right: &'a [Point],
}

impl Banks<'_> {
    /// Both banks at the arc-length parameter `t`, between the samples around it.
    fn at(&self, t: f64) -> (Point, Point) {
        let last = self.parameters.len() - 1;
        let upper = self
            .parameters
            .partition_point(|value| *value < t)
            .clamp(1, last);
        let lower = upper - 1;
        let span = self.parameters[upper] - self.parameters[lower];
        let share = if span <= 1.0e-12 {
            0.0
        } else {
            ((t - self.parameters[lower]) / span).clamp(0.0, 1.0)
        };
        let blend =
            |a: Point, b: Point| Point::new(a.x + (b.x - a.x) * share, a.y + (b.y - a.y) * share);
        (
            blend(self.left[lower], self.left[upper]),
            blend(self.right[lower], self.right[upper]),
        )
    }

    /// The parameters from `from` to `to`: both ends and the samples between.
    fn span(&self, from: f64, to: f64) -> Vec<f64> {
        let mut values = vec![from];
        values.extend(
            self.parameters
                .iter()
                .copied()
                .filter(|t| *t > from + 1.0e-9 && *t < to - 1.0e-9),
        );
        values.push(to);
        values
    }
}

/// Lay one flat band along a performed centerline, or `None` for a band without length.
pub(crate) fn flat_band(request: FlatBandRequest<'_>) -> Option<FlatBand> {
    let FlatBandRequest {
        centerline,
        energies,
        hold,
        base_width,
        weight,
        seed,
        support,
        scale,
        brush_size,
    } = request;
    let count = centerline.len();
    if count < 2 || energies.len() != count || base_width <= 0.0 {
        return None;
    }
    let mut running = vec![0.0; count];
    for index in 1..count {
        let (a, b) = (centerline[index - 1], centerline[index]);
        running[index] = running[index - 1] + (b.x - a.x).hypot(b.y - a.y);
    }
    let total = running[count - 1];
    if !total.is_finite() || total <= 1.0e-6 {
        return None;
    }
    let parameters = running
        .iter()
        .map(|value| value / total)
        .collect::<Vec<_>>();

    // The paper's response as factors of a unit width. A brush's tooth never
    // reaches the cut level, so the band stays whole.
    let (factors, _) = support_response(&vec![1.0; count], weight, seed, support);
    let widths = (0..count)
        .map(|index| {
            base_width
                * (1.0 + PRESSURE * energies[index].clamp(-1.0, 1.0))
                * (1.0 + SUPPORT_SHARE * (factors[index] - 1.0))
        })
        .collect::<Vec<_>>();
    let chord = Point::new(
        centerline[count - 1].x - centerline[0].x,
        centerline[count - 1].y - centerline[0].y,
    );
    let chord_length = chord.x.hypot(chord.y);
    let normals = if hold == FlatHold::Fixed && chord_length > 1.0e-6 {
        vec![Point::new(-chord.y / chord_length, chord.x / chord_length); count]
    } else {
        centerline_normals(centerline, false)
    };
    let left = (0..count)
        .map(|index| {
            Point::new(
                centerline[index].x + normals[index].x * widths[index] / 2.0,
                centerline[index].y + normals[index].y * widths[index] / 2.0,
            )
        })
        .collect::<Vec<_>>();
    let right = (0..count)
        .map(|index| {
            Point::new(
                centerline[index].x - normals[index].x * widths[index] / 2.0,
                centerline[index].y - normals[index].y * widths[index] / 2.0,
            )
        })
        .collect::<Vec<_>>();
    let banks = Banks {
        parameters: &parameters,
        left: &left,
        right: &right,
    };

    let drying = dry_end(weight);
    let dry = brush_size * (drying.shortest + drying.span * hash01(0, seed, "flat-dry"));
    // A mark shorter than twice its dry end lifts before the brush runs dry:
    // it ends square at its full width.
    let dries = 2.0 * dry <= total;
    let dry_from = if dries { 1.0 - dry / total } else { 1.0 };

    // The band: a square entry and both banks. Over its dry end it narrows,
    // evenly about its centerline, to a little over half its width, and ends
    // square without parting.
    let mut body = String::new();
    let end_share = DRY_NARROWEST + DRY_NARROW_SPAN * hash01(0, seed, "flat-dry-narrow");
    let mut outline = (0..count)
        .filter(|index| parameters[*index] < dry_from - 1.0e-9)
        .map(|index| left[index])
        .collect::<Vec<_>>();
    let mut far = Vec::new();
    if dries {
        for t in banks.span(dry_from, 1.0) {
            let along = (t - dry_from) / (1.0 - dry_from);
            let half = 0.5 * (1.0 - (1.0 - end_share) * along);
            let (l, r) = banks.at(t);
            outline.push(hundredths(across(l, r, 0.5 - half)));
            far.push(hundredths(across(l, r, 0.5 + half)));
        }
    } else {
        let (end_left, end_right) = banks.at(1.0);
        outline.push(end_left);
        far.push(end_right);
    }
    outline.extend(far.into_iter().rev());
    outline.extend(
        (0..count)
            .rev()
            .filter(|index| parameters[*index] < dry_from - 1.0e-9)
            .map(|index| right[index]),
    );
    push_polygon(&mut body, &outline);

    // Bristle streaks: dark ones carry the loaded entry, light ones start a
    // little later; both end before the band starts to dry.
    let unit_width = base_width / scale.max(1.0e-9);
    let streaks = ((drying.streak_root * unit_width.sqrt()).round() as usize)
        .clamp(3, 8)
        .saturating_sub(2)
        .clamp(2, 5);
    let mut dark = String::new();
    let mut light = String::new();
    for streak in 0..streaks {
        let index = streak as i64;
        let place = 0.10
            + 0.80 * (streak as f64 + 0.2 + 0.6 * hash01(index, seed, "flat-streak-place"))
                / streaks as f64;
        let is_dark = hash01(index, seed, "flat-streak-dark") < DARK_SHARE;
        let start = if is_dark {
            0.0
        } else {
            0.05 + 0.20 * hash01(index, seed, "flat-streak-start")
        };
        let floor = if is_dark { 0.55 } else { 0.5 };
        let end = (floor + (1.0 - floor) * hash01(index, seed, "flat-streak-end")).min(dry_from);
        if end <= start {
            continue;
        }
        let points = banks
            .span(start, end)
            .into_iter()
            .map(|t| {
                let (l, r) = banks.at(t);
                hundredths(across(l, r, place))
            })
            .collect::<Vec<_>>();
        push_polyline(if is_dark { &mut dark } else { &mut light }, &points);
    }
    let floor = 0.5 * scale;
    Some(FlatBand {
        body,
        dark,
        light,
        dark_width: (base_width * DARK_WIDTH).max(floor),
        light_width: (base_width * LIGHT_WIDTH).max(floor),
    })
}

/// The band in its pigment and the streaks a step darker and lighter.
///
/// The paths are opaque; the caller sets the band's opacity on the element
/// that also carries the tool's texture filter. An opacity group nested inside
/// a filtered group loses pieces when a renderer draws a cropped view of it.
pub(crate) fn flat_band_element(band: &FlatBand, color: &str, class_name: &str) -> Element {
    let mut group = Element::new("g").attr("class", class_name);
    group.push(
        Element::new("path")
            .attr("d", &band.body)
            .attr("class", "flat-brush-body-v1")
            .attr("fill", color)
            .attr("fill-rule", "nonzero")
            .attr("stroke", "none"),
    );
    for (path, step, width, name) in [
        (
            &band.dark,
            DARK_STEP,
            band.dark_width,
            "flat-brush-streak-dark-v1",
        ),
        (
            &band.light,
            LIGHT_STEP,
            band.light_width,
            "flat-brush-streak-light-v1",
        ),
    ] {
        if path.is_empty() {
            continue;
        }
        group.push(
            Element::new("path")
                .attr("d", path)
                .attr("class", name)
                .attr("fill", "none")
                .attr("stroke", bristle_tone(color, step))
                .attr("stroke-width", format_number(width))
                .attr("stroke-linecap", "butt"),
        );
    }
    group
}

#[cfg(test)]
mod tests {
    use super::*;

    /// A paper that neither bleeds nor skips, so the band shows the brush alone.
    const STILL: Support = Support {
        absorb: 0.0,
        tooth: 0.0,
    };

    fn straight(length: f64, count: usize) -> Vec<Point> {
        (0..count)
            .map(|index| Point::new(length * index as f64 / (count - 1) as f64, 100.0))
            .collect()
    }

    fn lay(
        centerline: &[Point],
        weight: Weight,
        base_width: f64,
        brush_size: f64,
        hold: FlatHold,
    ) -> FlatBand {
        flat_band(FlatBandRequest {
            centerline,
            energies: &vec![0.0; centerline.len()],
            hold,
            base_width,
            weight,
            seed: 17,
            support: STILL,
            scale: 1.0,
            brush_size,
        })
        .expect("a band with length")
    }

    fn polygons(path: &str) -> Vec<Vec<Point>> {
        path.split('M')
            .filter(|chunk| !chunk.trim().is_empty())
            .map(|chunk| {
                chunk
                    .trim()
                    .trim_end_matches('Z')
                    .split('L')
                    .map(|pair| {
                        let mut numbers = pair
                            .split_whitespace()
                            .map(|value| value.parse::<f64>().unwrap());
                        Point::new(numbers.next().unwrap(), numbers.next().unwrap())
                    })
                    .collect()
            })
            .collect()
    }

    /// The band's pairs across it, from the entry to its end: its one closed
    /// path read from both ends.
    fn pairs(band: &FlatBand) -> Vec<(Point, Point)> {
        let parts = polygons(&band.body);
        assert_eq!(parts.len(), 1, "the band ends without parting");
        let body = &parts[0];
        (0..body.len() / 2)
            .map(|index| (body[index], body[body.len() - 1 - index]))
            .collect()
    }

    fn width((left, right): &(Point, Point)) -> f64 {
        (left.x - right.x).hypot(left.y - right.y)
    }

    /// How far from a straight line's end the band starts to dry: from its last
    /// pair at full width. The drying pairs keep hundredths of a pixel, so a
    /// sample just past the start may still read as full, hundredths further on.
    fn dry_run(band: &FlatBand, length: f64, full: f64) -> f64 {
        let pairs = pairs(band);
        let last_full = pairs
            .iter()
            .rposition(|pair| width(pair) >= full - 1e-9)
            .expect("a band starts at its full width");
        length - pairs[last_full].0.x
    }

    #[test]
    fn only_a_brush_sweep_lays_a_flat_band() {
        let instruction = |weight: &str, texture: &str| {
            serde_json::from_str::<Instruction>(&format!(
                r#"{{"primitive":"line","weight":"{weight}","surface":{{"texture":"{texture}"}}}}"#
            ))
            .unwrap()
        };
        assert!(sweeps_flat(&instruction("brush_thin", "sweep")));
        assert!(sweeps_flat(&instruction("brush_thick", "sweep")));
        assert!(!sweeps_flat(&instruction("brush_thick", "wash")));
        assert!(!sweeps_flat(&instruction("brush_thick", "grain")));
        assert!(!sweeps_flat(&instruction("oil_paint", "sweep")));
        assert!(!sweeps_flat(&instruction("pen", "sweep")));
    }

    #[test]
    fn a_band_enters_square_and_keeps_its_width() {
        let band = lay(
            &straight(400.0, 41),
            Weight::BrushThick,
            24.0,
            24.0,
            FlatHold::Fixed,
        );
        let pairs = pairs(&band);
        // Without pressure or paper the band keeps the base width up to where it
        // starts to dry (at most two brush sizes, 48 px, from the end). Every
        // pair lies square across the line and is never wider than the base.
        for (left, right) in &pairs {
            assert!((left.x - right.x).abs() < 1e-9);
            let across = (left.y - right.y).abs();
            assert!(across <= 24.0 + 1e-9, "{across}");
            if left.x <= 400.0 - 48.0 {
                assert!((across - 24.0).abs() < 1e-9, "{across} at {}", left.x);
            }
        }
        assert!(pairs[0].0.x.abs() < 1e-9 && pairs[0].1.x.abs() < 1e-9);
    }

    #[test]
    fn the_dry_end_runs_by_the_brush_size_not_the_length() {
        for (weight, size) in [(Weight::BrushThin, 9.0), (Weight::BrushThick, 24.0)] {
            let short = lay(&straight(300.0, 61), weight, size, size, FlatHold::Fixed);
            let long = lay(&straight(900.0, 61), weight, size, size, FlatHold::Fixed);
            let (short_run, long_run) = (dry_run(&short, 300.0, size), dry_run(&long, 900.0, size));
            assert!((short_run - long_run).abs() < 0.1, "{short_run} {long_run}");
            assert!(
                (size - 0.1..=2.0 * size + 0.1).contains(&short_run),
                "{short_run}"
            );
            // It narrows to a little over half its width and ends square.
            for band in [&short, &long] {
                let end = *pairs(band).last().unwrap();
                assert!((end.0.x - end.1.x).abs() < 1e-9);
                let share = width(&end) / size;
                assert!((0.54..=0.66).contains(&share), "{share}");
            }
        }
    }

    #[test]
    fn a_mark_shorter_than_twice_its_dry_end_ends_square() {
        // The thick brush's dry end runs at least 24 px, so a 40 px mark cannot hold two.
        let band = lay(
            &straight(40.0, 17),
            Weight::BrushThick,
            24.0,
            24.0,
            FlatHold::Fixed,
        );
        let parts = polygons(&band.body);
        assert_eq!(parts.len(), 1);
        let body = &parts[0];
        let half = body.len() / 2;
        assert!((body[half - 1].x - 40.0).abs() < 1e-9 && (body[half].x - 40.0).abs() < 1e-9);
    }

    #[test]
    fn a_closed_shapes_pass_dries_by_its_brush_not_its_band() {
        // A thin brush's 50 px pass dries over the brush's own 9-18 px rather
        // than over a run sized by the band, and narrows to a little over half
        // the band's width.
        let band = lay(
            &straight(300.0, 17),
            Weight::BrushThin,
            50.0,
            9.0,
            FlatHold::Fixed,
        );
        let run = dry_run(&band, 300.0, 50.0);
        assert!((8.9..=18.1).contains(&run), "{run}");
        let share = width(pairs(&band).last().unwrap()) / 50.0;
        assert!((0.54..=0.66).contains(&share), "{share}");
    }

    #[test]
    fn a_curved_band_keeps_its_tip_square_to_the_travel() {
        let centerline = (0..=40)
            .map(|index| {
                let angle = std::f64::consts::FRAC_PI_2 * f64::from(index) / 40.0;
                Point::new(200.0 * angle.cos(), 200.0 * angle.sin())
            })
            .collect::<Vec<_>>();
        let normals = centerline_normals(&centerline, false);
        let band = lay(
            &centerline,
            Weight::BrushThick,
            24.0,
            24.0,
            FlatHold::Turning,
        );
        let pairs = pairs(&band);
        // The thick brush dries over at most 48 px of the 314 px arc, so the
        // first 34 pairs (to 82% of the way) are its banks at full width. The
        // path keeps six decimals, so the read-back points carry that rounding.
        for (index, (left, right)) in pairs.iter().enumerate().take(34) {
            let across = Point::new(left.x - right.x, left.y - right.y);
            assert!((across.x * normals[index].y - across.y * normals[index].x).abs() < 1e-5);
            assert!((across.x.hypot(across.y) - 24.0).abs() < 1e-5);
        }
        // Narrowed where it ends, its tip is still square to the travel there.
        // The drying pairs keep hundredths of a pixel.
        let (left, right) = *pairs.last().unwrap();
        let across = Point::new(left.x - right.x, left.y - right.y);
        let normal = normals[normals.len() - 1];
        assert!((across.x * normal.y - across.y * normal.x).abs() < 0.02);
    }
}
