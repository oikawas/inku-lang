from inku_server.composer import SYSTEM_PROMPT as STAGE2_PROMPT_JA
from inku_server.composer import SYSTEM_PROMPT_EN as STAGE2_PROMPT_EN
from inku_server.ddl_expander import expand_intermediate_ddl
from inku_server.interpreter import SYSTEM_PROMPT as STAGE1_PROMPT_JA
from inku_server.interpreter import SYSTEM_PROMPT_EN as STAGE1_PROMPT_EN
from inku_server.languages import (
    INSTRUCTION_LANGUAGE_REGISTRY,
    expand_intermediate_for_lang,
    resolve_instruction_lang,
    stage_prompts_for_lang,
)


def test_language_registry_preserves_existing_prompt_bindings():
    assert set(INSTRUCTION_LANGUAGE_REGISTRY) == {"ja", "en"}
    assert stage_prompts_for_lang("ja") == (STAGE1_PROMPT_JA, STAGE2_PROMPT_JA)
    assert stage_prompts_for_lang("en") == (STAGE1_PROMPT_EN, STAGE2_PROMPT_EN)


def test_language_registry_preserves_existing_expander_behavior():
    ja_ddl = "中心に黒い四角を置く。白い横線を三本引く。"
    en_ddl = "Place one black square in the center. Draw three white horizontal lines."

    assert expand_intermediate_for_lang(ja_ddl, lang="ja") == expand_intermediate_ddl(ja_ddl, lang="ja")
    assert expand_intermediate_for_lang(en_ddl, lang="en") == expand_intermediate_ddl(en_ddl, lang="en")


def test_english_language_support_adds_no_taste_of_its_own():
    """The English support used to append sentences the DDL never asked for.

    `jazz`, `quilt`, `subway`, `billboard`, `prairie`, `coastal fog` and
    `warehouse` each summoned a line of their own -- but only at the `auto`
    staffage level, which is what shows they were staffage. The level was folded
    away (v2.11.0) and so were they: the registry path is now the plain expander
    in both languages.
    """
    ja_ddl = "中心に黒い四角を置く。白い横線を三本引く。"
    en_ddl = "Draw three blue lines with jazz syncopation near a city corner."

    assert expand_intermediate_for_lang(ja_ddl, lang="ja") == expand_intermediate_ddl(ja_ddl, lang="ja")
    en_after = expand_intermediate_for_lang(en_ddl, lang="en")
    assert en_after == expand_intermediate_ddl(en_ddl, lang="en")
    assert "syncopated city rhythm" not in en_after
    assert "blue-note value" not in en_after


def test_language_support_owns_coerce_marker_sets():
    ja_markers = INSTRUCTION_LANGUAGE_REGISTRY["ja"].coerce_markers
    en_markers = INSTRUCTION_LANGUAGE_REGISTRY["en"].coerce_markers

    assert "patchwork" in en_markers["rhythm"]
    assert "patchwork" not in ja_markers["rhythm"]
    assert "暗闇" in ja_markers["explicit_surface"]
    assert "dark field" in en_markers["explicit_surface"]


def test_auto_instruction_language_resolution_remains_stable():
    assert resolve_instruction_lang("一滴の墨", "auto") == "ja"
    assert resolve_instruction_lang("one black line", "auto") == "en"
    assert resolve_instruction_lang("12345", "auto") == "ja"
    assert resolve_instruction_lang("12345", "auto", fallback="en") == "en"
