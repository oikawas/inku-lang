"""`review unread` sends the word in the list the server reads.

POST /api/feedback/unread-words takes `words` (a list) and `context`, and drops
unknown keys. The CLI sent `word`, so nothing was ever recorded while it
printed that the word had been reported (found while checking the CLI
reference, 2026-10-24).
"""

from __future__ import annotations

from inku_cli import cli


def test_review_unread_sends_the_word_as_a_list(monkeypatch, capsys):
    sent = []

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def request(self, method, path, *, data=None, **kwargs):
            sent.append((method, path, data))
            return {"ok": True}, None

    monkeypatch.setattr(cli, "ApiClient", FakeClient)
    monkeypatch.setattr(cli, "load_config", lambda: cli.CliConfig())

    assert cli.main(["review", "unread", "霞む", "--context", "遠くの山が霞む"]) == 0

    assert sent == [("POST", "/api/feedback/unread-words", {"words": ["霞む"], "context": "遠くの山が霞む"})]
    capsys.readouterr()
