"""Build metadata shared by the API and reference."""

from pathlib import Path


def build_number(root: Path | None = None) -> str | None:
    path = (root or Path(__file__).resolve().parents[3]) / "web" / "BUILD_NUMBER"
    try:
        return path.read_text(encoding="utf-8").strip() or None
    except OSError:
        return None
