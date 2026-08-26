"""Direct compatibility coverage for the fixed permission-group vocabulary."""

from __future__ import annotations

import ast
import inspect

import pytest

from inku_server import db
from inku_server.persistence import groups


def _owner_or_skip():
    owner = getattr(groups, "normalize_permission_groups", None)
    if owner is None:
        pytest.skip("permission vocabulary owner is intentionally absent during fail-first")
    return owner


def test_groups_owns_vocabulary_and_db_delegates() -> None:
    assert hasattr(groups, "PERMISSION_GROUPS")
    assert hasattr(groups, "normalize_permission_groups")
    assert hasattr(groups, "derived_role")
    for name in ("_derived_role", "_normalize_permission_groups"):
        facade = ast.parse(inspect.getsource(getattr(db, name))).body[0]
        assert isinstance(facade, ast.FunctionDef)
        assert isinstance(facade.body[-1], ast.Return)
    assert db.PERMISSION_GROUPS is groups.PERMISSION_GROUPS
    assert db.PERMISSION_GROUP_LABELS is groups.PERMISSION_GROUP_LABELS
    assert db._ROLE_MIRROR_BY_GROUP is groups.ROLE_MIRROR_BY_GROUP
    assert db._ELEVATED_PERMISSION_GROUPS is groups.ELEVATED_PERMISSION_GROUPS
    assert db._LEGACY_ROLE_TO_PERMISSION_GROUP is groups.LEGACY_ROLE_TO_PERMISSION_GROUP


def test_permission_group_normalization_preserves_order_and_deduplication() -> None:
    normalize = _owner_or_skip()
    assert normalize(["users", "admins", "users", "leaders"]) == [
        "admins",
        "leaders",
        "users",
    ]


def test_permission_group_normalization_preserves_exact_errors() -> None:
    normalize = _owner_or_skip()
    with pytest.raises(ValueError, match="permission_groups must be a list"):
        normalize("admins")
    with pytest.raises(ValueError, match="invalid permission group: unknown"):
        normalize(["unknown"])
    with pytest.raises(ValueError, match="at least one permission group is required"):
        normalize([])


def test_legacy_role_projection_preserves_priority_and_reverse_map() -> None:
    _owner_or_skip()
    assert groups.derived_role(["leaders", "admins"]) == "admin"
    assert groups.derived_role(["leaders", "users"]) == "group_lead"
    assert groups.derived_role(["users"]) == "user"
    assert groups.LEGACY_ROLE_TO_PERMISSION_GROUP == {
        "admin": "admins",
        "group_lead": "leaders",
        "user": "users",
    }
