import { createElapsed } from '$lib/elapsed.svelte';
import { t, getLang } from '$lib/i18n/index.svelte';
import { qualifiedModelId, type ModelOption, type Provider, type ProviderGroup } from '$lib/models';
import { type CanvasAspectId } from '$lib/plugins/system/canvas-aspect';
import { type RenderOverrides } from '$lib/features/render-payload';
import { tenkeiOverride } from '$lib/features/tenkei/render';
import { type TenkeiLevel } from '$lib/tenkei';
import { type Score } from '$lib/historyManagerState.svelte';
import { colorCatalogSettings } from '$lib/features/color-catalog/settings.svelte';

/**
 * Model comparison and language comparison: draw the same description with
 * several models (or several Stage 1 x Stage 2 language pairs) and let the
 * author adopt the ones worth keeping.
 *
 * A factory rather than a class so the function bodies move across unchanged --
 * they still close over plain `let ... = $state(...)` bindings, and the $effect
 * inside is created in the component's effect context because the page calls
 * this during initialisation.  The page lends what it owns through `deps`; the
 * selection, the results and the run state belong here.
 *
 * Only what this feature actually reads is declared, structurally.  Hoisting
 * the page's types into a shared file would create exactly the shared append
 * point this split exists to remove.
 */
type PaintedStage1 = { ddl: string; thinking: string | null; tokens_in: number | null; tokens_out: number | null };
type PaintedStage2 = {
	svg: string;
	score: Score;
	stage2_model?: string | null;
	tokens_in: number | null;
	tokens_out: number | null;
	render_build_number?: string | null;
	render_color_profile?: Record<string, string> | null;
	render_engine_id?: string | null;
	render_engine_version?: string | null;
	render_color_catalog_id?: string | null;
	render_color_catalog_name?: string | null;
	render_color_catalog_sub?: string | null;
	render_color_map?: Record<string, string> | null;
	render_canvas_aspect?: string | null;
	render_canvas_aspect_id?: string | null;
	render_canvas_aspect_ratio?: number | null;
	render_seed?: number | null;
	render_wild?: boolean | null;
	composition_seed?: number | null;
	interpretation_seed?: string | null;
	instruction_lang_requested?: string | null;
	instruction_lang_resolved?: string | null;
};

export type ModelInspectionDeps = {
	/** Page state, read through getters so the bodies below stay reactive. */
	availableModelCatalog: () => ProviderGroup[];
	result: () => { stage1_model?: string | null; stage2_model?: string | null; instruction_lang_resolved?: string | null } | null;
	stage1Provider: () => Provider;
	stage1Model: () => string;
	stage2Provider: () => Provider;
	stage2Model: () => string;
	loading: () => boolean;
	input: () => string;
	refineTenkeiOverride: () => TenkeiLevel | null;
	currentUser: () => { username: string } | null;
	setCurrentUser: (user: unknown) => void;
	/**
	 * A plain counter, not $state: every flow snapshots it and bails when it has
	 * moved. It is read through a call rather than a $derived for that reason.
	 */
	targetContextVersion: () => number;
	/** Page collaborators, taken as-is. */
	apiFetch: (path: string, init?: RequestInit) => Promise<Response>;
	interpretOne: (text: string, signal?: AbortSignal, modelOverride?: string, langOverride?: 'ja' | 'en', tenkei?: TenkeiLevel | null) => Promise<PaintedStage1>;
	composeOne: (currentDdl: string, originalText: string, signal?: AbortSignal, modelOverride?: string, langOverride?: 'ja' | 'en', renderOptions?: { canvasAspectId?: CanvasAspectId; lineageParentNodeId?: string | null; renderOverrides?: RenderOverrides }) => Promise<PaintedStage2>;
	ensureVisibleLineageParentId: () => Promise<string | null>;
	pushHistory: (it: Record<string, unknown>, options?: Record<string, unknown>) => Promise<{ id?: string; starred?: boolean; note?: string | null } | null>;
	toggleHistoryStar: (item: { id?: string; starred?: boolean; note?: string | null }) => Promise<void>;
	addTokens: (total: number | null, delta: number | null | undefined) => number | null;
	statusModelName: (m: string | null | undefined) => string;
	effectiveCanvasAspectId: () => CanvasAspectId;
};

export function createModelInspection(deps: ModelInspectionDeps) {
	// Collaborators bind straight through, so the bodies below are unchanged.
	const { apiFetch, interpretOne, composeOne, ensureVisibleLineageParentId,
		pushHistory, toggleHistoryStar, addTokens, statusModelName,
		effectiveCanvasAspectId } = deps;
	// Page state the bodies read as plain values.
	const availableModelCatalog = $derived(deps.availableModelCatalog());
	const result = $derived(deps.result());
	const stage1Provider = $derived(deps.stage1Provider());
	const stage1Model = $derived(deps.stage1Model());
	const stage2Provider = $derived(deps.stage2Provider());
	const stage2Model = $derived(deps.stage2Model());
	const loading = $derived(deps.loading());
	const input = $derived(deps.input());
	const refineTenkeiOverride = $derived(deps.refineTenkeiOverride());
	const currentUser = $derived(deps.currentUser());
type ModelInspectionResult = {
	id: string;
	model: string;
	stage1Model?: string | null;
	label: string;
	input: string;
	ddl: string;
	svg: string;
	score: Score;
	stage2Model?: string | null;
	renderBuildNumber?: string | null;
	renderColorProfile?: Record<string, string> | null;
	renderEngineId?: string | null;
	renderEngineVersion?: string | null;
	renderColorCatalogId?: string | null;
	renderColorCatalogName?: string | null;
	renderColorCatalogSub?: string | null;
	renderColorMap?: Record<string, string> | null;
	renderCanvasAspect?: string | null;
	renderCanvasAspectId?: string | null;
	renderCanvasAspectRatio?: number | null;
	renderSeed?: number | null;
	renderWild?: boolean | null;
	compositionSeed?: number | null;
	tokensIn: number | null;
	tokensOut: number | null;
	tokensInStage2: number | null;
	tokensOutStage2: number | null;
	elapsedMs: number;
	lineageParentNodeId?: string | null;
	compareMode: ModelCompareMode;
	comparisonKind?: 'model' | 'language';
	stage1Lang?: 'ja' | 'en';
	stage2Lang?: 'ja' | 'en';
	savedHistoryId?: string | null;
	starred?: boolean;
	saving?: boolean;
};
type ModelInspectionChoice = { id: string; label: string; providerLabel: string; model: ModelOption };

type ModelCompareMode = 'common' | 'stage1_fixed' | 'stage2_fixed';
let modelCompareMode = $state<ModelCompareMode>('common');
let modelCompareFixedModel = $state('');
let modelInspectionBusy = $state(false);
let modelInspectionStatus = $state<string | null>(null);
let modelInspectionResults = $state<ModelInspectionResult[]>([]);
let modelInspectionSelectedModels = $state<string[]>([]);
let modelInspectionFailedModels = $state<Record<string, string>>({});
let modelInspectionRunId = 0;
let modelInspectionAbortController: AbortController | null = null;
let modelInspectionCurrentModel = $state('');
// Language comparison selects (Stage 1 × Stage 2) language combinations directly,
// each id is `${stage1}:${stage2}` (e.g. 'ja:en').
let languageInspectionSelectedCombos = $state<string[]>([]);
let languageInspectionBusy = $state(false);
let languageInspectionStatus = $state<string | null>(null);
let languageInspectionResults = $state<ModelInspectionResult[]>([]);
let languageInspectionRunId = 0;
let languageInspectionAbortController: AbortController | null = null;
let languageInspectionCurrentLabel = $state('');

let modelInspectionTokensIn = $state<number | null>(null);
let modelInspectionTokensOut = $state<number | null>(null);
let languageInspectionTokensIn = $state<number | null>(null);
let languageInspectionTokensOut = $state<number | null>(null);
const modelInspectionElapsed = createElapsed();
	const languageInspectionElapsed = createElapsed();


function modelInspectionModelChoices(): ModelInspectionChoice[] {
	const seen = new Set<string>();
	const choices: ModelInspectionChoice[] = [];
	for (const group of availableModelCatalog) {
		for (const model of group.models) {
			const id = qualifiedModelId(group.id as Provider, model.id);
			if (seen.has(id)) continue;
			seen.add(id);
			choices.push({ id, label: model.label || model.id, providerLabel: group.label || String(group.id), model });
		}
	}
	return choices;
}

const modelInspectionChoices = $derived(modelInspectionModelChoices());

const modelInspectionTargetStage1Model = $derived(result?.stage1_model ?? qualifiedModelId(stage1Provider, stage1Model));
const modelInspectionTargetStage2Model = $derived(result?.stage2_model ?? qualifiedModelId(stage2Provider, stage2Model));
const modelInspectionTargetModel = $derived(modelInspectionTargetStage1Model);

function setModelCompareMode(mode: ModelCompareMode) {
	if (modelInspectionBusy) return;
	modelCompareMode = mode;
	modelCompareFixedModel = mode === 'stage1_fixed' ? modelInspectionTargetStage1Model : mode === 'stage2_fixed' ? modelInspectionTargetStage2Model : '';
	modelInspectionSelectedModels = []; modelInspectionResults = []; modelInspectionFailedModels = {}; modelInspectionStatus = null;
}

function setModelCompareFixedModel(model: string) {
	if (modelInspectionBusy) return;
	modelCompareFixedModel = model; modelInspectionResults = []; modelInspectionFailedModels = {}; modelInspectionStatus = null;
}

function isModelInspectionChoiceBlocked(model: string) {
	if (modelCompareMode === 'common') return model === modelInspectionTargetStage1Model || model === modelInspectionTargetStage2Model;
	if (modelCompareMode === 'stage1_fixed') return modelCompareFixedModel === modelInspectionTargetStage1Model && model === modelInspectionTargetStage2Model;
	return model === modelInspectionTargetStage1Model && modelCompareFixedModel === modelInspectionTargetStage2Model;
}

async function persistModelInspectionSelection(models: string[]) {
	if (!currentUser) return;
	try {
		const r = await apiFetch('/api/auth/me/settings', {
			method: 'PATCH',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({
				model_settings: {
					model_inspection_selected_models: models.slice(0, 4),
				},
			}),
		});
		if (!r.ok) throw new Error(`HTTP ${r.status}`);
		deps.setCurrentUser(await r.json());
	} catch (e) {
		console.warn('failed to save model comparison selection', e);
	}
}

$effect(() => {
	const available = new Set(modelInspectionChoices.map((choice) => choice.id));
	const next = modelInspectionSelectedModels.filter((id) => available.has(id) && !isModelInspectionChoiceBlocked(id)).slice(0, 4);
	if (next.join("\n") !== modelInspectionSelectedModels.join("\n")) {
		modelInspectionSelectedModels = next;
		void persistModelInspectionSelection(next);
	}
});

function toggleModelInspectionModel(modelId: string) {
	if (modelInspectionBusy || isModelInspectionChoiceBlocked(modelId)) return;
	if (modelInspectionSelectedModels.includes(modelId)) {
		const next = modelInspectionSelectedModels.filter((id) => id !== modelId);
		modelInspectionSelectedModels = next;
		void persistModelInspectionSelection(next);
		return;
	}
	if (modelInspectionSelectedModels.length >= 4) {
		modelInspectionStatus = t().modelCompareMaxSelected;
		return;
	}
	const next = [...modelInspectionSelectedModels, modelId];
	modelInspectionSelectedModels = next;
	if (modelInspectionFailedModels[modelId]) {
		const { [modelId]: _failed, ...rest } = modelInspectionFailedModels;
		modelInspectionFailedModels = rest;
	}
	void persistModelInspectionSelection(next);
	modelInspectionStatus = null;
}

async function runModelInspection() {
	if (modelInspectionBusy || loading) return;
	const source = input.trim();
	if (!source) return;
	const contextVersion = deps.targetContextVersion();
	const modelParentNodeId = await ensureVisibleLineageParentId();
	if (contextVersion !== deps.targetContextVersion()) return;
	const selectedModels = modelInspectionSelectedModels.slice(0, 4).filter((model) => !isModelInspectionChoiceBlocked(model));
	if (selectedModels.length === 0) { modelInspectionStatus = t().modelCompareSelectPrompt; return; }
	const jobs = selectedModels.map((model) => {
		const stage1 = modelCompareMode === "stage1_fixed" ? modelCompareFixedModel : model;
		const stage2 = modelCompareMode === "stage2_fixed" ? modelCompareFixedModel : model;
		return { model, stage1, stage2, id: modelCompareMode + ":" + stage1 + ":" + stage2 };
	});
	const rendered = new Set(modelInspectionResults.map((item) => item.id));
	const pending = jobs.filter((job) => !rendered.has(job.id));
	if (pending.length === 0) { modelInspectionStatus = t().modelCompareAllRendered; return; }

	const runId = ++modelInspectionRunId;
	const abortController = new AbortController();
	modelInspectionAbortController = abortController;
	modelInspectionBusy = true;
	modelInspectionStatus = null;
	modelInspectionTokensIn = null;
	modelInspectionTokensOut = null;
	modelInspectionElapsed.start();
	const successful = [...modelInspectionResults];
	const failed: Record<string, string> = {};
	try {
		for (const job of pending) {
			if (abortController.signal.aborted || modelInspectionRunId !== runId) return;
			const jobStage1Name = statusModelName(job.stage1);
			const jobStage2Name = statusModelName(job.stage2);
			modelInspectionCurrentModel = jobStage1Name === jobStage2Name ? jobStage1Name : `${jobStage1Name} / ${jobStage2Name}`;
			try {
				const started = Date.now();
				const interpreted = await interpretOne(source, abortController.signal, job.stage1, undefined, refineTenkeiOverride);
				if (abortController.signal.aborted || modelInspectionRunId !== runId) return;
				modelInspectionTokensIn = addTokens(modelInspectionTokensIn, interpreted.tokens_in);
				modelInspectionTokensOut = addTokens(modelInspectionTokensOut, interpreted.tokens_out);
				const composed = await composeOne(interpreted.ddl, source, abortController.signal, job.stage2, undefined, { renderOverrides: tenkeiOverride(refineTenkeiOverride), lineageParentNodeId: modelParentNodeId });
				if (abortController.signal.aborted || modelInspectionRunId !== runId) return;
				modelInspectionTokensIn = addTokens(modelInspectionTokensIn, composed.tokens_in);
				modelInspectionTokensOut = addTokens(modelInspectionTokensOut, composed.tokens_out);
				successful.push({
					id: job.id,
					model: job.model,
					stage1Model: job.stage1,
					label: statusModelName(job.stage1) + " / " + statusModelName(job.stage2),
					input: source,
					ddl: interpreted.ddl,
					svg: composed.svg,
					score: composed.score,
					stage2Model: composed.stage2_model ?? job.stage2,
					renderBuildNumber: composed.render_build_number ?? null,
					renderColorProfile: composed.render_color_profile ?? null,
					renderEngineId: composed.render_engine_id ?? null,
					renderEngineVersion: composed.render_engine_version ?? null,
					renderColorCatalogId: composed.render_color_catalog_id ?? null,
					renderColorCatalogName: composed.render_color_catalog_name ?? null,
					renderColorCatalogSub: composed.render_color_catalog_sub ?? null,
					renderColorMap: composed.render_color_map ?? null,
					renderCanvasAspect: composed.render_canvas_aspect ?? null,
					renderCanvasAspectId: composed.render_canvas_aspect_id ?? null,
					renderCanvasAspectRatio: composed.render_canvas_aspect_ratio ?? null,
					renderSeed: composed.render_seed ?? null,
					renderWild: composed.render_wild ?? null,
					compositionSeed: composed.composition_seed ?? null,
					tokensIn: interpreted.tokens_in,
					tokensOut: interpreted.tokens_out,
					tokensInStage2: composed.tokens_in,
					tokensOutStage2: composed.tokens_out,
					elapsedMs: Date.now() - started,
					lineageParentNodeId: modelParentNodeId,
					compareMode: modelCompareMode,
					savedHistoryId: null,
					starred: false,
					saving: false,
				});
				modelInspectionResults = [...successful];
			} catch (cause) {
				if (abortController.signal.aborted || modelInspectionRunId !== runId) return;
				failed[job.model] = cause instanceof Error ? cause.message : String(cause);
				modelInspectionFailedModels = { ...modelInspectionFailedModels, [job.model]: failed[job.model] };
			}
		}
		if (Object.keys(failed).length > 0 && modelInspectionRunId === runId) {
			modelInspectionStatus = t().modelCompareFailedSummary(Object.keys(failed).length);
		}
	} finally {
		if (modelInspectionRunId === runId) {
			modelInspectionAbortController = null;
			modelInspectionBusy = false;
			modelInspectionCurrentModel = '';
			modelInspectionElapsed.stop();
		}
	}
}

function abortModelInspection() {
	modelInspectionAbortController?.abort();
}

const languageInspectionTargetLang = $derived(
	(result?.instruction_lang_resolved === 'en' ? 'en' : result?.instruction_lang_resolved === 'ja' ? 'ja' : getLang()) as 'ja' | 'en'
);

// The target artwork's combination (Stage 1 lang == Stage 2 lang == target).
function isLanguageComboBlocked(stage1: 'ja' | 'en', stage2: 'ja' | 'en') {
	return stage1 === languageInspectionTargetLang && stage2 === languageInspectionTargetLang;
}

function toggleLanguageCombo(id: string) {
	if (languageInspectionBusy) return;
	const [s1, s2] = id.split(':') as ['ja' | 'en', 'ja' | 'en'];
	if (isLanguageComboBlocked(s1, s2)) return;
	languageInspectionSelectedCombos = languageInspectionSelectedCombos.includes(id)
		? languageInspectionSelectedCombos.filter((value) => value !== id)
		: [...languageInspectionSelectedCombos, id];
	languageInspectionStatus = null;
}

function abortLanguageInspection() {
	languageInspectionAbortController?.abort();
}

async function runLanguageInspection() {
	if (languageInspectionBusy || loading) return;
	const source = input.trim();
	if (!source) return;
	const selected = languageInspectionSelectedCombos.filter((id) => {
		const [s1, s2] = id.split(':') as ['ja' | 'en', 'ja' | 'en'];
		return !isLanguageComboBlocked(s1, s2);
	});
	if (selected.length === 0) {
		languageInspectionStatus = getLang() === 'ja' ? '比較する組み合わせを1つ以上選択してください。' : 'Select at least one combination to compare.';
		return;
	}
	const contextVersion = deps.targetContextVersion();
	const parentNodeId = await ensureVisibleLineageParentId();
	if (contextVersion !== deps.targetContextVersion()) return;
	const jobs = selected.map((id) => {
		const [stage1Lang, stage2Lang] = id.split(':') as ['ja' | 'en', 'ja' | 'en'];
		return { lang: stage2Lang, stage1Lang, stage2Lang, id };
	});
	const rendered = new Set(languageInspectionResults.map((item) => item.id));
	const pending = jobs.filter((job) => !rendered.has(job.id));
	if (pending.length === 0) {
		languageInspectionStatus = getLang() === 'ja' ? '選択済みの言語構成はすべて描画済みです。' : 'All chosen language combinations have been painted.';
		return;
	}
	const runId = ++languageInspectionRunId;
	const abortController = new AbortController();
	languageInspectionAbortController = abortController;
	languageInspectionBusy = true;
	languageInspectionStatus = null;
	languageInspectionTokensIn = null;
	languageInspectionTokensOut = null;
	languageInspectionElapsed.start();
	const successful = [...languageInspectionResults];
	const langLabel = (lang: 'ja' | 'en') => lang === 'ja' ? (getLang() === 'ja' ? '日本語' : 'Japanese') : 'English';
	try {
		for (const job of pending) {
			if (abortController.signal.aborted || languageInspectionRunId !== runId) return;
			languageInspectionCurrentLabel = `${langLabel(job.stage1Lang)} / ${langLabel(job.stage2Lang)}`;
			try {
				const started = Date.now();
				const interpreted = await interpretOne(source, abortController.signal, undefined, job.stage1Lang, refineTenkeiOverride);
				languageInspectionTokensIn = addTokens(languageInspectionTokensIn, interpreted.tokens_in);
				languageInspectionTokensOut = addTokens(languageInspectionTokensOut, interpreted.tokens_out);
				const composed = await composeOne(interpreted.ddl, source, abortController.signal, undefined, job.stage2Lang, { renderOverrides: tenkeiOverride(refineTenkeiOverride), lineageParentNodeId: parentNodeId });
				if (abortController.signal.aborted || languageInspectionRunId !== runId) return;
				languageInspectionTokensIn = addTokens(languageInspectionTokensIn, composed.tokens_in);
				languageInspectionTokensOut = addTokens(languageInspectionTokensOut, composed.tokens_out);
				successful.push({
					id: job.id,
					model: qualifiedModelId(stage1Provider, stage1Model),
					stage1Model: qualifiedModelId(stage1Provider, stage1Model),
					stage2Model: composed.stage2_model ?? qualifiedModelId(stage2Provider, stage2Model),
					label: `${langLabel(job.stage1Lang)} / ${langLabel(job.stage2Lang)}`,
					input: source,
					ddl: interpreted.ddl,
					svg: composed.svg,
					score: composed.score,
					renderBuildNumber: composed.render_build_number ?? null,
					renderColorProfile: composed.render_color_profile ?? null,
					renderEngineId: composed.render_engine_id ?? null,
					renderEngineVersion: composed.render_engine_version ?? null,
					renderColorCatalogId: composed.render_color_catalog_id ?? null,
					renderColorCatalogName: composed.render_color_catalog_name ?? null,
					renderColorCatalogSub: composed.render_color_catalog_sub ?? null,
					renderColorMap: composed.render_color_map ?? null,
					renderCanvasAspect: composed.render_canvas_aspect ?? null,
					renderCanvasAspectId: composed.render_canvas_aspect_id ?? null,
					renderCanvasAspectRatio: composed.render_canvas_aspect_ratio ?? null,
					renderSeed: composed.render_seed ?? null,
					renderWild: composed.render_wild ?? null,
					compositionSeed: composed.composition_seed ?? null,
					tokensIn: interpreted.tokens_in,
					tokensOut: interpreted.tokens_out,
					tokensInStage2: composed.tokens_in,
					tokensOutStage2: composed.tokens_out,
					elapsedMs: Date.now() - started,
					lineageParentNodeId: parentNodeId,
					compareMode: 'common',
					comparisonKind: 'language',
					stage1Lang: job.stage1Lang,
					stage2Lang: job.stage2Lang,
					savedHistoryId: null,
					starred: false,
					saving: false,
				});
				languageInspectionResults = [...successful];
			} catch (cause) {
				if (abortController.signal.aborted || languageInspectionRunId !== runId) return;
				languageInspectionStatus = cause instanceof Error ? cause.message : String(cause);
			}
		}
	} finally {
		if (languageInspectionRunId === runId) {
			languageInspectionAbortController = null;
			languageInspectionBusy = false;
			languageInspectionCurrentLabel = '';
			languageInspectionElapsed.stop();
		}
	}
}


function updateModelInspectionResult(id: string, patch: Partial<ModelInspectionResult>) {
	modelInspectionResults = modelInspectionResults.map((item) => item.id === id ? { ...item, ...patch } : item);
	languageInspectionResults = languageInspectionResults.map((item) => item.id === id ? { ...item, ...patch } : item);
}

async function saveModelInspectionResult(item: ModelInspectionResult, options: { star?: boolean } = {}) {
	if (item.saving) return;
	const contextVersion = deps.targetContextVersion();
	if (item.savedHistoryId) {
		if (options.star) {
			await toggleHistoryStar({ id: item.savedHistoryId, starred: !!item.starred });
			if (contextVersion === deps.targetContextVersion()) updateModelInspectionResult(item.id, { starred: !item.starred });
		}
		return;
	}
	updateModelInspectionResult(item.id, { saving: true });
	if (item.comparisonKind === 'language') languageInspectionStatus = null;
	else modelInspectionStatus = null;
	try {
		const saved = await pushHistory({
			input: item.input,
			ddl: item.ddl,
			score: item.score,
			svg: item.svg,
			at: Date.now(),
			elapsed_ms: item.elapsedMs,
			stage1_model: item.stage1Model ?? item.model,
			stage2_model: item.stage2Model ?? null,
			tokens_in: (item.tokensIn ?? 0) + (item.tokensInStage2 ?? 0) || null,
			tokens_out: (item.tokensOut ?? 0) + (item.tokensOutStage2 ?? 0) || null,
			catalog_id: item.renderColorCatalogId ?? colorCatalogSettings.selected,
			render_build_number: item.renderBuildNumber ?? null,
			render_color_profile: item.renderColorProfile ?? null,
			render_engine_id: item.renderEngineId ?? null,
			render_engine_version: item.renderEngineVersion ?? null,
			render_color_catalog_id: item.renderColorCatalogId ?? null,
			render_color_catalog_name: item.renderColorCatalogName ?? null,
			render_color_catalog_sub: item.renderColorCatalogSub ?? null,
			render_color_map: item.renderColorMap ?? null,
			render_canvas_aspect: item.renderCanvasAspect ?? item.renderCanvasAspectId ?? effectiveCanvasAspectId(),
			render_canvas_aspect_id: item.renderCanvasAspectId ?? item.renderCanvasAspect ?? effectiveCanvasAspectId(),
			render_canvas_aspect_ratio: item.renderCanvasAspectRatio ?? null,
			render_seed: item.renderSeed ?? null,
			render_wild: item.renderWild ?? null,
			composition_seed: item.compositionSeed ?? null,
			instruction_lang_requested: item.comparisonKind === 'language' ? item.stage2Lang : undefined,
			instruction_lang_resolved: item.comparisonKind === 'language' ? item.stage2Lang : undefined,
			ui_lang: getLang(),
		}, {
			countGeneration: true,
			sourceText: item.input,
			lineageParentNodeId: item.lineageParentNodeId ?? null,
			derivationKind: item.lineageParentNodeId ? (item.comparisonKind === 'language' ? 'language_comparison' : 'model_comparison') : null,
			derivationMetadata: item.comparisonKind === 'language'
				? { comparison_mode: item.compareMode, stage1_language: item.stage1Lang, stage2_language: item.stage2Lang }
				: { comparison_mode: item.compareMode, compared_model: item.model, stage1_model: item.stage1Model, stage2_model: item.stage2Model },
		});
		if (!saved?.id) throw new Error('failed to save comparison result');
		if (contextVersion !== deps.targetContextVersion()) return;
		updateModelInspectionResult(item.id, { savedHistoryId: saved.id, starred: !!saved.starred, saving: false });
		if (options.star) {
			await toggleHistoryStar({ id: saved.id, starred: !!saved.starred, note: saved.note });
			if (contextVersion === deps.targetContextVersion()) updateModelInspectionResult(item.id, { starred: !saved.starred });
		}
	} catch (e) {
		if (contextVersion === deps.targetContextVersion()) {
			updateModelInspectionResult(item.id, { saving: false });
			if (item.comparisonKind === 'language') languageInspectionStatus = e instanceof Error ? e.message : String(e);
			else modelInspectionStatus = e instanceof Error ? e.message : String(e);
		}
	}
}

	/** Abort both runs and drop their results: the target artwork changed. */
	function reset() {
		if (modelInspectionAbortController) modelInspectionAbortController.abort();
		modelInspectionAbortController = null;
		modelInspectionRunId += 1;
		modelInspectionBusy = false;
		modelInspectionResults = [];
		modelInspectionFailedModels = {};
		modelInspectionStatus = null;
		if (languageInspectionAbortController) languageInspectionAbortController.abort();
		languageInspectionAbortController = null;
		languageInspectionRunId += 1;
		languageInspectionBusy = false;
		languageInspectionResults = [];
		languageInspectionStatus = null;
	}

	return {
		// The selection is persisted with the user's model settings, so the page
		// both reads and writes it.
		get selectedModels() { return modelInspectionSelectedModels; },
		set selectedModels(value: string[]) { modelInspectionSelectedModels = value; },
		get compareMode() { return modelCompareMode; },
		get compareFixedModel() { return modelCompareFixedModel; },
		get choices() { return modelInspectionChoices; },
		get targetStage1Model() { return modelInspectionTargetStage1Model; },
		get targetStage2Model() { return modelInspectionTargetStage2Model; },
		get targetModel() { return modelInspectionTargetModel; },
		get busy() { return modelInspectionBusy; },
		get status() { return modelInspectionStatus; },
		get results() { return modelInspectionResults; },
		get failedModels() { return modelInspectionFailedModels; },
		get currentModel() { return modelInspectionCurrentModel; },
		get elapsedMs() { return modelInspectionElapsed.ms; },
		get tokensIn() { return modelInspectionTokensIn; },
		get tokensOut() { return modelInspectionTokensOut; },
		get languageSelectedCombos() { return languageInspectionSelectedCombos; },
		get languageBusy() { return languageInspectionBusy; },
		get languageStatus() { return languageInspectionStatus; },
		get languageResults() { return languageInspectionResults; },
		get languageCurrentLabel() { return languageInspectionCurrentLabel; },
		get languageTargetLang() { return languageInspectionTargetLang; },
		get languageElapsedMs() { return languageInspectionElapsed.ms; },
		get languageTokensIn() { return languageInspectionTokensIn; },
		get languageTokensOut() { return languageInspectionTokensOut; },
		setCompareMode: setModelCompareMode,
		setCompareFixedModel: setModelCompareFixedModel,
		isChoiceBlocked: isModelInspectionChoiceBlocked,
		toggleModel: toggleModelInspectionModel,
		run: runModelInspection,
		abort: abortModelInspection,
		isLanguageComboBlocked,
		toggleLanguageCombo,
		runLanguage: runLanguageInspection,
		abortLanguage: abortLanguageInspection,
		saveResult: saveModelInspectionResult,
		reset,
	};
}
