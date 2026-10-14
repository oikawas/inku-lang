import { getLang, t } from '$lib/i18n/index.svelte';
import { colorCatalogOverride } from '$lib/features/color-catalog/render';
import { renderSettingsPayload, type RenderOverrides } from '$lib/features/render-payload';
import { wildOverride } from '$lib/features/wild/render';
import { normalizeCanvasAspectId, type CanvasAspectId } from '$lib/plugins/system/canvas-aspect';
import type { HistoryItem } from '$lib/historyManagerState.svelte';
import { projectHistoryCurrentWork } from '$lib/features/history/current-work';
import type { SaveHistoryOptions } from '$lib/features/history/save';
import type { PaintResult, PaintOptions } from '$lib/features/run/current-work';
import type { WorkState } from '$lib/features/work/state.svelte';
import { RefinementSessionState, type RefineKind, type VariationCandidate } from '$lib/features/canvas/refinement-session.svelte';
import { saveRefinementCandidates } from '$lib/features/canvas/refinement-actions';
import { otherCatalogIds, planRefinementCandidates, runRefinementFanout } from '$lib/features/canvas/refinement-fanout';
import { layoutCandidateResult, requestLayoutComposition, type ComposeLayoutGeneration, type RecomposeMode, type LayoutComposeResponse } from './recomposition.ts';

type Iteration = HistoryItem;
type RefinementWork = Pick<WorkState,
	'confirmFallbackRefine' | 'currentRefineParent' | 'ddl' | 'displayedHistoryItem' |
	'input' | 'instructionLang' | 'loading' | 'paintOne' | 'paintTokensIn' | 'paintTokensOut' |
	'result' | 'pipelineCompatibilityError' | 'sketchTextFor' | 'thinking'
>;

export type RefinementCoordinatorDeps = {
	apiFetch: (path: string, init?: RequestInit) => Promise<Response>;
	apiError: (response: Response) => Promise<Error>;
	work: RefinementWork;
	session: RefinementSessionState;
	history: {
		syncToItem: (item: Iteration) => Promise<unknown>;
	};
	models: {
		stage1: () => string;
		stage2: () => string;
		/** The name a model's option is labelled with, provider included. */
		label: (model: string) => string;
		/** The model's own name, without the provider, for its lane under the mascot. */
		shortLabel: (model: string) => string;
	};
	catalog: {
		defaultId: () => string;
		effectiveId: () => string;
		available: () => Array<{ id: string; }>;
		name: (id: string | null | undefined) => string;
	};
	render: {
		canvasAspectId: () => CanvasAspectId;
		wild: () => boolean;
		fanoutLimit: () => number;
	};
	seeds: {
		composition: (excluded?: Set<number>) => number;
	};
	lineageParentId: () => string | null;
	ensureVisibleLineageParentId: () => Promise<string | null>;
	pushHistory: (item: Iteration, options?: SaveHistoryOptions) => Promise<Iteration | null>;
	resetTargetScopedState: (options?: { preserveVariationCandidates?: boolean; }) => void;
};

export function createRefinementCoordinator(deps: RefinementCoordinatorDeps) {
	const { apiFetch, apiError, work, session: refinementSession } = deps;
	let targetIdentityVersion = 0;
	// Keep each saved work's next page even when its dialog is closed and reopened.
	const colorArrangementCursors = new Map<string, number | null>();

	function resetTarget(options: { preserveVariationCandidates?: boolean; } = {}): void {
		targetIdentityVersion += 1;
		refinementSession.reset({ preserveCandidates: options.preserveVariationCandidates });
	}

	function composeCandidateResult(thinking: string | null, data: LayoutComposeResponse & { ddl: string; thinking?: string | null; }): PaintResult & { ddl: string; thinking: string | null; } {
		return {
			...data,
			ddl: data.ddl,
			thinking: data.thinking ?? thinking,
			stage1_model: work.result?.stage1_model ?? deps.models.stage1(),
			stage2_model: data.stage2_model ?? deps.models.stage2(),
			elapsed_stage1_ms: 0,
			elapsed_stage2_ms: data.elapsed_ms ?? 0,
			elapsed_total_ms: data.elapsed_ms ?? 0,
			tokens_in_stage1: null,
			tokens_out_stage1: null,
			tokens_in_stage2: data.tokens_in ?? null,
			tokens_out_stage2: data.tokens_out ?? null,
			user_generation_count: null,
		};
	}

	function refinementCatalogId(): string {
		return work.result?.render_color_catalog_id ?? work.displayedHistoryItem?.catalog_id ?? deps.catalog.defaultId();
	}

	// The saved work a redraw is a redraw OF. The server reads that work's own
	// recorded colors, so a catalog definition that has since changed, been
	// renamed, or been retired no longer repaints it. The catalog id keeps being
	// sent alongside -- it is the nameplate, and only the colors moved.
	//
	// Null means there is no saved work yet: an unsaved result was just drawn
	// from today's definition, so today's definition is the one it remembers.
	function refinementWorkId(): string | null {
		return work.result?.history_id ?? work.displayedHistoryItem?.id ?? null;
	}

	// The words, instructions, sketch and thinking of the work being refined.
	// Opening a saved work for refinement keeps an unfinished draft in the left
	// pane, so the pane is the target only for a result not yet in the history.
	function refinementTarget(): { source: string; ddl: string; thinking: string | null; sketchText: string | null; } {
		const shown = work.displayedHistoryItem;
		if (shown?.id && shown.id === refinementWorkId()) {
			const saved = projectHistoryCurrentWork(shown);
			return { source: saved.sourceText.trim(), ddl: saved.ddl, thinking: saved.thinking, sketchText: saved.sketchText };
		}
		const source = work.input.trim();
		return { source, ddl: work.ddl ?? '', thinking: work.thinking, sketchText: work.sketchTextFor(source) };
	}

	function workReferencePayload(workId: string | null | undefined): Record<string, string> {
		return workId ? { work_id: workId } : {};
	}

	// A refinement redraws against the artwork it refines: its catalog, the level
	// the author chose for this round, and the switch the artwork was drawn with.
	function refinementRenderOverrides(): RenderOverrides {
		return {
			...colorCatalogOverride(refinementCatalogId()),
			...wildOverride(deps.render.wild())
		};
	}

	function refinementCanvasAspectId(): CanvasAspectId {
		return normalizeCanvasAspectId(work.result?.render_canvas_aspect_id ?? work.result?.render_canvas_aspect ?? work.result?.score?.canvas ?? deps.render.canvasAspectId());
	}

	async function composeVariationCandidate(compositionSeed: number, label: string, signal: AbortSignal, mode: RecomposeMode): Promise<VariationCandidate> {
		const target = refinementTarget();
		const baseDdl = target.ddl;
		const data = await requestLayoutComposition({
				ddl: baseDdl,
				description: target.source,
				...(target.sketchText ? { sketch_text: target.sketchText } : {}),
				model: deps.models.stage2(),
				instruction_lang: work.instructionLang,
				ui_lang: getLang(),
				canvas_aspect: refinementCanvasAspectId(),
				composition_seed: compositionSeed,
				// The server forks the candidate from this saved work, with its
				// saved settings and seeds; an unsaved result starts afresh.
				...workReferencePayload(refinementWorkId()),
				...renderSettingsPayload('compose', refinementRenderOverrides()),
				...(deps.lineageParentId() ? { lineage_parent_node_id: deps.lineageParentId() } : {}),
		}, mode, signal, apiFetch, work.pipelineCompatibilityError);
		const layout = layoutCandidateResult(data, baseDdl, compositionSeed, mode);
		return { id: `comp-${compositionSeed}`, kind: 'layout', label, selected: false, result: { ...composeCandidateResult(target.thinking, layout), lineage_parent_node_id: deps.lineageParentId(), derivation_kind: deps.lineageParentId() ? 'layout_change' : null, derivation_metadata: layout.derivation_metadata } };
	}

	const composeLayoutGeneration: ComposeLayoutGeneration = async (parent, source, options: PaintOptions) => {
		const seed = deps.seeds.composition(new Set([Number(parent.compositionSeed ?? parent.renderSeed)]));
		const data = await requestLayoutComposition({
			ddl: parent.ddl,
			description: source,
			...(options.sketchText ? { sketch_text: options.sketchText } : {}),
			model: options.stage2Model ?? deps.models.stage2(),
			instruction_lang: parent.instructionLang ?? work.instructionLang,
			ui_lang: getLang(),
			canvas_aspect: normalizeCanvasAspectId(parent.canvasAspectId ?? deps.render.canvasAspectId()),
			render_seed: parent.renderSeed,
			composition_seed: seed,
			...workReferencePayload(parent.id),
			...renderSettingsPayload('compose', options.renderOverrides),
			...(options.lineageParentNodeId ? { lineage_parent_node_id: options.lineageParentNodeId } : {}),
		}, 'principled', options.signal, apiFetch, work.pipelineCompatibilityError);
		const layout = layoutCandidateResult(data, parent.ddl, seed, 'principled');
		const result = {
			...composeCandidateResult(work.thinking, layout),
			stage1_model: parent.stage1Model,
			lineage_parent_node_id: options.lineageParentNodeId ?? null,
			derivation_kind: 'layout_change' as const,
			derivation_metadata: { ...options.derivationMetadata, ...layout.derivation_metadata },
			source_text: source
		};
		const saved = await deps.pushHistory({
			...result, input: source, at: Date.now(),
			ddl_source_origin: parent.ddlSourceOrigin,
			elapsed_ms: result.elapsed_total_ms,
			tokens_in: result.tokens_in_stage2,
			tokens_out: result.tokens_out_stage2,
			catalog_id: result.render_color_catalog_id ?? parent.catalogId ?? deps.catalog.defaultId()
		}, {
			countGeneration: options.countGeneration,
			sourceText: source,
			historyVisibility: options.historyVisibility,
			lineageParentNodeId: result.lineage_parent_node_id,
			derivationKind: 'layout_change',
			derivationMetadata: result.derivation_metadata
		});
		if (!saved?.id) throw new Error(t().pipelineAttentionReason('host_commit_failed'));
		return { ...result, history_id: saved.id, history_at: saved.at, lineage_node_id: saved.lineage_node_id };
	};

	async function renderColorCatalogCandidate(catalogId: string, label: string, signal?: AbortSignal): Promise<VariationCandidate> {
		if (!work.result) throw new Error("missing result");
		const target = refinementTarget();
		const fromCatalogId = refinementCatalogId();
		const r = await apiFetch("/api/render-score", {
			method: "POST",
			signal,
			headers: { "Content-Type": "application/json" },
			body: JSON.stringify({
				score: work.result.score,
				input: target.source,
				ddl: target.ddl,
				canvas_aspect: refinementCanvasAspectId(),
				render_seed: work.result.render_seed,
				composition_seed: work.result.composition_seed,
				interpretation_seed: work.result.interpretation_seed,
				...renderSettingsPayload('render-score', colorCatalogOverride(catalogId)),
			}),
		});
		if (!r.ok) throw await apiError(r);
		const data = await r.json() as Partial<PaintResult> & Pick<PaintResult, "svg" | "score">;
		return {
			id: "catalog-" + catalogId + "-" + label,
			label,
			selected: false,
			result: {
				...work.result,
				focus: undefined,
				variation_amplitude: undefined,
				variation_seed: undefined,
				recomposition: undefined,
				...data,
				ddl: target.ddl,
				thinking: target.thinking,
				history_id: null,
				history_at: null,
				lineage_node_id: null,
				lineage_parent_node_id: deps.lineageParentId(),
				derivation_kind: deps.lineageParentId() ? "catalog_change" : null,
				derivation_metadata: { catalog_id_from: fromCatalogId, catalog_id_to: catalogId },
			},
		};
	}

	// Four touch changes of the work (the author, 2026-10-14): every sentence on
	// one tool, or a tool drawn for each sentence. The Server draws the parent's
	// Score with only the tools changed and writes the tool words into the
	// instructions; a saved option is drawn again from the parent. The options
	// are added to those already made, so the two ways can be compared.
	async function generateToolCandidates(): Promise<void> {
		if (!work.result || refinementSession.gridBusy || work.loading) return;
		const parent = work.result;
		const workId = refinementWorkId();
		if (!workId) {
			refinementSession.setStatus(t().workActionSaveFirst);
			return;
		}
		const mode = refinementSession.toolMode;
		const contextVersion = targetIdentityVersion;
		await deps.ensureVisibleLineageParentId();
		if (contextVersion !== targetIdentityVersion || work.result !== parent || refinementSession.gridBusy) return;
		const parentNodeId = deps.lineageParentId();
		const { thinking } = refinementTarget();
		const ja = getLang() === 'ja';
		const earlier = refinementSession.candidates;
		const controller = refinementSession.beginGrid({ includesReading: false, taskLabel: t().workActionTool, count: 4 });
		const abortTimer = window.setTimeout(() => refinementSession.enableAbort(controller), 3000);
		try {
			const response = await apiFetch('/api/tool-variants/plan', {
				method: 'POST', signal: controller.signal, headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ work_id: workId, mode })
			});
			if (!response.ok) throw await apiError(response);
			type Change = { index: number; from: string; to: string };
			const plan = await response.json() as { tools: Record<string, { ja: string; en: string }>; entries: Array<{ tools: Record<string, string>; changes: Change[] }> };
			if (contextVersion !== targetIdentityVersion || !refinementSession.isActive(controller)) return;
			const word = (tool: string) => plan.tools[tool]?.[ja ? 'ja' : 'en'] ?? tool;
			const label = (entry: { changes: Change[] }, number: number) => mode === 'uniform'
				? word(entry.changes[0]?.to ?? '')
				: t().toolChangePerSentenceCandidate(number);
			if (plan.entries.length === 0) {
				refinementSession.setStatus(t().toolChangeNone);
				return;
			}
			refinementSession.gridTotal = plan.entries.length;
			refinementSession.setPlans(controller, plan.entries.map((entry, index) => label(entry, index + 1)));
			const stamp = Date.now();
			const candidates = await runRefinementFanout(plan.entries.map((entry, index) => async (): Promise<VariationCandidate> => {
				const rendered = await apiFetch('/api/render-tool-variant', {
					method: 'POST', signal: controller.signal, headers: { 'Content-Type': 'application/json' },
					body: JSON.stringify({ work_id: workId, mode, tools: entry.tools })
				});
				if (!rendered.ok) throw await apiError(rendered);
				const data = await rendered.json() as Partial<PaintResult> & Pick<PaintResult, 'svg' | 'score'> & { ddl: string };
				return {
					id: `tool-${workId}-${stamp}-${index}`, kind: 'color',
					label: label(entry, index + 1), selected: false,
					details: mode === 'uniform' ? [] : entry.changes.map((change) => `${change.index + 1}: ${word(change.from)} → ${word(change.to)}`),
					result: {
						...parent, ...data, thinking,
						focus: undefined, variation_amplitude: undefined, variation_seed: undefined, recomposition: undefined,
						history_id: null, history_at: null, lineage_node_id: null,
						lineage_parent_node_id: parentNodeId,
						derivation_kind: 'tool_change',
						derivation_metadata: { tool_mode: mode, tools: entry.tools }
					}
				};
			}), deps.render.fanoutLimit(), {
				onStart: (index) => refinementSession.seatSlot(controller, index, 'running'),
				onDone: (index) => { refinementSession.finishSlot(controller, index); }
			});
			refinementSession.commitCandidates(controller, [...earlier, ...candidates]);
		} catch (error) {
			if (!controller.signal.aborted) refinementSession.failGrid(controller, error instanceof Error ? error.message : String(error));
		} finally {
			window.clearTimeout(abortTimer);
			refinementSession.finishGrid(controller);
		}
	}

	function modelCandidateId(model: string): string {
		return `model-${model}`;
	}

	// The work drawn again from its description by another model, which draws
	// both stages. The render settings are the work's own, as for the other
	// options, so only the model differs.
	async function renderModelCandidate(model: string, label: string, signal: AbortSignal): Promise<VariationCandidate> {
		const target = refinementTarget();
		const source = target.source;
		const r = await work.paintOne(source, {
			historyInput: source,
			sourceText: source,
			saveHistory: false,
			saveArtifacts: false,
			countGeneration: false,
			canvasAspectId: refinementCanvasAspectId(),
			sketchText: target.sketchText,
			signal,
			renderOverrides: refinementRenderOverrides(),
			lineageParentNodeId: deps.lineageParentId(),
			stage1Model: model,
			stage2Model: model,
		});
		return {
			id: modelCandidateId(model),
			label,
			selected: false,
			result: {
				...r,
				lineage_parent_node_id: deps.lineageParentId(),
				derivation_kind: deps.lineageParentId() ? 'model_comparison' : null,
				derivation_metadata: { comparison_mode: 'common', compared_model: model, stage1_model: r.stage1_model ?? model, stage2_model: r.stage2_model ?? model },
			},
		};
	}

	/** The work in every other catalog; the color change dialog starts it on open. */
	async function generateColorCatalogCandidates() {
		const others = otherCatalogIds(deps.catalog.available().map((catalog) => catalog.id), refinementCatalogId());
		if (others.length === 0) {
			refinementSession.setStatus(t().refineNoAlternateCatalog);
			return;
		}
		await generateVariationCandidates('color', others.length);
	}

	async function generateColorArrangementCandidates(): Promise<void> {
		if (!work.result || refinementSession.gridBusy || work.loading) return;
		const parent = work.result;
		const workId = refinementWorkId();
		if (!workId) {
			refinementSession.setStatus(t().workActionSaveFirst);
			return;
		}
		const cursor = colorArrangementCursors.get(workId) ?? 0;
		if (colorArrangementCursors.has(workId) && colorArrangementCursors.get(workId) === null) {
			refinementSession.colorArrangementExhausted = true;
			refinementSession.setStatus(t().colorArrangementExhausted);
			return;
		}
		const contextVersion = targetIdentityVersion;
		await deps.ensureVisibleLineageParentId();
		if (contextVersion !== targetIdentityVersion || work.result !== parent || refinementSession.gridBusy) return;
		const parentNodeId = deps.lineageParentId();
		const { ddl, thinking } = refinementTarget();
		const controller = refinementSession.beginGrid({ includesReading: false, taskLabel: t().workActionColorArrangement, count: 8 });
		const abortTimer = window.setTimeout(() => refinementSession.enableAbort(controller), 3000);
		try {
			const response = await apiFetch('/api/color-arrangements/plan', {
				method: 'POST', signal: controller.signal, headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ work_id: workId, cursor })
			});
			if (!response.ok) throw await apiError(response);
			const plan = await response.json() as { entries: Array<{ index: number }>; next_cursor: number | null; total: number };
			if (contextVersion !== targetIdentityVersion || !refinementSession.isActive(controller)) return;
			// Reserve the whole page before rendering: stopped and failed options
			// are not silently redrawn when the author asks for the next page.
			colorArrangementCursors.set(workId, plan.next_cursor);
			refinementSession.colorArrangementExhausted = plan.next_cursor === null;
			refinementSession.gridTotal = plan.entries.length;
			refinementSession.setPlans(controller, plan.entries.map((entry) => t().colorArrangementCandidate(entry.index + 1)));
			if (plan.entries.length === 0) {
				refinementSession.setStatus(t().colorArrangementExhausted);
				return;
			}
			const candidates = await runRefinementFanout(plan.entries.map((entry) => async (): Promise<VariationCandidate> => {
				const rendered = await apiFetch('/api/render-color-arrangement', {
					method: 'POST', signal: controller.signal, headers: { 'Content-Type': 'application/json' },
					body: JSON.stringify({ work_id: workId, index: entry.index })
				});
				if (!rendered.ok) throw await apiError(rendered);
				const data = await rendered.json() as Partial<PaintResult> & Pick<PaintResult, 'svg' | 'score'>;
				return {
					id: `color-arrangement-${workId}-${entry.index}`, kind: 'color',
					label: t().colorArrangementCandidate(entry.index + 1), selected: false,
					result: {
						...parent, ...data, ddl, thinking,
						focus: undefined, variation_amplitude: undefined, variation_seed: undefined, recomposition: undefined,
						history_id: null, history_at: null, lineage_node_id: null,
						lineage_parent_node_id: parentNodeId,
						derivation_kind: 'color_arrangement_change',
						derivation_metadata: { color_arrangement_index: entry.index, catalog_id: data.render_color_catalog_id }
					}
				};
			}), deps.render.fanoutLimit(), {
				onStart: (index) => refinementSession.seatSlot(controller, index, 'running'),
				onDone: (index) => { refinementSession.finishSlot(controller, index); }
			});
			refinementSession.commitCandidates(controller, candidates);
		} catch (error) {
			if (!controller.signal.aborted) refinementSession.failGrid(controller, error instanceof Error ? error.message : String(error));
		} finally {
			window.clearTimeout(abortTimer);
			refinementSession.finishGrid(controller);
		}
	}

	// The work's ground swapped for every named support it is not on: six, or
	// all seven when it names none. The Server draws the parent's Score with only
	// the ground changed, and draws it again from the parent when one is saved.
	async function generateGroundCandidates(): Promise<void> {
		if (!work.result || refinementSession.gridBusy || work.loading) return;
		const parent = work.result;
		const workId = refinementWorkId();
		if (!workId) {
			refinementSession.setStatus(t().workActionSaveFirst);
			return;
		}
		const contextVersion = targetIdentityVersion;
		await deps.ensureVisibleLineageParentId();
		if (contextVersion !== targetIdentityVersion || work.result !== parent || refinementSession.gridBusy) return;
		const parentNodeId = deps.lineageParentId();
		const { thinking } = refinementTarget();
		const ja = getLang() === 'ja';
		const controller = refinementSession.beginGrid({ includesReading: false, taskLabel: t().workActionGround, count: 7 });
		const abortTimer = window.setTimeout(() => refinementSession.enableAbort(controller), 3000);
		try {
			const response = await apiFetch('/api/ground-variants/plan', {
				method: 'POST', signal: controller.signal, headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ work_id: workId })
			});
			if (!response.ok) throw await apiError(response);
			type Named = { label_ja?: string | null; label_en?: string | null; current_label_ja?: string | null; current_label_en?: string | null };
			const plan = await response.json() as Named & { entries: Array<Named & { material: string }> };
			if (contextVersion !== targetIdentityVersion || !refinementSession.isActive(controller)) return;
			refinementSession.groundCurrent = (ja ? plan.current_label_ja : plan.current_label_en) ?? t().groundChangePlain;
			const label = (entry: Named & { material: string }) => (ja ? entry.label_ja : entry.label_en) ?? entry.material;
			refinementSession.gridTotal = plan.entries.length;
			refinementSession.setPlans(controller, plan.entries.map(label));
			const candidates = await runRefinementFanout(plan.entries.map((entry) => async (): Promise<VariationCandidate> => {
				const rendered = await apiFetch('/api/render-ground-variant', {
					method: 'POST', signal: controller.signal, headers: { 'Content-Type': 'application/json' },
					body: JSON.stringify({ work_id: workId, material: entry.material })
				});
				if (!rendered.ok) throw await apiError(rendered);
				const data = await rendered.json() as Partial<PaintResult> & Pick<PaintResult, 'svg' | 'score'> & { ddl: string };
				return {
					id: `ground-${workId}-${entry.material}`, kind: 'color',
					label: label(entry), selected: false,
					result: {
						...parent, ...data, thinking,
						focus: undefined, variation_amplitude: undefined, variation_seed: undefined, recomposition: undefined,
						history_id: null, history_at: null, lineage_node_id: null,
						lineage_parent_node_id: parentNodeId,
						derivation_kind: 'ground_change',
						derivation_metadata: { ground_material: entry.material }
					}
				};
			}), deps.render.fanoutLimit(), {
				onStart: (index) => refinementSession.seatSlot(controller, index, 'running'),
				onDone: (index) => { refinementSession.finishSlot(controller, index); }
			});
			refinementSession.commitCandidates(controller, candidates);
		} catch (error) {
			if (!controller.signal.aborted) refinementSession.failGrid(controller, error instanceof Error ? error.message : String(error));
		} finally {
			window.clearTimeout(abortTimer);
			refinementSession.finishGrid(controller);
		}
	}

	async function generateVariationCandidates(kind: RefineKind, count: number) {
		if (!work.result || refinementSession.gridBusy || work.loading) return;
		// Every option in this round uses the choice made before any await.
		const recomposeMode = refinementSession.recomposeMode;
		const { source, ddl } = refinementTarget();
		// A layout draws the saved DDL, and a catalog change draws the saved
		// Score. Neither needs a description; the other kinds keep their guard.
		if (!source && kind !== 'color' && kind !== 'layout') {
			refinementSession.setStatus(t().refineNeedsDescription);
			return;
		}
		if (!ddl && kind !== 'color') {
			refinementSession.setStatus(t().refineNeedsDdl);
			return;
		}
		// Ask before the words are carried into a child (contract § stage 4).
		if (!(await work.confirmFallbackRefine(work.currentRefineParent()))) return;
		const contextVersion = targetIdentityVersion;
		await deps.ensureVisibleLineageParentId();
		if (contextVersion !== targetIdentityVersion) return;
		const taskLabel = kind === "layout" ? t().canvasVaryComposition : t().canvasVaryColor;
		const abortController = refinementSession.beginGrid({
			includesReading: false,
			taskLabel,
			count
		});
		const abortTimer = window.setTimeout(() => {
			refinementSession.enableAbort(abortController);
		}, 3000);
		try {
			const plans = await planRefinementCandidates({
				kind,
				count,
				signal: abortController.signal,
				labels: {
					layout: t().canvasVaryComposition,
					noAlternateCatalog: t().refineNoAlternateCatalog
				},
				currentCompositionSeed: work.result.composition_seed,
				previousCandidates: refinementSession.candidates,
				availableCatalogIds: deps.catalog.available().map((catalog) => catalog.id),
				currentCatalogId: refinementCatalogId()
			}, {
				createCompositionSeed: deps.seeds.composition,
				catalogName: deps.catalog.name,
				renderLayout: (seed, label, signal) => composeVariationCandidate(seed, label, signal, recomposeMode),
				renderColor: renderColorCatalogCandidate
			});
			refinementSession.setPlans(abortController, plans.map((plan) => plan.label));
			const candidates = await runRefinementFanout(plans.map((plan) => plan.run), deps.render.fanoutLimit(), {
				onStart: (index) => refinementSession.seatSlot(abortController, index, 'running'),
				onDone: (index) => { refinementSession.finishSlot(abortController, index); },
			});
			refinementSession.commitCandidates(abortController, candidates);
			for (const candidate of candidates) {
				refinementSession.addTokens(abortController, work.paintTokensIn(candidate.result), work.paintTokensOut(candidate.result));
			}
		} catch (e) {
			if (!(e instanceof DOMException && e.name === "AbortError")) {
				refinementSession.failGrid(abortController, e instanceof Error ? e.message : String(e));
			}
		} finally {
			window.clearTimeout(abortTimer);
			refinementSession.finishGrid(abortController);
		}
	}

	/**
	 * The work drawn by each picked model, as options beside the ones already
	 * drawn: a model that has drawn once is not drawn again. A model that fails
	 * leaves the others' options; the failures come back so the picker can
	 * mark them.
	 */
	async function generateModelCandidates(models: readonly string[]): Promise<Record<string, string>> {
		if (!work.result || refinementSession.gridBusy || work.loading) return {};
		const { source } = refinementTarget();
		if (!source) {
			refinementSession.setStatus(t().refineNeedsDescription);
			return {};
		}
		if (models.length === 0) {
			refinementSession.setStatus(t().modelCompareSelectPrompt);
			return {};
		}
		const drawn = new Set(refinementSession.candidates.map((candidate) => candidate.id));
		const pending = models.filter((model) => !drawn.has(modelCandidateId(model)));
		if (pending.length === 0) {
			refinementSession.setStatus(t().modelCompareAllRendered);
			return {};
		}
		const contextVersion = targetIdentityVersion;
		await deps.ensureVisibleLineageParentId();
		if (contextVersion !== targetIdentityVersion) return {};
		const labels = pending.map((model) => deps.models.label(model));
		const abortController = refinementSession.beginGrid({
			includesReading: true,
			taskLabel: t().workActionModels,
			count: pending.length
		});
		const abortTimer = window.setTimeout(() => {
			refinementSession.enableAbort(abortController);
		}, 3000);
		const failed: Record<string, string> = {};
		try {
			refinementSession.setPlans(abortController, pending.map((model) => deps.models.shortLabel(model)));
			const results = await runRefinementFanout(pending.map((model, index) => async () => {
				try {
					return await renderModelCandidate(model, labels[index], abortController.signal);
				} catch (e) {
					if (abortController.signal.aborted) throw e;
					failed[model] = e instanceof Error ? e.message : String(e);
					return null;
				}
			}), deps.render.fanoutLimit(), {
				onStart: (index) => refinementSession.seatSlot(abortController, index, 'running'),
				onDone: (index) => { refinementSession.finishSlot(abortController, index); },
			});
			const candidates = results.filter((candidate): candidate is VariationCandidate => candidate !== null);
			refinementSession.commitCandidates(abortController, [...refinementSession.candidates, ...candidates]);
			for (const candidate of candidates) {
				refinementSession.addTokens(abortController, work.paintTokensIn(candidate.result), work.paintTokensOut(candidate.result));
			}
			const failures = Object.keys(failed).length;
			if (failures > 0) refinementSession.failGrid(abortController, t().modelCompareFailedSummary(failures));
		} catch (e) {
			if (!(e instanceof DOMException && e.name === "AbortError")) {
				refinementSession.failGrid(abortController, e instanceof Error ? e.message : String(e));
			}
		} finally {
			window.clearTimeout(abortTimer);
			refinementSession.finishGrid(abortController);
		}
		return contextVersion === targetIdentityVersion ? failed : {};
	}

	/** True when every chosen option is now in the history. */
	async function saveSelectedVariationCandidates(): Promise<boolean> {
		const contextVersion = targetIdentityVersion;
		const selected = refinementSession.candidates.filter((candidate) => candidate.selected && !candidate.saved);
		if (selected.length === 0) {
			refinementSession.setStatus(t().variationGridEmpty);
			return false;
		}
		refinementSession.beginSave();
		try {
			const outcome = await saveRefinementCandidates({
				candidates: selected,
				sourceText: () => refinementTarget().source,
				fallbackCatalogId: () => deps.catalog.effectiveId()
			}, {
				saveHistory: deps.pushHistory,
				isCurrentContext: () => contextVersion === targetIdentityVersion,
				markSaved: (id) => refinementSession.markSaved(id),
				isCurrentResult: (candidateResult) => work.result === candidateResult,
				adoptSavedIdentity: (candidateResult, saved) => {
					work.result = { ...candidateResult, history_id: saved.id, history_at: saved.at, render_hash: saved.render_hash, render_hash_short: saved.render_hash_short, description_hash: saved.description_hash, lineage_node_id: saved.lineage_node_id };
					work.displayedHistoryItem = saved;
					void deps.history.syncToItem(saved);
				}
			});
			if (outcome === 'failed' && contextVersion === targetIdentityVersion) {
				refinementSession.setStatus(t().pipelineAttentionReason('host_commit_failed'));
			}
			return outcome === 'complete';
		} finally {
			if (contextVersion === targetIdentityVersion) refinementSession.finishSave();
		}
	}

	return {
		get contextVersion() { return targetIdentityVersion; },
		resetTarget,
		workReferencePayload,
		refinementCatalogId,
		refinementCanvasAspectId,
		generateVariationCandidates,
		composeLayoutGeneration,
		generateColorCatalogCandidates,
		generateColorArrangementCandidates,
		generateGroundCandidates,
		generateToolCandidates,
		generateModelCandidates,
		saveSelectedVariationCandidates,
	};
}
