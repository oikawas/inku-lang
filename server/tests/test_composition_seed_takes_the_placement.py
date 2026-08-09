"""engine 23: the placement phase belongs to `composition_seed`.

Until engine 22 one `render_seed` decided both where an arrangement put its
marks and how each mark was drawn, so refining the touch always moved the
composition too -- on a 60-mark scatter, moving render_seed alone moved all 180
coordinates. SPEC :614 and :678 both state the opposite. These twelve tests
hold the split from both sides: placement follows the composition seed (T-1),
and nothing else does (T-2); the composition holds still when the performance
seed moves (T-3), which is the SPEC clause itself; an absent composition seed
falls back to the performance seed (T-4) while the seed 0 is a seed (T-5); the
value reaches the renderer from each of the five points on the way in (T-6 to
T-9); and the frozen corpus carries cases that can tell the difference (T-10 to
T-12).

A machine tool (`rotring`) draws the arrangement wherever the picture has to
hold still under one seed while moving under the other: its hand amplitude is
zero, so the only thing left in the SVG that either seed can move is the
placement. The tests that ask the opposite -- that the touch is still live --
use `pen`, which is where the hand is.
"""

from __future__ import annotations

import importlib.util
import inspect
import json
import pathlib
import uuid

import pytest
from fastapi.testclient import TestClient

from inku_server import db
from inku_server.api import app
from inku_server.api_core.rendering import (
    _render_metadata,
    _render_score_svg,
    _render_with_metadata,
    _resolved_catalog_id,
)
from inku_server.api_core.routers import render as render_routes
from inku_server.render_engines import current_render_engine
from inku_server.render_engines.base import RenderEngine
from inku_server.renderer import render
from inku_server.schema import Score

client = TestClient(app)

SERVER_ROOT = pathlib.Path(__file__).resolve().parents[1]
GENERATOR_PATH = SERVER_ROOT / "scripts" / "gen_render_reference.py"
REFERENCE_ROOT = SERVER_ROOT / "reference"

RENDER_SEED = 4242
OTHER_RENDER_SEED = 9999
COMPOSITION_SEED = 1111
OTHER_COMPOSITION_SEED = 2222

# The four cases engine 23 added, and the case each one copies. The pair is the
# claim: same score, same performance seed, one states a composition seed.
COMPOSITION_TWINS = {
    "G-composition-cluster-center": "G-cluster-center",
    "G-composition-grid-center": "G-grid-center",
    "G-composition-path-wave-edge": "G-path-wave-edge",
    "G-composition-scatter-edge": "G-scatter-edge",
}


def _arrangement_score(weight: str = "rotring") -> dict:
    return {
        "instructions": [
            {
                "primitive": "circle",
                "center": [0.5, 0.5],
                "radius": 0.03,
                "weight": weight,
                "arrangement": {
                    "count": 12,
                    "layout": "scatter",
                    "jitter": 0.12,
                    "margin": 0.1,
                },
            }
        ]
    }


def _plain_score(weight: str = "pen") -> dict:
    return {
        "instructions": [
            {
                "primitive": "circle",
                "center": [0.5, 0.5],
                "radius": 0.24,
                "weight": weight,
            }
        ]
    }


def _render(payload: dict, **kwargs) -> str:
    return render(Score.model_validate(payload), svg_profile="editable", **kwargs)


@pytest.fixture
def auth_headers():
    suffix = uuid.uuid4().hex[:8]
    group = db.add_user_group(f"composition-seed-{suffix}")
    user = db.add_user(
        username=f"composition-seed-{suffix}",
        email=f"composition-seed-{suffix}@example.test",
        password="password-123",
        role="user",
        group_id=group["id"],
    )
    token = db.create_session(user["id"])
    yield {"Authorization": f"Bearer {token}"}
    db.delete_session(token)
    # cascade: two of these tests save history rows, which is the point of them.
    db.delete_user(user["id"], cascade=True)
    db.delete_user_group(group["id"])


# T-1 --------------------------------------------------------------------
def test_the_composition_seed_decides_the_placement():
    """Same Score, same performance seed: the composition seed moves the marks."""
    score = _arrangement_score()
    a = _render(score, render_seed=RENDER_SEED, composition_seed=COMPOSITION_SEED)
    b = _render(score, render_seed=RENDER_SEED, composition_seed=OTHER_COMPOSITION_SEED)
    assert a != b

    # Not vacuous: the marks really are placed, and there are twelve of them.
    assert a.count("<circle") >= 12


# T-2 --------------------------------------------------------------------
def test_the_composition_seed_does_not_touch_the_hand():
    """A Score with no arrangement is byte-identical across composition seeds.

    Paired with T-1: without this, an implementation that re-salted the whole
    drawing from the composition seed would pass just as well.
    """
    score = _plain_score()
    a = _render(score, render_seed=RENDER_SEED, composition_seed=COMPOSITION_SEED)
    b = _render(score, render_seed=RENDER_SEED, composition_seed=OTHER_COMPOSITION_SEED)
    assert a == b

    # Not vacuous: this drawing does have a hand, and the performance seed moves
    # it. Without the control the equality above would hold for a blank canvas.
    moved = _render(score, render_seed=OTHER_RENDER_SEED, composition_seed=COMPOSITION_SEED)
    assert moved != a


# T-3 --------------------------------------------------------------------
def test_the_performance_seed_does_not_move_the_placement():
    """SPEC :614 / :678 -- a touch change keeps the composition of the Score.

    The tool is a machine, so the touch is not what is being held still here:
    with the hand at zero amplitude the only thing either seed can move in this
    drawing is where the twelve marks sit. T-1 is the same picture proving the
    placement is live.
    """
    score = _arrangement_score()
    a = _render(score, render_seed=RENDER_SEED, composition_seed=COMPOSITION_SEED)
    b = _render(score, render_seed=OTHER_RENDER_SEED, composition_seed=COMPOSITION_SEED)
    assert a == b


# T-4 --------------------------------------------------------------------
def test_no_composition_seed_falls_back_to_the_performance_seed():
    """Every drawing made before the split replays: NULL lands on render_seed."""
    score = _arrangement_score(weight="pen")
    absent = _render(score, render_seed=RENDER_SEED)
    stated = _render(score, render_seed=RENDER_SEED, composition_seed=RENDER_SEED)
    assert absent == stated

    # Not vacuous: some other seed does not produce this picture.
    assert _render(score, render_seed=RENDER_SEED, composition_seed=COMPOSITION_SEED) != absent


# T-5 --------------------------------------------------------------------
def test_zero_is_a_composition_seed_and_not_an_absent_one():
    """`is None`, never `or`. This is the only test that catches an `or`.

    db.py:1911 reads the same field the same way; a falsy test would send the
    seed 0 -- and only the seed 0 -- down the fallback path.
    """
    score = _arrangement_score()
    zero = _render(score, render_seed=RENDER_SEED, composition_seed=0)
    absent = _render(score, render_seed=RENDER_SEED)
    assert zero != absent


# T-6 --------------------------------------------------------------------
def test_all_four_stages_of_the_way_in_carry_the_composition_seed():
    """Each layer is entered at its own door, not through the renderer.

    The renderer is where T-1 already looks. What can break here is the
    carriage: a stage that accepts the argument and forgets to pass it on.
    """
    # 1. the engine protocol declares it
    protocol_parameters = inspect.signature(RenderEngine.render).parameters
    assert "composition_seed" in protocol_parameters
    assert protocol_parameters["composition_seed"].kind is inspect.Parameter.KEYWORD_ONLY

    score = Score.model_validate(_arrangement_score())
    payload = _arrangement_score()

    # 2. the default engine
    engine = current_render_engine()
    engine_a = engine.render(score, render_seed=RENDER_SEED, composition_seed=COMPOSITION_SEED)
    engine_b = engine.render(
        score, render_seed=RENDER_SEED, composition_seed=OTHER_COMPOSITION_SEED
    )
    assert engine_a.svg != engine_b.svg

    # 3. _render_with_metadata, which reads the seed out of the metadata dict
    metadata = _render_metadata(_resolved_catalog_id(None))
    meta_a, _ = _render_with_metadata(
        score, {**metadata, "render_seed": RENDER_SEED, "composition_seed": COMPOSITION_SEED}
    )
    meta_b, _ = _render_with_metadata(
        score,
        {**metadata, "render_seed": RENDER_SEED, "composition_seed": OTHER_COMPOSITION_SEED},
    )
    assert meta_a != meta_b

    # 4. _render_score_svg, the other entrance into the engine
    svg_a, _, _ = _render_score_svg(
        payload, catalog_id=None, svg_profile="editable", composition_seed=COMPOSITION_SEED
    )
    svg_b, _, _ = _render_score_svg(
        payload,
        catalog_id=None,
        svg_profile="editable",
        composition_seed=OTHER_COMPOSITION_SEED,
    )
    assert svg_a != svg_b


# T-7 --------------------------------------------------------------------
def test_the_four_render_metadata_callers_deliver_it_to_the_picture(monkeypatch, auth_headers):
    """All four routes that build a render_metadata dict reach the placement.

    Not "the key is in the dict": each route is called twice over HTTP with
    nothing different but the composition seed, and the two drawings must
    differ.
    """
    fake_score = Score.model_validate(_arrangement_score())
    monkeypatch.setattr(
        render_routes,
        "interpret_detail",
        lambda text, model=None, include_thinking=False: ("中心に黒い円を置く。", None),
    )
    monkeypatch.setattr(
        render_routes, "compose", lambda ddl, model=None, **kwargs: fake_score
    )

    routes = {
        "/api/compose": {"ddl": "twelve small circles", "render_seed": RENDER_SEED},
        "/api/paint": {"description": "一滴の墨", "render_seed": RENDER_SEED},
        "/api/render-score": {
            "score": _arrangement_score(),
            "render_seed": RENDER_SEED,
        },
        "/api/history": {
            "score": _arrangement_score(),
            "input": "twelve small circles",
            "at": 1770000000000,
            "render_seed": RENDER_SEED,
        },
    }
    for path, body in routes.items():
        drawings = []
        for seed in (COMPOSITION_SEED, OTHER_COMPOSITION_SEED):
            response = client.post(
                path, json={**body, "composition_seed": seed}, headers=auth_headers
            )
            assert response.status_code == 200, (path, response.status_code, response.text)
            drawings.append(response.json()["svg"])
        assert drawings[0] != drawings[1], path


# T-8 --------------------------------------------------------------------
def test_render_svg_endpoint_takes_a_composition_seed(auth_headers):
    drawings = []
    for seed in (COMPOSITION_SEED, OTHER_COMPOSITION_SEED):
        response = client.post(
            "/api/render-svg",
            json={
                "score": _arrangement_score(),
                "svg_profile": "editable",
                "render_seed": RENDER_SEED,
                "composition_seed": seed,
            },
            headers=auth_headers,
        )
        assert response.status_code == 200, response.text
        drawings.append(response.text)
    assert drawings[0] != drawings[1]


# T-9 --------------------------------------------------------------------
def test_history_svg_export_draws_with_the_stored_composition_seed(auth_headers):
    """The editable export re-renders, so it has to read the row's own seed.

    This route still does not pass `render_seed` (measured 2026-08-08, left as
    it was by contract), so the export replays the composition but not the
    touch. What is held here is the half that now works.
    """
    exported = []
    for seed in (COMPOSITION_SEED, OTHER_COMPOSITION_SEED):
        saved = client.post(
            "/api/history",
            json={
                "score": _arrangement_score(),
                "input": "twelve small circles",
                "at": 1770000000000 + seed,
                "render_seed": RENDER_SEED,
                "composition_seed": seed,
            },
            headers=auth_headers,
        )
        assert saved.status_code == 200, saved.text
        item_id = saved.json()["id"]
        assert saved.json()["composition_seed"] == seed
        response = client.get(
            f"/api/history/{item_id}/svg", params={"profile": "editable"}, headers=auth_headers
        )
        assert response.status_code == 200, response.text
        exported.append(response.text)
    assert exported[0] != exported[1]


# T-10 -------------------------------------------------------------------
def test_the_engine_names_itself_23():
    """The split shipped in 23, and no engine after it took the name back.

    A later engine bumps the number, so what this holds is the floor: 23 is
    where `composition_seed` reached the renderer, and the corpus directory
    that carries the twins below is 23's.
    """
    assert int(current_render_engine().version) >= 23
    assert (REFERENCE_ROOT / "render-engine-23" / "manifest.json").is_file()


# T-11 -------------------------------------------------------------------
def test_no_case_frozen_before_this_change_moved():
    """The 531 cases of engine 22 are byte-identical here, because none of them
    states a composition seed and NULL lands on the performance seed.

    A regenerated record, not a property: on its own it is evidence that the
    fallback is right, not that the split happened. T-12 is the other half.
    """
    # This version, not the current one: the claim is about what engine 23 did
    # to engine 22's corpus, and a later engine that moves a case moves it for
    # its own reasons.
    current = json.loads(
        (REFERENCE_ROOT / "render-engine-23" / "manifest.json").read_text(encoding="utf-8")
    )
    previous = json.loads(
        (REFERENCE_ROOT / "render-engine-22" / "manifest.json").read_text(encoding="utf-8")
    )
    assert len(previous["cases"]) == 531
    moved = [
        case_id
        for case_id, case in previous["cases"].items()
        if current["cases"][case_id]["digest"] != case["digest"]
    ]
    assert moved == []
    # Everything this version lists as changed is a case that did not exist
    # before it, so the listing still means "what this version added".
    assert set(current["changed_from_previous"]) == set(COMPOSITION_TWINS)
    assert not (set(current["changed_from_previous"]) & set(previous["cases"]))


# T-12 -------------------------------------------------------------------
def test_the_added_cases_can_tell_the_two_seeds_apart(monkeypatch):
    """Each added case states a composition seed, and the value is load-bearing.

    Without this the corpus would record that engine 23 changed no picture,
    which is true and says nothing about whether the split happened.

    Engine 25's per-member size used to be taken back out here, because the
    yardstick was engine 23's frozen bytes and the size moved them for a reason
    that has nothing to do with which seed placed them. engine 28 moved the
    material layer and the wobble as well, so reaching engine 23 that way would
    mean rebuilding two more engines inside a fixture. The bake's own call is
    checked against the current corpus instead, which is what "survives the trip
    the generator makes" was ever about; the split itself is measured below by
    dropping the seed and watching the picture move, and that half never needed
    a frozen body at all.
    """
    spec = importlib.util.spec_from_file_location("gen_render_reference", GENERATOR_PATH)
    assert spec is not None and spec.loader is not None
    generator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(generator)
    inputs = generator.build_inputs()
    manifest = json.loads(
        (REFERENCE_ROOT / "render-engine-28" / "manifest.json").read_text(encoding="utf-8")
    )

    for case_id, twin_id in COMPOSITION_TWINS.items():
        case = inputs[case_id]
        twin = inputs[twin_id]
        # Through the bake's own call: the stated seed has to survive the trip
        # the generator itself makes, not one this test writes out by hand.
        assert (
            generator._normalized_digest(generator.render_case(case))
            == manifest["cases"][case_id]["digest"]
        ), case_id
        assert case["composition_seed"] is not None, case_id
        assert case["composition_seed"] != case["render_seed"], case_id
        # The pair differs by the seed and nothing else.
        assert "composition_seed" not in twin, twin_id
        assert case["score"] == twin["score"], case_id
        assert case["render_seed"] == twin["render_seed"], case_id
        assert manifest["cases"][case_id]["digest"] != manifest["cases"][twin_id]["digest"], case_id

        # And the value is what makes the difference: drop it and the case
        # collapses onto its twin.
        without = generator.render(
            Score.model_validate(case["score"]),
            color_map=case["color_map"],
            catalog_id=case["catalog_id"],
            render_seed=case["render_seed"],
            svg_profile=case["svg_profile"],
            wild=case["wild"],
        )
        assert generator._normalized_digest(without) == manifest["cases"][twin_id]["digest"], case_id
