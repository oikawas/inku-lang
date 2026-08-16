"""Every limit that governs how many marks a work may carry, in one place.

The values here are the DEFAULTS. They are also today's shipping values, read
off the tree before this module existed. The source of the *effective* values is
a stored setting (`render_limit_settings`), normalized here and resolved once per
request; every reader must come through a `Limits` instance and not reach for a
module constant of its own.

A per-install setting does not break reproducibility on its own -- the effective
limits are recorded on the work, the same way the chosen model and the colour
catalogue already are. The version identifies the code, the recorded limits
identify the configuration, and the two together decide the behaviour.

Aesthetic governors (MAX_QUIET_*, MAX_NEON_BLUR_*, FOCAL_EVENT_*) deliberately
stay where they are: they are not other names for these numbers, they are
different numbers with a different purpose.
"""

from __future__ import annotations

import dataclasses
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Iterator


@dataclass(frozen=True)
class Limits:
    """The bounds on how much a single work may ask to be drawn."""

    # How many marks may actually be drawn.
    max_expanded_primitives: int = 400  # per work
    max_expanded_per_instruction: int = 240  # per instruction

    # How a stated number is honoured. Below the threshold the number the
    # description asked for is drawn as stated; above it the group is shown as a
    # band, because a reader cannot count that many by eye.
    literal_count_threshold: int = 240
    represented_count_min: int = 80
    represented_count_max: int = 120

    # The ceiling applied when a numeral is read OUT OF THE DESCRIPTION.
    # "1500 lines" in a clause becomes 1000; a literal grid request may reach 2000.
    ddl_count_max: int = 1000
    ddl_count_max_grid: int = 2000

    # The only bound validated on Stage 2's own output. The `le=2000` field bound
    # and the `_clamp_count` validator in schema.py are LAYOUT-BLIND: a scatter
    # arrangement declaring 1500 passes today. The "1-1000 for normal layouts"
    # line in the prompt is guidance to the model, not a checked bound.
    schema_count_max: int = 2000

    # The instruction list had no bound at all: schema.py declares a bare
    # `list[Instruction]`. Production has never exceeded 27 (p50=4, p90=7,
    # p99=18), so 64 leaves every real work untouched and stops only a runaway.
    max_instructions: int = 64


DEFAULT_LIMITS = Limits()

LIMIT_FIELD_NAMES: tuple[str, ...] = tuple(
    field.name for field in dataclasses.fields(Limits)
)

# The three families the settings tab shows, in the order it shows them. The
# grouping is not decoration: each family answers to a different authority, and
# the panel has to say which, or an administrator cannot tell what moving a
# number will move.
#
#   capability  what THIS INSTALLATION can afford to draw. A faster machine may
#               raise it. Measured on the development Mac at render engine 35,
#               one grid mark costs ~13 KB of SVG with a pen and ~16 KB with a
#               thick brush, so the 400 default already lets one work reach
#               5-6.5 MB. This is the only family that should follow the
#               hardware.
#   legibility  where counting by eye stops and a group is shown as a band.
#               A faster machine does not make an eye faster, so this family
#               must NOT be linked to capability. What it has to keep constant
#               is the look -- how much ink sits in one cluster -- not the
#               threshold digits.
#   safety      typo and runaway guards. Nothing here improves a drawing; they
#               only stop a pasted phone number. An installation should be able
#               to leave the whole family alone.
LIMIT_GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "capability",
        ("max_expanded_primitives", "max_expanded_per_instruction"),
    ),
    (
        "legibility",
        ("literal_count_threshold", "represented_count_min", "represented_count_max"),
    ),
    (
        "safety",
        ("max_instructions", "ddl_count_max", "ddl_count_max_grid", "schema_count_max"),
    ),
)

# How much ink one cluster holds. This is the quantity the legibility family
# exists to keep constant: what an administrator raising `represented_count_max`
# wants is a denser picture, not clusters that quietly stop reading as clusters.
# A faster machine does not make an eye faster, so neither number scales.
#
# Both are read off what the tree shipped with, at the default ceiling of 120:
#   24  the most one cluster ever holds -- 120 marks drawn in 5 clusters
#   10  the least -- the `le=12` that used to sit on Arrangement.cluster_count
#       said, at that ceiling, that a cluster below ten marks is not a cluster
#
# They are here rather than beside their readers because three layers consult
# them and a copy in any of them would freeze the day it was copied: coerce
# picks the cluster count, the schema clamps what the model may declare, and the
# composer writes the bound into the tool the model is handed.
MAX_MARKS_PER_CLUSTER = 24
MIN_MARKS_PER_CLUSTER = 10


def max_cluster_count(limits: Limits) -> int:
    """The most clusters a group may be split into under these limits.

    At the defaults this is 12, which is the number that used to be written
    straight onto the field. Raise the representation ceiling and it rises with
    it, which is the whole point: the drawn count already followed the setting
    and the divisor did not, so one cluster took every extra mark.
    """
    return max(1, limits.represented_count_max // MIN_MARKS_PER_CLUSTER)


# Not a tuning bound -- a typo guard. Every limit here multiplies into drawing
# cost (measured at 4.2 ms per mark on the development Mac), so a pasted phone
# number would hang a request rather than produce a work. 100000 is ~250x the
# largest default and cannot bind any real adjustment.
LIMIT_ABSOLUTE_MAX = 100000


def _positive_int(value: object, fallback: int) -> int:
    try:
        number = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return fallback
    return min(max(number, 1), LIMIT_ABSOLUTE_MAX)


def normalize_limits(settings: object) -> dict[str, int]:
    """Fill in the defaults, then round until the set cannot contradict itself.

    Bad values are rounded, not rejected, and the rounded set is what gets
    stored and returned -- so the panel can show what actually took effect
    instead of what was typed.
    """
    clean = {name: getattr(DEFAULT_LIMITS, name) for name in LIMIT_FIELD_NAMES}
    if isinstance(settings, dict):
        for name in LIMIT_FIELD_NAMES:
            if name in settings:
                clean[name] = _positive_int(settings[name], clean[name])

    # A group is shown as a band because it is too large to count by eye, so the
    # band cannot start above where counting stops.
    clean["represented_count_max"] = min(
        clean["represented_count_max"], clean["literal_count_threshold"]
    )
    clean["represented_count_min"] = min(
        clean["represented_count_min"], clean["represented_count_max"]
    )
    # One instruction cannot be allowed more marks than the whole work.
    clean["max_expanded_per_instruction"] = min(
        clean["max_expanded_per_instruction"], clean["max_expanded_primitives"]
    )
    return clean


def limits_from_settings(settings: object) -> Limits:
    """The effective limits for one request, from whatever the DB holds."""
    return Limits(**normalize_limits(settings))


def limits_as_dict(limits: Limits) -> dict[str, int]:
    """What gets recorded on the work and returned in the response."""
    return {name: getattr(limits, name) for name in LIMIT_FIELD_NAMES}


# An explicit argument is the primary channel and stays that way -- coerce, the
# prompt builders and the recorders all take `limits` by name, so a caller that
# forgets one is visible in the signature.
#
# Two readers cannot take an argument: the pydantic validator on
# Arrangement.count, and the tool-schema description handed to the model. Both
# run inside `Score.model_validate` / `model_json_schema`, which have no room
# for one. They read this instead. The request path sets it from the SAME
# resolved Limits it passes explicitly, and a test asserts the two agree.
#
# The default is DEFAULT_LIMITS, which is what makes the reference generators
# and every test that never enters a request run at the defaults.
_CURRENT_LIMITS: ContextVar[Limits] = ContextVar("inku_current_limits", default=DEFAULT_LIMITS)


def current_limits() -> Limits:
    """The limits in force for this request, for the two readers that cannot take an argument."""
    return _CURRENT_LIMITS.get()


@contextmanager
def using_limits(limits: Limits) -> Iterator[Limits]:
    token = _CURRENT_LIMITS.set(limits)
    try:
        yield limits
    finally:
        _CURRENT_LIMITS.reset(token)


def note_limit(notes: list[str] | None, name: str, detail: str) -> None:
    """Record that the limit called `name` took effect.

    The name comes first in the line because the reader is an administrator
    asking which of these nine moved the picture: "the ink halved" was the whole
    of what the two existing notes could say, and neither of them named a
    setting. `name` is a field of `Limits`, so the line can be matched by key.

    Recorded once per limit per work. A ceiling that clipped four arrangements
    bound once; four identical lines answer "which setting" no better than one,
    and the count of lines would then mean "how many arrangements", which is a
    different question with a different answer already in the Score.

    `notes` is None wherever coerce runs outside a request -- the reference
    generators, the tests that call it directly -- and then nothing is recorded
    and nothing else changes. This never touches the Score: what a limit did to
    the drawing is already written into the instruction's own note, and moving
    those bytes would redraw every frozen corpus.
    """
    if notes is None:
        return
    prefix = f"{name}: "
    if any(line.startswith(prefix) for line in notes):
        return
    notes.append(prefix + detail)
