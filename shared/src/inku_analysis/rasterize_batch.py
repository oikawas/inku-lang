"""Rasterize a directory of SVG files to PNG, one child process per file.

    python -m inku_analysis.rasterize_batch SRC DST --width 1618 --workers 6

**Why this lives in `shared/` and not in the CLI.** Four run directories under
`cli/out2/` each carried their own copy of this -- `rasterize_one.py`,
`rasterize_all.py`, `rasterize_full.py`, `rasterize_on_pentala.py` -- and all four
called the same single line. Rasterizing is worth doing on the development
server, which is about eight times faster than the Mac, and that machine carries
only what its two services need (ledger I-059): `cli/` is not synced there and
the server image does not copy it. `inku-analysis` is a dependency of the server
itself, so this module is importable on pentala and inside the image with no
`sys.path` work at all.

**One SVG per child process.** resvg panics take the interpreter with them
([I-075]), so a pool of workers that rasterize in-process loses a worker -- and
everything it was holding -- to the first bad file. A deeply nested SVG segfaults
the interpreter on macOS and Linux alike. Each file gets its own child here, so
that costs one picture and nothing else.

**A failed file is an absent measurement, not a zero.** The child writes to a
temporary name; only the parent moves it into place, and only when the child
exited cleanly having written something. An interrupted run once left a 0-byte
PNG behind, and a 0-byte PNG is a file that exists -- it gets counted,
contact-sheeted, and looked at. Failures are carried in the report instead, and
``__main__`` prints them under UNRESOLVED with the count that was dropped.

This module imports neither ``inku_cli`` nor ``inku_server``, and must not: the
container runs it as ``python -m`` and the CLI is not in the image.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

# The name the child is spawned under. Read from the spec rather than written
# out, so renaming the module cannot leave the parent calling a module that is
# no longer there while the tests, which import it by its new name, stay green.
_MODULE = __spec__.name if __spec__ is not None else "inku_analysis.rasterize_batch"

# .../shared/src -- handed to the child so it can import inku_analysis even when
# the parent was started from a checkout that is not on the default path.
_SRC_ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Failure:
    """One SVG that was not rasterized, and why it was not."""

    source: Path
    reason: str


@dataclass(frozen=True)
class Report:
    """What a directory came to. ``written`` holds the PNGs that exist afterwards."""

    written: tuple[Path, ...]
    failed: tuple[Failure, ...]

    @property
    def succeeded(self) -> int:
        return len(self.written)

    @property
    def failures(self) -> int:
        return len(self.failed)

    @property
    def attempted(self) -> int:
        return len(self.written) + len(self.failed)


def _child_env() -> dict[str, str]:
    """Environment for the child, with this checkout's `src` reachable."""
    env = dict(os.environ)
    existing = env.get("PYTHONPATH")
    env["PYTHONPATH"] = os.pathsep.join([str(_SRC_ROOT), existing] if existing else [str(_SRC_ROOT)])
    return env


def _child_failure_reason(done: subprocess.CompletedProcess[str]) -> str:
    """Say what happened to the child in one line.

    A negative return code is a signal: that is the panic case [I-075] was about,
    and it reads as nothing at all in stderr, so it has to be named here.
    """
    if done.returncode < 0:
        return f"child killed by signal {-done.returncode}"
    lines = (done.stderr or "").strip().splitlines()
    if lines:
        return lines[-1][:200]
    if done.returncode == 0:
        return "child exited cleanly but wrote no PNG"
    return f"child exited {done.returncode}"


def _rasterize_one(source: Path, dst_dir: Path, width: int | None) -> tuple[Path, Path | None, str]:
    """Burn one SVG in its own process. Returns (source, png or None, reason)."""
    final = dst_dir / f"{source.stem}.png"
    # Hidden and suffixed, so an interrupted run leaves something that is
    # obviously not an output and that the next run over the same directory
    # will not pick up as a picture.
    partial = dst_dir / f".{source.stem}.png.part"
    argv = [sys.executable, "-m", _MODULE, "--one", str(source), str(partial)]
    if width is not None:
        argv += ["--width", str(width)]
    done = subprocess.run(argv, capture_output=True, text=True, env=_child_env())
    if done.returncode == 0 and partial.is_file() and partial.stat().st_size > 0:
        os.replace(partial, final)
        return source, final, ""
    partial.unlink(missing_ok=True)
    return source, None, _child_failure_reason(done)


def rasterize_dir(
    src: Path,
    dst: Path,
    *,
    width: int | None = None,
    workers: int = 1,
) -> Report:
    """Rasterize every ``*.svg`` directly under ``src`` into ``dst``.

    ``width`` renders at that pixel width and scales the height to keep the
    aspect ratio; omitting it renders at the width the SVG declares. ``workers``
    is how many files are in flight at once -- each still gets its own process,
    so the number only buys wall-clock, never a different picture.
    """
    src = Path(src)
    dst = Path(dst)
    if not src.is_dir():
        raise NotADirectoryError(f"{src} is not a directory")
    sources = sorted(path for path in src.glob("*.svg") if path.is_file())
    dst.mkdir(parents=True, exist_ok=True)
    if not sources:
        return Report(written=(), failed=())

    with ThreadPoolExecutor(max_workers=max(1, int(workers))) as pool:
        outcomes = list(pool.map(lambda path: _rasterize_one(path, dst, width), sources))

    return Report(
        written=tuple(png for _, png, _ in outcomes if png is not None),
        failed=tuple(Failure(source, reason) for source, png, reason in outcomes if png is None),
    )


def _render_one_file(source: Path, target: Path, width: int | None) -> None:
    """The child's whole job: read one SVG, rasterize, write the bytes.

    The bytes are produced before the file is opened. Nothing here creates a file
    it might not be able to fill.
    """
    from inku_analysis.rasterizer import svg_to_png

    png = svg_to_png(source.read_text(encoding="utf-8"), width=width)
    target.write_bytes(png)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog=f"python -m {_MODULE}",
        description="Rasterize a directory of SVG files to PNG, one child process per file.",
    )
    # Optional only so that `--one`, which carries its own two paths, can be
    # parsed by the same parser. Missing them is still an error, below.
    parser.add_argument("src", type=Path, nargs="?", help="directory holding the .svg files")
    parser.add_argument("dst", type=Path, nargs="?", help="directory the .png files are written to")
    parser.add_argument(
        "--width",
        type=int,
        help="render at this pixel width instead of the width the SVG declares",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help="rasterize this many files at once; each file still gets its own process",
    )
    # The child re-enters here. Not part of the interface: the parent is the only
    # caller, and keeping it in this module is what stops a second rule for how a
    # picture is burned from being written somewhere else.
    parser.add_argument("--one", nargs=2, type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)

    if args.one:
        _render_one_file(args.one[0], args.one[1], args.width)
        return 0
    if args.src is None or args.dst is None:
        parser.error("the following arguments are required: src, dst")

    report = rasterize_dir(args.src, args.dst, width=args.width, workers=args.workers)
    width = "the width each SVG declares" if args.width is None else f"width {args.width}"
    print(
        f"{report.attempted} files, {width}, {args.workers} at a time",
        flush=True,
    )
    print(f"done {report.succeeded} / {report.attempted}, failed {report.failures}")
    if report.failed:
        print("UNRESOLVED (absent measurements, not zeros):")
        for failure in report.failed:
            print(f"  {failure.source}  {failure.reason}")
    return 1 if report.failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
