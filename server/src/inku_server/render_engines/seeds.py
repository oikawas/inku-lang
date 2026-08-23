"""Host-owned issuance of non-deterministic render seeds."""

from __future__ import annotations

import secrets


def new_render_seed() -> int:
    """Issue a JavaScript-safe seed for one render performance."""

    return secrets.randbits(53)
