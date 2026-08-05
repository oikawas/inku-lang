// Companion notes for the AI contact sheet.
//
// The sheet itself can only say "No.7"; it carries index badges instead of
// captions because captions are illegible after a vision model downscales the
// image. This file is the other half of that pair: it maps every badge number
// back to the description that was written, and to the machinery that performed
// it, so a model can judge the drawing against its intent rather than merely
// describe what it sees.
//
// Labels are English regardless of the UI language — the reader is a model, and
// stable keys matter more than localisation. The descriptions stay in whatever
// language they were written in.

export type ContactSheetNoteEntry = {
	// Written in full. The on-sheet caption is truncated; this is not.
	description: string;
	colorCatalog?: string | null;
	canvas?: string | null;
	engine?: string | null;
	models?: string | null;
	variation?: string | null;
	renderHash?: string | null;
	created?: string | null;
	ddl?: string | null;
};

export type ContactSheetNotesOptions = {
	title: string;
	generatedAt: string;
	// One entry per emitted PNG, in order, with the badge range it covers.
	sheets: Array<{ name: string; from: number; to: number }>;
};

// Values that are absent drop their whole line rather than printing a dash: a
// model reads "field: -" as a fact about the artwork, which it is not.
function field(lines: string[], key: string, value: string | null | undefined) {
	const text = (value ?? '').trim();
	if (!text) return;
	if (text.includes('\n')) {
		lines.push(`${key}:`);
		lines.push('```');
		lines.push(text);
		lines.push('```');
		return;
	}
	lines.push(`${key}: ${text}`);
}

export function buildContactSheetNotes(entries: ContactSheetNoteEntry[], options: ContactSheetNotesOptions): string {
	const lines: string[] = [];
	lines.push(`# ${options.title}`);
	lines.push('');
	lines.push(`generated: ${options.generatedAt}`);
	lines.push(`items: ${entries.length}`);
	for (const sheet of options.sheets) {
		const range = sheet.from === sheet.to ? `No.${sheet.from}` : `No.${sheet.from}-${sheet.to}`;
		lines.push(`sheet: ${sheet.name} (${range})`);
	}
	lines.push('');
	lines.push('Each numbered section below corresponds to the badge drawn on the artwork.');

	entries.forEach((entry, index) => {
		lines.push('');
		lines.push(`## No.${index + 1}`);
		field(lines, 'description', entry.description);
		field(lines, 'color catalog', entry.colorCatalog);
		field(lines, 'canvas', entry.canvas);
		field(lines, 'engine', entry.engine);
		field(lines, 'models', entry.models);
		field(lines, 'variation', entry.variation);
		field(lines, 'render hash', entry.renderHash);
		field(lines, 'created', entry.created);
		const ddl = (entry.ddl ?? '').trim();
		if (ddl) {
			lines.push('ddl:');
			lines.push('```');
			lines.push(ddl);
			lines.push('```');
		}
	});

	lines.push('');
	return lines.join('\n');
}
