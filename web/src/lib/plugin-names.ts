/** A plugin's visible names and insertion spellings from the Server. */
export type PluginNameEntry = {
	qualified_name: string;
	surface_ja?: string[];
	surface_en?: string[];
	written_ja?: string;
	written_en?: string;
};

export function pluginDisplayName(entry: PluginNameEntry, lang: 'ja' | 'en'): string {
	const written = lang === 'ja' ? entry.written_ja : entry.written_en;
	if (written) return written;
	const primary = (lang === 'ja' ? entry.surface_ja : entry.surface_en)?.[0];
	return primary ? (lang === 'ja' ? `｛${primary}｝` : `{${primary}}`) : entry.qualified_name;
}
