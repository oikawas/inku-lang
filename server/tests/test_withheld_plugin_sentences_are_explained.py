"""A plugin sentence the compiler withheld is explained with the host's lists.

The shared explainer needs the enabled names, the installed-but-disabled names,
and the names this work may use from its own saved or imported definitions.
"""

from __future__ import annotations

import json

from inku_server import macro_catalog


class _Binding:
    def __init__(self) -> None:
        self.received: dict | None = None

    def explain_plugin_diagnostics(self, payload: bytes) -> bytes:
        self.received = json.loads(payload)
        return json.dumps({"schema": "inku.plugin-diagnostics.v1", "plugins": [{"name": "Old.Mark"}]}).encode()


def test_work_plugins_count_as_enabled_and_disabled_documents_are_named(monkeypatch):
    monkeypatch.setattr(macro_catalog, "_installed_plugin_names", lambda: (["Nature.若葉"], ["Old.Mark"]))
    binding = _Binding()
    diagnostics = [{"reason": "macro_resolution_missing_lock", "span": {"start_byte": 0, "end_byte": 9}}]
    explained = macro_catalog.explain_plugin_diagnostics(binding, "Old.Mark。", diagnostics, ["Studio.Mark"])
    assert explained == [{"name": "Old.Mark"}]
    assert binding.received == {
        "source": "Old.Mark。",
        "upstream_diagnostics": diagnostics,
        "enabled": ["Nature.若葉", "Studio.Mark"],
        "disabled": ["Old.Mark"],
    }


def test_no_diagnostics_or_an_older_wheel_explains_nothing(monkeypatch):
    monkeypatch.setattr(macro_catalog, "_installed_plugin_names", lambda: ([], []))
    assert macro_catalog.explain_plugin_diagnostics(_Binding(), "x", []) == []
    assert macro_catalog.explain_plugin_diagnostics(object(), "x", [{"reason": "r"}]) == []
