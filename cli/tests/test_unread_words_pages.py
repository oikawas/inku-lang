"""Unread-word pagination must neither truncate nor silently repeat an old API."""

import json

from inku_cli import cli


def test_reads_each_page_and_retains_scope(monkeypatch, capsys):
    calls = []

    class Client:
        def __init__(self, *args, **kwargs):
            pass

        def request(self, method, path, *, query):
            calls.append((path, query))
            pages = {0: [{"word": "a"}, {"word": "b"}], 2: [{"word": "c"}]}
            return pages[query.get("offset", 0)], None

    monkeypatch.setattr(cli, "ApiClient", Client)
    monkeypatch.setattr(cli, "load_config", lambda: cli.CliConfig())
    assert cli.main(["unread-words", "--limit", "2", "--all-pages"]) == 0
    assert [w["word"] for w in json.loads(capsys.readouterr().out)["words"]] == ["a", "b", "c"]
    assert calls == [("/api/feedback/unread-words", {"limit": 2}),
                     ("/api/feedback/unread-words", {"limit": 2, "offset": 2})]


def test_rejects_old_server_repeating_first_page(monkeypatch, capsys):
    class Client:
        def __init__(self, *args, **kwargs):
            pass

        def request(self, method, path, *, query):
            return [{"word": "a"}, {"word": "b"}], None

    monkeypatch.setattr(cli, "ApiClient", Client)
    monkeypatch.setattr(cli, "load_config", lambda: cli.CliConfig())
    assert cli.main(["unread-words", "--limit", "2", "--all-pages"]) != 0
    assert "pagination did not advance" in capsys.readouterr().err
