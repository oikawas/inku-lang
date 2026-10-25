"""`history show` and `history png` name a work by its UUID, not its render hash.

Two saved works can share one rh3 (the same score drawn again with the same
seed), and a stored rh3 is rewritten when its scheme changes. The UUID is the
work's own name. There is no endpoint for one work, so the CLI asks the
listing for a page of one with `anchor_id`.
"""

from __future__ import annotations

import json

import pytest

from inku_cli import cli

WORK_A = "76640192-0f3e-4c1a-9a1b-2d3c4e5f6a7b"
WORK_B = "76640192-aaaa-4bbb-8ccc-dddddddddddd"
WORK_C = "c0ffee00-1111-4222-8333-444444444444"

# Two works with one render hash: the case a hash cannot tell apart.
SHARED_RH3 = "rh3:" + "e" * 60 + "BEEF"

ITEMS = [
    {
        "id": WORK_C,
        "at": 300,
        "input": "history text",
        "source_text": "青い円がひとつ",
        "ddl": "青い円を置く。",
        "score": {"canvas": "square", "instructions": [{"primitive": "circle"}]},
        "svg": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 900 1600"></svg>',
        "render_hash": SHARED_RH3,
    },
    {
        "id": WORK_A,
        "at": 200,
        "input": "赤い丸",
        "ddl": "赤い丸を置く。",
        "score": {"canvas": "square", "instructions": []},
        "svg": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1600 900"></svg>',
        "render_hash": SHARED_RH3,
    },
    {
        "id": WORK_B,
        "at": 100,
        "input": "線",
        "ddl": None,
        "score": {},
        "svg": "",
        "render_hash": "rh3:" + "f" * 64,
    },
]


class FakeServer:
    """The listing as the server answers it, anchor_id included."""

    def __init__(self, *args, **kwargs):
        self.calls: list[dict] = []
        FakeServer.last = self

    def request(self, method, path, *, query=None, **kwargs):
        assert (method, path) == ("GET", "/api/history")
        query = {k: v for k, v in (query or {}).items() if v is not None}
        self.calls.append(query)
        limit = int(query.get("limit", 10))
        offset = int(query.get("offset", 0))
        anchor = query.get("anchor_id")
        if anchor:
            position = next((i for i, item in enumerate(ITEMS) if item["id"] == anchor), None)
            if position is not None:
                offset = (position // limit) * limit
        page = [dict(item) for item in ITEMS[offset:offset + limit]]
        if query.get("include_svg") is False:
            page = [{**item, "svg": ""} for item in page]
        return {"items": page, "total": len(ITEMS), "offset": offset, "limit": limit}, None


@pytest.fixture
def server(monkeypatch):
    monkeypatch.setattr(cli, "ApiClient", FakeServer)
    printed: list = []
    monkeypatch.setattr(cli, "_print_json", printed.append)
    return printed


def _run(argv):
    args = cli.build_parser().parse_args(argv)
    return args.func(args)


def test_a_full_uuid_is_one_page_of_one_by_anchor(server):
    assert _run(["history", "show", WORK_A]) == 0
    assert FakeServer.last.calls == [{"anchor_id": WORK_A, "limit": 1, "include_svg": False}]
    assert server == [{
        "id": WORK_A,
        "at": 200,
        "description": "赤い丸",
        "ddl": "赤い丸を置く。",
        "score": {"canvas": "square", "instructions": []},
    }]


def test_works_sharing_one_render_hash_are_told_apart_by_uuid(server):
    assert _run(["history", "show", WORK_C]) == 0
    assert _run(["history", "show", WORK_A]) == 0
    assert [entry["id"] for entry in server] == [WORK_C, WORK_A]


def test_the_description_is_the_authors_own_words(server, capsys):
    assert _run(["history", "show", WORK_C, "--part", "description"]) == 0
    assert capsys.readouterr().out == "青い円がひとつ\n"
    assert _run(["history", "show", WORK_C, "--part", "ddl"]) == 0
    assert capsys.readouterr().out == "青い円を置く。\n"
    assert _run(["history", "show", WORK_C, "--part", "score"]) == 0
    assert server == [{"canvas": "square", "instructions": [{"primitive": "circle"}]}]


def test_a_prefix_resolves_against_the_listing_without_pictures(server):
    assert _run(["history", "show", "C0FFEE"]) == 0
    assert server[0]["id"] == WORK_C
    listing, anchored = FakeServer.last.calls
    assert listing["include_svg"] is False
    assert anchored["anchor_id"] == WORK_C


def test_an_ambiguous_prefix_is_refused_with_candidates(server):
    with pytest.raises(cli.CliError, match="ambiguous.*Use more characters") as error:
        _run(["history", "show", "76640192"])
    assert WORK_A in str(error.value) and WORK_B in str(error.value)


def test_an_anchor_the_server_does_not_find_is_not_taken_for_the_newest_work(server):
    missing = "00000000-0000-4000-8000-000000000000"
    with pytest.raises(cli.CliError, match="work id not found"):
        _run(["history", "show", missing])


def test_png_writes_the_saved_svg_alone_at_the_long_edge(server, monkeypatch, tmp_path):
    rasterized = []
    monkeypatch.setattr(cli, "svg_to_png", lambda svg, **kwargs: rasterized.append((svg, kwargs)) or b"png")
    assert _run(["history", "png", WORK_A, "-o", f"{tmp_path}/out/"]) == 0
    assert _run(["history", "png", WORK_C, "-o", str(tmp_path / "tall.png"), "--size", "512"]) == 0
    assert (tmp_path / "out" / f"{WORK_A}.png").read_bytes() == b"png"
    assert (tmp_path / "tall.png").read_bytes() == b"png"
    # Landscape is sized by width, portrait by height; the other side keeps the aspect.
    assert [kwargs for _, kwargs in rasterized] == [{"width": 1024}, {"height": 512}]
    assert rasterized[0][0] == ITEMS[1]["svg"]
    assert FakeServer.last.calls[-1] == {"anchor_id": WORK_C, "limit": 1}
    assert server[0]["path"] == str(tmp_path / "out" / f"{WORK_A}.png")


def test_png_refuses_a_work_without_a_saved_svg(server, tmp_path):
    with pytest.raises(cli.CliError, match="no saved SVG"):
        _run(["history", "png", WORK_B, "-o", str(tmp_path / "b.png")])


def test_png_refuses_a_size_too_small_to_look_at(server, tmp_path):
    with pytest.raises(cli.CliError, match="at least 64"):
        _run(["history", "png", WORK_A, "-o", str(tmp_path / "a.png"), "--size", "10"])


def test_the_listing_keeps_its_request_when_pictures_are_wanted():
    """`include_svg` is only sent to withhold the pictures; existing callers send what they sent."""

    class Recorder:
        def __init__(self):
            self.queries = []

        def request(self, method, path, *, query=None, **kwargs):
            self.queries.append(query)
            return {"items": [], "total": 0}, None

    recorder = Recorder()
    cli._fetch_all_history(recorder)
    assert recorder.queries[0]["include_svg"] is None
    json.dumps(recorder.queries)
