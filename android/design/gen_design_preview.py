#!/usr/bin/env python3
"""Bake the Android token layer into HTML cards for Claude Design.

The tokens are Kotlin, and Kotlin is not something a design tool can open. This
reads `ui/theme/Color.kt`, `Dimens.kt` and `Type.kt` and writes one HTML page per
group, each carrying an `@dsCard` marker on its first line so the Design System
pane can index it.

**It reads the Kotlin source rather than running the app on purpose.** A
generator that needed Gradle or the Android SDK could only run on a machine with
the toolchain, which is not the machine CI uses, and the whole point of baking
these files is that a job can rebake them and fail when the checked-in copies
have gone stale. Parsing declarations is enough: the tokens are literals by
construction, because stage A-1 forbids computing them.

The output is deterministic -- no timestamps, no ordering by hash -- because
`test_t8_design_preview_is_what_the_generator_bakes` requires byte identity, and
a byte-identical check against a generator that varies is just a flaky test.

Usage:
    python android/design/gen_design_preview.py [--out DIR]
"""

from __future__ import annotations

import argparse
import html
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
ANDROID_TREE = HERE.parent
THEME = ANDROID_TREE / "app/src/main/java/app/inku/mobile/ui/theme"

COLOR_KT = THEME / "Color.kt"
DIMENS_KT = THEME / "Dimens.kt"
TYPE_KT = THEME / "Type.kt"

# A KDoc block immediately above a declaration is that token's description. Both
# `/** one line */` and the multi-line form appear in the token files.
KDOC_ONE_LINE = re.compile(r"^\s*/\*\*\s*(.*?)\s*\*/\s*$")
KDOC_CLOSE = re.compile(r"^\s*\*+/\s*$")

COLOR_DECL = re.compile(r"^val\s+(\w+)\s*=\s*Color\((0x[0-9A-Fa-f]+)\)\s*$")
DIMEN_DECL = re.compile(r"^\s*val\s+(\w+):\s*Dp\s*=\s*(\d+\.?\d*)\.dp\s*$")
DIMEN_ALIAS = re.compile(r"^\s*val\s+(\w+):\s*Dp\s*=\s*(\w+)\s*$")
TYPE_DECL = re.compile(r"^\s*val\s+(\w+):\s*TextUnit\s*=\s*(\d+\.?\d*)\.sp\s*$")
SECTION = re.compile(r"^\s*//\s*---\s*(.+?)\s*-{2,}\s*$")


def _kdoc_above(lines: list[str], index: int) -> str:
    """The KDoc that ends on the line before `index`, flattened to one line."""
    i = index - 1
    while i >= 0 and not lines[i].strip():
        i -= 1
    if i < 0:
        return ""
    one = KDOC_ONE_LINE.match(lines[i])
    if one:
        return one.group(1)
    if not KDOC_CLOSE.match(lines[i]):
        return ""
    body: list[str] = []
    i -= 1
    while i >= 0 and "/**" not in lines[i]:
        body.append(lines[i].strip().lstrip("*").strip())
        i -= 1
    if i >= 0:
        body.append(lines[i].split("/**", 1)[1].strip())
    text = " ".join(part for part in reversed(body) if part)
    return text.split(". ")[0].rstrip(".") + "." if text else ""


def _parse(path: pathlib.Path, decl: re.Pattern[str]) -> list[tuple[str, str, str, str]]:
    """(section, name, value, doc) for every declaration `decl` matches."""
    lines = path.read_text(encoding="utf-8").splitlines()
    section = ""
    found: list[tuple[str, str, str, str]] = []
    for i, line in enumerate(lines):
        heading = SECTION.match(line)
        if heading:
            section = heading.group(1)
            continue
        match = decl.match(line)
        if match:
            found.append((section, match.group(1), match.group(2), _kdoc_above(lines, i)))
    return found


def _parse_dimens() -> list[tuple[str, str, str, str]]:
    """Dimensions, with aliases (`radiusCard = spaceXxl`) resolved to numbers."""
    direct = _parse(DIMENS_KT, DIMEN_DECL)
    by_name = {name: value for _, name, value, _ in direct}
    aliases = [
        (section, name, by_name[target], doc)
        for section, name, target, doc in _parse(DIMENS_KT, DIMEN_ALIAS)
        if target in by_name
    ]
    merged = direct + aliases
    # Declaration order is what the file reads like; keep it stable by sorting on
    # section first and then on the numeric value, so the page groups sensibly and
    # two runs never disagree.
    order = {section: n for n, section in enumerate(dict.fromkeys(s for s, _, _, _ in merged))}
    return sorted(merged, key=lambda row: (order[row[0]], float(row[2]), row[1]))


def _scheme_roles() -> dict[str, str]:
    """The nine `InkuColors` roles, resolved through their named colour."""
    text = COLOR_KT.read_text(encoding="utf-8")
    literals = dict(
        (name, value)
        for line in text.splitlines()
        for name, value in [m.groups() for m in [COLOR_DECL.match(line)] if m]
    )
    block = re.search(r"darkColorScheme\((.*?)\n\)", text, re.S)
    if not block:
        return {}
    roles: dict[str, str] = {}
    for role, token in re.findall(r"(\w+)\s*=\s*(\w+),", block.group(1)):
        if token in literals:
            roles[role] = literals[token]
    return roles


def _css_color(argb: str) -> str:
    """`0xAARRGGBB` as the `#rrggbbaa` CSS wants."""
    digits = argb[2:].rjust(8, "0")
    alpha, rgb = digits[:2], digits[2:]
    return f"#{rgb}{alpha}".lower()


HEAD = """<!-- @dsCard group="{group}" -->
<!doctype html>
<meta charset="utf-8">
<title>{title}</title>
<style>
  :root {{ color-scheme: dark; }}
  body {{
    margin: 0; padding: 32px;
    background: #11100f; color: #ede7de;
    font: 14px/1.6 -apple-system, "Helvetica Neue", "Hiragino Sans", sans-serif;
  }}
  h1 {{ font-size: 21px; font-weight: 600; margin: 0 0 4px; }}
  .lede {{ color: #cfc6ba; max-width: 62ch; margin: 0 0 28px; }}
  h2 {{
    font-size: 12px; font-weight: 600; letter-spacing: .08em; text-transform: uppercase;
    color: #cfc6ba; margin: 32px 0 12px; padding-bottom: 6px; border-bottom: 1px solid #34302b;
  }}
  .grid {{ display: grid; gap: 12px; grid-template-columns: repeat(auto-fill, minmax(210px, 1fr)); }}
  .tile {{ background: #181715; border: 1px solid #34302b; border-radius: 14px; padding: 12px; }}
  .swatch {{
    height: 56px; border-radius: 8px; border: 1px solid #66000000;
    background-image: linear-gradient(45deg, #2a2622 25%, transparent 25%),
                      linear-gradient(-45deg, #2a2622 25%, transparent 25%),
                      linear-gradient(45deg, transparent 75%, #2a2622 75%),
                      linear-gradient(-45deg, transparent 75%, #2a2622 75%);
    background-size: 12px 12px;
    background-position: 0 0, 0 6px, 6px -6px, -6px 0;
    margin-bottom: 10px; position: relative; overflow: hidden;
  }}
  .swatch span {{ position: absolute; inset: 0; }}
  .name {{ font-weight: 600; word-break: break-word; }}
  .value {{ color: #cfc6ba; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 12px; }}
  .doc {{ color: #cfc6ba; margin-top: 6px; }}
  .bar {{ background: #7fa6d8; height: 10px; border-radius: 5px; margin: 10px 0; }}
  table {{ border-collapse: collapse; width: 100%; }}
  th, td {{ text-align: left; padding: 8px 10px; border-bottom: 1px solid #24211e; vertical-align: baseline; }}
  th {{ color: #cfc6ba; font-weight: 600; font-size: 12px; }}
  td.n {{ font-family: ui-monospace, SFMono-Regular, Menlo, monospace; white-space: nowrap; }}
  .role {{ display: flex; align-items: center; gap: 10px; }}
  .chip {{ width: 22px; height: 22px; border-radius: 4px; border: 1px solid #514a43; flex: none; }}
</style>
<h1>{title}</h1>
<p class="lede">{lede}</p>
"""


def _page(group: str, title: str, lede: str, body: str) -> str:
    return HEAD.format(group=group, title=title, lede=lede) + body


def _colors_page() -> str:
    roles = _scheme_roles()
    rows = "".join(
        f'<tr><td><div class="role"><span class="chip" style="background:{_css_color(v)}"></span>'
        f"<code>{html.escape(role)}</code></div></td>"
        f'<td class="n">{html.escape(v.upper())}</td></tr>'
        for role, v in roles.items()
    )
    scheme = (
        "<h2>What MaterialTheme exposes</h2>"
        "<p class=\"lede\">The nine roles <code>MaterialTheme.colorScheme</code> exposes. "
        "160 call sites read these indirectly, so a change here moves the whole app. "
        "The app is dark-only.</p>"
        f"<table><tr><th>role</th><th>ARGB</th></tr>{rows}</table>"
    )

    sections: dict[str, list[str]] = {}
    for section, name, value, doc in _parse(COLOR_KT, COLOR_DECL):
        tile = (
            f'<div class="tile">'
            f'<div class="swatch"><span style="background:{_css_color(value)}"></span></div>'
            f'<div class="name">{html.escape(name)}</div>'
            f'<div class="value">{html.escape(value.upper())}</div>'
            f'<div class="doc">{html.escape(doc)}</div>'
            f"</div>"
        )
        sections.setdefault(section or "Tokens", []).append(tile)

    body = scheme + "".join(
        f"<h2>{html.escape(section)}</h2><div class=\"grid\">{''.join(tiles)}</div>"
        for section, tiles in sections.items()
    )
    return _page(
        "Color",
        "inku Android — Color",
        "Every colour the app paints with, named by what it is for. The values are "
        "exactly the ones the screens used before the token layer existed: nothing was "
        "merged or rounded, so two roles that happen to share an ARGB keep two names.",
        body,
    )


def _dimens_page() -> str:
    sections: dict[str, list[str]] = {}
    for section, name, value, doc in _parse_dimens():
        px = float(value)
        bar = min(px, 320)
        sections.setdefault(section or "Tokens", []).append(
            f"<tr><td><code>{html.escape(name)}</code></td>"
            f'<td class="n">{html.escape(value)}dp</td>'
            f'<td style="width:45%"><div class="bar" style="width:{bar / 320 * 100:.4f}%"></div></td>'
            f"<td>{html.escape(doc)}</td></tr>"
        )
    body = "".join(
        f"<h2>{html.escape(section)}</h2><table>"
        f"<tr><th>token</th><th>value</th><th></th><th>what it measures</th></tr>"
        f"{''.join(rows)}</table>"
        for section, rows in sections.items()
    )
    return _page(
        "Dimens",
        "inku Android — Dimens",
        "Every distance the app measures with. These are not on a 4dp grid — 22 of the "
        "53 sit off it — because pulling them onto one would move the drawing. That work "
        "belongs to the stage that rebuilds the screens. Bars are drawn to scale, "
        "clamped at 320dp.",
        body,
    )


def _type_page() -> str:
    rows = "".join(
        f"<tr><td><code>{html.escape(name)}</code></td>"
        f'<td class="n">{html.escape(value)}sp</td>'
        f'<td style="font-size:{value}px">Aa 墨 いろは</td>'
        f"<td>{html.escape(doc)}</td></tr>"
        for _, name, value, doc in _parse(TYPE_KT, TYPE_DECL)
    )
    # The usage table lives in `Type.kt`'s KDoc, so every row carries a ` * ` prefix.
    scale = re.findall(r"^\s*\*\s*\|\s*`(\w+)`\s*\|\s*(\d+)\s*\|\s*(.+?)\s*\|\s*$",
                       TYPE_KT.read_text(encoding="utf-8"), re.M)
    usage = "".join(
        f"<tr><td><code>{html.escape(step)}</code></td>"
        f'<td class="n">{html.escape(uses)}</td><td>{html.escape(carries)}</td></tr>'
        for step, uses, carries in scale
    )
    body = (
        "<h2>Hand-set sizes</h2>"
        "<p class=\"lede\">The eight places that override a size or a line height on top "
        "of a Material scale step. The preview column is rendered in CSS px, which is a "
        "sketch of the relationship, not the device rendering.</p>"
        f"<table><tr><th>token</th><th>value</th><th>preview</th><th>where</th></tr>{rows}</table>"
        "<h2>Which scale steps the screens use</h2>"
        "<p class=\"lede\">The app defines no <code>Typography</code> of its own; all 140 "
        "text styles come from M3's default scale. The distribution is the useful part: "
        "<code>labelSmall</code> carries more than half of all text.</p>"
        f"<table><tr><th>step</th><th>uses</th><th>what it carries</th></tr>{usage}</table>"
    )
    return _page(
        "Type",
        "inku Android — Type",
        "Type sizes the app sets by hand, and a record of which Material scale steps it "
        "actually leans on.",
        body,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--out",
        type=pathlib.Path,
        default=HERE / "preview",
        help="where to write the HTML cards (default: android/design/preview)",
    )
    args = parser.parse_args(argv)

    args.out.mkdir(parents=True, exist_ok=True)
    pages = {
        "color.html": _colors_page(),
        "dimens.html": _dimens_page(),
        "type.html": _type_page(),
    }
    for name, text in pages.items():
        (args.out / name).write_text(text, encoding="utf-8", newline="\n")
        print(f"wrote {args.out / name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
