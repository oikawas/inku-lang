<script lang="ts">
	import { t } from '$lib/i18n/index.svelte';
	import ModelMetaCard from '$lib/components/ModelMetaCard.svelte';
	import { sortModels } from '$lib/modelMeta';
	import type { ModelOption, Provider, ProviderGroup } from '$lib/models';
	import type { ModelAdministration, ModelProviderSetting } from './model-administration.svelte';
	import './model-administration-settings.css';

	type Props = {
		administration: ModelAdministration;
		providerGroups: ProviderGroup[];
	};

	let { administration, providerGroups }: Props = $props();
	const modelSettings = $derived(administration.modelSettings);
	const modelSettingsStatus = $derived(administration.modelSettingsStatus);
	const modelFetchResults = $derived(administration.modelFetchResults);
	const modelSettingsLoading = $derived(administration.modelSettingsLoading);
	const onUpdateModelProvider = (provider: Provider, patch: Partial<ModelProviderSetting>) => administration.updateModelProvider(provider, patch);
	const onAddModelProvider = (provider: Provider, patch: Partial<ModelProviderSetting>) => administration.addModelProvider(provider, patch);
	const onAskDeleteModelProvider = (provider: Provider) => administration.askDeleteModelProvider(provider);
	const onAskClearModelApiKey = (provider: Provider) => administration.askClearModelApiKey(provider);
	const onFetchModelList = (provider: Provider) => administration.fetchProviderModels(provider);
	const onSaveModelProviderName = (provider: Provider, label: string) => administration.saveModelProviderName(provider, label);
	const onSaveModelProviderMemo = (provider: Provider, memo: string) => administration.saveModelProviderMemo(provider, memo);
	const onSaveModelProvider = (provider: Provider, patch?: Partial<ModelProviderSetting>) => administration.saveModelProvider(provider, patch);
	let newProviderId = $state('');
	let newProviderLabel = $state('');
	let newProviderKind = $state('openai_compatible');
	let newProviderBaseUrl = $state('');
	let newProviderApiKey = $state('');
	let showAddServiceDialog = $state(false);
	let modelPickerProviderId = $state<Provider | null>(null);
	let modelPickerSearch = $state('');
	let modelPickerEnabledDraft = $state<Record<string, boolean>>({});
	let modelPickerPurposeDraft = $state<Record<string, ('llm' | 'vision')[]>>({});
	let modelPickerMetadataDraft = $state<Record<string, ModelOption>>({});
	let editProviderId = $state<Provider | null>(null);
	let editProviderLabel = $state('');
	let memoProviderId = $state<Provider | null>(null);
	let memoProviderLabel = $state('');
	let memoProviderText = $state('');
	let baseUrlDrafts = $state<Record<string, string>>({});

	async function addModelProvider() {
		const id = newProviderId.trim().toLowerCase();
		const label = newProviderLabel.trim() || id;
		if (!id || !label || !newProviderBaseUrl.trim()) return;
		await onAddModelProvider(id, {
			label,
			kind: newProviderKind,
			base_url: newProviderBaseUrl.trim(),
			default_base_url: newProviderBaseUrl.trim(),
			requires_api_key: !!newProviderApiKey.trim(),
			api_key: newProviderApiKey.trim() || undefined,
			models: [],
			enabled_models: {},
		});
		newProviderId = '';
		newProviderLabel = '';
		newProviderKind = 'openai_compatible';
		newProviderBaseUrl = '';
		newProviderApiKey = '';
		showAddServiceDialog = false;
	}

	function openEditProvider(provider: ProviderGroup) {
		editProviderId = provider.id;
		editProviderLabel = provider.label;
	}

	async function saveEditProvider() {
		if (!editProviderId || !editProviderLabel.trim()) return;
		await onSaveModelProviderName(editProviderId, editProviderLabel.trim());
		editProviderId = null;
		editProviderLabel = '';
	}

	function openMemoProvider(provider: ProviderGroup) {
		memoProviderId = provider.id;
		memoProviderLabel = provider.label;
		memoProviderText = provider.memo ?? '';
	}

	async function saveMemoProvider() {
		if (!memoProviderId) return;
		await onSaveModelProviderMemo(memoProviderId, memoProviderText);
		memoProviderId = null;
		memoProviderLabel = '';
		memoProviderText = '';
	}

	function baseUrlValue(provider: Provider, setting: ModelProviderSetting): string {
		return baseUrlDrafts[provider] ?? setting.base_url ?? '';
	}

	function baseUrlChanged(provider: Provider, setting: ModelProviderSetting): boolean {
		return baseUrlDrafts[provider] != null && baseUrlDrafts[provider] !== (setting.base_url ?? '');
	}

	function setBaseUrlDraft(provider: Provider, value: string) {
		baseUrlDrafts = { ...baseUrlDrafts, [provider]: value };
	}

	async function saveBaseUrl(provider: Provider, setting: ModelProviderSetting) {
		const value = baseUrlValue(provider, setting).trim();
		onUpdateModelProvider(provider, { base_url: value });
		await onSaveModelProvider(provider);
		const nextDrafts = { ...baseUrlDrafts };
		delete nextDrafts[provider];
		baseUrlDrafts = nextDrafts;
	}

	function setAllPublishedModels(models: { id: string }[], enabled: boolean) {
		modelPickerEnabledDraft = {
			...modelPickerEnabledDraft,
			...Object.fromEntries(models.map((model) => [model.id, enabled])),
		};
	}

	function openModelPicker(provider: Provider) {
		const setting = modelSettings?.providers[provider];
		modelPickerSearch = '';
		modelPickerEnabledDraft = { ...(setting?.enabled_models ?? {}) };
		const catalogProvider = providerGroups.find((group) => group.id === provider);
		modelPickerPurposeDraft = Object.fromEntries((catalogProvider?.models ?? []).map((model) => [model.id, model.purposes ?? ['llm']]));
		modelPickerMetadataDraft = Object.fromEntries((catalogProvider?.models ?? []).map((model) => [model.id, { ...model }]));
		modelPickerProviderId = provider;
	}

	function closeModelPicker() {
		modelPickerProviderId = null;
		modelPickerSearch = '';
		modelPickerEnabledDraft = {};
		modelPickerPurposeDraft = {};
		modelPickerMetadataDraft = {};
	}

	function modelEnabled(setting: ModelProviderSetting, modelId: string): boolean {
		return setting.enabled_models?.[modelId] !== false;
	}

	function modelPickerDraftEnabled(modelId: string): boolean {
		return modelPickerEnabledDraft[modelId] !== false;
	}

	function modelPurposeSelected(modelId: string, purpose: 'llm' | 'vision'): boolean {
		return (modelPickerPurposeDraft[modelId] ?? ['llm']).includes(purpose);
	}

	function toggleModelPurpose(modelId: string, purpose: 'llm' | 'vision'): void {
		const current = modelPickerPurposeDraft[modelId] ?? ['llm'];
		const next = current.includes(purpose) ? current.filter((item) => item !== purpose) : [...current, purpose];
		modelPickerPurposeDraft = { ...modelPickerPurposeDraft, [modelId]: next };
		modelPickerEnabledDraft = { ...modelPickerEnabledDraft, [modelId]: next.length > 0 };
	}

	function modelDraft(model: ModelOption): ModelOption {
		return {
			...model,
			...(modelPickerMetadataDraft[model.id] ?? {}),
			purposes: modelPickerPurposeDraft[model.id] ?? model.purposes ?? ['llm'],
		};
	}

	function updateModelMetadata(model: ModelOption, patch: Partial<ModelOption>): void {
		modelPickerMetadataDraft = {
			...modelPickerMetadataDraft,
			[model.id]: { ...modelDraft(model), ...patch },
		};
	}

	const isJapanese = $derived(t().closeLabel !== 'Close');


	function serviceIdLabel(provider: Provider): string {
		return `${t().settingsModelServiceId}: ${provider}`;
	}

	async function saveModelPicker() {
		if (!modelPickerProvider) return;
		const models = modelPickerProvider.models.map((model) => modelDraft(model));
		await onSaveModelProvider(modelPickerProvider.id, { models, enabled_models: modelPickerEnabledDraft });
		closeModelPicker();
	}

	async function fetchModelPickerModels() {
		if (!modelPickerProvider) return;
		const providerId = modelPickerProvider.id;
		await onFetchModelList(providerId);
		const setting = modelSettings?.providers[providerId];
		modelPickerEnabledDraft = { ...(setting?.enabled_models ?? {}) };
		const provider = providerGroups.find((group) => group.id === providerId);
		modelPickerPurposeDraft = Object.fromEntries((provider?.models ?? []).map((model) => [model.id, model.purposes ?? ['llm']]));
		modelPickerMetadataDraft = Object.fromEntries((provider?.models ?? []).map((model) => [model.id, { ...model }]));
	}

	function hasPendingApiKey(setting: ModelProviderSetting): boolean {
		return !setting.api_key_set && !!setting.api_key?.trim();
	}

	function apiKeyInputValue(setting: ModelProviderSetting): string {
		return setting.api_key_set ? t().settingsModelKeepApiKey : (setting.api_key ?? '');
	}

	function selectedModels(provider: ProviderGroup, setting: ModelProviderSetting, purpose: 'llm' | 'vision') {
		return sortModels(
			provider.models.filter((model) => modelEnabled(setting, model.id) && (model.purposes ?? ['llm']).includes(purpose)),
			purpose
		);
	}

	const settingsProviderGroups = $derived.by(() => {
		const priority: Record<string, number> = { "ollama-cloud": 0, ollama: 1 };
		return providerGroups
			.map((provider, index) => ({ provider, index }))
			.sort((a, b) => (priority[a.provider.id] ?? 2) - (priority[b.provider.id] ?? 2) || a.index - b.index)
			.map(({ provider }) => provider);
	});
	const modelPickerProvider = $derived(providerGroups.find((provider) => provider.id === modelPickerProviderId) ?? null);
	const modelPickerSetting = $derived(
		modelPickerProviderId && modelSettings
			? (modelSettings.providers[modelPickerProviderId] ?? { base_url: '', api_key_set: false, api_key_hint: null, enabled_models: {} })
			: null
	);
	const filteredModelPickerModels = $derived.by(() => {
		const provider = modelPickerProvider;
		if (!provider) return [];
		const query = modelPickerSearch.trim().toLowerCase();
		if (!query) return sortModels(provider.models);
		return sortModels(
			provider.models.filter((model) => {
				const text = `${model.id} ${model.label ?? ''} ${model.notes ?? ''} ${model.speed_label ?? ''} ${model.comment_ja ?? ''} ${model.comment_en ?? ''}`.toLowerCase();
				return text.includes(query);
			})
		);
	});

</script>


			{#if modelSettingsLoading}
				<div class="popover-group"><div class="inline-message">{t().settingsLoading}</div></div>
			{:else if !modelSettings}
				<div class="popover-group"><div class="inline-message">{modelSettingsStatus ?? t().settingsLoadFailed}</div></div>
			{/if}
			{#if modelSettings}
				<div class="popover-group">
					<div class="model-connections-heading">
						<div class="popover-group-label">{t().settingsModelConnectionsTitle}</div>
						<div class="model-security-note">{t().settingsModelSecurityNote}</div>
					</div>
					<div class="model-provider-list">
						{#each settingsProviderGroups as provider (provider.id)}
							{@const setting = modelSettings.providers[provider.id] ?? { base_url: '', api_key_set: false, api_key_hint: null, enabled_models: {} }}
							<div class="model-provider-row">
								<div class="model-provider-head">
									<div class="model-provider-title-row">
										<strong>{provider.label}</strong>
										<button class="ghost-btn model-provider-edit" onclick={() => openEditProvider(provider)} disabled={modelSettingsLoading}>{t().editButton}</button>
									</div>
									<div class="model-provider-head-actions">
										<span class="model-key-state">{serviceIdLabel(provider.id)}</span>
									</div>
								</div>
								<label>
									<span>{t().settingsModelBaseUrl}</span>
									<div class="model-base-url-row">
										<input
											value={baseUrlValue(provider.id, setting)}
											oninput={(e) => setBaseUrlDraft(provider.id, (e.currentTarget as HTMLInputElement).value)}
										/>
										<button
											class="ghost-btn model-base-url-save"
											onclick={() => saveBaseUrl(provider.id, setting)}
											disabled={modelSettingsLoading || !baseUrlChanged(provider.id, setting)}
										>{t().profileSaveButton}</button>
									</div>
								</label>
								<label>
									<span>{t().settingsModelApiKey}</span>
									<div class="model-api-key-row">
										<input
											type="text"
											autocomplete="off"
											autocapitalize="off"
											spellcheck="false"
											value={apiKeyInputValue(setting)}
											placeholder={setting.api_key_set ? t().settingsModelKeepApiKey : t().settingsModelApiKeyPlaceholder}
											disabled={setting.api_key_set}
											oninput={(e) => onUpdateModelProvider(provider.id, { api_key: (e.currentTarget as HTMLInputElement).value, clear_api_key: false })}
										/>
										{#if hasPendingApiKey(setting)}
											<button
												class="ghost-btn primary-inline model-key-delete"
												onclick={() => onSaveModelProvider(provider.id)}
												disabled={modelSettingsLoading}
											>{t().profileSaveButton}</button>
										{:else}
											<button
												class="ghost-btn model-key-delete"
												onclick={() => onAskClearModelApiKey(provider.id)}
												disabled={!setting.api_key_set || modelSettingsLoading}
											>{t().deleteButton}</button>
										{/if}
									</div>
								</label>
								<div class="model-publish-summary" aria-label={t().settingsModelPublishedModels}>
									<div class="model-publish-head">
										<div class="model-publish-title">{t().settingsModelPublishedModels}</div>
										<button class="ghost-btn model-fetch-btn" onclick={() => openModelPicker(provider.id)} disabled={modelSettingsLoading}>{t().settingsModelSelectModels}</button>
									</div>
									{#each ['llm', 'vision'] as purpose}
										<div class="model-publish-title">{purpose === 'llm' ? 'LLM' : 'Vision'}</div>
										{#if selectedModels(provider, setting, purpose as 'llm' | 'vision').length}
											<div class="model-publish-selected">
												{#each selectedModels(provider, setting, purpose as 'llm' | 'vision') as model, modelIndex (`${purpose}:${model.id}:${modelIndex}`)}
													<span>{model.label}{model.notes ? ` - ${model.notes}` : ''}</span>
												{/each}
											</div>
										{:else}<div class="model-publish-empty">{t().settingsModelNoPublishedModels}</div>{/if}
									{/each}
								</div>
								<div class="model-provider-actions">
									<button class="ghost-btn model-service-memo" onclick={() => openMemoProvider(provider)} disabled={modelSettingsLoading}>{t().settingsModelServiceMemoButton}</button>
									<button class="ghost-btn model-service-delete" onclick={() => onAskDeleteModelProvider(provider.id)} disabled={modelSettingsLoading}>{t().settingsModelDeleteService}</button>
								</div>
							</div>
						{/each}
					</div>
					{#if modelSettingsStatus}
						<div class="inline-message">{modelSettingsStatus}</div>
					{/if}
				</div>
				<div class="settings-inline-actions model-settings-footer-actions">
					<button class="ghost-btn" onclick={() => (showAddServiceDialog = true)} disabled={modelSettingsLoading}>{t().settingsModelAddServiceButton}</button>
				</div>
			{/if}
{#if showAddServiceDialog}
	<div class="modal-backdrop add-service-backdrop" onclick={() => (showAddServiceDialog = false)} aria-hidden="true"></div>
	<div class="add-service-dialog" role="dialog" aria-modal="true" tabindex="-1" onclick={(e) => e.stopPropagation()} onkeydown={(e) => e.stopPropagation()}>
		<div class="modal-head">
			<div class="catalog-modal-title">{t().settingsModelAddServiceTitle}</div>
			<button class="catalog-close" onclick={() => (showAddServiceDialog = false)}>×</button>
		</div>
		<div class="add-service-body">
			<div class="model-add-grid">
				<label>
					<span class="model-add-label-with-help">
						{t().settingsModelServiceId}
						<button type="button" class="model-key-info model-service-id-info" aria-label={t().settingsModelServiceIdHelp}>
							i
							<span class="model-key-tooltip model-service-id-tooltip">{t().settingsModelServiceIdHelp}</span>
						</button>
					</span>
					<input bind:value={newProviderId} placeholder="my-openai" />
				</label>
				<label>
					<span>{t().settingsModelServiceName}</span>
					<input bind:value={newProviderLabel} placeholder="My OpenAI-compatible server" />
				</label>
				<label>
					<span>{t().settingsModelServiceKind}</span>
					<select bind:value={newProviderKind}>
						<option value="openai_compatible">OpenAI compatible</option>
						<option value="anthropic">Claude API</option>
						<option value="gemini">Gemini API</option>
					</select>
				</label>
				<label>
					<span>{t().settingsModelBaseUrl}</span>
					<input bind:value={newProviderBaseUrl} placeholder="http://127.0.0.1:11434/v1" />
				</label>
				<label>
					<span>{t().settingsModelApiKey}</span>
					<input bind:value={newProviderApiKey} type="password" placeholder={t().settingsModelApiKeyPlaceholder} />
				</label>
			</div>
		</div>
		<div class="add-service-actions">
			<button class="ghost-btn" onclick={() => (showAddServiceDialog = false)}>{t().confirmCancel}</button>
			<button class="ghost-btn primary-inline" onclick={addModelProvider} disabled={modelSettingsLoading}>{t().addButton}</button>
		</div>
	</div>
{/if}

{#if editProviderId}
	<div class="modal-backdrop add-service-backdrop" onclick={() => (editProviderId = null)} aria-hidden="true"></div>
	<div class="service-edit-dialog" role="dialog" aria-modal="true" tabindex="-1" onclick={(e) => e.stopPropagation()} onkeydown={(e) => e.stopPropagation()}>
		<div class="modal-head">
			<div class="catalog-modal-title">{t().settingsModelEditServiceTitle}</div>
			<button class="catalog-close" onclick={() => (editProviderId = null)}>×</button>
		</div>
		<div class="add-service-body">
			<div class="model-add-grid">
				<div class="model-add-readonly-field">
					<span>{t().settingsModelServiceId}</span>
					<div class="readonly-service-id">{editProviderId}</div>
				</div>
				<label>
					<span>{t().settingsModelServiceName}</span>
					<input bind:value={editProviderLabel} />
				</label>
			</div>
		</div>
		<div class="add-service-actions">
			<button class="ghost-btn" onclick={() => (editProviderId = null)}>{t().confirmCancel}</button>
			<button class="ghost-btn primary-inline" onclick={saveEditProvider} disabled={modelSettingsLoading || !editProviderLabel.trim()}>{t().profileSaveButton}</button>
		</div>
	</div>
{/if}

{#if memoProviderId}
	<div class="modal-backdrop add-service-backdrop" onclick={() => (memoProviderId = null)} aria-hidden="true"></div>
	<div class="service-memo-dialog" role="dialog" aria-modal="true" tabindex="-1" onclick={(e) => e.stopPropagation()} onkeydown={(e) => e.stopPropagation()}>
		<div class="modal-head">
			<div class="catalog-modal-title">{t().settingsModelServiceMemoTitle(memoProviderLabel)}</div>
			<button class="catalog-close" onclick={() => (memoProviderId = null)}>×</button>
		</div>
		<div class="add-service-body">
			<label class="model-service-memo-field">
				<span>{t().settingsModelServiceMemoLabel}</span>
				<textarea
					bind:value={memoProviderText}
					rows="8"
					spellcheck="false"
					placeholder={t().settingsModelServiceMemoPlaceholder}
				></textarea>
			</label>
		</div>
		<div class="add-service-actions">
			<button class="ghost-btn" onclick={() => (memoProviderId = null)}>{t().confirmCancel}</button>
			<button class="ghost-btn primary-inline" onclick={saveMemoProvider} disabled={modelSettingsLoading}>{t().profileSaveButton}</button>
		</div>
	</div>
{/if}

{#if modelPickerProvider && modelPickerSetting}
	<div class="modal-backdrop model-picker-backdrop" onclick={closeModelPicker} aria-hidden="true"></div>
	<div class="model-picker-dialog" role="dialog" aria-modal="true" tabindex="-1" onclick={(e) => e.stopPropagation()} onkeydown={(e) => e.stopPropagation()}>
		<div class="modal-head">
			<div class="catalog-modal-title">{t().settingsModelSelectModelsTitle(modelPickerProvider.label)}</div>
			<button class="catalog-close" onclick={closeModelPicker}>×</button>
		</div>
		<div class="model-picker-body">
			<div class="model-picker-actions">
				<button class="ghost-btn" onclick={fetchModelPickerModels} disabled={modelSettingsLoading}>{t().settingsModelFetchModels}</button>
				<button class="ghost-btn" onclick={() => setAllPublishedModels(filteredModelPickerModels, true)} disabled={modelSettingsLoading}>{t().settingsModelSelectAll}</button>
				<button class="ghost-btn" onclick={() => setAllPublishedModels(filteredModelPickerModels, false)} disabled={modelSettingsLoading}>{t().settingsModelClearAll}</button>
			</div>
			<input
				class="model-picker-search"
				type="search"
				bind:value={modelPickerSearch}
				placeholder={t().settingsModelSearchPlaceholder}
				aria-label={t().settingsModelSearchPlaceholder}
				autocomplete="off"
				spellcheck="false"
			/>
			<div class="model-picker-list" aria-label={t().settingsModelPublishedModels}>
				{#each filteredModelPickerModels as model, modelIndex (`${model.id}:${modelIndex}`)}
					<div class="model-picker-entry">
						<label class="check-row model-picker-row model-metadata-hover">
							<input
								type="checkbox"
								checked={modelPickerDraftEnabled(model.id)}
								onchange={(e) => {
									modelPickerEnabledDraft = {
										...modelPickerEnabledDraft,
										[model.id]: (e.currentTarget as HTMLInputElement).checked,
									};
								}}
							/>
							<span>{model.label}{model.notes ? ` - ${model.notes}` : ''}</span>
							<span class="model-purpose-label">
								<button type="button" class:active={modelPurposeSelected(model.id, 'llm')} onclick={(event) => { event.preventDefault(); toggleModelPurpose(model.id, 'llm'); }}>LLM</button>
								<button type="button" class:active={modelPurposeSelected(model.id, 'vision')} onclick={(event) => { event.preventDefault(); toggleModelPurpose(model.id, 'vision'); }}>Vision</button>
							</span>
							<ModelMetaCard model={modelDraft(model)} {isJapanese} />
						</label>
						<details class="model-metadata-editor">
							<summary>評価設定 / Model metadata</summary>
							<div class="model-metadata-fields">
								<label><span>オススメ度 / Recommendation</span><select value={modelDraft(model).recommendation_level ?? 0} onchange={(event) => updateModelMetadata(model, { recommendation_level: Number(event.currentTarget.value) || undefined })}><option value="0">—</option>{#each [1, 2, 3, 4, 5] as level}<option value={level}>{level} / 5</option>{/each}</select></label>
								<label><span>速度区分 / Speed class</span><select value={modelDraft(model).speed_class ?? ''} onchange={(event) => updateModelMetadata(model, { speed_class: event.currentTarget.value || undefined })}><option value="">—</option><option value="ultra-fast">ultra-fast</option><option value="fast">fast</option><option value="medium">medium</option><option value="slow">slow</option><option value="low-speed-outlier">low-speed-outlier</option></select></label>
								<label class="wide"><span>実測値に基づく速度ラベル / Measured speed label</span><input value={modelDraft(model).speed_label ?? ''} oninput={(event) => updateModelMetadata(model, { speed_label: event.currentTarget.value })} /></label>
								<label class="wide"><span>評価コメント（日本語）</span><textarea rows="2" value={modelDraft(model).comment_ja ?? ''} oninput={(event) => updateModelMetadata(model, { comment_ja: event.currentTarget.value })}></textarea></label>
								<label class="wide"><span>Evaluation comment (English)</span><textarea rows="2" value={modelDraft(model).comment_en ?? ''} oninput={(event) => updateModelMetadata(model, { comment_en: event.currentTarget.value })}></textarea></label>
							</div>
						</details>
					</div>
				{/each}
			</div>
		</div>
		<div class="model-picker-footer">
			{#if modelFetchResults[modelPickerProvider.id]}
				<div class:error={modelFetchResults[modelPickerProvider.id].type === 'error'} class="model-picker-result">{modelFetchResults[modelPickerProvider.id].message}</div>
			{/if}
			<button class="ghost-btn" onclick={closeModelPicker}>{t().confirmCancel}</button>
			<button class="ghost-btn primary-inline" onclick={saveModelPicker} disabled={modelSettingsLoading}>{t().profileSaveButton}</button>
		</div>
	</div>
{/if}
