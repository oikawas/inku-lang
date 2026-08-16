"""Count what the eye reacts to on a raster, at the width the raster has.

    python -m inku_analysis.raster_metrics PNGDIR

**The counting rule does not choose a width.** Burning an SVG does -- that is
``rasterize_batch`` -- and 2026-08-08 ruled that a work is burned at the width it
declares (1618px) and measured there. This module reads a PNG and counts its
pixels; whatever it was handed is what it measures.

**Why that has to be said in code and not only in prose.** The rule was already
written down, and the tool that the evaluation track names every round still
halved the image on its second line before counting anything. A halved raster
loses thin marks: they blend into the paper and drop out of "strong ink", while
thick ones survive. Measured that way, a change that thins the marks reads as no
change and a change that thickens them reads as larger than it is -- so running
the loop enough times makes the ruler pick fat pictures. Measured over the 255
full-size rasters of run 851, halving moves strong ink by x0.735 and turns six
works from "has strong ink" into "has none".

**Why this lives in `shared/` and not in the CLI.** The same reason
``rasterize_batch`` does: the counting rule had grown eight copies under
`cli/out2/`, four of which halve unconditionally. A rule with one home can carry
acceptance tests; a rule copied into a run directory cannot, and drifts in
silence. `inku-analysis` is a dependency of the server, so this is importable
wherever the pictures are.

**There is no flag for shrinking.** Reading an old record that was written at
380px means burning at 380px and counting that -- the width is chosen when the
picture is made, never when it is counted.

This module imports neither ``inku_cli`` nor ``inku_server``, and must not.
"""

from __future__ import annotations

import argparse
import colorsys
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from PIL import Image

# Distance from the ground, in 0..255 of the widest channel. A mark is anything
# past FAINT; STRONG is the ink that reads as figure rather than as tint. The
# two numbers are the ones `vision_metrics.py` has counted with since 2026-08-06,
# kept so the new rule and the recorded baselines are the same quantity.
FAINT = 24
STRONG = 96
COLOR_SAT = 0.25


def measure_png(path: Path) -> dict[str, Any]:
    """Count one PNG at its own size and return the eight quantities.

    ``pixels`` is the size of the file that was opened. Nothing here resizes,
    thumbnails or reduces -- that is the whole point of the module.
    """
    img = Image.open(Path(path)).convert("RGB")
    total = img.width * img.height
    # `getdata()` is deprecated in Pillow 12.3 and goes away in Pillow 14, and a
    # per-pixel Python loop over a 1618x1618 raster is 2.6M iterations. The raw
    # RGB bytes fold into a colour histogram instead, and the arithmetic below
    # runs once per distinct colour rather than once per pixel. Verified equal to
    # `vision_metrics.measure` on every fixed material and on 10 sampled works.
    data = img.tobytes()
    counts = Counter(zip(data[0::3], data[1::3], data[2::3]))
    # The ground is the modal colour, ties going to the one seen first -- which
    # is what `Counter.most_common` does. Not the first pixel and not the
    # lightest colour: a work on black paper has neither of those as its ground.
    ground = counts.most_common(1)[0][0]
    br, bg, bb = ground

    faint = strong = colored = 0
    distance_sum = 0
    saturation_sum = 0.0
    for (red, green, blue), seen in counts.items():
        distance = max(abs(red - br), abs(green - bg), abs(blue - bb))
        distance_sum += distance * seen
        if distance > FAINT:
            faint += seen
            if distance > STRONG:
                strong += seen
            saturation = colorsys.rgb_to_hsv(red / 255, green / 255, blue / 255)[1]
            saturation_sum += saturation * seen
            if saturation > COLOR_SAT:
                colored += seen

    return {
        "pixels": total,
        "ground": [br, bg, bb],
        "ground_light": (br + bg + bb) / 3 / 255,
        "faint": faint / total,
        "strong": strong / total,
        "mean_distance": distance_sum / total,
        "sat_marks": (saturation_sum / faint) if faint else 0.0,
        "colored_share": (colored / faint) if faint else 0.0,
    }


def measure_dir(directory: Path) -> dict[str, Any]:
    """Count every ``*.png`` directly under ``directory``.

    A file that cannot be read is an absent measurement, not a zero: it is named
    in ``unresolved`` with the reason, the way ``rasterize_dir`` carries a
    picture it failed to burn. A zero row would be counted, plotted and averaged.
    """
    directory = Path(directory)
    if not directory.is_dir():
        raise NotADirectoryError(f"{directory} is not a directory")
    works: dict[str, Any] = {}
    unresolved: list[dict[str, str]] = []
    for path in sorted(path for path in directory.glob("*.png") if path.is_file()):
        try:
            works[path.stem] = measure_png(path)
        except (OSError, ValueError) as error:
            unresolved.append({"source": str(path), "reason": f"{type(error).__name__}: {error}"[:200]})
    return {
        "directory": str(directory),
        "measured": len(works),
        "unresolved": unresolved,
        "works": works,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m inku_analysis.raster_metrics",
        description="Count the ink of every PNG in a directory, at the width each PNG has.",
    )
    parser.add_argument("directory", type=Path, help="directory holding the .png files")
    parser.add_argument("--out", type=Path, help="write the report here instead of standard output")
    args = parser.parse_args(argv)

    report = measure_dir(args.directory)
    text = json.dumps(report, ensure_ascii=False, indent=1)
    if args.out:
        args.out.write_text(text, encoding="utf-8")
        print(f"measured {report['measured']} -> {args.out}")
    else:
        print(text)
    if report["unresolved"]:
        print("UNRESOLVED (absent measurements, not zeros):", file=sys.stderr)
        for failure in report["unresolved"]:
            print(f"  {failure['source']}  {failure['reason']}", file=sys.stderr)
    return 1 if report["unresolved"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
