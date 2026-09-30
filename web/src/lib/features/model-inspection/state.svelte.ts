import { t } from '$lib/i18n/index.svelte';
import { qualifiedModelId, type ModelOption, type Provider, type ProviderGroup } from '$lib/models';
import { registerUserSettingsContributor } from '$lib/features/user-settings';

export type ModelInspectionDeps = {
	/** Page state, read through getters so the bodies below stay reactive. */
	availableModelCatalog: () => ProviderGroup[];
	result: () => { stage1_model?: string | null; stage2_model?: string | null } | null;
	stage1Provider: () => Provider;
	stage1Model: () => string;
	stage2Provider: () => Provider;
	stage2Model: () => string;
	currentUser: () => { username: string } | null;
	setCurrentUser: (user: unknown) => void;
	apiFetch: (path: string, init?: RequestInit) => Promise<Response>;
};

/**
 * The models the "change the model" dialog draws the work with: which ones the
 * author picked, which one is already on the canvas, and which ones failed.
 *
 * The drawing itself goes through the refinement session like the color
 * change: each picked model draws an option, and the author keeps the ones
 * worth keeping with "+" before saving them.
 *
 * A factory rather than a class so the $effect inside is created in the
 * component's effect context, because the page calls this during
 * initialisation.
 */
export function createModelInspection(deps: ModelInspectionDeps) {
	const { apiFetch } = deps;
	// Page state the bodies read as plain values.
	const availableModelCatalog = $derived(deps.availableModelCatalog());
	const result = $derived(deps.result());
	const stage1Provider = $derived(deps.stage1Provider());
	const stage1Model = $derived(deps.stage1Model());
	const stage2Provider = $derived(deps.stage2Provider());
	const stage2Model = $derived(deps.stage2Model());
	const currentUser = $derived(deps.currentUser());
type ModelInspectionChoice = { id: string; label: string; providerLabel: string; model: ModelOption };

let modelInspectionStatus = $state<string | null>(null);
let modelInspectionSelectedModels = $state<string[]>([]);
// The selection rides along in the user's model_settings on the server. The
// key is the one the server already stores; nothing is renamed.
const SELECTED_MODELS_FIELD = 'model_inspection_selected_models';
registerUserSettingsContributor({
	id: 'model-inspection',
	collect: () => ({ [SELECTED_MODELS_FIELD]: modelInspectionSelectedModels }),
	apply: (settings) => {
		const stored = settings[SELECTED_MODELS_FIELD];
		modelInspectionSelectedModels = Array.isArray(stored)
			? stored.filter((model): model is string => typeof model === 'string').slice(0, 4)
			: [];
	}
});
let modelInspectionFailedModels = $state<Record<string, string>>({});

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

// A work drawn before the stages shared a model may name two; either one is
// already on the canvas, so neither is offered for comparison.
function isModelInspectionChoiceBlocked(model: string) {
	return model === modelInspectionTargetStage1Model || model === modelInspectionTargetStage2Model;
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
	if (isModelInspectionChoiceBlocked(modelId)) return;
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

/** The picked models the work can be drawn with, in the order picked. */
function drawableModels(): string[] {
	return modelInspectionSelectedModels.slice(0, 4).filter((model) => !isModelInspectionChoiceBlocked(model));
}

/** Mark the models that failed to draw, so their choices say so. */
function recordFailures(failed: Record<string, string>) {
	modelInspectionFailedModels = { ...modelInspectionFailedModels, ...failed };
}

	/** Forget the failures: the target artwork changed. */
	function reset() {
		modelInspectionFailedModels = {};
		modelInspectionStatus = null;
	}

	return {
		// The selection is persisted with the user's model settings, so the page
		// both reads and writes it.
		get selectedModels() { return modelInspectionSelectedModels; },
		set selectedModels(value: string[]) { modelInspectionSelectedModels = value; },
		get choices() { return modelInspectionChoices; },
		get targetStage1Model() { return modelInspectionTargetStage1Model; },
		get targetStage2Model() { return modelInspectionTargetStage2Model; },
		get targetModel() { return modelInspectionTargetModel; },
		get status() { return modelInspectionStatus; },
		get failedModels() { return modelInspectionFailedModels; },
		isChoiceBlocked: isModelInspectionChoiceBlocked,
		toggleModel: toggleModelInspectionModel,
		drawableModels,
		recordFailures,
		reset,
	};
}
