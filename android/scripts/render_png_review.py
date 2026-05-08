#!/usr/bin/env python3
"""Build PNG review artifacts for Android/server headless comparisons."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import cairosvg
from PIL import Image, ImageChops, ImageDraw, ImageStat


def svg_to_png(svg_path: Path, png_path: Path, *, size: int) -> None:
    if not svg_path.exists():
        raise FileNotFoundError(svg_path)
    png_path.parent.mkdir(parents=True, exist_ok=True)
    cairosvg.svg2png(
        bytestring=svg_path.read_bytes(),
        write_to=str(png_path),
        output_width=size,
        output_height=size,
    )


def _open_rgb(path: Path, *, size: int) -> Image.Image:
    image = Image.open(path).convert("RGB")
    if image.size != (size, size):
        image = image.resize((size, size), Image.Resampling.LANCZOS)
    return image


def _label(draw: ImageDraw.ImageDraw, xy: tuple[int, int], text: str) -> None:
    x, y = xy
    draw.rectangle((x, y, x + 260, y + 24), fill=(255, 255, 255))
    draw.text((x + 8, y + 5), text, fill=(32, 32, 32))


def make_pair_review(run_dir: Path, *, size: int) -> dict[str, Any]:
    android_svg = run_dir / "android" / "output.svg"
    web_svg = run_dir / "web" / "output.svg"
    android_png = run_dir / "android" / "output.png"
    web_png = run_dir / "web" / "output.png"
    review_dir = run_dir / "png-review"
    review_dir.mkdir(parents=True, exist_ok=True)

    svg_to_png(android_svg, android_png, size=size)
    svg_to_png(web_svg, web_png, size=size)

    android = _open_rgb(android_png, size=size)
    web = _open_rgb(web_png, size=size)
    diff = ImageChops.difference(android, web)
    stat = ImageStat.Stat(diff)
    mean_abs = sum(stat.mean) / (len(stat.mean) * 255.0)
    rms = (sum(value * value for value in stat.rms) / len(stat.rms)) ** 0.5 / 255.0
    bbox = diff.getbbox()

    amplified = diff.point(lambda value: min(255, value * 4))
    diff_path = review_dir / "diff-amplified.png"
    amplified.save(diff_path)

    gap = 20
    label_h = 32
    sheet = Image.new("RGB", (size * 3 + gap * 4, size + label_h + gap * 2), "white")
    sheet.paste(web, (gap, gap + label_h))
    sheet.paste(android, (size + gap * 2, gap + label_h))
    sheet.paste(amplified, (size * 2 + gap * 3, gap + label_h))
    draw = ImageDraw.Draw(sheet)
    _label(draw, (gap, gap), "server")
    _label(draw, (size + gap * 2, gap), "android")
    _label(draw, (size * 2 + gap * 3, gap), "diff x4")
    compare_path = review_dir / "server-android-diff.png"
    sheet.save(compare_path)

    metrics = {
        "run_id": run_dir.name,
        "size": size,
        "server_png": str(web_png),
        "android_png": str(android_png),
        "diff_png": str(diff_path),
        "comparison_png": str(compare_path),
        "mean_absolute_difference_percent": round(mean_abs * 100.0, 4),
        "rms_difference_percent": round(rms * 100.0, 4),
        "different_pixel_bbox": list(bbox) if bbox else None,
    }
    (review_dir / "metrics.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return metrics


def make_batch_sheet(batch_dir: Path, metrics: list[dict[str, Any]], *, thumb_width: int) -> Path | None:
    images = [Path(item["comparison_png"]) for item in metrics if item.get("comparison_png")]
    images = [path for path in images if path.exists()]
    if not images:
        return None
    loaded: list[tuple[Path, Image.Image]] = []
    for path in images:
        image = Image.open(path).convert("RGB")
        ratio = thumb_width / image.width
        loaded.append((path, image.resize((thumb_width, max(1, int(image.height * ratio))), Image.Resampling.LANCZOS)))
    gap = 16
    label_h = 26
    width = thumb_width + gap * 2
    height = gap + sum(image.height + label_h + gap for _, image in loaded)
    sheet = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(sheet)
    y = gap
    for path, image in loaded:
        draw.text((gap, y), path.parents[1].name, fill=(32, 32, 32))
        y += label_h
        sheet.paste(image, (gap, y))
        y += image.height + gap
    output = batch_dir / "png-review-contact-sheet.png"
    sheet.save(output)
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description="Create PNG review artifacts for headless comparison outputs")
    parser.add_argument("path", help="run directory or batch directory")
    parser.add_argument("--size", type=int, default=1024)
    parser.add_argument("--batch", action="store_true", help="treat PATH as a batch directory")
    parser.add_argument("--thumb-width", type=int, default=1200)
    args = parser.parse_args()

    root = Path(args.path)
    if args.batch:
        metrics: list[dict[str, Any]] = []
        for run_dir in sorted(path for path in root.iterdir() if path.is_dir()):
            if (run_dir / "android" / "output.svg").exists() and (run_dir / "web" / "output.svg").exists():
                metrics.append(make_pair_review(run_dir, size=args.size))
        sheet = make_batch_sheet(root, metrics, thumb_width=args.thumb_width)
        summary = {"count": len(metrics), "contact_sheet": str(sheet) if sheet else None, "items": metrics}
        (root / "png-review-summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0

    metrics = make_pair_review(root, size=args.size)
    print(json.dumps(metrics, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
