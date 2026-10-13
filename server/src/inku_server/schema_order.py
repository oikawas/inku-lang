"""Write a schema's properties in the order it names, for every sender but Gemini.

The core's JSON keeps no key order, so a schema arrives with its properties in
name order; a schema whose order matters names it in `propertyOrdering` (today
only the composition reading's, thesis first). The Gemini projection already
writes properties in that order. Every other sender used to pass the name order
on, so GPT, Claude and the rest were sent the reading with thesis last, unlike
what the prototype and the C5 measurement sent (the draw session's request, the
author's choice of 2026-10-13). Here nothing is projected or dropped: every key
and word stays, `propertyOrdering` included, and a schema without one comes
back key for key as it was.
"""

from __future__ import annotations

from typing import Any

# Keys whose value maps names to schemas rather than being a schema itself, so
# a property that happens to be called "properties" is not read as a keyword.
_NAMED_SCHEMA_MAPS = {"properties", "$defs", "definitions", "patternProperties"}


def ordered_schema(value: Any, *, named: bool = False) -> Any:
    """The schema with each object's properties in its propertyOrdering, nested ones too.

    Names the ordering leaves out follow in their present order.
    """
    if isinstance(value, list):
        return [ordered_schema(item) for item in value]
    if not isinstance(value, dict):
        return value
    if named:
        return {name: ordered_schema(item) for name, item in value.items()}
    result = {key: ordered_schema(item, named=key in _NAMED_SCHEMA_MAPS) for key, item in value.items()}
    ordering, properties = result.get("propertyOrdering"), result.get("properties")
    if isinstance(ordering, list) and isinstance(properties, dict):
        first = [name for name in ordering if name in properties]
        result["properties"] = {**{name: properties[name] for name in first},
                                **{name: item for name, item in properties.items() if name not in first}}
    return result
