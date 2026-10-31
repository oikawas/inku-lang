/** Reading a DDL file back into the editor.
 *
 * An `inku.ddl-export.v2` file carries the visible DDL and the plugin
 * definitions selected by its saved locks. They travel with the next new work only and
 * are validated again by the server's shared boundary; this module does not
 * interpret them. Any other text is read as plain DDL without definitions.
 */

export const DDL_EXPORT_SCHEMA = 'inku.ddl-export.v2';
import { resolveInstructionLang } from '../../instructionLang';
import type { ApiFetch } from '../../transport/api-fetch';
const MAX_IMPORTED_PLUGINS = 64;

export type ImportedPlugin = { definition: Record<string, unknown>; note: string };

export type DdlImport = {
	ddl: string;
	plugins: ImportedPlugin[];
	/** Qualified names of the carried plugins, for the author-facing notice. */
	names: string[];
};

function record(value: unknown): Record<string, unknown> | null {
	return value !== null && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : null;
}

export function parseDdlImport(text: string, language: 'ja' | 'en' = 'ja'): DdlImport {
	let parsed: unknown = null;
	try {
		parsed = JSON.parse(text);
	} catch {
		return { ddl: text, plugins: [], names: [] };
	}
	const file = record(parsed);
	if (file?.schema === 'inku.ddl-export.v1') throw new Error('ddl_export_requires_v2');
	if (file?.schema !== DDL_EXPORT_SCHEMA) {
		// JSON that is not an export is still the author's text.
		return { ddl: text, plugins: [], names: [] };
	}
	if (typeof file.ddl !== 'string') throw new Error('ddl_export_without_ddl');
	const plugins: ImportedPlugin[] = [];
	for (const item of Array.isArray(file.plugins) ? file.plugins : []) {
		const plugin = record(item);
		const definition = record(plugin?.definition);
		if (!definition) throw new Error('ddl_export_invalid_plugin');
		plugins.push({ definition, note: typeof plugin?.note === 'string' ? plugin.note : '' });
	}
	if (plugins.length > MAX_IMPORTED_PLUGINS) throw new Error('ddl_export_too_many_plugins');
	const wordLanguage = resolveInstructionLang(file.ddl, language);
	const names = plugins.map(({ definition }) => {
		const names = record(definition.names);
		const values = names?.[wordLanguage];
		const primary = Array.isArray(values) && typeof values[0] === 'string' ? values[0] : String(definition.heading ?? definition.id ?? '');
		return wordLanguage === 'ja' ? `｛${primary}｝` : `{${primary}}`;
	});
	return { ddl: file.ddl, plugins, names };
}

/** Migrate an older portable export before any DDL or definitions are applied. */
export async function importDdl(text: string, language: 'ja' | 'en', apiFetch?: ApiFetch): Promise<DdlImport & { edits: number | null }> {
	const parsed = parseDdlImport(text, language);
	let file: Record<string, unknown> | null = null;
	try { file = record(JSON.parse(text)); } catch { /* Plain DDL needs no migration. */ }
	if (file?.schema !== DDL_EXPORT_SCHEMA) return { ...parsed, edits: null };
	if (file.saijiki === 'inku.saijiki.v3') return { ...parsed, edits: null };
	if ((Object.hasOwn(file, 'saijiki') && file.saijiki !== 'inku.saijiki.v2') || !apiFetch) throw new Error('ddl_export_invalid');
	const response = await apiFetch('/api/ddl-export/migrate-v2', {
		method: 'POST', headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify({ ddl: parsed.ddl, language: file.language === 'en' ? 'en' : 'ja', plugins: parsed.plugins })
	});
	if (!response.ok) throw new Error('ddl_export_invalid');
	const migrated = await response.json();
	if (typeof migrated.ddl !== 'string' || !Array.isArray(migrated.plugins) || !Number.isSafeInteger(migrated.edits) || migrated.edits < 0) throw new Error('ddl_export_invalid');
	const normalized = parseDdlImport(JSON.stringify({ schema: DDL_EXPORT_SCHEMA, ddl: migrated.ddl, plugins: migrated.plugins }), language);
	return { ...normalized, edits: migrated.edits };
}
