import type { CanvasAspectId } from '$lib/plugins/system/canvas-aspect';
import type { PaintResult } from '$lib/features/run/current-work';
import type { ApiFetch } from '$lib/transport/api-fetch';
import type { PipelineDiagnostic, PipelineHistoryDiagnostics, PluginDiagnostic } from './diagnostics';
import type { ImportedPlugin } from '../ddl-editor/ddl-import';

export type PipelineAuthority = {
	revision: string;
	origin: string;
	authority: 'description_authoritative' | 'ddl_authoritative';
};

export type PipelinePhase = {
	tag: string;
	reason?: string;
	candidate?: { source: string };
	proposal_digest?: string;
};

export type PipelineResult = PaintResult & {
	ddl?: string | null;
	thinking?: string | null;
	render_diagnostics?: Record<string, unknown> | null;
	resource_execution?: Record<string, unknown> | null;
	pipeline_diagnostics?: { plugin_diagnostics?: PluginDiagnostic[] } | null;
};

/**
 * The model call a running execution is waiting on. The shared core numbers
 * the attempt and sets its budget; the server adds the deadline once it has
 * begun the attempt.
 */
export type PipelineProviderAttempt = {
	action: string;
	/** One-based. */
	attempt: number;
	max_attempts: number;
	delay_ms?: string;
	timeout_ms?: string;
	/** Epoch ms when the attempt gives up. */
	deadline_at?: number;
};

export type PipelineView = {
	execution_id: string;
	variation_id: string;
	sequence?: string;
	authority: PipelineAuthority;
	description: string;
	catalog_diagnostics?: unknown[];
	document: { source: string; language: string } | null;
	phase: PipelinePhase;
	delivery: {
		score: unknown;
		upstream_diagnostics: unknown[];
		downstream_diagnostics: unknown[];
		resource_omissions: unknown[];
		relation_omissions: unknown[];
	} | null;
	busy: boolean;
	provider_attempt?: PipelineProviderAttempt;
	/** The last model-call failure, kept so a failed stage can say what happened. */
	provider_failure?: { failure: string; stage: string; attempt: number; elapsed_ms?: number; detail?: string };
	rendered: { svg: string } | null;
	result: PipelineResult | null;
};

export type PipelineOptions = {
	imported_plugins?: ImportedPlugin[];
	sketch?: 'off' | 'on';
	sketch_text?: string;
	stage1_model?: string;
	stage2_model?: string;
	instruction_lang?: string;
	ui_lang?: string;
	catalog_id?: string;
	catalog_mode?: string;
	canvas_aspect?: CanvasAspectId;
	render_seed?: number;
	composition_seed?: number;
	wild?: boolean;
	variation_amplitude?: string;
	variation_seed?: number;
	interpretation_seed?: string;
	seed_text?: string;
	history_display_label?: string;
	batch_line_number?: number;
	batch_run_id?: string;
	history_visibility?: 'normal' | 'lineage_only';
	lineage_parent_node_id?: string;
	derivation_kind?: string;
	derivation_metadata?: Record<string, unknown>;
	count_generation?: boolean;
};

export type PipelineErrorDetail = {
	code: string;
	message?: string;
	current_revision?: string;
	current_view?: PipelineView;
};

export function pipelineViewFromErrorDetail(detail: unknown): PipelineView | null {
	if (!detail || typeof detail !== 'object' || !('current_view' in detail)) return null;
	const view = (detail as { current_view?: unknown }).current_view;
	if (!view || typeof view !== 'object') return null;
	return view as PipelineView;
}

export class PipelineApiError extends Error {
	readonly status: number;
	readonly detail: PipelineErrorDetail;

	constructor(status: number, detail: PipelineErrorDetail) {
		super(detail.message ?? detail.code);
		this.name = 'PipelineApiError';
		this.status = status;
		this.detail = detail;
	}
}

type VariationKind = 'description' | 'direct_ddl';

export class PipelineApi {
	private readonly apiFetch: ApiFetch;
	private readonly base: string;

	constructor(apiFetch: ApiFetch, base = '/api/pipeline') {
		this.apiFetch = apiFetch;
		this.base = base;
	}

	private async request<T>(path: string, body?: unknown, signal?: AbortSignal): Promise<T> {
		const response = await this.apiFetch(this.base + path, {
			method: body === undefined ? 'GET' : 'POST',
			signal,
			headers: body === undefined ? {} : { 'Content-Type': 'application/json' },
			body: body === undefined ? undefined : JSON.stringify(body),
		});
		if (!response.ok) {
			const payload = await response.json().catch(() => ({})) as { detail?: string | PipelineErrorDetail };
			const detail = typeof payload.detail === 'string'
				? { code: payload.detail }
				: payload.detail ?? { code: `http_${response.status}` };
			throw new PipelineApiError(response.status, detail);
		}
		return response.json() as Promise<T>;
	}

	start(kind: VariationKind, text: string, options: PipelineOptions, signal?: AbortSignal) {
		return this.request<PipelineView>('/variations', {
			kind,
			text,
			canvas_format_id: options.canvas_aspect,
			options,
		}, signal);
	}

	load(variationId: string, signal?: AbortSignal) {
		return this.request<PipelineView>(`/variations/${encodeURIComponent(variationId)}`, undefined, signal);
	}

	historyLink(historyId: string, signal?: AbortSignal) {
		return this.request<{ variation_id: string; revision: string }>(
			`/history/${encodeURIComponent(historyId)}`,
			undefined,
			signal,
		);
	}

	forkLegacy(historyId: string, kind: VariationKind, text: string, options: PipelineOptions, signal?: AbortSignal) {
		return this.request<PipelineView>(`/legacy/${encodeURIComponent(historyId)}/fork`, {
			kind,
			text,
			canvas_format_id: options.canvas_aspect,
			options,
		}, signal);
	}

	forkHistory(historyId: string, kind: VariationKind, text: string, options: PipelineOptions, signal?: AbortSignal) {
		return this.request<PipelineView>(`/history/${encodeURIComponent(historyId)}/fork`, {
			kind,
			text,
			options,
		}, signal);
	}

	forkDescription(view: PipelineView, description: string, options: PipelineOptions, signal?: AbortSignal) {
		return this.request<PipelineView>(`/variations/${encodeURIComponent(view.variation_id)}/fork-description`, {
			expected_revision: view.authority.revision,
			description,
			options,
		}, signal);
	}

	authorDdl(view: PipelineView, source: string, options: PipelineOptions, signal?: AbortSignal) {
		return this.request<PipelineView>(`/executions/${encodeURIComponent(view.execution_id)}/author-ddl`, {
			source,
			expected_revision: view.authority.revision,
			options,
		}, signal);
	}

	command(view: PipelineView, command: Record<string, unknown>, signal?: AbortSignal) {
		return this.request<PipelineView>(`/executions/${encodeURIComponent(view.execution_id)}/commands`, command, signal);
	}
}

export function pipelineDiagnostics(
	view: PipelineView | null,
	saved: PipelineHistoryDiagnostics | null | undefined = null,
): PipelineDiagnostic[] {
	const catalog = (view?.catalog_diagnostics ?? []).map((value) => ({ channel: 'catalog' as const, value }));
	const delivery = view ? view.delivery : saved;
	const renderDiagnostics = view ? view.result?.render_diagnostics : saved?.render_diagnostics;
	const resourceExecution = view ? view.result?.resource_execution : saved?.resource_execution;
	const recordArray = (record: Record<string, unknown> | null | undefined, field: string): unknown[] => {
		const value = record?.[field];
		return Array.isArray(value) ? value : [];
	};
	const plugins = (view ? view.result?.pipeline_diagnostics?.plugin_diagnostics : saved?.plugin_diagnostics) ?? [];
	// A plugin sentence's explanation replaces the compiler's generic entry for the same source range.
	const explained = (value: unknown) => {
		const span = (value as { span?: { start_byte?: unknown; end_byte?: unknown } } | null)?.span;
		return plugins.some((plugin) => plugin.start_byte === span?.start_byte && plugin.end_byte === span?.end_byte);
	};
	return [
		...plugins.map((value) => ({ channel: 'plugin' as const, value })),
		...catalog,
		...(delivery?.upstream_diagnostics ?? []).filter((value) => !explained(value)).map((value) => ({ channel: 'upstream' as const, value })),
		...(delivery?.downstream_diagnostics ?? []).map((value) => ({ channel: 'downstream' as const, value })),
		...(delivery?.resource_omissions ?? []).map((value) => ({ channel: 'resource' as const, value })),
		...(delivery?.relation_omissions ?? []).map((value) => ({ channel: 'relation' as const, value })),
		...recordArray(renderDiagnostics, 'diagnostics').map((value) => ({ channel: 'render' as const, value })),
		...recordArray(resourceExecution, 'omissions').map((value) => ({ channel: 'resource' as const, value })),
		...recordArray(resourceExecution, 'relation_omissions').map((value) => ({ channel: 'relation' as const, value })),
	];
}

export function pipelinePatch(view: PipelineView | null): PipelinePhase | null {
	return view?.phase.tag === 'awaiting_patch_approval' ? view.phase : null;
}
