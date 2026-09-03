"""Focused acceptance for I-655 documentation-gate diagnostics."""

from __future__ import annotations

import importlib.util
import pathlib
import types

ROOT = pathlib.Path(__file__).resolve().parents[2]
CHECK_DOCS = ROOT / "server/scripts/check_docs.py"


def _check_docs() -> types.ModuleType:
    spec = importlib.util.spec_from_file_location("check_docs_diagnostics", CHECK_DOCS)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_plugin_pair_is_checked_on_all_existing_document_faces() -> None:
    module = _check_docs()
    pair = ("PLUGIN.ja.md", "PLUGIN.md", "shape", None)
    assert pair in module.PAIRS
    assert "PLUGIN.md" in module.terminology_targets()


def test_first_reordered_heading_reports_both_source_lines(
    tmp_path: pathlib.Path,
) -> None:
    module = _check_docs()
    module.REPO_ROOT = tmp_path
    module.PAIRS = (("ja.md", "en.md", "shape", None),)
    (tmp_path / "ja.md").write_text("# Top\n\n\n### Third\n## Second\n", encoding="utf-8")
    (tmp_path / "en.md").write_text("# Top\n\n## Second\n### Third\n", encoding="utf-8")

    problem = module.check_parity()[0]

    assert "first difference: heading 2" in problem
    assert "ja.md: h3 at line 4" in problem
    assert "en.md: h2 at line 3" in problem


def test_first_excess_heading_reports_the_other_side_as_absent(
    tmp_path: pathlib.Path,
) -> None:
    module = _check_docs()
    module.REPO_ROOT = tmp_path
    module.PAIRS = (("ja.md", "en.md", "shape", None),)
    (tmp_path / "ja.md").write_text("# Top\n## Section\n### Extra\n", encoding="utf-8")
    (tmp_path / "en.md").write_text("# Top\n## Section\n", encoding="utf-8")

    problem = module.check_parity()[0]

    assert "first difference: heading 3" in problem
    assert "ja.md: h3 at line 3" in problem
    assert "en.md: <no heading>" in problem
