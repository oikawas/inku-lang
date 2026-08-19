"""The web image builds its bundle on the builder, not on the target platform.

Release run 32092151332 published `inku-api:2.13.42` and never published
`inku-web:2.13.42`. The web job did not fail and was not slow in any way a
timeout would describe: `#22 [linux/arm64 build 6/6] RUN npm run build` printed
`rendering chunks...` and then said nothing for 21,480 seconds, until the 6h
job limit cancelled it. The amd64 leg of the same run finished that step in
14.4 seconds. rollup was running under QEMU, and it stopped.

The fix is one word in `web/Dockerfile`: the build stage is pinned to
`$BUILDPLATFORM`, so the toolchain always runs on the builder's own
architecture. That is only correct because the app declares no runtime
dependencies and adapter-node emits plain JS -- the bundle is the same bytes
whichever arch produced it -- while the runtime stage stays on the target
platform, which is where the shipped node binary comes from.

Nothing else could have caught this. The only workflow that builds the image
fires on a tag push, which is after the version is public, and a green test
suite says nothing about a Dockerfile. So the check here is static: it reads
the stages out of the Dockerfile and asserts the shape, at the moment it is
changed.
"""
from __future__ import annotations

import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[2]
DOCKERFILE = ROOT / "web" / "Dockerfile"

FROM_LINE = re.compile(r"^FROM\s+(?:(--platform=\S+)\s+)?(\S+)(?:\s+AS\s+(\S+))?\s*$", re.IGNORECASE)

# The commands that run the site build. `npm ci` is deliberately absent: the
# runtime stage runs one too, and installing for the target platform is what
# that stage is for.
TOOLCHAIN = ("npm run build", "vite build")


class Stage:
    def __init__(self, name: str | None, platform: str | None):
        self.name = name
        self.platform = platform
        self.runs: list[str] = []

    def runs_the_toolchain(self) -> bool:
        return any(marker in run for run in self.runs for marker in TOOLCHAIN)

    def __repr__(self) -> str:  # shown when an assertion fails
        return f"<stage {self.name or '(unnamed)'} platform={self.platform}>"


def _stages() -> list[Stage]:
    stages: list[Stage] = []
    for line in DOCKERFILE.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        match = FROM_LINE.match(stripped)
        if match:
            stages.append(Stage(name=match.group(3), platform=match.group(1)))
        elif stripped.startswith("RUN ") and stages:
            stages[-1].runs.append(stripped)
    return stages


def test_the_stage_that_runs_the_web_build_is_pinned_to_the_build_platform():
    """T-301"""
    unpinned = [
        stage
        for stage in _stages()
        if stage.runs_the_toolchain() and stage.platform != "--platform=$BUILDPLATFORM"
    ]

    assert not unpinned, (
        f"{unpinned} runs the web build on the target platform; on the arm64 leg "
        "that means rollup under QEMU, which hung for 5h58m in release run "
        "32092151332 and left the version without a web image"
    )


def test_the_stage_the_image_ships_from_is_not_pinned_to_the_build_platform():
    """T-302

    The other direction of the same rule. Pinning the final stage would build
    an amd64 runtime and publish it under the arm64 tag: the manifest would
    still say arm64, and the image would not run.
    """
    shipped = _stages()[-1]

    assert shipped.platform is None, (
        f"{shipped} is the stage the image ships from and it is pinned; the "
        "published arm64 image would carry the builder's architecture"
    )


def test_the_scan_finds_the_stages_it_is_meant_to_find():
    """T-303

    Both assertions above are satisfied by a Dockerfile this parser cannot
    read: no stages means no unpinned stage, and no toolchain means the first
    assertion looks at nothing.
    """
    stages = _stages()

    assert len(stages) >= 2, f"the scan found {stages}"
    assert [stage for stage in stages if stage.runs_the_toolchain()], (
        f"the scan found no stage running any of {TOOLCHAIN} in {stages}"
    )
