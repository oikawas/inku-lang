import type { ContactSheetNoteEntry } from "../../contactSheetNotes.ts";

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
	stage1_model?: string | null;
	stage2_model?: string | null;
	render_hash?: string | null;
	render_hash_short?: string | null;
	render_build_number?: string | null;
	render_engine_id?: string | null;
	render_engine_version?: string | null;
	render_color_catalog_id?: string | null;
	render_color_catalog_name?: string | null;
	render_canvas_aspect?: string | null;
	render_canvas_aspect_id?: string | null;
	render_canvas_aspect_ratio?: number | null;
	variation_amplitude?: string | null;
	// The history item types this loosely; the notes only ever print it.
	variation_seed?: string | number | null;
};

export type ContactSheetNoteDeps = {
	catalogName: (id: string | null | undefined) => string;
	formatDate: (at: number) => string;
};

export function noteEntryFor(
	work: ContactSheetWork,
	deps: ContactSheetNoteDeps,
): ContactSheetNoteEntry {
	const catalog = work.render_color_catalog_name
		? work.render_color_catalog_name
		: deps.catalogName(work.render_color_catalog_id ?? work.catalog_id);
	const aspect = work.render_canvas_aspect ?? work.render_canvas_aspect_id ?? "";
	const ratio = work.render_canvas_aspect_ratio;
	const engineName = [work.render_engine_id, work.render_engine_version].filter(Boolean).join(" ");
	const models = [work.stage1_model, work.stage2_model].filter(Boolean).join(" -> ");
	const variation = work.variation_amplitude
		? work.variation_seed == null
			? work.variation_amplitude
			: `${work.variation_amplitude} (seed ${work.variation_seed})`
		: "";
	return {
		description: work.source_text || work.input || "",
		colorCatalog: catalog,
		canvas: aspect ? (ratio ? `${aspect} (${ratio.toFixed(3)})` : aspect) : "",
		engine: engineName
			? work.render_build_number
				? `${engineName} / build ${work.render_build_number}`
				: engineName
			: "",
		models,
		variation,
		renderHash: work.render_hash_short ?? work.render_hash ?? "",
		created: deps.formatDate(work.at),
		ddl: work.ddl,
	};
}
