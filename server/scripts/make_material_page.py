"""Write one HTML page holding the four grounds, for viewing in a browser.

cairosvg drops feTurbulence entirely -- a filtered rect comes back as one flat
colour -- so the display profile cannot be judged through the PNG path. A
browser renders the filter properly, so the sheet is handed over as HTML.

The editable profile draws the ground with explicit marks instead, and that one
does survive the PNG path; it is rendered beside each display tile so the two
can be compared.

Run from `server/`:

    UV_CACHE_DIR=/tmp/inku-uv-cache uv run python scripts/make_material_page.py <outdir>
"""

import pathlib
import sys

from inku_server import renderer
from inku_server.schema import Score

OUT = pathlib.Path(sys.argv[1])
OUT.mkdir(parents=True, exist_ok=True)
MATERIALS = ["plain", "paper", "washi", "ink_wash"]
SEED = 20260727

ROWS = [
    ("tone=off_white grain=medium opacity=0.14", "off_white", "medium", 0.14),
    ("tone=warm grain=coarse opacity=0.18", "warm", "coarse", 0.18),
]


def score_for(material: str, tone: str, grain: str, opacity: float) -> Score:
    return Score(
        **{
            "canvas": {"aspect": "square", "ground": {
                "material": material, "tone": tone, "grain": grain,
                "density": 0.6, "opacity": opacity,
            }},
            "background": "white",
            "instructions": [
                {"primitive": "line", "from": [0.18, 0.34], "to": [0.82, 0.30],
                 "color": "black", "weight": "pen"},
                {"primitive": "circle", "center": [0.5, 0.62], "radius": 0.17,
                 "color": "black", "weight": "pencil"},
            ],
        }
    )


parts = [
    "<meta charset='utf-8'><title>material</title>",
    "<style>body{font:13px/1.5 system-ui;margin:24px;background:#fff}"
    "h2{font-size:14px;font-weight:600;margin:28px 0 8px}"
    ".row{display:flex;gap:14px;flex-wrap:wrap}"
    ".cell{width:340px}.cell svg{width:340px;height:340px;border:1px solid #ddd;display:block}"
    ".name{margin:6px 0 0;color:#444}</style>",
    "<h1 style='font-size:15px'>material: the four grounds that used to render identically</h1>",
    "<p>Same Score, same seed. The display profile puts the sheet in the filter; "
    "the editable profile puts it in the marks the ground already draws. "
    "Neither adds a population of elements.</p>",
]
for label, tone, grain, opacity in ROWS:
    for profile in ("display", "editable"):
        parts.append(f"<h2>{label} &mdash; profile: {profile}</h2><div class='row'>")
        for material in MATERIALS:
            svg = renderer.render(
                score_for(material, tone, grain, opacity),
                render_seed=SEED,
                svg_profile=profile,
            )
            parts.append(f"<div class='cell'>{svg}<p class='name'>{material}</p></div>")
        parts.append("</div>")

page = OUT / "material.html"
page.write_text("\n".join(parts), encoding="utf-8")
print("wrote", page)
