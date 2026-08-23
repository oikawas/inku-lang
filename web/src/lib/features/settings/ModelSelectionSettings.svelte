<script lang="ts">
	import { t } from '$lib/i18n/index.svelte';
	import ModelMetaCard from '$lib/components/ModelMetaCard.svelte';
	import { modelStatusLabel, isModelUnselectable, sortModels, type ModelPurpose, type ModelStage } from '$lib/modelMeta';
	import type { Provider, ProviderGroup } from '$lib/models';
	import './model-selection-settings.css';

	type Props = {
		stage1Provider: Provider;
		stage1Model: string;
		stage2Provider: Provider;
		stage2Model: string;
		visionProvider: Provider;
		visionModel: string;
		providerGroups: ProviderGroup[];
		visionProviderGroups: ProviderGroup[];
		allowVisionSelection: boolean;
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
		stage1Provider, stage1Model, stage2Provider, stage2Model,
		visionProvider, visionModel, providerGroups, visionProviderGroups,
		allowVisionSelection, includeThinking = $bindable(),
		onSetStage1Provider, onSetStage1Model, onSetStage2Provider, onSetStage2Model,
		onSetVisionProvider, onSetVisionModel, onCancel, onConfirm
	}: Props = $props();

	const isJapanese = $derived(t().closeLabel !== 'Close');
	type ModelSelectionTab = 'shared' | 'stage1' | 'stage2' | 'vision';
	let modelSelectionTab = $state<ModelSelectionTab>('shared');
	// The tab already knows which stage is being chosen for; before this it was
	// collapsed to 'llm' and the stage was thrown away, so Stage 1 and Stage 2
	// showed the same number for models whose two stages disagree.
	const recommendationPurpose = $derived<ModelPurpose>(modelSelectionTab === 'vision' ? 'vision' : 'llm');
	const recommendationStage = $derived<ModelStage | undefined>(
		modelSelectionTab === 'vision' ? undefined : modelSelectionTab === 'shared' ? 'both' : modelSelectionTab
	);
	function modelSelected(provider: Provider, model: string): boolean {
		if (modelSelectionTab === 'vision') return visionProvider === provider && visionModel === model;
		if (modelSelectionTab === 'shared') {
			return stage1Provider === provider && stage1Model === model && stage2Provider === provider && stage2Model === model;
		}
		return modelSelectionTab === 'stage1'
			? stage1Provider === provider && stage1Model === model
			: stage2Provider === provider && stage2Model === model;
	}

	function selectGenerationModel(provider: Provider, model: string): void {
		if (modelSelectionTab === 'vision') {
			onSetVisionProvider(provider);
			onSetVisionModel(model);
			return;
		}
		if (modelSelectionTab === 'shared' || modelSelectionTab === 'stage1') {
			onSetStage1Provider(provider);
			onSetStage1Model(model);
		}
		if (modelSelectionTab === 'shared' || modelSelectionTab === 'stage2') {
			onSetStage2Provider(provider);
			onSetStage2Model(model);
		}
	}


</script>

		<div class="settings-tabs model-selection-tabs" role="tablist" aria-label={t().modelSelectButton}>
			<button role="tab" aria-selected={modelSelectionTab === 'shared'} class:active={modelSelectionTab === 'shared'} onclick={() => (modelSelectionTab = 'shared')}>Stage 1/2</button>
			<button role="tab" aria-selected={modelSelectionTab === 'stage1'} class:active={modelSelectionTab === 'stage1'} onclick={() => (modelSelectionTab = 'stage1')}>Stage 1</button>
			<button role="tab" aria-selected={modelSelectionTab === 'stage2'} class:active={modelSelectionTab === 'stage2'} onclick={() => (modelSelectionTab = 'stage2')}>Stage 2</button>
			{#if allowVisionSelection}<button role="tab" aria-selected={modelSelectionTab === 'vision'} class:active={modelSelectionTab === 'vision'} onclick={() => (modelSelectionTab = 'vision')}>Vision</button>{/if}
		</div>
	<div class="settings-body">
			<div class="model-selection-summary">
				<span><strong>Stage 1</strong>{providerGroups.find((group) => group.id === stage1Provider)?.models.find((model) => model.id === stage1Model)?.label ?? stage1Model}</span>
				<span><strong>Stage 2</strong>{providerGroups.find((group) => group.id === stage2Provider)?.models.find((model) => model.id === stage2Model)?.label ?? stage2Model}</span>
				{#if allowVisionSelection}<span><strong>Vision</strong>{visionProviderGroups.find((group) => group.id === visionProvider)?.models.find((model) => model.id === visionModel)?.label ?? visionModel}</span>{/if}
			</div>
			<p class="model-selection-hint">{modelSelectionTab === 'shared' ? t().modelSelectionSharedHint : modelSelectionTab === 'vision' ? t().modelSelectionVisionHint : t().modelSelectionSeparateHint}</p>
			<div class="generation-model-groups">
				{#each (modelSelectionTab === 'vision' ? visionProviderGroups : providerGroups) as provider (provider.id)}
					{#if provider.models.length > 0}
						<section class="generation-model-provider">
							<h3>{provider.label}</h3>
							<div class="generation-model-grid">
								{#each sortModels(provider.models, recommendationPurpose, recommendationStage) as model (model.id)}
								<button
									type="button"
									class="model-metadata-hover"
									class:selected={modelSelected(provider.id, model.id)}
									class:eol={model.eol}
									class:unselectable={isModelUnselectable(model)}
									disabled={isModelUnselectable(model)}
									aria-pressed={modelSelected(provider.id, model.id)}
									onclick={() => selectGenerationModel(provider.id, model.id)}
								>
									<strong>{model.label}</strong>
									{#if isModelUnselectable(model)}<span class="eol-mark">{modelStatusLabel(model, isJapanese)}</span>{/if}
									{#if model.notes}<span>{model.notes}</span>{/if}
									<ModelMetaCard {model} {isJapanese} purpose={recommendationPurpose} />
								</button>
							{/each}
							</div>
						</section>
					{/if}
				{/each}
			</div>
			{#if modelSelectionTab !== 'stage2' && stage1Model.includes('qwen3')}
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
