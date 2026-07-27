"""Render washi at four fibre settings beside paper, so the number can be seen.

The first cut read as scratches across the picture; the second was so faint that
washi and paper could not be told apart. This lays the candidates out.

Run from `server/`:

    UV_CACHE_DIR=/tmp/inku-uv-cache uv run python scripts/make_washi_ladder.py <outdir>
"""

import io
import pathlib
import sys

import cairosvg
from PIL import Image, ImageDraw

from inku_server import renderer
from inku_server.schema import Score

OUT = pathlib.Path(sys.argv[1])
OUT.mkdir(parents=True, exist_ok=True)
TILE = 700
SEED = 20260727

# (label, count(medium), length(base, span), width, opacity gain)
LADDER = [
    ("A  n=38 len 0.035-0.12 w 0.0009 op 0.55   (short, many, faint)", 38, (0.035, 0.085), 0.0009, 0.55),
    ("B  n=38 len 0.06-0.21 w 0.0013 op 0.80    (middle)", 38, (0.06, 0.15), 0.0013, 0.80),
    ("C  n=30 len 0.09-0.29 w 0.0016 op 1.00    (longer, darker)", 30, (0.09, 0.20), 0.0016, 1.00),
    ("D  n=10 len 0.18-0.52 w 0.0011 op 0.85    (first cut: reads as scratches)", 10, (0.18, 0.34), 0.0011, 0.85),
]


def score_for(material: str) -> Score:
    return Score(
        **{
            "canvas": {"aspect": "square", "ground": {
                "material": material, "tone": "off_white", "grain": "medium",
                "density": 0.6, "opacity": 0.14,
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


def png(score: Score) -> Image.Image:
    svg = renderer.render(score, render_seed=SEED)
    data = cairosvg.svg2png(bytestring=svg.encode("utf-8"),
                            output_width=TILE, output_height=TILE)
    return Image.open(io.BytesIO(data)).convert("RGB")


sheet = Image.new("RGB", (TILE * (len(LADDER) + 1), TILE + 60), "white")
draw = ImageDraw.Draw(sheet)
draw.text((12, 14), "washi: how much fibre?  (leftmost is paper, for reference)", fill="black")

sheet.paste(png(score_for("paper")), (0, 60))
draw.text((12, 66), "paper", fill="black")

for i, (label, count, length, width, gain) in enumerate(LADDER):
    renderer._WASHI_FIBER_COUNT = {"fine": int(count * 1.4), "medium": count,
                                   "coarse": int(count * 0.7), "none": count}
    renderer._WASHI_FIBER_LENGTH = length
    renderer._WASHI_FIBER_WIDTH = width
    renderer._WASHI_FIBER_OPACITY = gain
    sheet.paste(png(score_for("washi")), ((i + 1) * TILE, 60))
    draw.text(((i + 1) * TILE + 12, 66), label, fill="black")

path = OUT / "washi-ladder.png"
sheet.save(path)
print("wrote", path)
