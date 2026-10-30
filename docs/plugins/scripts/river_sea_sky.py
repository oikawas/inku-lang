"""Water.River (川), Water.Sea (海), Sky.Clouds (雲), Sky.Heavens (大空), Sky.Rain (雨) 2.0.0 and Sky.Snow (雪).

Imported by build_v2.py, which reads WORDS.
"""
import math
from helpers import ref, dec, num, loc, cyc, definition, arc_circle, arc_x_at

def d3(x): return dec(f"{x:.3f}")
def ci(name, values, f): return cyc(name, [f(v) for v in values])
def V(a=None, fq=None, q=None, sp=None):
    return {k: ref("variation", v) for k, v in [("fluctuation_amplitude", a), ("fluctuation_frequency", fq),
            ("fluctuation_quality", q), ("ink_spread", sp)] if v}
def emit(**fields):
    f = {"movement": ref("movement", "place")}; f.update(fields)
    return {"op": "emit", "binding": None, "fields": f}
def turn(deg, node, tx=None, ty=None):
    t = {"rotate_degrees": num(deg)}
    if tx is not None: t["translate_x"] = tx
    if ty is not None: t["translate_y"] = ty
    return {"op": "transform", "transform": t, "body": [node]}
def count_param(lo, hi, omitted, counter):
    return {"type": "integer", "receives": "count", "minimum": lo, "maximum": hi, "omitted": omitted, "counter": counter}
def rep(param, maximum, index, body):
    return {"op": "repeat", "count": {"expr": "parameter", "name": param}, "maximum": maximum, "index": index, "body": body}
def choose(binding, n, body):
    return {"op": "vary", "binding": binding, "domain": binding, "choices": [{"expr": "integer", "value": i} for i in range(n)], "body": body}
def C(c): return ref("color", c)
def T(t): return ref("touch", t)
def scatter(shape, count, **fields):
    f = {"shape": ref("shape", shape), "movement": ref("movement", "scatter"), "count": count}; f.update(fields)
    return {"op": "emit", "binding": None, "fields": f}

# ---------------------------------------------------------------- Sky.Clouds (suyari-gasumi)
BANDS = [(0.10, 0.62, 0.20, 0.072), (0.38, 0.92, 0.31, 0.064), (0.06, 0.50, 0.43, 0.056), (0.50, 0.88, 0.54, 0.052), (0.18, 0.56, 0.64, 0.048)]
B = "band_index"
band_line = {"color": C("gray"), "touch": T("brush_thin"), **V("narrowly", "loosely", "swaying")}
mid = [(xl + xr) / 2 for xl, xr, _, _ in BANDS]; width = [xr - xl for xl, xr, _, _ in BANDS]
top = [yc - h / 2 for _, _, yc, h in BANDS]; bot = [yc + h / 2 for _, _, yc, h in BANDS]
cap = [h for *_, h in BANDS]                       # chord of the end caps = band height
cap_s = [h / 2 for *_, h in BANDS]
lcap_x = [xl - h / 4 for xl, _, _, h in BANDS]; rcap_x = [xr + h / 4 for _, xr, _, h in BANDS]
cap_y = [yc + h / 4 for _, _, yc, h in BANDS]
def cap_arc(xs):
    return emit(shape=ref("shape", "arc"), position_x=ci(B, xs, d3), position_y=ci(B, cap_y, d3),
                chord=ci(B, cap, d3), sagitta=ci(B, cap_s, d3), **band_line)
clouds_body = rep("band_count", 5, B, [
    emit(shape=ref("shape", "line"), position_x=ci(B, mid, d3), position_y=ci(B, top, d3), length=ci(B, width, d3), **band_line),
    emit(shape=ref("shape", "line"), position_x=ci(B, mid, d3), position_y=ci(B, bot, d3), length=ci(B, width, d3), **band_line),
    turn(-90, cap_arc(lcap_x)), turn(90, cap_arc(rcap_x)),
    emit(shape=ref("shape", "line"), position_x=ci(B, mid, d3), position_y=ci(B, [yc for _, _, yc, _ in BANDS], d3),
         length=ci(B, [w * 0.82 for w in width], d3), color=C("yellow"), touch=T("brush_thick"),
         **V("narrowly", "loosely", "swaying", "bleeding"))])
CL_M = [1.0, -1.0, 1.0, -1.0]; CL_T = [0.000, 0.040, 0.080, -0.020]
clouds = definition("Clouds", [choose("cloud_lie", 4, [{"op": "transform",
    "transform": {"scale_x": ci("cloud_lie", CL_M, num), "translate_y": ci("cloud_lie", CL_T, num)}, "body": [clouds_body]}])],
    params={"band_count": count_param(1, 5, [3, 4], "long")}, alias="雲")

# ---------------------------------------------------------------- Sky.Heavens (ichimonji bokashi)
HY = [0.010, 0.022, 0.036, 0.052, 0.070, 0.092, 0.118, 0.148, 0.184, 0.226, 0.276, 0.334]
H = "stroke_index"
heavens = definition("Heavens", [rep("stroke_count", 12, H, [emit(
    shape=ref("shape", "line"), position_x=d3(0.5), position_y=ci(H, HY, d3),
    length=ci(H, [0.98] * 9 + [0.90, 0.82, 0.74], d3),
    color=ci(H, ["blue"] * 6 + ["gray"] * 6, C),
    touch=ci(H, ["brush_thick"] * 3 + ["brush_thin"] * 9, T),
    **V("narrowly", "loosely", "swaying", "bleeding"))])],
    params={"stroke_count": count_param(1, 12, [8, 9, 10], "long")}, alias="空")

# ---------------------------------------------------------------- Sky.Rain (Hiroshige's sudden shower, on the wind)
haze = {"color": C("gray"), "touch": T("brush_thin"), **V("narrowly", "loosely", "swaying", "bleeding")}
RAIN_CLOUD = [(0.500, 0.010, 0.98, "brush_thick"), (0.480, 0.024, 0.94, "brush_thin"), (0.530, 0.042, 0.88, "brush_thin"),
              (0.460, 0.064, 0.80, "brush_thin"), (0.550, 0.092, 0.70, "brush_thin")]
RAIN_MIST = [(0.30, 0.740, 0.46), (0.66, 0.765, 0.52), (0.46, 0.800, 0.34)]
WIND = [8.0, -8.0, 12.0, -12.0]                    # the middle layer's slant; far is 3 degrees less, near 5 more
def slanted(offset, node):
    return {"op": "transform", "transform": {"rotate_degrees": ci("rain_wind", [w + offset * (1 if w > 0 else -1) for w in WIND], num)},
            "body": [node]}
rain = definition("Rain", [
    *[emit(shape=ref("shape", "line"), position_x=d3(x), position_y=d3(y), length=d3(l), color=C("gray"), touch=T(t),
           **V("narrowly", "loosely", "swaying", "bleeding")) for x, y, l, t in RAIN_CLOUD],
    choose("rain_wind", 4, [
        slanted(-3, scatter("line", {"expr": "integer", "value": 30}, angle=ref("angle", "vertical"), length=d3(0.240),
                            color=C("gray"), touch=T("silverpoint"), thinness=ref("thinness", "extra_fine"))),
        slanted(0, scatter("line", {"expr": "parameter", "name": "rain_count"}, angle=ref("angle", "vertical"), length=d3(0.380),
                           color=C("gray"), touch=T("pen"), thinness=ref("thinness", "fine"))),
        slanted(5, scatter("line", {"expr": "integer", "value": 12}, angle=ref("angle", "vertical"), length=d3(0.560),
                           color=C("blue"), touch=T("pen"), thinness=ref("thinness", "fine")))]),
    *[emit(shape=ref("shape", "line"), position_x=d3(x), position_y=d3(y), length=d3(l), thinness=ref("thinness", "extra_fine"), **haze)
      for x, y, l in RAIN_MIST]],
    params={"rain_count": count_param(1, 80, [36, 42, 48], "long")}, alias="雨", version="2.0.0")

# ---------------------------------------------------------------- Sky.Snow (gofun flakes)
flake = {"color": C("white"), "touch": T("brush_thick"), **V(sp="bleeding")}
snow = definition("Snow", [
    scatter("point", {"expr": "parameter", "name": "flake_count"}, radius=d3(0.005), **flake),
    scatter("point", {"expr": "integer", "value": 14}, radius=d3(0.010), **flake),
    scatter("point", {"expr": "integer", "value": 6}, radius=d3(0.017), **flake)],
    params={"flake_count": count_param(1, 80, [36, 42, 48], "general")}, alias="雪")

# ---------------------------------------------------------------- Water.River (receding, bending)
LB = ((0.08, 0.98), (0.52, 0.30)); RB = ((0.90, 0.98), (0.60, 0.30)); LS, RS, BL = 0.10, 0.14, False
def tilted(p1, p2, s, bulge_left, **fields):
    (x1, y1), (x2, y2) = p1, p2; c = math.hypot(x2 - x1, y2 - y1)
    th = math.degrees(math.atan2(y2 - y1, x2 - x1)) + (0 if bulge_left else 180)
    t = math.radians(th); mx, my = (x1 + x2) / 2, (y1 + y2) / 2
    cx, cy = mx + math.sin(t) * s / 2, my - math.cos(t) * s / 2
    node = emit(shape=ref("shape", "arc"), position_x=d3(0.5), position_y=d3(0.5 + s / 2), chord=d3(c), sagitta=d3(s), **fields)
    return turn(round(th, 2), node, num(round(cx - 0.5, 4)), num(round(cy - 0.5, 4)))
bank = {"color": C("gray"), "touch": T("brush_thick"), **V("narrowly", "loosely", "swaying")}
ROWS = [0.335, 0.37, 0.415, 0.47, 0.535, 0.61, 0.70, 0.80, 0.91]          # far to near
ORDER = [8, 4, 1, 6, 2, 7, 0, 5, 3]                                       # any count spreads from far to near
rx, rl = [], []
for k in ORDER:
    y = ROWS[k]; xl = arc_x_at(LB[0], LB[1], LS, BL, y); xr = arc_x_at(RB[0], RB[1], RS, BL, y)
    rx.append((xl + xr) / 2); rl.append((xr - xl) * 0.76)
R = "flow_index"
near = [ORDER.index(k) for k in range(9)]
river_body = [tilted(LB[0], LB[1], LS, BL, **bank), tilted(RB[0], RB[1], RS, BL, **bank),
    rep("flow_count", 9, R, [emit(shape=ref("shape", "line"), position_x=ci(R, rx, d3), position_y=ci(R, [ROWS[k] for k in ORDER], d3),
        length=ci(R, rl, d3), color=ci(R, ["blue" if k % 3 != 2 else "gray" for k in ORDER], C), touch=T("brush_thin"),
        fluctuation_amplitude=ref("variation", "narrowly"),
        fluctuation_frequency=ci(R, ["tightly" if k < 3 else "loosely" for k in ORDER], lambda v: ref("variation", v)),
        fluctuation_quality=ref("variation", "undulating"))])]
RV_M = [1.0, -1.0, 1.0, -1.0]; RV_T = [0.000, 0.000, -0.020, -0.020]
river = definition("River", [choose("river_lie", 4, [{"op": "transform",
    "transform": {"scale_x": ci("river_lie", RV_M, num), "translate_y": ci("river_lie", RV_T, num)}, "body": river_body}])],
    params={"flow_count": count_param(1, 9, [6, 7], "long")}, alias="川")

# ---------------------------------------------------------------- Water.Sea (to the horizon)
SROWS = [0.44, 0.48, 0.53, 0.59, 0.66, 0.74, 0.83, 0.92]                 # far to near
SORDER = [7, 3, 5, 1, 6, 2, 4, 0]
W = "wave_index"
crest_r = [0.012 + 0.035 * k / 7 for k in SORDER]
def crest(xs, color):
    return emit(shape=ref("shape", "arc"), position_x=ci(W, xs, d3), position_y=ci(W, [SROWS[k] - 0.004 for k in SORDER], d3),
                chord=ci(W, [2 * r for r in crest_r], d3), sagitta=ci(W, [r * 0.45 for r in crest_r], d3),
                color=C(color), touch=T("brush_thin"), **V("narrowly", "loosely", "swaying"))
sea_body = [emit(shape=ref("shape", "line"), position_x=d3(0.5), position_y=d3(0.40), length=d3(0.96),
                 color=C("gray"), touch=T("pen"), thinness=ref("thinness", "fine")),
    rep("wave_count", 8, W, [
        emit(shape=ref("shape", "line"), position_x=d3(0.5), position_y=ci(W, [SROWS[k] for k in SORDER], d3), length=d3(0.94),
             color=ci(W, ["blue" if k % 2 else "gray" for k in SORDER], C), touch=T("brush_thin"),
             fluctuation_amplitude=ref("variation", "narrowly"),
             fluctuation_frequency=ci(W, ["tightly" if k < 3 else "loosely" for k in SORDER], lambda v: ref("variation", v)),
             fluctuation_quality=ref("variation", "undulating")),
        crest([[0.22, 0.34, 0.27, 0.19, 0.31, 0.24, 0.36, 0.21][k] for k in SORDER], "gray"),
        crest([[0.70, 0.62, 0.78, 0.66, 0.74, 0.81, 0.64, 0.72][k] for k in SORDER], "blue")])]
SEA_T = [0.000, -0.040, -0.070]
sea = definition("Sea", [choose("sea_lie", 3, [{"op": "transform", "transform": {"translate_y": ci("sea_lie", SEA_T, num)}, "body": sea_body}])],
    params={"wave_count": count_param(1, 8, [5, 6], "long")}, alias="海")

for word in (clouds, heavens, rain, snow):
    word["namespace"] = "Sky"
WORDS = {"River": river, "Sea": sea, "Clouds": clouds, "Heavens": heavens, "Rain": rain, "Snow": snow}
