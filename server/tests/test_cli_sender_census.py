"""Roll call of the senders: every `/api/paint` field must reach the CLI or be excused.

`/api/paint` takes one request model but has more than one sender, and a sender that
never names a field is not an error -- pydantic fills the default and returns 200.
So a layer added to the server arrives complete for the web UI and is simply absent
from the command line, silently, for as long as nobody looks.

Measured on 2026-08-04 at `ab1b8a22`, before this census existed: of the 37
`PaintRequest` fields the web UI sent 33 and the CLI sent 17. Among the 18 the CLI
left out were `sketch`, `wild`, `variation_amplitude`, `catalog_mode` and
`interpretation_seed` -- so **no drawing ever made from the command line had gone
through Stage 0.5**, and neither had any bench or reference corpus, while the web
UI had it on by default.

The 14 `TestClient` suites did not catch it because every one of them names the
fields it is testing. They measure what happens when a field IS sent. Nothing
measured what happens to a client that stays quiet.

This test reads `cli/src/inku_cli/cli.py` as TEXT and parses it with `ast`. The CLI
lives in its own virtualenv (`cli/pyproject.toml`), so importing it from the server
suite is not available; parsing is not a weaker check here, because the thing being
checked is which literal keys the payload dict names.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

from inku_server.api_core.routers.render import PaintRequest

ROOT = pathlib.Path(__file__).resolve().parents[2]

# Key the skip to the DIRECTORY, not to the file below: `cli/` is not part of the
# pentala sync path, so on the deployed server the whole tree is absent and reading
# the source would raise FileNotFoundError. Wherever `cli/` exists -- every
# checkout, every developer machine, CI -- the census runs, and a moved or renamed
# cli.py is a failure rather than a skip.
CLI_TREE = ROOT / "cli"
CLI_SOURCE = CLI_TREE / "src/inku_cli/cli.py"

cli_tree_only = pytest.mark.skipif(
    not CLI_TREE.is_dir(),
    reason="cli/ is not synced to the server; the sender census runs where the tree exists",
)

# Fields the CLI deliberately does not send, each with the reason it is excused.
# A field is excused only for a reason that survives being read aloud: "the CLI has
# no use for it" is one, "we forgot" is not.
EXCUSED: dict[str, str] = {
    # Deprecated: the server ignores it and resolves the catalog from catalog_id.
    "color_map": "deprecated; ignored server-side in favour of catalog_id",
    # History and lineage. These decide how a drawing is filed, not how it looks.
    # The CLI files its own history through /api/history when --save-history is set.
    "count_generation": "history bookkeeping; does not change the drawing",
    "history_at": "history bookkeeping; the server stamps the time",
    "history_source_text": "history bookkeeping; does not change the drawing",
    "history_display_label": "history bookkeeping; does not change the drawing",
    "batch_line_number": "history bookkeeping; does not change the drawing",
    "batch_run_id": "history bookkeeping; does not change the drawing",
    "history_visibility": "history bookkeeping; does not change the drawing",
    "lineage_parent_node_id": "lineage; `refine perform` sends it on its own path",
    "derivation_kind": "lineage; `refine perform` sends it on its own path",
    "derivation_metadata": "lineage; `refine perform` sends it on its own path",
    # Both sides default to True, so staying quiet and sending True are the same
    # request. A flag to turn it off is a separate judgement, not an omission.
    "auto_repair": "server default True matches what the CLI wants; no flag defined yet",
}


def _payload_keys() -> set[str]:
    """The literal keys of the dict `_paint_payload` builds, read from the source."""
    tree = ast.parse(CLI_SOURCE.read_text(encoding="utf-8"))
    function = next(
        node for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "_paint_payload"
    )
    keys: set[str] = set()
    for node in ast.walk(function):
        if not isinstance(node, ast.Dict):
            continue
        for key in node.keys:
            if isinstance(key, ast.Constant) and isinstance(key.value, str):
                keys.add(key.value)
    return keys


@cli_tree_only
def test_the_cli_names_every_paint_field_or_excuses_it():
    fields = set(PaintRequest.model_fields)
    sent = _payload_keys()

    # State how many were looked at. An enumeration that silently empties out --
    # a renamed model, a parser that finds no dict -- would otherwise pass by
    # asserting nothing at all.
    assert len(fields) >= 37, f"PaintRequest のフィールドが {len(fields)} 件しか見えていない"
    assert len(sent) >= 25, f"_paint_payload の鍵が {len(sent)} 件しか読めていない"

    missing = sorted(fields - sent - set(EXCUSED))
    assert not missing, (
        f"PaintRequest {len(fields)} 件のうち {len(missing)} 件が CLI から送られず、"
        f"除外表にも無い: {missing}. "
        "旗を CLI に足して _paint_payload へ載せるか、EXCUSED へ理由つきで書く"
    )


@cli_tree_only
def test_every_key_the_cli_sends_is_a_field_the_server_declares():
    """A misspelled key is accepted with a 200 and changes nothing.

    Extra fields are dropped by the request model, so `sketch_grane` would draw a
    picture, save it, and report success while the layer it names never ran.
    """
    unknown = sorted(_payload_keys() - set(PaintRequest.model_fields))
    assert not unknown, f"PaintRequest に無い鍵を送っている（黙って捨てられる）: {unknown}"


@cli_tree_only
def test_the_excuse_table_does_not_rot():
    """An excuse for a field that no longer exists hides a field that does."""
    fields = set(PaintRequest.model_fields)
    stale = sorted(set(EXCUSED) - fields)
    assert not stale, f"除外表に PaintRequest に無い名前が残っている: {stale}"

    both = sorted(set(EXCUSED) & _payload_keys())
    assert not both, f"送っているのに除外表にも載っている: {both}"

    assert len(EXCUSED) == 12, f"除外表が {len(EXCUSED)} 件（数を動かしたなら理由も書く）"
    for name, reason in EXCUSED.items():
        assert reason.strip(), f"{name} の除外理由が空"
