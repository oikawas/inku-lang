"""Render one sheet holding the four undifferentiated grounds side by side.

paper, washi, ink_wash and plain were byte-identical in the ground layer; only
their seeds differed, so the grain was dealt afresh without the sheet ever
changing character. This renders the same Score on each of them so the
difference can be looked at rather than argued about.

Run from `server/`:

    UV_CACHE_DIR=/tmp/inku-uv-cache uv run python scripts/make_material_sheet.py <outdir>
"""

import io
import pathlib
import sys

from PIL import Image, ImageDraw

from inku_analysis.rasterizer import svg_to_png

from inku_server import renderer
from inku_server.schema import Score

OUT = pathlib.Path(sys.argv[1])
OUT.mkdir(parents=True, exist_ok=True)

MATERIALS = ["plain", "paper", "washi", "ink_wash"]
TILE = 620
SEED = 20260727


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


def png_of(score: Score, profile: str = "display") -> Image.Image:
    """Rasterize through the project's rasterizer, which is resvg.

    An earlier version of this script called cairosvg directly. cairosvg drops
    every filter without saying so, so the ground came back flat and three
    materials looked identical when they were not. Never reach past svg_to_png.
    """
    svg = renderer.render(score, render_seed=SEED, svg_profile=profile)
    return Image.open(io.BytesIO(svg_to_png(svg, width=TILE, height=TILE))).convert("RGB")


rows = [
    ("tone=off_white grain=medium opacity=0.14", "off_white", "medium", 0.14),
    ("tone=warm grain=coarse opacity=0.18", "warm", "coarse", 0.18),
]

sheet = Image.new("RGB", (TILE * len(MATERIALS), (TILE + 34) * len(rows) + 34), "white")
draw = ImageDraw.Draw(sheet)
draw.text((12, 12), "material: the four grounds that used to render identically  (same Score, same seed)", fill="black")
y = 34
for label, tone, grain, opacity in rows:
    draw.text((12, y + 8), label, fill="black")
    for i, material in enumerate(MATERIALS):
        img = png_of(score_for(material, tone, grain, opacity))
        sheet.paste(img, (i * TILE, y + 34))
        draw.text((i * TILE + 12, y + 40), material, fill="black")
    y += TILE + 34

path = OUT / "material-sheet.png"
sheet.save(path)
print("wrote", path)

for material in MATERIALS:
    svg = renderer.render(score_for(material, "off_white", "medium", 0.14), render_seed=SEED)
    (OUT / f"{material}.svg").write_text(svg, encoding="utf-8")
    print(f"{material:10} {len(svg):7} bytes")
