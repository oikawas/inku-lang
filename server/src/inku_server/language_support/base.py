"""Shared types for instruction-language support."""

from __future__ import annotations

from dataclasses import dataclass
@dataclass(frozen=True)
class InstructionLanguageSupport:
    code: str
