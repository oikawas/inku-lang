//! Prepared simple regions for exact-count fills and flat vector clipping.
//!
//! Geometry is in one common coordinate space. Callers prepare the region before
//! allocating any instance-sized collection. Holes and intersecting contours are
//! rejected, never replaced by a convex hull. This does not alter surface scatter.

use crate::determinism::hash01;
use crate::types::{Point, Seed};

/// Bounds the input-dependent preparation and clipping work.
pub const MAX_REGION_VERTICES: usize = 4096;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum RegionError {
    TooFewVertices,
    TooManyVertices,
    NonFinite,
    Degenerate,
    SelfIntersection,
    TriangulationFailed,
}

impl std::fmt::Display for RegionError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str(match self {
            Self::TooFewVertices => "fill region requires at least three vertices",
            Self::TooManyVertices => "fill region exceeds the vertex limit",
            Self::NonFinite => "fill region contains non-finite coordinates or area",
            Self::Degenerate => "fill region has degenerate geometry",
            Self::SelfIntersection => "fill region is not a simple contour",
            Self::TriangulationFailed => "fill region could not be triangulated",
        })
    }
}

impl std::error::Error for RegionError {}

#[derive(Clone, Debug, PartialEq)]
pub struct PreparedRegion {
    contour: Vec<Point>,
    triangles: Vec<[Point; 3]>,
    cumulative_area: Vec<f64>,
    area: f64,
}

impl PreparedRegion {
    /// Accepts either winding and an optional repeated closing vertex.
    pub fn new(contour: &[Point]) -> Result<Self, RegionError> {
        let mut contour = clean_contour(contour)?;
        validate_extent(contour.iter())?;
        validate_simple(&contour)?;
        let signed_area = signed_area(&contour);
        if !signed_area.is_finite() {
            return Err(RegionError::NonFinite);
        }
        if signed_area == 0.0 {
            return Err(RegionError::Degenerate);
        }
        if signed_area < 0.0 {
            contour.reverse();
        }
        let triangles = triangulate(&contour)?;
        let mut area = 0.0;
        let cumulative_area = triangles
            .iter()
            .map(|t| {
                area += cross(t[0], t[1], t[2]) / 2.0;
                area
            })
            .collect();
        if !area.is_finite() {
            return Err(RegionError::NonFinite);
        }
        if area <= 0.0 {
            return Err(RegionError::Degenerate);
        }
        Ok(Self {
            contour,
            triangles,
            cumulative_area,
            area,
        })
    }

    #[must_use]
    pub fn contour(&self) -> &[Point] {
        &self.contour
    }

    #[must_use]
    pub fn area(&self) -> f64 {
        self.area
    }

    /// Rebuild the prepared contour after a caller-owned affine transform.
    /// Sampling and clipping therefore use the same final geometry.
    pub fn transformed(
        &self,
        transform: crate::affine::AffineTransform,
    ) -> Result<Self, RegionError> {
        Self::new(
            &self
                .contour
                .iter()
                .copied()
                .map(|point| transform.apply(point))
                .collect::<Vec<_>>(),
        )
    }

    /// Inclusive of the boundary, including concave contour edges.
    #[must_use]
    pub fn contains(&self, point: Point) -> bool {
        finite(point)
            && (self
                .contour
                .iter()
                .enumerate()
                .any(|(i, &a)| on_boundary(a, self.contour[(i + 1) % self.contour.len()], point))
                || crate::surface_geometry::point_in_polygon(point, &self.contour))
    }

    /// One independent uniform area sample, with no rejection loop or grid.
    /// Count is intentionally absent so a prefix stays stable when count changes.
    #[must_use]
    pub fn sample(&self, seed: Seed, group: usize, member: usize, instance: usize) -> Point {
        let salt = format!("exact-fill:{group}:{member}:{instance}");
        let target = hash01(0, seed, &salt) * self.area;
        let index = self
            .cumulative_area
            .partition_point(|&area| area <= target)
            .min(self.triangles.len() - 1);
        let [a, b, c] = self.triangles[index];
        let u = hash01(1, seed, &salt).sqrt();
        let v = hash01(2, seed, &salt);
        Point::new(
            a.x * (1.0 - u) + b.x * (u * (1.0 - v)) + c.x * (u * v),
            a.y * (1.0 - u) + b.y * (u * (1.0 - v)) + c.y * (u * v),
        )
    }

    /// Call only after the caller's symbolic count/resource preflight succeeds.
    #[must_use]
    pub fn sample_exact(
        &self,
        count: usize,
        seed: Seed,
        group: usize,
        member: usize,
    ) -> Vec<Point> {
        (0..count)
            .map(|instance| self.sample(seed, group, member, instance))
            .collect()
    }

    /// Clips a centerline, preserving the original endpoints when wholly inside.
    /// A painted stroke must first be expanded to a filled silhouette if its full
    /// width and caps must be contained. This API does not clip stroke appearance.
    pub fn clip_line(&self, start: Point, end: Point) -> Result<Vec<[Point; 2]>, RegionError> {
        if !finite(start) || !finite(end) {
            return Err(RegionError::NonFinite);
        }
        validate_extent(self.contour.iter().chain([&start, &end]))?;
        if start == end {
            return Ok(if self.contains(start) {
                vec![[start, end]]
            } else {
                vec![]
            });
        }
        let mut cuts = vec![0.0, 1.0];
        let dx = end.x - start.x;
        let dy = end.y - start.y;
        if !dx.is_finite() || !dy.is_finite() {
            return Err(RegionError::NonFinite);
        }
        for i in 0..self.contour.len() {
            let a = self.contour[i];
            let b = self.contour[(i + 1) % self.contour.len()];
            let ex = b.x - a.x;
            let ey = b.y - a.y;
            let denominator = dx * ey - dy * ex;
            if denominator != 0.0 {
                let t = ((a.x - start.x) * ey - (a.y - start.y) * ex) / denominator;
                let u = ((a.x - start.x) * dy - (a.y - start.y) * dx) / denominator;
                if (0.0..=1.0).contains(&t) && (0.0..=1.0).contains(&u) {
                    cuts.push(t);
                }
            } else if cross(start, end, a) == 0.0 {
                for p in [a, b] {
                    let t = if dx.abs() >= dy.abs() {
                        (p.x - start.x) / dx
                    } else {
                        (p.y - start.y) / dy
                    };
                    if (0.0..=1.0).contains(&t) {
                        cuts.push(t);
                    }
                }
            }
        }
        cuts.sort_by(f64::total_cmp);
        cuts.dedup();
        let mut spans: Vec<(f64, f64)> = Vec::new();
        for pair in cuts.windows(2) {
            if self.contains(lerp(start, end, (pair[0] + pair[1]) / 2.0)) {
                if let Some(last) = spans.last_mut().filter(|last| last.1 == pair[0]) {
                    last.1 = pair[1];
                } else {
                    spans.push((pair[0], pair[1]));
                }
            }
        }
        Ok(spans
            .into_iter()
            .map(|(a, b)| [lerp(start, end, a), lerp(start, end, b)])
            .collect())
    }

    /// Clips a simple filled polygon into disjoint-interior flat fragments.
    /// Preserve the material on every fragment; do not stroke fragment edges.
    /// Fully contained polygons retain their original point sequence exactly.
    pub fn clip_polygon(&self, polygon: &[Point]) -> Result<Vec<Vec<Point>>, RegionError> {
        let subject = Self::new(polygon)?;
        validate_extent(self.contour.iter().chain(subject.contour.iter()))?;
        let mut inside = true;
        for (i, &a) in subject.contour.iter().enumerate() {
            let b = subject.contour[(i + 1) % subject.contour.len()];
            if self.clip_line(a, b)? != vec![[a, b]] {
                inside = false;
                break;
            }
        }
        if inside {
            return Ok(vec![polygon.to_vec()]);
        }
        let mut result = Vec::new();
        for source in &subject.triangles {
            for target in &self.triangles {
                let mut fragment = source.to_vec();
                for i in 0..3 {
                    fragment = clip_half_plane(&fragment, target[i], target[(i + 1) % 3]);
                }
                if fragment.len() >= 3 && signed_area(&fragment) > 0.0 {
                    result.push(fragment);
                }
            }
        }
        Ok(result)
    }
}

fn finite(p: Point) -> bool {
    p.x.is_finite() && p.y.is_finite()
}
fn validate_extent<'a>(points: impl Iterator<Item = &'a Point>) -> Result<(), RegionError> {
    let mut min = Point::new(f64::INFINITY, f64::INFINITY);
    let mut max = Point::new(f64::NEG_INFINITY, f64::NEG_INFINITY);
    for point in points {
        min.x = min.x.min(point.x);
        min.y = min.y.min(point.y);
        max.x = max.x.max(point.x);
        max.y = max.y.max(point.y);
    }
    let extent = (max.x - min.x).max(max.y - min.y);
    // Reserve headroom for cross products and their differences during clipping.
    if !(extent * extent * 8.0).is_finite() {
        return Err(RegionError::NonFinite);
    }
    Ok(())
}
fn cross(a: Point, b: Point, c: Point) -> f64 {
    (b.x - a.x) * (c.y - a.y) - (b.y - a.y) * (c.x - a.x)
}
fn lerp(a: Point, b: Point, t: f64) -> Point {
    if t == 0.0 {
        return a;
    }
    if t == 1.0 {
        return b;
    }
    Point::new(a.x + (b.x - a.x) * t, a.y + (b.y - a.y) * t)
}
fn signed_area(points: &[Point]) -> f64 {
    (1..points.len().saturating_sub(1))
        .map(|i| cross(points[0], points[i], points[i + 1]) / 2.0)
        .sum()
}
fn on_segment(a: Point, b: Point, p: Point) -> bool {
    cross(a, b, p) == 0.0
        && p.x >= a.x.min(b.x)
        && p.x <= a.x.max(b.x)
        && p.y >= a.y.min(b.y)
        && p.y <= a.y.max(b.y)
}
// Intersection arithmetic can land a few ulps beyond an edge. Keep this
// tolerance local to containment; topology validation still uses exact signs.
fn on_boundary(a: Point, b: Point, p: Point) -> bool {
    let scale =
        a.x.abs()
            .max(a.y.abs())
            .max(b.x.abs())
            .max(b.y.abs())
            .max(p.x.abs())
            .max(p.y.abs())
            .max(f64::MIN_POSITIVE);
    let tolerance = scale * f64::EPSILON * 16.0;
    cross(a, b, p).abs() <= tolerance * ((b.x - a.x).abs() + (b.y - a.y).abs())
        && p.x >= a.x.min(b.x) - tolerance
        && p.x <= a.x.max(b.x) + tolerance
        && p.y >= a.y.min(b.y) - tolerance
        && p.y <= a.y.max(b.y) + tolerance
}
fn clean_contour(points: &[Point]) -> Result<Vec<Point>, RegionError> {
    if points.len() > MAX_REGION_VERTICES {
        return Err(RegionError::TooManyVertices);
    }
    if !points.iter().all(|&p| finite(p)) {
        return Err(RegionError::NonFinite);
    }
    let mut points = points.to_vec();
    points.dedup();
    if points.len() > 1 && points.first() == points.last() {
        points.pop();
    }
    // Each removal reduces the size, bounding this cleanup independently of count.
    loop {
        if points.len() < 3 {
            return Err(RegionError::TooFewVertices);
        }
        let redundant = (0..points.len()).find(|&i| {
            on_segment(
                points[(i + points.len() - 1) % points.len()],
                points[(i + 1) % points.len()],
                points[i],
            )
        });
        if let Some(i) = redundant {
            points.remove(i);
        } else {
            break;
        }
    }
    Ok(points)
}
fn validate_simple(points: &[Point]) -> Result<(), RegionError> {
    let n = points.len();
    for i in 0..n {
        let (a, b) = (points[i], points[(i + 1) % n]);
        for j in i + 1..n {
            if j == i + 1 || (i == 0 && j == n - 1) {
                continue;
            }
            let (c, d) = (points[j], points[(j + 1) % n]);
            let values = [
                cross(a, b, c),
                cross(a, b, d),
                cross(c, d, a),
                cross(c, d, b),
            ];
            if !values.iter().all(|v| v.is_finite()) {
                return Err(RegionError::NonFinite);
            }
            let [ac, ad, ca, cb] = values;
            if on_segment(a, b, c)
                || on_segment(a, b, d)
                || on_segment(c, d, a)
                || on_segment(c, d, b)
                || ((ac > 0.0) != (ad > 0.0)
                    && (ca > 0.0) != (cb > 0.0)
                    && ac != 0.0
                    && ad != 0.0
                    && ca != 0.0
                    && cb != 0.0)
            {
                return Err(RegionError::SelfIntersection);
            }
        }
    }
    Ok(())
}
fn triangulate(points: &[Point]) -> Result<Vec<[Point; 3]>, RegionError> {
    let mut indices: Vec<usize> = (0..points.len()).collect();
    let mut result = Vec::with_capacity(points.len() - 2);
    while indices.len() > 3 {
        let ear = (0..indices.len())
            .find(|&i| {
                let a = indices[(i + indices.len() - 1) % indices.len()];
                let b = indices[i];
                let c = indices[(i + 1) % indices.len()];
                cross(points[a], points[b], points[c]) > 0.0
                    && !indices.iter().any(|&p| {
                        p != a
                            && p != b
                            && p != c
                            && cross(points[a], points[b], points[p]) >= 0.0
                            && cross(points[b], points[c], points[p]) >= 0.0
                            && cross(points[c], points[a], points[p]) >= 0.0
                    })
            })
            .ok_or(RegionError::TriangulationFailed)?;
        result.push([
            points[indices[(ear + indices.len() - 1) % indices.len()]],
            points[indices[ear]],
            points[indices[(ear + 1) % indices.len()]],
        ]);
        indices.remove(ear);
    }
    let final_triangle = [points[indices[0]], points[indices[1]], points[indices[2]]];
    if cross(final_triangle[0], final_triangle[1], final_triangle[2]) <= 0.0 {
        return Err(RegionError::TriangulationFailed);
    }
    result.push(final_triangle);
    Ok(result)
}
fn clip_half_plane(points: &[Point], a: Point, b: Point) -> Vec<Point> {
    let mut output = Vec::new();
    if points.is_empty() {
        return output;
    }
    let mut previous = points[points.len() - 1];
    let mut previous_side = cross(a, b, previous);
    for &point in points {
        let side = cross(a, b, point);
        if (side >= 0.0) != (previous_side >= 0.0) {
            output.push(lerp(
                previous,
                point,
                previous_side / (previous_side - side),
            ));
        }
        if side >= 0.0 {
            output.push(point);
        }
        previous = point;
        previous_side = side;
    }
    output.dedup();
    if output.len() > 1 && output.first() == output.last() {
        output.pop();
    }
    output
}

#[cfg(test)]
mod tests {
    use super::*;
    fn p(x: f64, y: f64) -> Point {
        Point::new(x, y)
    }
    fn concave() -> PreparedRegion {
        PreparedRegion::new(&[
            p(0., 0.),
            p(4., 0.),
            p(4., 1.),
            p(1., 1.),
            p(1., 4.),
            p(0., 4.),
        ])
        .unwrap()
    }
    #[test]
    fn exact_uniform_samples_are_seeded_inside_concave_region() {
        let region = concave();
        let points = region.sample_exact(10_000, 31, 2, 3);
        assert_eq!(points.len(), 10_000);
        assert_eq!(points, region.sample_exact(10_000, 31, 2, 3));
        assert!(points.iter().all(|&point| region.contains(point)));
        assert_eq!(&points[..7], region.sample_exact(7, 31, 2, 3));
        assert_ne!(points[0], region.sample(32, 2, 3, 0));
        assert_ne!(points[0], region.sample(31, 3, 3, 0));
        assert_ne!(points[0], region.sample(31, 2, 4, 0));
        // The unit corner occupies 1/7 of this L, not 1/3 or its hull's share.
        let corner = points.iter().filter(|p| p.x < 1.0 && p.y < 1.0).count();
        assert!(
            (1250..1600).contains(&corner),
            "corner sample count: {corner}"
        );
        assert!(region.sample_exact(0, 31, 2, 3).is_empty());
    }
    #[test]
    fn concave_clip_preserves_inside_and_removes_the_notch() {
        let region = concave();
        let inside = vec![p(0.1, 0.1), p(0.8, 0.1), p(0.8, 2.), p(0.1, 2.)];
        assert_eq!(region.clip_polygon(&inside).unwrap(), vec![inside]);
        let cover = [p(-1., -1.), p(5., -1.), p(5., 5.), p(-1., 5.)];
        let fragments = region.clip_polygon(&cover).unwrap();
        assert!((fragments.iter().map(|f| signed_area(f)).sum::<f64>() - 7.0).abs() < 1e-10);
        for f in fragments {
            assert!(f.iter().all(|&p| region.contains(p)));
        }
        assert!(
            region
                .clip_polygon(&[p(2., 2.), p(3., 2.), p(3., 3.), p(2., 3.)])
                .unwrap()
                .is_empty()
        );
        assert_eq!(
            region.clip_line(p(-1., 2.), p(5., 2.)).unwrap(),
            vec![[p(0., 2.), p(1., 2.)]]
        );
        assert_eq!(
            region.clip_line(p(0., 0.), p(4., 0.)).unwrap(),
            vec![[p(0., 0.), p(4., 0.)]]
        );
    }
    #[test]
    fn concave_inside_vertices_do_not_imply_inside_edges() {
        let region = concave();
        let triangle = [p(0.5, 0.5), p(3.5, 0.5), p(0.5, 3.5)];
        let clipped = region.clip_polygon(&triangle).unwrap();
        assert_ne!(clipped, vec![triangle.to_vec()]);
        assert!((clipped.iter().map(|f| signed_area(f)).sum::<f64>() - 2.5).abs() < 1e-10);
        let u = PreparedRegion::new(&[
            p(0., 0.),
            p(4., 0.),
            p(4., 4.),
            p(3., 4.),
            p(3., 1.),
            p(1., 1.),
            p(1., 4.),
            p(0., 4.),
        ])
        .unwrap();
        assert_eq!(
            u.clip_line(p(0.5, 2.), p(3.5, 2.)).unwrap(),
            vec![[p(0.5, 2.), p(1., 2.)], [p(3., 2.), p(3.5, 2.)]]
        );
    }
    #[test]
    fn invalid_regions_are_errors_and_winding_is_supported() {
        assert!(PreparedRegion::new(&[]).is_err());
        assert_eq!(
            concave()
                .clip_line(p(-1e200, 0.), p(1e200, 0.))
                .unwrap_err(),
            RegionError::NonFinite
        );
        assert!(PreparedRegion::new(&[p(0., 0.), p(1., 0.), p(2., 0.)]).is_err());
        assert_eq!(
            PreparedRegion::new(&[p(0., 0.), p(2., 2.), p(0., 2.), p(2., 0.)]).unwrap_err(),
            RegionError::SelfIntersection
        );
        assert_eq!(
            PreparedRegion::new(&[p(0., 0.), p(f64::NAN, 1.), p(1., 0.)]).unwrap_err(),
            RegionError::NonFinite
        );
        let clockwise = [p(0., 0.), p(0., 1.), p(1., 1.), p(1., 0.), p(0., 0.)];
        assert_eq!(PreparedRegion::new(&clockwise).unwrap().area(), 1.0);
        assert_eq!(
            PreparedRegion::new(&vec![p(0., 0.); MAX_REGION_VERTICES + 1]).unwrap_err(),
            RegionError::TooManyVertices
        );
    }
}
