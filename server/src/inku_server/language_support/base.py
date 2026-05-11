"""Shared types for instruction-language support."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class InstructionLanguageSupport:
    code: str
    stage1_prompt: str
    stage2_prompt: str
    expand_intermediate: Callable[[str, str | None], str]
