"""A work is drawn in the colors it was drawn in, not in today's definition.

Until this, a redraw sent only the id of a color catalog and the server looked
that id up in the build it happened to be running. The name does not decide the
colors, so a catalog edited since -- 1,274 works, 46% of the corpus, measured
2026-08-09 -- came back silently repainted, and a catalog renamed or retired
came back as a 422. Now the work carries its own recorded colors and a redraw
names the work; the catalog id stays on as a nameplate.

The gate that matters is T-1 with T-2: the recorded colors survive an edit to
today's definition, AND the same edit still reaches a drawing that named no
work. Either half alone is passed by an implementation that stopped resolving
colors altogether.

The perturbation those two apply moves `palette` as well as `map`. The Rust
core builds drawn colors from the `palette:` entries and falls back to `map`
only for a band with no candidate, so changing only `map` would not exercise
the snapshot path.
"""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import uuid
from contextlib import contextmanager
from pathlib import Path

import pytest
from fastapi.routing import APIRoute, iter_route_contexts
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from inku_server import color_catalogs as _catalogs
from inku_server import db
from inku_server.api import app
from inku_server.api_core.rendering import COLOR_CATALOG_ID_HEADER, COLOR_SOURCE_HEADER
from inku_server.color_catalogs import (
    RENAMED_COLOR_CATALOG_IDS,
    current_color_catalog_id,
    render_color_map_for_catalog,
)

client = TestClient(app)

# The nine pairs that have rows in production plus `chinese`, which was renamed
# with none. Pinned as a literal so that dropping an entry from the production
# table turns this red -- parametrizing over the table alone would just run one
# case fewer and stay green (contract perturbation P-4).
EXPECTED_RENAMES = {
    "japanese": "ink_season",
    "mexican": "vivid_material",
    "indian": "dye_earth",
    "british": "weathered_heritage",
    "egyptian": "desert_mineral",
    "impressionism": "open_air_light",
    "greek": "sea_stone",
    "renaissance": "fresco_study",
    "nordic": "cool_material",
    "chinese": "ink_porcelain",
}

DRAWN_WITH = "ink_season"
RETIRED_ID = "desert_mineral"
RENAMED_OLD_ID = "japanese"
# The pair agrees at many seeds -- 38% of 200 disagree, measured 2026-08-09 --
# so a test that wants the id to matter has to name a seed where it does.
SEED_WHERE_THE_IDS_DISAGREE = 1

# The colors one work recorded, frozen as a literal.
#
# Building this out of today's catalog would make the gates below compare a
# definition against itself: the very edit they perturb would move the
# "recorded" colors too, and a build that read the catalog instead of the row
# would stay green throughout. #111111 is the black `ink_season` actually
# carried when these works were saved; today's definition says #141210.
RECORDED_COLORS = {
    "white": "#fffff0",
    "black": "#111111",
    "gray": "#565656",
    "red": "#cc3311",
    "orange": "#ee9911",
    "yellow": "#887722",
    "green": "#007744",
    "blue": "#115588",
    "purple": "#aa88cc",
    "palette:Pine Soot": "#111111",
    "palette:Warm Paper": "#fffff0",
    "palette:Soft Soot": "#565656",
    "palette:Vermilion Accent": "#cc3311",
    "palette:Evergreen": "#007744",
    "palette:Indigo Shade": "#115588",
    "palette:Uguisu": "#887722",
    "palette:Golden Flower": "#ee9911",
    "palette:Pale Violet": "#aa88cc",
    "palette:Madder": "#992211",
}
RECORDED_BLACK = "#111111"

SCORE = {
    "version": "0.1.0",
    "canvas": {"aspect": "square", "ground": None},
    "background": "white",
    "instructions": [
        {
            "primitive": "circle",
            "center": [0.5, 0.5],
            "radius": 0.24,
            "weight": "pencil",
            "color": "black",
        },
        {
            "primitive": "circle",
            "center": [0.3, 0.3],
            "radius": 0.1,
            "filled": True,
            "weight": "brush_thick",
            "color": "red",
        },
    ],
}


@pytest.fixture
def actor():
    suffix = uuid.uuid4().hex[:8]
    group = db.add_user_group(f"work-colors-{suffix}")
    user = db.add_user(
        username=f"work-colors-{suffix}",
        email=f"work-colors-{suffix}@example.test",
        password="password-123",
        permission_groups=["users"],
        group_id=group["id"],
    )
    token = db.create_session(user["id"])
    yield user, {"Authorization": f"Bearer {token}"}
    db.delete_session(token)
    db.delete_user(user["id"], cascade=True)
    db.delete_user_group(group["id"])


def _work(user_id: str, *, catalog_id: str = DRAWN_WITH, snapshot: dict | None = None) -> dict:
    """A saved work, with or without the colors it was drawn in."""
    item = {
        "id": str(uuid.uuid4()),
        "user_id": user_id,
        "at": 1000,
        "input": "a work that remembers",
        "score": SCORE,
        "svg": "<svg xmlns='http://www.w3.org/2000/svg'/>",
        "catalog_id": catalog_id,
        "render_color_catalog_id": catalog_id,
        "render_color_catalog_name": "Ink Season",
        "render_color_catalog_sub": "recorded at the time",
    }
    if snapshot is not None:
        item["render_color_map"] = snapshot
    return db.add_item(item)


@contextmanager
def _repainted(catalog_id: str):
    """Edit today's definition of one catalog, the way a real change would.

    Both halves move: see the module docstring for why `map` alone is inert.
    """
    original = _catalogs.COLOR_CATALOGS
    replaced = []
    for catalog in original:
        if catalog["id"] == catalog_id:
            catalog = dict(catalog)
            catalog["map"] = {key: "#0b0b0b" for key in catalog["map"]}
            catalog["palette"] = [{**color, "code": "#0b0b0b"} for color in catalog["palette"]]
        replaced.append(catalog)
    _catalogs.COLOR_CATALOGS = tuple(replaced)
    try:
        yield
    finally:
        _catalogs.COLOR_CATALOGS = original


def _render_svg(headers: dict, **body) -> tuple[int, str, dict]:
    response = client.post("/api/render-svg", json={"score": SCORE, **body}, headers=headers)
    return response.status_code, response.text, dict(response.headers)


# Stage 1: the server reads the work's colors --------------------------------


def test_a_work_keeps_its_colors_when_todays_definition_is_repainted(actor):
    """The one gate this whole change exists for.

    Not "the ids match" -- that was already true and already silently wrong.
    The picture itself has to hold still while the catalog underneath it moves.
    """
    user, headers = actor
    work = _work(user["id"], snapshot=RECORDED_COLORS)

    _, before, _ = _render_svg(headers, work_id=work["id"], render_seed=7)
    with _repainted(DRAWN_WITH):
        _, after, _ = _render_svg(headers, work_id=work["id"], render_seed=7)

    assert before == after
    # Not vacuous, twice over: the drawing carries the colors the WORK recorded,
    # and that black is not the one today's catalog would have supplied.
    assert RECORDED_BLACK in before
    assert render_color_map_for_catalog(DRAWN_WITH)["black"] not in before


def test_without_a_work_reference_the_repaint_reaches_the_picture(actor):
    """The control for the test above.

    A build that simply stopped resolving colors would pass T-1 and fail here,
    which is the only thing separating "remembers" from "ignores".
    """
    _, headers = actor

    _, before, _ = _render_svg(headers, catalog_id=DRAWN_WITH, render_seed=7)
    with _repainted(DRAWN_WITH):
        _, after, _ = _render_svg(headers, catalog_id=DRAWN_WITH, render_seed=7)

    assert before != after
    assert "#0b0b0b" in after


def test_a_retired_catalog_still_draws_for_a_work_that_recorded_its_colors(actor):
    """`_resolved_catalog_id` is never reached on this path.

    118 works carry a catalog id no current build knows, and every redraw of
    them answered 422. The colors were on the row the whole time.
    """
    user, headers = actor
    work = _work(user["id"], catalog_id=RETIRED_ID, snapshot=RECORDED_COLORS)

    status, svg, response_headers = _render_svg(headers, work_id=work["id"], render_seed=7)

    assert status == 200
    assert response_headers[COLOR_SOURCE_HEADER.lower()] == "snapshot"
    assert RECORDED_BLACK in svg


def test_a_retired_catalog_is_still_refused_when_no_work_is_named(actor):
    """The counterpart. A new drawing may not ask for a catalog that is gone.

    Without this, "the retired id draws" would be satisfied by dropping the
    validation for everybody.
    """
    _, headers = actor

    status, _, _ = _render_svg(headers, catalog_id=RETIRED_ID, render_seed=7)

    assert status == 422


def test_a_renamed_catalog_still_draws_for_a_work_that_recorded_its_colors(actor):
    """57 works carry an id that was renamed out from under them."""
    user, headers = actor
    work = _work(user["id"], catalog_id=RENAMED_OLD_ID, snapshot=RECORDED_COLORS)

    status, svg, response_headers = _render_svg(headers, work_id=work["id"], render_seed=7)

    assert status == 200
    assert response_headers[COLOR_SOURCE_HEADER.lower()] == "snapshot"
    assert RECORDED_BLACK in svg


def test_a_work_with_no_snapshot_falls_to_todays_definition_and_says_so(actor):
    """464 works predate the recording. They still draw -- in today's colors.

    The response has to say which, because nothing in an SVG does.
    """
    user, headers = actor
    work = _work(user["id"], snapshot=None)

    status, _, response_headers = _render_svg(
        headers, work_id=work["id"], catalog_id=DRAWN_WITH, render_seed=7
    )

    assert status == 200
    assert response_headers[COLOR_SOURCE_HEADER.lower()] == "catalog"


def test_a_work_with_no_snapshot_and_a_retired_id_still_draws(actor):
    """Falling back must not become a second way to answer 422.

    Refusing here would leave exactly the oldest works -- no snapshot, and a
    catalog since retired -- unable to be redrawn at all.
    """
    user, headers = actor
    work = _work(user["id"], catalog_id=RETIRED_ID, snapshot=None)

    status, _, response_headers = _render_svg(
        headers, work_id=work["id"], catalog_id=RETIRED_ID, render_seed=7
    )

    assert status == 200
    assert response_headers[COLOR_SOURCE_HEADER.lower()] == "catalog"


def test_render_svg_names_the_catalog_it_actually_drew_with(actor):
    """The caller asked for nothing, so it cannot know without being told.

    The CLI writes this id into the render hash; naming the requested one there
    would describe a picture that was not drawn.
    """
    user, headers = actor
    work = _work(user["id"], catalog_id=RENAMED_OLD_ID, snapshot=RECORDED_COLORS)

    _, _, response_headers = _render_svg(headers, work_id=work["id"], render_seed=7)

    assert response_headers[COLOR_CATALOG_ID_HEADER.lower()] == RENAMED_OLD_ID


def test_render_score_names_the_source_of_its_colors(actor):
    """Same statement as the header, on the endpoint that answers JSON."""
    user, headers = actor
    work = _work(user["id"], snapshot=RECORDED_COLORS)

    with_work = client.post(
        "/api/render-score",
        json={"score": SCORE, "work_id": work["id"], "render_seed": 7},
        headers=headers,
    ).json()
    without = client.post(
        "/api/render-score",
        json={"score": SCORE, "catalog_id": DRAWN_WITH, "render_seed": 7},
        headers=headers,
    ).json()

    assert with_work["render_color_source"] == "snapshot"
    assert without["render_color_source"] == "catalog"
    assert with_work["render_color_map"] == RECORDED_COLORS


def test_render_score_draws_a_new_work_exactly_as_it_always_did(actor):
    """The path with no work reference is not to move by one byte.

    Every drawing that is not a redraw comes through here.
    """
    _, headers = actor

    body = client.post(
        "/api/render-score",
        json={"score": SCORE, "catalog_id": DRAWN_WITH, "render_seed": 7},
        headers=headers,
    ).json()

    assert body["render_color_catalog_id"] == DRAWN_WITH
    assert body["render_color_map"] == render_color_map_for_catalog(DRAWN_WITH)


def test_the_work_supplies_the_catalog_id_that_seeds_its_own_colors(actor):
    """The recorded id is carried through, not replaced by the requested one.

    It is not only a nameplate: the renderer hashes it into the seed that picks
    each chromatic work color, so a work redrawn under a different id comes back
    repainted out of the very same map.
    """
    user, headers = actor
    snapshot = RECORDED_COLORS
    work = _work(user["id"], catalog_id=RENAMED_OLD_ID, snapshot=snapshot)

    body = client.post(
        "/api/render-score",
        json={
            "score": SCORE,
            "work_id": work["id"],
            "catalog_id": DRAWN_WITH,
            "render_seed": SEED_WHERE_THE_IDS_DISAGREE,
        },
        headers=headers,
    ).json()

    assert body["render_color_catalog_id"] == RENAMED_OLD_ID


def test_the_editable_redraw_of_a_saved_work_uses_the_works_own_colors(actor):
    """/api/history/{id}/svg re-renders for the editable and compat profiles.

    It already held the work, and it was reading the catalog id instead: the
    same silent repaint, on a route that takes no new key at all.
    """
    user, headers = actor
    work = _work(user["id"], snapshot=RECORDED_COLORS)

    before = client.get(f"/api/history/{work['id']}/svg?profile=editable", headers=headers).text
    with _repainted(DRAWN_WITH):
        after = client.get(f"/api/history/{work['id']}/svg?profile=editable", headers=headers).text

    assert before == after
    assert RECORDED_BLACK in before


# Stage 1: authorization ------------------------------------------------------


def test_another_users_work_is_not_readable_through_the_colors(actor):
    """The new key must not become a way to read a stranger's row.

    `get_items` is scoped to the caller, so a work_id naming someone else's
    work answers exactly as one naming nothing does -- no existence oracle.
    """
    user, headers = actor
    stranger_suffix = uuid.uuid4().hex[:8]
    stranger_group = db.add_user_group(f"work-colors-other-{stranger_suffix}")
    stranger = db.add_user(
        username=f"work-colors-other-{stranger_suffix}",
        email=f"work-colors-other-{stranger_suffix}@example.test",
        password="password-123",
        permission_groups=["users"],
        group_id=stranger_group["id"],
    )
    try:
        theirs = _work(stranger["id"], snapshot={"black": "#abcabc", "palette:Theirs": "#abcabc"})

        status, body, _ = _render_svg(headers, work_id=theirs["id"], render_seed=7)
        unknown, _, _ = _render_svg(headers, work_id=str(uuid.uuid4()), render_seed=7)

        assert status == 404
        assert unknown == 404
        assert "#abcabc" not in body
    finally:
        db.delete_user(stranger["id"], cascade=True)
        db.delete_user_group(stranger_group["id"])


def test_a_trashed_work_is_not_readable_through_the_colors(actor):
    """Same rule as every other id-addressable route (ledger I-094)."""
    user, headers = actor
    work = _work(user["id"], snapshot=RECORDED_COLORS)
    db.trash_items(user["id"], [work["id"]])

    status, _, _ = _render_svg(headers, work_id=work["id"], render_seed=7)

    assert status == 404


def test_every_route_that_takes_a_work_reference_is_guarded():
    """Walk the live app, not the source text.

    The reference is only as private as the route carrying it; a guard removed
    from either enforcement point would leave the snapshot readable by anyone.
    """
    guarded = set()
    for context in iter_route_contexts(app.routes):
        if not isinstance(context.original_route, APIRoute):
            continue
        if context.path not in {"/api/render-svg", "/api/render-score"}:
            continue
        names = _dependency_names(context.dependant)
        assert "_current_user" in names, f"{context.path} is not behind _current_user"
        guarded.add(context.path)

    assert guarded == {"/api/render-svg", "/api/render-score"}


def _dependency_names(dependant, seen=None) -> set[str]:
    if seen is None:
        seen = set()
    names: set[str] = set()
    for dep in dependant.dependencies:
        if dep.call is not None:
            names.add(getattr(dep.call, "__name__", ""))
        if id(dep) not in seen:
            seen.add(id(dep))
            names |= _dependency_names(dep, seen)
    return names


# Stage 3: the rename migration ----------------------------------------------


def test_the_rename_table_names_every_pair_that_was_renamed():
    """Pinned literally so that losing an entry is a red test, not a shorter run."""
    assert RENAMED_COLOR_CATALOG_IDS == EXPECTED_RENAMES


def _legacy_history_db(path: Path, rows: list[tuple[str, str, str]]) -> None:
    """A `history` table as an older build left it, with rows already in place."""
    connection = sqlite3.connect(path)
    connection.execute(
        """
        CREATE TABLE history (
            id VARCHAR PRIMARY KEY, catalog_id VARCHAR,
            render_color_catalog_id VARCHAR, render_color_map TEXT
        )
        """
    )
    connection.executemany("INSERT INTO history VALUES (?, ?, ?, ?)", rows)
    connection.commit()
    connection.close()


def _migrated(tmp_path: Path, rows: list[tuple[str, str, str]]) -> list[tuple]:
    from inku_server.db import _migrate_renamed_catalog_nameplates

    db_path = tmp_path / f"nameplates-{uuid.uuid4().hex[:8]}.db"
    _legacy_history_db(db_path, rows)
    engine = create_engine(f"sqlite:///{db_path}")
    with engine.begin() as conn:
        _migrate_renamed_catalog_nameplates(conn)
    with engine.begin() as conn:
        rows_out = list(
            conn.execute(
                text("SELECT id, catalog_id, render_color_catalog_id, render_color_map FROM history")
            )
        )
    engine.dispose()
    return rows_out


SNAPSHOT_JSON = json.dumps({"black": "#111111", "palette:Sumi": "#111111"}, ensure_ascii=False)


@pytest.mark.parametrize(("old_id", "new_id"), sorted(EXPECTED_RENAMES.items()))
def test_the_migration_moves_each_old_nameplate(tmp_path, old_id, new_id):
    """One case per pair, so a table that lost a pair loses a green test."""
    rows = _migrated(tmp_path, [("w-1", old_id, old_id, SNAPSHOT_JSON)])

    assert rows[0][1] == new_id


def test_the_migration_does_not_touch_the_colors_a_work_was_drawn_in(tmp_path):
    """The nameplate is the only thing wrong; the colors were always right."""
    rows = _migrated(tmp_path, [("w-1", RENAMED_OLD_ID, RENAMED_OLD_ID, SNAPSHOT_JSON)])

    assert rows[0][3] == SNAPSHOT_JSON


def test_the_migration_does_not_touch_the_id_a_work_was_drawn_with(tmp_path):
    """Author's ruling 2026-08-09, and the reason is measured below.

    `render_color_catalog_id` is seed material for the chromatic assignment, so
    rewriting it repaints the work out of its own unchanged snapshot -- which is
    the symptom this whole change removes.
    """
    rows = _migrated(tmp_path, [("w-1", RENAMED_OLD_ID, RENAMED_OLD_ID, SNAPSHOT_JSON)])

    assert rows[0][2] == RENAMED_OLD_ID


def test_the_migration_is_idempotent(tmp_path):
    """It runs on every start. A second pass must find nothing left to move."""
    from inku_server.db import _migrate_renamed_catalog_nameplates

    db_path = tmp_path / "idempotent.db"
    _legacy_history_db(db_path, [("w-1", RENAMED_OLD_ID, RENAMED_OLD_ID, SNAPSHOT_JSON)])
    engine = create_engine(f"sqlite:///{db_path}")
    with engine.begin() as conn:
        _migrate_renamed_catalog_nameplates(conn)
        first = conn.execute(text("SELECT catalog_id FROM history")).scalar_one()
    with engine.begin() as conn:
        _migrate_renamed_catalog_nameplates(conn)
        second = conn.execute(text("SELECT catalog_id FROM history")).scalar_one()
    engine.dispose()

    assert first == second == EXPECTED_RENAMES[RENAMED_OLD_ID]


def test_starting_the_server_migrates_a_row_that_was_already_there(tmp_path):
    """The catalog transform is reachable from the pre-registry startup path.

    A registry-bearing current database must never replay legacy repairs. The
    fixture therefore removes only the registry after building a complete
    pre-registry shape, then starts the Server once through the legacy gate.
    """
    db_path = tmp_path / "startup.db"
    code = """
import json, os, sqlite3
from inku_server import db

db.init_db()
group = db.add_user_group("legacy-group")
user = db.add_user(
    username="legacy",
    email="legacy@example.test",
    password="password-123",
    permission_groups=["users"],
    group_id=group["id"],
)
db.add_item({
    "id": "legacy-1",
    "user_id": user["id"],
    "at": 1,
    "input": "a work saved before the rename",
    "score": {},
    "svg": "<svg/>",
    "catalog_id": "japanese",
    "render_color_catalog_id": "japanese",
    "render_color_map": {"black": "#111111"},
})

# Model the last build before the registry existed. The schema and persisted row
# remain intact; only the new coordinator metadata is absent.
with db.engine.begin() as connection:
    connection.exec_driver_sql("DROP TABLE schema_migrations")
db.init_db()

connection = sqlite3.connect(os.environ["INKU_DB_PATH"])
row = connection.execute(
    "SELECT catalog_id, render_color_catalog_id, render_color_map FROM history WHERE id='legacy-1'"
).fetchone()
connection.close()
print(json.dumps(row))
"""
    env = os.environ.copy()
    env["INKU_DB_URL"] = f"sqlite:///{db_path}"
    env["INKU_DB_PATH"] = str(db_path)
    env["INKU_TEST_USE_CONFIGURED_DB"] = "1"
    completed = subprocess.run(
        [sys.executable, "-c", code],
        cwd=Path(__file__).parents[1],
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    catalog_id, drawn_with, snapshot = json.loads(completed.stdout.strip().splitlines()[-1])

    assert catalog_id == "ink_season"
    assert drawn_with == "japanese"
    assert json.loads(snapshot) == {"black": "#111111"}


# Stage 5: the nameplate ------------------------------------------------------


def test_the_catalog_list_serves_the_rename_table(actor):
    """A client holding an old id has no other way to name the catalog."""
    _user, headers = actor
    body = client.get("/api/color-catalogs", headers=headers).json()

    assert body["renamed_catalog_ids"] == EXPECTED_RENAMES


def test_a_renamed_id_resolves_and_a_retired_one_does_not():
    """Retired is a fact about the nameplate, not about whether the work draws."""
    assert current_color_catalog_id(RENAMED_OLD_ID) == DRAWN_WITH
    assert current_color_catalog_id(RETIRED_ID) is None
    assert current_color_catalog_id(DRAWN_WITH) == DRAWN_WITH
