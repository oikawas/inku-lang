"""English forms are told apart by lines and syllables.

A word's syllables are the vowels of its pronunciation in the bundled CMU
Pronouncing Dictionary; a word it lacks is counted by vowel groups and named.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from inku_server import db
from inku_server.api import app
from inku_server.syllables import count_syllables

client = TestClient(app)


@pytest.fixture
def member_headers():
    suffix = uuid.uuid4().hex[:8]
    group = db.add_user_group(f"syll-{suffix}")
    user = db.add_user(
        username=f"syll-{suffix}",
        email=f"syll-{suffix}@example.test",
        password="password-123",
        permission_groups=["users"],
        group_id=group["id"],
    )
    token = db.create_session(user["id"])
    yield {"Authorization": f"Bearer {token}"}
    db.delete_session(token)
    db.delete_user(user["id"])
    db.delete_user_group(group["id"])


def test_a_haiku_in_english_is_five_seven_five():
    counted = count_syllables("An old silent pond\nA frog jumps into the pond\nSplash! Silence again")
    assert counted.lines == [5, 7, 5]
    assert counted.unknown == []


def test_a_cinquain_is_two_four_six_eight_two():
    # Adelaide Crapsey, "November Night".
    counted = count_syllables(
        "Listen...\nWith faint dry sound,\nLike steps of passing ghosts,\n"
        "The leaves, frost-crisp'd, break from the trees\nAnd fall."
    )
    assert counted.lines == [2, 4, 6, 8, 2]


def test_a_word_the_dictionary_lacks_is_estimated_and_named():
    counted = count_syllables("Inku draws")
    assert counted.unknown == ["Inku"]
    assert counted.total == 3


def test_the_endpoint_returns_the_lines(member_headers):
    response = client.post(
        "/api/description/syllables",
        json={"text": "An old silent pond\nA frog jumps into the pond\nSplash! Silence again"},
        headers=member_headers,
    )
    assert response.status_code == 200
    assert response.json() == {"syllables": 17, "lines": [5, 7, 5], "unknown": []}
