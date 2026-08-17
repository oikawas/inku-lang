"""What a member may do is decided by the permission groups they hold.

The `user_accounts.role` flag is gone from every decision.  The column itself
stays, written as a machine-derived mirror, so a database taken after this
change still opens on a build from before it -- and the tests below measure
that nothing reads it, by behaviour rather than by reading the source.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import pathlib
import uuid

import pytest
from fastapi.testclient import TestClient

from inku_server import db
from inku_server.api import app


client = TestClient(app)


# One route from each guard's set, used as the reachability probe.  Both are
# reads, so a 200 says the guard let the caller through and nothing else.
ADMIN_ROUTE = "/api/settings/status"
ADMIN_ROUTE_2 = "/api/settings/models"
MANAGER_ROUTE = "/api/users"


def _member(prefix: str, groups: list[str], group_id: str | None = None) -> tuple[dict, dict[str, str]]:
    suffix = uuid.uuid4().hex[:8]
    user = db.add_user(
        f"{prefix}-{suffix}",
        f"{prefix}-{suffix}@example.test",
        "password-123",
        groups,
        group_id,
    )
    token = db.create_session(user["id"])
    return user, {"Authorization": f"Bearer {token}"}


def _memberships(user_id: str) -> list[str]:
    with db.SessionLocal() as session:
        return db._permission_groups_of(session, user_id)


def _membership_row_count(user_id: str) -> int:
    with db.SessionLocal() as session:
        return (
            session.query(db.UserPermissionGroupRow)
            .filter(db.UserPermissionGroupRow.user_id == user_id)
            .count()
        )


def _make_legacy_account(role: str) -> str:
    """An account as a pre-migration database holds it: a role, no memberships."""
    user, _headers = _member("legacy", ["users"])
    with db.SessionLocal() as session:
        session.query(db.UserPermissionGroupRow).filter(
            db.UserPermissionGroupRow.user_id == user["id"]
        ).delete(synchronize_session=False)
        session.get(db.UserAccountRow, user["id"]).role = role
        session.commit()
    assert _memberships(user["id"]) == []
    return user["id"]


# --- T-1: the migration maps one legacy role to exactly one group ------------


@pytest.mark.parametrize(
    ("legacy_role", "expected"),
    [("admin", ["admins"]), ("group_lead", ["leaders"]), ("user", ["users"])],
)
def test_t1_the_migration_maps_each_legacy_role_to_one_group(legacy_role: str, expected: list[str]) -> None:
    """One-to-one on purpose.

    Reading `admin` as "an admin is also a leader" would be a helpful guess that
    makes the original role unrecoverable: nothing afterwards could tell an
    account the migration widened from one an administrator widened on purpose.
    """
    user_id = _make_legacy_account(legacy_role)
    db._migrate_roles_to_permission_groups()
    assert _memberships(user_id) == expected


# --- T-2: running it twice changes nothing ----------------------------------


def test_t2_the_migration_is_idempotent() -> None:
    user_id = _make_legacy_account("group_lead")
    db._migrate_roles_to_permission_groups()
    first = _memberships(user_id)
    db._migrate_roles_to_permission_groups()

    assert _memberships(user_id) == first == ["leaders"]
    # Not just the names: a second insert would leave two rows naming the same
    # group, which the set-valued reader above would hide.
    assert _membership_row_count(user_id) == 1

    # The half the unique constraint cannot catch.  A migration that re-derived
    # every account from the role mirror on each run would delete-and-rewrite
    # rather than duplicate, so the database would raise nothing -- and an
    # account deliberately given both groups would silently lose one, because
    # the mirror can only name the stronger.
    widened, _headers = _member("widened", ["admins", "leaders"])
    db._migrate_roles_to_permission_groups()
    assert _memberships(widened["id"]) == ["admins", "leaders"]


# --- T-3: the role mirror is not read by any decision -----------------------


def _member_whose_mirror_lies() -> dict[str, str]:
    """Holds only `users`, while the legacy column claims `admin`."""
    user, headers = _member("mirror-lies", ["users"])
    with db.SessionLocal() as session:
        session.get(db.UserAccountRow, user["id"]).role = "admin"
        session.commit()
    with db.SessionLocal() as session:
        assert session.get(db.UserAccountRow, user["id"]).role == "admin"
    assert _memberships(user["id"]) == ["users"]
    return headers


def test_t3_an_admin_role_mirror_does_not_open_the_admin_routes() -> None:
    headers = _member_whose_mirror_lies()
    assert client.get(ADMIN_ROUTE, headers=headers).status_code == 403


def test_t3_an_admin_role_mirror_does_not_open_the_user_manager_routes() -> None:
    headers = _member_whose_mirror_lies()
    assert client.get(MANAGER_ROUTE, headers=headers).status_code == 403


# --- T-4/T-5/T-6: what each group reaches -----------------------------------


def test_t4_admins_reach_the_admin_routes() -> None:
    _user, headers = _member("reach-admin", ["admins"])
    assert client.get(ADMIN_ROUTE, headers=headers).status_code == 200


def test_t4_admins_reach_a_second_admin_route() -> None:
    _user, headers = _member("reach-admin2", ["admins"])
    assert client.get(ADMIN_ROUTE_2, headers=headers).status_code == 200


def test_t5_leaders_reach_the_user_manager_routes() -> None:
    _user, headers = _member("reach-lead", ["leaders"])
    assert client.get(MANAGER_ROUTE, headers=headers).status_code == 200


def test_t5_leaders_do_not_reach_the_admin_routes() -> None:
    _user, headers = _member("reach-lead-stop", ["leaders"])
    assert client.get(ADMIN_ROUTE, headers=headers).status_code == 403


def test_t6_plain_users_do_not_reach_the_user_manager_routes() -> None:
    _user, headers = _member("reach-user", ["users"])
    assert client.get(MANAGER_ROUTE, headers=headers).status_code == 403


def test_t6_plain_users_do_not_reach_the_admin_routes() -> None:
    _user, headers = _member("reach-user-admin", ["users"])
    assert client.get(ADMIN_ROUTE, headers=headers).status_code == 403


# --- T-8: the API surface moved exactly where it was meant to ---------------


_BEFORE = pathlib.Path(__file__).parent / "data" / "api-surface-before-permission-groups.json"
_CHANGED_SCHEMAS = ("UserAccountItem", "UserAccountCreateBody", "UserAccountUpdateBody")


def test_t8_the_api_surface_delta_is_exactly_the_three_user_schemas() -> None:
    """A count that does not move is not evidence that nothing was lost.

    endpoint/operation/schema counts all stay at 82 through this change, so the
    gate has to name the fields: what left the three user schemas, what arrived,
    and that the other 79 did not move a byte.

    Those 79 are selected BY NAME (2026-08-11). This read `len(everything) == 79`
    and compared a digest of everything-but-the-three, which measured two claims
    at once: that the frozen 79 are intact, and that no schema has been added
    since. The second is not this test's business -- the ACL work added three and
    turned it red without one of the 79 having moved -- and the frozen file had
    no name list, so the digest could not be recomputed over the right subset.
    Selecting by name keeps the real claim and drops the accidental one; a
    missing name now fails, which the count could not distinguish from a swap.
    """
    # Load the sibling by path rather than by name: the surface is computed in
    # exactly one place, and a copy here would drift from it silently.
    spec = importlib.util.spec_from_file_location(
        "_api_surface_for_delta", pathlib.Path(__file__).parent / "test_api_surface.py"
    )
    surface_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(surface_module)
    _stable, current_surface = surface_module._stable, surface_module.current_surface

    before = json.loads(_BEFORE.read_text(encoding="utf-8"))
    after = current_surface()

    frozen_names = before["unchanged_schema_names"]
    assert len(frozen_names) == before["unchanged_schema_count"]
    missing = [name for name in frozen_names if name not in after["schemas"]]
    assert not missing, f"schemas that existed before permission groups are gone: {missing}"

    # Contract 2 added one field to a schema that predates permission groups.
    # It is named here and taken back out before hashing, so the frozen digest
    # still measures the other 77 byte for byte -- declaring the one change
    # keeps the gate rather than regenerating past it.
    # v2.14 added one optional key to a schema that predates permission
    # groups, for the same reason and by the same rule: named here, taken
    # back out before hashing, so the frozen digest still measures the rest
    # byte for byte.
    # [I-257] added one field to two schemas that predate permission groups, by
    # the same rule: named here, taken back out before hashing, so the frozen
    # digest keeps measuring everything else byte for byte.
    declared_additions = {
        "HistoryPostBody": {"catalog_mode"},
        "AppInfoResponse": {"thumbnail_hidpi"},
        "ComposeRequest": {"fires_on"},
        "Arrangement": {"group_size"},
        # I-154 added one key to three requests and one to three responses, by
        # the same rule: named here, taken back out before hashing, so the
        # frozen digest keeps measuring everything else byte for byte. A second
        # key arriving in any of the six is still red.
        "PaintRequest": {"limits"},
        "RenderSvgRequest": {"limits"},
        "RenderScoreRequest": {"limits"},
        "PaintResponse": {"render_limits_source"},
        "ComposeResponse": {"render_limits_source"},
        "RenderScoreResponse": {"render_limits_source"},
        # I-132 added one key to the settings response, by the same rule: the
        # panel turns the total into the weight of a work, and the measured cost
        # of one mark comes from the server rather than a copy in the browser.
        "RenderLimitsStatus": {"bytes_per_mark"},
        # 2026-08-17 added one key to each of two schemas that predate
        # permission groups, by the same rule: named here, taken back out
        # before hashing. `HistoryItem.svg_bytes` is a work's own weight,
        # which the strip needs while the listing withholds the picture;
        # `UserSettingsBody.history_strip_fields` is the reader's choice of
        # what the strip prints. A SECOND key arriving in either is still red.
        # UserAccountItem carries the same choice and is already one of the
        # three schemas this test excludes wholesale.
        "UserSettingsBody": {"history_strip_fields"},
    }
    # I-136 changed a schema by taking a bound OFF a property rather than by
    # adding or removing one, so `declared_additions` above cannot express it and
    # the digest would move with nothing named. `Arrangement.cluster_count` gave
    # up its static maximum for the reason `count` never had one: a bound no
    # setting can reach is a second, invisible copy of the setting, and twelve
    # was the real stop on how many clusters a raised ceiling could be split
    # into. Put it back before hashing, so the frozen digest keeps measuring
    # everything else byte for byte and a SECOND movement in this schema is red.
    declared_bound_restorations = {
        "Arrangement": ("cluster_count", "maximum", 12.0),
    }
    # ddl-engine 18 changed a schema without adding a field to it: a fill became
    # a surface word like the other eight, so `SurfaceTexture` gained a value.
    # Declared the same way and taken back out the same way, so the frozen digest
    # keeps measuring everything else byte for byte. The description names the
    # values too, so it is restored along with the enum.
    # ddl-engine 19 / render-engine 34 did the same to `CanvasGroundSpec`: the
    # ground became a support you can name, so `GroundMaterial` gained two. A
    # schema may now declare more than one value, because this one gained two at
    # once and a single-value shape would have had to be relaxed into "any
    # movement in this enum is fine".
    declared_enum_additions = {
        "SurfaceSpec": ("texture", ("solid",), (" / solid=塗り",)),
        "CanvasGroundSpec": (
            "material",
            ("canvas", "drawing_paper"),
            (" / canvas=カンバス", " / drawing_paper=画用紙"),
        ),
    }
    # Every table above is read inside the loop below, and the loop walks the
    # frozen names alone. A name that is not frozen therefore declares nothing:
    # the entry is never looked up, nothing is taken back out, and no digest
    # moves -- yet it reads on the page as though that schema were covered.
    # `HistoryItem` sat here that way (it is in neither the frozen 78 nor the
    # three changed schemas, so this test never touched it), and I-191 added two
    # keys to it while the entry claimed two others. Declaring an unfrozen name
    # is the mistake, so it is red rather than silent.
    for table, label in (
        (declared_additions, "declared_additions"),
        (declared_enum_additions, "declared_enum_additions"),
        (declared_bound_restorations, "declared_bound_restorations"),
    ):
        unfrozen = sorted(set(table) - set(frozen_names))
        assert not unfrozen, (
            f"{label} names schemas this test never reads: {unfrozen}. "
            "Only the frozen names are walked, so an entry here measures nothing. "
            "Either the schema belongs in the frozen set, or the entry should go."
        )

    others = {}
    for name in frozen_names:
        body = after["schemas"][name]
        added = declared_additions.get(name)
        if added:
            parsed = json.loads(body)
            for field in added:
                assert field in parsed["properties"], f"{name} was declared to gain {field}"
                del parsed["properties"][field]
                # A key with no default is also listed under `required`, and
                # leaving it there would move the digest with nothing named. The
                # twelve keys declared before this one were all optional, so the
                # list never had to be touched; taking the name out of it is a
                # no-op for them and the whole of the change for a required one.
                if isinstance(parsed.get("required"), list):
                    parsed["required"] = [f for f in parsed["required"] if f != field]
            body = _stable(parsed)
        enum_added = declared_enum_additions.get(name)
        if enum_added:
            field, added_values, description_fragments = enum_added
            parsed = json.loads(body)
            values = parsed["properties"][field]["enum"]
            for value in added_values:
                assert value in values, f"{name}.{field} was declared to gain {value}"
            parsed["properties"][field]["enum"] = [
                v for v in values if v not in added_values
            ]
            description = parsed["properties"][field]["description"]
            for fragment in description_fragments:
                assert fragment in description, f"{name}.{field} description"
                description = description.replace(fragment, "", 1)
            parsed["properties"][field]["description"] = description
            body = _stable(parsed)
        bound = declared_bound_restorations.get(name)
        if bound:
            field, key, value = bound
            parsed = json.loads(body)
            branches = parsed["properties"][field]["anyOf"]
            branch = next(b for b in branches if b.get("type") == "integer")
            assert key not in branch, f"{name}.{field} was declared to lose {key}"
            branch[key] = value
            body = _stable(parsed)
        others[name] = body
    assert (
        hashlib.sha256(_stable(others).encode()).hexdigest()
        == before["unchanged_schema_digest"]
    )

    for name in _CHANGED_SCHEMAS:
        old_props = set(json.loads(before["changed_schemas"][name])["properties"])
        new_props = set(json.loads(after["schemas"][name])["properties"])
        assert old_props - new_props == {"role"} | ({"role_label"} if name == "UserAccountItem" else set()), name
        # 2026-08-17: the account also carries which facts the history strip
        # prints under each thumbnail. Named here rather than left to widen the
        # comparison, so a THIRD arrival in UserAccountItem is still red.
        expected_arrivals = {"permission_groups"} | (
            {"permission_group_labels", "history_strip_fields"}
            if name == "UserAccountItem" else set()
        )
        assert new_props - old_props == expected_arrivals, name


# --- T-9: permission groups and organisation groups are separate ------------


def test_t9_two_members_of_one_organisation_group_are_judged_separately() -> None:
    """The organisation group they share says nothing about what they may do."""
    circle = db.add_user_group(f"circle-a-{uuid.uuid4().hex[:8]}")
    _lead, lead_headers = _member("circle-lead", ["leaders"], circle["id"])
    _plain, plain_headers = _member("circle-plain", ["users"], circle["id"])

    assert client.get(MANAGER_ROUTE, headers=lead_headers).status_code == 200
    assert client.get(MANAGER_ROUTE, headers=plain_headers).status_code == 403


def test_t9_moving_between_organisation_groups_does_not_move_permission() -> None:
    first = db.add_user_group(f"circle-b-{uuid.uuid4().hex[:8]}")
    second = db.add_user_group(f"circle-c-{uuid.uuid4().hex[:8]}")
    user, headers = _member("circle-move", ["users"], first["id"])
    assert client.get(MANAGER_ROUTE, headers=headers).status_code == 403

    moved = db.update_user(user["id"], group_id=second["id"])
    assert moved["group_id"] == second["id"]
    assert moved["permission_groups"] == ["users"]
    assert client.get(MANAGER_ROUTE, headers=headers).status_code == 403


# --- T-10: holding two groups works, and the stronger one decides -----------


def test_t10_a_member_holding_admins_and_leaders_gets_both() -> None:
    user, headers = _member("both", ["admins", "leaders"])
    assert _memberships(user["id"]) == ["admins", "leaders"]
    # The user-manager routes come with `leaders`, the admin ones with `admins`:
    # a implementation that kept only the first membership would lose one of these.
    assert client.get(MANAGER_ROUTE, headers=headers).status_code == 200
    assert client.get(ADMIN_ROUTE, headers=headers).status_code == 200


# --- T-13: single-user mode's pin is untouched by any of this ---------------


def test_t13_the_single_user_pin_does_not_follow_the_permission_groups() -> None:
    """The pin holds an account id and reads neither role nor group.

    Single-user mode resolves the owner once and writes the id down, so a
    restored backup names the same person.  Swapping that person's permission
    groups must not move the pin -- if it did, the owner's works would appear
    to belong to somebody else.
    """
    user, _headers = _member("pinned", ["admins"])
    db._write_app_setting(db._SINGLE_USER_SETTING_KEY, {"user_id": user["id"]})
    assert db.single_user_pinned_id() == user["id"]

    db.update_user(user["id"], permission_groups=["users"])
    assert _memberships(user["id"]) == ["users"]
    assert db.single_user_pinned_id() == user["id"]
