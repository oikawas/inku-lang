"""Plan Saijiki v3 changes to copied installed plugin packages.

This module only reads and produces proposed bytes; it never writes packages.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

from inku_server.ddl_export import migrate_v2_export
from .saijiki_v3_migration import migrate_unit_v3

_OLD_TOOL = re.compile(
    r"細筆|太筆|ロットリング|クレヨン|ビュラン|ドライポイント|"
    r"(?<![a-z])(?:fine-brush|thick-brush|rotring|crayon|burin|drypoint)(?![a-z])",
    re.IGNORECASE,
)


def plan_packages(directory: Path, *, journal: Callable[[dict[str, Any]], None] | None = None) -> tuple[dict[str, Any], dict[Path, bytes]]:
    """Return a private report and proposed package files, leaving the input unchanged."""
    root = directory.resolve(strict=True)
    if directory.is_symlink() or not root.is_dir():
        raise ValueError("invalid_package_root")
    report: dict[str, Any] = {"packages": 0, "changed": 0, "unchanged": 0,
                              "refused_records": [], "notes_with_old_tools": [],
                              "unadjusted_thinness_records": [], "unassociated_tool_records": [],
                              "unassociated_sweep_records": [], "edits": {}}
    proposed: dict[Path, bytes] = {}
    for child in sorted(root.iterdir()):
        if child.is_symlink():
            raise ValueError("symlink_in_package_root")
        if not child.is_dir():
            continue
        path = child / "package.json"
        if not path.exists():
            continue
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 16_000_000:
            raise ValueError("invalid_package_file")
        report["packages"] += 1
        original = path.read_bytes()
        index = None
        try:
            package = json.loads(original)
            words = package["words"]
            if not isinstance(words, list):
                raise ValueError("invalid_words")
            for index, word in enumerate(words):
                definition = word["definition"]
                unit = {"definitions": [definition]}
                result = json.loads(migrate_unit_v3(json.dumps(unit, ensure_ascii=False).encode()))
                if journal:
                    journal({"package": child.name, "word": index, "kind": "definition", "input": unit, "answer": result})
                answer = result["definitions"][0]
                if result.get("error") or answer.get("error"):
                    raise ValueError(json.dumps(answer.get("error") or result["error"], ensure_ascii=False))
                for language in ("ja", "en"):
                    note = word.get(f"note_{language}")
                    if isinstance(note, str) and _OLD_TOOL.search(note):
                        report["notes_with_old_tools"].append({"package": child.name, "word": index, "language": language})
                    example = word.get(f"example_{language}")
                    if isinstance(example, str) and example:
                        moved = migrate_v2_export(
                            example, language, [{"definition": definition, "note": ""}], include_details=True,
                            journal=(lambda entry: journal({"package": child.name, "word": index,
                                                            "language": language, **entry})) if journal else None)
                        word[f"example_{language}"] = moved["ddl"]
                        for edit in moved["edit_details"]:
                            key = f"{edit['original']} -> {edit['replacement']}"
                            report["edits"][key] = report["edits"].get(key, 0) + 1
                        for kind in ("unassociated_tools", "unassociated_sweeps"):
                            if moved[kind]:
                                report["unassociated_tool_records" if kind == "unassociated_tools" else "unassociated_sweep_records"].append(
                                    {"package": child.name, "word": index, "language": language, kind: moved[kind]})
                if answer.get("unadjusted_thinness"):
                    report["unadjusted_thinness_records"].append({"package": child.name, "word": index,
                                                                  "details": answer["unadjusted_thinness"]})
                word["definition"] = answer["definition"]
            encoded = (json.dumps(package, ensure_ascii=False, indent=2) + "\n").encode()
            # Do not mark formatting alone as a change.
            if json.loads(original) != package:
                proposed[path] = encoded
                report["changed"] += 1
            else:
                report["unchanged"] += 1
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            report["refused_records"].append({"package": child.name, "word": index, "error": str(exc),
                                               "source": original.decode("utf-8", errors="replace"), "locks": 1 if index is not None else 0})
    return report, proposed
