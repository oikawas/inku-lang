from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_t327_user_facing_compat_copy_names_the_portable_subset_without_overclaiming():
    ja = (ROOT / "web/src/lib/i18n/ja.ts").read_text(encoding="utf-8")
    en = (ROOT / "web/src/lib/i18n/en.ts").read_text(encoding="utf-8")
    cli = (ROOT / "cli/src/inku_cli/cli.py").read_text(encoding="utf-8")
    cli_readme = (ROOT / "cli/README.md").read_text(encoding="utf-8")
    spec_ja = (ROOT / "SPEC.ja.md").read_text(encoding="utf-8")
    spec_en = (ROOT / "SPEC.md").read_text(encoding="utf-8")

    assert "定義済みportable subset" in ja
    assert "defined portable subset" in en
    assert "filter / clip-path を使わない" in ja
    assert "filter / clip-path free" in en
    assert "defined portable subset" in cli
    assert "defined portable subset" in " ".join(cli_readme.split())
    assert "定義済みportable subset" in spec_ja
    assert "defined portable subset" in spec_en
    for text in (ja, en, cli, cli_readme, spec_ja, spec_en):
        assert "all SVG editors" not in text
        assert "すべてのSVG editor" not in text
