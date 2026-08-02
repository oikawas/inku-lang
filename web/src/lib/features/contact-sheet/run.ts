/**
 * Building and saving a contact sheet, for whichever panel asked for one.
 *
 * The history manager had this inline. The lineage panel needs the same thing
 * over its own checked works, and a copy would be a copy that only gets fixed on
 * one side -- the page splitting, the note numbering that runs straight through
 * the split sheets, and the pause between programmatic downloads are all easy to
 * get subtly different. So the body lives here and both panels supply what only
 * they know: which ids are selected, how to resolve one to a work, and how to
 * name a catalog.
 */
import {
	buildContactSheet,
	sheetCapacity,
	sheetPageCount,
	type ContactSheetEntry,
	type SheetVariant,
} from '$lib/contactSheet';
import { buildContactSheetNotes, type ContactSheetNoteEntry } from '$lib/contactSheetNotes';
import { normalizeTenkei, tenkeiLabel } from '$lib/tenkei';

/** Only the fields the sheet and its notes read. */
export type ContactSheetWork = {
	id?: string;
	svg?: string;
	at: number;
	input?: string;
	source_text?: string | null;
	display_label?: string | null;
	ddl?: string | null;
	catalog_id?: string | null;
	tenkei?: string | null;
	stage1_model?: string | null;
	stage2_model?: string | null;
	render_hash?: string | null;
	render_hash_short?: string | null;
	render_build_number?: string | null;
	render_engine_id?: string | null;
	render_engine_version?: string | null;
	render_color_catalog_id?: string | null;
	render_color_catalog_name?: string | null;
	render_color_catalog_sub?: string | null;
	render_canvas_aspect?: string | null;
	render_canvas_aspect_id?: string | null;
	render_canvas_aspect_ratio?: number | null;
	variation_amplitude?: string | null;
	// The history item types this loosely; the notes only ever print it.
	variation_seed?: string | number | null;
};

export type ContactSheetDeps = {
	/** The works to place, in the order they should be numbered. */
	ids: () => string[];
	/** On-page lookup first, network second: the panel knows which is which. */
	resolveWork: (id: string) => ContactSheetWork | null | Promise<ContactSheetWork | null>;
	catalogName: (id: string | null | undefined) => string;
	formatDate: (at: number) => string;
	previewText: (text: string) => string;
	/** The single save path -- see features/export/save-target. */
	save: (blob: Blob, filename: string) => Promise<void>;
	labels: {
		title: string;
		subtitle: (total: number, date: string, page: number, pages: number) => string;
	};
};

export function noteEntryFor(work: ContactSheetWork, deps: ContactSheetDeps): ContactSheetNoteEntry {
	const catalog = work.render_color_catalog_name
		? work.render_color_catalog_sub
			? `${work.render_color_catalog_name} (${work.render_color_catalog_sub})`
			: work.render_color_catalog_name
		: deps.catalogName(work.render_color_catalog_id ?? work.catalog_id);
	const aspect = work.render_canvas_aspect ?? work.render_canvas_aspect_id ?? '';
	const ratio = work.render_canvas_aspect_ratio;
	const engineName = [work.render_engine_id, work.render_engine_version].filter(Boolean).join(' ');
	const level = normalizeTenkei(work.tenkei);
	const models = [work.stage1_model, work.stage2_model].filter(Boolean).join(' -> ');
	const variation = work.variation_amplitude
		? work.variation_seed == null
			? work.variation_amplitude
			: `${work.variation_amplitude} (seed ${work.variation_seed})`
		: '';
	return {
		description: work.source_text || work.input || '',
		staffage: level ? tenkeiLabel(level, false) : '',
		colorCatalog: catalog,
		canvas: aspect ? (ratio ? `${aspect} (${ratio.toFixed(3)})` : aspect) : '',
		engine: engineName
			? work.render_build_number
				? `${engineName} / build ${work.render_build_number}`
				: engineName
			: '',
		models,
		variation,
		renderHash: work.render_hash_short ?? work.render_hash ?? '',
		created: deps.formatDate(work.at),
		ddl: work.ddl,
	};
}

function timestamp(at: Date): string {
	return [
		at.getFullYear(),
		String(at.getMonth() + 1).padStart(2, '0'),
		String(at.getDate()).padStart(2, '0'),
		'-',
		String(at.getHours()).padStart(2, '0'),
		String(at.getMinutes()).padStart(2, '0'),
		String(at.getSeconds()).padStart(2, '0'),
	].join('');
}

/**
 * Build the sheets and save them. Throws when the selection holds no artwork,
 * so the caller can show its own error in its own place.
 */
export async function runContactSheet(variant: SheetVariant, deps: ContactSheetDeps): Promise<void> {
	const entries: ContactSheetEntry[] = [];
	const notes: ContactSheetNoteEntry[] = [];
	for (const id of deps.ids()) {
		const work = await deps.resolveWork(id);
		if (!work?.svg) continue;
		entries.push({
			svg: work.svg,
			caption: deps.previewText(work.display_label || work.source_text || work.input || ''),
			sub: deps.formatDate(work.at),
		});
		if (variant === 'ai') notes.push(noteEntryFor(work, deps));
	}
	if (entries.length === 0) throw new Error('no artworks to place on the sheet');

	const generatedAt = new Date();
	const stamp = timestamp(generatedAt);
	const capacity = sheetCapacity(variant);
	const pages = sheetPageCount(entries.length, variant);
	const kind = variant === 'ai' ? '-ai' : '';
	const sheetFiles: Array<{ name: string; from: number; to: number }> = [];

	for (let page = 0; page < pages; page += 1) {
		const startIndex = page * capacity;
		const slice = entries.slice(startIndex, startIndex + capacity);
		const blob = await buildContactSheet(slice, {
			variant,
			title: deps.labels.title,
			subtitle: deps.labels.subtitle(
				entries.length,
				deps.formatDate(generatedAt.getTime()),
				page + 1,
				pages,
			),
			startIndex,
		});
		const suffix = pages > 1 ? `-${String(page + 1).padStart(2, '0')}` : '';
		const filename = `inku-contact-sheet${kind}-${stamp}${suffix}.png`;
		sheetFiles.push({ name: filename, from: startIndex + 1, to: startIndex + slice.length });
		await deps.save(blob, filename);
		// Browsers drop back-to-back programmatic downloads; space them out.
		if (page < pages - 1) await new Promise((resolve) => setTimeout(resolve, 400));
	}

	// One notes file for the whole selection, numbered straight through the split
	// sheets, so the badges stay unambiguous across files.
	if (variant === 'ai' && notes.length > 0) {
		await new Promise((resolve) => setTimeout(resolve, 400));
		const markdown = buildContactSheetNotes(notes, {
			title: deps.labels.title,
			generatedAt: deps.formatDate(generatedAt.getTime()),
			sheets: sheetFiles,
		});
		await deps.save(
			new Blob([markdown], { type: 'text/markdown;charset=utf-8' }),
			`inku-contact-sheet-ai-${stamp}.md`,
		);
	}
}
