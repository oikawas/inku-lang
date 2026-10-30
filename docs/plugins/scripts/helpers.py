"""Small builders for MacroDefinition expressions, shared by the word scripts.

The word scripts first build each definition in an internal form (a heading and
an alias, as the first examples were written); build_v2.py turns that into
inku.macro-definition.v2 with its id, names and kind.
"""
import math


def ref(category, word_id):
    return {"expr": "semantic_ref", "category": category, "id": word_id}


def dec(value):
    return {"expr": "exact_decimal", "value": value}


def num(value):
    return {"expr": "number", "value": value}


def loc(name):
    return {"expr": "local", "name": name}


def cyc(index, items):
    return {"expr": "cycle", "index": index if isinstance(index, dict) else loc(index), "items": items}


def definition(heading, body, params=None, alias=None, version="1.0.0"):
    """A definition in the internal form; build_v2.py rewrites it as v2."""
    word = {"namespace": "Water", "heading": heading, "version": version,
            "parameters": params or {}, "components": {}, "body": body}
    if alias:
        word["aliases"] = [alias]
    return word


def arc_circle(p1, p2, s, bulge_left=True):
    """Center, radius and apex of the arc from p1 to p2 with sagitta s (y grows downward)."""
    (x1, y1), (x2, y2) = p1, p2
    c = math.hypot(x2 - x1, y2 - y1)
    mx, my = (x1 + x2) / 2, (y1 + y2) / 2
    ux, uy = (x2 - x1) / c, (y2 - y1) / c
    nx, ny = (uy, -ux)                      # the left of travel
    if not bulge_left:
        nx, ny = -nx, -ny
    radius = (c * c / 4 + s * s) / (2 * s)
    apex = (mx + nx * s, my + ny * s)
    return (apex[0] - nx * radius, apex[1] - ny * radius), radius, apex


def arc_x_at(p1, p2, s, bulge_left, y):
    """The x where that arc crosses height y, or None."""
    (cx, cy), radius, apex = arc_circle(p1, p2, s, bulge_left)
    d = radius * radius - (y - cy) ** 2
    if d < 0:
        return None
    mx, my = (p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2
    nx, ny = apex[0] - mx, apex[1] - my
    xs = [x for x in (cx + math.sqrt(d), cx - math.sqrt(d)) if (x - mx) * nx + (y - my) * ny >= -1e-9]
    return min(xs, key=lambda x: abs(x - apex[0])) if xs else None
