import type { DerivationKind } from '../../derivation.ts';
import type { HistoryItem } from '../../historyManagerState.svelte.ts';
import type { ApiFetch } from '../../transport/api-fetch.ts';

export type SaveHistoryOptions = {
	selectSaved?: boolean;
	countGeneration?: boolean;
	sourceText?: string;
	displayLabel?: string;
	batchLineNumber?: number;
	batchRunId?: string;
	historyVisibility?: 'normal' | 'lineage_only';
	lineageParentNodeId?: string | null;
	derivationKind?: DerivationKind | null;
	derivationMetadata?: Record<string, unknown>;
};

export type SaveHistoryDefaults = {
	catalogId: string;
	catalogMode: 'auto' | 'fixed';
	canvasAspectId: string;
	instructionLang: string;
	uiLang: string;
};

export type SaveHistoryDependencies = {
	apiFetch: ApiFetch;
	signedIn: () => boolean;
	ensureSvg: (item: HistoryItem) => Promise<string>;
	composeFallbackFor: (item: HistoryItem) => string | null;
	refreshCountedUser: () => Promise<void>;
	activeHistoryId: () => string | null;
	currentOffset: () => number;
	fetchOffset: (offset: number, options?: { anchorId?: string; preserveSelection?: boolean }) => Promise<boolean>;
	clearSelection: () => void;
};

/**
 * Persist one work and reconcile the history strip around the active identity.
 *
 * The caller supplies resolved browser preferences and named browsing
 * operations. This module owns the wire payload and post-save ordering without
 * acquiring route state or a second history manager.
 */
export async function saveHistoryItem(
	item: HistoryItem,
	options: SaveHistoryOptions,
	defaults: SaveHistoryDefaults,
	deps: SaveHistoryDependencies
): Promise<HistoryItem | null> {
	if (!deps.signedIn()) return null;

	// A listing item carries a thumbnail, not necessarily the drawing. Saving it
	// again must fetch the one full SVG before the copy is written.
	const svg = await deps.ensureSvg(item);
	// An absent compose record means “predates the field”, while an explicit
	// value records what the stage did. Never turn the former into `none`.
	const composeFallback = deps.composeFallbackFor(item);
	let saved: HistoryItem | null = null;
	try {
		const response = await deps.apiFetch('/api/history', {
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({
				input: item.input,
				ddl: item.ddl,
				expanded_ddl: item.expanded_ddl ?? null,
				focus: item.focus ?? null,
				score: item.score,
				svg,
				at: item.at,
				elapsed_ms: item.elapsed_ms ?? 0,
				stage1_model: item.stage1_model ?? null,
				stage2_model: item.stage2_model ?? null,
				tokens_in: item.tokens_in ?? null,
				tokens_out: item.tokens_out ?? null,
				catalog_id: item.catalog_id ?? defaults.catalogId,
				catalog_mode: item.catalog_mode ?? defaults.catalogMode,
				render_build_number: item.render_build_number ?? null,
				render_color_profile: item.render_color_profile ?? null,
				render_engine_id: item.render_engine_id ?? null,
				render_engine_version: item.render_engine_version ?? null,
				render_color_catalog_id: item.render_color_catalog_id ?? null,
				render_color_catalog_name: item.render_color_catalog_name ?? null,
				render_color_catalog_sub: item.render_color_catalog_sub ?? null,
				render_color_map: item.render_color_map ?? null,
				render_canvas_aspect: item.render_canvas_aspect ?? item.render_canvas_aspect_id ?? defaults.canvasAspectId,
				render_canvas_aspect_id: item.render_canvas_aspect_id ?? item.render_canvas_aspect ?? defaults.canvasAspectId,
				render_canvas_aspect_ratio: item.render_canvas_aspect_ratio ?? null,
				render_seed: item.render_seed == null ? null : Number(item.render_seed),
				composition_seed: item.composition_seed == null ? null : Number(item.composition_seed),
				interpretation_seed: item.interpretation_seed ?? null,
				variation_amplitude: item.variation_amplitude ?? null,
				variation_seed: item.variation_seed == null ? null : Number(item.variation_seed),
				save_artifacts: true,
				count_generation: options.countGeneration ?? false,
				canvas_aspect: item.render_canvas_aspect_id ?? item.render_canvas_aspect ?? defaults.canvasAspectId,
				instruction_lang_requested: item.instruction_lang_requested ?? defaults.instructionLang,
				instruction_lang_resolved: item.instruction_lang_resolved ?? null,
				ui_lang: item.ui_lang ?? defaults.uiLang,
				source_text: options.sourceText ?? item.source_text ?? item.input,
				display_label: options.displayLabel ?? item.display_label ?? null,
				batch_line_number: options.batchLineNumber ?? item.batch_line_number ?? null,
				batch_run_id: options.batchRunId ?? item.batch_run_id ?? null,
				history_visibility: options.historyVisibility ?? 'normal',
				lineage_parent_node_id: options.lineageParentNodeId ?? null,
				derivation_kind: options.derivationKind ?? null,
				derivation_metadata: options.derivationMetadata ?? {},
				sketch_text: item.sketch_text ?? null,
				sketch_grain: item.sketch_grain ?? null,
				...(item.sketch_state ? { sketch_state: item.sketch_state } : {}),
				...(composeFallback === null ? {} : { compose_fallback: composeFallback })
			})
		});
		if (response.ok) saved = await response.json() as HistoryItem;
	} catch {
		// Preserve the existing best-effort save contract. Callers reconcile the
		// listing even when the transport failed and receive null for the save.
	}

	if (options.countGeneration) await deps.refreshCountedUser();
	if (options.selectSaved && saved?.id && options.historyVisibility !== 'lineage_only') {
		await deps.fetchOffset(0, { anchorId: saved.id });
		return saved;
	}
	const activeId = deps.activeHistoryId();
	if (activeId) await deps.fetchOffset(0, { anchorId: activeId });
	else {
		await deps.fetchOffset(deps.currentOffset(), { preserveSelection: true });
		deps.clearSelection();
	}
	return saved;
}
