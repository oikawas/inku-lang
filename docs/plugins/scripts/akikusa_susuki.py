"""Akikusa.Susuki (すすき), Akikusa.Obana (尾花) and Akikusa.SusukiField (すすき原).

Silver grass after the autumn grasses of Rinpa (Sakai Hōitsu, Suzuki Kiitsu) and the
Musashino screens: ears of fine spikelets bowed downwind, stems bending with the wind, long
blades arching from the root. Imported by build_v2.py, which reads WORDS_V2 (these words are
written as v2 definitions directly, two of them objects).
"""
import math

from helpers import ref, dec, num, Box


def d3(x):
    return dec(f"{x:.3f}")


def V(a=None, fq=None, q=None, sp=None):
    return {k: ref("variation", v) for k, v in [("fluctuation_amplitude", a), ("fluctuation_frequency", fq),
            ("fluctuation_quality", q), ("ink_spread", sp)] if v}


def C(c):
    return ref("color", c)


def T(t):
    return ref("touch", t)


# The ears are the most literal colour (gray), so a colour word on an object recolours them and the
# stems: 黄色の｛すすき｝ is gold in the evening light, 白い｛すすき｝ on a dark ground is Hōitsu's white.
EAR = {"color": C("gray"), "touch": T("watercolor"), **V("narrowly", "tightly", "undulating", "bleeding")}   # feathery edge
STEM = {"color": C("gray"), "touch": T("pen"), "thinness": ref("thinness", "fine"), **V("narrowly", "loosely", "swaying")}
LEAF = {"color": C("green"), "touch": T("gouache"), **V("narrowly", "loosely", "swaying")}
DRY_LEAF = {**LEAF, "color": C("yellow")}


def ear_arcs(node, lean, n, spread, length, curl):
    """(p1, p2, sagitta, bulge_left) of n spikelets in a narrow fan around lean (degrees from upright,
    + is right), all bowed downwind."""
    arcs = []
    for i in range(n):
        f = 2 * i / (n - 1) - 1
        a = lean + spread * f
        length_i = length * (0.78 + 0.22 * (1 - f * f))
        r = math.radians(a + curl * 0.35)
        arcs.append((node, (node[0] + length_i * math.sin(r), node[1] - length_i * math.cos(r)), length_i * curl / 100, lean >= 0))
    return arcs


def object_word(word_id, ja, en, body, counter):
    return {"schema": "inku.macro-definition.v2", "namespace": "Akikusa", "id": word_id, "names": {"ja": ja, "en": en},
            "kind": "object", "aspect": "1:1", "counter": counter, "version": "1.0.0",
            "parameters": {}, "components": {}, "body": body}


# A square box: in a non-square object box a transformed arc was not drawn (2026-10-31), so the
# plant stands in the middle of a square one.
BOX = Box(1, 1)


def arc(p1, p2, s, bulge_left, fields):
    return BOX.arc(p1, p2, s, bulge_left, fields, d3, num)


def clump(ear=EAR, lean=16):
    base = (0.50, 0.98)
    stems = [((0.46, 0.40), lean - 4, 0.30), ((0.62, 0.34), lean + 4, 0.32), ((0.34, 0.50), lean - 8, 0.26)]
    body = []
    for node, ear_lean, length in stems:
        body.append(arc(base, node, 0.05, False, STEM))                              # bowed downwind
        body += [arc(p1, p2, s, bl, ear) for p1, p2, s, bl in ear_arcs(node, ear_lean, 7, 20, length, 22)]
    leaves = [((0.12, 0.62), 0.10, False, LEAF), ((0.90, 0.70), 0.09, True, LEAF), ((0.74, 0.30), 0.05, False, LEAF),
              ((0.20, 0.86), 0.05, False, DRY_LEAF), ((0.30, 0.36), 0.05, True, LEAF)]
    body += [arc(base, end, s, bl, style) for end, s, bl, style in leaves]
    return body


def obana(ear=EAR, lean=16):
    node = (0.40, 0.42)
    body = [arc((0.46, 0.98), node, 0.05, False, STEM)]
    body += [arc(p1, p2, s, bl, ear) for p1, p2, s, bl in ear_arcs(node, lean, 11, 24, 0.40, 24)]
    body.append(arc((0.46, 0.98), (0.90, 0.60), 0.09, True, LEAF))
    body.append(arc((0.46, 0.98), (0.14, 0.72), 0.06, False, DRY_LEAF))
    return body


# ---- the field (a scene): plants along the bottom; every arc of a plant comes from cycle tables over the plant
FIELD = [  # base, ear node, lean, ear length; the order spreads any count across the row
    ((0.50, 0.99), (0.46, 0.52), 18, 0.24), ((0.22, 0.99), (0.19, 0.60), 14, 0.20), ((0.78, 0.99), (0.74, 0.56), 20, 0.22),
    ((0.36, 0.99), (0.33, 0.66), 16, 0.18), ((0.64, 0.99), (0.60, 0.62), 22, 0.20), ((0.10, 0.99), (0.08, 0.70), 12, 0.16),
    ((0.90, 0.99), (0.86, 0.68), 18, 0.17), ((0.56, 0.99), (0.54, 0.74), 24, 0.15)]


def arc_numbers(p1, p2, s, bulge_left):
    (x1, y1), (x2, y2) = p1, p2
    c = math.hypot(x2 - x1, y2 - y1)
    th = math.degrees(math.atan2(y2 - y1, x2 - x1)) + (0 if bulge_left else 180)
    t = math.radians(th)
    mx, my = (x1 + x2) / 2, (y1 + y2) / 2
    cx, cy = mx + math.sin(t) * s / 2, my - math.cos(t) * s / 2
    return {"th": round(th, 2), "tx": round(cx - 0.5, 4), "ty": round(cy - 0.5, 4), "c": c, "s": s, "y": 0.5 + s / 2}


def field(ear=EAR):
    index = "plant_index"
    plants = []
    for base, node, lean, length in FIELD:
        leaf_end = (base[0] + 0.16, base[1] - 0.20) if base[0] < 0.75 else (base[0] - 0.16, base[1] - 0.20)
        arcs = ([(base, node, 0.05, False, "stem")] + [(*a, "ear") for a in ear_arcs(node, lean, 5, 16, length, 22)]
                + [(base, leaf_end, 0.05, base[0] < 0.75, "leaf")])
        plants.append([arc_numbers(*a[:4]) | {"kind": a[4]} for a in arcs])
    body = []
    for j in range(len(plants[0])):
        column = [plant[j] for plant in plants]

        def table(key, f):
            return {"expr": "cycle", "index": {"expr": "local", "name": index}, "items": [f(p[key]) for p in column]}

        style = {"stem": STEM, "ear": ear, "leaf": LEAF}[column[0]["kind"]]
        node = {"op": "emit", "fields": {"shape": ref("shape", "arc"), "movement": ref("movement", "place"),
                "position_x": d3(0.5), "position_y": table("y", d3), "chord": table("c", d3), "sagitta": table("s", d3), **style}}
        body.append({"op": "transform", "transform": {"rotate_degrees": table("th", num), "translate_x": table("tx", num),
                     "translate_y": table("ty", num)}, "body": [node]})
    return [{"op": "repeat", "count": {"expr": "parameter", "name": "plant_count"}, "maximum": 8, "index": index, "body": body}]


def build(ear=EAR):
    field_word = {"schema": "inku.macro-definition.v2", "namespace": "Akikusa", "id": "SusukiField",
                  "names": {"ja": ["すすき原", "芒原"], "en": ["silver grass field", "susuki field"]}, "kind": "scene",
                  "version": "1.0.0",
                  "parameters": {"plant_count": {"type": "integer", "receives": "count", "minimum": 1, "maximum": 8,
                                                 "omitted": [5, 6], "counter": "long"}},
                  "components": {}, "body": field(ear)}
    return {
        "Susuki": object_word("Susuki", ["すすき", "芒"], ["silver grass", "susuki"], clump(ear), "long"),
        "Obana": object_word("Obana", ["尾花"], ["silver grass plume", "obana"], obana(ear), "long"),
        "SusukiField": field_word,
    }


WORDS_V2 = build()
