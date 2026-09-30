"""Endpoints about a description itself, apart from drawing it."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from ...mora import count_mora
from ..deps import _current_user


router = APIRouter(dependencies=[Depends(_current_user)])


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
    counted = count_mora(body.text)
    return DescriptionMoraResponse(mora=counted.total, phrases=counted.phrases, unread=counted.unread)
