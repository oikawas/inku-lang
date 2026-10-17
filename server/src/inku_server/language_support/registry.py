"""Instruction-language identity and request resolution."""

from __future__ import annotations

import importlib
from functools import lru_cache
from types import ModuleType

from .base import InstructionLanguageSupport
from .en import SUPPORT as EN_SUPPORT
from .ja import SUPPORT as JA_SUPPORT


INSTRUCTION_LANGUAGE_REGISTRY: dict[str, InstructionLanguageSupport] = {
    JA_SUPPORT.code: JA_SUPPORT,
    EN_SUPPORT.code: EN_SUPPORT,
}

SUPPORTED_INSTRUCTION_LANGS = frozenset(INSTRUCTION_LANGUAGE_REGISTRY)
REQUESTED_INSTRUCTION_LANGS = SUPPORTED_INSTRUCTION_LANGS | {"auto"}

@lru_cache(maxsize=1)
def _native() -> ModuleType:
    return importlib.import_module("inku_render")


def normalize_instruction_lang(value: str | None, *, default: str = "ja") -> str:
    # The rule is the shared core's (Python's `(value or default).strip().lower()`),
    # so Server, Android and Swift read a request alike.
    lang = _native().pipeline_normalize_instruction_language(value, default)
    if lang is None:
        raise ValueError(f"unsupported instruction language: {value}")
    return lang


def resolve_instruction_lang(text: str, requested: str, *, fallback: str = "ja") -> str:
    """Japanese script first, then Latin letters, then the fallback (shared core)."""
    normalize_instruction_lang(requested)
    lang = _native().pipeline_resolve_instruction_language(text, requested, fallback)
    if lang is None:
        raise ValueError(f"unsupported instruction language: {fallback}")
    return lang


def instruction_language(lang: str) -> InstructionLanguageSupport:
    normalized = normalize_instruction_lang(lang)
    if normalized == "auto":
        raise ValueError("auto must be resolved before selecting language support")
    return INSTRUCTION_LANGUAGE_REGISTRY[normalized]
