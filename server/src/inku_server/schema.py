"""JSON Score schema for inku DDL.

座標系は 0.0-1.0 の比率 (SPEC §2 原則4)。
各フィールドの description がスペックの正典 (Source of Truth)。
システムプロンプトにフィールド仕様を書かないこと — ここに書く。
"""

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

Coord = tuple[float, float]

Primitive = Literal["line", "circle", "ellipse", "triangle", "square", "arc"]
LineStyle = Literal["solid", "dashed", "dotted", "dash_dot"]
Weight = Literal[
    "hair", "pencil", "pen", "rotring", "crayon", "chalk",
    "brush_thin", "brush_thick", "rope",
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
Layout = Literal["horizontal", "vertical", "radial", "scatter"]


class Variation(BaseModel):
    """揺らぎ指定。明示された場合のみ使用する。"""

    amplitude: Amplitude = Field(
        default="medium",
        description="揺れ幅: fine=細かく・震える / medium=中程度 / broad=大きく",
    )
    frequency: Frequency = Field(
        default="medium",
        description="揺れ頻度: slow=ゆっくり / medium=普通 / high=速く",
    )
    quality: Quality = Field(
        default="none",
        description="揺れ種類: perlin=揺れ・震える / wave=波打つ / pink=滲む / white=白色雑音 / none=なし",
    )
    dimensions: list[Dimension] = Field(
        default_factory=list,
        description="揺れ軸: 横線→[position_y] / 縦線→[position_x] / 斜め→[position_x,position_y]",
    )


class Arrangement(BaseModel):
    """複数の同一図形を並べる指定。Renderer が展開し N 個の SVG 要素を生成する。"""

    count: int = Field(
        ge=1,
        le=50,
        description="配置数。2以上の同一図形には必ず使う。複数 instruction 生成は禁止",
    )

    @field_validator("count", mode="before")
    @classmethod
    def _clamp_count(cls, v: object) -> object:
        if isinstance(v, (int, float)):
            return min(max(int(v), 1), 50)
        return v
    layout: Layout = Field(
        default="horizontal",
        description=(
            "horizontal=x軸等間隔 / vertical=y軸等間隔"
            " / radial=指定中心周囲に円状 / scatter=決定的ランダム散布"
        ),
    )
    margin: float = Field(
        default=0.1,
        ge=0.0,
        le=0.45,
        description="端余白 0.0-0.45 (省略=0.1)",
    )
    center: Optional[Coord] = Field(
        default=None,
        description="radial の回転中心 [x,y] (省略=0.5,0.5)",
    )
    radius: Optional[float] = Field(
        default=None,
        description="radial の配置半径 (省略=0.3)",
    )


class Instruction(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    primitive: Primitive = Field(
        description="line=線 / circle=円 / ellipse=楕円 / triangle=三角 / square=四角 / arc=弧",
    )

    from_: Optional[Coord] = Field(
        default=None,
        alias="from",
        description="line の始点 [x,y] (line のみ必須)",
    )
    to: Optional[Coord] = Field(
        default=None,
        description="line の終点 [x,y] (line のみ必須)",
    )
    center: Optional[Coord] = Field(
        default=None,
        description="circle/ellipse/arc の中心 [x,y]。square/triangle には使わない (→position)",
    )
    radius: Optional[float] = Field(
        default=None,
        description="circle/arc の半径 (省略=0.1)",
    )
    position: Optional[Coord] = Field(
        default=None,
        description="square/triangle の bbox 左上 [x,y]。中央配置: [0.5-w/2, 0.5-h/2]",
    )
    size: Optional[tuple[float, float]] = Field(
        default=None,
        description="[幅, 高さ] (省略=(0.3,0.3))",
    )
    angle_start: Optional[float] = Field(
        default=None,
        description="arc 始端角(度): 0=東 90=北 180=西 270=南、CCW正",
    )
    angle_end: Optional[float] = Field(
        default=None,
        description="arc 終端角(度) 同上",
    )

    style: LineStyle = Field(
        default="solid",
        description="solid=実線 / dashed=破線 / dotted=点線 / dash_dot=一点鎖線",
    )
    weight: Weight = Field(
        default="pen",
        description=(
            "hair=髪 / pencil=鉛筆 / pen=ペン / rotring=ロットリング"
            " / crayon=クレヨン / chalk=チョーク / brush_thin=細筆 / brush_thick=太筆 / rope=縄"
        ),
    )
    color: Color = Field(
        default="black",
        description="white=白 / black=黒 / blue=青 / red=赤 / green=緑 / gray=灰",
    )
    variation: Optional[Variation] = Field(
        default=None,
        description="揺らぎ。明示された場合のみ付ける",
    )
    arrangement: Optional[Arrangement] = Field(
        default=None,
        description="N個配置。2以上の同一図形は必ずこれを使う。複数 instruction 生成は絶対禁止",
    )


class Score(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str = "0.1.0"
    canvas: Literal["square"] = "square"
    instructions: list[Instruction]
