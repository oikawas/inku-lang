"""T-1..T-12 of 契約 limits-are-settings.

The first half moved the nine limits into one module. This half replaces where
their values come from: a stored setting, resolved once per request, written
into what the model is told, and recorded on the work.

What each stage can get wrong, and what catches it here:

  setting     a value is stored but never reaches coerce -- `limits=` defaults to
              DEFAULT_LIMITS, so a route that forgets runs at the defaults and
              says nothing (T-1, and the five-site count in T-7);
  prompt      the model is told 240 while coerce honours 480. Told and applied
              have to move together, and a constant, an alias or an unwired
              argument all pass a one-directional check (T-2, T-4);
  validation  a static `le=` is a second copy of the ceiling that no setting can
              reach, and it lets a clamp test pass by accident (T-8);
  record      a per-install setting with nothing on the row to say which one is
              exactly what §0.1 forbids (T-6);
  spill       the frozen corpora quietly becoming per-install (T-3, T-12).

The frozen corpora do NOT gate any of this. They run at the defaults, so the
intended change moves 0 cases -- T-12 is a regression guard and is written as
one, not as evidence that the settings work.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import pathlib
import re
import uuid

import pytest
from fastapi.testclient import TestClient

from inku_server import composer, db, interpreter
from inku_server.api import app
from inku_server.api_core.rendering import _effective_limits
from inku_server.api_core.routers import render as render_routes
from inku_server.coerce import coerce_score
from inku_server.limits import (
    DEFAULT_LIMITS,
    LIMIT_FIELD_NAMES,
    LIMIT_GROUPS,
    Limits,
    limits_as_dict,
    normalize_limits,
)
from inku_server.schema import Score

client = TestClient(app)

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
SERVER_ROOT = pathlib.Path(__file__).resolve().parents[1]
WEB_ROOT = REPO_ROOT / "web"
ANDROID_ROOT = REPO_ROOT / "android"

# A single clause stating a number that sits between the default threshold (240)
# and the raised one (480). At the defaults it must be represented; with the
# threshold at 480 it must come through whole.
LITERAL_CLAUSE = "黒い点を三百個散らす。"
LITERAL_SCORE = {
    "instructions": [
        {
            "primitive": "ellipse",
            "at": {"region": [0.1, 0.1, 0.9, 0.9]},
            "arrangement": {"count": 300, "layout": "scatter"},
        }
    ]
}
RAISED = {
    "literal_count_threshold": 480,
    "max_expanded_primitives": 900,
    "max_expanded_per_instruction": 480,
}


@pytest.fixture
def stored_limits():
    """Store a setting and put it back afterwards.

    app_settings is process-wide, so a leaked value would silently retune every
    test that runs after this one.
    """
    written: list[dict] = []

    def store(values: dict) -> dict:
        if not written:
            written.append(db.get_render_limit_settings())
        return db.update_render_limit_settings(values)

    yield store
    if written:
        db.update_render_limit_settings(written[0])


def _auth_headers(user: dict) -> tuple[dict[str, str], str]:
    token = db.create_session(user["id"])
    return {"Authorization": f"Bearer {token}"}, token


@pytest.fixture
def admin_context():
    suffix = uuid.uuid4().hex[:8]
    group = db.add_user_group(f"limits-{suffix}")
    user = db.add_user(
        username=f"limits-{suffix}",
        email=f"limits-{suffix}@example.test",
        password="password-123",
        permission_groups=["admins"],
        group_id=group["id"],
    )
    headers, token = _auth_headers(user)
    created: list[str] = []
    yield headers, user, group, created
    # The user cannot be deleted while it owns history, and T-6 has to save a
    # work for the record to be readable at all.
    if created:
        db.delete_items(user["id"], created)
    db.delete_session(token)
    db.delete_user(user["id"])
    db.delete_user_group(group["id"])


def _counts(score: Score) -> list[int | None]:
    return [ins.arrangement.count if ins.arrangement else None for ins in score.instructions]


# --------------------------------------------------------------------------
# T-1  a stored setting actually reaches coerce
# --------------------------------------------------------------------------


def test_t1_stored_setting_reaches_coerce(stored_limits):
    """Through coerce_score, the entry point -- not through the helpers it calls.

    Calling `_budgeted_count` directly would skip the gate that decides whether
    the branch runs at all, and has measured a fire rate that does not exist
    (gate_bypass_measurement_error).
    """
    at_default = coerce_score(
        Score.model_validate(LITERAL_SCORE), ddl=LITERAL_CLAUSE, limits=_effective_limits()
    )
    assert _counts(at_default) == [120], "the default threshold must still represent 300"

    stored_limits(RAISED)
    raised = coerce_score(
        Score.model_validate(LITERAL_SCORE), ddl=LITERAL_CLAUSE, limits=_effective_limits()
    )
    assert _counts(raised) == [300], "300 must come through literal once the threshold is 480"


# --------------------------------------------------------------------------
# T-2  the prompt and coerce read the SAME setting
# --------------------------------------------------------------------------


def test_t2_prompt_and_coerce_read_the_same_setting(stored_limits):
    stored_limits(RAISED)
    limits = _effective_limits()

    prompt = composer.build_system_prompt("ja", limits)
    assert "480 未満なら literal" in prompt
    assert "240 未満なら literal" not in prompt

    coerced = coerce_score(
        Score.model_validate(LITERAL_SCORE), ddl=LITERAL_CLAUSE, limits=limits
    )
    assert _counts(coerced) == [300]


def test_t2_reverse_each_stated_limit_is_separately_bound():
    """The reverse leg: a constant, an alias or an unwired argument must fail.

    The contract wrote this as "same threshold, different budget -> the prompt
    is unchanged". That is no longer true and must not be asserted: the budget
    (max_expanded_primitives) IS stated in the prompt -- the 400 in the
    literal-sum rule, which the contract's §2.2 table had missed and the author
    ruled in on 2026-08-05. So the invariance pair is restated per field:

      forward   changing ONE stated limit changes the text;
      reverse   changing a limit the prompt does NOT state leaves all four
                prompts byte-identical.

    Without the reverse leg a builder that hashed the whole Limits, or ignored
    it, would pass (invariance_gate_misses_the_binding).
    """
    # Which prompts each limit is stated in, EXACTLY. "at least one moved" is
    # not enough: reverting only the Japanese copy of a rule leaves the English
    # one moving, the set stays non-empty, and the check passes while the two
    # languages now teach the model different rules -- the failure §2.2 names
    # (half_perturbation_masked_by_resnap).
    stated = {
        "literal_count_threshold": (480, {"s2ja", "s2en"}),
        "represented_count_min": (40, {"s2ja", "s2en"}),
        "represented_count_max": (90, {"s2ja", "s2en"}),
        "ddl_count_max": (1500, {"s2ja", "s2en", "s1ja", "s1en"}),
        "ddl_count_max_grid": (3000, {"s2ja", "s2en", "s1ja", "s1en"}),
        "max_expanded_primitives": (900, {"s2ja", "s2en"}),
    }
    baseline = {
        "s2ja": composer.build_system_prompt("ja", DEFAULT_LIMITS),
        "s2en": composer.build_system_prompt("en", DEFAULT_LIMITS),
        "s1ja": interpreter.build_stage1_prefix("ja", DEFAULT_LIMITS),
        "s1en": interpreter.build_stage1_prefix("en", DEFAULT_LIMITS),
    }

    for field, (value, expected) in stated.items():
        altered = Limits(**{**limits_as_dict(DEFAULT_LIMITS), field: value})
        moved = {
            key
            for key, text in baseline.items()
            if text
            != (
                composer.build_system_prompt(key[-2:], altered)
                if key.startswith("s2")
                else interpreter.build_stage1_prefix(key[-2:], altered)
            )
        }
        assert moved == expected, f"{field}: expected {sorted(expected)} to move, got {sorted(moved)}"

    # max_instructions is the negative control: it governs coerce and is named
    # in no prompt, so every prompt must come back byte-identical.
    unstated = Limits(**{**limits_as_dict(DEFAULT_LIMITS), "max_instructions": 7})
    assert composer.build_system_prompt("ja", unstated) == baseline["s2ja"]
    assert composer.build_system_prompt("en", unstated) == baseline["s2en"]
    assert interpreter.build_stage1_prefix("ja", unstated) == baseline["s1ja"]
    assert interpreter.build_stage1_prefix("en", unstated) == baseline["s1en"]


# --------------------------------------------------------------------------
# T-3  the reference generators run on the DEFAULTS, not on app_settings
# --------------------------------------------------------------------------


def _ddl_generator():
    path = SERVER_ROOT / "scripts" / "gen_ddl_reference.py"
    spec = importlib.util.spec_from_file_location("gen_ddl_reference_for_limits", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_t3_reference_generator_ignores_the_stored_setting(stored_limits):
    """Without this the frozen corpora silently become per-install."""
    generator = _ddl_generator()
    before, _ = generator._render_cases()

    stored_limits(RAISED)
    assert db.get_render_limit_settings()["literal_count_threshold"] == 480

    after, _ = generator._render_cases()
    moved = [case for case in before if before[case]["digest"] != after[case]["digest"]]
    assert moved == [], f"the stored setting leaked into the frozen corpus: {moved}"


# --------------------------------------------------------------------------
# T-4  the injection is real, not cosmetic
# --------------------------------------------------------------------------


def _digest16(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


@pytest.fixture
def empty_plugin_vocabulary(monkeypatch):
    """The same condition test_prompt_digests.py records its values under.

    Loaded plugins add vocabulary to the Stage 1 prefix, so a digest measured
    without this fixture is a different number for a reason that has nothing to
    do with the limits.
    """
    from inku_server.plugins import DOCUMENT_PLUGIN_MANAGER

    monkeypatch.setattr(DOCUMENT_PLUGIN_MANAGER, "prompt_vocabulary", lambda lang: ())


@pytest.mark.usefixtures("empty_plugin_vocabulary")
def test_t4_digests_hold_at_the_defaults_and_move_under_a_setting():
    """A digest test that passes under both configurations measures nothing.

    The recorded values come from test_prompt_digests.py, which runs at the
    defaults; the second half of each pair is what proves the numbers in the
    prompt are really the setting's and not a copy of it.
    """
    _, base_ja = interpreter._build_system_prompt_parts(
        "入力文は不変部へ入らない。", lang="ja", limits=DEFAULT_LIMITS
    )
    assert _digest16(base_ja) == "0c03e4dfb10715eb"
    assert len(base_ja.encode("utf-8")) == 19_584

    altered = Limits(**{**limits_as_dict(DEFAULT_LIMITS), "ddl_count_max": 1500})
    _, base_alt = interpreter._build_system_prompt_parts(
        "入力文は不変部へ入らない。", lang="ja", limits=altered
    )
    assert _digest16(base_alt) != "0c03e4dfb10715eb"
    assert "1〜1500 の振れ幅" in base_alt

    # Stage 2 the same way: identical at the defaults, moved by the setting.
    assert composer._stage2_prompt_digest(composer.SYSTEM_PROMPT) == "cfa0e44d64743a14"
    raised = Limits(**{**limits_as_dict(DEFAULT_LIMITS), **RAISED})
    assert (
        composer._stage2_prompt_digest(composer.build_system_prompt("ja", raised))
        != "cfa0e44d64743a14"
    )


# --------------------------------------------------------------------------
# T-5  normalization keeps the set self-consistent
# --------------------------------------------------------------------------


def test_t5_normalization_rounds_the_set_into_agreement(stored_limits):
    """Asserted on the STORED result, not on the validator's return alone.

    A normalizer that returns a corrected dict but writes the raw one would pass
    a check that only looked at the return value.
    """
    stored_limits(
        {
            "literal_count_threshold": 100,
            "represented_count_max": 900,
            "represented_count_min": 800,
            "max_expanded_primitives": 300,
            "max_expanded_per_instruction": 999,
        }
    )
    stored = db.get_render_limit_settings()
    assert stored["represented_count_max"] == 100, "the band cannot start above the threshold"
    assert stored["represented_count_min"] == 100, "nor can its low end"
    assert stored["max_expanded_per_instruction"] == 300, "one instruction cannot outrun the work"

    # And the read-back path agrees with the write path.
    assert limits_as_dict(_effective_limits()) == stored

    # Garbage and zero round rather than raise, the way the panel expects.
    assert normalize_limits({"max_instructions": 0})["max_instructions"] == 1
    assert normalize_limits({"max_instructions": "nonsense"})["max_instructions"] == (
        DEFAULT_LIMITS.max_instructions
    )


# --------------------------------------------------------------------------
# T-6  THE EFFECTIVE LIMITS ARE RECORDED ON THE WORK
# --------------------------------------------------------------------------


def test_t6_the_effective_limits_are_recorded_on_the_work(
    monkeypatch, admin_context, stored_limits
):
    """Without the record, a per-install setting is what §0.1 forbids."""
    headers, actor, _, created = admin_context
    stored_limits(RAISED)

    monkeypatch.setattr(
        render_routes,
        "interpret_detail",
        lambda text, model=None, include_thinking=False: ("中心に黒い円を置く。", None),
    )
    monkeypatch.setattr(
        render_routes,
        "compose",
        lambda ddl, model=None: Score.model_validate(
            {"instructions": [{"primitive": "circle", "center": [0.5, 0.5], "radius": 0.1}]}
        ),
    )

    r = client.post("/api/paint", json={"description": "一滴の墨"}, headers=headers)
    assert r.status_code == 200
    data = r.json()

    expected = limits_as_dict(_effective_limits())
    assert expected["literal_count_threshold"] == 480
    assert data["render_limits"] == expected, "the response must carry what was used"

    # /api/paint renders but does not persist; the client saves through
    # POST /api/history, which is coerce site 2. The row is written there, so
    # that is where the record has to show up.
    saved = client.post(
        "/api/history",
        json={
            "input": data["description"],
            "ddl": data["ddl"],
            "score": data["score"],
            "at": 1_785_000_000_000,
        },
        headers=headers,
    )
    assert saved.status_code == 200
    item = saved.json()
    created.append(item["id"])
    assert item["render_limits"] == expected, "the saved item must carry the used set"

    rows = db.get_items(actor["id"], [item["id"]])
    assert len(rows) == 1
    recorded = rows[0].get("render_limits")
    assert recorded == expected, "the stored row must carry the used set"
    assert recorded != limits_as_dict(DEFAULT_LIMITS), "not the defaults"
    assert set(recorded) == set(LIMIT_FIELD_NAMES), "and not a partial record"


def test_t6_a_row_without_the_column_is_absent_not_default():
    """Absent is a third state. Backfilling old rows would claim a configuration
    nobody recorded, which is the same mistake sketch_state was added to avoid.
    """
    migrations = (SERVER_ROOT / "src" / "inku_server" / "db.py").read_text(encoding="utf-8")
    statement = 'ALTER TABLE history ADD COLUMN render_limits TEXT'
    assert statement in migrations
    assert "render_limits TEXT DEFAULT" not in migrations, "a DEFAULT would erase the distinction"


# --------------------------------------------------------------------------
# T-7  the response carries them, and every sender is counted
# --------------------------------------------------------------------------


def test_t7_every_coerce_site_passes_the_limits():
    """Five call sites, counted -- not assumed.

    `coerce_score(limits=...)` defaults to DEFAULT_LIMITS, so a route that
    forgets runs at the defaults and returns 200 (silent_sender_is_never_tested).
    The count is the assertion.
    """
    sources = {
        path: path.read_text(encoding="utf-8")
        for path in [
            SERVER_ROOT / "src" / "inku_server" / "api_core" / "rendering.py",
            SERVER_ROOT / "src" / "inku_server" / "api_core" / "routers" / "history.py",
            SERVER_ROOT / "src" / "inku_server" / "api_core" / "routers" / "render.py",
        ]
    }
    calls = sum(len(re.findall(r"\bcoerce_score\(", text)) for text in sources.values())
    assert calls == 5, f"the call-site count moved: {calls}"

    # Each one is inside a `with using_limits(...)` and hands `limits=` along.
    passing = sum(len(re.findall(r"limits=limits", text)) for text in sources.values())
    assert passing >= calls, f"only {passing} of {calls} sites pass the limits"
    for path, text in sources.items():
        for match in re.finditer(r"\bcoerce_score\(", text):
            window = text[match.start() : match.start() + 600]
            assert "limits=limits" in window, f"{path.name} has a coerce_score without limits="


def test_t7_all_four_areas_are_counted_for_the_new_field():
    """web / server / cli / android, the four-area count for an API field.

    A receiver that drops unknown fields keeps a missed sender at 200, so the
    areas are counted rather than trusted (api_field_rename_count_all_senders).
    """
    areas = {
        "server": SERVER_ROOT / "src",
        "cli": REPO_ROOT / "cli" / "src",
        "web": WEB_ROOT / "src",
        "android": ANDROID_ROOT / "app",
    }
    carrying = {}
    for name, root in areas.items():
        if not root.is_dir():
            carrying[name] = None
            continue
        hits = 0
        for path in root.rglob("*"):
            if path.is_file() and path.suffix in {".py", ".ts", ".svelte", ".kt"}:
                if "render_limits" in path.read_text(encoding="utf-8", errors="ignore"):
                    hits += 1
        carrying[name] = hits

    # server produces it, cli and web read it back. android is a local-only
    # pipeline with no settings of its own, so it deliberately carries none --
    # stated here so a future reader sees a decision, not an omission.
    #
    # An area that is not in this checkout is not counted: the development server
    # carries only what its two services need (ledger I-059). `server` is the one
    # area that must be here, since these tests live inside it.
    assert carrying["server"] and carrying["server"] > 0
    for area in ("cli", "web"):
        if carrying[area] is not None:
            assert carrying[area] > 0, f"{area} stopped carrying the field"
    if carrying["android"] is not None:
        assert carrying["android"] == 0, "android has no settings route; see §2.5"


# --------------------------------------------------------------------------
# T-8  the schema bound follows the setting
# --------------------------------------------------------------------------


def test_t8_the_schema_bound_follows_the_setting(stored_limits):
    """The old static bound must be GONE.

    A validator still carrying `le=2000` clamps 1500 to 1500 and passes a test
    that only checked the new ceiling did something -- so the absence of the
    static bound is asserted first.
    """
    from inku_server.limits import using_limits

    properties = Score.model_json_schema()["$defs"]["Arrangement"]["properties"]
    assert "maximum" not in properties["count"], "a static le= is a ceiling no setting can reach"

    stored_limits({"schema_count_max": 900})
    limits = _effective_limits()
    assert limits.schema_count_max == 900

    with using_limits(limits):
        score = Score.model_validate(
            {
                "instructions": [
                    {
                        "primitive": "ellipse",
                        "at": {"region": [0.1, 0.1, 0.9, 0.9]},
                        "arrangement": {"count": 1500, "layout": "scatter"},
                    }
                ]
            }
        )
    assert _counts(score) == [900]

    # And at the defaults the same declaration is left alone, so the clamp is
    # the setting's doing and not a blanket reduction.
    default_score = Score.model_validate(
        {
            "instructions": [
                {
                    "primitive": "ellipse",
                    "at": {"region": [0.1, 0.1, 0.9, 0.9]},
                    "arrangement": {"count": 1500, "layout": "scatter"},
                }
            ]
        }
    )
    assert _counts(default_score) == [1500]


# --------------------------------------------------------------------------
# T-9  the Limits tab
# --------------------------------------------------------------------------


@pytest.mark.skipif(not WEB_ROOT.is_dir(), reason="web/ is not present in this checkout")
def test_t9_the_limits_tab_carries_all_nine_rows_and_a_reset():
    panel = (WEB_ROOT / "src" / "lib" / "components" / "SettingsModal.svelte").read_text(
        encoding="utf-8"
    )
    assert "settingsTab === 'limits'" in panel
    assert "'limits'" in panel.split("type SettingsTab =")[1].split(";")[0]

    labels = (WEB_ROOT / "src" / "lib" / "i18n" / "ja.ts").read_text(encoding="utf-8")
    block = labels.split("settingsRenderLimitLabels: {")[1].split("}")[0]
    for field in LIMIT_FIELD_NAMES:
        assert f"{field}:" in block, f"the panel has no row for {field}"

    # Three families, named by the server so the panel cannot invent a fourth.
    assert {name for name, _ in LIMIT_GROUPS} == {"drawn", "stated", "ceiling"}
    assert sorted(f for _, fields in LIMIT_GROUPS for f in fields) == sorted(LIMIT_FIELD_NAMES)
    groups_block = labels.split("settingsRenderLimitGroups: {")[1].split("}")[0]
    for name, _ in LIMIT_GROUPS:
        assert f"{name}:" in groups_block

    # Deleting the reset control must turn this red: an adjustment device you
    # cannot put back is not usable.
    assert "onUpdateRenderLimits(null)" in panel
    assert "settingsRenderLimitsReset" in panel


# --------------------------------------------------------------------------
# T-10  i18n and the glossary
# --------------------------------------------------------------------------


@pytest.mark.skipif(not WEB_ROOT.is_dir(), reason="web/ is not present in this checkout")
def test_t10_i18n_keys_and_the_glossary_row():
    i18n = WEB_ROOT / "src" / "lib" / "i18n"
    for name in ("types.ts", "ja.ts", "en.ts"):
        assert "settingsTabLimits" in (i18n / name).read_text(encoding="utf-8"), name

    # lint:i18n reads web display strings only, never documents, so the glossary
    # row is asserted separately or nothing checks it at all.
    glossary = (i18n / "GLOSSARY.md").read_text(encoding="utf-8")
    row = [line for line in glossary.splitlines() if line.startswith("| 制限値 ")]
    assert row, "GLOSSARY.md carries no 制限値 row"
    assert "**Limits**" in row[0]


# --------------------------------------------------------------------------
# T-11  Android
# --------------------------------------------------------------------------


@pytest.mark.skipif(
    not ANDROID_ROOT.is_dir(), reason="android/ is not present (it is excluded from pentala)"
)
def test_t11_android_no_longer_carries_a_bare_240():
    pipeline = (
        ANDROID_ROOT
        / "app"
        / "src"
        / "main"
        / "java"
        / "app"
        / "inku"
        / "mobile"
        / "pipeline"
        / "LocalFallbackPipeline.kt"
    )
    source = pipeline.read_text(encoding="utf-8")
    bare = [
        line.strip()
        for line in source.splitlines()
        if re.search(r"\b240\b", line) and "const val" not in line
    ]
    assert bare == [], f"a bare 240 is left in the pipeline: {bare}"
    assert "private const val LITERAL_COUNT_THRESHOLD = 240" in source
    assert "originalCount >= LITERAL_COUNT_THRESHOLD" in source


# --------------------------------------------------------------------------
# T-12  frozen corpora unchanged at the defaults (a REGRESSION GUARD)
# --------------------------------------------------------------------------


def test_t12_frozen_corpus_is_unchanged_at_the_defaults():
    """This is not evidence that the settings work. It is the guard that says
    the code path for the default configuration did not move. The evidence is
    T-1..T-8.
    """
    from inku_server.layer_versions import DDL_ENGINE_VERSION

    manifest_path = SERVER_ROOT / "reference" / f"ddl-engine-{DDL_ENGINE_VERSION}" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    cases, _ = _ddl_generator()._render_cases()

    moved = [
        case
        for case, entry in manifest["cases"].items()
        if case in cases and cases[case]["digest"] != entry["digest"]
    ]
    assert moved == [], f"{len(moved)} frozen cases moved at the defaults: {moved[:5]}"
