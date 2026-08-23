import type { HistoryItem } from '../../historyManagerState.svelte.ts';
import type { ApiFetch } from '../../transport/api-fetch.ts';

export type ReplaySource = 'history-manager' | 'canvas' | 'refine' | 'lineage';

export type ReplayComparison = {
	source: ReplaySource;
	originalSvg: string;
	replayedSvg: string;
	recordedVersion: string | null;
	currentVersion: string | null;
	versionMessage: string | null;
	provisionalSeed: number | null;
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
	const replaySeed = hasRecordedSeed ? Number(item.render_seed) : provisionalSeed;
	const catalogId = item.render_color_catalog_id ?? item.catalog_id ?? defaults.effectiveCatalogId;
	const canvasId = item.render_canvas_aspect_id
		?? item.render_canvas_aspect
		?? item.score?.canvas
		?? defaults.effectiveCanvasAspectId;

	const response = await deps.apiFetch('/api/render-svg', {
		method: 'POST',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify({
			score: item.score,
			canvas_aspect: canvasId,
			render_seed: replaySeed,
			// Keep the recorded placement seed raw. The renderer already falls
			// back to the performance seed when this value is absent; substituting
			// here would make engine differences include an invented placement.
			composition_seed: item.composition_seed ?? null,
			seed_text: item.seed_text,
			...defaults.renderPayload(item, catalogId)
		})
	});
	if (!response.ok) throw await deps.apiError(response);
	const replayedSvg = await response.text();
	// Match the route's established stale boundary: decide after rendering but
	// before a lazy original-SVG fetch can outlive the selected canvas target.
	if (deps.acceptRendered && !deps.acceptRendered()) return null;
	const currentVersion = defaults.currentRenderEngineVersion;
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
		provisionalSeed
	};
}
