"""JSON Score schema for inku DDL.

座標系は 0.0-1.0 の比率 (SPEC §2 原則4)。
各フィールドの description がスペックの正典 (Source of Truth)。
システムプロンプトにフィールド仕様を書かないこと — ここに書く。
"""

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .limits import DEFAULT_LIMITS, Limits, current_limits


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
ScoreVersion = Literal["0.1.0"]

Primitive = Literal[
    "line", "circle", "ellipse", "triangle", "square", "polygon", "arc", "cloudform"
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
LineStyle = Literal["solid", "dashed", "dotted", "dash_dot"]
Weight = Literal[
    "silverpoint",
    "pencil",
    "pen",
    "rotring",
    "crayon",
    "chalk",
    "brush_thin",
    "brush_thick",
    "burin",
    "drypoint",
    "computer",
]
Thinness = Literal["fine", "extra_fine"]
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
    "stipple",
    "hatch",
    "crosshatch",
    "aquatint",
    "grain",
    "wash",
    "bleed",
    "paper_grain",
]
SurfaceDirection = Literal[
    "none", "horizontal", "vertical", "diagonal_rising", "diagonal_falling"
]
GroundMaterial = Literal[
    "plain", "paper", "washi", "ink_wash", "charcoal_ground", "mezzotint"
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
RelationType = Literal["along", "not_touching", "cutting", "between", "touching"]
RelationGap = Literal["narrow", "medium", "wide"]
InstructionMode = Literal["additive", "carve"]
CarveDepth = Literal["light", "half", "bright"]
SurfaceSpacingGradient = Literal["none", "coarse_to_dense", "dense_to_coarse"]


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
            "面の質感: none=なし / stipple=点 / hatch=平行線 / crosshatch=交差線"
            " / aquatint=段階的な粒 / grain=粒立つ / wash=薄墨・水彩 / bleed=端が滲む / paper_grain=紙目"
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
        description="地の素材: plain=無地 / paper=紙 / washi=和紙 / ink_wash=薄墨地 / charcoal_ground=木炭地 / mezzotint=目立てした黒地",
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


class CanvasSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    """キャンバス比率と地の指定。旧形式の文字列 canvas も互換で受ける。"""

    aspect: str = Field(default="square", description="キャンバス比率ID")
    ground: Optional[CanvasGroundSpec] = Field(
        default=None, description="キャンバス地の質感"
    )


Canvas = str | CanvasSpec


class AtRegion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    """演奏時に Renderer が解決する配置領域。"""

    region: tuple[float, float, float, float] = Field(
        description="[x0,y0,x1,y1] の正規化領域。Renderer が render_seed で実座標へ解決する",
    )

    @field_validator("region", mode="before")
    @classmethod
    def _normalize_region(cls, v: object) -> object:
        if not isinstance(v, (list, tuple)) or len(v) != 4:
            return v
        vals = [float(item) for item in v]
        x0, y0, x1, y1 = vals
        return (
            max(0.0, min(1.0, min(x0, x1))),
            max(0.0, min(1.0, min(y0, y1))),
            max(0.0, min(1.0, max(x0, x1))),
            max(0.0, min(1.0, max(y0, y1))),
        )


class Relation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    """直前 instruction との観察可能な関係。参照先は暗黙 prev のみ。"""

    type: RelationType = Field(
        description="along=沿う / not_touching=触れない / cutting=切る / between=直前2要素の間に / touching=触れる",
    )
    gap: RelationGap = Field(
        default="medium",
        description="関係解決時の距離目安: narrow / medium / wide。具体距離は Renderer が解決する",
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

    @field_validator("count", mode="before")
    @classmethod
    def _clamp_count(cls, v: object) -> object:
        # Still layout-blind, deliberately: "1-1000 for ordinary arrangements"
        # is guidance in the prompt, not a checked bound, and making it one is a
        # separate design decision.
        if isinstance(v, (int, float)):
            return min(max(int(v), 1), current_limits().schema_count_max)
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
    cluster_count: Optional[int] = Field(
        default=None,
        ge=1,
        le=12,
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


class Instruction(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    primitive: Primitive = Field(
        description=(
            "line=線 / circle=円 / ellipse=楕円 / triangle=三角 / square=四角"
            " / polygon=多角形 / arc=弧 / cloudform=雲形"
        ),
    )
    note: Optional[str] = Field(
        default=None,
        description="機械が付ける処理注記。描画に影響しない。出力しないこと",
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
        description="circle/ellipse/arc/polygon/cloudform の中心 [x,y]。square/triangle には使わない (→position)",
    )
    radius: Optional[float] = Field(
        default=None,
        description="circle/arc/polygon の半径 (省略=0.1)",
    )
    sides: Optional[int] = Field(
        default=None,
        ge=5,
        le=8,
        description="polygon の頂点数。5-8 の正多角形のみ。個別 primitive は増やさず、多角形語彙はここに集約する",
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
    rotation: Optional[float] = Field(
        default=None,
        description=(
            "図形全体の回転角(度)。0=水平、正=時計回り、負=反時計回り。"
            "線・楕円・四角・三角・弧を中心まわりに回転する。"
        ),
    )

    filled: bool = Field(
        default=False,
        description="塗りつぶし: True=color で塗りつぶす / False=輪郭のみ。line には無効",
    )
    style: LineStyle = Field(
        default="solid",
        description="solid=実線 / dashed=破線 / dotted=点線 / dash_dot=一点鎖線",
    )
    weight: Weight = Field(
        default="pen",
        description=(
            "silverpoint=銀筆 / pencil=鉛筆 / pen=ペン / rotring=ロットリング"
            " / crayon=クレヨン / chalk=チョーク / brush_thin=細筆 / brush_thick=太筆"
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
    thinness: Optional[Thinness] = Field(
        default=None,
        description=(
            "線の細さ。道具の既定より細く引く指定。fine=細い / extra_fine=極細。"
            "省略時は道具の既定。太くする指定は無い"
        ),
    )
    surface: Optional[SurfaceSpec] = Field(
        default=None,
        description="閉じた図形の面の質感。line/arc では安全に無視または近似される。SVG固有の pattern/filter は入れない",
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


class Score(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: ScoreVersion = "0.1.0"
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
    instructions: list[Instruction]

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
