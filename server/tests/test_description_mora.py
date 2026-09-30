"""The description meter counts sounds, not characters.

Verse forms are counted in sounds: 「古池や」 is five sounds in three
characters. The count reads each word with SudachiPy's small dictionary, so a
kanji counts the sounds of its reading, a small ャュョ joins the kana before
it, and ッ, ン and ー count one each.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from inku_server import db
from inku_server.api import app
from inku_server.mora import UNREAD_KANJI_MORA, count_mora, kana_mora

client = TestClient(app)


@pytest.fixture
def member_headers():
    suffix = uuid.uuid4().hex[:8]
    group = db.add_user_group(f"mora-{suffix}")
    user = db.add_user(
        username=f"mora-{suffix}",
        email=f"mora-{suffix}@example.test",
        password="password-123",
        permission_groups=["users"],
        group_id=group["id"],
    )
    token = db.create_session(user["id"])
    yield {"Authorization": f"Bearer {token}"}
    db.delete_session(token)
    db.delete_user(user["id"])
    db.delete_user_group(group["id"])


def test_a_haiku_counts_seventeen_sounds_in_eleven_characters():
    counted = count_mora("古池や蛙飛び込む水の音")
    assert counted.total == 17
    assert counted.unread == []


def test_a_poem_set_out_in_lines_is_counted_phrase_by_phrase():
    assert count_mora("古池や\n蛙飛び込む\n水の音").phrases == [5, 7, 5]
    assert count_mora("柿食えば　鐘が鳴るなり、法隆寺").phrases == [5, 7, 5]


def test_joined_and_long_sounds_count_as_spoken():
    # きょ-う-は-と-う-きょ-う-で-あ-め
    assert count_mora("今日は東京で雨").total == 10
    assert kana_mora("きゃっと") == 3
    assert kana_mora("ラーメン") == 4


def test_the_drawing_reads_no_comment_and_neither_does_the_meter():
    assert count_mora("古池や[季語は蛙]蛙飛び込む水の音").total == 17


def test_a_character_the_dictionary_cannot_read_is_estimated_and_named():
    counted = count_mora("濡")
    assert counted.unread == ["濡"]
    assert counted.total == UNREAD_KANJI_MORA


def test_the_endpoint_returns_the_count(member_headers):
    response = client.post("/api/description/mora", json={"text": "古池や\n蛙飛び込む\n水の音"}, headers=member_headers)
    assert response.status_code == 200
    assert response.json() == {"mora": 17, "phrases": [5, 7, 5], "unread": []}
