"""Endpoints about a description itself, apart from drawing it.

The description meter asks these as the author types. Each language's
judgement can be turned off in Settings > Other (server); a count asked for
while its language is off is refused with 409, and the page, which reads the
same switches from /api/client-config, does not ask.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ... import db as _db
from ...mora import count_mora
from ...syllables import count_syllables
from ..deps import _current_user


router = APIRouter(dependencies=[Depends(_current_user)])


def _require_meter(language: str) -> None:
    if not _db.get_description_meter_settings()[language]:
        raise HTTPException(status_code=409, detail=f"the {language} description meter is off")


class DescriptionMoraBody(BaseModel):
    # The meter asks as the author types; a description far past a chōka is
    # counted by characters on the page instead.
    text: str = Field(default="", max_length=4000)


class DescriptionMoraResponse(BaseModel):
    mora: int = Field(description="音数の合計（読めなかった字は推定で数える）")
    phrases: list[int] = Field(description="改行・空白・読点で区切った句ごとの音数")
    unread: list[str] = Field(description="辞書が読めなかった字。空でなければ合計は推定を含む")


@router.post("/api/description/mora", response_model=DescriptionMoraResponse)
def api_description_mora(body: DescriptionMoraBody) -> DescriptionMoraResponse:
    """記述の音数を数える。記述欄の詩型の目安（俳句 5-7-5 など）に使う。"""
    _require_meter("japanese")
    counted = count_mora(body.text)
    return DescriptionMoraResponse(mora=counted.total, phrases=counted.phrases, unread=counted.unread)


class DescriptionSyllablesBody(BaseModel):
    text: str = Field(default="", max_length=4000)


class DescriptionSyllablesResponse(BaseModel):
    syllables: int = Field(description="音節の合計（辞書に無い語は推定で数える）")
    lines: list[int] = Field(description="空でない行ごとの音節")
    unknown: list[str] = Field(description="発音辞書に無かった語。空でなければ合計は推定を含む")


@router.post("/api/description/syllables", response_model=DescriptionSyllablesResponse)
def api_description_syllables(body: DescriptionSyllablesBody) -> DescriptionSyllablesResponse:
    """英語の記述の音節を行ごとに数える（CMU Pronouncing Dictionary）。記述欄の形式の目安に使う。"""
    _require_meter("english")
    counted = count_syllables(body.text)
    return DescriptionSyllablesResponse(syllables=counted.total, lines=counted.lines, unknown=counted.unknown)
