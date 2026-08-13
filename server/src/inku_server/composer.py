"""Stage 2: Normalized DDL → JSON Score.

設計原則:
  SYSTEM_PROMPT は「手順」のみ。フィールド仕様は schema.py の description が正典。
  新しい primitive や属性を追加する場合は schema.py を更新する。ここは変えない。

Which backend a model id reaches is decided by model_settings.provider_for_model
and its three rules (explicit qualification, sole ownership, the stage default).
Nothing here guesses it from the shape of the string.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import unicodedata
import urllib.request
from copy import deepcopy
from typing import Any, get_args

from .limits import DEFAULT_LIMITS, Limits, current_limits
from .llm_retry import call_with_llm_retry
from .model_settings import connection_for, provider_for_model
from .plugins import CANVAS_ASPECTS, CanvasAspect
from .provider_limits import provider_slot
from .saijiki import relation_literal_markers
from .schema import Score, ScoreVersion, Variation, count_field_description

DEFAULT_ANTHROPIC_MODEL = "claude-haiku-4-5-20251001"
MAX_TOKENS = 2048
# Read off the Literal rather than written again, so the two cannot drift apart.
SCORE_VERSION = get_args(ScoreVersion)[0]
_logger = logging.getLogger(__name__)

# The prompt states the limits as literal numbers, so it has to be built from the
# effective ones. A prompt that says "below 240 is literal" while coerce honours
# 480 teaches the model a rule the system does not follow.
#
# Only the numbers move. The prompt is a template with two substitution points,
# not a dynamically generated document, and `.replace` is used rather than
# `.format` because the body is full of literal braces (at={"region":[...]}).
_COUNT_DENSITY_SLOT = "%%COUNT_DENSITY%%"
_GRID_COUNT_SLOT = "%%GRID_COUNT%%"
# The support slot. Unlike the two above it can resolve to nothing: a call that
# names no paper leaves the prompt byte-identical to the paperless body, which
# is what keeps the module-level constants free of a paper they cannot know.
_CANVAS_SLOT = "%%CANVAS%%"
# The slot swallows its own trailing blank line, so the paperless body has no
# gap where the block would have been.
_CANVAS_SLOT_LINE = _CANVAS_SLOT + "\n\n"
# The heading the support block opens with, in both languages. A gate on the
# block has to cut this region out of the prompt: the same words appear in the
# conversion rules, so a search over the whole body is satisfied by the wrong
# occurrence.
_CANVAS_BLOCK_HEADING_JA = "## 支持体（この作品を描く紙）"
_CANVAS_BLOCK_HEADING_EN = "## Support (the paper this work is drawn on)"
_CANVAS_ASPECT_BY_ID: dict[str, CanvasAspect] = {item.id: item for item in CANVAS_ASPECTS}

# The density bands under the count ceiling. The final upper edge IS the ceiling;
# the interior edges are prose about density, so they are kept as written and
# only clamped, never rescaled -- rescaling them would invent numbers nobody
# chose. Written once and rendered in both languages so the two cannot drift.
_VAGUE_QUANTITY_BANDS: tuple[tuple[int, int | None], ...] = (
    (3, 8),
    (8, 20),
    (40, 120),
    (120, 350),
    (300, 800),
    (700, None),
)
_VAGUE_QUANTITY_LABELS_JA = ("少し", "点々", "たくさん", "密集/埋める", "無数/満天/砂/雨/雪", "全面/埋め尽くす")
_VAGUE_QUANTITY_LABELS_EN = (
    "a few",
    "several/dotted",
    "many",
    "dense/fill",
    "countless/starry/sand/rain/snow",
    "all-over/fill whole canvas",
)


def _vague_quantity_bands(labels: tuple[str, ...], *, cap: int, dash: str, sep: str) -> str:
    parts = []
    for label, (low, high) in zip(labels, _VAGUE_QUANTITY_BANDS):
        top = cap if high is None else min(high, cap)
        parts.append(f"{label}={min(low, top)}{dash}{top}")
    return sep.join(parts)


def _count_density_block_ja(limits: Limits) -> str:
    bands = _vague_quantity_bands(_VAGUE_QUANTITY_LABELS_JA, cap=limits.ddl_count_max, dash="〜", sep="、")
    return "\n".join(
        (
            f"- **count は 1〜{limits.ddl_count_max} の整数**",
            f"- **曖昧数量が残っている場合は固定値に丸めず、密度語と対象語から具体数を選ぶ: {bands}**",
            f"- **明示数量は、後述する grid を除き、{limits.literal_count_threshold} 未満なら literal。要求値をそのまま arrangement.count に使う。110 / 64 / 48 などの代表値へ置換せず、密度や余白を理由に縮小しない**",
            f"- **明示数量が {limits.literal_count_threshold} 以上なら代表化する。count を {limits.represented_count_min}〜{limits.represented_count_max} とし、density=\"high\", cluster_count=5〜9, fade=\"outward\" または \"directional\", preserve_space=true で群の見え方と配置語を保持する**",
            f"- **複数群の literal 対象の合計が {limits.max_expanded_primitives} を超える場合は、要求値の大きい群から順に代表化し、literal 合計が {limits.max_expanded_primitives} 以下になった時点で止める。小さい群を先に削らず、比例縮小や群の統合をしない**",
        )
    )


def _grid_count_line_ja(limits: Limits) -> str:
    return (
        f"- **grid の count だけは1〜{limits.ddl_count_max_grid}を許可し、代表数への縮小、cluster_count、fade、preserve_space を適用しない。"
        f"通常配置の count は従来どおり1〜{limits.ddl_count_max}**"
    )


def _count_density_block_en(limits: Limits) -> str:
    bands = _vague_quantity_bands(_VAGUE_QUANTITY_LABELS_EN, cap=limits.ddl_count_max, dash="–", sep=", ")
    return "\n".join(
        (
            f"- **count is an integer from 1–{limits.ddl_count_max}**",
            f"- **If vague quantity words remain, do not collapse them to a fixed number. Choose a concrete count from density and object type: {bands}**",
            f"- **Except for grid described below, an explicit quantity below {limits.literal_count_threshold} is literal. Use the requested value unchanged as arrangement.count. Do not replace it with a representative value such as 110, 64, or 48, and do not reduce it for density or negative space**",
            f"- **Represent an explicit quantity of {limits.literal_count_threshold} or more with count {limits.represented_count_min}–{limits.represented_count_max} plus density=\"high\", cluster_count=5–9, fade=\"outward\" or \"directional\", and preserve_space=true. Preserve the visible group behavior and placement phrase**",
            f"- **When the sum of literal groups exceeds {limits.max_expanded_primitives}, convert the largest requested groups to representation one by one and stop as soon as the remaining literal sum is {limits.max_expanded_primitives} or less. Do not reduce smaller groups first, scale groups proportionally, or merge groups**",
        )
    )


def _grid_count_line_en(limits: Limits) -> str:
    return (
        f"- **Only grid may use count 1–{limits.ddl_count_max_grid}. Do not reduce it to a representative count and do not add cluster_count, fade, or preserve_space. "
        f"Ordinary arrangements remain limited to 1–{limits.ddl_count_max}**"
    )


def _ratio_text(value: float) -> str:
    """`1.0` as "1", `2.35` as "2.35" -- the ratio as a reader would write it."""
    return f"{value:g}"


def _canvas_orientation(aspect: CanvasAspect, lang: str) -> str:
    # Not the word "横長": the conversion rules already teach it as the
    # proportion of a SHAPE ("横長の四角" is an ellipse twice as wide as tall).
    # The support is described with words that cannot be read as an adjective
    # of a mark.
    if aspect.ratio_w > aspect.ratio_h:
        return "a support wider than it is tall" if lang == "en" else "横に広い支持体"
    if aspect.ratio_w < aspect.ratio_h:
        return "a support taller than it is wide" if lang == "en" else "縦に長い支持体"
    return "a square support" if lang == "en" else "正方形の支持体"


def _canvas_block(canvas_aspect: str, lang: str) -> str:
    """What the composition is told about the paper it is composing for.

    Three statements, in the order they bind: which paper this is, that the
    paper may move size and placement, and that it may not overrule a size the
    description itself stated.
    """
    aspect = _CANVAS_ASPECT_BY_ID.get(canvas_aspect)
    if aspect is None:
        return ""
    ratio = f"{_ratio_text(aspect.ratio_w)}:{_ratio_text(aspect.ratio_h)}"
    if lang == "en":
        return "\n".join(
            (
                _CANVAS_BLOCK_HEADING_EN,
                "",
                f'- **This work is drawn on the support `{canvas_aspect}` -- {_canvas_orientation(aspect, "en")}, ratio {ratio}. Compose for this support, not for a square**',
                f'- **Write this support into canvas.aspect: {{"canvas":{{"aspect":"{canvas_aspect}"}}}}. Keep canvas.ground when the normalized DDL asks for one: {{"canvas":{{"aspect":"{canvas_aspect}","ground":{{...}}}}}}**',
                "- **What the support may move is the SIZE and the PLACEMENT of the marks. A mark that would be a speck on this support is drawn at the size this support asks for, and the placement follows the long side**",
                "- **The support may not move the COUNT. The count comes from the normalized DDL. Do not add or remove marks because the support is narrow or wide**",
                "- **The support may not overrule a size the description stated. When the normalized DDL says small, thin, or faint, the mark stays small, thin, or faint on every support**",
            )
        )
    return "\n".join(
        (
            _CANVAS_BLOCK_HEADING_JA,
            "",
            f"- **この作品を描く支持体は `{canvas_aspect}`（{_canvas_orientation(aspect, 'ja')}・比 {ratio}）。正方形ではなくこの支持体のために構図を組む**",
            f'- **この支持体を canvas.aspect へ書く: {{"canvas":{{"aspect":"{canvas_aspect}"}}}}。正規化DDL が地を求めている場合は ground を併記する: {{"canvas":{{"aspect":"{canvas_aspect}","ground":{{...}}}}}}**',
            "- **支持体に合わせてよいのは痕の大きさと配置である。この支持体の上で塵のようになる大きさは、この支持体が求める大きさで描き、配置は長辺に沿わせる**",
            "- **支持体で個数を変えない。個数は正規化DDL が決める。支持体が細いから、広いからという理由で痕を増減しない**",
            "- **記述が述べた大きさを支持体の都合で覆さない。正規化DDL が「小さい」「細い」「かすか」と述べている痕は、どの支持体でも小さいまま・細いまま・かすかなままにする**",
        )
    )


def canvas_retry_line(canvas_aspect: str | None, lang: str) -> str:
    """The support, for the compact retry prompt.

    The retry replaces the whole system prompt, so a retry that does not state
    the support composes on a paper it was never told about -- the same defect
    the main prompt just fixed, showing up only on the runs that happened to
    retry. Empty when no support was requested, which keeps the retry body of
    such a run byte-identical to what it was before.
    """
    aspect = _CANVAS_ASPECT_BY_ID.get(canvas_aspect or "")
    if aspect is None:
        return ""
    ratio = f"{_ratio_text(aspect.ratio_w)}:{_ratio_text(aspect.ratio_h)}"
    if lang == "en":
        return (
            f'The support is `{aspect.id}` -- {_canvas_orientation(aspect, "en")}, ratio {ratio}. '
            f'Compose for it and write it into canvas.aspect: {{"canvas":{{"aspect":"{aspect.id}"}}}}. '
            "The support may move the size and placement of the marks, never their count, "
            "and never a size the description itself stated.\n"
        )
    return (
        f"支持体は `{aspect.id}`（{_canvas_orientation(aspect, 'ja')}・比 {ratio}）。"
        f'この支持体のために構図を組み、canvas.aspect へ書く: {{"canvas":{{"aspect":"{aspect.id}"}}}}。'
        "支持体に合わせてよいのは痕の大きさと配置だけで、個数は変えず、記述が述べた大きさも覆さない。\n"
    )


def build_system_prompt(
    lang: str,
    limits: Limits = DEFAULT_LIMITS,
    canvas_aspect: str | None = None,
) -> str:
    """The Stage 2 prompt with the effective limits and the support written into it.

    `canvas_aspect=None` states no support at all -- the body is then the
    paperless one, byte for byte. The module-level constants are built that way
    because they are read at import time, before any request exists.
    """
    if lang == "en":
        template, block, grid = (
            _SYSTEM_PROMPT_EN_TEMPLATE,
            _count_density_block_en(limits),
            _grid_count_line_en(limits),
        )
    else:
        template, block, grid = (
            _SYSTEM_PROMPT_TEMPLATE,
            _count_density_block_ja(limits),
            _grid_count_line_ja(limits),
        )
    prompt = template.replace(_COUNT_DENSITY_SLOT, block).replace(_GRID_COUNT_SLOT, grid)
    canvas_block = _canvas_block(canvas_aspect, lang) if canvas_aspect is not None else ""
    if not canvas_block:
        return prompt.replace(_CANVAS_SLOT_LINE, "")
    return prompt.replace(_CANVAS_SLOT_LINE, canvas_block + "\n\n")


# 手順のみ。フィールド仕様は submit_score スキーマの description を参照。
# 例は「最も非自明なパターン」に絞る — 追加は EXAMPLE_POOL (interpreter.py) と同じ方針で。
_SYSTEM_PROMPT_TEMPLATE = """あなたは inku DDL の第二段階コンパイラ。
正規化DDL を解析し submit_score を呼び出せ。
フィールド仕様は submit_score スキーマの description フィールドが正典。
「原文」が付いている場合は正規化DDL を主とし、原文は省略された属性（色・素材・数量など）の補完に使え。

%%CANVAS%%

# 変換ルール (厳守)

## 図形と圧縮

- **note は機械専用の処理注記。Stage 2 からは絶対に出力しない**
- 座標: 0.0-1.0 比率 (左上=(0,0) 右下=(1,1))
- circle/ellipse/arc/polygon/cloudform → center フィールド。square/triangle → position フィールド (bbox 左上)
- **正規化DDLの「雲形」だけを primitive="cloudform", center+size へ転記する。輪郭座標・制御点は生成しない。雲形を補完・推測で追加しない**
- **正規化DDLに雲形が1句以上ある場合、出力にも同じ雲形 instruction を必ず残す。横長、arrangement、surface、carve と合成されても ellipse/line へ置換・省略しない。複数同一雲形は1 instruction + arrangementにする**
- 中央配置の square/triangle: position = [0.5-w/2, 0.5-h/2]
- **同一図形の同一配置の反復 → 1 instruction + arrangement.count。反復を N 件の instruction へ展開しない。個数・配置・位置が異なる群は別 instruction にする**
- **正規化DDL に図形・線・弧の指示がある場合、instructions を空配列にしてはいけない。変換不能なら最も近い線・楕円・四角へ落とし込む**
- **疎で最小限の作品も有効。単一の方向線・地平線・端寄りの焦点だけの DDL も、少なくとも1つの描画可能な instruction にする**
- **出力は 1〜5 instructions に圧縮する。DDL 全文を説明し直さず、主題を成立させる主要な視覚関係だけを JSON 化する**
- **作品ごとに主技法は一つだけ。DDL に複数の技法語があっても、最も主題に合うものを一つ選び、残りは必要な場合だけ小さな補助層にする**
- **圧縮しすぎない。光・香り・温度・音・待つ時間・五感などの感覚語が DDL にある場合、主題を壊さない範囲で 1〜2 個の薄い補助層として残す。削りすぎて作品の情報量や楽しさを失わせない**

## 余白・揺らぎ・質感

- **余白は構図要素。小さな焦点、端寄りの線、反復の欠落、画面外へ続く方向で余白に圧力を作る。余白を全面散布で埋めない**
- variation は明示された揺らぎがある場合のみ付ける
- **形容語・動作語・質感語は、DDL で指定された主図形へ適用する。震える・揺れる・滲む・太い・細い等を理由に、DDL にない補助線・補助図形・別色の instruction を追加してはいけない**
- **面の質感は instruction.surface へ入れる。点=texture="stipple"、平行線=texture="hatch"、交差線=texture="crosshatch"、アクアチント=texture="aquatint"、粒/粒立つ/かすれ=texture="grain"、薄墨/水彩=texture="wash"、にじみ/端が滲む=texture="bleed"。質感を理由に独立 instruction を追加しない**
- **「面: 塗り」は texture="solid"。面の語はすべて surface.texture へ入る。「面: 空」は既定なので surface を出さない**
- **「面: 濃い」は surface.density=0.60, surface.opacity=0.50。「面: 薄い」は surface.density=0.20, surface.opacity=0.15 (既定は density=0.35, opacity=0.28)。濃い・薄いは相対の語で、質感の語に添えられたときはその質感の濃さを動かす。「面: 薄墨（濃い）」は texture="wash" のまま density と opacity を上げる**
- **紙目・生成りの紙・和紙・薄墨の地は canvas.ground へ入れる。canvas は {"aspect":"square","ground":{...}} 形式にしてよい。地は background ではなく支持体の質感であり、座標系を変えない**
- **「地: ...」の文は canvas.ground へだけ変換し、その文から instruction を追加しない。「面: ...」の文は直前に指定された主図形の surface に入れる。一つの質感要求を複数の質感付き instruction に複製しない**
- **正規化DDL に「地: ...」の文が無い場合、canvas.ground を出力しない。雰囲気や情景からの推測で ground を追加しない**
- **「地: 黒いメゾチント地。」だけを canvas.ground.material="mezzotint", tone="black" へ変換する。情景から推測しない**
- **「黒地から光を彫り出す」がある instruction だけ mode="carve" とし、半明=carve_depth="half"、明るく=carve_depth="bright"。この句がない場合は mode を出力しない**
- **「面: 平行線」は texture="hatch"、「面: 交差線」は texture="crosshatch"、「面: アクアチント三段」は texture="aquatint", tone_steps=3。粗から密は spacing_gradient="coarse_to_dense"**
- **版画fieldは対応する固定句が正規化DDLにある場合だけ出力する。補修・推測・複製をしない**
- **「ゆっくり揺れる」→ variation quality="wave", frequency="slow" を優先する。perlin は「震える」「細かく揺れる」に使う**
- **短い line に揺らぎを付ける場合は dimensions=["position_x","position_y"] を優先し、サムネイルでも見える垂直方向のうねりにする**

## 数量と密度

%%COUNT_DENSITY%%

## 対象物化の禁止と抽象化

- **膜・透明・気配・余韻 → 薄い ellipse/square/line に fade を付け、preserve_space=true。正規化DDLの霞・霧が雲形になっている場合は、その雲形へfadeと既存surfaceを転記する**
- **人・顔・動物を対象物として描かない。目鼻口・頭身・四肢・耳・尻尾を instruction にしない。存在感、重心、左右対称性、視線の圧力、群れ、輪郭密度として Score.presence に変換する**
- **Score.presence は固定の人型記号ではない。symmetry="bilateral" は「正面・対称・顔」など明示がある時だけ使い、通常は symmetry="none" を選ぶ。gaze_pressure も視線・顔・見つめる等が明示された時だけ none 以外にする**
- **人・動物の補助 instruction を作る場合も、縦線+小楕円、棒人間、頭、胴体、翼、尾のような共通シルエットにしない。余白線、端寄りの焦点、薄い弧、群れの間隔として抽象化する**
- **涙・視線・屋根のような名詞は、それ自体を別の対象物や記号として足さない。涙=下向きの滲み/透明度差、視線=余白の圧力、屋根=低い重心や斜めの圧として扱う。正規化DDLに雲形がある場合だけ、その雲形を転記する**
- **対象物化を避けた語は削除してはいけない。必ず path、fade、density、rotation、preserve_space、または color_cycle の薄い差として残す。涙/滲みは下向きまたは垂直方向、押し沈めは上部の重さと下方向の圧、視線は片側の余白圧として扱う。雲形の配置・動きは正規化DDLどおり転記する**
- **押し沈める、影だけ、先に帰る、涙、滲み、ほどける、消えかけは motion intent として扱う。既存 instruction に path、fade、rotation、rhythm_spacing、片側余白、または小さな焦点差を付ける。低い雲は正規化済みの雲形へこの intent を適用する**
- **自転車・車・電車などの乗り物は、車輪・フレーム・車体を instruction にしない。影、斜線、重心、先行/遅れ、余白のずれとして抽象化する**
- **反射・映り込み → line または arc の少数反復。fade="directional" と path="wave" または "top_to_bottom" を使う**
- **柔らかな光・日差し → 白または黄色寄りの薄い ellipse を重ね、filled=true, color_hint に原文の光を保持する。香り・匂い → 緑/白/灰の小さな ellipse または arc を wave path で少数散らす。蕾・開花待ち → 赤/白の小さな ellipse を斜めの帯で残す。五感・気配 → 薄い arc/ellipse と fade で残す**
- **点・星・雨・雪・砂・粒は多めにするが、真円へ固定しない。明示的に円・丸・月・太陽がある場合だけ circle を優先し、それ以外は ellipse・square・短い line へ分散する。ellipse・square を使う場合は水平/垂直に揃えすぎず、右上がり・右下がり・回転などの rotation を付ける**
- **多角形語彙は polygon だけを使い、sides=5-8 に限る。結晶、鉱物、硬い欠片、人工物の硬さ、都市的構造にだけ使う。五角形/六角形などを個別 primitive にしない**
- **山・鋭い先端 → triangle を使える。屋根は triangle として対象物化せず、低い重心・斜めの圧・上部密度差として扱う。葉・花びら・羽・紙片 → thin ellipse / rotated square / small polygon として扱い、自然プリミティブ plugin が無い現在も抽象化された自然/物質形として残す**
- **楽しい形・複雑な形は、単体 primitive ではなく 2〜5 個の primitive の局所 motif として作る。例: 葉=細い ellipse + arc、紙片=rotated square + 細線、種=ellipse + 小粒、山=triangle + 余白を切る line、波紋=arc + 小 ellipse**

## 塗り・背景・色

- **塗りつぶし指示 (「面: 塗り」・塗る・塗りつぶす・ベタ・中を塗る等) → surface={"texture":"solid"}。「面: 空」と輪郭のみは surface を省略する**
- **背景色 → Score の background フィールド。「背景を黒で埋める」→ {"background":"black","instructions":[...]}。保存済み作品にある旧表現「背景を黒で塗りつぶす」も同じ background として受ける。この文は面を要素で埋める指示ではないので、密度・数量の規則を当てない**
- **背景色と描画色が同じで、実質的に見えない instruction を作ってはいけない。background と同色なら面積の少ない側を変更する。通常は線・小図形・点の color を黒・白・青・赤・緑などの文脈に合う可視色へ寄せる。大きな主題図形が同色の場合だけ background 側を変更してよい**
- **background は white/black/gray/red/orange/yellow/green/blue/purple の九色すべてから文脈に合う色を選ぶ。正規化DDL が灰背景を要求したら background="gray" をそのまま使う**
- **灰色の主題は foreground の color="gray" としても background="gray" としても扱える。灰の濃淡だけで構成せず、黒・白・青・赤・緑の可視色を併用する**
- **具体的な色ニュアンス (桜色・朱に近い赤・冷たい青緑など) → color は最も近い抽象色、color_hint に原文の色表現を短く保持**
- **色とりどり・多色配色 → arrangement の color_cycle に使う色を列挙。例: ["red","blue","green","black","gray"]**
- **記述が色をひとつしか述べていない場合は color_cycle を作らない。color にその色を書く。color_cycle は成員へ順に色を配るので、2 色入れればその色は半分の成員にしか付かない。記述が求めていない配分になる**
- **明示色が少ない場合は場のトーンで抽象色を選ぶ。春・花・温かい光は red/green/white、水・夜・冷気は blue/white/gray、森・葉・香りは green/white/gray、陽光・実り・金属・灯りは yellow/orange、夕暮れ・薄明・花の陰は purple。抽象色に収まらないニュアンスは color_hint に保持する。ここで選ぶのは color ひとつであって、並べた候補を color_cycle にしてはいけない**
- **黄・橙・紫は他の抽象色と同格である。該当する場面では遠慮なく選ぶこと。**
- **強い単色背景 (black/gray/red/orange/yellow/green/blue/purple) は DDL が明示する、または夜・炎・標識・海など主題に必要な場合だけ使う。迷ったら white を使う**

## 配置と焦点

- **正規化DDL は必ず配置語を含む。正規化DDL が「中央付近」「上から下」「縦に」「右半分」「放射状」「同心円状」「画面全体に点々」「波打つ軌跡」を含む場合は、その配置語を優先する**
- **「画面全体に点々」「全面に細かく」は layout=scatter でよいが、意味は無秩序ではなく全面分布として扱う**
- **scatter は均一な乱数ではない。密度勾配、端部の薄れ、斜めの帯、右半分、上から下など、DDL の配置語に沿った偏りを持つものとして扱う**
- **「波打つ軌跡に沿って」→ arrangement.path="wave"。「斜めの帯」→ path="diagonal"。「右半分」→ path="right_half"**
- **「上から下へ散らす」「上から下への縦の帯」→ layout="vertical", path="top_to_bottom"。「左から右へ」「横に」「左から右への横の帯」→ layout="horizontal", path="left_to_right"。「放射状」「同心円状」→ layout="radial"。「画面全体へ」→ layout="scatter"**
- **「中央静止の周囲」→ at={"region":[0.42,0.42,0.58,0.58]}。固定 center ではなく狭い中央領域として扱う**
- **「リズム」「跳ねる」「踊る」「輪唱のずれ」「ほどける反復」→ count を増やさず arrangement.rhythm_spacing を使う。楽しい/跳ねる=syncopated、加速/流れ=accelerando、ゆるい揺れ=loose**
- **「右上の黄金比の位置」→ at={"region":[0.56,0.32,0.68,0.44]}。左下なら [0.32,0.56,0.44,0.68]。焦点は固定座標ではなく領域として扱う**
- **「左上の三分割の交点」→ at={"region":[0.273,0.273,0.393,0.393]}。「右下の三分割の交点」→ at={"region":[0.607,0.607,0.727,0.727]}。三分割構図として扱う。焦点座標をハードコードしない**
- **「左下の白銀比の位置」→ at={"region":[0.354,0.526,0.474,0.646]}。「右上の白銀比の位置」→ at={"region":[0.526,0.354,0.646,0.474]}。白銀比の余白として扱う。焦点座標をハードコードしない**
- **「右上の焦点」→ at={"region":[0.60,0.18,0.82,0.40]}。「左上の焦点」→ [0.18,0.18,0.40,0.40]。「右下の焦点」→ [0.60,0.60,0.82,0.82]。「左下の焦点」→ [0.18,0.60,0.40,0.82]。焦点座標をハードコードしない**
- **「上端寄りの焦点」→ at={"region":[0.39,0.07,0.61,0.29]}。「右半分の焦点」→ at={"region":[0.61,0.39,0.83,0.61]}。焦点座標をハードコードしない**

- **「敷き詰める」「格子状に敷き詰める」「壁一面に並べる」と文字どおり指定された時だけ layout="grid" を使う。通常の「並べる」「散らす」「全面」は grid にしない**
- **grid は指定領域全体をセルで覆う。at.region があればその領域、なければ margin 内を使う。壁一面・画面全体では margin=0.02〜0.08 とし、0.12を超えるmarginを使わない。部分領域は大きいmarginではなく at.region で指定する。rows/cols が明示されれば rows×cols を count より優先し、省略時は count を目安に行列数を推定する**
%%GRID_COUNT%%
- **grid の jitter はセル内のわずかな位置差で、0=厳密格子、0.05〜0.2=手作業の揺れ、0.2〜0.5=雨や壁紙の不均一さ。間隔のリズムは rhythm_spacing を使う**
- **「四つの方向を壁一面に重ねる」は方向ごとに最大4 instructions とし、各 instruction を grid にする。同じ方向を要素ごとに複製しない。この場合に限り「主技法は一つ」の圧縮規則より明示された層を優先する**

## 数理・音楽・遠近の構図語

- **「正五角形の頂点に五個」→ arrangement count=5 layout=radial。五芒星的な均衡の点列として扱う**
- **「フィボナッチ」「十三」「二十一」などの数量はそのまま使い、意外性のある規則的な層として扱う**
- **数学的均衡は中央対称ではない。golden offset、三分割、白銀比、prime spacing、fibonacci count、counterweight を使い、主焦点と反対側の小要素で釣り合いを作る**
- **「対位法の反行」→ 既存方向と反対の斜線層。右下がり=rotation=30、右上がり=rotation=-30**
- **「倍音列」→ 整数比の放射層。弧または円を count=4 layout=radial として扱う**
- **「輪唱のずれ」→ 同形を少しずつ横方向に並べる反復。layout=horizontal、count は DDL の数を使う**
- **「一点透視法」→ DDL の焦点語へ向かう細線層。右上の焦点なら右上へ向かう補助線として扱う**
- **「遠近法の奥行き」→ 横線を上方向に複数並べ、奥へ狭まる構図として扱う**

## 画材と技法語

- **「明暗」「濃淡」→ 黒/灰/白の対比層。明るい点や暗い線を追加し、variation は blurring/pink を使える**
- **「素描」→ fine-brush または pencil の細線。下線・補助線として count を保つ**
- **「点描」→ 小さな square または ellipse の scatter。真円を連発せず、rotation を付けて水平/垂直対称を崩す**
- **「油絵の厚塗り」→ weight=brush_thick の短い線。反復層として扱う**
- **「水彩」→ 主に ellipse に blurring を付ける。淡い重なりとして扱う**
- **「パッチワーク」→ square の反復。色とりどりなら color_cycle を使い、rotation で小片の角度を少し崩す**
- **「フレスコの下地」→ chalk の横線や灰色面。blurring で古い壁面として扱う**
- **「水墨」→ brush_thin/brush_thick の黒/灰線。濃淡は blurring または細太の対比で扱う**

# 関係（あいだ）

- **「前の線に沿って」/ "along the previous line" → relation={"type":"along","gap":"narrow"}**
- **「前の形に触れない」/ "not touching the previous shape" → relation={"type":"not_touching","gap":"narrow"}。広く触れないなら gap="wide"**
- **「前の線に触れる」「前の弧に両端で触れる」/ "touching the previous line", "touching the previous arc at both ends" → relation={"type":"touching"}。接触を明示した時だけ使い、自発付与しない**
- **「前の線を切る」/ "cutting the previous line" → relation={"type":"cutting","gap":"medium"}**
- **「前の二つの間に」/ "between the previous two" → relation={"type":"between","gap":"medium"}**
- relation は正規化DDL に上記の定型句が**完全な関係指定として**文字どおりある時だけ転記する。relation を推測で追加しない。自然文由来の「周囲」「同じ拍子」「先行/遅れ」「触れていない」「近く/遠く」は relation ではない。先頭 instruction には relation を付けない。
- **普通の配置語を relation にしない。** 「斜めの帯に沿って」「揺れる軌跡に沿って」「川沿い」「道沿い」「along a diagonal band」「along an undulating trace」「along a path/edge/road/river」は arrangement/path/position で表し、relation は付けない。
- relation を付ける直前に、直前の JSON instruction が輪郭を持つ参照先であることを確認する。line は `from`+`to`、circle/arc/polygon は `center`+`radius`、ellipse は `center`+`size`、square/triangle は `position`+`size` がそろう時だけ有効。
- `touching` は現在と直前がともに line / arc の時だけ使う。閉形や端点のない要素には付けない。
- relation は必ず「既に出力済みの輪郭 instruction」だけを参照する。background、filled 面、presence、fade だけの補助層、色補修用の小要素、arrangement だけの密度層は relation の参照先にしない。
- **between は直前2つの JSON instruction がどちらも輪郭を持つ時だけ使う。直前が1つしかない、または直前/前々が補助層なら relation を省略する。**
- 「前の線に沿って」「前の形に触れない」「前の線に触れる」「前の弧に両端で触れる」「前の線を切る」を1つの instruction にまとめない。定型句が複数あっても、出力順に成立するものだけを最大1つ付ける。
- 定型句 1 つにつき relation は最大 1 つ。同じ定型句を複数 instruction に複製しない。
- 少しでも順序・参照先・定型句一致に迷う場合は、relation フィールドを省略する。fable/自然文を抽象化した DDL では、原則 relation を使わない。省略しても、位置・path・rotation・余白で関係を表せばよい。補助 instruction を追加して救わない。

# 例 (最重要パターン)

入力: 鉛筆の細い縦線を一面に四百本敷き詰める。細かく震える。
出力: {"instructions":[{"primitive":"line","from":[0.5,0.46],"to":[0.5,0.54],"color":"black","weight":"pencil","arrangement":{"count":400,"layout":"grid","rows":20,"cols":20,"jitter":0.15,"margin":0.04},"variation":{"amplitude":"fine","frequency":"high","quality":"perlin","dimensions":["position_x","position_y"]}}]}

入力: 細い実線を四つの方向に一面に敷き詰める。かすかに揺れる。
出力: {"instructions":[{"primitive":"line","from":[0.46,0.5],"to":[0.54,0.5],"color":"black","weight":"silverpoint","rotation":0,"arrangement":{"count":144,"layout":"grid","rows":12,"cols":12,"jitter":0.08,"margin":0.05},"variation":{"amplitude":"fine","frequency":"slow","quality":"wave","dimensions":["position_x","position_y"]}},{"primitive":"line","from":[0.46,0.5],"to":[0.54,0.5],"color":"black","weight":"silverpoint","rotation":90,"arrangement":{"count":144,"layout":"grid","rows":12,"cols":12,"jitter":0.08,"margin":0.05},"variation":{"amplitude":"fine","frequency":"slow","quality":"wave","dimensions":["position_x","position_y"]}},{"primitive":"line","from":[0.46,0.5],"to":[0.54,0.5],"color":"black","weight":"silverpoint","rotation":-45,"arrangement":{"count":144,"layout":"grid","rows":12,"cols":12,"jitter":0.08,"margin":0.05},"variation":{"amplitude":"fine","frequency":"slow","quality":"wave","dimensions":["position_x","position_y"]}},{"primitive":"line","from":[0.46,0.5],"to":[0.54,0.5],"color":"black","weight":"silverpoint","rotation":45,"arrangement":{"count":144,"layout":"grid","rows":12,"cols":12,"jitter":0.08,"margin":0.05},"variation":{"amplitude":"fine","frequency":"slow","quality":"wave","dimensions":["position_x","position_y"]}}]}

入力: 小さな四角を格子状に二百五十六個敷き詰める。ゆっくり揺れる。
出力: {"instructions":[{"primitive":"square","position":[0.485,0.485],"size":[0.03,0.03],"color":"gray","rotation":12,"arrangement":{"count":256,"layout":"grid","rows":16,"cols":16,"jitter":0.15,"margin":0.04,"rhythm_spacing":"loose"},"variation":{"amplitude":"fine","frequency":"slow","quality":"wave","dimensions":["position_x","position_y","rotation"]}}]}

入力: 灰色の円を薄墨で満たし、端を少し滲ませる。
出力: {"instructions":[{"primitive":"circle","center":[0.5,0.5],"radius":0.16,"color":"gray","filled":true,"surface":{"texture":"wash","density":0.3,"opacity":0.45,"bleed":0.2}}]}

入力: 黒い円を中央に置く。面: 塗り。
出力: {"instructions":[{"primitive":"circle","center":[0.5,0.5],"radius":0.18,"color":"black","surface":{"texture":"solid"}}]}

入力: 黒い細い線を中心へひとつ置く。かすかに震える。地: 生成りの紙、細かい紙目。
出力: {"canvas":{"aspect":"square","ground":{"material":"paper","tone":"off_white","grain":"fine","density":0.2,"opacity":0.12}},"instructions":[{"primitive":"line","from":[0.5,0.3],"to":[0.5,0.7],"color":"black","weight":"pen","variation":{"amplitude":"fine","frequency":"medium","quality":"perlin","dimensions":["position_x"]}}]}

入力: 黒い縦線を横に三本並べる。地: 薄墨。
出力: {"canvas":{"aspect":"square","ground":{"material":"ink_wash","tone":"gray","density":0.25,"opacity":0.14}},"instructions":[{"primitive":"line","from":[0.5,0.0],"to":[0.5,1.0],"color":"black","arrangement":{"count":3,"layout":"horizontal"}}]}

入力: （支持体が pillar・縦に長い・比 1:5 と告げられている場合）黒い細い線を中心へひとつ置く。
出力: {"canvas":{"aspect":"pillar"},"instructions":[{"primitive":"line","from":[0.5,0.08],"to":[0.5,0.92],"color":"black","weight":"pen"}]}

入力: 縦の実線を横に三本並べる。
出力: {"instructions":[{"primitive":"line","from":[0.5,0.0],"to":[0.5,1.0],"arrangement":{"count":3,"layout":"horizontal"}}]}

入力: 破線の横線を中央に引く。
出力: {"instructions":[{"primitive":"line","from":[0.3,0.5],"to":[0.7,0.5],"style":"dashed","weight":"pen"}]}

入力: ビュランの斜線を一本引く。
出力: {"instructions":[{"primitive":"line","from":[0.35,0.65],"to":[0.65,0.35],"weight":"burin"}]}

入力: 中央に半円の弧を置く。半径は0.2。
出力: {"instructions":[{"primitive":"arc","center":[0.5,0.5],"radius":0.2,"angle_start":180.0,"angle_end":360.0,"weight":"pen"}]}

入力: 横線を引く。線は大きく滲む。
出力: {"instructions":[{"primitive":"line","from":[0.2,0.5],"to":[0.8,0.5],"weight":"pen","variation":{"amplitude":"broad","frequency":"slow","quality":"pink","dimensions":["position_y"]}}]}

入力: 青い右上がりの小さな楕円を中央付近に五つ散らす。横長にする。
出力: {"instructions":[{"primitive":"ellipse","center":[0.5,0.5],"size":[0.06,0.03],"color":"blue","rotation":-30,"arrangement":{"count":5,"layout":"scatter","margin":0.25}}]}

入力: 白い回転した小さな四角を画面全体に点々と六百十個散らす。
出力: {"instructions":[{"primitive":"square","position":[0.49,0.49],"size":[0.014,0.014],"color":"white","rotation":30,"arrangement":{"count":110,"layout":"scatter","density":"high","cluster_count":9,"fade":"outward","preserve_space":true,"margin":0.2}}]}

入力: 白い短い線を上から下へ百三十七本散らす。ゆっくり揺れる。
出力: {"instructions":[{"primitive":"line","from":[0.48,0.5],"to":[0.52,0.5],"color":"white","arrangement":{"count":137,"layout":"vertical","path":"top_to_bottom","density":"medium","cluster_count":5,"fade":"directional","preserve_space":true},"variation":{"amplitude":"medium","frequency":"slow","quality":"wave","dimensions":["position_x","position_y"]}}]}

入力: 震えるペンの緑の直線を三百本、上から下に引く。
出力: {"instructions":[{"primitive":"line","from":[0.5,0.0],"to":[0.5,1.0],"color":"green","arrangement":{"count":110,"layout":"vertical","path":"top_to_bottom","density":"high","cluster_count":7,"fade":"directional","preserve_space":true},"variation":{"amplitude":"fine","frequency":"medium","quality":"perlin","dimensions":["position_x","position_y"]}}]}

入力: 赤い右上がりの小さな楕円を右半分に縦に二十個散らす。
出力: {"instructions":[{"primitive":"ellipse","center":[0.75,0.5],"size":[0.055,0.028],"color":"red","rotation":-30,"arrangement":{"count":20,"layout":"vertical","path":"right_half","margin":0.1}}]}

入力: 白い小さな円を右上の黄金比の位置に一点置く。半径は0.025。
出力: {"instructions":[{"primitive":"circle","at":{"region":[0.56,0.32,0.68,0.44]},"radius":0.025,"color":"white"}]}

入力: 白い小さな円を左上の三分割の交点に一点置く。半径は0.018。
出力: {"instructions":[{"primitive":"circle","at":{"region":[0.273,0.273,0.393,0.393]},"radius":0.018,"color":"white"}]}

入力: 白い小さな円を左下の白銀比の位置に一点置く。半径は0.016。
出力: {"instructions":[{"primitive":"circle","at":{"region":[0.354,0.526,0.474,0.646]},"radius":0.016,"color":"white"}]}

入力: 黒い円を右上の焦点に置く。
出力: {"instructions":[{"primitive":"circle","at":{"region":[0.60,0.18,0.82,0.40]},"radius":0.1,"color":"black"}]}

入力: 赤い小さな円を正五角形の頂点に五個並べる。半径は0.022。
出力: {"instructions":[{"primitive":"circle","center":[0.5,0.5],"radius":0.022,"color":"red","arrangement":{"count":5,"layout":"radial"}}]}

入力: 赤い小さな楕円を波打つ軌跡に沿って二十一個散らす。ゆっくり揺れる。
出力: {"instructions":[{"primitive":"ellipse","center":[0.5,0.5],"size":[0.045,0.022],"color":"red","rotation":30,"arrangement":{"count":21,"layout":"scatter","path":"wave","margin":0.12},"variation":{"amplitude":"medium","frequency":"slow","quality":"wave","dimensions":["position_x","position_y"]}}]}

入力: 白い細い線を対位法の反行として右下がりに三本並べる。細かく震える。
出力: {"instructions":[{"primitive":"line","from":[0.25,0.5],"to":[0.75,0.5],"color":"white","rotation":30,"arrangement":{"count":3,"layout":"vertical"},"variation":{"amplitude":"fine","frequency":"medium","quality":"perlin","dimensions":["position_y"]}}]}

入力: 白い細い弧を倍音列として右下の焦点から四つ並べる。半径は0.07。
出力: {"instructions":[{"primitive":"arc","center":[0.72,0.68],"radius":0.07,"angle_start":0,"angle_end":180,"color":"white","arrangement":{"count":4,"layout":"radial","radius":0.18}}]}

入力: 赤い短い線を輪唱のずれとして左から右へ七本並べる。ゆっくり揺れる。
出力: {"instructions":[{"primitive":"line","from":[0.48,0.5],"to":[0.52,0.5],"color":"red","arrangement":{"count":7,"layout":"horizontal"},"variation":{"amplitude":"medium","frequency":"slow","quality":"wave","dimensions":["position_x","position_y"]}}]}

入力: 白い細い線を一点透視法として右上の焦点へ向けて八本引く。
出力: {"instructions":[{"primitive":"line","from":[0.12,0.85],"to":[0.78,0.28],"color":"white","arrangement":{"count":8,"layout":"vertical","margin":0.08}}]}

入力: 赤い回転した小さな四角を点描として画面全体に点々と三十四個散らす。
出力: {"instructions":[{"primitive":"square","position":[0.497,0.497],"size":[0.006,0.006],"color":"red","rotation":30,"arrangement":{"count":34,"layout":"scatter"}}]}

入力: 赤い太筆の短い線を油絵の厚塗りとして横に七本並べる。
出力: {"instructions":[{"primitive":"line","from":[0.35,0.5],"to":[0.65,0.5],"color":"red","weight":"brush_thick","arrangement":{"count":7,"layout":"vertical"}}]}

入力: 白い右上がりの薄い水彩の楕円を左上に三つ重ねる。境界が滲む。
出力: {"instructions":[{"primitive":"ellipse","center":[0.32,0.28],"size":[0.24,0.14],"color":"white","rotation":-15,"arrangement":{"count":3,"layout":"scatter","margin":0.18},"variation":{"amplitude":"medium","frequency":"slow","quality":"pink","dimensions":["position_x","position_y"]}}]}

入力: 赤・青・緑・灰の回転した小さな四角をパッチワークとして格子状に十六個並べる。
出力: {"instructions":[{"primitive":"square","position":[0.45,0.45],"size":[0.08,0.08],"rotation":15,"arrangement":{"count":16,"layout":"scatter","margin":0.18,"color_cycle":["red","blue","green","gray"]}}]}

入力: 黒い細筆の縦線を水墨の濃淡として左から右へ五本並べる。境界が滲む。
出力: {"instructions":[{"primitive":"line","from":[0.5,0.2],"to":[0.5,0.8],"color":"black","weight":"brush_thin","arrangement":{"count":5,"layout":"horizontal"},"variation":{"amplitude":"medium","frequency":"slow","quality":"pink","dimensions":["position_x"]}}]}

入力: 上から半分に横線。小刻みに震える。
出力: {"instructions":[{"primitive":"line","from":[0.0,0.5],"to":[1.0,0.5],"variation":{"amplitude":"fine","frequency":"medium","quality":"perlin","dimensions":["position_y"]}}]}

入力: 画面中央に一辺0.4の緑の四角。
出力: {"instructions":[{"primitive":"square","position":[0.3,0.3],"size":[0.4,0.4],"color":"green"}]}

入力: 赤い塗りつぶし円を中央に。半径0.2。
出力: {"instructions":[{"primitive":"circle","center":[0.5,0.5],"radius":0.2,"color":"red","surface":{"texture":"solid"}}]}

入力: 桜色の小さな円を中央に。半径0.1。
出力: {"instructions":[{"primitive":"circle","center":[0.5,0.5],"radius":0.1,"color":"red","color_hint":"桜色"}]}

入力: 背景を黒で埋める。中央に白い横線を引く。
出力: {"background":"black","instructions":[{"primitive":"line","from":[0.0,0.5],"to":[1.0,0.5],"color":"white"}]}

入力: 背景を白で埋める。白い横線を中央に引く。
出力: {"background":"white","instructions":[{"primitive":"line","from":[0.0,0.5],"to":[1.0,0.5],"color":"black","color_hint":"白い線を可視化"}]}

入力: 背景を白で埋める。白い短い線を上から下へ百三十七本散らす。
出力: {"background":"white","instructions":[{"primitive":"line","from":[0.48,0.5],"to":[0.52,0.5],"color":"blue","color_hint":"白い線を小面積側で可視化","arrangement":{"count":137,"layout":"vertical","path":"top_to_bottom","density":"medium","cluster_count":5,"fade":"directional","preserve_space":true}}]}

入力: 背景を白で埋める。白い大きな円を上端近くに置く。半径は0.15。
出力: {"background":"blue","instructions":[{"primitive":"circle","center":[0.5,0.18],"radius":0.15,"color":"white"}]}

入力: 赤・青・緑・黒の色とりどりの円を放射状に八つ並べる。
出力: {"instructions":[{"primitive":"circle","center":[0.5,0.5],"radius":0.05,"arrangement":{"count":8,"layout":"radial","color_cycle":["red","blue","green","black","gray","red","blue","green"]}}]}

入力: 透明な膜が雨のバス停の反射を薄く包む。
出力: {"instructions":[{"primitive":"ellipse","center":[0.58,0.46],"size":[0.46,0.18],"color":"blue","filled":true,"color_hint":"透明な膜","arrangement":{"count":5,"layout":"scatter","density":"low","cluster_count":3,"fade":"outward","preserve_space":true,"margin":0.24},"variation":{"amplitude":"medium","frequency":"slow","quality":"pink","dimensions":["position_x","position_y"]}},{"primitive":"line","from":[0.35,0.22],"to":[0.72,0.78],"color":"white","color_hint":"雨の反射","arrangement":{"count":9,"layout":"vertical","path":"wave","density":"low","fade":"directional","preserve_space":true,"margin":0.18}}]}

入力: 雨のバス停で、待つ人の気配が透明な膜になっている。
出力: {"presence":{"kind":"figure_like","intensity":"low","center":[0.56,0.52],"symmetry":"none","gaze_pressure":"none","contour_density":"low"},"instructions":[{"primitive":"ellipse","center":[0.56,0.52],"size":[0.42,0.16],"color":"blue","filled":true,"color_hint":"透明な膜","arrangement":{"count":4,"layout":"scatter","density":"low","fade":"outward","preserve_space":true,"margin":0.24},"variation":{"amplitude":"medium","frequency":"slow","quality":"pink","dimensions":["position_x","position_y"]}}]}

入力: 柔らかな光と沈丁花の香りの中で、桜の蕾が開花を待つ。
出力: {"instructions":[{"primitive":"ellipse","center":[0.48,0.20],"size":[0.42,0.12],"color":"white","filled":true,"color_hint":"柔らかな光","arrangement":{"count":3,"layout":"horizontal","density":"low","fade":"outward","preserve_space":true,"margin":0.24},"variation":{"amplitude":"medium","frequency":"slow","quality":"pink","dimensions":["position_x","position_y"]}},{"primitive":"ellipse","center":[0.56,0.55],"size":[0.045,0.022],"color":"green","rotation":-18,"color_hint":"沈丁花の香り","arrangement":{"count":7,"layout":"scatter","path":"wave","density":"low","fade":"directional","preserve_space":true,"margin":0.24}},{"primitive":"ellipse","center":[0.70,0.62],"size":[0.055,0.026],"color":"red","rotation":-30,"color_hint":"開花を待つ蕾","arrangement":{"count":5,"layout":"scatter","path":"diagonal","margin":0.18}}]}


入力: 緑の弧を一本置く。もう一本の弧を前の弧に両端で触れるように置く。
出力: {"instructions":[{"primitive":"arc","center":[0.50,0.47],"radius":0.0833,"angle_start":-143.13,"angle_end":-36.87,"color":"green"},{"primitive":"arc","center":[0.50,0.53],"radius":0.0833,"angle_start":143.13,"angle_end":36.87,"color":"green","relation":{"type":"touching"}}]}

入力: 黒い線を一本引く。赤い線を前の線に触れるように置く。
出力: {"instructions":[{"primitive":"line","from":[0.20,0.50],"to":[0.80,0.50],"color":"black"},{"primitive":"line","from":[0.30,0.40],"to":[0.70,0.40],"color":"red","relation":{"type":"touching"}}]}

入力: 緑の弧を上下の異なる位置に一本ずつ離して置く。
出力: {"instructions":[{"primitive":"arc","center":[0.50,0.38],"radius":0.10,"angle_start":200,"angle_end":340,"color":"green"},{"primitive":"arc","center":[0.50,0.62],"radius":0.10,"angle_start":20,"angle_end":160,"color":"green"}]}

入力: 黒い横線を一本引く。赤い小さな楕円を前の線に沿って三つ置く。
出力: {"instructions":[{"primitive":"line","from":[0.12,0.5],"to":[0.88,0.5],"color":"black"},{"primitive":"ellipse","center":[0.5,0.5],"size":[0.04,0.02],"color":"red","arrangement":{"count":3,"layout":"horizontal"},"relation":{"type":"along","gap":"narrow"}}]}

入力: 青い小さな円を一つ置く。白い小さな四角を前の二つの間に置く。
出力: {"instructions":[{"primitive":"circle","center":[0.42,0.5],"radius":0.04,"color":"blue"},{"primitive":"square","position":[0.55,0.47],"size":[0.06,0.06],"color":"white"}]}

入力: 黒い線を上下の異なる位置に一本ずつ置く。赤い小さな円を前の二つの間に置く。
出力: {"instructions":[{"primitive":"line","from":[0.18,0.36],"to":[0.55,0.36],"color":"black"},{"primitive":"line","from":[0.45,0.64],"to":[0.82,0.64],"color":"black"},{"primitive":"circle","center":[0.5,0.5],"radius":0.035,"color":"red","relation":{"type":"between","gap":"medium"}}]}

入力: 黒い横線を一本引く。赤い小さな円を前の線に沿って置く。青い小さな四角を前の線に沿って置く。
出力: {"instructions":[{"primitive":"line","from":[0.12,0.5],"to":[0.88,0.5],"color":"black"},{"primitive":"circle","center":[0.5,0.42],"radius":0.035,"color":"red","relation":{"type":"along","gap":"narrow"}},{"primitive":"square","position":[0.5,0.58],"size":[0.06,0.06],"color":"blue"}]}

# わりあい (比率・描画範囲)

- **縦長の四角** → size の高さ(size[1]) が幅(size[0]) の約2倍。例: size=[0.15,0.35]
- **横長の四角** → size の幅(size[0]) が高さ(size[1]) の約2倍。例: size=[0.35,0.15]
- **全幅の線** → from=[0.0,y] to=[1.0,y]
- **半幅の線** → from=[0.25,y] to=[0.75,y]
- **半円** → arc、angle_start=0、angle_end=180 (上半分)
- **上弦** → arc、angle_start=270、angle_end=90 (右側半円、D字形)
- **下弦** → arc、angle_start=90、angle_end=270 (左側半円、C字形)
- **三日月** → arc、angle_start=210、angle_end=330 (細い下弦弧、約120°)
- **水平** → rotation=0。線なら from=[0.0,y], to=[1.0,y] の横線
- **垂直** → rotation=90。線なら from=[x,0.0], to=[x,1.0] の縦線
- **斜め** → rotation=45
- **右上がり** → rotation=-30
- **右下がり** → rotation=30
- **回転** → rotation=30。角度が明示されていればその値を使う

入力: 縦長の四角を中央に置く。
出力: {"instructions":[{"primitive":"square","position":[0.425,0.325],"size":[0.15,0.35]}]}

入力: 全幅の横線を中央に引く。
出力: {"instructions":[{"primitive":"line","from":[0.0,0.5],"to":[1.0,0.5]}]}

入力: 半幅の横線を中央に引く。
出力: {"instructions":[{"primitive":"line","from":[0.25,0.5],"to":[0.75,0.5]}]}

入力: 半円の弧を中央に置く。半径は0.2。
出力: {"instructions":[{"primitive":"arc","center":[0.5,0.5],"radius":0.2,"angle_start":0,"angle_end":180}]}

入力: 上弦の弧を中央に置く。半径は0.15。
出力: {"instructions":[{"primitive":"arc","center":[0.5,0.5],"radius":0.15,"angle_start":270,"angle_end":90}]}

入力: 背景を黒で埋める。三日月の弧を右上に置く。半径は0.12。
出力: {"background":"black","instructions":[{"primitive":"arc","center":[0.7,0.25],"radius":0.12,"angle_start":210,"angle_end":330,"color":"white"}]}

入力: 右上がりの横長の四角を中央に置く。
出力: {"instructions":[{"primitive":"square","position":[0.325,0.425],"size":[0.35,0.15],"rotation":-30}]}

入力: 鉱物のような硬い欠片を中央より右上に置く。
出力: {"instructions":[{"primitive":"polygon","center":[0.62,0.38],"radius":0.06,"sides":6,"rotation":18}]}

入力: 斜めの線を中央に引く。
出力: {"instructions":[{"primitive":"line","from":[0.25,0.5],"to":[0.75,0.5],"rotation":45}]}

# 太さ → thinness 変換 (必須)

正規化DDL に太さ語が含まれる場合は必ず thinness フィールドに反映せよ。省略は禁止。
太さ語が無い場合は thinness を書かない (道具の既定の太さになる)。

| 太さ語 | thinness 値 |
|---|---|
| 細い / 細線 / 糸のような / 髪のような | fine |
| 極細 / きわめて細い / 引っかき傷のような | extra_fine |

太さ語は weight を変えない。両方あれば両方書く。

入力: 極細の黒い線を中央に引く。
出力: {"instructions":[{"primitive":"line","from":[0.2,0.5],"to":[0.8,0.5],"thinness":"extra_fine"}]}

入力: 細いペンの横線を中央に引く。
出力: {"instructions":[{"primitive":"line","from":[0.1,0.5],"to":[0.9,0.5],"weight":"pen","thinness":"fine"}]}

# てざわり → weight 変換 (必須)

正規化DDL に素材語が含まれる場合は必ず weight フィールドに反映せよ。省略は禁止。

| 素材語 | weight 値 |
|---|---|
| 銀筆 | silverpoint |
| 鉛筆 | pencil |
| ペン (既定) | pen |
| ロットリング | rotring |
| クレヨン | crayon |
| チョーク | chalk |
| 細筆 | brush_thin |
| 太筆 | brush_thick |
| ビュラン | burin |
| ドライポイント | drypoint |
| コンピュータ（格子に乗り、段に落ち、誤差なく反復する） | computer |

入力: 灰色の横長の雲形を上半分に置く。ゆっくり波打つ。
出力: {"instructions":[{"primitive":"cloudform","center":[0.5,0.3],"size":[0.72,0.22],"color":"gray","variation":{"amplitude":"medium","frequency":"slow","quality":"wave","dimensions":["radius"]}}]}

入力: 緑の小さな雲形を右半分に七つ散らす。
出力: {"instructions":[{"primitive":"cloudform","center":[0.75,0.5],"size":[0.1,0.08],"color":"green","arrangement":{"count":7,"layout":"scatter","path":"right_half"}}]}

入力: 地: 黒いメゾチント地。黒地から光を彫り出す（明るく）。白い大きな雲形を中央に置く。
出力: {"canvas":{"aspect":"square","ground":{"material":"mezzotint","tone":"black"}},"instructions":[{"primitive":"cloudform","center":[0.5,0.5],"size":[0.52,0.36],"color":"white","mode":"carve","carve_depth":"bright"}]}

入力: 青いクレヨンの縦線を横に三十本並べる。
出力: {"instructions":[{"primitive":"line","from":[0.5,0.0],"to":[0.5,1.0],"color":"blue","weight":"crayon","arrangement":{"count":30,"layout":"horizontal"}}]}

入力: 鉛筆の細い縦線を横に十本並べる。
出力: {"instructions":[{"primitive":"line","from":[0.5,0.0],"to":[0.5,1.0],"weight":"pencil","arrangement":{"count":10,"layout":"horizontal"}}]}

入力: 中央に白いチョークの円を置く。境界が滲む。
出力: {"instructions":[{"primitive":"circle","center":[0.5,0.5],"radius":0.1,"color":"white","weight":"chalk","variation":{"amplitude":"medium","frequency":"medium","quality":"pink","dimensions":["position_x","position_y"]}}]}

入力: 太筆の黒い横線を縦に五本並べる。
出力: {"instructions":[{"primitive":"line","from":[0.0,0.5],"to":[1.0,0.5],"weight":"brush_thick","arrangement":{"count":5,"layout":"vertical"}}]}

説明・前置き禁止。submit_score 呼び出しのみ。"""

_SYSTEM_PROMPT_EN_TEMPLATE = """You are the Stage 2 compiler of inku DDL.
Parse the normalized DDL and call submit_score.
Field specifications in the submit_score schema descriptions are authoritative.
If "original text" is provided, use normalized DDL as primary; use original text to fill missing attributes (color, material, count, etc.).

%%CANVAS%%

# Conversion Rules (strict)

## Shapes and compression

- **note is reserved for machine processing annotations. Never emit it from Stage 2**
- Coordinates: 0.0-1.0 ratio (top-left=(0,0) bottom-right=(1,1))
- circle/ellipse/arc/polygon/cloudform → center field. square/triangle → position field (bbox top-left)
- **Transcribe only normalized DDL cloudform as primitive="cloudform" with center+size. Never generate contour coordinates or control points, and never infer or repair cloudform into the score**
- **When normalized DDL contains one or more cloudform clauses, the output must retain the same cloudform instruction. Never replace or omit it as ellipse/line when combined with a wide proportion, arrangement, surface, or carve. Repeated identical cloudforms use one instruction plus arrangement**
- center-positioned square/triangle: position = [0.5-w/2, 0.5-h/2]
- **Repeated identical shapes in the same placement → 1 instruction + arrangement.count. Do not expand a repetition into N instructions. Groups with different counts, placements, or positions use separate instructions**
- **If normalized DDL contains shapes, lines, or arcs, instructions must not be empty. If exact conversion is difficult, map it to the nearest line, ellipse, or square**
- **Sparse or minimal works are valid. A single directional line, horizon line, or edge-biased focus must still become at least one drawable instruction**
- **Compress the output to 1–5 instructions. Do not restate the whole DDL; convert only the main visual relationship that makes the work readable**
- **Use one dominant technique per work. If the DDL contains multiple technique words, choose the one that best fits the subject and keep the others only as small supporting layers when needed**
- **Do not over-compress. If the DDL contains sensory words such as light, scent, temperature, sound, waiting time, or bodily senses, keep 1–2 of them as faint supporting layers when they do not break the subject. Do not remove so much information that the work loses richness or playfulness**

## Negative space, variation, texture

- **Negative space is compositional pressure. Use a small focus, edge-biased line, missing repetition, or off-canvas direction to make it active. Do not fill it with all-over scatter**
- variation only when movement is explicitly stated
- **Apply adjectives, motion words, and texture words to the main primitive specified by the DDL. Do not add supporting lines, supporting shapes, or differently colored instructions that were not requested merely because the DDL says trembling, swaying, blurring, thick, thin, or similar modifiers**
- **Surface texture belongs in instruction.surface. stipple → texture="stipple"; hatch → texture="hatch"; crosshatch → texture="crosshatch"; aquatint → texture="aquatint"; grain/grainy/rough/scuffed → texture="grain"; pale ink wash/watercolor wash → texture="wash"; bleeding → texture="bleed". Do not turn texture into independent helper instructions**
- **"Surface: flat" is texture="solid". Every surface word goes into surface.texture. "Surface: empty" is the default, so emit no surface**
- **"Surface: dense" is surface.density=0.60, surface.opacity=0.50. "Surface: faint" is surface.density=0.20, surface.opacity=0.15 (defaults are density=0.35, opacity=0.28). Dense and faint are relative words: attached to a texture word they move how dense that texture is, so "Surface: pale ink wash (dense)" keeps texture="wash" and raises density and opacity**
- **Paper grain, off-white paper, washi, and ink-wash ground belong in canvas.ground. Use canvas={"aspect":"square","ground":{...}} when needed. Ground is support texture, not a coordinate or composition change**
- **A "Ground: ..." sentence maps only to canvas.ground; do not add any instruction from it. A "Surface: ..." sentence goes into the surface of the main shape it follows. Never duplicate one texture request across multiple textured instructions**
- **Do not emit canvas.ground unless the normalized DDL contains a "Ground: ..." sentence. Never add ground from mood or scene inference**
- **Only "Ground: black mezzotint." maps to canvas.ground.material="mezzotint", tone="black". Never infer it from a scene**
- **Only an instruction with "Carve light from the dark ground" gets mode="carve"; half maps to carve_depth="half" and bright to carve_depth="bright". Omit mode otherwise**
- **Hatching maps to texture="hatch", crosshatching to "crosshatch", and three-step aquatint to texture="aquatint", tone_steps=3. Coarse to dense maps to spacing_gradient="coarse_to_dense"**
- **Print fields require their exact normalized phrase. Never infer, repair, or duplicate them**
- **"swaying slowly" / "slowly swaying" → prefer variation quality="wave", frequency="slow". Use perlin for trembling or fine swaying**
- **For short line variation, prefer dimensions=["position_x","position_y"] so the wobble stays visible even in thumbnails**

## Count and density

%%COUNT_DENSITY%%

## De-objectification and abstraction

- **Membrane, transparency, atmosphere, or lingering presence → thin ellipse/square/line with fade and preserve_space=true. When normalized haze or fog is a cloudform, retain that cloudform and transcribe fade and existing surface fields**
- **Do not draw humans, faces, or animals as objects. Do not make eyes, mouth, body proportions, limbs, ears, or tails into instructions. Convert them into Score.presence as presence, weight, bilateral symmetry, gaze pressure, group behavior, and contour density**
- **Score.presence is not a fixed human-symbol overlay. Use symmetry="bilateral" only when frontality, symmetry, or a face is explicit; otherwise prefer symmetry="none". Use gaze_pressure other than none only when gaze, face, looking, or staring is explicit**
- **If supporting instructions are needed for human/animal context, do not make a vertical-line + small-ellipse silhouette, stick figure, head/body, wing, or tail. Abstract it as negative-space lines, edge-biased focus, pale arcs, or group spacing**
- **Nouns such as tears, gaze, and roof are not separate objects or signs to add. Convert tears into downward blur or opacity contrast, gaze into negative-space pressure, and roof into low weight or diagonal pressure. Transcribe cloudform only when normalized DDL contains it**
- **Do not simply delete words that were not objectified. Preserve them as path, fade, density, rotation, preserve_space, or a faint color_cycle contrast. Tears/blurring should bias downward or vertical; pressing-down should become upper weight and downward pressure; gaze should become one-sided negative-space pressure. Transcribe placement and motion attached to a normalized cloudform**
- **Pressing down, shadow only, going ahead, tears, blur, unraveling, and fading are motion intents. Apply them as path, fade, rotation, rhythm_spacing, one-sided negative space, or a small focal contrast. Apply low-cloud intent to the normalized cloudform**
- **Vehicles such as bicycles, cars, and trains must not become wheels, frames, or bodies. Abstract them as shadows, diagonals, center of gravity, leading/lagging motion, or shifted negative space**
- **Reflection → sparse repeated line or arc with fade="directional" and path="wave" or "top_to_bottom"**
- **Soft light / sunlight → layered pale white or yellow-leaning ellipse, filled=true, preserving the original phrase in color_hint. Scent / fragrance → small green/white/gray ellipse or arc along path="wave". Buds / waiting to bloom → small red/white ellipses along a diagonal band. Five-sense presence / atmosphere → faint arc/ellipse with fade**
- **Use more for dots/stars/rain/snow/sand/particles, but do not default them to true circles. Prefer ellipse, square, or short line unless circle/round/moon/sun is explicit. Add rotation to ellipses and squares so they are not locked to horizontal/vertical symmetry**
- **Use only polygon for polygonal vocabulary, with sides=5-8. Use it only for crystals, minerals, hard shards, artificial hardness, or urban structure. Do not add separate pentagon/hexagon primitives**
- **Mountain / sharp peak → triangle is allowed. Do not objectify roof as a triangle; treat it as low weight, diagonal pressure, or upper density contrast. Leaf / petal / feather / paper fragment → use thin ellipse, rotated square, or small polygon so abstract natural/material forms survive until natural primitive plugins exist**
- **Playful or complex shapes should be local motifs made from 2-5 primitives, not a single primitive. Examples: leaf=thin ellipse + arc, paper shard=rotated square + thin line, seed pod=ellipse + small particles, mountain=triangle + a line cutting negative space, ripple=arc + small ellipse**

## Fill, background, and color

- **"Surface: flat"/fill/paint/solid fill → surface={"texture":"solid"}. "Surface: empty" and outline only = omit surface**
- **background → Score background field. "Fill background with black" → {"background":"black","instructions":[...]}. This sentence is not a request to fill an area with elements, so do not apply the density or count rules to it**
- **Do not create effectively invisible instructions whose drawing color matches the background. If they match, change the smaller visual area. Usually change line/small-shape/dot color to a context-fitting visible color such as black, white, blue, red, or green. Change the background only when the matching subject is large and dominant**
- **Choose the background from all nine abstract colors: white/black/gray/red/orange/yellow/green/blue/purple. If normalized DDL asks for a gray background, keep background="gray"**
- **A gray subject may be a foreground color="gray" or a background="gray". Do not build gray value-only drawings; combine gray with visible black, white, blue, red, or green foreground**
- **Specific color nuance (cherry-blossom pink, cinnabar red, cool blue-green, etc.) → keep color as nearest abstract color, and preserve the original short nuance in color_hint**
- **colorful/multi-color → arrangement color_cycle. e.g. ["red","blue","green","black","gray"]**
- **When the description names only one color, do not write a color_cycle. Put that color in color. The cycle hands one color to each member in turn, so a second color in it takes half the members -- a share the description did not ask for**
- **When explicit colors are sparse, choose the abstract colors by scene tone. Spring/flowers/warm light → red/green/white; water/night/cold air → blue/white/gray; forest/leaves/fragrance → green/white/gray; sunlight/harvest/metal/lamplight → yellow/orange; dusk/twilight/shadowed flowers → purple. Preserve unavailable nuance in color_hint. What you choose here is one color, not a cycle: never turn the listed candidates into a color_cycle**
- **Yellow, orange, and purple are peers of the other abstract colors. Choose them freely when the scene calls for them.**
- **Strong solid backgrounds (black/gray/red/orange/yellow/green/blue/purple) are allowed only when explicit or required by context such as night, flame, sign, or sea. If unsure, use white**

## Placement and focus

- **Normalized DDL must include placement words. If normalized DDL says "near the center", "top to bottom", "vertical", "right half", "radial", "concentric", "dotted across the whole canvas", or "undulating trace", prioritize that placement phrase**
- **"dotted across the whole canvas" / "finely across the whole canvas" may use layout=scatter, but treat it as all-over distribution, not disorder**
- **scatter is not uniform noise. Treat it as biased by density gradient, fading edges, diagonal band, right half, or top-to-bottom placement from the DDL**
- **"undulating trace" → arrangement.path="wave". "diagonal band" → path="diagonal". "right half" → path="right_half"**
- **"from top to bottom" / "vertical band" → layout="vertical", path="top_to_bottom". "left to right" / "horizontal" / "horizontal strata" → layout="horizontal", path="left_to_right". "radial" / "concentric" → layout="radial". "across the whole canvas" → layout="scatter"**
- **"central stillness" → at={"region":[0.42,0.42,0.58,0.58]}. Treat it as a narrow central region, not a fixed center coordinate**
- **"rhythm", "bounce", "dance", "canon-like offset", or "unraveling repetition" → use arrangement.rhythm_spacing without increasing count. playful/bouncing=syncopated, accelerating/flowing=accelerando, loose swaying=loose**
- **"upper-right golden-ratio position" → at={"region":[0.56,0.32,0.68,0.44]}. Lower-left uses at={"region":[0.32,0.56,0.44,0.68]}. Treat focus as a region, not a hard-coded coordinate**
- **"upper-left rule-of-thirds point" → at={"region":[0.273,0.273,0.393,0.393]}. "lower-right rule-of-thirds point" → at={"region":[0.607,0.607,0.727,0.727]}. Treat it as rule-of-thirds composition. Do not hard-code focus coordinates**
- **"lower-left silver-ratio position" → at={"region":[0.354,0.526,0.474,0.646]}. "upper-right silver-ratio position" → at={"region":[0.526,0.354,0.646,0.474]}. Treat it as silver-ratio spacing. Do not hard-code focus coordinates**
- **"upper-right focus" → at={"region":[0.60,0.18,0.82,0.40]}. "upper-left focus" → [0.18,0.18,0.40,0.40]. "lower-right focus" → [0.60,0.60,0.82,0.82]. "lower-left focus" → [0.18,0.60,0.40,0.82]. Do not hard-code focus coordinates**
- **"upper-edge focus" → at={"region":[0.39,0.07,0.61,0.29]}. "right-half focus" → at={"region":[0.61,0.39,0.83,0.61]}. Do not hard-code focus coordinates**

- **Use layout="grid" only for literal tiling instructions such as "tile", "tiled in a grid", or "cover the wall with a grid". Ordinary "line up", "scatter", or "all-over" does not imply grid**
- **A grid covers its requested region with cells: use at.region when present, otherwise the area inside margin. For a whole wall or whole canvas use margin=0.02–0.08 and never a margin above 0.12; use at.region, not a large margin, for a smaller region. Explicit rows/cols take priority as rows×cols; otherwise estimate rows and columns from count**
%%GRID_COUNT%%
- **grid jitter is a within-cell offset: 0=strict grid, 0.05–0.2=handmade variation, 0.2–0.5=uneven rain or wallpaper. Use rhythm_spacing for spacing rhythm**
- **For "four directions superimposed across the wall", emit at most four instructions, one grid per direction. Do not duplicate each direction into separate element instructions. Only here, explicit directional layers take priority over the one-dominant-technique compression rule**

## Mathematical, musical, and perspective composition

- **"regular pentagon vertices" → arrangement count=5 layout=radial. Treat it as a pentagonal balance layer**
- **Fibonacci-like counts such as thirteen and twenty-one are intentional; keep them as explicit counts**
- **Mathematical balance is not central symmetry. Use golden offset, rule-of-thirds, silver ratio, prime spacing, fibonacci count, and counterweight; balance the main focus with smaller elements on the opposite side**
- **"contrapuntal contrary motion" → a line layer moving against the main direction. Falling to the right uses rotation=30; rising to the right uses rotation=-30**
- **"harmonic overtone series" → an integer-ratio radial arc/circle layer. Keep the explicit count**
- **"canon offset" → repeated same shape with slight horizontal delay. Use layout=horizontal and the explicit count**
- **"one-point perspective" → thin guide lines toward the DDL focus. If the focus is upper right, use guide lines converging there**
- **"perspective depth" → repeated horizontal lines upward, preserving count**

## Materials and technique words

- **"value" / "light and shade" → black/gray/white contrast layers; blurring may express soft value transitions**
- **"drawing underlines" → fine-brush or pencil thin lines; preserve count**
- **"pointillism" → small square or ellipse scatter; avoid repeated true circles and add rotation to break axis symmetry**
- **"oil impasto" → short brush_thick line repetition**
- **"watercolor" → primarily ellipse with blurring, layered softly**
- **"patchwork" → square repetition; use color_cycle for multiple colors and add slight rotation to the pieces**
- **"fresco ground" → chalk gray horizontal lines or ground plane with blurring**
- **"ink-wash value" → black/gray brush lines with blurring or weight contrast**
- **English idiom and cultural texture are compositional signals, not objects. "syncopated city rhythm" / "blue-note value" → short line or arc rhythm with rhythm_spacing="syncopated"; "quilt-like patchwork" → rotated square color_cycle; "subway-map pressure" → rotring line convergence; "billboard edge pressure" → cropped rectangle/diagonal edge tension; "prairie horizon" → low horizontal negative-space pressure; "coastal fog plane" → pale watercolor ellipse layers with blurring; "warehouse grid cuts" → sparse rotated square/line grid fragments**

# Relations

- **"along the previous line" -> relation={"type":"along","gap":"narrow"}**
- **"not touching the previous shape" -> relation={"type":"not_touching","gap":"narrow"}. Use gap="wide" for wide separation**
- **"touching the previous line" / "touching the previous arc at both ends" -> relation={"type":"touching"}. Use only for explicit contact language; never add it spontaneously**
- **"cutting the previous line" -> relation={"type":"cutting","gap":"medium"}**
- **"between the previous two" -> relation={"type":"between","gap":"medium"}**
- Copy relation only when the normalized DDL literally contains one of these fixed phrases as an explicit previous-object relation. Do not infer relations. Natural-language-derived phrases such as "around", "same beat", "ahead/behind", "not touched", "near", or "far" are not relations. Do not attach relation to the first instruction.
- **Do not turn ordinary placement language into relation.** Phrases such as "along a diagonal band", "along an undulating trace", "along a path/edge/road/river", "riverbank", or "roadside" are arrangement/path/position, not relation.
- Before writing relation, verify that the immediately previous JSON instruction has an outline target: line has `from`+`to`, circle/arc/polygon has `center`+`radius`, ellipse has `center`+`size`, and square/triangle has `position`+`size`.
- Use `touching` only when both the current and immediately previous instruction are a line or arc. Never attach it to a closed or endpointless form.
- Relations may refer only to already emitted drawable outline instructions. Do not use background, filled planes, presence, fade-only support layers, small color-repair marks, or arrangement-only density layers as relation targets.
- **Use between only when the previous two JSON instructions both have outlines. If only one previous drawable exists, or if either previous item is a support layer, omit the relation.**
- Do not combine "along", "not touching", "touching", and "cutting" on one instruction. If several fixed phrases appear, keep only the one that is valid in output order.
- Generate at most one relation per fixed relation phrase. Do not replicate the same relation phrase into multiple instructions.
- If there is any doubt about order, target validity, or exact fixed-phrase match, omit the relation field. For fable/natural-language-derived DDL, use no relation by default. Express the relationship with position, path, rotation, and spacing instead; do not add a support instruction to rescue it.

# Examples (key patterns)

Input: Tile four hundred thin pencil vertical lines across the whole canvas. Trembling fine.
Output: {"instructions":[{"primitive":"line","from":[0.5,0.46],"to":[0.5,0.54],"color":"black","weight":"pencil","arrangement":{"count":400,"layout":"grid","rows":20,"cols":20,"jitter":0.15,"margin":0.04},"variation":{"amplitude":"fine","frequency":"high","quality":"perlin","dimensions":["position_x","position_y"]}}]}

Input: Tile thin solid lines in four directions across the whole canvas. Swaying faintly.
Output: {"instructions":[{"primitive":"line","from":[0.46,0.5],"to":[0.54,0.5],"color":"black","weight":"silverpoint","rotation":0,"arrangement":{"count":144,"layout":"grid","rows":12,"cols":12,"jitter":0.08,"margin":0.05},"variation":{"amplitude":"fine","frequency":"slow","quality":"wave","dimensions":["position_x","position_y"]}},{"primitive":"line","from":[0.46,0.5],"to":[0.54,0.5],"color":"black","weight":"silverpoint","rotation":90,"arrangement":{"count":144,"layout":"grid","rows":12,"cols":12,"jitter":0.08,"margin":0.05},"variation":{"amplitude":"fine","frequency":"slow","quality":"wave","dimensions":["position_x","position_y"]}},{"primitive":"line","from":[0.46,0.5],"to":[0.54,0.5],"color":"black","weight":"silverpoint","rotation":-45,"arrangement":{"count":144,"layout":"grid","rows":12,"cols":12,"jitter":0.08,"margin":0.05},"variation":{"amplitude":"fine","frequency":"slow","quality":"wave","dimensions":["position_x","position_y"]}},{"primitive":"line","from":[0.46,0.5],"to":[0.54,0.5],"color":"black","weight":"silverpoint","rotation":45,"arrangement":{"count":144,"layout":"grid","rows":12,"cols":12,"jitter":0.08,"margin":0.05},"variation":{"amplitude":"fine","frequency":"slow","quality":"wave","dimensions":["position_x","position_y"]}}]}

Input: Tile two hundred fifty-six small squares in a grid. Swaying slowly.
Output: {"instructions":[{"primitive":"square","position":[0.485,0.485],"size":[0.03,0.03],"color":"gray","rotation":12,"arrangement":{"count":256,"layout":"grid","rows":16,"cols":16,"jitter":0.15,"margin":0.04,"rhythm_spacing":"loose"},"variation":{"amplitude":"fine","frequency":"slow","quality":"wave","dimensions":["position_x","position_y","rotation"]}}]}

Input: Fill a gray circle with pale ink wash and let the edge bleed slightly.
Output: {"instructions":[{"primitive":"circle","center":[0.5,0.5],"radius":0.16,"color":"gray","filled":true,"surface":{"texture":"wash","density":0.3,"opacity":0.45,"bleed":0.2}}]}

Input: Place a black circle at the center. Surface: flat.
Output: {"instructions":[{"primitive":"circle","center":[0.5,0.5],"radius":0.18,"color":"black","surface":{"texture":"solid"}}]}

Input: Place one thin black line at center. Trembling faintly. Ground: off-white paper, fine paper grain.
Output: {"canvas":{"aspect":"square","ground":{"material":"paper","tone":"off_white","grain":"fine","density":0.2,"opacity":0.12}},"instructions":[{"primitive":"line","from":[0.5,0.3],"to":[0.5,0.7],"color":"black","weight":"pen","variation":{"amplitude":"fine","frequency":"medium","quality":"perlin","dimensions":["position_x"]}}]}

Input: Line up three vertical black lines horizontally. Ground: ink wash.
Output: {"canvas":{"aspect":"square","ground":{"material":"ink_wash","tone":"gray","density":0.25,"opacity":0.14}},"instructions":[{"primitive":"line","from":[0.5,0.0],"to":[0.5,1.0],"color":"black","arrangement":{"count":3,"layout":"horizontal"}}]}

Input: (when the support announced is pillar -- taller than wide, ratio 1:5) Place one thin black line at center.
Output: {"canvas":{"aspect":"pillar"},"instructions":[{"primitive":"line","from":[0.5,0.08],"to":[0.5,0.92],"color":"black","weight":"pen"}]}

Input: Line up three vertical solid lines horizontally.
Output: {"instructions":[{"primitive":"line","from":[0.5,0.0],"to":[0.5,1.0],"arrangement":{"count":3,"layout":"horizontal"}}]}

Input: Scatter five small blue ellipses rising to the right near the center. Make them wide.
Output: {"instructions":[{"primitive":"ellipse","center":[0.5,0.5],"size":[0.06,0.03],"color":"blue","rotation":-30,"arrangement":{"count":5,"layout":"scatter","margin":0.25}}]}

Input: Scatter six hundred ten small rotated white squares dotted across the whole canvas.
Output: {"instructions":[{"primitive":"square","position":[0.49,0.49],"size":[0.014,0.014],"color":"white","rotation":30,"arrangement":{"count":110,"layout":"scatter","density":"high","cluster_count":9,"fade":"outward","preserve_space":true,"margin":0.2}}]}

Input: Scatter one hundred thirty-seven short white lines from top to bottom. Swaying slowly.
Output: {"instructions":[{"primitive":"line","from":[0.48,0.5],"to":[0.52,0.5],"color":"white","arrangement":{"count":137,"layout":"vertical","path":"top_to_bottom","density":"medium","cluster_count":5,"fade":"directional","preserve_space":true},"variation":{"amplitude":"medium","frequency":"slow","quality":"wave","dimensions":["position_x","position_y"]}}]}

Input: Draw three hundred trembling green pen lines from top to bottom.
Output: {"instructions":[{"primitive":"line","from":[0.5,0.0],"to":[0.5,1.0],"color":"green","arrangement":{"count":110,"layout":"vertical","path":"top_to_bottom","density":"high","cluster_count":7,"fade":"directional","preserve_space":true},"variation":{"amplitude":"fine","frequency":"medium","quality":"perlin","dimensions":["position_x","position_y"]}}]}

Input: Scatter twenty small red ellipses rising to the right vertically in the right half.
Output: {"instructions":[{"primitive":"ellipse","center":[0.75,0.5],"size":[0.055,0.028],"color":"red","rotation":-30,"arrangement":{"count":20,"layout":"vertical","path":"right_half","margin":0.1}}]}

Input: Place one small white circle at the upper-right golden-ratio position. Radius 0.025.
Output: {"instructions":[{"primitive":"circle","at":{"region":[0.56,0.32,0.68,0.44]},"radius":0.025,"color":"white"}]}

Input: Place one small white circle at the upper-left rule-of-thirds point. Radius 0.018.
Output: {"instructions":[{"primitive":"circle","at":{"region":[0.273,0.273,0.393,0.393]},"radius":0.018,"color":"white"}]}

Input: Place one small white circle at the lower-left silver-ratio position. Radius 0.016.
Output: {"instructions":[{"primitive":"circle","at":{"region":[0.354,0.526,0.474,0.646]},"radius":0.016,"color":"white"}]}

Input: Place a black circle at the upper-right focus.
Output: {"instructions":[{"primitive":"circle","at":{"region":[0.60,0.18,0.82,0.40]},"radius":0.1,"color":"black"}]}

Input: Line up five small red circles on regular pentagon vertices. Radius 0.022.
Output: {"instructions":[{"primitive":"circle","center":[0.5,0.5],"radius":0.022,"color":"red","arrangement":{"count":5,"layout":"radial"}}]}

Input: Scatter twenty-one small red ellipses along an undulating trace. Swaying slowly.
Output: {"instructions":[{"primitive":"ellipse","center":[0.5,0.5],"size":[0.045,0.022],"color":"red","rotation":30,"arrangement":{"count":21,"layout":"scatter","path":"wave","margin":0.12},"variation":{"amplitude":"medium","frequency":"slow","quality":"wave","dimensions":["position_x","position_y"]}}]}

Input: Line up three thin white lines falling to the right as contrapuntal contrary motion. Fine trembling.
Output: {"instructions":[{"primitive":"line","from":[0.25,0.5],"to":[0.75,0.5],"color":"white","rotation":30,"arrangement":{"count":3,"layout":"vertical"},"variation":{"amplitude":"fine","frequency":"medium","quality":"perlin","dimensions":["position_y"]}}]}

Input: Line up four thin white arcs from a lower-right focus as a harmonic overtone series. Radius 0.07.
Output: {"instructions":[{"primitive":"arc","center":[0.72,0.68],"radius":0.07,"angle_start":0,"angle_end":180,"color":"white","arrangement":{"count":4,"layout":"radial","radius":0.18}}]}

Input: Line up seven short red lines left to right as a canon offset. Swaying slowly.
Output: {"instructions":[{"primitive":"line","from":[0.48,0.5],"to":[0.52,0.5],"color":"red","arrangement":{"count":7,"layout":"horizontal"},"variation":{"amplitude":"medium","frequency":"slow","quality":"wave","dimensions":["position_x","position_y"]}}]}

Input: Draw eight thin white lines toward an upper-right focus as one-point perspective.
Output: {"instructions":[{"primitive":"line","from":[0.12,0.85],"to":[0.78,0.28],"color":"white","arrangement":{"count":8,"layout":"vertical","margin":0.08}}]}

Input: Scatter thirty-four small rotated red squares dotted across the whole canvas as pointillism.
Output: {"instructions":[{"primitive":"square","position":[0.497,0.497],"size":[0.006,0.006],"color":"red","rotation":30,"arrangement":{"count":34,"layout":"scatter"}}]}

Input: Line up seven short red thick-brush lines horizontally as oil impasto.
Output: {"instructions":[{"primitive":"line","from":[0.35,0.5],"to":[0.65,0.5],"color":"red","weight":"brush_thick","arrangement":{"count":7,"layout":"vertical"}}]}

Input: Layer three pale watercolor ellipses rising to the right in the upper left. Edges blurring.
Output: {"instructions":[{"primitive":"ellipse","center":[0.32,0.28],"size":[0.24,0.14],"color":"white","rotation":-15,"arrangement":{"count":3,"layout":"scatter","margin":0.18},"variation":{"amplitude":"medium","frequency":"slow","quality":"pink","dimensions":["position_x","position_y"]}}]}

Input: Line up sixteen small rotated squares in red, blue, green, gray as patchwork grid.
Output: {"instructions":[{"primitive":"square","position":[0.45,0.45],"size":[0.08,0.08],"rotation":15,"arrangement":{"count":16,"layout":"scatter","margin":0.18,"color_cycle":["red","blue","green","gray"]}}]}

Input: Line up five black fine-brush vertical lines left to right as ink-wash value. Edges blurring.
Output: {"instructions":[{"primitive":"line","from":[0.5,0.2],"to":[0.5,0.8],"color":"black","weight":"brush_thin","arrangement":{"count":5,"layout":"horizontal"},"variation":{"amplitude":"medium","frequency":"slow","quality":"pink","dimensions":["position_x"]}}]}

Input: Line up seven short blue fine-brush lines left to right as syncopated city rhythm. Swaying slowly.
Output: {"instructions":[{"primitive":"line","from":[0.47,0.5],"to":[0.53,0.5],"color":"blue","weight":"brush_thin","arrangement":{"count":7,"layout":"horizontal","rhythm_spacing":"syncopated"},"variation":{"amplitude":"medium","frequency":"slow","quality":"wave","dimensions":["position_x","position_y"]}}]}


Input: Place one green arc. Place another arc touching the previous arc at both ends.
Output: {"instructions":[{"primitive":"arc","center":[0.50,0.47],"radius":0.0833,"angle_start":-143.13,"angle_end":-36.87,"color":"green"},{"primitive":"arc","center":[0.50,0.53],"radius":0.0833,"angle_start":143.13,"angle_end":36.87,"color":"green","relation":{"type":"touching"}}]}

Input: Draw one black line. Place a red line touching the previous line.
Output: {"instructions":[{"primitive":"line","from":[0.20,0.50],"to":[0.80,0.50],"color":"black"},{"primitive":"line","from":[0.30,0.40],"to":[0.70,0.40],"color":"red","relation":{"type":"touching"}}]}

Input: Place one green arc at each of two separate vertical positions.
Output: {"instructions":[{"primitive":"arc","center":[0.50,0.38],"radius":0.10,"angle_start":200,"angle_end":340,"color":"green"},{"primitive":"arc","center":[0.50,0.62],"radius":0.10,"angle_start":20,"angle_end":160,"color":"green"}]}

Input: Draw one black horizontal line. Place three small red ellipses along the previous line.
Output: {"instructions":[{"primitive":"line","from":[0.12,0.5],"to":[0.88,0.5],"color":"black"},{"primitive":"ellipse","center":[0.5,0.5],"size":[0.04,0.02],"color":"red","arrangement":{"count":3,"layout":"horizontal"},"relation":{"type":"along","gap":"narrow"}}]}

Input: Place one small blue circle. Place one small white square between the previous two.
Output: {"instructions":[{"primitive":"circle","center":[0.42,0.5],"radius":0.04,"color":"blue"},{"primitive":"square","position":[0.55,0.47],"size":[0.06,0.06],"color":"white"}]}

Input: Draw one black line at each of two different vertical positions. Place a small red circle between the previous two.
Output: {"instructions":[{"primitive":"line","from":[0.18,0.36],"to":[0.55,0.36],"color":"black"},{"primitive":"line","from":[0.45,0.64],"to":[0.82,0.64],"color":"black"},{"primitive":"circle","center":[0.5,0.5],"radius":0.035,"color":"red","relation":{"type":"between","gap":"medium"}}]}

Input: Draw one black horizontal line. Place one small red circle along the previous line. Place one small blue square along the previous line.
Output: {"instructions":[{"primitive":"line","from":[0.12,0.5],"to":[0.88,0.5],"color":"black"},{"primitive":"circle","center":[0.5,0.42],"radius":0.035,"color":"red","relation":{"type":"along","gap":"narrow"}},{"primitive":"square","position":[0.5,0.58],"size":[0.06,0.06],"color":"blue"}]}

Input: Draw five thin rotring lines toward an upper-right focus as subway-map pressure.
Output: {"instructions":[{"primitive":"line","from":[0.14,0.82],"to":[0.72,0.28],"color":"black","weight":"rotring","arrangement":{"count":5,"layout":"vertical","margin":0.08}}]}

Input: Draw one long pale horizontal line near the lower third as prairie horizon.
Output: {"instructions":[{"primitive":"line","from":[0.06,0.66],"to":[0.94,0.66],"color":"gray","weight":"pencil","color_hint":"prairie horizon"}]}

Input: Draw a horizontal line at center. Fine trembling.
Output: {"instructions":[{"primitive":"line","from":[0.0,0.5],"to":[1.0,0.5],"variation":{"amplitude":"fine","frequency":"medium","quality":"perlin","dimensions":["position_y"]}}]}

Input: Place a green square of side 0.4 at center.
Output: {"instructions":[{"primitive":"square","position":[0.3,0.3],"size":[0.4,0.4],"color":"green"}]}

Input: Place a filled red circle at center. Radius 0.2.
Output: {"instructions":[{"primitive":"circle","center":[0.5,0.5],"radius":0.2,"color":"red","surface":{"texture":"solid"}}]}

Input: Place a small cherry-blossom pink circle at center. Radius 0.1.
Output: {"instructions":[{"primitive":"circle","center":[0.5,0.5],"radius":0.1,"color":"red","color_hint":"cherry-blossom pink"}]}

Input: Fill background with black. Draw a white horizontal line at center.
Output: {"background":"black","instructions":[{"primitive":"line","from":[0.0,0.5],"to":[1.0,0.5],"color":"white"}]}

Input: Fill background with white. Draw a white horizontal line at center.
Output: {"background":"white","instructions":[{"primitive":"line","from":[0.0,0.5],"to":[1.0,0.5],"color":"black","color_hint":"white line made visible"}]}

Input: Draw one gray line rising from the bottom-left to the upper-right.
Output: {"instructions":[{"primitive":"line","from":[0.15,0.78],"to":[0.78,0.28],"color":"gray","arrangement":{"count":1,"layout":"scatter","density":"low","fade":"outward","preserve_space":true}}]}

Input: Fill background with white. Scatter one hundred thirty-seven short white lines from top to bottom.
Output: {"background":"white","instructions":[{"primitive":"line","from":[0.48,0.5],"to":[0.52,0.5],"color":"blue","color_hint":"white lines made visible on the smaller area","arrangement":{"count":137,"layout":"vertical","path":"top_to_bottom","density":"medium","cluster_count":5,"fade":"directional","preserve_space":true}}]}

Input: Fill background with white. Place a large white circle near the top edge. Radius 0.15.
Output: {"background":"blue","instructions":[{"primitive":"circle","center":[0.5,0.18],"radius":0.15,"color":"white"}]}

Input: Arrange eight circles radially in red, blue, green, black.
Output: {"instructions":[{"primitive":"circle","center":[0.5,0.5],"radius":0.05,"arrangement":{"count":8,"layout":"radial","color_cycle":["red","blue","green","black","gray","red","blue","green"]}}]}

Input: A transparent membrane wraps faint reflections at a rainy bus stop.
Output: {"instructions":[{"primitive":"ellipse","center":[0.58,0.46],"size":[0.46,0.18],"color":"blue","filled":true,"color_hint":"transparent membrane","arrangement":{"count":5,"layout":"scatter","density":"low","cluster_count":3,"fade":"outward","preserve_space":true,"margin":0.24},"variation":{"amplitude":"medium","frequency":"slow","quality":"pink","dimensions":["position_x","position_y"]}},{"primitive":"line","from":[0.35,0.22],"to":[0.72,0.78],"color":"white","color_hint":"rain reflection","arrangement":{"count":9,"layout":"vertical","path":"wave","density":"low","fade":"directional","preserve_space":true,"margin":0.18}}]}

Input: At a rainy bus stop, the presence of a waiting person becomes a transparent membrane.
Output: {"presence":{"kind":"figure_like","intensity":"low","center":[0.56,0.52],"symmetry":"none","gaze_pressure":"none","contour_density":"low"},"instructions":[{"primitive":"ellipse","center":[0.56,0.52],"size":[0.42,0.16],"color":"blue","filled":true,"color_hint":"transparent membrane","arrangement":{"count":4,"layout":"scatter","density":"low","fade":"outward","preserve_space":true,"margin":0.24},"variation":{"amplitude":"medium","frequency":"slow","quality":"pink","dimensions":["position_x","position_y"]}}]}

Input: Soft light and daphne fragrance surround cherry buds waiting to bloom.
Output: {"instructions":[{"primitive":"ellipse","center":[0.48,0.20],"size":[0.42,0.12],"color":"white","filled":true,"color_hint":"soft light","arrangement":{"count":3,"layout":"horizontal","density":"low","fade":"outward","preserve_space":true,"margin":0.24},"variation":{"amplitude":"medium","frequency":"slow","quality":"pink","dimensions":["position_x","position_y"]}},{"primitive":"ellipse","center":[0.56,0.55],"size":[0.045,0.022],"color":"green","rotation":-18,"color_hint":"daphne fragrance","arrangement":{"count":7,"layout":"scatter","path":"wave","density":"low","fade":"directional","preserve_space":true,"margin":0.24}},{"primitive":"ellipse","center":[0.70,0.62],"size":[0.055,0.026],"color":"red","rotation":-30,"color_hint":"waiting buds","arrangement":{"count":5,"layout":"scatter","path":"diagonal","margin":0.18}}]}

# Proportions

- **tall rectangle** → size[1] ≈ twice size[0]. e.g. size=[0.15,0.35]
- **wide rectangle** → size[0] ≈ twice size[1]. e.g. size=[0.35,0.15]
- **full-width line** → from=[0.0,y] to=[1.0,y]
- **half-width line** → from=[0.25,y] to=[0.75,y]
- **semicircle** → arc, angle_start=0, angle_end=180
- **waxing** → arc, angle_start=270, angle_end=90
- **waning** → arc, angle_start=90, angle_end=270
- **crescent** → arc, angle_start=210, angle_end=330
- **horizontal** → rotation=0. For line, use from=[0.0,y], to=[1.0,y]
- **vertical** → rotation=90. For line, use from=[x,0.0], to=[x,1.0]
- **diagonal** → rotation=45
- **rising** → rotation=-30
- **falling** → rotation=30
- **rotated** → rotation=30, unless an explicit angle is given

Input: Place a tall rectangle at center.
Output: {"instructions":[{"primitive":"square","position":[0.425,0.325],"size":[0.15,0.35]}]}

# Thinness → thinness (required)

When the normalized DDL contains a thinness word, always set the thinness field. Omission is forbidden.
When there is no thinness word, omit thinness (the tool draws at its default width).

| thinness word | thinness value |
|---|---|
| thin / fine line / threadlike / hairlike | fine |
| extra fine / extremely thin / scratchlike | extra_fine |

A thinness word never changes weight. When both are present, write both.

Input: Draw an extra fine black line at center.
Output: {"instructions":[{"primitive":"line","from":[0.2,0.5],"to":[0.8,0.5],"thinness":"extra_fine"}]}

Input: Draw a thin pen horizontal line at center.
Output: {"instructions":[{"primitive":"line","from":[0.1,0.5],"to":[0.9,0.5],"weight":"pen","thinness":"fine"}]}

# Touches → weight (required)

When the normalized DDL contains a material word, always set the weight field. Omission is forbidden.

| material word | weight value |
|---|---|
| silverpoint | silverpoint |
| pencil | pencil |
| pen (default) | pen |
| rotring | rotring |
| crayon | crayon |
| chalk | chalk |
| fine-brush | brush_thin |
| thick-brush | brush_thick |
| burin | burin |
| drypoint | drypoint |
| computer (snaps to a grid, falls into steps, repeats without error) | computer |

Input: Place a wide gray cloudform in the upper half. Make it undulate slowly.
Output: {"instructions":[{"primitive":"cloudform","center":[0.5,0.3],"size":[0.72,0.22],"color":"gray","variation":{"amplitude":"medium","frequency":"slow","quality":"wave","dimensions":["radius"]}}]}

Input: Scatter seven small green cloudforms across the right half.
Output: {"instructions":[{"primitive":"cloudform","center":[0.75,0.5],"size":[0.1,0.08],"color":"green","arrangement":{"count":7,"layout":"scatter","path":"right_half"}}]}

Input: Ground: black mezzotint. Carve light from the dark ground (bright). Place one large white cloudform at center.
Output: {"canvas":{"aspect":"square","ground":{"material":"mezzotint","tone":"black"}},"instructions":[{"primitive":"cloudform","center":[0.5,0.5],"size":[0.52,0.36],"color":"white","mode":"carve","carve_depth":"bright"}]}

Input: Line up thirty vertical blue crayon lines horizontally.
Output: {"instructions":[{"primitive":"line","from":[0.5,0.0],"to":[0.5,1.0],"color":"blue","weight":"crayon","arrangement":{"count":30,"layout":"horizontal"}}]}

Input: Line up ten thin vertical pencil lines horizontally.
Output: {"instructions":[{"primitive":"line","from":[0.5,0.0],"to":[0.5,1.0],"weight":"pencil","arrangement":{"count":10,"layout":"horizontal"}}]}

Input: Place a white chalk circle at center. Edges blurring.
Output: {"instructions":[{"primitive":"circle","center":[0.5,0.5],"radius":0.1,"color":"white","weight":"chalk","variation":{"amplitude":"medium","frequency":"medium","quality":"pink","dimensions":["position_x","position_y"]}}]}

Input: Draw a dashed horizontal line at center.
Output: {"instructions":[{"primitive":"line","from":[0.3,0.5],"to":[0.7,0.5],"style":"dashed","weight":"pen"}]}

Input: Draw one diagonal burin line.
Output: {"instructions":[{"primitive":"line","from":[0.35,0.65],"to":[0.65,0.35],"weight":"burin"}]}

Input: Place a semicircle arc at center. Radius 0.2.
Output: {"instructions":[{"primitive":"arc","center":[0.5,0.5],"radius":0.2,"angle_start":180.0,"angle_end":360.0,"weight":"pen"}]}

Input: Draw a horizontal line. The line blurs largely.
Output: {"instructions":[{"primitive":"line","from":[0.2,0.5],"to":[0.8,0.5],"weight":"pen","variation":{"amplitude":"broad","frequency":"slow","quality":"pink","dimensions":["position_y"]}}]}

No explanation. Call submit_score only."""

# The prompts AT THE DEFAULTS. Everything that reads a module-level prompt --
# tests, the reference generators, the snapshot callers -- keeps reading the
# default configuration, which is what makes the frozen corpora stay per-code
# and not per-install. A request that has a stored setting builds its own.
SYSTEM_PROMPT = build_system_prompt("ja", DEFAULT_LIMITS)
SYSTEM_PROMPT_EN = build_system_prompt("en", DEFAULT_LIMITS)


def _count_node(node: dict[str, Any], limits: Limits) -> dict[str, Any]:
    """The count property with the effective ceiling, in pydantic's key order."""
    rebuilt: dict[str, Any] = {}
    for key, value in node.items():
        if key == "minimum":
            rebuilt["maximum"] = limits.schema_count_max
        rebuilt[key] = count_field_description(limits) if key == "description" else value
    if "maximum" not in rebuilt:
        rebuilt["maximum"] = limits.schema_count_max
    return rebuilt


def _score_tool_schema(limits: Limits | None = None) -> dict[str, Any]:
    schema = Score.model_json_schema()
    defs = schema.pop("$defs", {})
    # `count` carries the ceiling twice, and both copies travel to the model:
    # the numeric `maximum` and the description text. They used to come from a
    # static `le=2000` on the field, which no setting could reach. They are
    # written in here instead, from the effective limits.
    #
    # Key order is not cosmetic -- the declaration order reaches the LLM and
    # moves how often optional fields are carried (I-038), which is why the
    # digest does not sort. `maximum` is reinserted where pydantic put it, so
    # the default configuration produces byte-identical tool JSON.
    effective = limits if limits is not None else current_limits()
    arrangement = defs.get("Arrangement")
    if isinstance(arrangement, dict):
        properties = arrangement.get("properties")
        if isinstance(properties, dict) and isinstance(properties.get("count"), dict):
            properties["count"] = _count_node(properties["count"], effective)

    def inline(node: Any, seen: set[str] | None = None) -> Any:
        if seen is None:
            seen = set()
        if isinstance(node, dict):
            ref = node.get("$ref")
            if isinstance(ref, str) and ref.startswith("#/$defs/"):
                name = ref.removeprefix("#/$defs/")
                if name in seen:
                    return {k: inline(v, seen) for k, v in node.items() if k != "$ref"}
                target = deepcopy(defs.get(name, {}))
                merged = {**target, **{k: v for k, v in node.items() if k != "$ref"}}
                return inline(merged, seen | {name})
            return {k: inline(v, seen) for k, v in node.items() if k != "$defs"}
        if isinstance(node, list):
            return [inline(item, seen) for item in node]
        return node

    return inline(schema)


def _submit_tool() -> dict[str, Any]:
    return {
        "name": "submit_score",
        "description": "正規化DDLから導出した JSON Score を提出する。",
        "input_schema": _score_tool_schema(),
    }


def _prompt_digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def _stage2_prompt_digest(system_prompt: str) -> str:
    # 鍵を並べ替えない。宣言順は tool schema に並びごと LLM へ渡り、任意フィールドの
    # 搬送率を動かす (I-038)。`sort_keys=True` はその並びを潰すので、絵を動かす変更が
    # `history.stage2_prompt_digest` に残らなかった。
    tool_json = json.dumps(_submit_tool(), ensure_ascii=False)
    return _prompt_digest(system_prompt + "\n" + tool_json)


def _current_model_settings() -> dict:
    from . import db as _db

    return _db.get_model_settings()


_MOTION_OR_TEXTURE_TERMS = (
    "震える",
    "震え",
    "揺れる",
    "揺らぐ",
    "揺れ",
    "小刻み",
    "滲む",
    "にじむ",
    "太い",
    "細い",
    "trembling",
    "tremble",
    "swaying",
    "sway",
    "wobble",
    "wobbly",
    "blurring",
    "blurred",
    "thick",
    "thin",
)

_PRIMITIVE_TERMS = {
    "line": ("直線", "線", "縦線", "横線", "line", "lines"),
    "circle": ("円", "丸", "circle", "circles"),
    "ellipse": ("楕円", "ellipse", "ellipses", "oval", "ovals"),
    "triangle": ("三角", "triangle", "triangles"),
    "square": ("四角", "square", "squares"),
    "polygon": ("多角形", "polygon", "polygons"),
    "arc": ("弧", "arc", "arcs"),
}

_COLOR_TERMS = {
    "white": ("白", "white"),
    "black": ("黒", "black"),
    "blue": ("青", "blue"),
    "red": ("赤", "red"),
    "green": ("緑", "green"),
    "gray": ("灰", "グレー", "gray", "grey"),
}


# v1.92: relation 固定句の正は saijiki テーブル (saijiki.RELATIONS)。
_RELATION_LITERAL_MARKERS = relation_literal_markers()


def _literal_relation_types(ddl: str) -> set[str]:
    lower = ddl.lower()
    return {
        relation_type
        for relation_type, markers in _RELATION_LITERAL_MARKERS.items()
        if any(marker in ddl or marker in lower for marker in markers)
    }


def _mentioned_values(
    text: str, terms_by_value: dict[str, tuple[str, ...]]
) -> set[str]:
    haystack = text.lower()
    return {
        value
        for value, terms in terms_by_value.items()
        if any(term.lower() in haystack for term in terms)
    }


def _relation_contour_is_available(instruction: object) -> bool:
    primitive = getattr(instruction, "primitive", None)
    if primitive == "line":
        return instruction.from_ is not None and instruction.to is not None
    if primitive in {"circle", "arc", "polygon"}:
        return instruction.center is not None and instruction.radius is not None
    if primitive in {"ellipse", "cloudform"}:
        return instruction.center is not None and instruction.size is not None
    if primitive in {"square", "triangle"}:
        return instruction.position is not None and instruction.size is not None
    return False


def _enforce_cloudform_literal_delivery(score: Score, ddl: str) -> Score:
    """Transcribe explicit cloudform when Stage 2 replaced its closed shape."""

    normalized = unicodedata.normalize("NFKC", ddl)
    lower = normalized.lower()
    if "雲形" not in normalized and "cloudform" not in lower:
        return score
    if any(ins.primitive == "cloudform" for ins in score.instructions):
        return score

    data = score.model_dump(by_alias=True)
    candidates = list(enumerate(data["instructions"]))
    for _, item in candidates:
        if (
            item.get("primitive") == "ellipse"
            and item.get("center") is not None
            and item.get("size") is not None
        ):
            item["primitive"] = "cloudform"
            _logger.warning("explicit cloudform restored from Stage 2 ellipse omission")
            return Score.model_validate(data)
    for _, item in reversed(candidates):
        if (
            item.get("primitive") in {"square", "triangle"}
            and item.get("position") is not None
            and item.get("size") is not None
        ):
            position = item.pop("position")
            size = item["size"]
            item["primitive"] = "cloudform"
            item["center"] = [position[0] + size[0] / 2, position[1] + size[1] / 2]
            _logger.warning("explicit cloudform restored from Stage 2 closed-shape omission")
            return Score.model_validate(data)

    from .coerce import count_hint_from_ddl

    color = next(iter(_mentioned_values(normalized, _COLOR_TERMS)), "black")
    weight = "pen"
    for marker, value in (
        (("鉛筆", "pencil"), "pencil"),
        (("ロットリング", "rotring"), "rotring"),
        (("細筆", "fine-brush"), "brush_thin"),
        (("太筆", "thick-brush"), "brush_thick"),
    ):
        if any(term in normalized or term in lower for term in marker):
            weight = value
            break
    count = count_hint_from_ddl(normalized) or 1
    is_wide = any(term in normalized or term in lower for term in ("横長", "wide"))
    is_small = any(term in normalized or term in lower for term in ("小さ", "small"))
    center = [0.75, 0.5] if "右半分" in normalized or "right half" in lower else [0.5, 0.5]
    size = [0.72, 0.22] if is_wide else ([0.1, 0.08] if is_small else [0.34, 0.22])
    instruction = {
        "primitive": "cloudform",
        "center": center,
        "size": size,
        "color": color,
        "weight": weight,
    }
    if count > 1:
        instruction["arrangement"] = {
            "count": count,
            "layout": "scatter",
            "path": "right_half" if center[0] > 0.5 else "none",
        }
    data["instructions"].append(instruction)
    _logger.warning("explicit cloudform transcribed after complete Stage 2 omission")
    return Score.model_validate(data)


def _enforce_relation_literal_gate(score: Score, ddl: str) -> Score:
    """Keep only literal relations and transcribe one unambiguous omission."""

    allowed_types = _literal_relation_types(ddl)
    instructions = []
    changed = False
    for ins in score.instructions:
        if ins.relation is None or ins.relation.type in allowed_types:
            instructions.append(ins.model_dump(by_alias=True))
            continue
        data = ins.model_dump(by_alias=True)
        data.pop("relation", None)
        instructions.append(data)
        changed = True

    normalized = unicodedata.normalize("NFKC", ddl)
    lower = normalized.lower()
    explicit_cloudform = "雲形" in normalized or "cloudform" in lower
    if explicit_cloudform and len(allowed_types) == 1:
        cloud_index = next(
            (
                index
                for index, item in enumerate(instructions)
                if item.get("primitive") == "cloudform"
            ),
            None,
        )
        if cloud_index == 0:
            target_index = next(
                (
                    index
                    for index in range(1, len(score.instructions))
                    if _relation_contour_is_available(score.instructions[index])
                ),
                None,
            )
            if target_index is not None:
                cloud_item = instructions.pop(0)
                instructions.insert(target_index, cloud_item)
                score_data = score.model_dump(by_alias=True)
                score_data["instructions"] = instructions
                score = Score.model_validate(score_data)
                changed = True

    present_types = {
        relation["type"]
        for item in instructions
        if isinstance((relation := item.get("relation")), dict)
        and isinstance(relation.get("type"), str)
    }
    if len(allowed_types) == 1:
        relation_type = next(iter(allowed_types))
        if relation_type not in present_types:
            minimum_index = 2 if relation_type == "between" else 1
            for index in range(minimum_index, len(score.instructions)):
                if instructions[index].get("relation") is not None:
                    continue
                if not _relation_contour_is_available(score.instructions[index - 1]):
                    continue
                if relation_type == "between" and not _relation_contour_is_available(
                    score.instructions[index - 2]
                ):
                    continue
                if relation_type == "touching" and (
                    score.instructions[index].primitive not in {"line", "arc"}
                    or score.instructions[index - 1].primitive not in {"line", "arc"}
                ):
                    continue
                instructions[index]["relation"] = {
                    "type": relation_type,
                    **(
                        {}
                        if relation_type == "touching"
                        else {
                            "gap": "medium"
                            if relation_type in {"cutting", "between"}
                            else "narrow"
                        }
                    ),
                }
                changed = True
                break

    if not changed:
        return score
    data = score.model_dump(by_alias=True)
    data["instructions"] = instructions
    return Score.model_validate(data)


def _enforce_print_literal_transcription(score: Score, ddl: str) -> Score:
    """Transcribe exact mezzotint/carve phrases omitted by Stage 2."""

    normalized = unicodedata.normalize("NFKC", ddl)
    lower = normalized.lower()
    has_ground = "地: 黒いメゾチント地" in normalized or "ground: black mezzotint" in lower
    has_carve = "黒地から光を彫り出す" in normalized or "carve light from the dark ground" in lower
    if not has_ground and not has_carve:
        return score

    data = score.model_dump(by_alias=True)
    if has_ground:
        canvas = data.get("canvas", "square")
        aspect = canvas if isinstance(canvas, str) else canvas.get("aspect", "square")
        data["canvas"] = {
            "aspect": aspect,
            "ground": {"material": "mezzotint", "tone": "black"},
        }
    if has_ground and has_carve:
        depth = "bright" if "明るく" in normalized or "bright" in lower else "half"
        target = next(
            (item for item in data["instructions"] if item.get("primitive") == "cloudform"),
            None,
        )
        if target is not None:
            target["mode"] = "carve"
            target["carve_depth"] = depth
    return Score.model_validate(data)


def _enforce_ground_literal_gate(score: Score, ddl: str) -> Score:
    """Drop model-inferred canvas ground unless the DDL contains its exact marker."""

    normalized = unicodedata.normalize("NFKC", ddl)
    if "地:" in normalized or "ground:" in normalized.lower():
        return score
    if isinstance(score.canvas, str) or score.canvas.ground is None:
        return score

    data = score.model_dump(by_alias=True)
    data["canvas"] = score.canvas.aspect
    _logger.warning("canvas ground dropped by literal gate")
    return Score.model_validate(data)


def _enforce_print_literal_gate(score: Score, ddl: str) -> Score:
    """Printmaking fields are input-driven and invalid carve is drop-only."""
    normalized = unicodedata.normalize("NFKC", ddl)
    lower = normalized.lower()
    canvas = score.canvas
    dark_ground = (
        not isinstance(canvas, str)
        and canvas.ground is not None
        and (
            canvas.ground.material in {"mezzotint", "charcoal_ground"}
            or canvas.ground.tone == "black"
        )
    )
    data = score.model_dump(by_alias=True)
    changed = False
    if (
        not isinstance(canvas, str)
        and canvas.ground is not None
        and canvas.ground.material == "mezzotint"
        and "メゾチント" not in normalized
        and "mezzotint" not in lower
    ):
        data["canvas"] = canvas.aspect
        dark_ground = False
        changed = True
    for item in data["instructions"]:
        weight = item.get("weight")
        if weight == "burin" and "ビュラン" not in normalized and "burin" not in lower:
            item["weight"] = "pen"
            changed = True
        if (
            weight == "drypoint"
            and "ドライポイント" not in normalized
            and "drypoint" not in lower
        ):
            item["weight"] = "pen"
            changed = True
        surface = item.get("surface") or {}
        tokens = {
            "hatch": ("平行線", "hatch"),
            "crosshatch": ("交差線", "crosshatch"),
            "aquatint": ("アクアチント", "aquatint"),
        }.get(surface.get("texture"))
        if tokens and not any(
            token in normalized or token in lower for token in tokens
        ):
            item.pop("surface", None)
            changed = True
        if item.get("mode") == "carve" and (
            not dark_ground
            or not any(
                token in normalized or token in lower
                for token in ("彫り出す", "彫る", "carve light", "carve")
            )
        ):
            item["mode"] = "additive"
            item.pop("carve_depth", None)
            changed = True
    if changed:
        _logger.warning("printmaking fields dropped by literal gate")
        return Score.model_validate(data)
    return score


def _finalize_score(score: Score, ddl: str) -> Score:
    score = _enforce_modifier_targeting(score, ddl)
    score = _enforce_cloudform_literal_delivery(score, ddl)
    score = _enforce_relation_literal_gate(score, ddl)
    score = _enforce_print_literal_transcription(score, ddl)
    score = _enforce_ground_literal_gate(score, ddl)
    score = _enforce_print_literal_gate(score, ddl)
    return _enforce_explicit_region_instruction_count(score, ddl)


def _enforce_explicit_region_instruction_count(score: Score, ddl: str) -> Score:
    """Do not let Stage 2 add motifs to fully region-resolved core DDL.

    Each numeric region marks one already composed drawing clause. Prefer the
    instructions that retained those regions, then fall back to source order
    when a model converted the regions into direct coordinates.
    """

    region_count = len(
        re.findall(
            r"(?:領域|region)\s*\[\s*(?:0(?:\.\d+)?|1(?:\.0+)?)\s*,",
            unicodedata.normalize("NFKC", ddl),
            flags=re.IGNORECASE,
        )
    )
    if region_count == 0 or len(score.instructions) <= region_count:
        return score

    data = score.model_dump(by_alias=True)
    instructions = data["instructions"]
    region_anchored = [
        item
        for item in instructions
        if isinstance(item.get("at"), dict)
        and isinstance(item["at"].get("region"), (list, tuple))
        and len(item["at"]["region"]) == 4
    ]
    data["instructions"] = (
        region_anchored[:region_count]
        if len(region_anchored) >= region_count
        else instructions[:region_count]
    )
    _logger.warning(
        "Stage 2 support instructions dropped for %d explicit numeric regions",
        region_count,
    )
    return Score.model_validate(data)


def _enforce_modifier_targeting(score: Score, ddl: str) -> Score:
    """Keep motion/texture modifiers on the explicitly requested single motif.

    This is a Stage 2 contract guard, not the broader visual auto-repair pass.
    It only applies when the DDL names exactly one primitive family and includes
    a motion/texture modifier, because those modifiers should decorate the named
    primitive instead of creating unrequested support marks.
    """

    if not any(term.lower() in ddl.lower() for term in _MOTION_OR_TEXTURE_TERMS):
        return score
    target_primitives = _mentioned_values(ddl, _PRIMITIVE_TERMS)
    if len(target_primitives) != 1:
        return score
    target_colors = _mentioned_values(ddl, _COLOR_TERMS)
    target_primitive = next(iter(target_primitives))

    def matches_target(ins) -> bool:
        if ins.primitive != target_primitive:
            return False
        return not target_colors or ins.color in target_colors

    targeted = [ins for ins in score.instructions if matches_target(ins)]
    if not targeted:
        return score
    if len(targeted) == len(score.instructions) and all(
        ins.variation is not None for ins in targeted
    ):
        return score

    repaired = []
    for ins in targeted:
        if ins.variation is not None or target_primitive != "line":
            repaired.append(ins)
            continue
        repaired.append(
            ins.model_copy(
                update={
                    "variation": Variation(
                        amplitude="fine",
                        frequency="medium",
                        quality="perlin",
                        dimensions=["position_x", "position_y"],
                    )
                }
            )
        )

    data = score.model_dump()
    data["instructions"] = [ins.model_dump(by_alias=True) for ins in repaired]
    return Score.model_validate(data)


def compose(
    ddl: str,
    *,
    model: str | None = None,
    system_prompt: str | None = None,
    lang: str = "ja",
    trace_sink: list[dict] | None = None,
    prompt_metadata: dict[str, str] | None = None,
    limits: Limits = DEFAULT_LIMITS,
    canvas_aspect: str | None = None,
) -> tuple[Score, int | None, int | None]:
    """(score, tokens_in, tokens_out) を返す。system_prompt 指定時はスナップショット使用。

    trace_sink 指定時は、この呼び出しの Stage 2 生応答 {raw_text, parse_ok} を
    append する (観測のみ; retry/fallback の判定・挙動は変えない)。
    """
    # The DDL is the whole user message. It used to be prefixed with the
    # original text under a [原文] heading; the description-propagation cut
    # made the DDL the single route by which a description reaches Stage 2.
    user_msg = ddl
    if system_prompt is not None:
        effective_prompt = system_prompt
    else:
        # Built here, not read off the module constant: the limits the model is
        # told about must be the ones coerce will apply to its answer, and the
        # support it composes for must be the one the request asked for.
        effective_prompt = build_system_prompt(lang, limits, canvas_aspect)
    if prompt_metadata is not None:
        prompt_metadata["stage2_prompt_digest"] = _stage2_prompt_digest(effective_prompt)
    settings = _current_model_settings()
    if model:
        provider, model_id = provider_for_model(
            model, stage="stage2", settings=settings
        )
        if provider == "anthropic":
            score, tokens_in, tokens_out = _compose_anthropic(
                user_msg,
                model=model_id,
                system_prompt=effective_prompt,
                settings=settings,
                trace_sink=trace_sink,
            )
            return _finalize_score(score, ddl), tokens_in, tokens_out
        if provider == "gemini":
            score, tokens_in, tokens_out = _compose_gemini(
                user_msg,
                model=model_id,
                system_prompt=effective_prompt,
                settings=settings,
                trace_sink=trace_sink,
            )
            return _finalize_score(score, ddl), tokens_in, tokens_out
        score, tokens_in, tokens_out = _compose_openai(
            user_msg,
            model=model_id,
            provider=provider,
            system_prompt=effective_prompt,
            trace_sink=trace_sink,
        )
        return _finalize_score(score, ddl), tokens_in, tokens_out
    backend = os.getenv("INKU_LLM_BACKEND", "anthropic").lower()
    if backend == "openai":
        score, tokens_in, tokens_out = _compose_openai(
            user_msg, model=None, system_prompt=effective_prompt, trace_sink=trace_sink
        )
        return _finalize_score(score, ddl), tokens_in, tokens_out
    score, tokens_in, tokens_out = _compose_anthropic(
        user_msg, system_prompt=effective_prompt, trace_sink=trace_sink
    )
    return _finalize_score(score, ddl), tokens_in, tokens_out


def _record_stage2_raw(trace_sink: list[dict] | None, raw_text: str, parse_ok: bool) -> None:
    # Observation only (trace): record the Stage 2 model's raw response text and
    # whether it parsed. Never affects retry/fallback control flow.
    if trace_sink is not None:
        trace_sink.append({"raw_text": raw_text, "parse_ok": bool(parse_ok)})


def _score_from_model_output(data: object) -> Score:
    """Validate a Score a model wrote, without letting one constant throw it away.

    `version` is `Literal["0.1.0"]` with that same value as its default, and the
    tool schema does not require it: the model has nothing to say through this
    field, and the one legal value is already ours. A provider whose decoder is
    constrained cannot get it wrong, but Ollama Cloud ignores structured output
    in all three of its forms (measured 2026-07-27), so the model writes the
    field from the prompt and guesses -- `"1.0"`, every time it guessed.

    That guess cost the whole Score. Of the thirty-two Stage 2 runs measured on
    2026-07-29 across the eight cloud models the free tier can reach, **nine
    failed on this field and nothing else**, taking four models from "returns
    nothing usable" to a working Score once the key is dropped.

    Dropped rather than rewritten: rewriting would mean deciding the model meant
    0.1.0, and there is nothing to decide -- the field simply carries no
    information from a model. The default then supplies it.
    """
    if isinstance(data, dict) and "version" in data and data.get("version") != SCORE_VERSION:
        data = {key: value for key, value in data.items() if key != "version"}
    return Score.model_validate(data)


def _compose_anthropic(
    user_msg: str,
    *,
    model: str | None = None,
    system_prompt: str = SYSTEM_PROMPT,
    settings: dict | None = None,
    trace_sink: list[dict] | None = None,
) -> tuple[Score, int | None, int | None]:
    from anthropic import Anthropic

    connection = connection_for("anthropic", settings or _current_model_settings())
    kwargs = {"api_key": connection["api_key"]} if connection.get("api_key") else {}
    if connection.get("base_url"):
        kwargs["base_url"] = connection["base_url"]
    client = Anthropic(**kwargs)
    resp = client.messages.create(
        model=model or DEFAULT_ANTHROPIC_MODEL,
        max_tokens=MAX_TOKENS,
        system=system_prompt,
        tools=[_submit_tool()],
        tool_choice={"type": "tool", "name": "submit_score"},
        messages=[{"role": "user", "content": user_msg}],
    )
    tin = getattr(resp.usage, "input_tokens", None)
    tout = getattr(resp.usage, "output_tokens", None)
    for block in resp.content:
        if block.type == "tool_use" and block.name == "submit_score":
            raw_text = json.dumps(block.input, ensure_ascii=False, default=str)
            try:
                score = _score_from_model_output(block.input)
            except Exception:
                _record_stage2_raw(trace_sink, raw_text, False)
                raise
            _record_stage2_raw(trace_sink, raw_text, True)
            return score, tin, tout
    _record_stage2_raw(trace_sink, "", False)
    raise RuntimeError("Anthropic did not return submit_score tool call")


def _compose_gemini(
    user_msg: str,
    *,
    model: str,
    system_prompt: str = SYSTEM_PROMPT,
    settings: dict | None = None,
    trace_sink: list[dict] | None = None,
) -> tuple[Score, int | None, int | None]:
    connection = connection_for("gemini", settings or _current_model_settings())
    api_key = connection.get("api_key") or ""
    if not api_key:
        raise RuntimeError("Gemini API key is not configured")
    base_url = str(
        connection.get("base_url") or "https://generativelanguage.googleapis.com"
    ).rstrip("/")
    url = f"{base_url}/v1beta/models/{model}:generateContent?key={api_key}"
    body = {
        "systemInstruction": {"parts": [{"text": system_prompt}]},
        "contents": [{"role": "user", "parts": [{"text": user_msg}]}],
        "generationConfig": {
            "temperature": 0.0,
            "maxOutputTokens": MAX_TOKENS,
            "responseMimeType": "application/json",
        },
    }
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(
        request, timeout=float(os.getenv("INKU_LLM_REQUEST_TIMEOUT_SECONDS", "120"))
    ) as response:
        payload = json.loads(response.read().decode("utf-8"))
    parts = payload.get("candidates", [{}])[0].get("content", {}).get("parts", [])
    text_out = "\n".join(str(part.get("text", "")) for part in parts).strip()
    usage = payload.get("usageMetadata", {})
    try:
        score = _score_from_model_output(_extract_json(text_out))
    except Exception:
        _record_stage2_raw(trace_sink, text_out, False)
        raise
    _record_stage2_raw(trace_sink, text_out, True)
    return score, usage.get("promptTokenCount"), usage.get("candidatesTokenCount")


def _compose_openai(
    user_msg: str,
    *,
    model: str | None = None,
    provider: str | None = None,
    system_prompt: str = SYSTEM_PROMPT,
    trace_sink: list[dict] | None = None,
) -> tuple[Score, int | None, int | None]:
    from openai import OpenAI

    settings = _current_model_settings()
    if model is None:
        provider, model = provider_for_model(None, stage="stage2", settings=settings)
    provider = (
        provider or provider_for_model(model, stage="stage2", settings=settings)[0]
    )
    connection = connection_for(provider, settings)
    base_url = connection["base_url"]
    api_key = connection.get("api_key") or "none"

    timeout = float(os.getenv("INKU_LLM_REQUEST_TIMEOUT_SECONDS", "120"))
    client = OpenAI(base_url=base_url, api_key=api_key, timeout=timeout, max_retries=0)

    # A tool definition travels inside the prompt, and the Score schema is large
    # enough to push the request past the context window: with the 28k-character
    # system prompt, local Ollama reported 8,194 prompt tokens against 12,195 for
    # the same messages without tools -- a longer prompt counting fewer tokens,
    # because three quarters of it had been dropped to make room (measured
    # 2026-07-28, Ollama 0.32.4, 16384 context). `response_format` constrains the
    # decoder instead of the prompt, costs no tokens, and leaves the prompt whole.
    #
    # Ollama Cloud ignores every form of structured output but honours tool calling
    # (measured 2026-07-27), so that provider stays on tools. The remaining
    # OpenAI-compatible providers are unmeasured here and keep the tool path.
    #
    # `reasoning_effort` is the other half: Ollama turns thinking on by itself when
    # the argument is absent, and thinking shares MAX_TOKENS with the answer, so a
    # model that thinks past the budget returns nothing. Suppressing it ran the same
    # eight cases 8x faster, recovered the one that had been coming back empty, and
    # left coverage identical (measured 2026-07-28).
    #
    # The cloud used to be left out of this, on the grounds that its models emitted
    # no thinking either way. That was one model's behaviour read as the provider's:
    # gemma4:31b was the only cloud model measured on 2026-07-27. Asked the same
    # trivial question at three budgets on 2026-07-29, the eight cloud models the
    # free tier can reach answered 2/8 at sixteen tokens, 7/8 at 1024, and 8/8 only
    # once thinking was suppressed -- minimax-m3 needs the suppression to reach an
    # answer at all. Over four Stage 2 runs each, suppression took the clean total
    # from 6 to 9 and cut empty responses from 15 to 6.
    #
    # The other half of that old note holds: suppression can cost the tool call
    # (gpt-oss:20b loses it and returns nothing). It was kept anyway, because the
    # models it rescues outnumber the one it breaks, and gpt-oss:20b's Score was
    # already invalid without it.
    if provider == "ollama":
        structured: dict = {
            "reasoning_effort": "none",
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "submit_score",
                    "schema": _score_tool_schema(),
                    "strict": True,
                },
            },
        }
    else:
        structured = {
            "tools": [
                {
                    "type": "function",
                    "function": {
                        "name": "submit_score",
                        "description": "正規化DDLから導出した JSON Score を提出する。",
                        "parameters": _score_tool_schema(),
                    },
                }
            ],
            "tool_choice": {"type": "function", "function": {"name": "submit_score"}},
        }
        # The cloud keeps tools and gains only the suppression. The two settings are
        # separable: one chooses how the answer is shaped, the other whether the
        # model spends the budget before writing it.
        if provider == "ollama-cloud":
            structured["reasoning_effort"] = "none"

    with provider_slot(provider):
        resp = call_with_llm_retry(
            lambda: client.chat.completions.create(
                model=model,
                max_tokens=MAX_TOKENS,
                temperature=0.0,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_msg},
                ],
                stream=False,
                **structured,
            )
        )
    usage = resp.usage
    tin: int | None = getattr(usage, "prompt_tokens", None)
    tout: int | None = getattr(usage, "completion_tokens", None)

    msg = resp.choices[0].message
    if msg.tool_calls:
        args = msg.tool_calls[0].function.arguments
        try:
            score = _score_from_model_output(json.loads(args))
        except Exception:
            _record_stage2_raw(trace_sink, args, False)
            raise
        _record_stage2_raw(trace_sink, args, True)
        return score, tin, tout

    text = (msg.content or "").strip()
    args = _extract_tool_call_args(text)
    if args is not None:
        try:
            score = _score_from_model_output(args)
        except Exception:
            _record_stage2_raw(trace_sink, text, False)
            raise
        _record_stage2_raw(trace_sink, text, True)
        return score, tin, tout

    try:
        score = _score_from_model_output(_extract_json(text))
    except Exception:
        _record_stage2_raw(trace_sink, text, False)
        raise
    _record_stage2_raw(trace_sink, text, True)
    return score, tin, tout


def _extract_tool_call_args(text: str) -> dict | None:
    """Tool call の arguments 部を各モデル方言から抽出する。

    対応する形式:
    - Qwen2.5: `<tool_call>{"name":"X","arguments":{...}}</tool_call>`
    - Gemma 3: ```json {"tool_calls":[{"name":"X","arguments":{...}}]} ```
    - その他: 裸の {"instructions":[...]} (Score 直接)
    """
    m = re.search(r"<tool_call>\s*(\{.*?\})\s*</tool_call>", text, re.DOTALL)
    if m:
        try:
            payload = json.loads(m.group(1))
            return payload.get("arguments", payload)
        except json.JSONDecodeError:
            pass

    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if m:
        try:
            payload = json.loads(m.group(1))
            if isinstance(payload, dict):
                tcs = payload.get("tool_calls")
                if isinstance(tcs, list) and tcs:
                    args = tcs[0].get("arguments") or tcs[0].get("parameters")
                    if isinstance(args, dict):
                        return args
                if "arguments" in payload and isinstance(payload["arguments"], dict):
                    return payload["arguments"]
                if "instructions" in payload:
                    return payload
        except json.JSONDecodeError:
            pass

    return None


def _extract_json(text: str) -> dict:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if m:
        return json.loads(m.group(1))

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return json.loads(text[start : end + 1])

    raise ValueError(f"Could not extract JSON from response: {text[:500]}")
