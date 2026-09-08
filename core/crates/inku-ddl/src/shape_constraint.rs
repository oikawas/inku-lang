//! Finite shape constraints, independent of primitive identity and quantity.

#[derive(Clone, Copy, Debug, Default, Eq, PartialEq)]
pub struct ShapeConstraint {
    pub regular: bool,
    pub sides: Option<u64>,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct SemanticShapeConstraint {
    pub value: ShapeConstraint,
    pub provenance: crate::SourceOccurrence,
    pub additional_provenance: Vec<crate::SourceOccurrence>,
}

impl SemanticShapeConstraint {
    pub(crate) fn compatible(&self, other: &Self) -> bool {
        self.value.sides.is_none()
            || other.value.sides.is_none()
            || self.value.sides == other.value.sides
    }

    pub(crate) fn merge(&mut self, other: &Self) {
        self.value.regular |= other.value.regular;
        self.value.sides = self.value.sides.or(other.value.sides);
        for source in std::iter::once(&other.provenance).chain(&other.additional_provenance) {
            if source != &self.provenance && !self.additional_provenance.contains(source) {
                self.additional_provenance.push(source.clone());
            }
        }
    }
}

pub(crate) const SHAPE_HEADS_JA: &[(&str, &str, ShapeConstraint)] = &[
    (
        "正三角形",
        "三角",
        ShapeConstraint {
            regular: true,
            sides: None,
        },
    ),
    (
        "正方形",
        "四角",
        ShapeConstraint {
            regular: true,
            sides: None,
        },
    ),
    (
        "正四角形",
        "四角",
        ShapeConstraint {
            regular: true,
            sides: None,
        },
    ),
    (
        "五角形",
        "多角形",
        ShapeConstraint {
            regular: true,
            sides: Some(5),
        },
    ),
    (
        "六角形",
        "多角形",
        ShapeConstraint {
            regular: true,
            sides: Some(6),
        },
    ),
    (
        "七角形",
        "多角形",
        ShapeConstraint {
            regular: true,
            sides: Some(7),
        },
    ),
    (
        "八角形",
        "多角形",
        ShapeConstraint {
            regular: true,
            sides: Some(8),
        },
    ),
];
pub(crate) const SHAPE_HEADS_EN: &[(&str, &str, ShapeConstraint)] = &[
    (
        "equilateral triangle",
        "三角",
        ShapeConstraint {
            regular: true,
            sides: None,
        },
    ),
    (
        "regular square",
        "四角",
        ShapeConstraint {
            regular: true,
            sides: None,
        },
    ),
    (
        "pentagon",
        "多角形",
        ShapeConstraint {
            regular: true,
            sides: Some(5),
        },
    ),
    (
        "hexagon",
        "多角形",
        ShapeConstraint {
            regular: true,
            sides: Some(6),
        },
    ),
    (
        "heptagon",
        "多角形",
        ShapeConstraint {
            regular: true,
            sides: Some(7),
        },
    ),
    (
        "octagon",
        "多角形",
        ShapeConstraint {
            regular: true,
            sides: Some(8),
        },
    ),
];
