//! The geometry each primitive needs, read once from an instruction's optional fields.
//!
//! One `Instruction` type carries every primitive, so its geometric fields are
//! all optional. Drawing reads them through [`MarkGeometry`] instead: a missing
//! field is refused here, and only here, as a [`MarkError`], and the drawing
//! functions receive the values their primitive requires. Values stay as the
//! Score writes them (points as fractions of the canvas, radii and sizes in
//! short-side units, angles in degrees); drawing converts them to pixels.

use crate::marks::MarkError;
use crate::types::{ArcForm, Instruction, Point, Primitive};

/// Where a Line's omitted start falls: the top of the canvas's vertical midline.
const LINE_FROM: Point = Point::new(0.5, 0.0);
/// Where a Line's omitted end falls: the bottom of the canvas's vertical midline.
const LINE_TO: Point = Point::new(0.5, 1.0);
/// The number of sides a Polygon has when the Score leaves it out.
const POLYGON_SIDES: u8 = 5;

/// The geometry of one mark, by the shape it draws.
#[derive(Clone, Copy, Debug, PartialEq)]
pub(crate) enum MarkGeometry {
    /// A Line. An omitted end falls on the canvas's vertical midline.
    Line {
        from: Point,
        to: Point,
    },
    /// A Circle or a Point, which draw alike; the instruction's primitive still
    /// tells them apart where that matters.
    Circle {
        center: Point,
        radius: f64,
    },
    Ellipse {
        center: Point,
        size: Point,
    },
    Square {
        position: Point,
        size: Point,
    },
    Triangle {
        position: Point,
        size: Point,
    },
    /// A regular Polygon, five-sided unless the Score says otherwise.
    Polygon {
        center: Point,
        radius: f64,
        sides: usize,
    },
    Arc(ArcSpan),
    /// An Arc whose form is a crescent: it is drawn inside a box, not along a span.
    Crescent {
        center: Point,
        size: Point,
    },
    Cloudform {
        center: Point,
        size: Point,
    },
}

/// An open Arc's circle and the angles it runs between, in degrees.
#[derive(Clone, Copy, Debug, PartialEq)]
pub(crate) struct ArcSpan {
    pub(crate) center: Point,
    pub(crate) radius: f64,
    pub(crate) start: f64,
    pub(crate) end: f64,
}

fn required<T>(
    instruction: &Instruction,
    value: Option<T>,
    field: &'static str,
) -> Result<T, MarkError> {
    value.ok_or(MarkError {
        primitive: instruction.primitive,
        missing_field: field,
    })
}

impl MarkGeometry {
    /// Read the fields `instruction`'s primitive requires.
    ///
    /// The first missing field is the one reported, in the order drawing has
    /// always read them (the center or position before the radius or size).
    pub(crate) fn of(instruction: &Instruction) -> Result<Self, MarkError> {
        let center = || required(instruction, instruction.center, "center");
        let radius = || required(instruction, instruction.radius, "radius");
        let size = || required(instruction, instruction.size, "size");
        let position = || required(instruction, instruction.position, "position");
        Ok(match instruction.primitive {
            Primitive::Line => Self::Line {
                from: instruction.from_.unwrap_or(LINE_FROM),
                to: instruction.to.unwrap_or(LINE_TO),
            },
            Primitive::Circle | Primitive::Point => Self::Circle {
                center: center()?,
                radius: radius()?,
            },
            Primitive::Ellipse => Self::Ellipse {
                center: center()?,
                size: size()?,
            },
            Primitive::Square => Self::Square {
                position: position()?,
                size: size()?,
            },
            Primitive::Triangle => Self::Triangle {
                position: position()?,
                size: size()?,
            },
            Primitive::Polygon => Self::Polygon {
                center: center()?,
                radius: radius()?,
                sides: usize::from(instruction.sides.unwrap_or(POLYGON_SIDES)),
            },
            Primitive::Arc if instruction.arc_form == Some(ArcForm::Crescent) => Self::Crescent {
                center: center()?,
                size: size()?,
            },
            Primitive::Arc => Self::Arc(ArcSpan::of(instruction)?),
            Primitive::Cloudform => Self::Cloudform {
                center: center()?,
                size: size()?,
            },
        })
    }
}

impl ArcSpan {
    /// Read an open Arc's center, radius, and start and end angles, in that order.
    pub(crate) fn of(instruction: &Instruction) -> Result<Self, MarkError> {
        Ok(Self {
            center: required(instruction, instruction.center, "center")?,
            radius: required(instruction, instruction.radius, "radius")?,
            start: required(instruction, instruction.angle_start, "angle_start")?,
            end: required(instruction, instruction.angle_end, "angle_end")?,
        })
    }
}
