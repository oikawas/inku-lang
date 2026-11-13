// The names of the composition's forms, laws, roles, kinds and places, as the
// screen shows them (2026-11-13). One table for the whole app: the shared core
// owns it (inku-pipeline `composition_names.rs`), the shared fixture
// `server/tests/data/composition-names-v1.json` records it, and
// `server/scripts/gen_composition_names_ts.py` writes the generated module this
// file reads. A key the table does not have reads as itself, so a record from
// a newer core still shows something.

import { COMPOSITION_NAMES } from '../../composition-names.generated';

type Bilingual = { ja: string; en: string };
type Entry = { name: Bilingual };

function indexBy<T extends Entry>(rows: readonly T[], key: (row: T) => string): Map<string, T> {
	return new Map(rows.map((row) => [key(row), row]));
}

const FORMS = indexBy(COMPOSITION_NAMES.forms, (row) => row.id);
const LAWS = indexBy(COMPOSITION_NAMES.laws, (row) => row.code);
const COLOR_LAWS = indexBy(COMPOSITION_NAMES.color_laws, (row) => row.code);
const ROLES = indexBy(COMPOSITION_NAMES.roles, (row) => row.id);
const KINDS = indexBy(COMPOSITION_NAMES.kinds, (row) => row.id);
const AT = indexBy(COMPOSITION_NAMES.at, (row) => row.id);
const PLACES = indexBy(COMPOSITION_NAMES.places, (row) => row.id);

function pick(text: Bilingual | undefined, fallback: string, isJapanese: boolean): string {
	return text ? (isJapanese ? text.ja : text.en) : fallback;
}

export const formIds = (): string[] => COMPOSITION_NAMES.forms.map((row) => row.id);
export const formName = (id: string, isJapanese: boolean): string => pick(FORMS.get(id)?.name, id, isJapanese);
export const formDescription = (id: string, isJapanese: boolean): string =>
	pick(FORMS.get(id)?.description, '', isJapanese);
export const lawName = (code: string, isJapanese: boolean): string => pick(LAWS.get(code)?.name, code, isJapanese);
export const lawFamily = (code: string, isJapanese: boolean): string => pick(LAWS.get(code)?.family, '', isJapanese);
export const lawSummary = (code: string, isJapanese: boolean): string => pick(LAWS.get(code)?.summary, '', isJapanese);
export const colorLawName = (code: string, isJapanese: boolean): string =>
	pick(COLOR_LAWS.get(code)?.name, code, isJapanese);
export const roleName = (id: string, isJapanese: boolean): string => pick(ROLES.get(id)?.name, id, isJapanese);
export const kindName = (id: string, isJapanese: boolean): string => pick(KINDS.get(id)?.name, id, isJapanese);
export const atName = (id: string, isJapanese: boolean): string => pick(AT.get(id)?.name, id, isJapanese);
export const placeName = (id: string, isJapanese: boolean): string => pick(PLACES.get(id)?.name, id, isJapanese);

/** A law as the generation info's details show it: its name, with its code after it ("黄金分割（B1）"). */
export function lawNameWithCode(code: string, isJapanese: boolean): string {
	const name = lawName(code, isJapanese);
	if (name === code) return code;
	return isJapanese ? `${name}（${code}）` : `${name} (${code})`;
}

/** The same for a color law. */
export function colorLawNameWithCode(code: string, isJapanese: boolean): string {
	const name = colorLawName(code, isJapanese);
	if (name === code) return code;
	return isJapanese ? `${name}（${code}）` : `${name} (${code})`;
}
