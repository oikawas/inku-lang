"""Every limit that governs how many marks a work may carry, in one place.

The values here are TODAY'S SHIPPING VALUES, read off the tree before this module
existed. This module MOVES them; it does not change them. The follow-up contract
(limits-are-settings.md) replaces the source of these values with a stored
setting, which is why every reader must come through here and not reach for a
module constant of its own.

Aesthetic governors (MAX_QUIET_*, MAX_NEON_BLUR_*, FOCAL_EVENT_*) deliberately
stay where they are: they are not other names for these numbers, they are
different numbers with a different purpose.
"""

from __future__ import annotations

from dataclasses import dataclass


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
