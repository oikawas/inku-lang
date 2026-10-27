// Which language a description or a DDL is written in.
//
// The rule is the shared core's `resolve_instruction_language`, which the
// server calls (`server/src/inku_server/language_support/registry.py`), ported
// one for one:
//
//     text = text without its title lines (DDL 27; a title quotes a name in
//            any script)
//     if Japanese script in text: return "ja"
//     if Latin letters in text:   return "en"
//     return fallback
//
// Japanese wins over Latin, so a description that mixes the two is Japanese --
// which is why the two tests are ordered and not combined. Text that carries
// neither (an empty editor, a line of digits) resolves to the fallback, and the
// server's API layer makes that fallback the UI language
// (`fallback = ui_lang if ui_lang in SUPPORTED_INSTRUCTION_LANGS else "ja"`,
// api_core/common.py), which is what `instructionLangOf` narrows to here.
//
// Only the `auto` branch is ported: the web client sends `instruction_lang`
// as a const `'auto'`, so the server's early return for an explicitly
// requested language has no caller here. Porting it would add a branch nothing
// reaches.

import { withoutDdlTitleLines } from './ddl-titles';

/** A language a DDL can actually be in. `auto` is a request, never an answer. */
export type ResolvedInstructionLang = 'ja' | 'en';

const JAPANESE_TEXT_RE = /[\u3040-\u30ff\u3400-\u9fff]/;
const LATIN_TEXT_RE = /[A-Za-z]/;

/** The language `text` is written in, or `fallback` when it says neither. */
export function resolveInstructionLang(
	text: string,
	fallback: ResolvedInstructionLang
): ResolvedInstructionLang {
	const body = withoutDdlTitleLines(text);
	if (JAPANESE_TEXT_RE.test(body)) return 'ja';
	if (LATIN_TEXT_RE.test(body)) return 'en';
	return fallback;
}

/** The UI language as an instruction language, narrowed the way the server
    narrows it before using it as the fallback. */
export function instructionLangOf(uiLang: string | null | undefined): ResolvedInstructionLang {
	return uiLang === 'ja' || uiLang === 'en' ? uiLang : 'ja';
}
