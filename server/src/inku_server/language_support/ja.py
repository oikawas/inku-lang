"""Japanese instruction-language support."""

from __future__ import annotations

from ..composer import SYSTEM_PROMPT as STAGE2_PROMPT
from ..ddl_expander import expand_intermediate_ddl
from ..interpreter import SYSTEM_PROMPT as STAGE1_PROMPT
from .base import InstructionLanguageSupport


def expand_intermediate(ddl: str, context_text: str | None = None) -> str:
    return expand_intermediate_ddl(ddl, lang="ja", context_text=context_text)


SUPPORT = InstructionLanguageSupport(
    code="ja",
    stage1_prompt=STAGE1_PROMPT,
    stage2_prompt=STAGE2_PROMPT,
    expand_intermediate=expand_intermediate,
)
