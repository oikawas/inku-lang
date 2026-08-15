"""engine 15 段 2: 地の texture seed は支持体の同一性だけから作る。

engine 14 までの `_texture_seed` は Score 全体の dump をハッシュしていたため、
地と無関係な変更 — instruction の色注記や、描画に一度も読まれない
`ground.absorbency` — が地の粒配置を動かしていた。本版では

    seed = f(material, grain, render_seed)

とする。地の seed が決めているのは「どの紙か」であって「どれだけ濃いか」では
ないので、`opacity` を上げたときは同じ紙が濃くなり、別の紙に差し替わらない。

コーパスの digest は SVG 全体なので instruction を変えれば当然変わる。ここでは
地の層 `<g id="layer_01_canvas_ground">` だけを取り出して比べる。
"""

import re

import pytest
from pydantic import ValidationError

from inku_server.renderer import render
from inku_server.schema import CanvasGroundSpec, Score

GROUND_LAYER_ID = "layer_01_canvas_ground"
RENDER_SEED = 12345

BASE_GROUND: dict = {
    "material": "paper",
    "tone": "off_white",
    "grain": "medium",
    "density": 0.45,
    "opacity": 0.16,
    "seed": None,
}
BASE_INSTRUCTION: dict = {
    "primitive": "line",
    "from": [0.18, 0.50],
    "to": [0.82, 0.50],
    "weight": "pen",
}


def _score(ground: dict, **instruction_changes) -> Score:
    return Score.model_validate(
        {
            "canvas": {"aspect": "square", "ground": ground},
            "background": "white",
            "instructions": [{**BASE_INSTRUCTION, **instruction_changes}],
        }
    )


_PATTERN = re.compile(r'<pattern id="gp\d+".*?</pattern>', re.S)
_GRADIENT = re.compile(
    r'<(?:linear|radial)Gradient id="gg\d+".*?</(?:linear|radial)Gradient>', re.S
)


def _ground_layer(score: Score, *, render_seed: int | None = RENDER_SEED) -> str:
    """地の層だけを取り出す。

    ⚠ engine 34 で地は `<pattern>` になった。**タイルの中身は `<defs>` にあり、
    層のグループに残るのはそれを塗る矩形だけである。**グループだけを見ていた
    ころの抽出のままだと、粒がどう動いてもこのファイルの全検査が一致してしまう
    (実測: `grain` を変えても `density` を上げても層は完全一致した)。定義と
    グループの両方を取る。

    profile は 3 つとも同じものを出すので、どれで演奏しても同じ文字列になる。
    """
    svg = render(score, svg_profile="editable", render_seed=render_seed)
    start = svg.index(f'<g id="{GROUND_LAYER_ID}"')
    end = svg.index("</g>", start) + len("</g>")
    return (
        svg[start:end]
        + "".join(_GRADIENT.findall(svg))
        + "".join(_PATTERN.findall(svg))
    )


def _without_opacity(layer: str) -> str:
    return re.sub(r'\s(?:stroke-)?opacity="[^"]*"', "", layer)


def _ground(**changes) -> dict:
    return {**BASE_GROUND, **changes}


# --- P-1〜P-3: 地と無関係なものが地を動かさない -----------------------------


def test_p1_instruction_color_hint_does_not_move_the_ground() -> None:
    """P-1 (陽性): coerce の痕跡文字列を書き込んでも地の層は完全一致する。"""
    plain = _ground_layer(_score(_ground()))
    annotated = _ground_layer(
        _score(_ground(), color_hint="material inferred from ddl: rotring")
    )
    assert plain == annotated


def test_p2_absorbency_value_does_not_move_the_ground() -> None:
    """P-2 (陽性): 保存済み Score の `absorbency` の値は地を動かさない。"""
    low = _ground_layer(_score(_ground(absorbency=0.25)))
    high = _ground_layer(_score(_ground(absorbency=0.85)))
    assert low == high


def test_p3_absorbency_absence_does_not_move_the_ground() -> None:
    """P-3 (陽性): `absorbency` を持つ Score と持たない Score の地が一致する。"""
    with_field = _ground_layer(_score(_ground(absorbency=0.25)))
    without_field = _ground_layer(_score(_ground()))
    assert with_field == without_field


# --- P-4〜P-6: 支持体の同一性は確かに読まれている ---------------------------


def test_p4_grain_moves_the_ground() -> None:
    """P-4 (陰性): 紙目を変えたら別の紙になる。"""
    medium = _ground_layer(_score(_ground(grain="medium")))
    coarse = _ground_layer(_score(_ground(grain="coarse")))
    assert medium != coarse


def test_p5_material_moves_the_ground() -> None:
    """P-5 (陰性): paper と washi は同じ描画分岐に落ちるが、種は別である。

    材質が seed に入っていることの宣言。分岐が同じなので、ここが一致してしまう
    実装は `material` を読んでいない。
    """
    paper = _ground_layer(_score(_ground(material="paper")))
    washi = _ground_layer(_score(_ground(material="washi")))
    assert paper != washi


def test_p6_render_seed_moves_the_ground() -> None:
    """P-6 (陰性): 演奏 seed を変えたら地も引き直される。"""
    first = _ground_layer(_score(_ground()), render_seed=12345)
    second = _ground_layer(_score(_ground()), render_seed=98765)
    assert first != second


# --- P-7: 同じ紙が濃くなる (B2 の核) ---------------------------------------


def test_p7_opacity_changes_only_the_opacity() -> None:
    """P-7 (恒等): `opacity` だけを変えたとき、粒の位置は一致し濃さだけ変わる。"""
    thin = _ground_layer(_score(_ground(opacity=0.16)))
    thick = _ground_layer(_score(_ground(opacity=0.42)))
    assert thin != thick, "opacity は描画に読まれているので層は一致しない"
    assert _without_opacity(thin) == _without_opacity(thick)


def test_p7b_density_keeps_the_leading_grains() -> None:
    """P-7 の系: `density` を上げても先頭の粒は動かず、粒が足されるだけ。

    ⚠ engine 34 では層が 7 枚あるので、**細かい地のタイル 1 枚の中で測る**。
    層を全部つないだ文字列で数えると、細かい地が伸びたぶんだけ粗い粒が後ろへ
    ずれ、位置の一致が「動いた」に見える —— 動いていないことは下の 6 枚が
    バイト一致することで別に測る。
    """
    sparse = _ground_layer(_score(_ground(density=0.45)))
    dense = _ground_layer(_score(_ground(density=0.85)))
    assert sparse != dense
    marks = re.compile(r"<(?:circle|line)\b[^>]*/>")
    sparse_marks = marks.findall(_PATTERN.findall(sparse)[0])
    dense_marks = marks.findall(_PATTERN.findall(dense)[0])
    assert len(dense_marks) > len(sparse_marks)
    assert dense_marks[: len(sparse_marks)] == sparse_marks
    # 同じ紙が濃くなる: 粗い粒の 6 枚は 1 バイトも動かない。
    assert _PATTERN.findall(sparse)[1:] == _PATTERN.findall(dense)[1:]


# --- 明示 seed の分岐が残っていること ---------------------------------------


def test_explicit_ground_seed_still_bypasses_the_derivation() -> None:
    """`ground.seed` の明示指定は本版でも導出を通らない (本番 20 件中 2 件が使用)。

    動かすのは**導出の入力である演奏 seed** である。材質を対にすると、
    seed が一致していても粒の形そのものが違いうる (`washi`) ので、
    主張が測れない。演奏 seed なら、材質を固定したまま導出だけを揺らせる。
    """
    moving = _ground_layer(_score(_ground(material="paper")), render_seed=98765)
    assert moving != _ground_layer(
        _score(_ground(material="paper"))
    ), "この入力で差が出ないなら、下の一致は何も言っていない"

    fixed = _ground_layer(_score(_ground(material="paper", seed=13579)))
    assert fixed == _ground_layer(
        _score(_ground(material="paper", seed=13579)), render_seed=98765
    )
    assert fixed != _ground_layer(_score(_ground(material="paper")))


# --- 支持体は雑音の性格である (要素を増やさない) -----------------------------


def _ground_marks(layer: str) -> list[str]:
    return re.findall(r"<(?:circle|line|path|rect)\b[^>]*/>", layer)


@pytest.mark.parametrize("material", ["washi", "ink_wash"])
def test_material_changes_the_marks_not_only_the_seed(material: str) -> None:
    """支持体を替えると**粒の描き方**が変わる。engine 15 まで 4 種は完全に同一だった。

    **seed を明示して固定する。** 固定しないと `material` が導出 seed に入って
    いるぶんで層が動いてしまい、描き分けの分岐を殺しても差が出る
    (実測: 分岐を `if False` にしても素通りした)。
    """
    assert _ground_layer(
        _score(_ground(material=material, seed=13579))
    ) != _ground_layer(_score(_ground(material="paper", seed=13579)))


def test_the_profile_does_not_decide_the_ground(material: str = "washi") -> None:
    """engine 34: **profile で作り分けない。**3 つとも同じ地が出る。

    engine 33 まで `display` は `feTurbulence` の矩形・他の 2 つは点を撒く実装で、
    「支持体は雑音の性格である」という主張はその filter の中身で測られていた
    (`feBlend` が washi・`feGaussianBlur` が ink_wash)。**その機構ごと無くなった**
    ので、ここで測るのは filter の中身ではなく **filter を 1 つも使わないこと**
    である。素材ごとの描き分けそのものは
    `test_the_ground_is_a_support_you_can_name.py` の T-5 / T-7 が持つ。
    """
    for profile in ("display", "editable", "compat"):
        svg = render(
            _score(_ground(material=material)), svg_profile=profile, render_seed=RENDER_SEED
        )
        start = svg.index(f'<g id="{GROUND_LAYER_ID}"')
        end = svg.index("</g>", start) + len("</g>")
        assert "filter" not in svg[start:end], profile


# 「支持体は雑音の性格であって、描くものではない」という engine 15 の規則は
# engine 34 で失効した —— 繊維を 38 本引いて地が絵全体の 46% を占めたのは、
# 要素をキャンバスへ直接積んでいたからである。タイルの中の 80 本は画面に 1 度
# しか書かれない。**費用の歯止めは要素数ではなくバイトになった**（24 KB・
# 作者裁定 2026-08-14）。その受入は上記ファイルの T-6 が持つ。


# --- absorbency の退役 -------------------------------------------------------


def test_absorbency_is_retired_from_the_spec() -> None:
    """`absorbency` はフィールドとして退役した。"""
    assert "absorbency" not in CanvasGroundSpec.model_fields


def test_retired_absorbency_does_not_block_saved_scores() -> None:
    """保存済み Score が持つ `absorbency` は落とされ、再生を妨げない。

    `extra="forbid"` があるので、落とす経路が無いと再生時に ValidationError で
    弾かれる。本番の地あり 23 件はすべてこのキーを持っている。
    """
    score = _score(_ground(absorbency=0.85))
    ground = score.canvas.ground
    assert not hasattr(ground, "absorbency")
    assert ground.material == "paper"
    assert ground.grain == "medium"

    # 落とすのは退役した 1 つだけで、未知フィールドは今も拒否する。
    with pytest.raises(ValidationError):
        Score.model_validate(
            {
                "canvas": {
                    "aspect": "square",
                    "ground": _ground(viscosity=0.4),
                },
                "instructions": [dict(BASE_INSTRUCTION)],
            }
        )
