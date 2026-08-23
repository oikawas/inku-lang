import { getLang, t } from '$lib/i18n/index.svelte';
import { colorCatalogOverride } from '$lib/features/color-catalog/render';
import { renderSettingsPayload, type RenderOverrides } from '$lib/features/render-payload';
import { wildOverride } from '$lib/features/wild/render';
import { normalizeCanvasAspectId, type CanvasAspectId } from '$lib/plugins/system/canvas-aspect';
import type { HistoryItem } from '$lib/historyManagerState.svelte';
import type { SaveHistoryOptions } from '$lib/features/history/save';
import type { PaintResult } from '$lib/features/run/current-work';
import type { WorkState } from '$lib/features/work/state.svelte';
import { RefinementSessionState, type RefineKind, type VariationAmplitude, type VariationCandidate } from '$lib/features/canvas/refinement-session.svelte';
import { projectRefinementCandidate, saveRefinementCandidates } from '$lib/features/canvas/refinement-actions';
import { planRefinementCandidates, runRefinementFanout } from '$lib/features/canvas/refinement-fanout';
import { projectRefinementRedrawResult, runLayoutRedraw, runReadingRedraw, runTouchRedraw, type RefinementRedrawProjection } from '$lib/features/canvas/refinement-redraw';

type Iteration = HistoryItem;
type DdlDiffPart = { kind: 'same' | 'removed' | 'added'; text: string; };
type RefinementWork = Pick<WorkState,
	'confirmFallbackRefine' | 'currentRefineParent' | 'ddl' | 'ddlAutoRepairEnabled' |
	'ddlGeneratedBaseline' | 'displayedHistoryItem' | 'elapsedStage1Ms' | 'elapsedStage2Ms' |
	'elapsedTotalMs' | 'error' | 'expandedDdl' | 'input' | 'instructionLang' | 'loading' |
	'paintOne' | 'paintTokensIn' | 'paintTokensOut' | 'reloadError' | 'reloading' | 'result' |
	'sketchPayloadFor' | 'sketchTextFor' | 'stopTimer' | 'thinking' | 'tokensInStage1' |
	'tokensInStage2' | 'tokensOutStage1' | 'tokensOutStage2'
>;

export type RefinementCoordinatorDeps = {
	apiFetch: (path: string, init?: RequestInit) => Promise<Response>;
	apiError: (response: Response) => Promise<Error>;
	work: RefinementWork;
	session: RefinementSessionState;
	history: {
		clearSelection: () => void;
		fetchOffset: (offset: number, options?: { anchorId?: string; }) => Promise<unknown>;
		items: () => Iteration[];
		syncToItem: (item: Iteration) => Promise<unknown>;
	};
	models: { stage1: () => string; stage2: () => string; };
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
		interpretation: () => string;
	};
	lineageParentId: () => string | null;
	ensureVisibleLineageParentId: () => Promise<string | null>;
	buildDdlDiffParts: (before: string | null, after: string | null) => DdlDiffPart[];
	setInterpretationDiffParts: (parts: DdlDiffPart[]) => void;
	pushHistory: (item: Iteration, options?: SaveHistoryOptions) => Promise<Iteration | null>;
	resetTargetScopedState: (options?: { preserveVariationCandidates?: boolean; }) => void;
	showCanvas: () => void;
	fitCanvas: () => void;
};

export function createRefinementCoordinator(deps: RefinementCoordinatorDeps) {
	const { apiFetch, apiError, work, session: refinementSession } = deps;
	let targetIdentityVersion = 0;

	function resetTarget(options: { preserveVariationCandidates?: boolean; } = {}): void {
		targetIdentityVersion += 1;
		refinementSession.reset({ preserveCandidates: options.preserveVariationCandidates });
	}

	// The coordinator applies the projection to the canonical Work owner; the
	// action module decides only which response fields form that projection.
	function applyRefinementRedrawProjection(projection: RefinementRedrawProjection): void {
		work.ddl = projection.ddl;
		work.expandedDdl = projection.expandedDdl;
		work.ddlGeneratedBaseline = projection.ddl;
		work.thinking = projection.thinking;
		work.result = projection.result;
		work.displayedHistoryItem = null;
		work.elapsedStage1Ms = projection.elapsedStage1Ms;
		work.elapsedStage2Ms = projection.elapsedStage2Ms;
		work.elapsedTotalMs = projection.elapsedTotalMs;
		work.tokensInStage1 = projection.tokensInStage1;
		work.tokensOutStage1 = projection.tokensOutStage1;
		work.tokensInStage2 = projection.tokensInStage2;
		work.tokensOutStage2 = projection.tokensOutStage2;
	}

	async function varyPerformance() {
		if (!work.result || refinementSession.busy) return;
		// Ask before the words are carried into a child (contract § stage 4).
		if (!(await work.confirmFallbackRefine(work.currentRefineParent()))) return;
		const contextVersion = targetIdentityVersion;
		const parentNodeId = await deps.ensureVisibleLineageParentId();
		if (contextVersion !== targetIdentityVersion || !work.result) return;
		refinementSession.beginSingle();
		work.reloading = true;
		work.reloadError = null;
		try {
			const redrawn = await runTouchRedraw({
				current: work.result,
				canvasAspectId: refinementCanvasAspectId(),
				parentNodeId,
				workReference: workReferencePayload(refinementWorkId()),
				renderPayload: renderSettingsPayload('render-svg', colorCatalogOverride(refinementCatalogId()))
			}, {
				apiFetch,
				apiError,
				createRenderSeed: deps.seeds.composition,
				isCurrentTarget: () => contextVersion === targetIdentityVersion,
				currentResult: () => work.result!
			});
			if (!redrawn) return;
			work.result = redrawn;
			work.displayedHistoryItem = null;
			deps.history.clearSelection();
			deps.showCanvas();
			deps.fitCanvas();
		} catch (e) {
			if (contextVersion === targetIdentityVersion) {
				work.reloadError = e instanceof Error ? e.message : String(e);
			}
		} finally {
			work.reloading = false;
			if (contextVersion === targetIdentityVersion) refinementSession.finishSingle();
		}
	}

	async function varyComposition() {
		if (!work.result || refinementSession.busy || work.loading) return;
		const source = work.input.trim();
		if (!source) return;
		// Ask before the words are carried into a child (contract § stage 4).
		if (!(await work.confirmFallbackRefine(work.currentRefineParent()))) return;
		const parentNodeId = await deps.ensureVisibleLineageParentId();
		refinementSession.beginSingle();
		work.loading = true;
		work.error = null;
		try {
			const r = await runLayoutRedraw({
				source,
				current: work.result,
				canvasAspectId: refinementCanvasAspectId(),
				renderOverrides: inPlaceRedrawOverrides(),
				parentNodeId
			}, {
				createCompositionSeed: deps.seeds.composition,
				paint: work.paintOne
			});
			applyRefinementRedrawProjection(projectRefinementRedrawResult(r));
			deps.showCanvas();
			if (r.history_id) {
				await deps.history.fetchOffset(0, { anchorId: r.history_id });
				work.displayedHistoryItem = deps.history.items().find((item) => item.id === r.history_id) ?? null;
			} else {
				deps.history.clearSelection();
			}
			deps.fitCanvas();
		} catch (e) {
			work.error = e instanceof Error ? e.message : String(e);
		} finally {
			work.loading = false;
			refinementSession.finishSingle();
			work.stopTimer();
		}
	}

	async function varyInterpretation() {
		if (!work.result || refinementSession.busy || work.loading) return;
		const source = work.input.trim();
		if (!source) return;
		// Ask before the words are carried into a child (contract § stage 4).
		if (!(await work.confirmFallbackRefine(work.currentRefineParent()))) return;
		const parentNodeId = await deps.ensureVisibleLineageParentId();
		refinementSession.beginSingle();
		work.loading = true;
		work.error = null;
		const previousDdl = work.ddl;
		try {
			const r = await runReadingRedraw({
				source,
				canvasAspectId: refinementCanvasAspectId(),
				renderOverrides: inPlaceRedrawOverrides(),
				parentNodeId
			}, {
				createInterpretationSeed: deps.seeds.interpretation,
				paint: work.paintOne
			});
			deps.setInterpretationDiffParts(deps.buildDdlDiffParts(previousDdl, r.ddl));
			applyRefinementRedrawProjection(projectRefinementRedrawResult(r));
			deps.showCanvas();
			if (r.history_id) {
				await deps.history.fetchOffset(0, { anchorId: r.history_id });
				work.displayedHistoryItem = deps.history.items().find((item) => item.id === r.history_id) ?? null;
			} else {
				deps.history.clearSelection();
			}
			deps.fitCanvas();
		} catch (e) {
			work.error = e instanceof Error ? e.message : String(e);
		} finally {
			work.loading = false;
			refinementSession.finishSingle();
			work.stopTimer();
		}
	}

	function composeCandidateResult(source: string, baseDdl: string, data: PaintResult & { ddl: string; thinking?: string | null; elapsed_ms?: number; tokens_in?: number | null; tokens_out?: number | null; }): PaintResult & { ddl: string; thinking: string | null; } {
		return {
			...data,
			ddl: data.ddl,
			thinking: data.thinking ?? work.thinking,
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

	function workReferencePayload(workId: string | null | undefined): Record<string, string> {
		return workId ? { work_id: workId } : {};
	}

	// The two in-place redraws (vary the layout, reinterpret) keep the artwork's
	// catalog but have never carried the level or the switch: they omit the level
	// so the parent's is inherited, and draw tame. Preserved as-is.
	function inPlaceRedrawOverrides(): RenderOverrides {
		return {
			...colorCatalogOverride(refinementCatalogId()),
			...wildOverride(false)
		};
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

	async function renderWordTouchCandidate(seedText: string, label: string, signal?: AbortSignal): Promise<VariationCandidate> {
		if (!work.result) throw new Error("missing result");
		const normalizedSeedText = seedText.trim();
		if (!normalizedSeedText) throw new Error(getLang() === 'ja' ? 'タッチを変える言葉を入力してください。' : 'Enter words to vary the touch.');
		const r = await apiFetch('/api/render-score', {
			method: 'POST',
			signal,
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({
				score: work.result.score,
				input: work.input.trim(),
				ddl: work.ddl ?? '',
				canvas_aspect: refinementCanvasAspectId(),
				// Same reasoning as varyPerformance: the placement on screen followed render_seed
				// when the work carries no composition_seed, so sending the raw field would send
				// null and let the placement follow the new performance seed instead.
				composition_seed: work.result.composition_seed ?? work.result.render_seed ?? null,
				interpretation_seed: work.result.interpretation_seed,
				seed_text: normalizedSeedText,
				...workReferencePayload(refinementWorkId()),
				...renderSettingsPayload('render-score', colorCatalogOverride(refinementCatalogId())),
			}),
		});
		if (!r.ok) throw await apiError(r);
		const data = await r.json() as Partial<PaintResult> & Pick<PaintResult, 'svg' | 'score' | 'render_seed'>;
		return {
			id: `word-touch-${String(data.render_seed)}`,
			label,
			selected: false,
			result: {
				...work.result,
				...data,
				ddl: work.ddl ?? '',
				thinking: work.thinking,
				history_id: null,
				history_at: null,
				lineage_node_id: null,
				lineage_parent_node_id: deps.lineageParentId(),
				derivation_kind: deps.lineageParentId() ? 'touch_change' : null,
				derivation_metadata: { render_seed_from: work.result.render_seed ?? null, render_seed_to: data.render_seed, seed_text: normalizedSeedText },
			},
		};
	}

	async function composeVariationCandidate(compositionSeed: number, label: string, signal?: AbortSignal): Promise<VariationCandidate> {
		const source = work.input.trim();
		const baseDdl = work.ddl ?? "";
		const r = await apiFetch("/api/compose", {
			method: "POST",
			signal,
			headers: { "Content-Type": "application/json" },
			body: JSON.stringify({
				ddl: baseDdl,
				description: source,
				...work.sketchPayloadFor(source),
				model: deps.models.stage2(),
				instruction_lang: work.instructionLang,
				ui_lang: getLang(),
				canvas_aspect: refinementCanvasAspectId(),
				auto_repair: work.ddlAutoRepairEnabled,
				composition_seed: compositionSeed,
				...renderSettingsPayload('compose', refinementRenderOverrides()),
				...(deps.lineageParentId() ? { lineage_parent_node_id: deps.lineageParentId() } : {}),
			})
		});
		if (!r.ok) throw await apiError(r);
		const data = await r.json();
		return { id: `comp-${compositionSeed}`, label, selected: false, result: { ...composeCandidateResult(source, baseDdl, data), lineage_parent_node_id: deps.lineageParentId(), derivation_kind: deps.lineageParentId() ? 'layout_change' : null, derivation_metadata: { composition_seed: compositionSeed } } };
	}

	async function interpretationVariationCandidate(label: string, signal?: AbortSignal): Promise<VariationCandidate> {
		const source = work.input.trim();
		const interpretationSeed = deps.seeds.interpretation();
		const r = await work.paintOne(source, {
			historyInput: source,
			sourceText: source,
			saveHistory: false,
			saveArtifacts: false,
			countGeneration: false,
			canvasAspectId: refinementCanvasAspectId(),
			sketchText: work.sketchTextFor(source),
			interpretationSeed,
			signal,
			renderOverrides: refinementRenderOverrides(),
			lineageParentNodeId: deps.lineageParentId(),
		});
		return { id: "interp-" + interpretationSeed, label, selected: false, result: { ...r, lineage_parent_node_id: deps.lineageParentId(), derivation_kind: deps.lineageParentId() ? "reinterpretation" : null, derivation_metadata: { interpretation_seed: interpretationSeed } } };
	}

	async function renderColorCatalogCandidate(catalogId: string, label: string, signal?: AbortSignal): Promise<VariationCandidate> {
		if (!work.result) throw new Error("missing result");
		const source = work.input.trim();
		const fromCatalogId = refinementCatalogId();
		const r = await apiFetch("/api/render-score", {
			method: "POST",
			signal,
			headers: { "Content-Type": "application/json" },
			body: JSON.stringify({
				score: work.result.score,
				input: source,
				ddl: work.ddl ?? "",
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
				...data,
				ddl: work.ddl ?? "",
				thinking: work.thinking,
				history_id: null,
				history_at: null,
				lineage_node_id: null,
				lineage_parent_node_id: deps.lineageParentId(),
				derivation_kind: deps.lineageParentId() ? "catalog_change" : null,
				derivation_metadata: { catalog_id_from: fromCatalogId, catalog_id_to: catalogId },
			},
		};
	}

	async function variationCandidateLabel(amplitude: VariationAmplitude, seed: number, label: string, signal?: AbortSignal): Promise<VariationCandidate> {
		const source = work.input.trim();
		const baseDdl = work.ddl ?? "";
		const r = await apiFetch("/api/compose", {
			method: "POST",
			signal,
			headers: { "Content-Type": "application/json" },
			body: JSON.stringify({
				ddl: baseDdl,
				description: source,
				...work.sketchPayloadFor(source),
				model: deps.models.stage2(),
				instruction_lang: work.instructionLang,
				ui_lang: getLang(),
				canvas_aspect: refinementCanvasAspectId(),
				auto_repair: work.ddlAutoRepairEnabled,
				variation_amplitude: amplitude,
				variation_seed: seed,
				...renderSettingsPayload('compose', refinementRenderOverrides()),
				...(deps.lineageParentId() ? { lineage_parent_node_id: deps.lineageParentId() } : {}),
			})
		});
		if (!r.ok) throw await apiError(r);
		const data = await r.json();
		return {
			id: `variation-${amplitude}-${seed}`,
			label,
			selected: false,
			result: {
				...composeCandidateResult(source, baseDdl, data),
				lineage_parent_node_id: deps.lineageParentId(),
				derivation_kind: deps.lineageParentId() ? 'variation' : null,
				derivation_metadata: { variation_amplitude: amplitude, variation_seed: seed },
			},
		};
	}

	// The Server allocates variation seeds; seed-space ownership and deduplication stay out of the UI.
	async function allocateVariationSeeds(amplitude: VariationAmplitude, count: number): Promise<number[]> {
		const r = await apiFetch("/api/variation/seeds", {
			method: "POST",
			headers: { "Content-Type": "application/json" },
			body: JSON.stringify({ amplitude, count })
		});
		if (!r.ok) throw await apiError(r);
		return (await r.json()).seeds as number[];
	}

	async function generateVariationCandidates(kind: RefineKind, count: 1 | 4, touchWords?: string, amplitude?: VariationAmplitude) {
		if (!work.result || refinementSession.gridBusy || work.loading) return;
		const source = work.input.trim();
		if (!source || !work.ddl) return;
		const normalizedTouchWords = touchWords?.trim() ?? '';
		if (kind === 'touch' && !normalizedTouchWords) {
			refinementSession.setStatus(getLang() === 'ja' ? 'タッチを変える言葉を入力してください。' : 'Enter words to vary the touch.');
			return;
		}
		if (kind === 'touch' && count === 4) {
			refinementSession.setStatus(getLang() === 'ja' ? '同じ言葉は同じタッチ(Seed)になります。1案だけ生成可能です。' : 'The same words produce the same touch (Seed). Only one option can be made.');
			return;
		}
		// Ask before the words are carried into a child (contract § stage 4).
		if (!(await work.confirmFallbackRefine(work.currentRefineParent()))) return;
		const contextVersion = targetIdentityVersion;
		await deps.ensureVisibleLineageParentId();
		if (contextVersion !== targetIdentityVersion) return;
		const taskLabel = kind === "touch"
			? t().canvasVaryPerformance
			: kind === "layout"
				? t().canvasVaryComposition
				: kind === "reading"
					? t().canvasVaryInterpretation
					: kind === "variation"
						? t().variationTitle
						: t().canvasVaryColor;
		const abortController = refinementSession.beginGrid({
			includesReading: kind === 'reading',
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
				touchWords: normalizedTouchWords,
				amplitude,
				signal: abortController.signal,
				labels: {
					touch: t().canvasVaryPerformance,
					layout: t().canvasVaryComposition,
					reading: t().canvasVaryInterpretation,
					variation: t().variationTitle,
					color: t().canvasVaryColor,
					noAlternateCatalog: t().refineNoAlternateCatalog
				},
				currentCompositionSeed: work.result.composition_seed,
				previousCandidates: refinementSession.candidates,
				availableCatalogIds: deps.catalog.available().map((catalog) => catalog.id),
				currentCatalogId: refinementCatalogId()
			}, {
				createCompositionSeed: deps.seeds.composition,
				allocateVariationSeeds,
				catalogName: deps.catalog.name,
				renderTouch: renderWordTouchCandidate,
				renderLayout: composeVariationCandidate,
				renderReading: interpretationVariationCandidate,
				renderVariation: variationCandidateLabel,
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

	function showVariationCandidate(candidate: VariationCandidate) {
		const projection = projectRefinementCandidate(candidate);
		deps.resetTargetScopedState({ preserveVariationCandidates: true });
		deps.history.clearSelection();
		work.ddl = projection.ddl;
		work.expandedDdl = projection.expandedDdl;
		work.ddlGeneratedBaseline = work.ddl;
		work.thinking = projection.thinking;
		work.result = projection.result;
		work.displayedHistoryItem = null;
		deps.showCanvas();
		deps.fitCanvas();
	}

	async function saveSelectedVariationCandidates() {
		const contextVersion = targetIdentityVersion;
		const selected = refinementSession.candidates.filter((candidate) => candidate.selected && !candidate.saved);
		if (selected.length === 0) {
			refinementSession.setStatus(t().variationGridEmpty);
			return;
		}
		refinementSession.beginSave();
		try {
			await saveRefinementCandidates({
				candidates: selected,
				sourceText: () => work.input.trim(),
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
		varyPerformance,
		varyComposition,
		varyInterpretation,
		generateVariationCandidates,
		showVariationCandidate,
		saveSelectedVariationCandidates,
	};
}
