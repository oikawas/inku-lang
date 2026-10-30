"""Water.Stream (水流) 1.0.0, Water.Ripples (波紋) 3.0.0 and Water.Rings (水輪) 2.0.0.

Imported by build_v2.py, which reads WORDS.
"""
import math
from helpers import ref, dec, num, loc, cyc, definition

def d3(x): return dec(f"{x:.3f}")
def ci(name, values, f): return cyc(name, [f(v) for v in values])
def V(a=None, fq=None, q=None, sp=None):
    return {k: ref("variation", v) for k, v in [("fluctuation_amplitude", a), ("fluctuation_frequency", fq),
            ("fluctuation_quality", q), ("ink_spread", sp)] if v}
def emit(**fields):
    f = {"movement": ref("movement", "place")}; f.update(fields)
    return {"op": "emit", "binding": None, "fields": f}
def flip(node): return {"op": "transform", "transform": {"rotate_degrees": num(180)}, "body": [node]}
def count_param(lo, hi, omitted, counter):
    return {"type": "integer", "receives": "count", "minimum": lo, "maximum": hi, "omitted": omitted, "counter": counter}

# ---- broken ring: an upper and a lower arc of the same span, turned together about the ring center
def ring_tables(radii, spans, dys):
    up_y, lo_y, chord, sag = [], [], [], []
    for r, span, dy in zip(radii, spans, dys):
        h = math.radians(span / 2)
        c, s = 2 * r * math.sin(h), r * (1 - math.cos(h))
        up_y.append(0.5 + dy - r * math.cos(h))
        lo_y.append(0.5 + dy + r * math.cos(h) + s)   # emitted here, then turned 180 about its own box
        chord.append(c); sag.append(s)
    return up_y, lo_y, chord, sag

def ring_set(count_name, radii, spans, turns, dys, style):
    up_y, lo_y, chord, sag = ring_tables(radii, spans, dys)
    I = "ring_index"
    common = {"shape": ref("shape", "arc"), "position_x": d3(0.5),
              "chord": ci(I, chord, d3), "sagitta": ci(I, sag, d3)}
    common.update(style)
    upper = emit(**common, position_y=ci(I, up_y, d3))
    lower = flip(emit(**common, position_y=ci(I, lo_y, d3)))
    return {"op": "repeat", "count": {"expr": "parameter", "name": count_name}, "maximum": 6, "index": I,
            "body": [{"op": "transform", "transform": {"rotate_degrees": ci(I, turns, num)}, "body": [upper, lower]}]}

def ring_style(touches): return {
    "color": cyc("ring_index", [ref("color", c) for c in ["blue", "blue", "blue", "gray", "gray", "gray"]]),
    "touch": cyc("ring_index", [ref("touch", t) for t in touches]),
    "fluctuation_amplitude": cyc("ring_index", [ref("variation", a) for a in ["narrowly", "narrowly", "broadly", "broadly", "broadly", "broadly"]]),
    "fluctuation_frequency": ref("variation", "loosely"),
    "fluctuation_quality": ref("variation", "swaying"),
}
def drop(x, y):
    return emit(shape=ref("shape", "point"), position_x=d3(x), position_y=d3(y), radius=d3(0.007),
                color=ref("color", "blue"), touch=ref("touch", "brush_thick"), **V(sp="bleeding"))

# ---- Water.Ripples 3.0.0 (from above)
RIP_CX = [0.500, 0.380, 0.620, 0.440, 0.580]; RIP_CY = [0.560, 0.620, 0.580, 0.680, 0.460]
ripples = definition("Ripples", [{
    "op": "vary", "binding": "ripple_center", "domain": "ripple_center",
    "choices": [{"expr": "integer", "value": i} for i in range(5)],
    "body": [{"op": "vary", "binding": "ripple_turn", "domain": "ripple_turn",
              "choices": [num(v) for v in [0.0, 40.0, 80.0, 120.0, 160.0]],
              "body": [{"op": "transform",
                        "transform": {"translate_x": ci("ripple_center", [x - 0.5 for x in RIP_CX], num),
                                      "translate_y": ci("ripple_center", [y - 0.5 for y in RIP_CY], num),
                                      "rotate_degrees": loc("ripple_turn")},
                        "body": [drop(0.5, 0.5),
                                 ring_set("ring_count", [0.035, 0.070, 0.110, 0.155, 0.205, 0.260],
                                          [180, 180, 150, 135, 120, 100], [0, 30, -8, 14, -22, 34],
                                          [0] * 6, ring_style(["brush_thin", "brush_thick", "brush_thin", "brush_thin", "brush_thin", "brush_thin"]))]}]}]}],
    params={"ring_count": count_param(1, 6, [4, 5], "general")}, alias="波紋", version="3.0.0")

# ---- Water.Rings 2.0.0 (across the water)
RING_TX = [0.000, -0.070, 0.070, -0.040, 0.050]; RING_TY = [0.200, 0.160, 0.240, 0.260, 0.120]
REFLECT = [(0.170, 0.505, 0.090), (0.830, 0.515, 0.080), (0.230, 0.545, 0.140), (0.780, 0.560, 0.120), (0.500, 0.600, 0.220)]
reflections = [emit(shape=ref("shape", "line"), position_x=d3(x), position_y=d3(y), length=d3(l),
                    color=ref("color", "gray"), touch=ref("touch", "brush_thin"), thinness=ref("thinness", "fine"),
                    **V("narrowly", "loosely", "swaying")) for x, y, l in REFLECT]
rings = definition("Rings", [{
    "op": "vary", "binding": "ring_place", "domain": "ring_place",
    "choices": [{"expr": "integer", "value": i} for i in range(5)],
    "body": [{"op": "vary", "binding": "ring_tilt", "domain": "ring_tilt",
              "choices": [num(v) for v in [-3.0, -1.5, 0.0, 1.5, 3.0]],
              "body": [{"op": "transform",
                        "transform": {"translate_x": ci("ring_place", RING_TX, num),
                                      "translate_y": ci("ring_place", RING_TY, num),
                                      "rotate_degrees": loc("ring_tilt")},
                        "body": [{"op": "transform", "transform": {"scale_x": num(1.05), "scale_y": num(0.34)},
                                  "body": [drop(0.5, 0.5),
                                           ring_set("ring_count", [0.050, 0.095, 0.145, 0.200, 0.260, 0.320],
                                                    [180, 180, 150, 135, 120, 100], [0, 30, -8, 14, -22, 34],
                                                    [0.0, 0.006, 0.014, 0.024, 0.036, 0.050], ring_style(["brush_thin"] * 6))]}]
                        + reflections}]}]}],
    params={"ring_count": count_param(1, 6, [4, 5], "general")}, alias="水輪", version="2.0.0")

# ---- Water.Stream 1.0.0
HALF = 0.40; END_SP = 0.016; BASE = 0.090; LEAN = 0.006
ORDER = [0, 1, -1, 2, -2, 3, -3, 4, -4, 5, -5, 6]
ys = [0.5 + o * END_SP for o in ORDER]
sl = [BASE - o * LEAN for o in ORDER]          # left half bulges up: upper lines more
sr = [BASE + o * LEAN for o in ORDER]          # right half bulges down: lower lines more
L = "line_index"
TOUCH = ["brush_thick", "brush_thin", "brush_thin", "brush_thin", "brush_thick", "brush_thin",
         "brush_thin", "brush_thin", "brush_thin", "brush_thick", "brush_thin", "brush_thin"]
COLOR = ["blue", "blue", "blue", "blue", "gray", "blue", "gray", "gray", "blue", "gray", "blue", "gray"]
line_style = {"color": ci(L, COLOR, lambda c: ref("color", c)), "touch": ci(L, TOUCH, lambda t: ref("touch", t)),
              **V("narrowly", "loosely", "swaying")}
def half_arcs(y_left, y_right, s_left, s_right, style):
    left = emit(shape=ref("shape", "arc"), position_x=d3(0.5 - HALF / 2), position_y=y_left,
                chord=d3(HALF), sagitta=s_left, **style)
    right = flip(emit(shape=ref("shape", "arc"), position_x=d3(0.5 + HALF / 2), position_y=y_right,
                      chord=d3(HALF), sagitta=s_right, **style))
    return [left, right]
core = half_arcs(d3(0.5), d3(0.5 + BASE), d3(BASE), d3(BASE),
                 {"color": ref("color", "blue"), "touch": ref("touch", "brush_thick"),
                  **V("narrowly", "loosely", "swaying", "bleeding")})
lines = {"op": "repeat", "count": {"expr": "parameter", "name": "line_count"}, "maximum": 12, "index": L,
         "body": half_arcs(ci(L, ys, d3), ci(L, [y + s for y, s in zip(ys, sr)], d3), ci(L, sl, d3), ci(L, sr, d3), line_style)}
# eddy: a spiral of five semicircles around (0.5, 0.5), each half a turn smaller
def spiral(R=0.050, dl=0.010):
    out, r = [], R
    st = {"color": ref("color", "blue"), "touch": ref("touch", "brush_thin"), **V("narrowly", "loosely", "swaying")}
    for k in range(5):
        if k % 2 == 0:
            out.append(emit(shape=ref("shape", "arc"), position_x=d3(0.5), position_y=d3(0.5), chord=d3(2 * r), sagitta=d3(r), **st))
        else:
            out.append(flip(emit(shape=ref("shape", "arc"), position_x=d3(0.5 + dl), position_y=d3(0.5 + r), chord=d3(2 * r), sagitta=d3(r), **st)))
        r -= dl
    return out
eddy = {"parameters": {"dx": {"type": "number"}, "dy": {"type": "number"}, "turn": {"type": "number"}, "size": {"type": "number"}},
        "body": [{"op": "transform", "transform": {"translate_x": {"expr": "parameter", "name": "dx"},
                                                   "translate_y": {"expr": "parameter", "name": "dy"},
                                                   "rotate_degrees": {"expr": "parameter", "name": "turn"},
                                                   "scale_x": {"expr": "parameter", "name": "size"},
                                                   "scale_y": {"expr": "parameter", "name": "size"}},
                  "body": spiral()}]}
def use_eddy(dx, dy, turn, size):
    return {"op": "use", "component": "eddy", "arguments": {"dx": num(dx), "dy": num(dy), "turn": num(turn), "size": num(size)}}
# six ways for the stream to lie: tilt, mirror, and a small rise or fall
SR = [-12.0, 10.0, -6.0, 14.0, -16.0, 4.0]; SM = [1.0, 1.0, -1.0, -1.0, 1.0, -1.0]; ST = [0.000, 0.040, -0.040, 0.020, 0.050, -0.050]
stream = definition("Stream", [{
    "op": "vary", "binding": "stream_lie", "domain": "stream_lie",
    "choices": [{"expr": "integer", "value": i} for i in range(6)],
    "body": [{"op": "transform",
              "transform": {"rotate_degrees": ci("stream_lie", SR, num), "scale_x": ci("stream_lie", SM, num),
                            "translate_y": ci("stream_lie", ST, num)},
              "body": core + [lines, use_eddy(-0.270, 0.100, 20.0, 1.0), use_eddy(0.210, -0.100, 200.0, 0.8)]}]}],
    params={"line_count": count_param(1, 12, [7, 8, 9], "long")}, alias="水流")
stream["components"] = {"eddy": eddy}
WORDS = {"Stream": stream, "Ripples": ripples, "Rings": rings}
