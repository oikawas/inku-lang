"""T-1..T-10 of 契約 limits-hold-without-the-model.

Three things are under test, and they fail in different ways:

  stage 1  every limit is read from one module, so the follow-up settings
           contract has one place to swap;
  stage 2  a count stated in the description is honoured below the threshold and
           represented above it -- and the two routes to a represented count land
           on the SAME number, which is what [I-110] was about;
  stage 3  a ceiling no route can exceed, grids included, running after every
           governor.

The frozen corpora do NOT gate any of this: measured before the work began, the
intended change moves 0 of ddl-engine-6's 36 cases and 0 of render-engine-21's
525 (which never calls coerce at all). T-10 is a regression guard and is written
as one; it is not evidence that any of the above works.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

from inku_server.coerce import coerce_score
from inku_server.coerce.normalize import _enforce_hard_ceiling, _mark_count
from inku_server.limits import DEFAULT_LIMITS, Limits
from inku_server.schema import Score

COERCE_DIR = pathlib.Path(__file__).resolve().parents[1] / "src" / "inku_server" / "coerce"
COMPOSE_SOURCE = COERCE_DIR / "compose.py"


def _function(source: str, name: str) -> ast.FunctionDef:
    return next(
        node
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.FunctionDef) and node.name == name
    )


def _line(**overrides) -> dict:
    return {"primitive": "line", "from": [0.2, 0.2], "to": [0.8, 0.8], "color": "black", **overrides}


def _clause_route(requested_ja: str) -> int:
    """The count a number written in the description arrives at.

    Through coerce_score, the entry point. Calling the clause branch directly
    bypasses the caller's gate and over-reports.
    """
    score = Score.model_validate({"background": "white", "instructions": [_line()]})
    out = coerce_score(score, ddl=f"線を引く。青い点を{requested_ja}個散らす。")
    scattered = [ins for ins in out.instructions if ins.arrangement is not None]
    assert scattered, "the clause route produced no arrangement to measure"
    return scattered[0].arrangement.count


def _governor_route(requested: int) -> int:
    """The count a Stage 2 arrangement of the same size arrives at."""
    score = Score.model_validate(
        {
            "background": "white",
            "instructions": [
                {
                    "primitive": "circle",
                    "center": [0.5, 0.5],
                    "radius": 0.02,
                    "color": "black",
                    "arrangement": {"count": requested, "layout": "scatter", "margin": 0.18},
                }
            ],
        }
    )
    out = coerce_score(score)
    return out.instructions[0].arrangement.count


# --------------------------------------------------------------------------- T-1


def test_t1_the_clause_branch_caps_by_name_not_by_a_bare_literal() -> None:
    """Reintroducing min(count, 120) at the scatter site must turn this red.

    Asserting on the string "120" alone would stay green if someone wrote
    min(count, 0x78), so this asserts on the ABSENCE of any integer literal in the
    two arrangement caps AND on the PRESENCE of the named reference.
    """
    source = COMPOSE_SOURCE.read_text(encoding="utf-8")
    function = _function(source, "_fallback_instruction_from_clause")
    segment = ast.get_source_segment(source, function)
    assert segment is not None

    # The named reference is there, on both the scatter and the horizontal site.
    assert segment.count("_budgeted_count(count, limits)") == 2
    assert "limits.schema_count_max" in segment

    # And no bare literal is left capping the count. Walk every min(count, ...)
    # call in the function and refuse an integer constant as its bound. (Scoped to
    # `count`: `min(index, 4)` on the placement offset is not a mark budget.)
    capped_by_literal = []
    for node in ast.walk(function):
        if not isinstance(node, ast.Call):
            continue
        if not (isinstance(node.func, ast.Name) and node.func.id == "min"):
            continue
        if not (node.args and isinstance(node.args[0], ast.Name) and node.args[0].id == "count"):
            continue
        if any(isinstance(arg, ast.Constant) and isinstance(arg.value, int) for arg in node.args):
            capped_by_literal.append(node.lineno)
    assert capped_by_literal == [], f"min(count, <literal>) survives at {capped_by_literal}"


# --------------------------------------------------------------------------- T-2


def test_t2_a_clause_stating_233_comes_out_as_233() -> None:
    """SPEC 1502-1505 names this number outright: 233 lines are drawn as 233.

    Production had six works where 121-239 was cut to 120. This is that bug.
    """
    assert _clause_route("二百三十三") == 233


# --------------------------------------------------------------------------- T-3


def test_t3_control_a_clause_stating_300_still_comes_out_as_120() -> None:
    """Without this control, deleting the cap entirely passes T-2 and breaks the band."""
    assert _clause_route("三百") == DEFAULT_LIMITS.represented_count_max


# --------------------------------------------------------------------------- T-4


@pytest.mark.parametrize(
    ("requested", "written"),
    [(241, "二百四十一"), (250, "二百五十"), (300, "三百"), (500, "五百")],
)
def test_t4_the_two_routes_agree_on_the_same_number(requested: int, written: str) -> None:
    """THE T THAT CLOSES [I-110]. Inside the same band is not the same number.

    241 and 250 are the cases that matter. An implementation that returns the
    constant 120 above the threshold passes at 300 and 500 and fails only here:
    the density governor lands on 101 and 105 for these two, not 120. A test that
    only exercises 300 is vacuous.
    """
    assert _clause_route(written) == _governor_route(requested)


def test_t4_guard_241_and_250_really_are_the_discriminating_cases() -> None:
    """If these two ever stop discriminating, T-4 has quietly gone vacuous."""
    assert _governor_route(241) != DEFAULT_LIMITS.represented_count_max
    assert _governor_route(250) != DEFAULT_LIMITS.represented_count_max
    assert _governor_route(300) == DEFAULT_LIMITS.represented_count_max
    assert _governor_route(500) == DEFAULT_LIMITS.represented_count_max


# --------------------------------------------------------------------------- T-5


def test_t5_a_grid_is_not_exempt_from_the_ceiling() -> None:
    """The two density governors deliberately skip grids; the ceiling does not.

    The three grids must be structurally distinct: coerce dedupes identical
    instructions, so three copies of one grid collapse to a single 2000 and the
    hole is never exercised.
    """
    score = Score.model_validate(
        {
            "background": "white",
            "instructions": [
                {
                    "primitive": "square",
                    "position": [0.1, 0.1],
                    "size": [0.02, 0.02],
                    "color": "black",
                    "arrangement": {"count": 2000, "layout": "grid", "rows": 40, "cols": 50},
                },
                {
                    "primitive": "circle",
                    "center": [0.5, 0.5],
                    "radius": 0.01,
                    "color": "blue",
                    "arrangement": {"count": 2000, "layout": "grid", "rows": 50, "cols": 40},
                },
                {
                    "primitive": "triangle",
                    "position": [0.3, 0.3],
                    "size": [0.02, 0.02],
                    "color": "green",
                    "arrangement": {"count": 1600, "layout": "grid", "rows": 25, "cols": 64},
                },
            ],
        }
    )
    assert len(score.instructions) == 3, "the fixture must not dedupe before it is measured"

    out = coerce_score(score)
    grids = [ins for ins in out.instructions if ins.arrangement and ins.arrangement.layout == "grid"]
    assert len(grids) == 3

    total = sum(_mark_count(ins) for ins in out.instructions)
    assert total <= DEFAULT_LIMITS.max_expanded_primitives, total

    # A lattice with holes in it is not a lattice: the shape survives, the cell
    # count is what gives way.
    for ins, original in zip(grids, [(40, 50), (50, 40), (25, 64)]):
        arr = ins.arrangement
        assert arr.rows is not None and arr.cols is not None
        assert arr.count == arr.rows * arr.cols
        assert abs((arr.rows / arr.cols) / (original[0] / original[1]) - 1) < 0.10


# --------------------------------------------------------------------------- T-6


def test_t6_control_a_work_already_under_the_ceiling_is_untouched() -> None:
    """Without this, "clamp everything to 400" passes T-5.

    The identity check is the sharp end: an implementation that rebuilds the
    Score unconditionally fails it even when the numbers happen to agree.
    """
    score = Score.model_validate(
        {
            "background": "white",
            "instructions": [
                _line(),
                {
                    "primitive": "circle",
                    "center": [0.5, 0.5],
                    "radius": 0.02,
                    "color": "black",
                    "arrangement": {"count": 40, "layout": "scatter", "margin": 0.18},
                },
                {
                    "primitive": "square",
                    "position": [0.2, 0.2],
                    "size": [0.05, 0.05],
                    "color": "blue",
                    "arrangement": {"count": 12, "layout": "grid", "rows": 3, "cols": 4},
                },
            ],
        }
    )

    assert _enforce_hard_ceiling(score) is score

    out = coerce_score(score)
    counts = {
        ins.primitive: ins.arrangement.count for ins in out.instructions if ins.arrangement is not None
    }
    assert counts["circle"] == 40
    assert counts["square"] == 12
    assert all("hard ceiling" not in (ins.note or "") for ins in out.instructions)


# --------------------------------------------------------------------------- T-7


def test_t7_the_instruction_list_is_bounded_and_the_drop_is_recorded() -> None:
    """schema.py declares a bare list[Instruction]; nothing bounded it before.

    Production's worst work carries 27 instructions (p50=4, p90=7, p99=18), so
    64 stops a runaway without touching anything real.
    """
    score = Score.model_validate(
        {
            "background": "white",
            "instructions": [
                _line(**{"from": [0.1, index / 220], "to": [0.9, index / 220]}) for index in range(200)
            ],
        }
    )

    out = coerce_score(score)
    assert len(out.instructions) <= DEFAULT_LIMITS.max_instructions
    assert len(out.instructions) == DEFAULT_LIMITS.max_instructions

    notes = " ".join(ins.note or "" for ins in out.instructions)
    assert "instruction list capped" in notes
    assert str(200 - DEFAULT_LIMITS.max_instructions) in notes


# --------------------------------------------------------------------------- T-8


def test_t8_the_ceiling_is_the_last_word() -> None:
    """Order is measured, not assumed.

    `_with_literal_grid_fidelity` runs AFTER both density governors and writes
    `arrangement.count = count_hint` straight from the description -- it grows a
    count back. Move `_enforce_hard_ceiling` above it in the pipeline and this
    goes red, because the restored 1500 survives to the exit.
    """
    ddl = "四角を千五百個敷き詰める。"
    score = Score.model_validate(
        {
            "background": "white",
            "instructions": [
                {
                    "primitive": "square",
                    "position": [0.1, 0.1],
                    "size": [0.02, 0.02],
                    "color": "black",
                    "arrangement": {"count": 1500, "layout": "grid", "rows": 30, "cols": 50},
                }
            ],
        }
    )

    out = coerce_score(score, ddl=ddl)
    total = sum(_mark_count(ins) for ins in out.instructions)
    assert total <= DEFAULT_LIMITS.max_expanded_primitives, total

    # The governor that would re-grow it really does fire on this input, so the
    # assertion above is not passing by never reaching the branch.
    grid = next(ins for ins in out.instructions if ins.arrangement and ins.arrangement.layout == "grid")
    assert "hard ceiling" in (grid.note or "")


def test_t8_guard_the_restoring_governor_still_runs_after_the_governors() -> None:
    """The perturbation target for T-8, named so a refactor cannot hide it."""
    source = (COERCE_DIR / "__init__.py").read_text(encoding="utf-8")
    body = source[source.index("def coerce_score") :]
    ceiling_at = body.rindex("_enforce_hard_ceiling")
    fidelity_at = body.rindex("_with_literal_grid_fidelity")
    total_budget_at = body.rindex("_with_total_density_budget")
    assert total_budget_at < fidelity_at < ceiling_at


# --------------------------------------------------------------------------- T-9

# The aesthetic governors are excluded by name, not by accident. They are not
# other names for the mark budget: they bound how large or how bright a shape may
# be in a quiet composition. The list is spelled out so that adding a new one is
# a visible act, and each is asserted to still exist so the exclusion cannot rot
# into a list of names nobody defines any more.
AESTHETIC_GOVERNORS = frozenset(
    {
        "MAX_QUIET_VISUAL_COUNT",
        "MAX_QUIET_VERTICAL_COUNT",
        "MAX_NEON_BLUR_VISUAL_COUNT",
        "MAX_NEON_BLUR_VERTICAL_COUNT",
        "MAX_QUIET_LARGE_SHAPE_COUNT",
        "MAX_QUIET_SYMBOLIC_SHAPE_COUNT",
    }
)

MARK_BUDGET_WORDS = ("EXPANDED", "CLUSTERED", "LITERAL_COUNT", "REPRESENTED", "COUNT_MAX", "INSTRUCTIONS")


def _module_level_int_constants(path: pathlib.Path) -> dict[str, object]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: dict[str, object] = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if not isinstance(target, ast.Name):
                continue
            try:
                value = ast.literal_eval(node.value)
            except ValueError:
                continue
            if isinstance(value, int) or (
                isinstance(value, tuple) and value and all(isinstance(v, int) for v in value)
            ):
                found[target.id] = value
    return found


def test_t9_no_module_in_coerce_keeps_a_mark_budget_constant_of_its_own() -> None:
    """One place to swap is what the follow-up settings contract is buying.

    A constant here is not merely duplication: MAX_EXPANDED_PER_INSTRUCTION and
    LITERAL_COUNT_THRESHOLD were the same band under two names, and reading the
    band as a bare 120 is how "the top of the representative band" came to be
    used as "an unconditional cap".
    """
    offenders: dict[str, list[str]] = {}
    seen_aesthetic: set[str] = set()
    for path in sorted(COERCE_DIR.glob("*.py")):
        constants = _module_level_int_constants(path)
        seen_aesthetic |= set(constants) & AESTHETIC_GOVERNORS
        named = [
            name
            for name in constants
            if name not in AESTHETIC_GOVERNORS
            and any(word in name for word in MARK_BUDGET_WORDS)
        ]
        if named:
            offenders[path.name] = sorted(named)

    assert offenders == {}, offenders
    assert seen_aesthetic == AESTHETIC_GOVERNORS, AESTHETIC_GOVERNORS - seen_aesthetic


def test_t9_every_module_that_bounds_a_count_imports_the_one_source() -> None:
    for name in ("normalize.py", "compose.py", "__init__.py"):
        source = (COERCE_DIR / name).read_text(encoding="utf-8")
        assert "from ..limits import DEFAULT_LIMITS, Limits" in source, name


def test_t9_the_limits_table_covers_every_bound_the_contract_named() -> None:
    assert set(Limits.__dataclass_fields__) == {
        "max_expanded_primitives",
        "max_expanded_per_instruction",
        "literal_count_threshold",
        "represented_count_min",
        "represented_count_max",
        "ddl_count_max",
        "ddl_count_max_grid",
        "schema_count_max",
        "max_instructions",
    }
    # This stage moves the values, it does not change them.
    assert DEFAULT_LIMITS == Limits(
        max_expanded_primitives=400,
        max_expanded_per_instruction=240,
        literal_count_threshold=240,
        represented_count_min=80,
        represented_count_max=120,
        ddl_count_max=1000,
        ddl_count_max_grid=2000,
        schema_count_max=2000,
        max_instructions=64,
    )


# --------------------------------------------------------------------------- T-10


def test_t10_regression_guard_only_the_frozen_corpora_do_not_gate_this_work() -> None:
    """MEASURED BEFORE ISSUING: 0/36 and 0/525 move under the intended change.

    ddl-engine-6 reaches coerce but its largest single case totals 232 marks and
    its three arrangements are 12, 110 and 110 -- nothing near the 400 ceiling and
    nothing above the 240 threshold. render-engine-21 takes a Score directly and
    never calls coerce at all. Byte-identical corpora are therefore NOT evidence
    that any of T-1..T-9 works, and must not be reported as such.
    """
    from inku_server.layer_versions import DDL_ENGINE_VERSION  # noqa: PLC0415

    manifest_path = (
        pathlib.Path(__file__).resolve().parents[1]
        / "reference"
        / f"ddl-engine-{DDL_ENGINE_VERSION}"
        / "manifest.json"
    )
    import hashlib  # noqa: PLC0415
    import json  # noqa: PLC0415

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    coerce_cases = {k: v for k, v in manifest["cases"].items() if v["part"] == "b_coerce"}
    # 23 at ddl-engine 12, which added a stated-count pair. The property below is
    # what this counts for, and it still holds: the larger of the two stands at
    # 205 marks, well under the ceiling, and only becomes interesting once a
    # repair tries to write a stated count on top of it.
    assert len(coerce_cases) == 23

    for case in coerce_cases.values():
        data = (manifest_path.parent / case["output_path"]).read_bytes()
        assert hashlib.sha256(data).hexdigest()[:32] == case["digest"], case["output_path"]

    # And the corpus really is below both bounds, which is WHY it stays still.
    largest = 0
    for case in coerce_cases.values():
        score = Score.model_validate(case["input"]["score"])
        largest = max(largest, sum(_mark_count(ins) for ins in score.instructions))
    assert largest < DEFAULT_LIMITS.max_expanded_primitives, largest
