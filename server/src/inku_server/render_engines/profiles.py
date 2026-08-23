"""Implementation-neutral SVG profile contract for render-engine hosts."""

from __future__ import annotations

SVG_PROFILES = frozenset({"display", "editable", "compat"})


def normalize_svg_profile(svg_profile: str | None) -> str:
    """Return the canonical profile name or reject an unsupported profile."""

    profile = (svg_profile or "display").strip().lower()
    if profile not in SVG_PROFILES:
        raise ValueError(f"unsupported svg profile: {svg_profile}")
    return profile
