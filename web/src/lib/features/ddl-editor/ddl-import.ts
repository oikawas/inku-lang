/** Reading a DDL file back into the editor.
 *
 * An `inku.ddl-export.v1` file carries the visible DDL and the plugin
 * definitions it names. The definitions travel with the next new work only and
 * are validated again by the server's shared boundary; this module does not
 * interpret them. Any other text is read as plain DDL without definitions.
 */

export const DDL_EXPORT_SCHEMA = 'inku.ddl-export.v1';
const MAX_IMPORTED_PLUGINS = 64;

export type ImportedPlugin = { definition: Record<string, unknown>; summary: string };

export type DdlImport = {
	ddl: string;
	plugins: ImportedPlugin[];
	/** Qualified names of the carried plugins, for the author-facing notice. */
	names: string[];
};

function record(value: unknown): Record<string, unknown> | null {
	return value !== null && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : null;
}

export function parseDdlImport(text: string): DdlImport {
	let parsed: unknown = null;
	try {
		parsed = JSON.parse(text);
	} catch {
		return { ddl: text, plugins: [], names: [] };
	}
	const file = record(parsed);
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
		plugins.push({ definition, summary: typeof plugin?.summary === 'string' ? plugin.summary : '' });
	}
	if (plugins.length > MAX_IMPORTED_PLUGINS) throw new Error('ddl_export_too_many_plugins');
	const names = plugins.map(({ definition }) => `${String(definition.namespace)}.${String(definition.heading)}`);
	return { ddl: file.ddl, plugins, names };
}
