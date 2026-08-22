"""Ground and presence layers for the default render engine."""

from __future__ import annotations

import hashlib
import json
import math
import struct

import svgwrite

from ...master_grid import fmt
from ...plugins import CanvasSize
from ...schema import CanvasGroundSpec, Score
from ...stroke_engine import DEFAULT_SUPPORT, Support, support_for_ground
from .determinism import _hash01
from .document import _score_canvas_ground
from .palette import COLOR_MAP


def _score_support(score: Score) -> Support:
    """The sheet this work is worked on.

    One constant unless the work names its own ground: `Support`'s docstring
    says the sheet is one by default, and this is where a work that names it
    swaps it (render engine 37).
    """
    ground = _score_canvas_ground(score)
    if ground is None:
        return DEFAULT_SUPPORT
    return support_for_ground(ground.material)


def _texture_seed(
    ground: CanvasGroundSpec, kind: str, render_seed: int | None, index: int = 0
) -> int:
    """支持体の同一性だけから質感 seed を作る (render engine 15)。

    engine 14 までは Score 全体の dump をハッシュしていたため、地と無関係な変更 —
    instruction に coerce が書き込む色注記や、描画に一度も読まれない `absorbency` —
    が地の粒配置を動かしていた。地の seed が決めているのは「どの紙か」であって
    「どれだけ濃いか」ではないので、材質と紙目、そして演奏 seed だけを材料にする。
    `opacity` を上げれば同じ紙が濃くなり、`density` を上げれば同じ紙に粒が足される
    (先頭の粒は動かない)。`tone` は色調であって支持体ではない。
    """
    payload = {"material": ground.material, "grain": ground.grain}
    key = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    if render_seed is not None:
        key += f":render:{render_seed}"
    key += f":texture:{kind}:{index}"
    return struct.unpack("<Q", hashlib.sha256(key.encode("utf-8")).digest()[:8])[0]


def _ground_tone_color(ground: CanvasGroundSpec, bg: str) -> str:
    return {
        "white": bg,
        "off_white": "#f7f3e8",
        "warm": "#f3ead8",
        "cool": "#eef3f4",
        "gray": "#e4e2dc",
        "black": "#151515",
    }.get(ground.tone, bg)


# The prototypes that settled these forms were built on a 1000-unit sheet taken
# to be 210 mm across. Every canvas this renderer makes is 1000 units tall, so
# the scale is the same on every aspect: a grain keeps its physical size instead
# of being stretched to fit the paper (author's ruling, 2026-08-14).
_GROUND_MM = 1000 / 210.0

# The grain sizes the `grain` word has always meant. `medium` is the one the
# settled paper sheet was judged at.
_GROUND_GRAIN_RADIUS = {"fine": 0.7, "medium": 1.1, "coarse": 1.8, "none": 0.6}

# The defaults of `CanvasGroundSpec`. Every layer below carries the opacity and
# the count it was judged at, and these two fields move them from there.
_GROUND_OPACITY_DEFAULT = 0.12
_GROUND_DENSITY_DEFAULT = 0.20

# What one support's ground layer may cost (author's ruling, 2026-08-14).
#
# The contract asked for twice the settled paper ground, and put that at 13,338
# bytes -- twice what the prototype sheet cost. The prototypes were composed by
# hand and never passed `_apply_master_grid`, which writes every decimal to six
# places and does not trim (2026-07-24 ruling), so the same geometry costs 9 to
# 34 per cent more once the product draws it. The author restated the budget as
# a flat 24 KB rather than have the forms cut to fit an arithmetic that was
# measured off the product.
GROUND_BYTE_BUDGET = 24 * 1024

# A rocked plate is black before anything is done to it. This is the material
# itself, which is why it is here and not in `tone`.
_MEZZOTINT_PLATE = "#0d0d0d"


def _ground_mm(value: float) -> float:
    return value * _GROUND_MM


class _GroundRandom:
    """A counter over `_hash01`.

    The seven supports were settled by generators written against Python's
    `random`. Wrapping this module's own hash in the same three calls lets the
    ports read like the scripts they came from, without a second source of
    randomness in the renderer.
    """

    def __init__(self, seed: int, salt: str) -> None:
        self._seed = seed
        self._salt = salt
        self._index = 0

    def unit(self) -> float:
        value = _hash01(self._index, self._seed, self._salt)
        self._index += 1
        return value

    def uniform(self, low: float, high: float) -> float:
        return low + (high - low) * self.unit()

    def randrange(self, stop: int) -> int:
        return min(stop - 1, int(self.unit() * stop))


def _ground_wrapped(shape, w: float, h: float, cx: float, cy: float, reach: float):
    """The copies a shape needs so it continues across the tile edge.

    Pattern content is clipped to its tile, so a fibre running off the right
    edge would end in a cut unless the same fibre is drawn again one tile to the
    left. Only the sides the shape actually reaches get a copy.
    """
    offsets = [(0.0, 0.0)]
    if cx - reach < 0:
        offsets.append((w, 0.0))
    if cx + reach > w:
        offsets.append((-w, 0.0))
    if cy - reach < 0:
        offsets.append((0.0, h))
    if cy + reach > h:
        offsets.append((0.0, -h))
    return [shape(dx, dy) for dx, dy in offsets]


def _paper_ground_layers(ground: CanvasGroundSpec, seed: int) -> list[dict]:
    """A fine field that never shows its lattice, and six coarse periods.

    Twelve runs settled this. A lattice is only visible where the eye can tell
    one grain from the next, so the fine field needs no defence against its own
    period; the coarse grains do, and what defends them is one grain per tile at
    six different periods. A tile holding two or more grains repeats that group
    at a fixed interval, and the group then reads as a single larger grain.
    """
    rng = _GroundRandom(seed, "ground-paper")
    radius = _GROUND_GRAIN_RADIUS.get(ground.grain, 1.1)
    count = max(
        8, round(72 * max(0.02, ground.density) / _GROUND_DENSITY_DEFAULT)
    )
    fine = [
        f'<circle cx="{rng.uniform(0, 80):.1f}" cy="{rng.uniform(0, 80):.1f}" '
        f'r="{radius * rng.uniform(0.6, 1.4):.2f}" '
        f'opacity="{rng.uniform(0.35, 1.0):.2f}"/>'
        for _ in range(count)
    ]
    layers = [
        {
            "w": 80.0,
            "h": 80.0,
            "rotate": 23.0,
            "opacity": 0.30,
            "body": '<g fill="#777777">' + "".join(fine) + "</g>",
        }
    ]

    # A counter of its own, so how many fine grains there are cannot move the
    # coarse ones. Raising `density` must make the same sheet denser, not swap
    # it for another sheet -- the reason `_texture_seed` stopped hashing the
    # whole Score at engine 15.
    rng = _GroundRandom(seed, "ground-paper-coarse")

    # Six grains is too small a sample to leave to chance: drawn independently,
    # the coarseness of the whole sheet is decided by six throws. Each period
    # draws from its own band of the size range instead, and only which period
    # gets which band moves with the seed.
    bands = list(range(len(_PAPER_COARSE_TILES)))
    for index in range(len(bands) - 1, 0, -1):
        other = rng.randrange(index + 1)
        bands[index], bands[other] = bands[other], bands[index]
    low, high = _PAPER_COARSE_RADIUS
    step = (high - low) / len(bands)
    for tile, band in zip(_PAPER_COARSE_TILES, bands):
        grain = low + step * (band + rng.unit())
        # One grain's ink is capped, so a large grain comes out lighter: a large
        # dark circle reads as a circle rather than as grain, while a small dark
        # speck and a large pale stain are both things paper has. The heaviest
        # grain carries about 1.6 times the ink of the lightest.
        opacity = min(0.95, max(0.30, 0.92 * (low / grain) ** 1.27))
        layers.append(
            {
                "w": tile,
                "h": tile,
                "rotate": rng.uniform(0, 90),
                "opacity": 0.18,
                "body": (
                    f'<circle cx="{rng.uniform(0, tile):.1f}" '
                    f'cy="{rng.uniform(0, tile):.1f}" r="{grain:.2f}" '
                    f'fill="#777777" opacity="{opacity:.2f}"/>'
                ),
            }
        )
    return layers


def _washi_ground_layers(ground: CanvasGroundSpec, seed: int) -> list[dict]:
    """Kozo fibre, and the marks the screen leaves in the sheet.

    Kozo bast averages 10 mm -- an order longer than wood pulp's 0.7-2.5 mm --
    and is left long rather than chopped, which is why the sheet is thin and
    strong, and why the fibre is the thing that makes washi look like washi. The
    sheet is formed on a `su` of bamboo splints bound with silk thread, so it
    also carries laid lines from the splints and chain lines from the threads.
    """
    rng = _GroundRandom(seed, "ground-washi")
    pitch = _ground_mm(1.05)
    splint = _ground_mm(8)
    chain_w = _ground_mm(60)
    layers = [
        {
            "w": pitch,
            "h": splint,
            "rotate": 0.0,
            "opacity": 0.05,
            "body": (
                f'<rect x="0" y="0" width="{pitch * 0.38:.2f}" '
                f'height="{splint:.2f}" fill="#8a8a8a" opacity="0.5"/>'
            ),
        },
        {
            "w": chain_w,
            "h": _ground_mm(32),
            "rotate": 0.0,
            "opacity": 0.05,
            "body": (
                f'<rect x="0" y="0" width="{chain_w:.2f}" '
                f'height="{_ground_mm(0.45):.2f}" fill="#8a8a8a" opacity="0.45"/>'
            ),
        },
    ]

    # The tile has to be large and well filled. A sparse one shows its own
    # period, because the eye follows a repeated arrangement of long shapes far
    # more readily than a repeated field of dots.
    tile = _ground_mm(130)
    parts: list[str] = []
    for _ in range(80):
        length = _ground_mm(rng.uniform(5.0, 16.0))
        angle = rng.unit() * math.pi
        cx = rng.uniform(0, tile)
        cy = rng.uniform(0, tile)
        dx, dy = math.cos(angle) * length / 2, math.sin(angle) * length / 2
        bow = rng.uniform(-0.16, 0.16) * length
        width = rng.uniform(0.35, 0.8)
        opacity = rng.uniform(0.10, 0.34)

        def fibre(
            ox: float,
            oy: float,
            cx: float = cx,
            cy: float = cy,
            dx: float = dx,
            dy: float = dy,
            bow: float = bow,
            width: float = width,
            opacity: float = opacity,
            angle: float = angle,
        ) -> str:
            x1, y1 = cx - dx + ox, cy - dy + oy
            x2, y2 = cx + dx + ox, cy + dy + oy
            mx = (x1 + x2) / 2 - math.sin(angle) * bow
            my = (y1 + y2) / 2 + math.cos(angle) * bow
            # Colour and fill are carried by the group, not repeated per fibre.
            return (
                f'<path d="M{x1:.0f} {y1:.0f}Q{mx:.0f} {my:.0f} {x2:.0f} {y2:.0f}" '
                f'stroke-width="{width:.2f}" opacity="{opacity:.2f}"/>'
            )

        parts.extend(_ground_wrapped(fibre, tile, tile, cx, cy, length / 2))
    layers.append(
        {
            "w": tile,
            "h": tile,
            "rotate": 0.0,
            "opacity": 0.62,
            "body": '<g stroke="#8a8a8a" fill="none">' + "".join(parts) + "</g>",
        }
    )
    return layers


def _ink_wash_ground_layers(ground: CanvasGroundSpec, seed: int) -> list[dict]:
    """The passes of a loaded brush, and the tide each pass leaves behind.

    Dilute ink brushed across a finished sheet. What the eye reads is not a
    grain but the passes: broad soft bands, the hairs' streaks along them, and
    the darker line where a pass dried at its edge. How dark the wash is does
    not belong here -- `tone` owns that, and carrying it in both places makes
    the sheet twenty levels darker than it should be.
    """
    rng = _GroundRandom(seed, "ground-ink-wash")
    band = _ground_mm(46)
    tile_w = _ground_mm(210)
    defs: list[str] = []
    parts: list[str] = []
    for index, top in enumerate((0.0, band * 1.03)):
        # A pass is dense where the brush was loaded and fades as it lifts.
        gid = f"gg{index}"
        head = rng.uniform(0.05, 0.2)
        tail = rng.uniform(0.55, 0.8)
        defs.append(
            f'<linearGradient id="{gid}" x1="0" y1="0" x2="0" y2="1">'
            f'<stop offset="0" stop-color="#6f6f6f" stop-opacity="0.04"/>'
            f'<stop offset="{head:.2f}" stop-color="#6f6f6f" stop-opacity="0.30"/>'
            f'<stop offset="{tail:.2f}" stop-color="#6f6f6f" stop-opacity="0.16"/>'
            f'<stop offset="1" stop-color="#6f6f6f" stop-opacity="0.02"/>'
            f"</linearGradient>"
        )
        # A brush does not stop on a straight line: the pass is a filled shape
        # with a ragged lower edge, not a rectangle.
        height = band * rng.uniform(0.80, 0.93)
        lower = [
            (
                tile_w * step / 14,
                top + height + rng.uniform(-_ground_mm(1.6), _ground_mm(1.6)),
            )
            for step in range(15)
        ]
        edge = "L".join(f"{x:.1f} {y:.1f}" for x, y in reversed(lower))
        parts.append(
            f'<path d="M0 {top:.1f}L{tile_w:.1f} {top:.1f}L{edge}Z" fill="url(#{gid})"/>'
        )
        # The hairs of the brush leave streaks along the pass.
        for _ in range(40):
            y = top + rng.uniform(0.08, 0.92) * height
            x0 = rng.uniform(-tile_w * 0.1, tile_w * 0.8)
            run = rng.uniform(tile_w * 0.15, tile_w * 0.7)
            parts.append(
                f'<rect x="{x0:.0f}" y="{y:.0f}" width="{run:.0f}" '
                f'height="{rng.uniform(0.6, 2.4):.2f}" '
                f'opacity="{rng.uniform(0.08, 0.34):.2f}"/>'
            )
        # The tide line: where the pass stopped, the ink pooled and dried darker.
        tide = "L".join(f"{x:.1f} {y:.1f}" for x, y in lower)
        parts.append(
            f'<path d="M{tide}" stroke="#6f6f6f" '
            f'stroke-width="{rng.uniform(0.9, 1.8):.2f}" fill="none" opacity="0.30"/>'
        )
    return [
        {
            "w": tile_w,
            "h": band * 2,
            "rotate": 0.0,
            "opacity": 0.34,
            "body": '<g fill="#6f6f6f">' + "".join(parts) + "</g>",
            "defs": "".join(defs),
        }
    ]


def _charcoal_ground_layers(ground: CanvasGroundSpec, seed: int) -> list[dict]:
    """Ridged paper, the charcoal caught on the ridges, and loose dust.

    Charcoal paper is made with regular parallel ridges pressed into it so the
    powder has something to hold on to. Two earlier attempts made the deposit a
    run of dashes lined up in columns, and the sheet then read as a grid of that
    one block at every tile size tried -- at 37 mm as plainly as at 7 mm. What
    survives a short period is many small marks whose positions do not line up.
    The striation is a separate layer, and that one is *meant* to repeat,
    because a ridged sheet really is periodic.
    """
    rng = _GroundRandom(seed, "ground-charcoal")
    pitch = _ground_mm(1.1)
    layers = [
        {
            "w": pitch,
            "h": _ground_mm(10),
            "rotate": 0.0,
            "opacity": 0.10,
            "body": (
                f'<rect x="0" y="0" width="{pitch * 0.45:.2f}" '
                f'height="{_ground_mm(10):.2f}" fill="#3a3a3a" opacity="0.4"/>'
            ),
        }
    ]

    # Each tick sits on a ridge, so its width is the ridge's, but which ridge
    # and how far down are free -- that is what keeps the tile from becoming a
    # motif of its own.
    tile = _ground_mm(17)
    ridges = int(tile / pitch)
    ticks = []
    for _ in range(64):
        column = rng.randrange(ridges)
        ticks.append(
            f'<rect x="{pitch * column + pitch * 0.1:.1f}" '
            f'y="{rng.uniform(0, tile):.1f}" width="{pitch * 0.6:.2f}" '
            f'height="{_ground_mm(rng.uniform(0.35, 1.6)):.1f}" '
            f'opacity="{rng.uniform(0.18, 0.62):.2f}"/>'
        )
    layers.append(
        {
            "w": tile,
            "h": tile,
            "rotate": 0.0,
            "opacity": 0.55,
            "body": '<g fill="#2a2a2a">' + "".join(ticks) + "</g>",
        }
    )

    # Powder that fell where no ridge caught it, and the occasional smear.
    dust_tile = _ground_mm(53)
    dust = [
        f'<circle cx="{rng.uniform(0, dust_tile):.0f}" '
        f'cy="{rng.uniform(0, dust_tile):.0f}" r="{rng.uniform(0.4, 1.6):.2f}" '
        f'opacity="{rng.uniform(0.14, 0.45):.2f}"/>'
        for _ in range(26)
    ]
    dust.extend(
        f'<ellipse cx="{rng.uniform(0, dust_tile):.0f}" '
        f'cy="{rng.uniform(0, dust_tile):.0f}" '
        f'rx="{_ground_mm(rng.uniform(1.2, 3.5)):.1f}" '
        f'ry="{_ground_mm(rng.uniform(0.5, 1.4)):.1f}" '
        f'opacity="{rng.uniform(0.06, 0.16):.2f}"/>'
        for _ in range(5)
    )
    layers.append(
        {
            "w": dust_tile,
            "h": dust_tile,
            "rotate": 0.0,
            "opacity": 0.4,
            "body": '<g fill="#2a2a2a">' + "".join(dust) + "</g>",
        }
    )
    return layers


def _canvas_ground_layers(ground: CanvasGroundSpec, seed: int) -> list[dict]:
    """A plain weave, the slubs in the yarn, and the gesso over both.

    Artist linen is a plain weave -- each weft thread passes over and under
    successive warp threads -- at roughly 10.5 threads/cm for a coarse cloth and
    18 for a fine one. So the surface is a regular crossing grid, not a scatter,
    and this is the one layer in the family that is *supposed* to repeat: that
    periodicity is what the surface is. Linen also carries slubs, occasional
    thick threads running the whole way across.
    """
    rng = _GroundRandom(seed, "ground-canvas")

    # Fourteen threads per centimetre is the middle of the range artists use,
    # and the tile holds two threads each way so the over-and-under completes.
    pitch = _ground_mm(1000 / 14 / 100)
    weave = []
    for row in range(2):
        for col in range(2):
            x = col * pitch
            y = row * pitch
            over = (row + col) % 2 == 0
            bar = pitch * 0.46
            weft = (
                f'<rect x="{x:.2f}" y="{y + pitch * 0.27:.2f}" '
                f'width="{pitch:.2f}" height="{bar:.2f}" '
                f'opacity="{0.5 if over else 0.3:.2f}"/>'
            )
            warp = (
                f'<rect x="{x + pitch * 0.27:.2f}" y="{y:.2f}" '
                f'width="{bar:.2f}" height="{pitch:.2f}" '
                f'opacity="{0.3 if over else 0.5:.2f}"/>'
            )
            weave.append(weft if over else warp)
            weave.append(warp if over else weft)
    layers = [
        {
            "w": pitch * 2,
            "h": pitch * 2,
            "rotate": 0.0,
            "opacity": 0.30,
            "body": '<g fill="#8f8f8f">' + "".join(weave) + "</g>",
        }
    ]

    # Linen is spun from a fibre that will not be talked into an even thickness,
    # so a thick thread runs the whole way across every few centimetres.
    slub_tile = _ground_mm(115)
    slubs = []
    for _ in range(5):
        along = rng.unit() < 0.5
        thickness = pitch * rng.uniform(0.35, 0.75)
        position = rng.uniform(0, slub_tile)
        opacity = rng.uniform(0.10, 0.26)
        if along:
            slubs.append(
                f'<rect x="0" y="{position:.1f}" width="{slub_tile:.1f}" '
                f'height="{thickness:.2f}" opacity="{opacity:.2f}"/>'
            )
        else:
            slubs.append(
                f'<rect x="{position:.1f}" y="0" width="{thickness:.2f}" '
                f'height="{slub_tile:.1f}" opacity="{opacity:.2f}"/>'
            )
    layers.append(
        {
            "w": slub_tile,
            "h": slub_tile,
            "rotate": 0.0,
            "opacity": 0.30,
            "body": '<g fill="#8f8f8f">' + "".join(slubs) + "</g>",
        }
    )

    # The gesso does not lie perfectly flat over a cloth.
    mottle_tile = _ground_mm(160)
    defs = []
    blobs = []
    for index in range(5):
        gid = f"gg{index}"
        defs.append(
            f'<radialGradient id="{gid}">'
            f'<stop offset="0" stop-color="#8f8f8f" stop-opacity="0.16"/>'
            f'<stop offset="1" stop-color="#8f8f8f" stop-opacity="0"/>'
            f"</radialGradient>"
        )
        blobs.append(
            f'<ellipse cx="{rng.uniform(0, mottle_tile):.0f}" '
            f'cy="{rng.uniform(0, mottle_tile):.0f}" '
            f'rx="{_ground_mm(rng.uniform(9, 26)):.0f}" '
            f'ry="{_ground_mm(rng.uniform(7, 20)):.0f}" fill="url(#{gid})"/>'
        )
    layers.append(
        {
            "w": mottle_tile,
            "h": mottle_tile,
            "rotate": 0.0,
            "opacity": 0.5,
            "body": "".join(blobs),
            "defs": "".join(defs),
        }
    )
    return layers


def _drawing_paper_ground_layers(
    ground: CanvasGroundSpec, seed: int
) -> list[dict]:
    """An even tooth, and the cloudiness left by how the fibres settled.

    Machine-made wove paper with a tooth (中目 is the usual middle grade:
    hollows small enough to colour evenly, still uneven enough to catch
    pigment) and no laid lines at all. What sets it apart from a flecked
    handmade sheet is that it has no specks -- what it has is formation, the
    soft cloudiness left where the fibres settled unevenly.

    Two tiles of different periods share the tooth between them. One tile, no
    matter how unaligned its marks, still forms an arrangement the eye can
    learn; two periods leave nothing to learn. This works here and did not work
    for a lattice aligned to the sheet's own axes, where splitting the period
    made the banding worse.
    """
    rng = _GroundRandom(seed, "ground-drawing-paper")
    layers = []
    for side, count in ((5.0, 75), (3.7, 41)):
        tile = _ground_mm(side)
        tooth = []
        for _ in range(count):
            # A hollow reads as a soft short dash, slightly wider than tall,
            # because the felt drags the surface as the sheet is made.
            rx = rng.uniform(0.30, 0.72)
            tooth.append(
                f'<ellipse cx="{rng.uniform(0, tile):.1f}" '
                f'cy="{rng.uniform(0, tile):.1f}" rx="{rx:.2f}" '
                f'ry="{rx * rng.uniform(0.55, 0.8):.2f}" '
                f'opacity="{rng.uniform(0.18, 0.62):.2f}"/>'
            )
        layers.append(
            {
                "w": tile,
                "h": tile,
                "rotate": 0.0,
                "opacity": 0.42,
                "body": '<g fill="#8a8a8a">' + "".join(tooth) + "</g>",
            }
        )

    # Formation: hold a machine sheet to the light and the fibres are not spread
    # evenly. This is the part a field of grains does not have.
    cloud_tile = _ground_mm(155)
    defs = []
    clouds = []
    for index in range(6):
        gid = f"gg{index}"
        defs.append(
            f'<radialGradient id="{gid}">'
            f'<stop offset="0" stop-color="#8a8a8a" stop-opacity="0.10"/>'
            f'<stop offset="0.6" stop-color="#8a8a8a" stop-opacity="0.04"/>'
            f'<stop offset="1" stop-color="#8a8a8a" stop-opacity="0"/>'
            f"</radialGradient>"
        )
        clouds.append(
            f'<ellipse cx="{rng.uniform(0, cloud_tile):.0f}" '
            f'cy="{rng.uniform(0, cloud_tile):.0f}" '
            f'rx="{_ground_mm(rng.uniform(11, 30)):.0f}" '
            f'ry="{_ground_mm(rng.uniform(9, 24)):.0f}" fill="url(#{gid})"/>'
        )
    layers.append(
        {
            "w": cloud_tile,
            "h": cloud_tile,
            "rotate": 0.0,
            "opacity": 0.55,
            "body": "".join(clouds),
            "defs": "".join(defs),
        }
    )
    return layers


def _mezzotint_ground_layers(ground: CanvasGroundSpec, seed: int) -> list[dict]:
    """A plate rocked all over, printing as velvet black.

    A rocker -- a curved blade with teeth, sold by gauge in lines per inch -- is
    rocked over the plate again and again in criss-crossing directions until the
    whole surface carries burr. Burr holds ink, so a fully rocked plate prints a
    black no other intaglio process reaches, and the image is then made the
    other way round by scraping the burr away. On a black field what the eye
    picks up is not the burr but the light between it, so the pits are drawn
    white.
    """
    rng = _GroundRandom(seed, "ground-mezzotint")
    layers = []
    for across, angle, opacity in ((12, 0.0, 0.16), (9, 58.0, 0.13)):
        # 65 lines per inch is the middle gauge: 0.39 mm between teeth.
        pitch = _ground_mm(25.4 / 65)
        pits = []
        for row in range(across):
            for col in range(across):
                # One decimal is a fifth of a pixel at the size these are
                # judged at, and the second decimal costs 1.6 KB across the two
                # lattices.
                pits.append(
                    f'<circle cx="{(col + 0.5) * pitch + rng.uniform(-0.22, 0.22) * pitch:.1f}" '
                    f'cy="{(row + 0.5) * pitch + rng.uniform(-0.22, 0.22) * pitch:.1f}" '
                    f'r="{pitch * rng.uniform(0.17, 0.31):.2f}" '
                    f'opacity="{rng.uniform(0.30, 0.95):.2f}"/>'
                )
        layers.append(
            {
                "w": pitch * across,
                "h": pitch * across,
                "rotate": angle,
                "opacity": opacity,
                "body": '<g fill="#ffffff">' + "".join(pits) + "</g>",
            }
        )

    # The burr is never perfectly even: some places took less, and those print a
    # shade lighter.
    fleck_tile = _ground_mm(46)
    flecks = [
        f'<circle cx="{rng.uniform(0, fleck_tile):.1f}" '
        f'cy="{rng.uniform(0, fleck_tile):.1f}" r="{rng.uniform(0.5, 2.1):.2f}" '
        f'opacity="{rng.uniform(0.06, 0.22):.2f}"/>'
        for _ in range(18)
    ]
    layers.append(
        {
            "w": fleck_tile,
            "h": fleck_tile,
            "rotate": 0.0,
            "opacity": 0.5,
            "body": '<g fill="#ffffff">' + "".join(flecks) + "</g>",
        }
    )
    return layers


# The six periods the coarse grains of the paper ground repeat at, and the size
# range those grains are stratified across.
_PAPER_COARSE_TILES = (181.0, 231.0, 281.0, 341.0, 421.0, 522.0)
_PAPER_COARSE_RADIUS = (3.0, 6.2)

# One builder per support. `plain` is not here: asking for no ground is not
# asking for a ground, and `_score_canvas_ground` has already returned None.
_GROUND_LAYER_BUILDERS = {
    "paper": _paper_ground_layers,
    "washi": _washi_ground_layers,
    "ink_wash": _ink_wash_ground_layers,
    "charcoal_ground": _charcoal_ground_layers,
    "canvas": _canvas_ground_layers,
    "drawing_paper": _drawing_paper_ground_layers,
    "mezzotint": _mezzotint_ground_layers,
}


def _render_canvas_ground(
    dwg: svgwrite.Drawing,
    score: Score,
    canvas: CanvasSize,
    bg: str,
    *,
    profile: str,
    render_seed: int | None,
) -> tuple[object | None, str | None]:
    """The support the work is made on, drawn as tiled `<pattern>` layers.

    The same ground comes out of all three profiles. The mechanism used to be
    chosen by profile -- a `feTurbulence` rectangle for `display`, a scatter of
    dots for the other two -- which meant the support a work was made on
    depended on which file you exported. A pattern is neither a filter nor a
    clip path, so `compat` may carry it too.

    Returns the layer group and the pattern definitions to inject into `<defs>`.
    """
    ground = _score_canvas_ground(score)
    if ground is None:
        return None, None
    seed = int(
        ground.seed
        if ground.seed is not None
        else _texture_seed(ground, "canvas-ground", render_seed)
    )
    tone = _ground_tone_color(ground, bg)
    group = dwg.g(id="layer_01_canvas_ground")
    if ground.material == "mezzotint":
        shift = canvas.unit * (0.001 + _hash01(0, seed, "register-shift") * 0.003)
        angle = _hash01(1, seed, "register-angle") * math.tau
        group.translate(math.cos(angle) * shift, math.sin(angle) * shift)
    group.add(
        dwg.rect(
            insert=(0, 0), size=(canvas.width, canvas.height), fill=tone, opacity=0.98
        )
    )
    if ground.material == "mezzotint":
        # The plate itself, under the burr. This is the material, not the tone.
        group.add(
            dwg.rect(
                insert=(0, 0),
                size=(canvas.width, canvas.height),
                fill=_MEZZOTINT_PLATE,
            )
        )

    layers = _GROUND_LAYER_BUILDERS[ground.material](ground, seed)
    # Every layer carries the opacity its support was judged at, and the
    # `opacity` field moves all of them together from there.
    scale = max(0.0, ground.opacity) / _GROUND_OPACITY_DEFAULT
    defs: list[str] = []
    for index, layer in enumerate(layers):
        pattern_id = f"gp{index}"
        turn = (
            ""
            if not layer["rotate"]
            else f' patternTransform="rotate({layer["rotate"]:.1f})"'
        )
        defs.append(layer.get("defs", ""))
        defs.append(
            f'<pattern id="{pattern_id}" patternUnits="userSpaceOnUse" '
            f'width="{layer["w"]:.2f}" height="{layer["h"]:.2f}"{turn}>'
            f'{layer["body"]}</pattern>'
        )
        group.add(
            dwg.rect(
                insert=(0, 0),
                size=(canvas.width, canvas.height),
                fill=f"url(#{pattern_id})",
                opacity=min(1.0, layer["opacity"] * scale),
            )
        )
    return group, "".join(defs)


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def _score_visual_load(score: Score) -> int:
    load = 0
    for ins in score.instructions:
        if ins.arrangement is not None:
            load += max(1, int(ins.arrangement.count))
        else:
            load += 1
    return load


def _presence_center_px(score: Score, canvas: CanvasSize) -> tuple[float, float]:
    presence = score.presence
    if presence is None or presence.center is None:
        return canvas.width * 0.52, canvas.height * 0.50
    x, y = presence.center
    return _clamp01(x) * canvas.width, _clamp01(y) * canvas.height


def _presence_seed(score: Score) -> int:
    presence_json = (
        score.presence.model_dump_json() if score.presence is not None else ""
    )
    instruction_key = "|".join(
        f"{ins.primitive}:{ins.color}:{ins.weight}:{ins.arrangement.count if ins.arrangement else 1}"
        for ins in score.instructions
    )
    digest = hashlib.sha256(
        f"{presence_json}|{instruction_key}".encode("utf-8")
    ).digest()
    return struct.unpack("<Q", digest[:8])[0]


def _render_presence_layer(
    dwg: svgwrite.Drawing,
    score: Score,
    cmap: dict[str, str],
    canvas: CanvasSize,
    *,
    work_assignment: dict[str, str],
):
    """抽象化された存在感を描く。自然文キーワードや具象部品はここでは扱わない。"""
    presence = score.presence
    if presence is None or presence.kind == "none":
        return None

    cx, cy = _presence_center_px(score, canvas)
    unit = canvas.unit
    color = work_assignment.get("gray", cmap.get("gray", COLOR_MAP["gray"]))
    dark = work_assignment.get("black", cmap.get("black", COLOR_MAP["black"]))
    visual_load = _score_visual_load(score)
    load_opacity = 0.52 if visual_load >= 120 else 0.70 if visual_load >= 60 else 1.0
    intensity_opacity = {"low": 0.13, "medium": 0.21, "high": 0.30}[
        presence.intensity
    ] * load_opacity
    gaze_opacity = {"none": 0.0, "low": 0.11, "medium": 0.18, "high": 0.26}[
        presence.gaze_pressure
    ] * load_opacity
    contour_count = {"low": 4, "medium": 7, "high": 11}[presence.contour_density]
    radius_x = unit * {"low": 0.18, "medium": 0.24, "high": 0.30}[presence.intensity]
    radius_y = unit * {"low": 0.24, "medium": 0.32, "high": 0.40}[presence.intensity]
    stroke = max(1.2, unit * 0.003)
    layer = dwg.g(id="presence_layer")
    seed = _presence_seed(score)
    phase = math.tau * _hash01(0, seed, "presence-phase")
    tilt = (_hash01(1, seed, "presence-tilt") - 0.5) * 1.2

    if presence.symmetry == "bilateral":
        for i, side in enumerate((-1, 1, -1, 1)):
            y_shift = (-0.36 + i * 0.24) * radius_y
            x_outer = side * radius_x * (0.34 + 0.10 * _hash01(i, seed, "sym-x"))
            x_inner = side * radius_x * (0.10 + 0.08 * _hash01(i, seed, "sym-inner"))
            layer.add(
                dwg.line(
                    start=(cx + x_outer, cy + y_shift - radius_y * 0.06),
                    end=(cx + x_inner, cy + y_shift + radius_y * (0.10 + tilt * 0.06)),
                    stroke=color,
                    stroke_width=stroke,
                    stroke_opacity=intensity_opacity * 0.58,
                    stroke_linecap="round",
                )
            )
    elif presence.symmetry == "radial":
        for i in range(6):
            angle = phase + math.tau * i / 6.0
            inner = radius_x * 0.28
            outer = radius_x * 0.86
            layer.add(
                dwg.line(
                    start=(cx + math.cos(angle) * inner, cy + math.sin(angle) * inner),
                    end=(cx + math.cos(angle) * outer, cy + math.sin(angle) * outer),
                    stroke=color,
                    stroke_width=stroke,
                    stroke_opacity=intensity_opacity * 0.72,
                    stroke_linecap="round",
                )
            )

    if presence.gaze_pressure != "none":
        for i, side in enumerate((-1, 1, -1, 1, -1, 1)):
            t = (i + 1) / 7
            angle = phase + side * (0.34 + 0.08 * i)
            start_x = cx + math.cos(angle) * radius_x * (1.05 + 0.18 * (i % 2))
            start_y = cy + math.sin(angle) * radius_y * (0.72 + 0.08 * i)
            end_x = cx + math.cos(angle + math.pi) * radius_x * 0.12
            end_y = cy + (t - 0.5) * radius_y * 0.16
            layer.add(
                dwg.line(
                    start=(start_x, start_y),
                    end=(end_x, end_y),
                    stroke=dark,
                    stroke_width=stroke * 0.8,
                    stroke_opacity=gaze_opacity,
                    stroke_linecap="round",
                )
            )

    flow_angle = phase * 0.35 + tilt
    tx, ty = math.cos(flow_angle), math.sin(flow_angle)
    nx, ny = -ty, tx
    for i in range(contour_count):
        t = (i + 0.5) / contour_count
        along = (
            (t - 0.5)
            * radius_x
            * (1.18 + 0.18 * _hash01(i, seed, "presence-flow-span"))
        )
        cross = math.sin(t * math.pi * 1.7 + phase) * radius_y * 0.32
        cross += (_hash01(i, seed, "presence-flow-cross") - 0.5) * radius_y * 0.28
        px = cx + tx * along + nx * cross
        py = cy + ty * along + ny * cross
        half = radius_x * (0.09 + 0.04 * _hash01(i, seed, "presence-flow-half"))
        lift = radius_y * (0.05 + 0.04 * _hash01(i, seed, "presence-flow-lift"))
        side = -1.0 if i % 2 else 1.0
        x1 = px - tx * half - nx * lift * side
        y1 = py - ty * half - ny * lift * side
        x2 = px + tx * half + nx * lift * side
        y2 = py + ty * half + ny * lift * side
        xm = px + nx * lift * side * 1.4
        ym = py + ny * lift * side * 1.4
        path = dwg.path(
            d=f"M {fmt(x1)},{fmt(y1)} Q {fmt(xm)},{fmt(ym)} {fmt(x2)},{fmt(y2)}",
            fill="none",
            stroke=color,
            stroke_width=stroke,
            stroke_opacity=intensity_opacity * 0.82,
            stroke_linecap="round",
        )
        layer.add(path)

    if presence.kind == "group_like":
        for i in range(7):
            t = (i - 3) / 3.5
            px = (
                cx
                + tx * t * radius_x * 0.78
                + nx * (_hash01(i, seed, "group-x") - 0.5) * radius_x * 0.20
            )
            py = (
                cy
                + ty * t * radius_x * 0.78
                + ny * (_hash01(i, seed, "group-y") - 0.5) * radius_y * 0.58
            )
            layer.add(
                dwg.circle(
                    center=(px, py),
                    r=max(2.0, unit * 0.006),
                    fill=color,
                    fill_opacity=intensity_opacity * 0.72,
                )
            )
    elif presence.kind == "creature_like":
        for i in range(3):
            t = (i - 1) * 0.34
            layer.add(
                dwg.line(
                    start=(cx - radius_x * 0.30 + t * radius_x, cy + radius_y * 0.32),
                    end=(cx - radius_x * 0.05 + t * radius_x, cy + radius_y * 0.44),
                    stroke=color,
                    stroke_width=stroke,
                    stroke_opacity=intensity_opacity * 0.76,
                    stroke_linecap="round",
                )
            )

    return layer
