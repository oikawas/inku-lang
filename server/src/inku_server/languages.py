"""Instruction-language registry for Stage 1 / Stage 1.5 / Stage 2 support."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

from .composer import SYSTEM_PROMPT as STAGE2_PROMPT_JA
from .composer import SYSTEM_PROMPT_EN as STAGE2_PROMPT_EN
from .ddl_expander import expand_intermediate_ddl
from .interpreter import SYSTEM_PROMPT as STAGE1_PROMPT_JA
from .interpreter import SYSTEM_PROMPT_EN as STAGE1_PROMPT_EN


@dataclass(frozen=True)
class InstructionLanguageSupport:
    code: str
    stage1_prompt: str
    stage2_prompt: str
    expand_intermediate: Callable[[str, str | None], str]


def _expand_with_lang(lang: str) -> Callable[[str, str | None], str]:
    def expand(ddl: str, context_text: str | None = None) -> str:
        return expand_intermediate_ddl(ddl, lang=lang, context_text=context_text)

    return expand


INSTRUCTION_LANGUAGE_REGISTRY: dict[str, InstructionLanguageSupport] = {
    "ja": InstructionLanguageSupport(
        code="ja",
        stage1_prompt=STAGE1_PROMPT_JA,
        stage2_prompt=STAGE2_PROMPT_JA,
        expand_intermediate=_expand_with_lang("ja"),
    ),
    "en": InstructionLanguageSupport(
        code="en",
        stage1_prompt=STAGE1_PROMPT_EN,
        stage2_prompt=STAGE2_PROMPT_EN,
        expand_intermediate=_expand_with_lang("en"),
    ),
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


def resolve_instruction_lang(text: str, requested: str) -> str:
    lang = normalize_instruction_lang(requested)
    if lang != "auto":
        return lang
    if _JAPANESE_TEXT_RE.search(text):
        return "ja"
    if _LATIN_TEXT_RE.search(text):
        return "en"
    return "ja"


def instruction_language(lang: str) -> InstructionLanguageSupport:
    normalized = normalize_instruction_lang(lang)
    if normalized == "auto":
        raise ValueError("auto must be resolved before selecting language support")
    return INSTRUCTION_LANGUAGE_REGISTRY[normalized]


def stage_prompts_for_lang(lang: str) -> tuple[str, str]:
    support = instruction_language(lang)
    return support.stage1_prompt, support.stage2_prompt


def expand_intermediate_for_lang(ddl: str, *, lang: str, context_text: str | None = None) -> str:
    return instruction_language(lang).expand_intermediate(ddl, context_text)
