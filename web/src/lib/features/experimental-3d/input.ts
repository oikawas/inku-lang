import type { PaintResult } from '$lib/features/run/current-work';

/** The experiment receives a snapshot, never application state or credentials. */
export function snapshot(result: PaintResult): string {
	const fields = ['score', 'render_seed', 'composition_seed', 'render_wild', 'render_canvas_aspect_id',
		'render_canvas_aspect_ratio', 'render_canvas_aspect', 'render_color_map', 'render_color_catalog_id',
		'render_engine_id', 'render_engine_version', 'render_build_number', 'ddl_version', 'ddl_engine_version'] as const;
	const projected: Record<string, unknown> = {};
	for (const key of fields) if (result[key] !== undefined && result[key] !== null) projected[key] = result[key];
	for (const key of ['render_seed', 'composition_seed']) {
		const seed = projected[key];
		if (typeof seed === 'number' && !Number.isSafeInteger(seed)) throw new Error('unsafe_numeric_seed');
	}
	const json = JSON.stringify(projected);
	if (new TextEncoder().encode(json).byteLength > 16 * 1024 * 1024) throw new Error('input_budget_exceeded');
	return json;
}

/** Build-time opt in, restricted to a versioned static directory on this origin. */
export function configuredViewer(value: unknown): string | null {
	return typeof value === 'string' && /^\/experimental\/ddl-3d\/[a-zA-Z0-9][a-zA-Z0-9._-]{0,63}\/index\.html$/.test(value)
		? value : null;
}
