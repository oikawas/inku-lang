"""Instruction-language registry for Stage 1 / Stage 1.5 / Stage 2 support."""

from __future__ import annotations

import re

from .base import InstructionLanguageSupport
from .en import SUPPORT as EN_SUPPORT
from .ja import SUPPORT as JA_SUPPORT


INSTRUCTION_LANGUAGE_REGISTRY: dict[str, InstructionLanguageSupport] = {
    JA_SUPPORT.code: JA_SUPPORT,
    EN_SUPPORT.code: EN_SUPPORT,
}

SUPPORTED_INSTRUCTION_LANGS = frozenset(INSTRUCTION_LANGUAGE_REGISTRY)
REQUESTED_INSTRUCTION_LANGS = SUPPORTED_INSTRUCTION_LANGS | {"auto"}

_JAPANESE_TEXT_RE = re.compile(r"[\u3040-\u30ff\u3400-\u9fff]")
_LATIN_TEXT_RE = re.compile(r"[A-Za-z]")


def normalize_instruction_lang(value: str | None, *, default: str = "ja") -> str:
    lang = (value or default).strip().lower()
    if lang not in REQUESTED_INSTRUCTION_LANGS:
        raise ValueError(f"unsupported instruction language: {value}")
    return lang


def resolve_instruction_lang(text: str, requested: str, *, fallback: str = "ja") -> str:
    lang = normalize_instruction_lang(requested)
    if lang != "auto":
        return lang
    if _JAPANESE_TEXT_RE.search(text):
        return "ja"
    if _LATIN_TEXT_RE.search(text):
        return "en"
    normalized_fallback = normalize_instruction_lang(fallback)
    return "ja" if normalized_fallback == "auto" else normalized_fallback


def instruction_language(lang: str) -> InstructionLanguageSupport:
    normalized = normalize_instruction_lang(lang)
    if normalized == "auto":
        raise ValueError("auto must be resolved before selecting language support")
    return INSTRUCTION_LANGUAGE_REGISTRY[normalized]


def stage_prompts_for_lang(lang: str) -> tuple[str, str]:
    support = instruction_language(lang)
    return support.stage1_prompt, support.stage2_prompt


def expand_intermediate_for_lang(
    ddl: str,
    *,
    lang: str,
    context_text: str | None = None,
    vary_seed: int | None = None,
    plugin_instructions_present: bool = False,
    tenkei: str = "auto",
    focus: str | None = None,
    variation_amplitude: str | None = None,
    variation_seed: int | None = None,
    variation_report: dict | None = None,
) -> str:
    return instruction_language(lang).expand_intermediate(
        ddl,
        context_text,
        vary_seed,
        plugin_instructions_present=plugin_instructions_present,
        tenkei=tenkei,
        focus=focus,
        variation_amplitude=variation_amplitude,
        variation_seed=variation_seed,
        variation_report=variation_report,
    )
