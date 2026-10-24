"""JSON Score schema for inku DDL.

座標系は 0.0-1.0 の比率 (SPEC §2 原則4)。
各フィールドの description がスペックの正典 (Source of Truth)。
システムプロンプトにフィールド仕様を書かないこと — ここに書く。
"""

import math
from typing import Annotated, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .limits import DEFAULT_LIMITS, Limits, current_limits, max_cluster_count


def count_field_description(limits: Limits = DEFAULT_LIMITS) -> str:
    """The count field's description, which is ALSO sent to the model.

    Field descriptions are the canonical field spec (the Stage 2 prompt says so)
    and travel to the model inside the tool schema, so the numbers in them have
    to follow the setting for the same reason the prompt body does. Pydantic
    bakes a description at class-creation time, so this is the default text and
    composer rewrites it from the effective limits when it builds the tool.
    """
    return (
        f"配置数。通常配置は1-{limits.ddl_count_max}、gridは1-{limits.ddl_count_max_grid}。"
        "同一図形・同一配置の反復に使い、反復を N 件の instruction へ展開しない"
    )


COUNT_FIELD_DESCRIPTION = count_field_description(DEFAULT_LIMITS)

Coord = tuple[float, float]
ScoreVersion = Literal["0.22.0", "0.21.0", "0.20.0", "0.19.0", "0.18.0", "0.17.0", "0.16.0", "0.15.0", "0.14.0", "0.13.0", "0.12.0", "0.11.0", "0.10.0", "0.9.0", "0.8.0", "0.7.0", "0.6.0", "0.5.0", "0.4.0", "0.3.0", "0.2.0", "0.1.0"]

Primitive = Literal[
    "line",
    "circle",
    "ellipse",
    "triangle",
    "square",
    "polygon",
    "arc",
    "point",
    "cloudform",
    "free_line",
]
# The primitives that enclose an interior, and so the only ones a `surface` is
# drawn on. It lives here because two layers decide by it and they must not
# decide differently: the renderer skips the surface of anything outside this
# set, and coerce moves a surface off an instruction the renderer would skip.
# A copy in the second layer would freeze whatever the first layer had on the
# day it was copied.
CLOSED_SHAPES = frozenset(
    {"circle", "ellipse", "square", "triangle", "polygon", "cloudform"}
)
# The surface words that speak about the mark rather than about an interior.
# 粒 is the tool skipping on the sheet, にじみ is the ink spreading into it, and
# 薄墨 is how the ink was diluted before it ever met the sheet -- all three are
# things a line does, so a `面: ...` sentence naming one of them on a line or an
# arc is not a misattachment to be moved back. It lives beside CLOSED_SHAPES and
# for the same reason: coerce decides by it whether the surface stays where the
# sentence put it, and the stroke engine decides by it whether that instruction
# works the sheet harder. A copy in the second layer would freeze whatever the
# first layer had on the day it was copied.
#
# The three do not all land in the same place. 粒 and にじみ raise the sheet's
# own two quantities (render engine 37); 薄墨 says nothing about the sheet, so
# the renderer draws it as a broader, paler band instead (render engine 38).
# 刷き (sweep, Score 0.17.0) is that broad band without paleness of its own; the
# handling word 薄い makes it pale (render engine 72).
MARK_SURFACE_WORDS = frozenset({"grain", "bleed", "wash", "sweep"})
LineStyle = Literal["solid", "dashed", "dotted", "dash_dot"]
SurfaceIntensity = Literal["normal", "dense", "faint"]
Weight = Literal[
    "silverpoint",
    "pencil",
    "pen",
    "rotring",
    "crayon",
    "chalk",
    "brush_thin",
    "brush_thick",
    "oil_paint",
    "burin",
    "drypoint",
    "computer",
]
Thinness = Literal["fine", "extra_fine", "thick", "extra_thick"]
Color = Literal[
    "white",
    "black",
    "blue",
    "red",
    "green",
    "gray",
    "yellow",
    "orange",
    "purple",
]
SurfaceTexture = Literal[
    "none",
    # The material's default fill, not a printmaker's mark. It sits in this set
    # rather than in `filled` because the saijiki says how an interior is with
    # one vocabulary, and 塗り is one of its nine quality words; sending that one
    # word down a boolean of its own is what kept it from ever arriving
    # (measured 2026-08-13: 0/14 in English, 2/4 in Japanese, against 12/14 for
    # the words that go to `texture`). `filled` still exists and still draws --
    # coerce derives each from the other.
    "solid",
    "stipple",
    "hatch",
    "crosshatch",
    "aquatint",
    "grain",
    "wash",
    "sweep",
    "brushmarks",
    "bleed",
    "paper_grain",
]
SurfaceDirection = Literal[
    "none", "horizontal", "vertical", "diagonal_rising", "diagonal_falling"
]
# The supports a work can be made on. `plain` is the absence of one, which is
# why it is the default and why the saijiki has no word for it: asking for no
# ground is not asking for a ground. The other eight are named in the `ji`
# category and each one is drawn from what that support physically is.
GroundMaterial = Literal[
    "plain",
    "paper",
    "washi",
    "ink_wash",
    "charcoal_ground",
    "canvas",
    "drawing_paper",
    "mezzotint",
]
GroundTone = Literal["white", "off_white", "warm", "cool", "gray", "black"]
GroundGrain = Literal["none", "fine", "medium", "coarse"]

Amplitude = Literal["fine", "medium", "broad"]
Frequency = Literal["slow", "medium", "high"]
Quality = Literal["none", "white", "perlin", "pink", "wave"]
Dimension = Literal[
    "position_x",
    "position_y",
    "angle",
    "length",
    "rotation",
    "radius",
]
Layout = Literal["horizontal", "vertical", "radial", "scatter", "grid"]
Path = Literal[
    "none", "diagonal", "wave", "top_to_bottom", "left_to_right", "right_half"
]
Density = Literal["none", "low", "medium", "high"]
Fade = Literal["none", "outward", "directional"]
RhythmSpacing = Literal["none", "syncopated", "accelerando", "loose"]
PresenceKind = Literal["none", "figure_like", "creature_like", "group_like"]
PresenceIntensity = Literal["low", "medium", "high"]
PresenceSymmetry = Literal["none", "bilateral", "radial"]
GazePressure = Literal["none", "low", "medium", "high"]
ContourDensity = Literal["low", "medium", "high"]
RelationType = Literal[
    "along",
    "not_touching",
    "cutting",
    "between",
    "touching",
    "connected",
    "resting_on",
    "inside",
    "overlapping",
    "crossing",
]
JOINT_RELATION_TYPES = frozenset({"resting_on", "inside", "overlapping", "crossing"})
RelationGap = Literal["narrow", "medium", "wide"]
ConnectedPositionAuthority = Literal["named_movable", "numeric_fixed"]
InstructionMode = Literal["additive", "carve"]
CarveDepth = Literal["light", "half", "bright"]
SurfaceSpacingGradient = Literal["none", "coarse_to_dense", "dense_to_coarse"]
ArcForm = Literal["crescent"]


def _clamp_unit_value(v: object, default: float | None = None) -> object:
    if v is None:
        return default if default is not None else v
    try:
        return max(0.0, min(1.0, float(v)))
    except (TypeError, ValueError):
        return default if default is not None else v


class SurfaceSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    """図形の面に適用する抽象的な質感指定。SVG 実装詳細は持たない。"""

    texture: SurfaceTexture = Field(
        default="none",
        description=(
            "面の質感: none=なし / solid=塗り / stipple=点 / hatch=平行線 / crosshatch=交差線"
            " / aquatint=段階的な粒 / grain=粒立つ / wash=薄墨・水彩 / sweep=刷き / brushmarks=刷毛目"
            " / bleed=端が滲む / paper_grain=紙目"
        ),
    )
    density: float = Field(default=0.35, ge=0.0, le=1.0, description="質感密度 0.0-1.0")
    scale: float = Field(
        default=0.35, ge=0.0, le=1.0, description="質感粒度・間隔 0.0-1.0"
    )
    opacity: float = Field(
        default=0.28, ge=0.0, le=1.0, description="質感の不透明度 0.0-1.0"
    )
    bleed: float = Field(
        default=0.0, ge=0.0, le=1.0, description="滲み・広がり量 0.0-1.0"
    )
    direction: SurfaceDirection = Field(
        default="none",
        description="線状質感の向き: none / horizontal / vertical / diagonal_rising / diagonal_falling",
    )
    spacing_gradient: SurfaceSpacingGradient = Field(
        default="none", description="ハッチ間隔の勾配"
    )
    tone_steps: int = Field(
        default=3, ge=2, le=4, description="aquatint の離散調子段数 2-4"
    )
    seed: Optional[int] = Field(
        default=None,
        description="任意の質感 seed。省略時は Renderer が演奏 seed から導出",
    )

    @field_validator("density", "scale", "opacity", "bleed", mode="before")
    @classmethod
    def _clamp_units(cls, v: object) -> object:
        return _clamp_unit_value(v)


class CanvasGroundSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    """キャンバスそのものの地・支持体の抽象的な質感指定。"""

    material: GroundMaterial = Field(
        default="plain",
        description="地の素材: plain=無地 / paper=紙 / washi=和紙 / ink_wash=薄墨地 / charcoal_ground=木炭地 / canvas=カンバス / drawing_paper=画用紙 / mezzotint=目立てした黒地",
    )
    tone: GroundTone = Field(default="white", description="地の色調")
    grain: GroundGrain = Field(default="none", description="紙目・粒の粗さ")
    density: float = Field(
        default=0.20, ge=0.0, le=1.0, description="地の粒密度 0.0-1.0"
    )
    opacity: float = Field(
        default=0.12, ge=0.0, le=1.0, description="地の質感不透明度 0.0-1.0"
    )
    seed: Optional[int] = Field(
        default=None,
        description="任意の地 texture seed。省略時は Renderer が支持体の同一性から導出",
    )

    @field_validator("density", "opacity", mode="before")
    @classmethod
    def _clamp_units(cls, v: object) -> object:
        return _clamp_unit_value(v)

    @model_validator(mode="before")
    @classmethod
    def _drop_retired_absorbency(cls, v: object) -> object:
        # 退役フィールド (render engine 15)。値は一度も描画に読まれていなかったが、
        # 地の texture seed が Score 全体のハッシュだったため、消すと粒配置が動いて
        # しまい退役できずにいた。seed を支持体の同一性 (material / grain / 演奏
        # seed) だけから作るようにしたので、退役が無条件で解けた。保存済み Score に
        # は残っているため、ここで落として再生できるようにする。
        if isinstance(v, dict) and "absorbency" in v:
            v = {k: val for k, val in v.items() if k != "absorbency"}
        return v


class CanvasRatio(BaseModel):
    """横:縦の正の整数比。最大公約数で割った形（DDL 26）。"""

    model_config = ConfigDict(extra="forbid")

    width_units: int = Field(ge=1, le=10000, description="横の項")
    height_units: int = Field(ge=1, le=10000, description="縦の項")


class CanvasSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    """キャンバス比率と地の指定。旧形式の文字列 canvas も互換で受ける。"""

    aspect: str = Field(default="square", description="キャンバス比率ID")
    ground: Optional[CanvasGroundSpec] = Field(
        default=None, description="キャンバス地の質感"
    )
    declared_ratio: Optional[CanvasRatio] = Field(
        default=None,
        exclude_if=lambda value: value is None,
        description="DDL が宣言した画面比（画面比W:H。DDL 26）。aspect は描いた紙",
    )
    fit: Optional[Literal["contain"]] = Field(
        default=None,
        exclude_if=lambda value: value is None,
        description="宣言の比の枠を紙の中央にはめ込んで描く（描画エンジン 93）",
    )

    @model_validator(mode="after")
    def _fit_requires_declared_ratio(self) -> "CanvasSpec":
        if self.fit is not None and self.declared_ratio is None:
            raise ValueError("canvas fit requires a declared ratio")
        return self


Canvas = str | CanvasSpec


class AtRegion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    """演奏時に Renderer が解決する配置領域。"""

    region: tuple[float, float, float, float] = Field(
        description="[x0,y0,x1,y1] の正規化領域。Renderer が render_seed で実座標へ解決する",
    )


class AnchorPoint(BaseModel):
    """A non-drawing explicit point that Relations may target."""

    model_config = ConfigDict(extra="forbid")

    position: Optional[Coord] = Field(
        default=None,
        exclude_if=lambda value: value is None,
        description="Point [x, y] in unit-canvas coordinates, each 0.0-1.0. Set exactly one of position or at.",
    )
    at: Optional[AtRegion] = Field(
        default=None,
        exclude_if=lambda value: value is None,
        description="Named placement region that is resolved to a point when the work is performed. Set exactly one of position or at.",
    )

    @model_validator(mode="after")
    def _require_one_finite_placement(self) -> "AnchorPoint":
        if (self.position is None) == (self.at is None):
            raise ValueError("anchors require exactly one position or at")
        if self.position is not None and (
            not all(math.isfinite(value) and 0.0 <= value <= 1.0 for value in self.position)
        ):
            raise ValueError("anchor position must be finite and within the unit canvas")
        if self.at is not None:
            x0, y0, x1, y1 = self.at.region
            if not all(math.isfinite(value) for value in self.at.region) or x0 > x1 or y0 > y1:
                raise ValueError("anchor at region must be finite and ordered")
        return self


class TouchingConstraints(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dimensions_fixed: bool = Field(description="True when the dimensions of the touching object are fixed by the DDL.")
    direction_fixed: bool = Field(description="True when the direction of the touching object is fixed by the DDL.")


class Relation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    """直前 instruction との観察可能な関係。参照先は暗黙 prev のみ。"""

    type: RelationType = Field(
        description="along=沿う / not_touching=触れない / cutting=切る / between=直前2要素の間に / touching=触れる / connected=つながる / resting_on=載る / inside=中に / overlapping=重なる / crossing=横切る（Score 0.20）",
    )
    gap: RelationGap = Field(
        default="medium",
        description="関係解決時の距離目安: narrow / medium / wide。具体距離は Renderer が解決する",
    )
    target_instruction_index: Optional[int] = Field(
        default=None,
        ge=0,
        exclude_if=lambda value: value is None,
        description="checked connected / touching が参照する元 Score instruction index。旧 relation では省略",
    )
    target_anchor_index: Optional[int] = Field(
        default=None,
        ge=0,
        exclude_if=lambda value: value is None,
        description="checked relation が参照する非描画 Score anchor index。instruction target と排他的",
    )
    target_endpoint: Optional[Literal["start", "end"]] = Field(
        default=None,
        exclude_if=lambda value: value is None,
        description="Connected target Line/Arcの始点または終点。共通変形後も同じ端点を指す。Score 0.12で明示する",
    )
    target_path_position: Annotated[float, Field(ge=0.0, le=1.0, strict=True)] | Literal["interior"] | None = Field(
        default=None,
        exclude_if=lambda value: value is None,
        description="Connected接点。Score 0.11の数値0〜1はLine中心線の位置。Score 0.13のinteriorはLine/Arcの両端以外を演奏で選ぶ",
    )
    position_authority: Optional[ConnectedPositionAuthority] = Field(
        default=None,
        exclude_if=lambda value: value is None,
        description="checked connected / touching current の位置出自。named_movable または numeric_fixed",
    )
    touching_constraints: Optional[TouchingConstraints] = Field(
        default=None,
        exclude_if=lambda value: value is None,
        description="typed touching の明示寸法・向きの固定条件。省略normalとは区別する",
    )

    @model_validator(mode="before")
    @classmethod
    def _drop_retired_contact(cls, v: object) -> object:
        # 退役フィールド (v2.7.2)。touching の接触は both_ends しか許していなかったので
        # 値は情報を運んでおらず、Renderer も読んでいなかった。保存済み Score には
        # 残っているため、ここで落として再生できるようにする。
        if isinstance(v, dict) and "contact" in v:
            v = {k: val for k, val in v.items() if k != "contact"}
        return v

    @model_validator(mode="after")
    def _require_one_explicit_target(self) -> "Relation":
        if self.target_instruction_index is not None and self.target_anchor_index is not None:
            raise ValueError("relation target instruction and anchor are exclusive")
        if self.target_endpoint is not None:
            if self.type != "connected" or self.target_instruction_index is None or self.target_anchor_index is not None:
                raise ValueError("target_endpoint requires Connected to an instruction")
            if self.target_path_position is not None:
                raise ValueError("target_endpoint and target_path_position are exclusive")
        if self.target_path_position is not None and (
            self.type != "connected" or self.target_instruction_index is None or self.target_anchor_index is not None
        ):
            raise ValueError("target_path_position requires Connected to an instruction")
        return self


class Variation(BaseModel):
    model_config = ConfigDict(extra="forbid")

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
        description="揺れ種類: perlin=細かい揺れ・震える / wave=ゆっくり揺れる・波打つ / pink=滲む / white=白色雑音 / none=なし",
    )
    dimensions: list[Dimension] = Field(
        default_factory=list,
        description="揺れ軸: 横線→[position_y] / 縦線→[position_x] / 斜め→[position_x,position_y]",
    )

    @model_validator(mode="before")
    @classmethod
    def _drop_retired_dimensions(cls, v: object) -> object:
        # thickness は Renderer が一度も読まないまま宣言だけされていた (v2.7.2 で退役)。
        # 保存済み Score が持っていても揺らぎの残りは再生できるよう、値だけ落とす。
        if isinstance(v, dict) and isinstance(v.get("dimensions"), list):
            kept = [d for d in v["dimensions"] if d != "thickness"]
            if len(kept) != len(v["dimensions"]):
                v = {**v, "dimensions": kept}
        return v


class SourceInstructionOwner(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["source_instruction"] = Field(description='Always "source_instruction".')
    instruction_index: int = Field(ge=0, description="Index of the source Score instruction. Zero or greater.")


class MacroEmitOwner(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["macro_emit"] = Field(description='Always "macro_emit".')
    source_instruction_index: int = Field(ge=0, description="Index of the source instruction that invokes the Macro. Zero or greater.")
    invocation_ordinal: int = Field(ge=0, description="Position of this invocation among the invocations of the same source. Zero or greater.")
    generated_ordinal: int = Field(ge=0, description="Position of this instruction among those the invocation generates. Zero or greater.")


class OrdinaryGroupOwner(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["ordinary_group"] = Field(description='Always "ordinary_group".')
    source_instruction_indices: list[Annotated[int, Field(ge=0)]] = Field(
        min_length=1,
        description="Indices of the source instructions in the group, unique and in source order. At least one.",
    )

    @field_validator("source_instruction_indices")
    @classmethod
    def _require_source_order(cls, value: list[int]) -> list[int]:
        if any(left >= right for left, right in zip(value, value[1:])):
            raise ValueError("ordinary group sources must be unique and source ordered")
        return value


ScoreSourceOwner = SourceInstructionOwner | MacroEmitOwner | OrdinaryGroupOwner


class ExplicitCountOrigin(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["explicit"] = Field(description='Always "explicit": the count was written in the DDL.')


class OmittedDefaultCountOrigin(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["omitted_default"] = Field(description='Always "omitted_default": the count was not written and the default was used.')


class TemplateSingleCountOrigin(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["template_single"] = Field(description='Always "template_single": a single instance from a template.')


class OmittedRegionExtentCountOrigin(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["omitted_region_extent"] = Field(description='Always "omitted_region_extent": the count was derived from the region extent.')
    reference_extent: float = Field(gt=0.0, description="Extent of the region that the count was derived from. Positive.")


class OmittedBalancedGroupCountOrigin(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["omitted_balanced_group"] = Field(description='Always "omitted_balanced_group": the counts were balanced across the group.')
    reference_extents: list[Annotated[float, Field(gt=0.0)]] = Field(description="Reference extent of each group member used to balance the counts. Each positive.")
    explicit_counts: list[Optional[Annotated[int, Field(gt=0)]]] = Field(description="Count written for each group member, or null where the count was omitted. Each positive when set.")


CountOrigin = (
    ExplicitCountOrigin
    | OmittedDefaultCountOrigin
    | TemplateSingleCountOrigin
    | OmittedRegionExtentCountOrigin
    | OmittedBalancedGroupCountOrigin
)
InstanceOrdinalScheme = Literal["source_member_then_instance_v1"]


class PlaceRecipe(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["place"] = Field(description='Always "place".')


class HorizontalLineRecipe(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["horizontal_line"] = Field(description='Always "horizontal_line".')
    cell_width: float = Field(gt=0.0, description="Horizontal spacing between successive copies, in canvas-short-edge units. Positive.")


class VerticalLineRecipe(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["vertical_line"] = Field(description='Always "vertical_line".')
    cell_height: float = Field(gt=0.0, description="Vertical spacing between successive copies, in canvas-short-edge units. Positive.")


class DiagonalLineRecipe(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["diagonal_line"] = Field(description='Always "diagonal_line".')
    step: Coord = Field(description="Offset [x, y] from one copy to the next along the diagonal, in canvas-short-edge units.")


class GridRecipe(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["grid"] = Field(description='Always "grid".')
    columns: int = Field(gt=0, description="Number of columns in the grid. Positive.")
    rows: int = Field(gt=0, description="Number of rows in the grid. Positive.")
    filled_count: int = Field(gt=0, description="Number of grid cells that receive a copy. Positive.")
    cell_width: float = Field(gt=0.0, description="Width of one grid cell, in canvas-short-edge units. Positive.")
    cell_height: float = Field(gt=0.0, description="Height of one grid cell, in canvas-short-edge units. Positive.")
    centroid: Coord = Field(description="Centroid [x, y] of the filled cells, in unit-canvas coordinates.")
    translate_to_numeric_anchor: bool = Field(description="True when the grid is translated so that its centroid lands on the numeric anchor.")


class ScatterUniformRecipe(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["scatter_uniform_with_centroid_translation"] = Field(description='Always "scatter_uniform_with_centroid_translation".')


# Performance cuts cells the size of the largest performed copy and gives each
# copy its own cell (Score 0.19.0). Only a cells placement group uses it.
class CellsRecipe(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["cells"] = Field(description='Always "cells".')


ResolvedPlacementRecipe = (
    PlaceRecipe
    | HorizontalLineRecipe
    | VerticalLineRecipe
    | DiagonalLineRecipe
    | GridRecipe
    | ScatterUniformRecipe
    | CellsRecipe
)


class NumericPlacementAnchor(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["numeric"] = Field(description='Always "numeric".')
    point: Coord = Field(description="Anchor point [x, y] written in the DDL, in unit-canvas coordinates.")


class GeneratedNumericPlacementAnchor(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["generated_numeric"] = Field(description='Always "generated_numeric".')
    point: Coord = Field(description="Anchor point [x, y] generated by the compiler, in unit-canvas coordinates.")


class NamedPlacementAnchor(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["named"] = Field(description='Always "named".')
    region: tuple[float, float, float, float] = Field(description="Named region [x0, y0, x1, y1] in unit-canvas coordinates.")


class EnclosingGroupPlacementAnchor(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["enclosing_group"] = Field(description='Always "enclosing_group".')


ResolvedPlacementAnchor = (
    NumericPlacementAnchor
    | GeneratedNumericPlacementAnchor
    | NamedPlacementAnchor
    | EnclosingGroupPlacementAnchor
)


class ResolvedArrangement(BaseModel):
    model_config = ConfigDict(extra="forbid")
    owner: ScoreSourceOwner = Field(description="Source that owns this arrangement.")
    first_instance_ordinal: int = Field(ge=0, description="Ordinal of the first instance. Zero or greater.")
    count_origin: CountOrigin = Field(description="How the instance count was determined.")
    domain: Coord = Field(description="Domain [x, y] over which the instances are laid out.")
    anchor: ResolvedPlacementAnchor = Field(description="Anchor that the arrangement is placed around.")
    recipe: ResolvedPlacementRecipe = Field(description="Recipe that positions each instance.")
    ordinal_scheme: InstanceOrdinalScheme = Field(description="Scheme for numbering the instances. Currently always source_member_then_instance_v1.")


class Arrangement(BaseModel):
    model_config = ConfigDict(extra="forbid")

    """複数の同一図形を並べる指定。Renderer が展開し N 個 of SVG 要素を生成する。"""

    # No `le=` here on purpose. A static bound is a second, invisible copy of
    # schema_count_max that no setting can reach -- and it would still admit a
    # value the configured ceiling forbids, so a test that clamps 1500 would
    # pass for the wrong reason. The clamp below is the only bound.
    count: int = Field(
        ge=1,
        description=COUNT_FIELD_DESCRIPTION,
    )

    group_size: int = Field(
        default=1,
        ge=1,
        exclude_if=lambda value: value == 1,
        description=(
            "One repeated unit spans this many consecutive instructions, starting with "
            "the instruction that owns this arrangement. Use 1 for an ordinary "
            "single-mark arrangement."
        ),
    )

    @field_validator("count", mode="before")
    @classmethod
    def _clamp_count(cls, v: object) -> object:
        # Still layout-blind, deliberately: "1-1000 for ordinary arrangements"
        # is guidance in the prompt, not a checked bound, and making it one is a
        # separate design decision.
        if isinstance(v, (int, float)):
            return min(max(int(v), 1), current_limits().schema_count_max)
        return v

    @field_validator("cluster_count", mode="before")
    @classmethod
    def _clamp_cluster_count(cls, v: object) -> object:
        if isinstance(v, (int, float)):
            return min(max(int(v), 1), max_cluster_count(current_limits()))
        return v

    layout: Layout = Field(
        default="horizontal",
        description=(
            "horizontal=x軸等間隔 / vertical=y軸等間隔"
            " / radial=指定中心周囲に円状 / scatter=決定的ランダム散布"
            " / grid=等間隔の全面反復（敷き詰め）。scatter と違い偏り・薄れを持たない"
        ),
    )
    rows: Optional[int] = Field(
        default=None,
        ge=1,
        le=64,
        description="gridの行数 1-64。rowsとcolsの両方を指定した場合はrows×colsを優先",
    )
    cols: Optional[int] = Field(
        default=None,
        ge=1,
        le=64,
        description="gridの列数 1-64。省略時はcountと領域比率から推定",
    )
    jitter: float = Field(
        default=0.12,
        ge=0.0,
        le=1.0,
        description="gridセル内の決定的な位置揺らぎ 0.0-1.0 (省略=0.12)",
    )

    @field_validator("rows", "cols", mode="before")
    @classmethod
    def _clamp_grid_size(cls, v: object) -> object:
        if isinstance(v, (int, float)):
            return min(max(int(v), 1), 64)
        return v

    @field_validator("jitter", mode="before")
    @classmethod
    def _clamp_jitter(cls, v: object) -> object:
        return _clamp_unit_value(v, default=0.12)

    path: Path = Field(
        default="none",
        description=(
            "配置軌跡。none=layout通り / diagonal=斜めの帯"
            " / wave=波打つ軌跡 / top_to_bottom=上から下"
            " / left_to_right=左から右 / right_half=右半分"
        ),
    )
    color_cycle: list[Color] = Field(
        default_factory=list,
        description=(
            "配色サイクル: 空=全要素同色。"
            "設定するとインデックス順に color_cycle を循環して各要素に適用する。"
            "色とりどり・ランダム配色の表現に使う"
        ),
    )
    margin: float = Field(
        default=0.1,
        ge=0.0,
        le=0.45,
        description="端余白 0.0-0.45 (省略=0.1)。grid全面敷き詰めでは0.02-0.08を使い、部分領域はat.regionで指定",
    )
    center: Optional[Coord] = Field(
        default=None,
        description="radial の回転中心 [x,y] (省略=0.5,0.5)",
    )
    radius: Optional[float] = Field(
        default=None,
        description="radial の配置半径 (省略=0.3)",
    )
    density: Density = Field(
        default="none",
        description=(
            "群の視覚密度。none=通常配置 / low=粗い間隔 / medium=まとまりを感じる密度"
            " / high=粒・雨・雪などの濃い群。count が大きい時の見え方を Renderer に伝える"
        ),
    )
    # No `le=` here either, and for the reason spelled out over `count`: a static
    # bound is a second, invisible copy of a limit no setting can reach. The 12
    # that used to sit here was exactly that -- raise represented_count_max and
    # the marks per cluster climb, because the drawn count follows the setting
    # and the divisor stopped at twelve. The clamp below is the only bound, and
    # composer writes the effective one back into the tool schema, so the model
    # is still told a maximum and the default configuration still says 12.
    cluster_count: Optional[int] = Field(
        default=None,
        ge=1,
        description=(
            "群を何個のまとまりに分けるか。大数量を全面均一に埋めず、"
            "3-9 個程度のクラスタで余白を残す時に使う"
        ),
    )
    fade: Fade = Field(
        default="none",
        description=(
            "群の薄れ方。outward=中心から端へ薄れる / directional=軌跡方向へ薄れる"
            " / none=薄れなし"
        ),
    )
    preserve_space: bool = Field(
        default=False,
        description="true の場合、Renderer は margin と分布を広めに取り、余白を構図要素として残す",
    )
    rhythm_spacing: RhythmSpacing = Field(
        default="none",
        description=(
            "反復間隔の揺らし方。none=等間隔 / syncopated=詰まりと抜けを交互に作る"
            " / accelerando=後半へ向けて間隔を詰める / loose=ゆるい不均等間隔"
        ),
    )
    # Absent while unset, like the Rust Score, so an arrangement without a
    # resolved recipe keeps its canonical bytes.
    resolved: Optional[ResolvedArrangement] = Field(
        default=None,
        exclude_if=lambda value: value is None,
        description="Resolved arrangement, filled in when the Score is resolved. Absent when unset.",
    )


class Instruction(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    primitive: Primitive = Field(
        description=(
            "line=線 / circle=円 / ellipse=楕円 / triangle=三角 / square=四角"
            " / polygon=多角形 / arc=弧 / point=点 / cloudform=雲形 / free_line=自由線"
        ),
    )
    note: Optional[str] = Field(
        default=None,
        description="機械が付ける処理注記。描画に影響しない。出力しないこと",
    )

    from_: Optional[Coord] = Field(
        default=None,
        alias="from",
        description="line/free_line の始点 [x,y] (line/free_line のみ必須)",
    )
    to: Optional[Coord] = Field(
        default=None,
        description="line/free_line の終点 [x,y] (line/free_line のみ必須)",
    )
    center: Optional[Coord] = Field(
        default=None,
        description="circle/ellipse/arc/point/polygon/cloudform の中心 [x,y]。square/triangle には使わない (→position)",
    )
    radius: Optional[float] = Field(
        default=None,
        description="circle/arc/point/polygon の半径 (省略=0.1)",
    )
    sides: Optional[int] = Field(
        default=None,
        ge=5,
        le=8,
        description="polygon の頂点数。5-8 の正多角形のみ。個別 primitive は増やさず、多角形語彙はここに集約する",
    )
    position: Optional[Coord] = Field(
        default=None,
        description=(
            "square/triangle の bbox 左上 [x,y]。中央配置: [0.5-w/2, 0.5-h/2]。"
            "arc では typed DDL が指定した弦中点 semantic anchor。省略時は既存の円中心 anchor"
        ),
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
    rotation: Optional[float] = Field(
        default=None,
        description=(
            "図形全体の回転角(度)。0=水平、正=時計回り、負=反時計回り。"
            "線・自由線・楕円・四角・三角・弧を中心まわりに回転する。"
        ),
    )
    arc_form: Optional[ArcForm] = Field(
        default=None,
        exclude_if=lambda value: value is None,
        description=(
            "arc の閉じた輪郭形式。crescent は歳時記の細い塗り月形で、"
            "center と size を実際の外接bboxとして使う"
        ),
    )

    filled: bool = Field(
        default=False,
        description="塗りつぶし: True=color で塗りつぶす / False=輪郭のみ。line/free_line には無効",
    )
    style: LineStyle = Field(
        default="solid",
        description="solid=実線 / dashed=破線 / dotted=点線 / dash_dot=一点鎖線",
    )
    weight: Weight = Field(
        default="pen",
        description=(
            "silverpoint=銀筆 / pencil=鉛筆 / pen=ペン / rotring=ロットリング"
            " / crayon=クレヨン / chalk=チョーク / brush_thin=細筆 / brush_thick=太筆 / oil_paint=油彩"
            " / burin=ビュラン / drypoint=ドライポイント"
            " / computer=格子に乗り、段に落ち、誤差なく反復するコンピュータ"
        ),
    )
    mode: InstructionMode = Field(
        default="additive", description="additive=地へ加える / carve=暗い地から光を彫る"
    )
    carve_depth: Optional[CarveDepth] = Field(
        default=None, description="carve の明るさ: light / half / bright"
    )
    color: Color = Field(
        default="black",
        description=(
            "white=白 / black=黒 / blue=青 / red=赤 / green=緑 / gray=灰"
            " / yellow=黄 / orange=橙 / purple=紫"
        ),
    )
    color_hint: Optional[str] = Field(
        default=None,
        description=(
            "色ニュアンスの原文保持。例: 桜色、朱に近い赤、冷たい青緑。"
            "color は抽象色のまま、Renderer が色カタログ解決時に補助情報として使う"
        ),
    )
    ink_spread: Optional[Literal["bleed"]] = Field(
        default=None,
        exclude_if=lambda value: value is None,
        description="にじみ。痕の縁からインクが不均一に広がる。面の質感と揺れの品質とは独立し、Score 0.12で明示する",
    )
    variation: Optional[Variation] = Field(
        default=None,
        description="揺らぎ。明示された場合のみ付ける",
    )
    arrangement: Optional[Arrangement] = Field(
        default=None,
        description="N個配置。同一図形・同一配置の反復は必ずこれを使い、N 件の instruction へ展開しない。個数や配置が異なる群は別 instruction にする",
    )
    at: Optional[AtRegion] = Field(
        default=None,
        description='演奏時配置領域。例: {"region":[0.56,0.32,0.68,0.44]}。固定座標より弱い指定',
    )
    relation: Optional[Relation] = Field(
        default=None,
        description="直前 instruction への関係。DDL に exact previous-object phrase がある時だけ使う。1 instruction につき最大1つ。coerce は追加せず、invalid は drop",
    )
    # Declaration order rides along into the Stage 2 tool schema, and optional
    # fields fill in more often the further back they sit. Position is spec here,
    # not something to tidy up.
    #
    # `thinness` belongs immediately before `surface`, and no further back: when
    # it took the last slot itself, `surface` lost it and `surface`'s carry fell
    # 92% -> 42%, which halved Stage 2's whole output (168 runs, 2026-08-02).
    # Do not move it back next to `weight` either -- there it carries 3%
    # (I-036 / SPEC.ja.md §5.1).
    #
    # The last slot in `Instruction` is reserved for `surface`. Appending any new
    # optional field after it repeats the same regression.
    surface_intensity: SurfaceIntensity = Field(
        default="normal",
        exclude_if=lambda value: value == "normal",
        description=(
            "痕の濃淡。normal=通常 / dense=濃い / faint=薄い。閉じた図形の平らな塗りでは塗りの濃淡、"
            "線と質感の面では痕の置き量（Score version 0.17.0以上）"
        ),
    )
    thinness: Optional[Thinness] = Field(
        default=None,
        description=(
            "線の太さの段。道具の既定より細い側はfine=細い / extra_fine=極細、"
            "太い側はthick=太い / extra_thick=極太（Score version 0.16.0以上）。省略時は道具の既定"
        ),
    )
    surface: Optional[SurfaceSpec] = Field(
        default=None,
        description="閉じた図形の面の質感。line/free_line/arc では安全に無視または近似される。SVG固有の pattern/filter は入れない",
    )

    @field_validator("weight", mode="before")
    @classmethod
    def _rename_hair_to_silverpoint(cls, v: object) -> object:
        # `hair` was never a drawing material — nobody draws with head hair, and the
        # physics the name carried (hard, no width response, almost no sway) is a
        # silverpoint, not a brush. The tool is unchanged: the same 0.5 width and the
        # same eight grammar values moved under the new name. Saved Scores hold the
        # old name, so replace it here instead of dropping it — dropping would take
        # the tool away and fall back to the default.
        if v == "hair":
            return "silverpoint"
        return v

    @field_validator("sides", mode="before")
    @classmethod
    def _clamp_sides(cls, v: object) -> object:
        if v is None:
            return v
        try:
            return min(max(int(v), 5), 8)
        except (TypeError, ValueError):
            return 5

    @model_validator(mode="after")
    def _validate_arc_form(self) -> "Instruction":
        if self.arc_form != "crescent":
            return self
        if self.primitive != "arc":
            raise ValueError("arc_form=crescent requires primitive=arc")
        if not self.filled:
            raise ValueError("arc_form=crescent requires filled=true")
        if self.center is None and self.at is None:
            raise ValueError("arc_form=crescent requires center or at")
        if self.size is None or self.size[0] <= 0.0 or self.size[1] <= 0.0:
            raise ValueError("arc_form=crescent requires a positive size")
        if any(value is not None for value in (self.radius, self.position, self.angle_start, self.angle_end)):
            raise ValueError("arc_form=crescent cannot carry open-arc geometry")
        if self.surface is not None and self.surface.texture != "none":
            raise ValueError("arc_form=crescent uses filled instead of a surface texture")
        return self


def closed_solid_fill(ins: "Instruction") -> bool:
    """閉じた図形の平らな塗りか。Score 0.17.0 より前は、濃淡の指定はこの痕にしか届かない。"""
    closed = ins.primitive in CLOSED_SHAPES or ins.primitive == "point" or ins.arc_form == "crescent"
    solid = ins.surface is None or ins.surface.texture in {"none", "solid"}
    return closed and solid and fill_is_asked_for(ins)


def fill_is_asked_for(ins: "Instruction") -> bool:
    """`filled=true` と `surface.texture="solid"` は同じ要求の 2 通りの言い方。

    ここに 1 つだけ置くのは `CLOSED_SHAPES` と同じ理由で、下の層が写しを持つと、
    写した日の判定がそこで凍るため。読み手は renderer の塗りと、coerce の 2 つの
    governor (小さすぎる粒の修理・大きすぎる塗り図形の抑制) の 3 つ。どれか 1 つが
    真偽値だけを読むと、**同じ記述が書き方次第で別の道を通る** —— それが 塗り を
    1 つの語彙へ戻した ddl engine 18 の直した defect そのものである。
    """
    return bool(ins.filled) or (
        ins.surface is not None and ins.surface.texture == "solid"
    )


class Presence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    """人・顔・動物などの具象モチーフを、抽象的な構図圧として保持する。"""

    kind: PresenceKind = Field(
        default="none",
        description=(
            "存在の種類。none=なし / figure_like=人型の気配 / creature_like=動物的な気配"
            " / group_like=群れや複数の気配。具象的な顔・身体・動物として描かない"
        ),
    )
    intensity: PresenceIntensity = Field(
        default="medium",
        description="存在感の強さ: low=弱い / medium=中程度 / high=強い",
    )
    center: Optional[Coord] = Field(
        default=None,
        description="存在感の重心。省略時は画面中央付近",
    )
    symmetry: PresenceSymmetry = Field(
        default="none",
        description="対称性: none=なし / bilateral=左右対称の圧 / radial=放射的な圧",
    )
    gaze_pressure: GazePressure = Field(
        default="none",
        description="視線の圧力。顔や目は描かず、細い線の収束や余白の圧として描く",
    )
    contour_density: ContourDensity = Field(
        default="low",
        description="輪郭密度。具象輪郭ではなく、短い弧や線片の密度として扱う",
    )


def migrate_score_payload(value: object) -> object:
    """Idempotently normalize pre-version Score mappings without adding geometry."""
    if not isinstance(value, dict):
        return value
    migrated = dict(value)
    migrated.setdefault("version", "0.1.0")
    return migrated


class TransformGroup(BaseModel):
    """One postorder Macro transform over a contiguous Score instruction span."""

    model_config = ConfigDict(extra="forbid")

    start: int = Field(ge=0, description="変換する Score instruction 範囲の開始 index")
    end: int = Field(ge=0, description="変換する Score instruction 範囲の終端 exclusive index")
    rotation_degrees: float = Field(description="まとまり全体の回転角(度)。正=時計回り")
    scale_x: float = Field(
        default=1.0,
        exclude_if=lambda value: value == 1.0,
        description="Horizontal scale factor applied to the group. 1.0 means no scaling. Must be finite.",
    )
    scale_y: float = Field(
        default=1.0,
        exclude_if=lambda value: value == 1.0,
        description="Vertical scale factor applied to the group. 1.0 means no scaling. Must be finite.",
    )
    translate_x: float = Field(
        default=0.0,
        exclude_if=lambda value: value == 0.0,
        description="Horizontal translation applied to the group, in unit-canvas units. 0.0 means none. Must be finite.",
    )
    translate_y: float = Field(
        default=0.0,
        exclude_if=lambda value: value == 0.0,
        description="Vertical translation applied to the group, in unit-canvas units. 0.0 means none. Must be finite.",
    )
    fixed_position_indices: list[Annotated[int, Field(ge=0)]] = Field(
        default_factory=list,
        exclude_if=lambda value: not value,
        description="追加平行移動できない、範囲内の元 Score instruction index",
    )
    anchor_indices: list[Annotated[int, Field(ge=0)]] = Field(
        default_factory=list,
        exclude_if=lambda value: not value,
        description="この lexical transform に属する非描画 Score anchor index",
    )

    @field_validator("rotation_degrees")
    @classmethod
    def _require_finite_rotation(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("transform group rotation_degrees must be finite")
        return value

    @field_validator("scale_x", "scale_y", "translate_x", "translate_y")
    @classmethod
    def _require_finite_affine_axis(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("transform group affine axes must be finite")
        return value


class PlacementMember(BaseModel):
    """One atomic source member of a Score 0.9 coordinated placement."""

    model_config = ConfigDict(extra="forbid")

    start: int = Field(ge=0, description="Index of the first Score instruction of this member (inclusive).")
    end: int = Field(ge=0, description="Index just past the last Score instruction of this member (exclusive).")
    anchor_indices: list[Annotated[int, Field(ge=0)]] = Field(
        default_factory=list,
        exclude_if=lambda value: not value,
        description="Indices of the Score anchors that belong to this member.",
    )
    transform_group_indices: list[Annotated[int, Field(ge=0)]] = Field(
        default_factory=list,
        exclude_if=lambda value: not value,
        description="Indices of the Score transform groups that belong to this member.",
    )
    symbolic: Optional["SymbolicMember"] = Field(
        default=None,
        description="Symbolic description of how many instances this member produces. Absent when not symbolic.",
    )


class SymbolicMember(BaseModel):
    model_config = ConfigDict(extra="forbid")

    owner: ScoreSourceOwner = Field(description="Source that owns this member.")
    kind: Literal["primitive", "macro", "ordinary_group"] = Field(description="Kind of the member: primitive, macro or ordinary_group.")
    member_ordinal: int = Field(ge=0, description="Position of this member within its group, starting at 0.")
    first_instance_ordinal: int = Field(ge=0, description="Ordinal of the first instance this member produces. Zero or greater.")
    instance_count: int = Field(gt=0, description="Number of instances this member produces. Positive.")
    count_origin: CountOrigin = Field(description="How the instance count was determined.")


class CoordinatedPlacementGroupOwner(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["coordinated_group"] = Field(description='Always "coordinated_group".')
    group_index: int = Field(ge=0, description="Index of the coordinated group that owns this placement. Zero or greater.")


class ResolvedPlacementGroup(BaseModel):
    model_config = ConfigDict(extra="forbid")

    owner: CoordinatedPlacementGroupOwner = Field(description="Coordinated group that owns this placement.")
    logical_count: int = Field(gt=0, description="Number of logical instances the group places. Positive.")
    domain: Coord = Field(description="Domain [x, y] over which the instances are laid out.")
    anchor: ResolvedPlacementAnchor = Field(description="Anchor that the group is placed around.")
    recipe: ResolvedPlacementRecipe = Field(description="Recipe that positions each instance.")
    ordinal_scheme: InstanceOrdinalScheme = Field(description="Scheme for numbering the instances. Currently always source_member_then_instance_v1.")


class CycleMembersV1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    occurrence_count: int = Field(gt=0, description="Number of occurrences in the cycle. Must equal the resolved logical count of the group it belongs to.")


class PlacementGroup(BaseModel):
    """One direct coordinated-group placement over a contiguous Score span."""

    model_config = ConfigDict(extra="forbid")

    start: int = Field(ge=0, description="配置する Score instruction 範囲の開始 index")
    end: int = Field(ge=0, description="配置する Score instruction 範囲の終端 exclusive index")
    layout: Literal["overlap", "horizontal_source_order", "scatter", "tile", "cells"] = Field(
        description="How the group's members are laid out: overlap, horizontal_source_order, scatter, tile or cells."
    )
    at: AtRegion = Field(description="群全体の中心を一度だけ解決する named 配置領域")
    members: list[PlacementMember] = Field(
        default_factory=list,
        exclude_if=lambda value: not value,
        description="Score 0.9 Macro body boundaries; absent retains the legacy drawable span",
    )
    resolved: Optional[ResolvedPlacementGroup] = Field(
        default=None,
        exclude_if=lambda value: value is None,
        description="Resolved placement of the group, filled in when the Score is resolved. Absent when unset.",
    )
    cycle_members: Optional[CycleMembersV1] = Field(
        default=None,
        exclude_if=lambda value: value is None,
        description="Cycle record when the members repeat as a cycle. Absent otherwise.",
    )

    @model_validator(mode="after")
    def _require_finite_ordered_region(self) -> "PlacementGroup":
        x0, y0, x1, y1 = self.at.region
        if not all(math.isfinite(value) for value in self.at.region) or x0 > x1 or y0 > y1:
            raise ValueError("placement group at region must be finite and ordered")
        return self


class RepetitionGroup(BaseModel):
    model_config = ConfigDict(extra="forbid")

    member: PlacementMember = Field(description="The whole Macro member that is repeated.")
    ordinal_scheme: InstanceOrdinalScheme = Field(description="Scheme for numbering the instances. Currently always source_member_then_instance_v1.")


class CoordinatedFillGroupOwner(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["coordinated_group"] = Field(description='Always "coordinated_group".')
    group_index: int = Field(ge=0, description="Index of the coordinated group that owns this fill. Zero or greater.")


class InstructionFillGroupOwner(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["instruction"] = Field(description='Always "instruction".')
    source_instruction_index: int = Field(ge=0, description="Index of the Score instruction whose mark is filled. Zero or greater.")


FillGroupOwner = CoordinatedFillGroupOwner | InstructionFillGroupOwner


class ScoreSourceSite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    region_index: int = Field(ge=0, description="Index of the DDL region that contains the source text. Zero or greater.")
    clause_index: int = Field(ge=0, description="Index of the clause within that region. Zero or greater.")


class OmittedCanvasTargetOwner(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["omitted_canvas"] = Field(description='Always "omitted_canvas": the target was not written and defaults to the canvas.')


class ExplicitCanvasTargetOwner(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["explicit_canvas"] = Field(description='Always "explicit_canvas".')
    source: ScoreSourceSite = Field(description="Location of the canvas target in the DDL source text.")


class NamedTargetOwner(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["named"] = Field(description='Always "named".')
    category: str = Field(description="Category of the named target, as written in the DDL.")
    id: str = Field(description="Identifier of the named target within its category.")


class InlineShapeTargetOwner(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["inline_shape"] = Field(description='Always "inline_shape".')
    source_instruction_index: int = Field(ge=0, description="Index of the Score instruction that defines the inline shape. Zero or greater.")
    source: ScoreSourceSite = Field(description="Location of the inline shape in the DDL source text.")


# A range the author wrote in numbers (Score 0.18.0); the range itself is the
# rectangle's bounds.
class NumericRangeTargetOwner(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["numeric_range"] = Field(description='Always "numeric_range".')
    source: ScoreSourceSite = Field(description="Location of the numeric range in the DDL source text.")


FillTargetOwner = (
    OmittedCanvasTargetOwner
    | ExplicitCanvasTargetOwner
    | NamedTargetOwner
    | InlineShapeTargetOwner
    | NumericRangeTargetOwner
)


class BboxDimensions(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["bbox"] = Field(description='Always "bbox".')
    width: float = Field(gt=0.0, description="Width of the bounding box, in canvas-short-edge units. Positive.")
    height: float = Field(gt=0.0, description="Height of the bounding box, in canvas-short-edge units. Positive.")


class RegularTriangleDimensions(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["regular_triangle"] = Field(description='Always "regular_triangle".')
    side: float = Field(gt=0.0, description="Length of one side of the equilateral triangle, in canvas-short-edge units. Positive.")


class PolygonDimensions(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["polygon"] = Field(description='Always "polygon".')
    radius: float = Field(gt=0.0, description="Radius of the polygon's circumscribed circle, in canvas-short-edge units. Positive.")
    sides: int = Field(ge=5, le=8, description="Number of vertices of the regular polygon, from 5 to 8.")


class LineDimensions(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["line"] = Field(description='Always "line".')
    length: float = Field(gt=0.0, description="Length of the line, in canvas-short-edge units. Positive.")


class CircleDimensions(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["circle"] = Field(description='Always "circle".')
    radius: float = Field(gt=0.0, description="Radius of the circle, in canvas-short-edge units. Positive.")


class ArcDimensions(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["arc"] = Field(description='Always "arc".')
    chord: float = Field(gt=0.0, description="Length of the chord between the two ends of the arc, in canvas-short-edge units. Positive.")
    sagitta: float = Field(gt=0.0, description="Distance from the chord to the top of the arc, measured perpendicular to the chord. Positive.")


class PointDimensions(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["point"] = Field(description='Always "point".')
    radius: float = Field(gt=0.0, description="Radius of the point mark, in canvas-short-edge units. Positive.")


class CenteredSizeDimensions(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["centered_size"] = Field(description='Always "centered_size".')
    width: float = Field(gt=0.0, description="Width of the rectangle, in canvas-short-edge units. Positive.")
    height: float = Field(gt=0.0, description="Height of the rectangle, in canvas-short-edge units. Positive.")


class SquareDimensions(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["square"] = Field(description='Always "square".')
    side: float = Field(gt=0.0, description="Length of one side of the square, in canvas-short-edge units. Positive.")


ResolvedShapeDimensions = (
    BboxDimensions
    | RegularTriangleDimensions
    | PolygonDimensions
    | LineDimensions
    | CircleDimensions
    | ArcDimensions
    | PointDimensions
    | CenteredSizeDimensions
    | SquareDimensions
)


class NumericFillTargetAnchor(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["numeric"] = Field(description='Always "numeric".')
    point: Coord = Field(description="Anchor point [x, y] written in the DDL, in unit-canvas coordinates.")


class GeneratedNumericFillTargetAnchor(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["generated_numeric"] = Field(description='Always "generated_numeric".')
    point: Coord = Field(description="Anchor point [x, y] generated by the compiler, in unit-canvas coordinates.")


class NamedFillTargetAnchor(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["named"] = Field(description='Always "named".')
    region: tuple[float, float, float, float] = Field(description="Named region [x0, y0, x1, y1] of the fill target, in unit-canvas coordinates.")


FillTargetAnchor = (
    NumericFillTargetAnchor | GeneratedNumericFillTargetAnchor | NamedFillTargetAnchor
)


class RectangleFillTargetGeometry(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["rectangle"] = Field(description='Always "rectangle".')
    bounds: tuple[float, float, float, float] = Field(description="Bounds [x0, y0, x1, y1] of the rectangle, in unit-canvas coordinates.")


class ShapeFillTargetGeometry(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["shape"] = Field(description='Always "shape".')
    primitive: Primitive = Field(description="Primitive of the target shape.")
    dimensions: ResolvedShapeDimensions = Field(description="Resolved dimensions of the target shape.")
    arc_form: Optional[ArcForm] = Field(default=None, description="Arc form of the target when it is an arc. Null otherwise.")
    anchor: FillTargetAnchor = Field(description="Anchor that the target shape is placed around.")
    rotation_degrees: Optional[float] = Field(default=None, description="Rotation of the target shape in degrees. Null means no rotation.")
    contour_variation: Optional[Variation] = Field(default=None, description="Variation applied to the outline of the target. Null means none.")


FillTargetGeometry = RectangleFillTargetGeometry | ShapeFillTargetGeometry


class FillTarget(BaseModel):
    model_config = ConfigDict(extra="forbid")
    owner: FillTargetOwner = Field(description="Source that defines the fill target.")
    geometry: FillTargetGeometry = Field(description="Geometry of the fill target: a rectangle or a resolved shape.")
    reference_area: float = Field(gt=0.0, description="Area of the target in canvas-short-edge units squared, used as the reference for the count. Positive.")


class FillGroup(BaseModel):
    model_config = ConfigDict(extra="forbid")
    start: int = Field(ge=0, description="Index of the first Score instruction in the filled span (inclusive).")
    end: int = Field(ge=0, description="Index just past the last Score instruction in the filled span (exclusive).")
    owner: FillGroupOwner = Field(description="Source that owns this fill group.")
    logical_count: int = Field(gt=0, description="Number of logical instances the fill places. Positive.")
    recipe: Literal["uniform_in_region"] = Field(description='Always "uniform_in_region".')
    target: FillTarget = Field(description="Region that the fill is spread over.")
    boundary: Literal["clip_to_target"] = Field(description='Always "clip_to_target": marks are clipped to the target region.')
    ordinal_scheme: InstanceOrdinalScheme = Field(description="Scheme for numbering the instances. Currently always source_member_then_instance_v1.")
    members: list[PlacementMember] = Field(description="Atomic source members of the fill, in source order.")
    cycle_members: Optional[CycleMembersV1] = Field(
        default=None,
        exclude_if=lambda value: value is None,
        description="Cycle record when the members repeat as a cycle. Absent otherwise.",
    )


class ResourceDemand(BaseModel):
    model_config = ConfigDict(extra="forbid")
    logical_objects: int = Field(ge=0, description="Number of logical objects in the Score. Zero or greater.")
    primitive_marks: int = Field(ge=0, description="Number of primitive marks drawn. Zero or greater.")
    object_templates: int = Field(ge=0, description="Number of object templates. Zero or greater.")
    maximum_per_template_primitive_marks: int = Field(ge=0, description="Largest number of primitive marks that a single template produces, counting all outer repetitions. Zero or greater.")
    maximum_resolved_count: int = Field(ge=0, description="Largest resolved count of any single arrangement or group. Zero or greater.")
    template_nodes: int = Field(ge=0, description="Number of template nodes. Zero or greater.")
    anchor_instances: int = Field(ge=0, description="Number of anchor nodes in the source, before repetition. Zero or greater.")
    transform_instances: int = Field(ge=0, description="Number of transform nodes in the source, before repetition. Zero or greater.")
    placement_instances: int = Field(ge=0, description="Number of placement nodes in the source, before repetition. Zero or greater.")
    fill_instances: int = Field(ge=0, description="Number of fill nodes in the source, before repetition. Zero or greater.")


class ResourceBudget(BaseModel):
    model_config = ConfigDict(extra="forbid")
    maximum: ResourceDemand = Field(description="Maximum resource demand allowed under this budget.")


class HardResourcePolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")
    identity: str = Field(description="Identifier of this hard policy. Must be a non-empty string.")
    budget: ResourceBudget = Field(description="Hard budget: the maximum resource demand a Score may declare.")


class ScoreResourcePolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")
    accounting_id: Literal["inku.resource-accounting.v1"] = Field(description='Accounting scheme identifier. Always "inku.resource-accounting.v1".')
    hard_policy: HardResourcePolicy = Field(description="Hard policy captured with the Score.")
    operational_budget: ResourceBudget = Field(description="Operational budget for the performance.")


class MirrorInstructionRef(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["instruction"] = Field(description='Always "instruction".')
    instruction_index: int = Field(ge=0, description="Index of the referenced Score instruction. Zero or greater.")


class MirrorRepetitionGroupRef(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["repetition_group"] = Field(description='Always "repetition_group".')
    repetition_group_index: int = Field(ge=0, description="Index into the Score's repetition_groups. Zero or greater.")


class MirrorPlacementMemberRef(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["placement_member"] = Field(description='Always "placement_member".')
    placement_group_index: int = Field(ge=0, description="Index into the Score's placement_groups. Zero or greater.")
    member_index: int = Field(ge=0, description="Index of the member within that placement group's members. Zero or greater.")


class MirrorPlacementGroupRef(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["placement_group"] = Field(description='Always "placement_group".')
    placement_group_index: int = Field(ge=0, description="Index into the Score's placement_groups. Zero or greater.")


MirrorBodyRef = Annotated[
    MirrorInstructionRef | MirrorRepetitionGroupRef | MirrorPlacementMemberRef | MirrorPlacementGroupRef,
    Field(discriminator="kind"),
]


class MirrorFollowerFactsV1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    dimensions_fixed: bool = Field(description="True when the follower's dimensions are fixed and must not be changed by the mirror.")
    direction_degrees: Optional[float] = Field(
        default=None,
        exclude_if=lambda value: value is None,
        description="Direction of the follower in degrees, when the relation fixes one. Omitted otherwise. Must be finite.",
    )

    @field_validator("direction_degrees")
    @classmethod
    def _require_finite_direction(cls, value: float | None) -> float | None:
        if value is not None and not math.isfinite(value):
            raise ValueError("mirror direction_degrees must be finite")
        return value


class MirrorRelationV1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    target: MirrorBodyRef = Field(description="The body that is mirrored.")
    follower: MirrorBodyRef = Field(description="The body that is drawn as the mirror image of the target.")
    follower_facts: MirrorFollowerFactsV1 = Field(description="Facts about the follower that the renderer must keep.")


class Score(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: ScoreVersion = Field(
        default="0.9.0",
        description="Score format version. Governs which fields and values are allowed.",
    )
    canvas: Canvas = Field(
        default="square",
        description=(
            "キャンバス比率ID、または {aspect, ground}。標準値は square。"
            "ground は紙目・薄墨地などの支持体質感を保持する"
        ),
    )
    background: Color = Field(
        default="white",
        description=(
            "背景色: white=白 / black=黒 / blue=青 / red=赤 / green=緑 / gray=灰"
            " / yellow=黄 / orange=橙 / purple=紫 (省略=white)。"
            "「背景を黒で埋める」→ black。旧表現「背景を黒で塗りつぶす」も同じ"
        ),
    )
    presence: Optional[Presence] = Field(
        default=None,
        description=(
            "人・顔・動物・群れなどの対象物を直接描かず、存在感、重心、対称性、視線の圧力、"
            "群れ、輪郭密度へ抽象化した描画パラメータ。目鼻口・四肢・耳・尻尾などの具象部品は禁止"
        ),
    )
    instructions: list[Instruction] = Field(
        description="Drawing instructions, in drawing order. Each one is a single mark or group of marks.",
    )
    anchors: list["AnchorPoint"] = Field(
        default_factory=list,
        exclude_if=lambda value: not value,
        description="Relation が参照できる非描画の明示基準点",
    )
    transform_groups: list[TransformGroup] = Field(
        default_factory=list,
        exclude_if=lambda value: not value,
        description=(
            "Macro のまとまり変換。内側から外側の postorder で、各範囲は Score instruction "
            "index の連続区間を表す"
        ),
    )
    placement_groups: list[PlacementGroup] = Field(
        default_factory=list,
        exclude_if=lambda value: not value,
        description=(
            "通常DDLのdirect coordinated group配置。source順の連続 Score instruction 範囲を "
            "overlap、horizontal_source_order、scatter、tile と named 配置領域で一度だけ配置する"
        ),
    )
    repetition_groups: list[RepetitionGroup] = Field(
        default_factory=list,
        exclude_if=lambda value: not value,
        description="Score 0.10 standalone Macro whole-body repetition recipes",
    )
    fill_groups: list[FillGroup] = Field(
        default_factory=list,
        exclude_if=lambda value: not value,
        description="Score 0.10 compact fill recipes; sampled positions are absent",
    )
    mirror_relations: list[MirrorRelationV1] = Field(
        default_factory=list,
        exclude_if=lambda value: not value,
        description="Score 0.15 binary mirror relations between complete existing bodies",
    )
    resource_policy: Optional[ScoreResourcePolicy] = Field(
        default=None,
        # Absent like every later optional field, so a Score without a policy
        # keeps the canonical bytes, digest and rh3 it had before the field.
        exclude_if=lambda value: value is None,
        description="Resource authorities captured for saved-Score replay; demand is recomputed",
    )

    @model_validator(mode="before")
    @classmethod
    def _migrate_legacy_score(cls, value: object) -> object:
        return migrate_score_payload(value)

    @field_validator("canvas", mode="before")
    @classmethod
    def _normalize_canvas(cls, v: object) -> object:
        if isinstance(v, dict):
            return v
        if v is None:
            return "square"
        return str(v)

    def _uses_joint_relations(self) -> bool:
        """A joint relation needs Score 0.20.0.

        A saved Score before 0.20.0 may connect to a closed shape; it stays valid
        and keeps its older performance, where only that relation is omitted.
        """
        return any(
            instruction.relation is not None and instruction.relation.type in JOINT_RELATION_TYPES
            for instruction in self.instructions
        )

    @model_validator(mode="after")
    def _validate_composite_arrangements(self) -> "Score":
        """A composite is one contiguous, non-overlapping instruction span."""
        if self.version == "0.1.0" and any(
            instruction.arc_form is not None for instruction in self.instructions
        ):
            raise ValueError("arc_form requires Score version 0.2.0")
        if self.version in {"0.1.0", "0.2.0"} and any(
            instruction.surface_intensity != "normal" for instruction in self.instructions
        ):
            raise ValueError("surface_intensity requires Score version 0.3.0 or later")
        if self.version not in {"0.16.0", "0.17.0", "0.18.0", "0.19.0", "0.20.0", "0.21.0", "0.22.0"} and any(
            instruction.thinness in ("thick", "extra_thick") for instruction in self.instructions
        ):
            raise ValueError("thick thinness requires Score version 0.16.0")
        if self.version not in {"0.17.0", "0.18.0", "0.19.0", "0.20.0", "0.21.0", "0.22.0"} and any(
            instruction.surface_intensity != "normal" and not closed_solid_fill(instruction)
            for instruction in self.instructions
        ):
            raise ValueError(
                "surface_intensity on a stroke or a textured surface requires Score version 0.17.0"
            )
        if self.version not in {"0.17.0", "0.18.0", "0.19.0", "0.20.0", "0.21.0", "0.22.0"} and any(
            instruction.surface is not None and instruction.surface.texture == "sweep"
            for instruction in self.instructions
        ):
            raise ValueError("surface texture sweep requires Score version 0.17.0")
        if self.version != "0.22.0" and any(
            instruction.surface is not None and instruction.surface.texture == "brushmarks"
            for instruction in self.instructions
        ):
            raise ValueError("surface texture brushmarks requires Score version 0.22.0")
        if self.mirror_relations and self.version not in {"0.15.0", "0.16.0", "0.17.0", "0.18.0", "0.19.0", "0.20.0", "0.21.0", "0.22.0"}:
            raise ValueError("mirror_relations requires Score version 0.15.0")
        if self.version not in {"0.20.0", "0.21.0", "0.22.0"} and self._uses_joint_relations():
            raise ValueError("joint relations require Score version 0.20.0")
        if self.version not in {"0.21.0", "0.22.0"} and any(
            instruction.primitive == "free_line" for instruction in self.instructions
        ):
            raise ValueError("free_line requires Score version 0.21.0")
        if self.version not in {"0.18.0", "0.19.0", "0.20.0", "0.21.0", "0.22.0"} and any(
            isinstance(group.target.owner, NumericRangeTargetOwner) for group in self.fill_groups
        ):
            raise ValueError("fill target numeric_range requires Score version 0.18.0")
        covered_until = 0
        for index, instruction in enumerate(self.instructions):
            arrangement = instruction.arrangement
            if arrangement is None or arrangement.group_size == 1:
                continue
            if index < covered_until:
                raise ValueError("nested arrangement inside a composite group")
            if instruction.relation is not None:
                raise ValueError("composite group head cannot relate outside the group")
            stop = index + arrangement.group_size
            if stop > len(self.instructions):
                raise ValueError("arrangement group_size exceeds the instruction list")
            members = self.instructions[index + 1 : stop]
            if any(member.arrangement is not None for member in members):
                raise ValueError("nested arrangement inside a composite group")
            if any(member.mode != instruction.mode for member in members):
                raise ValueError(
                    "all instructions in a composite group must share one mode"
                )
            for offset, member in enumerate(members, start=1):
                if (
                    member.relation is not None
                    and member.relation.type == "between"
                    and offset < 2
                ):
                    raise ValueError(
                        "between needs two prior instructions inside its composite group"
                    )
            covered_until = stop
        if self.anchors and self.version not in {"0.6.0", "0.7.0", "0.8.0", "0.9.0", "0.10.0", "0.11.0", "0.12.0", "0.13.0", "0.14.0", "0.15.0", "0.16.0", "0.17.0", "0.18.0", "0.19.0", "0.20.0", "0.21.0", "0.22.0"}:
            raise ValueError("anchors requires Score version 0.6.0")
        if self.transform_groups and self.version not in {"0.4.0", "0.5.0", "0.6.0", "0.7.0", "0.8.0", "0.9.0", "0.10.0", "0.11.0", "0.12.0", "0.13.0", "0.14.0", "0.15.0", "0.16.0", "0.17.0", "0.18.0", "0.19.0", "0.20.0", "0.21.0", "0.22.0"}:
            raise ValueError("transform_groups requires Score version 0.4.0")
        for group_index, group in enumerate(self.transform_groups):
            if group.start > group.end or (
                group.start == group.end and not group.anchor_indices
            ):
                raise ValueError("transform group range must be nonempty unless it owns anchors")
            if group.end > len(self.instructions):
                raise ValueError("transform group range exceeds the instruction list")
            if self.version not in {"0.5.0", "0.6.0", "0.7.0", "0.8.0", "0.9.0", "0.10.0", "0.11.0", "0.12.0", "0.13.0", "0.14.0", "0.15.0", "0.16.0", "0.17.0", "0.18.0", "0.19.0", "0.20.0", "0.21.0", "0.22.0"} and (
                group.scale_x != 1.0
                or group.scale_y != 1.0
                or group.translate_x != 0.0
                or group.translate_y != 0.0
            ):
                raise ValueError("scale or translation requires Score version 0.5.0")
            if any(instruction.arrangement is not None and instruction.arrangement.resolved is None for instruction in self.instructions[group.start:group.end]):
                raise ValueError("transform group members cannot carry arrangements")
            fixed_indices = set(group.fixed_position_indices)
            if len(fixed_indices) != len(group.fixed_position_indices):
                raise ValueError("transform group fixed_position_indices must be unique")
            if any(index < group.start or index >= group.end for index in fixed_indices):
                raise ValueError("transform group fixed_position_indices must be within its range")
            anchor_indices = set(group.anchor_indices)
            if len(anchor_indices) != len(group.anchor_indices):
                raise ValueError("transform group anchor_indices must be unique")
            if any(index >= len(self.anchors) for index in anchor_indices):
                raise ValueError("transform group anchor_indices exceeds anchors")
            if group.anchor_indices and self.version not in {"0.6.0", "0.7.0", "0.8.0", "0.9.0", "0.10.0", "0.11.0", "0.12.0", "0.13.0", "0.14.0", "0.15.0", "0.16.0", "0.17.0", "0.18.0", "0.19.0", "0.20.0", "0.21.0", "0.22.0"}:
                raise ValueError("transform group anchor_indices requires Score version 0.6.0")
            for prior in self.transform_groups[:group_index]:
                current_contains_prior = (
                    (prior.start == prior.end or (group.start <= prior.start and prior.end <= group.end))
                    and set(prior.anchor_indices) <= anchor_indices
                )
                prior_contains_current = (
                    (group.start == group.end or (prior.start <= group.start and group.end <= prior.end))
                    and anchor_indices <= set(prior.anchor_indices)
                )
                drawable_overlap = (
                    group.start < group.end and prior.start < prior.end
                    and group.start < prior.end and prior.start < group.end
                )
                anchor_overlap = bool(anchor_indices.intersection(prior.anchor_indices))
                if not drawable_overlap and not anchor_overlap:
                    continue
                if not current_contains_prior:
                    if prior_contains_current:
                        raise ValueError("transform groups must be stored inner-before-outer")
                    raise ValueError("transform group ranges cannot cross")
                if not set(prior.fixed_position_indices) <= fixed_indices:
                    raise ValueError("outer transform groups must include descendant fixed_position_indices")
                if not set(prior.anchor_indices) <= anchor_indices:
                    raise ValueError("outer transform groups must include descendant anchor_indices")
        if self.placement_groups and self.version not in {"0.7.0", "0.8.0", "0.9.0", "0.10.0", "0.11.0", "0.12.0", "0.13.0", "0.14.0", "0.15.0", "0.16.0", "0.17.0", "0.18.0", "0.19.0", "0.20.0", "0.21.0", "0.22.0"}:
            raise ValueError("placement_groups requires Score version 0.7.0")
        for group in [*self.placement_groups, *self.fill_groups]:
            if group.cycle_members is not None and self.version not in {"0.14.0", "0.15.0", "0.16.0", "0.17.0", "0.18.0", "0.19.0", "0.20.0", "0.21.0", "0.22.0"}:
                raise ValueError("cycle_members requires Score version 0.14.0")
            for member in group.members:
                symbolic = member.symbolic
                if symbolic is not None and (
                    symbolic.kind == "ordinary_group" or isinstance(symbolic.owner, OrdinaryGroupOwner)
                ) and self.version not in {"0.14.0", "0.15.0", "0.16.0", "0.17.0", "0.18.0", "0.19.0", "0.20.0", "0.21.0", "0.22.0"}:
                    raise ValueError("ordinary group members require Score version 0.14.0")
                if symbolic is not None and (
                    symbolic.kind == "ordinary_group" or isinstance(symbolic.owner, OrdinaryGroupOwner)
                ) and group.cycle_members is None:
                    raise ValueError("ordinary group members require cycle_members")
                if group.cycle_members is not None and symbolic is not None:
                    owner_kind = {
                        "primitive": SourceInstructionOwner,
                        "macro": SourceInstructionOwner,
                        "ordinary_group": OrdinaryGroupOwner,
                    }[symbolic.kind]
                    if not isinstance(symbolic.owner, owner_kind):
                        raise ValueError("cycle member kind and owner are inconsistent")
        placement_end = 0
        placement_anchor_indices: set[int] = set()
        placement_transform_indices: set[int] = set()
        for group in self.placement_groups:
            if group.layout in {"scatter", "tile"} and self.version not in {"0.8.0", "0.9.0", "0.10.0", "0.11.0", "0.12.0", "0.13.0", "0.14.0", "0.15.0", "0.16.0", "0.17.0", "0.18.0", "0.19.0", "0.20.0", "0.21.0", "0.22.0"}:
                raise ValueError("scatter and tile placement_groups require Score version 0.8.0")
            if group.layout == "cells" and self.version not in {"0.19.0", "0.20.0", "0.21.0", "0.22.0"}:
                raise ValueError("cells placement_groups require Score version 0.19.0")
            recipe = group.resolved.recipe if group.resolved is not None else None
            if (group.layout == "cells") != isinstance(recipe, CellsRecipe):
                raise ValueError("cells placement_groups require the resolved cells recipe")
            if group.members and self.version not in {"0.9.0", "0.10.0", "0.11.0", "0.12.0", "0.13.0", "0.14.0", "0.15.0", "0.16.0", "0.17.0", "0.18.0", "0.19.0", "0.20.0", "0.21.0", "0.22.0"}:
                raise ValueError("placement group members require Score version 0.9.0")
            if not group.members and group.start >= group.end:
                raise ValueError("placement group range must be nonempty")
            if group.end > len(self.instructions):
                raise ValueError("placement group range exceeds the instruction list")
            if group.start < placement_end:
                raise ValueError("placement groups must be disjoint and source ordered")
            if any(instruction.arrangement is not None and instruction.arrangement.resolved is None for instruction in self.instructions[group.start:group.end]):
                raise ValueError("placement group members cannot carry arrangements")
            if group.members:
                member_end = group.start
                member_anchors: set[int] = set()
                member_transforms: set[int] = set()
                for member in group.members:
                    if member.start != member_end or member.start > member.end:
                        raise ValueError("placement members must partition the group in source order")
                    if member.end > group.end:
                        raise ValueError("placement member range exceeds its group")
                    if member.start == member.end and not member.anchor_indices:
                        raise ValueError("empty placement member requires anchors")
                    for anchor_index in member.anchor_indices:
                        if anchor_index >= len(self.anchors):
                            raise ValueError("placement member anchor_indices exceeds anchors")
                        if anchor_index in member_anchors or anchor_index in placement_anchor_indices:
                            raise ValueError("placement member anchors must be unique")
                        member_anchors.add(anchor_index)
                    for transform_index in member.transform_group_indices:
                        if transform_index >= len(self.transform_groups):
                            raise ValueError("placement member transform_group_indices exceeds transform groups")
                        if transform_index in member_transforms or transform_index in placement_transform_indices:
                            raise ValueError("placement member transform_group_indices must be unique")
                        transform = self.transform_groups[transform_index]
                        if not (
                            member.start <= transform.start
                            and transform.end <= member.end
                            and set(transform.anchor_indices) <= set(member.anchor_indices)
                        ):
                            raise ValueError("placement member transform must be wholly within its member")
                        member_transforms.add(transform_index)
                    member_end = member.end
                if member_end != group.end:
                    raise ValueError("placement members must end at the group end")
                placement_anchor_indices.update(member_anchors)
                placement_transform_indices.update(member_transforms)
            for affine_index, affine in enumerate(self.transform_groups):
                overlaps = group.start < affine.end and affine.start < group.end
                outer = affine.start <= group.start and group.end <= affine.end
                owned_member = any(
                    affine_index in member.transform_group_indices
                    and member.start <= affine.start
                    and affine.end <= member.end
                    and set(affine.anchor_indices) <= set(member.anchor_indices)
                    for member in group.members
                )
                if overlaps and not (outer or owned_member):
                    raise ValueError("transform group must contain an overlapping placement group")
            placement_end = group.end
        for instruction in self.instructions:
            relation = instruction.relation
            if instruction.arrangement is not None and instruction.arrangement.resolved is not None and isinstance(
                instruction.arrangement.resolved.owner, OrdinaryGroupOwner
            ):
                raise ValueError("instruction templates cannot use an ordinary group owner")
            if instruction.arrangement is not None and instruction.arrangement.resolved is not None and isinstance(
                instruction.arrangement.resolved.recipe, CellsRecipe
            ):
                raise ValueError("cells recipes belong to cells placement_groups")
            if self.version not in {"0.12.0", "0.13.0", "0.14.0", "0.15.0", "0.16.0", "0.17.0", "0.18.0", "0.19.0", "0.20.0", "0.21.0", "0.22.0"} and (
                instruction.ink_spread is not None
                or (relation is not None and relation.target_endpoint is not None)
            ):
                raise ValueError("ink_spread and target_endpoint require Score version 0.12.0")
            if relation is not None and relation.target_path_position == "interior" and self.version not in {"0.13.0", "0.14.0", "0.15.0", "0.16.0", "0.17.0", "0.18.0", "0.19.0", "0.20.0", "0.21.0", "0.22.0"}:
                raise ValueError("interior target_path_position requires Score version 0.13.0")
            if relation is not None and relation.target_path_position is not None and self.version not in {"0.11.0", "0.12.0", "0.13.0", "0.14.0", "0.15.0", "0.16.0", "0.17.0", "0.18.0", "0.19.0", "0.20.0", "0.21.0", "0.22.0"}:
                raise ValueError("target_path_position requires Score version 0.11.0")
            if relation is not None and relation.target_anchor_index is not None:
                if self.version not in {"0.6.0", "0.7.0", "0.8.0", "0.9.0", "0.10.0", "0.11.0", "0.12.0", "0.13.0", "0.14.0", "0.15.0", "0.16.0", "0.17.0", "0.18.0", "0.19.0", "0.20.0", "0.21.0", "0.22.0"}:
                    raise ValueError("relation target_anchor_index requires Score version 0.6.0")
                if relation.target_anchor_index >= len(self.anchors):
                    raise ValueError("relation target_anchor_index exceeds anchors")
        has_compact_fields = bool(
            self.repetition_groups
            or self.fill_groups
            or self.resource_policy is not None
            or any(group.resolved is not None or group.cycle_members is not None for group in self.placement_groups)
            or any(member.symbolic is not None for group in self.placement_groups for member in group.members)
            or any(
                instruction.arrangement is not None
                and instruction.arrangement.resolved is not None
                for instruction in self.instructions
            )
        )
        if has_compact_fields and self.version not in {"0.10.0", "0.11.0", "0.12.0", "0.13.0", "0.14.0", "0.15.0", "0.16.0", "0.17.0", "0.18.0", "0.19.0", "0.20.0", "0.21.0", "0.22.0"}:
            raise ValueError("compact symbolic fields require Score version 0.10.0 or newer")
        if self.version == "0.10.0" or (self.version in {"0.11.0", "0.12.0", "0.13.0", "0.14.0", "0.15.0", "0.16.0", "0.17.0", "0.18.0", "0.19.0", "0.20.0", "0.21.0", "0.22.0"} and has_compact_fields):
            if self.resource_policy is None:
                raise ValueError("Score 0.10 requires a resource_policy snapshot")
            if not self.resource_policy.hard_policy.identity:
                raise ValueError("Score 0.10 resource policy identity is invalid")
            if any(
                instruction.arrangement is None
                or instruction.arrangement.resolved is None
                for instruction in self.instructions
            ):
                raise ValueError("Score 0.10 instruction templates require resolved arrangements")
            for group in self.placement_groups:
                if group.resolved is None or not group.members:
                    raise ValueError("Score 0.10 placement groups require resolved members")
                expected = 0
                for ordinal, member in enumerate(group.members):
                    symbolic = member.symbolic
                    if symbolic is None or symbolic.member_ordinal != ordinal or symbolic.first_instance_ordinal != expected:
                        raise ValueError("placement symbolic member ordinals must form a source-order prefix")
                    if group.cycle_members is not None and symbolic.instance_count != 1:
                        raise ValueError("cycle members must each store one template instance")
                    expected += symbolic.instance_count
                if group.cycle_members is not None:
                    if group.cycle_members.occurrence_count != group.resolved.logical_count:
                        raise ValueError("cycle occurrence_count must equal the resolved logical count")
                elif expected != group.resolved.logical_count:
                    raise ValueError("placement member counts must equal the resolved logical count")
            for group in self.repetition_groups:
                symbolic = group.member.symbolic
                if symbolic is None or symbolic.kind != "macro" or isinstance(symbolic.owner, OrdinaryGroupOwner) or symbolic.member_ordinal != 0 or symbolic.first_instance_ordinal != 0:
                    raise ValueError("repetition group requires one whole Macro symbolic member")
            for group in self.fill_groups:
                expected = 0
                for ordinal, member in enumerate(group.members):
                    symbolic = member.symbolic
                    if symbolic is None or symbolic.member_ordinal != ordinal or symbolic.first_instance_ordinal != expected:
                        raise ValueError("fill symbolic member ordinals must form a source-order prefix")
                    if group.cycle_members is not None and symbolic.instance_count != 1:
                        raise ValueError("cycle members must each store one template instance")
                    expected += symbolic.instance_count
                if group.cycle_members is not None:
                    if group.cycle_members.occurrence_count != group.logical_count:
                        raise ValueError("cycle occurrence_count must equal the logical count")
                elif expected != group.logical_count:
                    raise ValueError("fill member counts must equal the logical count")
        return self
