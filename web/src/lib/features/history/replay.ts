import type { HistoryItem } from '../../historyManagerState.svelte.ts';
import type { ApiFetch } from '../../transport/api-fetch.ts';
import type { SaveHistoryOptions } from './save.ts';

export type ReplaySource = 'history-manager' | 'canvas' | 'refine' | 'lineage';

export type ReplayComparison = {
	source: ReplaySource;
	originalSvg: string;
	replayedSvg: string;
	recordedVersion: string | null;
	currentVersion: string | null;
	versionMessage: string | null;
	provisionalSeed: number | null;
	originalItem: HistoryItem;
	replayedItem: HistoryItem;
	renderHash: string | null;
	svgSha256: string | null;
	saveKey: string;
	saving: boolean;
	savedItem: HistoryItem | null;
	saveError: string | null;
};

export type ReplayHistoryDefaults = {
	effectiveCatalogId: string;
	effectiveCanvasAspectId: string;
	currentRenderEngineVersion: string | null;
	renderPayload: (item: HistoryItem, catalogId: string) => Record<string, unknown>;
	versionMismatchMessage: (recorded: string, current: string) => string;
	versionNotRecordedMessage: (current: string) => string;
};

export type ReplayHistoryDependencies = {
	apiFetch: ApiFetch;
	apiError: (response: Response) => Promise<Error>;
	ensureSvg: (item: HistoryItem) => Promise<string>;
	acceptRendered?: () => boolean;
};

/** Render a saved work again and return the comparison modal's typed input. */
export async function replayHistoryItem(
	item: HistoryItem,
	source: ReplaySource,
	defaults: ReplayHistoryDefaults,
	deps: ReplayHistoryDependencies
): Promise<ReplayComparison | null> {
	const hasRecordedSeed = item.render_seed != null;
	const hasSeedText = Boolean(item.seed_text?.trim());
	const provisionalSeed = !hasRecordedSeed && !hasSeedText ? 0 : null;
	const replaySeed = hasRecordedSeed ? item.render_seed : provisionalSeed;
	const catalogId = item.render_color_catalog_id ?? item.catalog_id ?? defaults.effectiveCatalogId;
	const canvasId = item.render_canvas_aspect_id
		?? item.render_canvas_aspect
		?? item.score?.canvas
		?? defaults.effectiveCanvasAspectId;

	const response = await deps.apiFetch('/api/render-score', {
		method: 'POST',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify({
			input: item.input,
			ddl: item.ddl,
			score: item.score,
			canvas_aspect: canvasId,
			render_seed: replaySeed,
			// Keep the recorded placement seed raw. The renderer already falls
			// back to the performance seed when this value is absent; substituting
			// here would make engine differences include an invented placement.
			composition_seed: item.composition_seed ?? null,
			interpretation_seed: item.interpretation_seed ?? null,
			seed_text: hasSeedText ? item.seed_text : null,
			...defaults.renderPayload(item, catalogId)
		})
	});
	if (!response.ok) throw await deps.apiError(response);
	const rendered = await response.json() as Partial<HistoryItem> & { svg: string; svg_sha256?: string };
	const replayedSvg = rendered.svg;
	// Match the route's established stale boundary: decide after rendering but
	// before a lazy original-SVG fetch can outlive the selected canvas target.
	if (deps.acceptRendered && !deps.acceptRendered()) return null;
	const currentVersion = rendered.render_engine_version ?? defaults.currentRenderEngineVersion;
	const recordedVersion = item.render_engine_version ?? null;
	const versionMessage = currentVersion
		? recordedVersion
			? recordedVersion === currentVersion
				? null
				: defaults.versionMismatchMessage(recordedVersion, currentVersion)
			: defaults.versionNotRecordedMessage(currentVersion)
		: null;

	return {
		source,
		originalSvg: await deps.ensureSvg(item),
		replayedSvg,
		recordedVersion,
		currentVersion,
		versionMessage,
		provisionalSeed,
		originalItem: { ...item },
		replayedItem: {
			...item, ...rendered,
			id: undefined, at: Date.now(), svg: replayedSvg,
			lineage_node_id: null, lineage_root_node_id: null,
			lineage_parent_node_id: item.lineage_node_id ?? null,
			pipeline_variation_id: null, pipeline_revision: null,
			derivation_kind: 'replay', derivation_metadata: {},
		},
		renderHash: rendered.render_hash ?? null,
		svgSha256: rendered.svg_sha256 ?? null,
		saveKey: typeof globalThis.crypto?.randomUUID === 'function'
			? globalThis.crypto.randomUUID()
			: `replay-${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`,
		saving: false, savedItem: null, saveError: null,
	};
}

/** Save the displayed performance once, retaining its key for safe retries. */
export async function saveReplayComparison(
	comparison: ReplayComparison,
	pushHistory: (item: HistoryItem, options: SaveHistoryOptions) => Promise<HistoryItem | null>,
	failureMessage: string,
): Promise<HistoryItem | null> {
	if (comparison.saving || comparison.savedItem) return comparison.savedItem;
	if (!comparison.originalItem.id || !comparison.originalItem.lineage_node_id || !comparison.renderHash || !comparison.svgSha256) {
		comparison.saveError = failureMessage;
		return null;
	}
	comparison.saving = true;
	comparison.saveError = null;
	try {
		const saved = await pushHistory(comparison.replayedItem, {
			countGeneration: false,
			historyVisibility: 'normal',
			lineageParentNodeId: comparison.originalItem.lineage_node_id,
			derivationKind: 'replay',
			replayWorkId: comparison.originalItem.id,
			replayRenderHash: comparison.renderHash,
			replaySvgSha256: comparison.svgSha256,
			idempotencyKey: comparison.saveKey,
			rejectOnFailure: true,
		});
		if (!saved) throw new Error(failureMessage);
		comparison.savedItem = saved;
		return saved;
	} catch (error) {
		comparison.saveError = error instanceof Error ? error.message : failureMessage;
		return null;
	} finally {
		comparison.saving = false;
	}
}
