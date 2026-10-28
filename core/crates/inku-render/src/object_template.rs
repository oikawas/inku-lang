//! Geometry of a plugin's local drawing inside a performed square box.

use crate::{
    affine::AffineTransform,
    types::{CanvasSize, Instruction, Point, Primitive},
};

/// The local canvas has the box's ratio but the work's short-side unit. The
/// geometry-only transform maps it into the box; stroke and texture metrics
/// therefore keep the work's unit instead of scaling with the box.
pub fn object_box_transform(
    instruction: &Instruction,
    canvas: CanvasSize,
    containing: AffineTransform,
) -> Result<(CanvasSize, AffineTransform), &'static str> {
    if instruction.primitive != Primitive::Square {
        return Err("object template requires a square");
    }
    let position = instruction.position.ok_or("object box has no position")?;
    let size = instruction.size.ok_or("object box has no size")?;
    if !(canvas.width.is_finite()
        && canvas.height.is_finite()
        && canvas.width > 0.0
        && canvas.height > 0.0
        && size.x.is_finite()
        && size.y.is_finite()
        && size.x > 0.0
        && size.y > 0.0
        && containing.is_finite())
    {
        return Err("invalid object box geometry");
    }
    let unit = canvas.unit();
    let width = size.x * unit;
    let height = size.y * unit;
    let short = width.min(height);
    let local = CanvasSize::new(unit * width / short, unit * height / short);
    let origin = Point::new(position.x * canvas.width, position.y * canvas.height);
    let center = Point::new(origin.x + width / 2.0, origin.y + height / 2.0);
    let map = AffineTransform {
        a: short / unit,
        b: 0.0,
        c: 0.0,
        d: short / unit,
        e: origin.x,
        f: origin.y,
    };
    let rotate = AffineTransform::around(
        center,
        1.0,
        1.0,
        instruction.rotation.unwrap_or(0.0),
        Point::new(0.0, 0.0),
    );
    let transform = containing.compose(rotate).compose(map);
    if !transform.is_finite() || !local.width.is_finite() || !local.height.is_finite() {
        return Err("invalid object box transform");
    }
    Ok((local, transform))
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn box_maps_local_corners_and_rotates_about_the_center() {
        let mut instruction: Instruction = serde_json::from_value(
            json!({"primitive":"square", "position":[0.2,0.65], "size":[0.2,0.1]}),
        )
        .unwrap();
        let (local, map) = object_box_transform(
            &instruction,
            CanvasSize::new(1000.0, 1000.0),
            AffineTransform::identity(),
        )
        .unwrap();
        assert_eq!(local, CanvasSize::new(2000.0, 1000.0));
        assert_eq!(map.apply(Point::new(0.0, 0.0)), Point::new(200.0, 650.0));
        assert_eq!(
            map.apply(Point::new(local.width, local.height)),
            Point::new(400.0, 750.0)
        );
        instruction.rotation = Some(90.0);
        let (_, rotated) = object_box_transform(
            &instruction,
            CanvasSize::new(1000.0, 1000.0),
            AffineTransform::identity(),
        )
        .unwrap();
        let center = rotated.apply(Point::new(local.width / 2.0, local.height / 2.0));
        assert!((center.x - 300.0).abs() < 1e-9 && (center.y - 700.0).abs() < 1e-9);
        let corner = rotated.apply(Point::new(0.0, 0.0));
        assert!((corner.x - 350.0).abs() < 1e-9 && (corner.y - 600.0).abs() < 1e-9);
    }
}
