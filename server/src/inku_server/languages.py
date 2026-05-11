"""Compatibility exports for instruction-language support."""

from .language_support import (
    INSTRUCTION_LANGUAGE_REGISTRY,
    REQUESTED_INSTRUCTION_LANGS,
    SUPPORTED_INSTRUCTION_LANGS,
    InstructionLanguageSupport,
    expand_intermediate_for_lang,
    instruction_language,
    normalize_instruction_lang,
    resolve_instruction_lang,
    stage_prompts_for_lang,
)

__all__ = [
    "INSTRUCTION_LANGUAGE_REGISTRY",
    "REQUESTED_INSTRUCTION_LANGS",
    "SUPPORTED_INSTRUCTION_LANGS",
    "InstructionLanguageSupport",
    "expand_intermediate_for_lang",
    "instruction_language",
    "normalize_instruction_lang",
    "resolve_instruction_lang",
    "stage_prompts_for_lang",
]
