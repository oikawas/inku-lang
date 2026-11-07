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


def test_relative_link_that_escapes_repository_root_is_reported(
    tmp_path: pathlib.Path,
) -> None:
    module = _check_docs()
    module.REPO_ROOT = tmp_path
    (tmp_path / "README.md").write_text("# Root\n", encoding="utf-8")
    (tmp_path / "guide.md").write_text(
        "[escape](../../README.md)\n", encoding="utf-8"
    )

    problems = module.check_links({"README.md", "guide.md"})

    assert problems == [
        "guide.md:1: relative link escapes the repository root: ../../README.md"
    ]


def test_relative_link_to_a_normal_parent_path_is_accepted(
    tmp_path: pathlib.Path,
) -> None:
    module = _check_docs()
    module.REPO_ROOT = tmp_path
    (tmp_path / "README.md").write_text("# Root\n", encoding="utf-8")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs/guide.md").write_text(
        "[root](../README.md)\n", encoding="utf-8"
    )

    assert module.check_links({"README.md", "docs/guide.md"}) == []


def test_macos_notices_written_from_another_lock_are_reported(
    tmp_path: pathlib.Path,
) -> None:
    import hashlib
    import json

    module = _check_docs()
    module.REPO_ROOT = tmp_path
    (tmp_path / "core").mkdir()
    lock = tmp_path / "core/Cargo.lock"
    lock.write_text("version = 4\n", encoding="utf-8")
    notices = tmp_path / module.MACOS_NOTICES
    notices.parent.mkdir(parents=True)
    digest = hashlib.sha256(lock.read_bytes()).hexdigest()
    notices.write_text(json.dumps({"inputs": {"core/Cargo.lock": digest}}), encoding="utf-8")

    assert module.check_notice_inputs() == []

    # I-733: a crate added to the lock left the snapshot behind.
    lock.write_text("version = 4\n[[package]]\nname = \"libm\"\n", encoding="utf-8")
    [problem] = module.check_notice_inputs()
    assert problem.startswith(f"{module.MACOS_NOTICES}: written from another core/Cargo.lock")
    assert "build-macos-notices.py" in problem


def _editions(newest: int) -> str:
    return "".join(f'            Self::V0_{n} => "0.{n}.0",\n' for n in range(1, newest + 1))


def test_3d_viewer_built_before_the_newest_score_edition_is_reported(
    tmp_path: pathlib.Path,
) -> None:
    import json

    module = _check_docs()
    module.REPO_ROOT = tmp_path
    registration = tmp_path / module.DDL_3D_REGISTRATION
    registration.parent.mkdir(parents=True)
    registration.write_text(
        json.dumps({"viewerUrl": "/experimental/ddl-3d/b1/index.html"}), encoding="utf-8"
    )
    provenance = tmp_path / module.DDL_3D_BUILDS / "b1/wasm/provenance.json"
    provenance.parent.mkdir(parents=True)
    provenance.write_text(
        json.dumps({"coreBaseSha": "a" * 40, "coreHasLocalChanges": False}), encoding="utf-8"
    )
    types_rs = tmp_path / module.SCORE_EDITIONS
    types_rs.parent.mkdir(parents=True)
    types_rs.write_text(_editions(24), encoding="utf-8")
    built = {"source": _editions(24)}
    module._file_at_commit = lambda commit, path: built["source"]

    assert module.check_3d_viewer_edition() == []

    # I-734: the registered build's core knew Score only up to 0.23.
    built["source"] = _editions(23)
    [problem] = module.check_3d_viewer_edition()
    assert problem.startswith(f"{module.DDL_3D_BUILDS}/b1: reads Score up to 0.23.0 but core writes 0.24.0")

    # A core commit this checkout cannot read is reported, not passed.
    built["source"] = None
    [problem] = module.check_3d_viewer_edition()
    assert "cannot read" in problem

    # An empty registration hides 3D and needs no viewer.
    registration.write_text(json.dumps({"viewerUrl": ""}), encoding="utf-8")
    assert module.check_3d_viewer_edition() == []
