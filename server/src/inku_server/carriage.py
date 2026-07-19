"""明示語彙の搬送契約の鏡 (v1.94 B・検査のみ).

正規化DDLに字面で明示された語彙が最終 Score に載ったかを決定的に検査し、
欠落を警告文字列として返す。生成・受け入れ・再試行には一切接続しない
（洗練の会計の「鏡」原則）。検査対象は対応が一意な語のみに限定する:

- つらなり: 破線/点線/一点鎖線 (dashed/dotted/dash-dot) → instruction.style
- てざわり: 素材語 → instruction.weight
- わりあい: 半円/semicircle → arc の掃引 180°±15
- ゆらぎ（対応が一意な 3 語）: 滲む→quality=pink、大きく→amplitude=broad、
  細かく→amplitude=fine

利き目監査 (harness-summary H-1/H-3/H-5/H-8) で実測された搬送切れ領域の計器。
違反はプロンプト・例・決定的転写の改善先を示す材料であり、作品の合否ではない。
"""

from __future__ import annotations

from .saijiki import weight_for_surface
from .schema import Score

_STYLE_TERMS = {
    "破線": "dashed",
    "点線": "dotted",
    "一点鎖線": "dash_dot",
    "dashed": "dashed",
    "dotted": "dotted",
    "dash-dot": "dash_dot",
}

_VARIATION_TERMS = {
    "滲む": ("quality", "pink"),
    "blurring": ("quality", "pink"),
    "大きく": ("amplitude", "broad"),
    "large": ("amplitude", "broad"),
    "細かく": ("amplitude", "fine"),
    "fine": ("amplitude", "fine"),
}

_SEMICIRCLE_TERMS = ("半円", "semicircle")


def carriage_warnings(ddl: str, score: Score) -> list[str]:
    """DDL に明示された語彙のうち Score へ搬送されなかったものを列挙する。"""
    warnings: list[str] = []
    instructions = score.instructions
    lower = ddl.lower()

    styles = {ins.style for ins in instructions if getattr(ins, "style", None)}
    for term, value in _STYLE_TERMS.items():
        if term in ddl or term in lower:
            if value not in styles:
                warnings.append(f"carriage: line style '{term}' not in score (expected style={value})")

    weights = {ins.weight for ins in instructions if ins.weight}
    for surface, value in weight_for_surface().items():
        if surface in ddl or surface.lower() in lower:
            if value not in weights:
                warnings.append(f"carriage: touch '{surface}' not in score (expected weight={value})")

    if any(term in ddl or term in lower for term in _SEMICIRCLE_TERMS):
        spans = [
            abs((ins.angle_end or 0.0) - (ins.angle_start or 0.0))
            for ins in instructions
            if ins.primitive == "arc" and ins.angle_end is not None and ins.angle_start is not None
        ]
        if not any(abs(span - 180.0) <= 15.0 for span in spans):
            warnings.append(
                f"carriage: semicircle not in score (arc sweeps={[round(s) for s in spans]}, expected 180±15)"
            )

    for term, (field, value) in _VARIATION_TERMS.items():
        if term in ddl or term in lower:
            hit = any(
                ins.variation is not None and getattr(ins.variation, field, None) == value
                for ins in instructions
            )
            if not hit:
                warnings.append(f"carriage: movement '{term}' not in score (expected variation.{field}={value})")

    return warnings
