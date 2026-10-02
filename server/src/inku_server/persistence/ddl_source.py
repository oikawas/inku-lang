"""The shared selection rule for a single saved instruction document."""

from __future__ import annotations

LEGACY_EXPANDED_ORIGIN = "legacy_expanded"
# Unicode White_Space, explicitly frozen for Server and Android agreement.
_SPACE_CODEPOINTS = (
    *range(0x0009, 0x000E), 0x0020, 0x0085, 0x00A0, 0x1680,
    *range(0x2000, 0x200B), 0x2028, 0x2029, 0x202F, 0x205F, 0x3000,
)
DDL_WHITESPACE = frozenset(chr(value) for value in _SPACE_CODEPOINTS)


def has_ddl_body(value: str | None) -> bool:
    return value is not None and any(character not in DDL_WHITESPACE for character in value)


def select_ddl(ddl: str | None, expanded_ddl: str | None) -> tuple[str | None, str | None]:
    """Select without trimming, normalizing, or compiling either document."""
    if has_ddl_body(ddl) or not has_ddl_body(expanded_ddl):
        return ddl, None
    return expanded_ddl, LEGACY_EXPANDED_ORIGIN
