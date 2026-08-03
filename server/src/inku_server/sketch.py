"""Stage 0.5 -- sketch from life.

A dense description (a tanka, say) reaches Stage 1 as a single knot: the DDL
comes out short and the picture stays thin however much the description holds.
This layer stands before Stage 1 and rewrites the description as plain prose in
the language of things -- what is there, its shape, colour, position, direction,
number, speed, light. Stage 1 then reads prose it can divide.

The layer is one LLM call and it has two prompts. They differ in GRAIN, not in
how much they say: `fine` (the default) cuts the description into one fact per
short sentence; `coarse` bundles related facts with subordinate clauses into
fewer, longer sentences, so each block is read more deeply downstream. Measured
on 20 classical poems, the two arms carried the same total length and the same
semantic families, but produced different kinds of density (see the contract
`tasks/stage05-sketch.md` section 0.3).

The English prompt never names the layer. `sketch` is already a weight word in
the Stage 1 English prompt ("pale, delicate, faint, sketch, draft" -> pencil),
so putting it in this layer's output vocabulary would move a Stage 1 field.
The identifiers `sketch_text` / `sketch_grain` are internal names and are read
by nobody but us.
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass, field

from .interpreter import _interpret_anthropic, _interpret_gemini, _interpret_openai_detail
from .model_settings import provider_for_model

MAX_TOKENS = 1024

SKETCH_GRAINS = ("fine", "coarse")
DEFAULT_SKETCH_GRAIN = "fine"


def normalize_sketch_grain(value: str | None) -> str:
    """Resolve a requested grain. An absent or unknown value means the default."""
    grain = str(value or "").strip().lower()
    return grain if grain in SKETCH_GRAINS else DEFAULT_SKETCH_GRAIN


_RULES_JA = """あなたは inku の写生層である。作者の記述を、物の言葉だけで書いた散文へ写す。

# 規則
- 目に見えるものだけを書く。物・形・色・位置・向き・数・速さ・明暗。
- 感情語と評価語を書かない。「美しい」「趣がある」「寂しい」「見事だ」の類は使わない。
- 比喩・連想・解釈を足さない。記述に無い物を持ち込まない。
- 記述にある物は落とさない。
- 出力は日本語の平叙文だけ。見出し・箇条書き・記号・前置き・後書きを書かない。"""

_RULES_EN = """You rewrite the author's description as plain prose that names only things.

# Rules
- Write only what can be seen: objects, shapes, colours, positions, directions,
  numbers, speeds, light and dark.
- Use no words of feeling or judgement. Nothing is "beautiful", "lonely",
  "serene", "striking".
- Add no metaphor, no association, no interpretation. Bring in no object the
  description does not have.
- Drop no object the description does have.
- Output plain declarative sentences and nothing else: no heading, no list, no
  markup, no preamble, no closing remark."""

_GRAIN_JA = {
    "fine": """# 区切り
細かく区切る。1 文には 1 つのことだけを書く。
1 文はおよそ 10 字。読点は使わない。文の数はおよそ 8〜10 文。""",
    "coarse": """# 区切り
大きく区切る。関係のあることを従属節で束ねて 1 文にする。
1 文はおよそ 25 字。読点を使う。文の数はおよそ 3〜5 文。
総量は変えない。変えるのは区切りの大きさだけである。""",
}

_GRAIN_EN = {
    "fine": """# Grain
Cut fine. One sentence carries one fact.
Keep sentences short, around eight words. Use no commas.
Write around eight to ten sentences.""",
    "coarse": """# Grain
Cut coarse. Bundle related facts into one sentence with subordinate clauses.
Keep sentences long, around twenty words. Use commas.
Write around three to five sentences.
Say the same amount. Only the size of the pieces changes.""",
}

# Few-shot material. The Japanese pairs are the author's own, written for the
# 20-poem corpus that the contract measured (no-git-sync/opus5/stage05/
# japanese-sample-classic01.md, poems 01 / 02 / 03 -- one sparse, one middling,
# one dense). `fine` shows the segmented arm, `coarse` the continuous one.
_EXAMPLES_JA: dict[str, tuple[tuple[str, str], ...]] = {
    "fine": (
        (
            "ひさかたの光のどけき春の日にしづ心なく花の散るらむ",
            "白い花びらが幾つも落ちる。花びらは途中で向きを変える。落ちる速さは一定でなく、"
            "速いものと遅いものが混じる。枝が上方に横たわる。花びらが枝から次々と離れる。"
            "日の光が面いっぱいに一様に広がる。影は薄い。",
        ),
        (
            "石走る垂水の上のさわらびの萌え出づる春になりにけるかも",
            "岩の面を水が速く流れ落ちる。水は白くくだけて跳ねる。細かいしぶきがあたりにかかる。"
            "濡れた岩は黒い。流れのすぐ上に土がある。土から蕨の芽が幾つも出る。芽は出たばかりで小さい。"
            "芽の先は丸く巻いている。芽は立ち上がる。",
        ),
        (
            "春の苑紅にほふ桃の花下照る道に出で立つをとめ",
            "桃の花が咲いている。花は濃い紅である。花は枝いっぱいに幾つも重なる。花の下に道がある。"
            "道は花の紅を受けてほのかに明るい。道の上に少女がひとり立つ。花は少女の頭より高い。"
            "花は面をなして広がる。",
        ),
    ),
    "coarse": (
        (
            "ひさかたの光のどけき春の日にしづ心なく花の散るらむ",
            "白い花びらが幾つも、まっすぐには落ちずに途中で向きを変えながら、上方に横たわる枝から"
            "次々と離れていく。落ちる速さは一定でなく、速いものと遅いものが混じり、面いっぱいに"
            "一様に広がる日の光のなかで影は薄い。",
        ),
        (
            "石走る垂水の上のさわらびの萌え出づる春になりにけるかも",
            "岩の面を水が速く流れ落ち、白くくだけて跳ね、細かいしぶきをあたりにかけている。"
            "濡れた岩は黒い。その流れのすぐ上の土から、蕨の芽が幾つも出たばかりで、"
            "先を丸く巻いたまま小さく立ち上がっている。",
        ),
        (
            "春の苑紅にほふ桃の花下照る道に出で立つをとめ",
            "濃い紅の桃の花が、枝いっぱいに幾つも重なって咲いている。花の下の道は、花の紅を受けて"
            "ほのかに明るい。その明るい道の上に、少女がひとり立つ。花は少女の頭より高いところで、"
            "面をなして広がっている。",
        ),
    ),
}

_EXAMPLES_EN: dict[str, tuple[tuple[str, str], ...]] = {
    "fine": (
        (
            "The last light on still water.",
            "Water lies flat. The surface is dark. A band of pale light crosses it. "
            "The band is narrow. The light comes from low down. The far edge is lost. "
            "Nothing moves the surface.",
        ),
        (
            "Rain on the roof of a shed.",
            "Rain falls in thin lines. The lines slant. A low roof stands under the rain. "
            "The roof is grey metal. Water runs along one edge. Drops fall from the edge in a row. "
            "The ground below is dark and wet.",
        ),
        (
            "A market street in full sun.",
            "A street runs straight. Stalls stand along both sides. Cloth covers hang above them. "
            "The covers are red and white. Fruit is piled in round heaps. People move between the stalls. "
            "The shadows are short and hard. The upper walls are bright.",
        ),
    ),
    "coarse": (
        (
            "The last light on still water.",
            "Water lies flat and dark, crossed by a narrow band of pale light that comes from low down. "
            "The far edge is lost, and nothing moves the surface.",
        ),
        (
            "Rain on the roof of a shed.",
            "Thin slanting lines of rain fall onto a low roof of grey metal. "
            "Water runs along one edge and falls from it in a row of drops, "
            "and the ground below is dark and wet.",
        ),
        (
            "A market street in full sun.",
            "A straight street has stalls along both sides, with red and white cloth covers hung above them "
            "and fruit piled in round heaps. People move between the stalls under short hard shadows, "
            "and the light is strong on the upper walls.",
        ),
    ),
}


def build_system_prompt(*, lang: str = "ja", grain: str = DEFAULT_SKETCH_GRAIN) -> str:
    """Build the Stage 0.5 system prompt for a language and a grain."""
    grain = normalize_sketch_grain(grain)
    if lang == "en":
        rules, grain_section = _RULES_EN, _GRAIN_EN[grain]
        header, in_label, out_label = "# Examples", "Description", "Prose"
        examples = _EXAMPLES_EN[grain]
    else:
        rules, grain_section = _RULES_JA, _GRAIN_JA[grain]
        header, in_label, out_label = "# 例", "記述", "写生文"
        examples = _EXAMPLES_JA[grain]
    blocks = "\n\n".join(
        f"{in_label}: {source}\n{out_label}: {rendered}" for source, rendered in examples
    )
    return f"{rules}\n\n{grain_section}\n\n{header}\n\n{blocks}"


def prompt_digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


@dataclass
class SketchDetail:
    """What Stage 0.5 produced, plus what it cost."""

    text: str
    grain: str = DEFAULT_SKETCH_GRAIN
    tokens_in: int | None = None
    tokens_out: int | None = None
    fallback_used: bool = False
    fallback_reasons: list[str] = field(default_factory=list)
    raw: str | None = None  # trace: the model's output before any trimming
    prompt_digest: str | None = None


def sketch_from_life(
    text: str,
    *,
    model: str | None = None,
    lang: str = "ja",
    grain: str = DEFAULT_SKETCH_GRAIN,
) -> tuple[str, int | None, int | None]:
    """Run Stage 0.5. Returns (sketch text, tokens_in, tokens_out).

    Raises on any provider failure. The caller decides what a failure means --
    here it always means the description travels on untouched, so a broken 0.5
    can never stop a painting (see `_call_sketch_detail`).
    """
    grain = normalize_sketch_grain(grain)
    system_prompt = build_system_prompt(lang=lang, grain=grain)
    from .interpreter import _current_model_settings

    settings = _current_model_settings()
    if model:
        provider, model_id = provider_for_model(model, stage="stage1", settings=settings)
        if provider == "anthropic":
            return _interpret_anthropic(
                text, model=model_id, system_prompt=system_prompt, settings=settings
            )
        if provider == "gemini":
            return _interpret_gemini(
                text, model=model_id, system_prompt=system_prompt, settings=settings
            )
        out, _thinking, tin, tout = _interpret_openai_detail(
            text,
            model=model_id,
            provider=provider,
            include_thinking=False,
            system_prompt=system_prompt,
        )
        return out, tin, tout
    backend = os.getenv("INKU_LLM_BACKEND", "anthropic").lower()
    if backend == "openai":
        out, _thinking, tin, tout = _interpret_openai_detail(
            text, model=None, include_thinking=False, system_prompt=system_prompt
        )
        return out, tin, tout
    return _interpret_anthropic(text, system_prompt=system_prompt)
