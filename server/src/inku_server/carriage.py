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

from dataclasses import dataclass

from .saijiki import weight_for_surface
from .schema import Instruction, Score

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


# --------------------------------------------------------------------------- #
# The other direction (I-107 / 契約 description-propagation-cut 段 3)          #
#                                                                              #
# Everything above answers "did what the DDL declared reach the Score". That is #
# one of two ways carriage fails, and the cheaper one to see. The other is the  #
# Score carrying what the DDL never declared, and until the description was cut #
# out of coerce's input it could not be measured at all: coerce read            #
# `prose\nDDL`, so an instruction it authored could always be traced to         #
# something the author had written, and an addition was indistinguishable from  #
# a delivery. With the DDL as the only route in, an addition that answers to no  #
# clause is visible.                                                            #
#                                                                              #
# This is a measurement, not an acceptance rule. Whether a rate is too high is  #
# a separate decision (契約 §5-6); coerce authoring a composition is by design  #
# ([[coerce_is_the_composer]]) and this instrument is what makes the size of    #
# that authorship reportable.                                                   #
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Addition:
    """One instruction the layer authored, and what in the DDL answers for it."""

    primitive: str
    color: str | None
    note: str | None
    grounded_primitive: bool
    grounded_color: bool

    @property
    def grounded(self) -> bool:
        """Whether the DDL names this shape, or this colour, at all."""
        return self.grounded_primitive or self.grounded_color


@dataclass(frozen=True)
class CarriageReport:
    dropped: list[str]
    additions: list[Addition]
    instructions_in: int
    instructions_out: int
    declared_colors: frozenset[str]
    declared_primitives: frozenset[str]
    branches_that_fired: dict[str, int]

    @property
    def ungrounded(self) -> list[Addition]:
        return [addition for addition in self.additions if not addition.grounded]


def _declared(ddl: str | None) -> tuple[frozenset[str], frozenset[str]]:
    """What the DDL states outright, in the product's own vocabulary.

    Imported from the coerce layer rather than restated: a second copy of "which
    words name a colour" drifts from the one the product uses, and this module
    would then be measuring itself.
    """
    from .coerce.compose import _ddl_clauses, _primitive_from_clause, _requested_colors_from_ddl

    return (
        frozenset(_requested_colors_from_ddl(ddl)),
        frozenset(_primitive_from_clause(clause) for clause in _ddl_clauses(ddl)),
    )


def _authored(before: list[Instruction], after: list[Instruction]) -> list[Instruction]:
    """The instructions in `after` that answer to nothing in `before`.

    Matched on the primitive alone, greedily. Comparing whole instructions would
    call every repaired instruction an addition -- repair is most of what this
    layer does, and a normalized centre is not a new mark. Matching on the
    primitive means a repair that CHANGES a primitive reads as one drop and one
    addition, which is the reading that keeps the count honest: the shape the
    Score carries is no longer the shape it was handed.
    """
    remaining: dict[str, int] = {}
    for ins in before:
        remaining[ins.primitive] = remaining.get(ins.primitive, 0) + 1
    authored: list[Instruction] = []
    for ins in after:
        if remaining.get(ins.primitive, 0) > 0:
            remaining[ins.primitive] -= 1
            continue
        authored.append(ins)
    return authored


def carriage_report(
    ddl: str | None,
    *,
    before: Score,
    after: Score,
    branch_report: dict[str, int] | None = None,
) -> CarriageReport:
    """Both directions for one work, from what the entry point produced.

    `before` is the Score the layer was handed and `after` is what it returned.
    Passing the same Score twice reports zero additions, which is true of the
    call and says nothing about the layer -- the caller has to hold both.
    """
    declared_colors, declared_primitives = _declared(ddl)
    additions = [
        Addition(
            primitive=ins.primitive,
            color=ins.color,
            note=ins.note,
            grounded_primitive=ins.primitive in declared_primitives,
            grounded_color=bool(ins.color) and ins.color in declared_colors,
        )
        for ins in _authored(before.instructions, after.instructions)
    ]
    return CarriageReport(
        dropped=carriage_warnings(ddl or "", after),
        additions=additions,
        instructions_in=len(before.instructions),
        instructions_out=len(after.instructions),
        declared_colors=declared_colors,
        declared_primitives=declared_primitives,
        branches_that_fired={
            name: count for name, count in sorted((branch_report or {}).items()) if count
        },
    )
