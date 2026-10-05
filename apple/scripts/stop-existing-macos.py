#!/usr/bin/env python3
"""Stop this user's verified Inku application instances before a rebuild."""

import argparse
import json
import os
import plistlib
import signal
import subprocess
import sys
import time
from pathlib import Path


BUNDLE_IDS = {"app.inku.macos", "app.inku.macos.authorreview"}


def instances():
    result = subprocess.run(
        ["/bin/ps", "-ww", "-axo", "pid=,uid=,comm="],
        text=True, capture_output=True, check=True,
    )
    rows = []
    for line in result.stdout.splitlines():
        parts = line.strip().split(None, 2)
        if len(parts) != 3 or int(parts[1]) != os.getuid():
            continue
        if not parts[2].endswith("/Contents/MacOS/Inku"):
            continue
        executable = Path(parts[2])
        if not executable.is_absolute():
            raise RuntimeError("Cannot identify an Inku process with a relative executable path")
        bundle = executable.parents[2]
        info = plistlib.loads((bundle / "Contents/Info.plist").read_bytes())
        if (bundle.suffix != ".app" or info.get("CFBundleIdentifier") not in BUNDLE_IDS
                or info.get("CFBundlePackageType") != "APPL"
                or info.get("CFBundleExecutable") != "Inku"):
            raise RuntimeError(f"Unrecognized Inku-like process; no signal sent: PID {parts[0]}")
        rows.append({"pid": int(parts[0]), "uid": int(parts[1]),
                     "executable": str(executable), "bundle_id": info["CFBundleIdentifier"]})
    return rows


def stop_existing():
    before = instances()
    stopped, disappeared = [], []
    for row in before:
        current = {item["pid"]: item for item in instances()}.get(row["pid"])
        if current is None:
            disappeared.append(row["pid"])
            continue
        if current != row:
            raise RuntimeError(f"Process identity changed; no signal sent: PID {row['pid']}")
        try:
            os.kill(row["pid"], signal.SIGKILL)
            stopped.append(row["pid"])
        except ProcessLookupError:
            disappeared.append(row["pid"])
    deadline = time.monotonic() + 10
    after = instances()
    while after and time.monotonic() < deadline:
        time.sleep(0.1)
        after = instances()
    if after:
        raise RuntimeError("Inku is still running; rebuild must not begin")
    return {"signal": "SIGKILL", "before": before, "stopped_pids": stopped,
            "already_exited_pids": disappeared, "after": after}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    if sys.platform != "darwin":
        parser.error("This operation requires macOS")
    result = stop_existing()
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
