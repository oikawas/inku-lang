"""Portable SVG subset validation for the ``compat`` export profile.

This module is the one policy shared by the renderer and the structural checker.
It deliberately accepts only structures emitted by the compat renderer: no
filters, clip paths, scripts, external resources, or implicit SVG extensions.
"""

from __future__ import annotations

from dataclasses import dataclass
from xml.etree import ElementTree


SVG_NAMESPACE = "http://www.w3.org/2000/svg"


class CompatSvgViolation(ValueError):
    """Raised when an SVG falls outside the compat portable subset."""


@dataclass(frozen=True)
class PortableSvgPolicy:
    namespace: str
    attributes_by_element: dict[str, frozenset[str]]
    reference_attributes: frozenset[str]


_COMMON_PAINT_ATTRIBUTES = frozenset(
    {
        "id",
        "class",
        "opacity",
        "fill",
        "fill-opacity",
        "fill-rule",
        "stroke",
        "stroke-opacity",
        "stroke-width",
        "stroke-linecap",
        "stroke-linejoin",
        "stroke-miterlimit",
        "stroke-dasharray",
        "stroke-dashoffset",
        "transform",
    }
)

# This is intentionally an explicit, per-element allowlist. It is not a
# general SVG sanitizer: unknown SVG is rejected rather than guessed safe.
PORTABLE_SVG_POLICY = PortableSvgPolicy(
    namespace=SVG_NAMESPACE,
    attributes_by_element={
        "svg": frozenset({"baseProfile", "height", "version", "viewBox", "width"}),
        "title": frozenset(),
        "desc": frozenset(),
        "metadata": frozenset({"id"}),
        "defs": frozenset(),
        "g": _COMMON_PAINT_ATTRIBUTES,
        "rect": _COMMON_PAINT_ATTRIBUTES
        | frozenset({"height", "rx", "ry", "width", "x", "y"}),
        "circle": _COMMON_PAINT_ATTRIBUTES | frozenset({"cx", "cy", "r"}),
        "ellipse": _COMMON_PAINT_ATTRIBUTES | frozenset({"cx", "cy", "rx", "ry"}),
        "line": _COMMON_PAINT_ATTRIBUTES | frozenset({"x1", "x2", "y1", "y2"}),
        "polyline": _COMMON_PAINT_ATTRIBUTES | frozenset({"points"}),
        "polygon": _COMMON_PAINT_ATTRIBUTES | frozenset({"points"}),
        "path": _COMMON_PAINT_ATTRIBUTES | frozenset({"d"}),
        "linearGradient": frozenset({"id", "x1", "x2", "y1", "y2"}),
        "radialGradient": frozenset({"id"}),
        "stop": frozenset({"offset", "stop-color", "stop-opacity"}),
        "pattern": frozenset(
            {
                "height",
                "id",
                "patternContentUnits",
                "patternTransform",
                "patternUnits",
                "width",
                "x",
                "y",
            }
        ),
    },
    reference_attributes=frozenset({"fill"}),
)


def _split_name(name: str) -> tuple[str | None, str]:
    if name.startswith("{"):
        namespace, local = name[1:].split("}", 1)
        return namespace, local
    return None, name


def _violation(message: str) -> CompatSvgViolation:
    return CompatSvgViolation(f"compat SVG portable subset violation: {message}")


def _reference_target(value: str) -> str | None:
    if not value.startswith("url("):
        return None
    if not (value.startswith("url(#") and value.endswith(")")):
        raise _violation(f"external or malformed reference {value!r}")
    target = value[5:-1]
    if not target:
        raise _violation("empty fragment reference")
    return target


def validate_compat_svg(svg: str) -> None:
    """Reject SVG XML outside :data:`PORTABLE_SVG_POLICY`.

    The checker is fail-closed. It also resolves the subset's only reference
    form (``fill=url(#id)``), so a valid spelling cannot point outside the file
    or to a missing definition.
    """

    try:
        root = ElementTree.fromstring(svg)
    except ElementTree.ParseError as exc:
        raise _violation(f"invalid XML: {exc}") from exc

    root_namespace, root_name = _split_name(root.tag)
    if root_namespace != PORTABLE_SVG_POLICY.namespace or root_name != "svg":
        raise _violation("root must be an SVG-namespace <svg>")

    ids: set[str] = set()
    references: list[str] = []
    for element in root.iter():
        namespace, name = _split_name(element.tag)
        if namespace != PORTABLE_SVG_POLICY.namespace:
            raise _violation(f"disallowed element namespace for {name!r}")
        allowed_attributes = PORTABLE_SVG_POLICY.attributes_by_element.get(name)
        if allowed_attributes is None:
            raise _violation(f"disallowed element <{name}>")
        for raw_attribute, value in element.attrib.items():
            attribute_namespace, attribute = _split_name(raw_attribute)
            if attribute_namespace is not None:
                raise _violation(f"disallowed attribute namespace on {name!r}")
            if attribute not in allowed_attributes:
                raise _violation(f"disallowed attribute {attribute!r} on <{name}>")
            target = _reference_target(value)
            if target is not None:
                if attribute not in PORTABLE_SVG_POLICY.reference_attributes:
                    raise _violation(f"reference is not allowed in {attribute!r}")
                references.append(target)
            if attribute == "id":
                if not value or value in ids:
                    raise _violation(f"missing or duplicate id {value!r}")
                ids.add(value)

    for target in references:
        if target not in ids:
            raise _violation(f"reference target #{target} is absent")
