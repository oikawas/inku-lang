"""JSON Score schema for inku DDL.

座標系は 0.0-1.0 の比率 (SPEC §2 原則4)。
"""

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

Coord = tuple[float, float]

Primitive = Literal["line", "circle", "ellipse", "triangle", "square", "arc"]
LineStyle = Literal["solid", "dashed", "dotted", "dash_dot"]
Weight = Literal[
    "hair",
    "pencil",
    "pen",
    "rotring",
    "crayon",
    "chalk",
    "brush_thin",
    "brush_thick",
    "rope",
]
Color = Literal["white", "black", "blue", "red", "green", "gray"]

Amplitude = Literal["fine", "medium", "broad"]
Frequency = Literal["slow", "medium", "high"]
Quality = Literal["none", "white", "perlin", "pink", "wave"]
Dimension = Literal[
    "position_x",
    "position_y",
    "angle",
    "length",
    "thickness",
    "rotation",
    "radius",
]


class Variation(BaseModel):
    amplitude: Amplitude = "medium"
    frequency: Frequency = "medium"
    quality: Quality = "none"
    dimensions: list[Dimension] = Field(default_factory=list)


class Instruction(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    primitive: Primitive

    from_: Optional[Coord] = Field(default=None, alias="from")
    to: Optional[Coord] = None
    center: Optional[Coord] = None
    radius: Optional[float] = None
    position: Optional[Coord] = None
    size: Optional[tuple[float, float]] = None
    angle_start: Optional[float] = Field(
        default=None,
        description="arc 始端角 (度、0=東、CCW正、90=北、180=西、270=南)",
    )
    angle_end: Optional[float] = Field(
        default=None, description="arc 終端角 (度、同上)"
    )

    style: LineStyle = "solid"
    weight: Weight = "pen"
    color: Color = "black"
    variation: Optional[Variation] = None


class Score(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str = "0.1.0"
    canvas: Literal["square"] = "square"
    instructions: list[Instruction]
