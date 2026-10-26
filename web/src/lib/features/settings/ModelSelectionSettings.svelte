<script lang="ts">
	import { t } from '$lib/i18n/index.svelte';
	import ModelMetaCard from '$lib/components/ModelMetaCard.svelte';
	import { modelRecommendation, modelRecommendationStars, modelStatusLabel, modelStatusParts, isModelUnselectable, purposeUnsupported, sortModels, type ModelPurpose, type ModelStage } from '$lib/modelMeta';
	import type { Provider, ProviderGroup } from '$lib/models';
	import './model-selection-settings.css';

	type Props = {
		stage1Provider: Provider;
		stage1Model: string;
		visionProvider: Provider;
		visionModel: string;
		providerGroups: ProviderGroup[];
		visionProviderGroups: ProviderGroup[];
		allowVisionSelection: boolean;
		visionOnlySelection?: boolean;
		includeThinking: boolean;
		onSetStage1Provider: (provider: Provider) => void;
		onSetStage1Model: (model: string) => void;
		onSetStage2Provider: (provider: Provider) => void;
		onSetStage2Model: (model: string) => void;
		onSetVisionProvider: (provider: Provider) => void;
		onSetVisionModel: (model: string) => void;
		onCancel: () => void;
		onConfirm: () => void;
	};

	let {
		stage1Provider, stage1Model,
		visionProvider, visionModel, providerGroups, visionProviderGroups,
		allowVisionSelection, visionOnlySelection = false, includeThinking = $bindable(),
		onSetStage1Provider, onSetStage1Model, onSetStage2Provider, onSetStage2Model,
		onSetVisionProvider, onSetVisionModel, onCancel, onConfirm
	}: Props = $props();

	const isJapanese = $derived(t().closeLabel !== 'Close');
	// One model draws both stages (2026-09-30, the author): the drawing tab
	// chooses it for Stage 1 and Stage 2 together, and there is no per-stage tab.
	type ModelSelectionTab = 'shared' | 'vision';
	let modelSelectionTab = $state<ModelSelectionTab>('shared');
	$effect(() => { if (visionOnlySelection) modelSelectionTab = 'vision'; });
	const recommendationPurpose = $derived<ModelPurpose>(modelSelectionTab === 'vision' ? 'vision' : 'llm');
	const recommendationStage = $derived<ModelStage | undefined>(modelSelectionTab === 'vision' ? undefined : 'both');
	function modelSelected(provider: Provider, model: string): boolean {
		if (modelSelectionTab === 'vision') return visionProvider === provider && visionModel === model;
		return stage1Provider === provider && stage1Model === model;
	}

	function selectGenerationModel(provider: Provider, model: string): void {
		if (modelSelectionTab === 'vision') {
			onSetVisionProvider(provider);
			onSetVisionModel(model);
			return;
		}
		onSetStage1Provider(provider);
		onSetStage1Model(model);
		onSetStage2Provider(provider);
		onSetStage2Model(model);
	}


</script>

		<div class="settings-tabs model-selection-tabs" role="tablist" aria-label={t().modelSelectButton}>
			{#if !visionOnlySelection}<button role="tab" aria-selected={modelSelectionTab === 'shared'} class:active={modelSelectionTab === 'shared'} onclick={() => (modelSelectionTab = 'shared')}>Stage 1/2</button>{/if}
			{#if allowVisionSelection}<button role="tab" aria-selected={modelSelectionTab === 'vision'} class:active={modelSelectionTab === 'vision'} onclick={() => (modelSelectionTab = 'vision')}>Vision</button>{/if}
		</div>
	<div class="settings-body">
			<div class="model-selection-summary">
				{#if !visionOnlySelection}<span><strong>Stage 1/2</strong>{providerGroups.find((group) => group.id === stage1Provider)?.models.find((model) => model.id === stage1Model)?.label ?? stage1Model}</span>{/if}
				{#if allowVisionSelection}<span><strong>Vision</strong>{visionProviderGroups.find((group) => group.id === visionProvider)?.models.find((model) => model.id === visionModel)?.label ?? visionModel}</span>{/if}
			</div>
			<p class="model-selection-hint">{modelSelectionTab === 'vision' ? t().modelSelectionVisionHint : t().modelSelectionSharedHint}</p>
			{#if !visionOnlySelection && stage1Provider === 'chatgpt'}
				<p>{providerGroups.some((group) => group.id === 'chatgpt' && group.models.some((model) => model.id === stage1Model)) ? t().chatgptUsingPlan : t().chatgptModelUnavailable}</p>
			{/if}
			<div class="generation-model-groups">
				{#each (modelSelectionTab === 'vision' ? visionProviderGroups : providerGroups) as provider (provider.id)}
					{#if provider.models.length > 0}
						<section class="generation-model-provider">
							<h3>{provider.id === 'chatgpt' ? t().chatgptPlanLabel : provider.label}</h3>
							<div class="generation-model-grid">
								{#each (provider.id === 'chatgpt' ? provider.models : sortModels(provider.models, recommendationPurpose, recommendationStage)) as model (model.id)}
								<button
									type="button"
									class="model-metadata-hover"
									class:selected={modelSelected(provider.id, model.id)}
									class:eol={model.eol}
									class:unselectable={isModelUnselectable(model)}
									class:not-recommended={purposeUnsupported(model, recommendationPurpose)}
									title={purposeUnsupported(model, recommendationPurpose) ? t().modelNotRecommendedHint : undefined}
									disabled={isModelUnselectable(model)}
									aria-pressed={modelSelected(provider.id, model.id)}
									onclick={() => selectGenerationModel(provider.id, model.id)}
								>
									<div class="model-button-heading">
										<strong>{model.label}</strong>
										<span class="model-recommendation" aria-label={`${t().settingsModelRecommendationFields[recommendationPurpose === 'vision' ? 'recommendation_vision' : 'recommendation_llm']} ${modelRecommendation(model, recommendationPurpose, recommendationStage)}`}>{modelRecommendationStars(model, recommendationPurpose, recommendationStage)}</span>
									</div>
									{#if purposeUnsupported(model, recommendationPurpose)}<span class="not-recommended-note">{t().modelNotRecommended}</span>{/if}
									{#if modelStatusLabel(model, isJapanese)}<span class="model-label-mark">{#each modelStatusParts(model, isJapanese) as part, partIndex (partIndex)}{#if partIndex > 0}{' · '}{/if}<span class:eol-mark={part.blocking}>{part.text}</span>{/each}</span>{/if}
									{#if model.notes}<span>{model.notes}</span>{/if}
									<ModelMetaCard {model} {isJapanese} purpose={recommendationPurpose} />
								</button>
							{/each}
							</div>
						</section>
					{/if}
				{/each}
			</div>
			{#if modelSelectionTab === 'shared' && stage1Model.includes('qwen3')}
				<label class="check-row model-thinking-row">
					<input type="checkbox" bind:checked={includeThinking} />
					<span>{t().showThinkingLabel}</span>
				</label>
			{/if}
	</div>
		<div class="catalog-modal-foot">
			<button class="ghost-btn" onclick={onCancel}>{t().confirmCancel}</button>
			<button class="ghost-btn primary-inline" onclick={onConfirm}>{t().colorCatalogConfirm}</button>
		</div>
