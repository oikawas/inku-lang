import copy
import json
from contextlib import nullcontext
from pathlib import Path

import pytest

from inku_server import chatgpt_provider


rows = [row for row in json.loads((Path(__file__).parents[1] / "data/provider-wire-cases.json").read_text())["chatgpt"]
        if row["request"].get("action") == "chatgpt_auth_pause_quota"]


@pytest.mark.parametrize("row", rows, ids=lambda row: row["why"])
def test_server_quota_transition_and_persistence(row, monkeypatch):
    profile = copy.deepcopy(row["request"].get("profile"))
    saved = {"profiles": {"fixture": profile} if profile is not None else {}}
    class Store:
        writes = 0
        def lock(self, *args):
            return nullcontext()
        def read(self, owner):
            return saved
        def write(self, owner, value):
            self.writes += 1
            assert value is saved
    store = Store()
    monkeypatch.setattr(chatgpt_provider, "CredentialStore", lambda: store)
    chatgpt_provider.pause_quota("owner", "fixture", row["request"]["generation"], 100)
    expected = row["expect"]
    assert store.writes == int(expected["changed"])
    assert saved["profiles"].get("fixture") == expected.get("profile", profile)
