"""Single source for geometry-assertion thresholds.

These numeric limits are the acceptance thresholds used by the leaf-sketch
geometry checks. They live here, in tracked server code, so both the check
script and the reference dump import the same values instead of duplicating
them. This module holds constants only; it makes no rendering or acceptance
decision on its own.
"""

from __future__ import annotations

# Maximum allowed gap between an arc pair's shared endpoints for "closed".
CLOSURE_LIMIT = 0.002
# Minimum interior angle (degrees) at a leaf tip before it reads as a cusp.
CUSP_LIMIT_DEGREES = 30.0
# Maximum relative error between requested and rendered arc sagitta (矢高).
SAGITTA_RELATIVE_LIMIT = 0.20
