//! Geometry-only affine transforms. Material dimensions remain in canvas units.

use crate::types::Point;

#[derive(Clone, Copy, Debug, PartialEq)]
pub struct AffineTransform {
    pub a: f64,
    pub b: f64,
    pub c: f64,
    pub d: f64,
    pub e: f64,
    pub f: f64,
}

impl Default for AffineTransform {
    fn default() -> Self {
        Self::identity()
    }
}

impl AffineTransform {
    pub const fn identity() -> Self {
        Self {
            a: 1.0,
            b: 0.0,
            c: 0.0,
            d: 1.0,
            e: 0.0,
            f: 0.0,
        }
    }

    pub fn is_identity(self) -> bool {
        self == Self::identity()
    }

    pub fn is_finite(self) -> bool {
        [self.a, self.b, self.c, self.d, self.e, self.f]
            .into_iter()
            .all(f64::is_finite)
    }

    pub fn apply(self, point: Point) -> Point {
        Point::new(
            self.a * point.x + self.c * point.y + self.e,
            self.b * point.x + self.d * point.y + self.f,
        )
    }

    pub fn vector(self, point: Point) -> Point {
        Point::new(
            self.a * point.x + self.c * point.y,
            self.b * point.x + self.d * point.y,
        )
    }

    /// Apply `inner` first, then `self`.
    pub fn compose(self, inner: Self) -> Self {
        Self {
            a: self.a * inner.a + self.c * inner.b,
            b: self.b * inner.a + self.d * inner.b,
            c: self.a * inner.c + self.c * inner.d,
            d: self.b * inner.c + self.d * inner.d,
            e: self.a * inner.e + self.c * inner.f + self.e,
            f: self.b * inner.e + self.d * inner.f + self.f,
        }
    }

    pub fn translation(delta: Point) -> Self {
        Self {
            e: delta.x,
            f: delta.y,
            ..Self::identity()
        }
    }

    /// Scale around the pivot, rotate around it, then translate.
    pub fn around(pivot: Point, scale_x: f64, scale_y: f64, degrees: f64, delta: Point) -> Self {
        let (sin, cos) = degrees.to_radians().sin_cos();
        let mut result = Self {
            a: cos * scale_x,
            b: sin * scale_x,
            c: -sin * scale_y,
            d: cos * scale_y,
            e: 0.0,
            f: 0.0,
        };
        let moved = result.vector(pivot);
        result.e = pivot.x - moved.x + delta.x;
        result.f = pivot.y - moved.y + delta.y;
        result
    }

    pub fn in_pixels(self, unit: f64) -> Self {
        Self {
            e: self.e * unit,
            f: self.f * unit,
            ..self
        }
    }
}
