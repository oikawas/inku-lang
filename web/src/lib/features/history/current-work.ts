import type { DerivationKind } from '../../derivation.ts';
import type { HistoryItem } from '../../historyManagerState.svelte.ts';
import type { PaintResult } from '../run/current-work.ts';

export type HistoryCurrentWorkProjection = {
	sourceText: string;
	ddl: string;
	expandedDdl: string | null;
	thinking: string | null;
	sketchText: string | null;
	sketchGrain: string | null | undefined;
	sketchState: string | null | undefined;
	result: PaintResult;
};

/** Map a persisted history item to the page's current drawing projection. */
export function projectHistoryCurrentWork(item: HistoryItem): HistoryCurrentWorkProjection {
	const sourceText = item.source_text ?? item.input;
	return {
		sourceText,
		ddl: item.ddl ?? '',
		expandedDdl: item.expanded_ddl ?? null,
		thinking: item.thinking ?? null,
		sketchText: item.sketch_text ?? null,
		sketchGrain: item.sketch_grain,
		sketchState: item.sketch_state,
		result: {
			score: item.score,
			svg: item.svg,
			stage1_model: item.stage1_model,
			stage2_model: item.stage2_model,
			render_build_number: item.render_build_number,
			render_color_profile: item.render_color_profile,
			render_engine_id: item.render_engine_id,
			render_engine_version: item.render_engine_version,
			ddl_version: item.ddl_version,
			ddl_engine_version: item.ddl_engine_version,
			render_color_catalog_id: item.render_color_catalog_id,
			render_color_catalog_name: item.render_color_catalog_name,
			render_color_catalog_sub: item.render_color_catalog_sub,
			render_color_map: item.render_color_map,
			render_canvas_aspect: item.render_canvas_aspect,
			render_canvas_aspect_id: item.render_canvas_aspect_id,
			render_canvas_aspect_ratio: item.render_canvas_aspect_ratio,
			instruction_lang_requested: item.instruction_lang_requested,
			instruction_lang_resolved: item.instruction_lang_resolved,
			ui_lang: item.ui_lang,
			seed_text: item.seed_text ?? null,
			render_hash: item.render_hash,
			render_hash_short: item.render_hash_short,
			description_hash: item.description_hash,
			lineage_node_id: item.lineage_node_id,
			lineage_parent_node_id: item.lineage_parent_node_id,
			derivation_kind: item.derivation_kind as DerivationKind | null | undefined,
			derivation_metadata: item.derivation_metadata,
			render_seed: item.render_seed == null ? null : Number(item.render_seed),
			composition_seed: item.composition_seed == null ? null : Number(item.composition_seed),
			interpretation_seed: item.interpretation_seed ?? null,
			variation_amplitude: item.variation_amplitude ?? null,
			variation_seed: item.variation_seed == null ? null : Number(item.variation_seed),
			elapsed_stage1_ms: 0,
			elapsed_stage2_ms: 0,
			elapsed_total_ms: item.elapsed_ms ?? 0,
			tokens_in_stage1: null,
			tokens_out_stage1: null,
			tokens_in_stage2: null,
			tokens_out_stage2: null
		}
	};
}
