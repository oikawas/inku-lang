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


class Box:
    """Physical space of an object's box: x in [0, W], y in [0, H], with the short side 1.

    Inside an object, positions are fractions of the box's width and height, while sizes and
    transform translations follow the box (PLUGIN §3.5). A tilted arc is made flat at the box
    center, shrunk if it would not fit before turning, then scaled back, turned and moved: an
    arc placed as it is would leave the box before turning and be dropped.
    """

    def __init__(self, w, h):
        s = min(w, h)
        self.W, self.H = w / s, h / s

    def bx(self, x):
        return x / self.W

    def by(self, y):
        return y / self.H

    def arc(self, p1, p2, s, bulge_left, fields, d3, num):
        """The statements of an arc from p1 to p2 (physical) with sagitta s, bulging left of travel (y down)."""
        (x1, y1), (x2, y2) = p1, p2
        c = math.hypot(x2 - x1, y2 - y1)
        th = math.degrees(math.atan2(y2 - y1, x2 - x1)) + (0 if bulge_left else 180)
        t = math.radians(th)
        mx, my = (x1 + x2) / 2, (y1 + y2) / 2
        cx, cy = mx + math.sin(t) * s / 2, my - math.cos(t) * s / 2       # box center of the turned arc
        k = math.ceil(max(1.0, c / (0.8 * self.W)) * 4) / 4                # shrink so the flat arc fits
        node = {"op": "emit", "fields": {"shape": ref("shape", "arc"), "movement": ref("movement", "place"),
                "position_x": d3(0.5), "position_y": d3(self.by(self.H / 2 + s / k / 2)),
                "chord": d3(c / k), "sagitta": d3(s / k), **fields}}
        transform = {"rotate_degrees": num(round(th, 2)),
                     "translate_x": num(round(self.bx(cx - self.W / 2), 4)),
                     "translate_y": num(round(self.by(cy - self.H / 2), 4))}
        if k != 1.0:
            transform.update(scale_x=num(k), scale_y=num(k))
        return {"op": "transform", "transform": transform, "body": [node]}
