<script lang="ts">
	import { tick } from 'svelte';
	import { t } from '$lib/i18n/index.svelte';
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
	let modelPickerFilter = $state<'all' | 'published' | 'unpublished' | 'llm' | 'vision'>('all');
	let modelPickerEnabledDraft = $state<Record<string, boolean>>({});
	let modelPickerPurposeDraft = $state<Record<string, ('llm' | 'vision')[]>>({});
	let modelPickerMetadataDraft = $state<Record<string, ModelOption>>({});
	let modelPickerInitialDraft = $state('');
	let modelPickerError = $state<string | null>(null);
	let serviceDialogError = $state<string | null>(null);
	let activeProviderId = $state<Provider | null>(null);
	let editProviderId = $state<Provider | null>(null);
	let editProviderLabel = $state('');
	let memoProviderId = $state<Provider | null>(null);
	let memoProviderLabel = $state('');
	let memoProviderText = $state('');
	let baseUrlDrafts = $state<Record<string, string>>({});

	function trapDialogFocus(node: HTMLElement, close: () => void) {
		const opener = document.activeElement instanceof HTMLElement ? document.activeElement : null;
		const focusable = () => Array.from(node.querySelectorAll<HTMLElement>('a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), summary, textarea:not([disabled]), [tabindex]:not([tabindex="-1"])')).filter((element) => element.tabIndex >= 0 && element.getClientRects().length > 0);
		const onKeydown = (event: KeyboardEvent) => {
			if (!node.isConnected) return;
			if (event.key === 'Escape') {
				event.preventDefault();
				event.stopPropagation();
				close();
				return;
			}
			if (event.key !== 'Tab') return;
			event.stopPropagation();
			const elements = focusable();
			if (!elements.length) {
				event.preventDefault();
				node.focus();
				return;
			}
			const active = document.activeElement as HTMLElement | null;
			if (!active || !node.contains(active)) {
				event.preventDefault();
				(event.shiftKey ? elements[elements.length - 1] : elements[0])?.focus();
			} else if (event.shiftKey && (active === elements[0] || active === node)) {
				event.preventDefault();
				elements[elements.length - 1]?.focus();
			} else if (!event.shiftKey && active === elements[elements.length - 1]) {
				event.preventDefault();
				elements[0].focus();
			}
		};
		document.addEventListener('keydown', onKeydown);
		void tick().then(() => {
			if (node.isConnected) node.querySelector<HTMLElement>('[data-dialog-focus]')?.focus();
		});
		return {
			destroy() {
				document.removeEventListener('keydown', onKeydown);
				if (opener?.isConnected) opener.focus();
			}
		};
	}

	async function addModelProvider() {
		const id = newProviderId.trim().toLowerCase();
		const label = newProviderLabel.trim() || id;
		if (!id || !label || !newProviderBaseUrl.trim()) return;
		serviceDialogError = null;
		try {
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
		} catch {
			serviceDialogError = modelSettingsStatus ?? t().settingsLoadFailed;
			return;
		}
		newProviderId = '';
		newProviderLabel = '';
		newProviderKind = 'openai_compatible';
		newProviderBaseUrl = '';
		newProviderApiKey = '';
		showAddServiceDialog = false;
	}

	function openEditProvider(provider: ProviderGroup) {
		serviceDialogError = null;
		editProviderId = provider.id;
		editProviderLabel = provider.label;
	}

	async function saveEditProvider() {
		if (!editProviderId || !editProviderLabel.trim()) return;
		if (await onSaveModelProviderName(editProviderId, editProviderLabel.trim())) {
			editProviderId = null;
			editProviderLabel = '';
		} else serviceDialogError = modelSettingsStatus ?? t().settingsLoadFailed;
	}

	function openMemoProvider(provider: ProviderGroup) {
		serviceDialogError = null;
		memoProviderId = provider.id;
		memoProviderLabel = provider.label;
		memoProviderText = provider.memo ?? '';
	}

	async function saveMemoProvider() {
		if (!memoProviderId) return;
		if (await onSaveModelProviderMemo(memoProviderId, memoProviderText)) {
			memoProviderId = null;
			memoProviderLabel = '';
			memoProviderText = '';
		} else serviceDialogError = modelSettingsStatus ?? t().settingsLoadFailed;
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
		const saved = await onSaveModelProvider(provider, { base_url: value });
		if (!saved) return;
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
		modelPickerFilter = 'all';
		modelPickerEnabledDraft = { ...(setting?.enabled_models ?? {}) };
		const catalogProvider = providerGroups.find((group) => group.id === provider);
		modelPickerPurposeDraft = Object.fromEntries((catalogProvider?.models ?? []).map((model) => [model.id, model.purposes ?? ['llm']]));
		modelPickerMetadataDraft = Object.fromEntries((catalogProvider?.models ?? []).map((model) => [model.id, { ...model }]));
		modelPickerError = null;
		modelPickerInitialDraft = pickerDraftSignature(catalogProvider?.models ?? []);
		modelPickerProviderId = provider;
	}

	function closeModelPicker() {
		modelPickerProviderId = null;
		modelPickerSearch = '';
		modelPickerFilter = 'all';
		modelPickerEnabledDraft = {};
		modelPickerPurposeDraft = {};
		modelPickerMetadataDraft = {};
		modelPickerInitialDraft = '';
		modelPickerError = null;
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

	function pickerDraftSignature(models: ModelOption[]): string {
		return JSON.stringify({
			enabled: modelPickerEnabledDraft,
			purposes: modelPickerPurposeDraft,
			models: models.map((model) => modelDraft(model)),
		});
	}

	function updateModelMetadata(model: ModelOption, patch: Partial<ModelOption>): void {
		modelPickerMetadataDraft = {
			...modelPickerMetadataDraft,
			[model.id]: { ...modelDraft(model), ...patch },
		};
	}

	function serviceIdLabel(provider: Provider): string {
		return `${t().settingsModelServiceId}: ${provider}`;
	}

	async function saveModelPicker() {
		if (!modelPickerProvider) return;
		const models = modelPickerProvider.models.map((model) => modelDraft(model));
		modelPickerError = null;
		const saved = await onSaveModelProvider(modelPickerProvider.id, { models, enabled_models: modelPickerEnabledDraft });
		if (saved) closeModelPicker();
		else modelPickerError = modelSettingsStatus ?? t().settingsLoadFailed;
	}

	async function fetchModelPickerModels() {
		if (!modelPickerProvider || modelPickerDirty) return;
		const providerId = modelPickerProvider.id;
		await onFetchModelList(providerId);
		const setting = modelSettings?.providers[providerId];
		modelPickerEnabledDraft = { ...(setting?.enabled_models ?? {}) };
		const provider = providerGroups.find((group) => group.id === providerId);
		modelPickerPurposeDraft = Object.fromEntries((provider?.models ?? []).map((model) => [model.id, model.purposes ?? ['llm']]));
		modelPickerMetadataDraft = Object.fromEntries((provider?.models ?? []).map((model) => [model.id, { ...model }]));
		modelPickerInitialDraft = pickerDraftSignature(provider?.models ?? []);
	}

	function hasPendingApiKey(setting: ModelProviderSetting): boolean {
		return !setting.api_key_set && !!setting.api_key?.trim();
	}

	function apiKeyInputValue(setting: ModelProviderSetting): string {
		return setting.api_key_set ? '' : (setting.api_key ?? '');
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
	const activeProvider = $derived(settingsProviderGroups.find((provider) => provider.id === activeProviderId) ?? settingsProviderGroups[0] ?? null);
	const activeProviderSetting = $derived(
		activeProvider && modelSettings
			? (modelSettings.providers[activeProvider.id] ?? { base_url: '', api_key_set: false, api_key_hint: null, enabled_models: {} })
			: null
	);
	const modelPickerDirty = $derived(modelPickerProvider ? pickerDraftSignature(modelPickerProvider.models) !== modelPickerInitialDraft : false);
	const modelPickerPublishedCount = $derived(
		modelPickerProvider ? modelPickerProvider.models.filter((model) => modelPickerDraftEnabled(model.id)).length : 0
	);

	function publishedModelCount(provider: ProviderGroup, setting: ModelProviderSetting): number {
		return provider.models.filter((model) => modelEnabled(setting, model.id)).length;
	}
	const filteredModelPickerModels = $derived.by(() => {
		const provider = modelPickerProvider;
		if (!provider) return [];
		const query = modelPickerSearch.trim().toLowerCase();
		return sortModels(
			provider.models.filter((model) => {
				const text = `${model.id} ${model.label ?? ''} ${model.notes ?? ''} ${model.speed_label ?? ''} ${model.comment_ja ?? ''} ${model.comment_en ?? ''}`.toLowerCase();
				if (!text.includes(query)) return false;
				if (modelPickerFilter === 'published') return modelPickerDraftEnabled(model.id);
				if (modelPickerFilter === 'unpublished') return !modelPickerDraftEnabled(model.id);
				if (modelPickerFilter === 'llm' || modelPickerFilter === 'vision') return modelPurposeSelected(model.id, modelPickerFilter);
				return true;
			})
		);
	});

</script>


		{#if modelSettingsLoading && !modelSettings}
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
				<div class="model-provider-selector" aria-label={t().settingsModelConnectionsTitle}>
					{#each settingsProviderGroups as provider (provider.id)}
						{@const setting = modelSettings.providers[provider.id] ?? { base_url: '', api_key_set: false, api_key_hint: null, enabled_models: {} }}
						<button
							type="button"
							class="model-provider-choice"
							class:active={activeProvider?.id === provider.id}
							aria-pressed={activeProvider?.id === provider.id}
							onclick={() => (activeProviderId = provider.id)}
						>
							<span class="model-provider-choice-label">{provider.label}</span>
							<span class="model-provider-choice-meta">{provider.id} · {setting.api_key_set ? t().settingsModelApiKeySet : t().settingsModelApiKeyUnset}</span>
							<span class="model-provider-choice-count">{t().settingsModelPublishedCount(publishedModelCount(provider, setting))}</span>
						</button>
					{/each}
				</div>
				{#if activeProvider && activeProviderSetting}
					<div class="model-provider-editor">
						<div class="model-provider-editor-head">
							<div><strong>{activeProvider.label}</strong><span>{serviceIdLabel(activeProvider.id)}</span></div>
							<button class="ghost-btn model-provider-edit" onclick={() => openEditProvider(activeProvider)} disabled={modelSettingsLoading}>{t().editButton}</button>
						</div>
						<section class="model-publish-summary" aria-label={t().settingsModelPublishedModels}>
							<div class="model-publish-head">
								<div><div class="model-publish-title">{t().settingsModelPublishedModels}</div><strong>{t().settingsModelPublishedCount(publishedModelCount(activeProvider, activeProviderSetting))}</strong></div>
								<button class="ghost-btn primary-inline" onclick={() => openModelPicker(activeProvider.id)} disabled={modelSettingsLoading}>{t().settingsModelSelectModels}</button>
							</div>
							{#if selectedModels(activeProvider, activeProviderSetting, 'llm').length || selectedModels(activeProvider, activeProviderSetting, 'vision').length}
								<div class="model-publish-selected">
									{#each ['llm', 'vision'] as purpose}
										{#each selectedModels(activeProvider, activeProviderSetting, purpose as 'llm' | 'vision') as model, modelIndex (`${purpose}:${model.id}:${modelIndex}`)}
											<span>{purpose === 'llm' ? 'LLM' : 'Vision'} · {model.label}</span>
										{/each}
									{/each}
								</div>
							{:else}<div class="model-publish-empty">{t().settingsModelNoPublishedModels}</div>{/if}
						</section>
						<details class="model-connection-details">
							<summary>{t().settingsModelConnectionDetails}</summary>
							<div class="model-connection-fields">
								<label><span>{t().settingsModelBaseUrl}</span><div class="model-base-url-row"><input value={baseUrlValue(activeProvider.id, activeProviderSetting)} oninput={(e) => setBaseUrlDraft(activeProvider!.id, (e.currentTarget as HTMLInputElement).value)} /><button class="ghost-btn" onclick={() => saveBaseUrl(activeProvider!.id, activeProviderSetting!)} disabled={modelSettingsLoading || !baseUrlChanged(activeProvider.id, activeProviderSetting)}>{t().profileSaveButton}</button></div></label>
								<label><span>{t().settingsModelApiKey}</span><div class="model-api-key-row"><input type="password" autocomplete="off" autocapitalize="off" spellcheck="false" value={apiKeyInputValue(activeProviderSetting)} placeholder={activeProviderSetting.api_key_set ? t().settingsModelKeepApiKey : t().settingsModelApiKeyPlaceholder} disabled={activeProviderSetting.api_key_set} oninput={(e) => onUpdateModelProvider(activeProvider!.id, { api_key: (e.currentTarget as HTMLInputElement).value, clear_api_key: false })} />{#if hasPendingApiKey(activeProviderSetting)}<button class="ghost-btn primary-inline" onclick={() => onSaveModelProvider(activeProvider!.id)} disabled={modelSettingsLoading}>{t().profileSaveButton}</button>{:else}<button class="ghost-btn" onclick={() => onAskClearModelApiKey(activeProvider!.id)} disabled={!activeProviderSetting.api_key_set || modelSettingsLoading}>{t().deleteButton}</button>{/if}</div></label>
								<div class="model-connection-actions"><button class="ghost-btn" onclick={() => openMemoProvider(activeProvider!)} disabled={modelSettingsLoading}>{t().settingsModelServiceMemoButton}</button><button class="ghost-btn model-service-delete" onclick={() => onAskDeleteModelProvider(activeProvider!.id)} disabled={modelSettingsLoading}>{t().settingsModelDeleteService}</button></div>
							</div>
						</details>
					</div>
				{/if}
				{#if modelSettingsStatus}
						<div class="inline-message">{modelSettingsStatus}</div>
					{/if}
				</div>
				<div class="settings-inline-actions model-settings-footer-actions">
				<button class="ghost-btn" onclick={() => { serviceDialogError = null; showAddServiceDialog = true; }} disabled={modelSettingsLoading}>{t().settingsModelAddServiceButton}</button>
				</div>
			{/if}
{#if showAddServiceDialog}
	<div class="modal-backdrop add-service-backdrop" onclick={() => (showAddServiceDialog = false)} aria-hidden="true"></div>
		<div class="add-service-dialog" role="dialog" aria-modal="true" aria-labelledby="add-service-title" tabindex="-1" data-settings-nested-dialog use:trapDialogFocus={() => (showAddServiceDialog = false)}>
			<div class="modal-head">
				<div id="add-service-title" class="catalog-modal-title">{t().settingsModelAddServiceTitle}</div>
				<button class="catalog-close" aria-label={t().closeLabel} onclick={() => (showAddServiceDialog = false)}>×</button>
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
						<input bind:value={newProviderId} placeholder="my-openai" data-dialog-focus />
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
						<input bind:value={newProviderApiKey} type="password" autocomplete="new-password" autocapitalize="off" spellcheck="false" placeholder={t().settingsModelApiKeyPlaceholder} />
				</label>
				</div>
			</div>
			{#if serviceDialogError}<div class="model-dialog-error" role="alert">{serviceDialogError}</div>{/if}
			<div class="add-service-actions">
			<button class="ghost-btn" onclick={() => (showAddServiceDialog = false)}>{t().confirmCancel}</button>
			<button class="ghost-btn primary-inline" onclick={addModelProvider} disabled={modelSettingsLoading}>{t().addButton}</button>
		</div>
	</div>
{/if}

{#if editProviderId}
	<div class="modal-backdrop add-service-backdrop" onclick={() => (editProviderId = null)} aria-hidden="true"></div>
		<div class="service-edit-dialog" role="dialog" aria-modal="true" aria-labelledby="edit-service-title" tabindex="-1" data-settings-nested-dialog use:trapDialogFocus={() => (editProviderId = null)}>
			<div class="modal-head">
				<div id="edit-service-title" class="catalog-modal-title">{t().settingsModelEditServiceTitle}</div>
				<button class="catalog-close" aria-label={t().closeLabel} onclick={() => (editProviderId = null)}>×</button>
		</div>
		<div class="add-service-body">
			<div class="model-add-grid">
				<div class="model-add-readonly-field">
					<span>{t().settingsModelServiceId}</span>
					<div class="readonly-service-id">{editProviderId}</div>
				</div>
				<label>
					<span>{t().settingsModelServiceName}</span>
						<input bind:value={editProviderLabel} data-dialog-focus />
				</label>
				</div>
			</div>
			{#if serviceDialogError}<div class="model-dialog-error" role="alert">{serviceDialogError}</div>{/if}
			<div class="add-service-actions">
			<button class="ghost-btn" onclick={() => (editProviderId = null)}>{t().confirmCancel}</button>
			<button class="ghost-btn primary-inline" onclick={saveEditProvider} disabled={modelSettingsLoading || !editProviderLabel.trim()}>{t().profileSaveButton}</button>
		</div>
	</div>
{/if}

{#if memoProviderId}
	<div class="modal-backdrop add-service-backdrop" onclick={() => (memoProviderId = null)} aria-hidden="true"></div>
		<div class="service-memo-dialog" role="dialog" aria-modal="true" aria-labelledby="service-memo-title" tabindex="-1" data-settings-nested-dialog use:trapDialogFocus={() => (memoProviderId = null)}>
			<div class="modal-head">
				<div id="service-memo-title" class="catalog-modal-title">{t().settingsModelServiceMemoTitle(memoProviderLabel)}</div>
				<button class="catalog-close" aria-label={t().closeLabel} onclick={() => (memoProviderId = null)}>×</button>
		</div>
		<div class="add-service-body">
			<label class="model-service-memo-field">
				<span>{t().settingsModelServiceMemoLabel}</span>
				<textarea
					bind:value={memoProviderText}
						rows="8"
						data-dialog-focus
					spellcheck="false"
					placeholder={t().settingsModelServiceMemoPlaceholder}
				></textarea>
				</label>
			</div>
			{#if serviceDialogError}<div class="model-dialog-error" role="alert">{serviceDialogError}</div>{/if}
			<div class="add-service-actions">
			<button class="ghost-btn" onclick={() => (memoProviderId = null)}>{t().confirmCancel}</button>
			<button class="ghost-btn primary-inline" onclick={saveMemoProvider} disabled={modelSettingsLoading}>{t().profileSaveButton}</button>
		</div>
	</div>
{/if}

	{#if modelPickerProvider && modelPickerSetting}
		<div class="modal-backdrop model-picker-backdrop" onclick={closeModelPicker} aria-hidden="true"></div>
		<div class="model-picker-dialog" role="dialog" aria-modal="true" aria-labelledby="model-picker-title" tabindex="-1" data-settings-nested-dialog use:trapDialogFocus={closeModelPicker}>
			<div class="modal-head">
				<div id="model-picker-title" class="catalog-modal-title">{t().settingsModelSelectModelsTitle(modelPickerProvider.label)}</div>
				<button class="catalog-close" aria-label={t().closeLabel} onclick={closeModelPicker}>×</button>
			</div>
			<div class="model-picker-toolbar">
				<input
					class="model-picker-search"
					type="search"
					bind:value={modelPickerSearch}
					placeholder={t().settingsModelSearchPlaceholder}
					aria-label={t().settingsModelSearchPlaceholder}
					autocomplete="off"
					spellcheck="false"
					data-dialog-focus
				/>
				<label class="model-picker-filter"><span>{t().settingsModelFilterLabel}</span><select bind:value={modelPickerFilter}><option value="all">{t().settingsModelFilterAll}</option><option value="published">{t().settingsModelFilterPublished}</option><option value="unpublished">{t().settingsModelFilterUnpublished}</option><option value="llm">{t().settingsModelFilterLlm}</option><option value="vision">{t().settingsModelFilterVision}</option></select></label>
				<div class="model-picker-actions">
					<button class="ghost-btn" title={modelPickerDirty ? t().settingsModelFetchDisabledWhileDirty : undefined} onclick={fetchModelPickerModels} disabled={modelSettingsLoading || modelPickerDirty}>{t().settingsModelFetchModels}</button>
					<button class="ghost-btn" onclick={() => setAllPublishedModels(filteredModelPickerModels, true)} disabled={modelSettingsLoading}>{t().settingsModelSelectVisible}</button>
					<button class="ghost-btn" onclick={() => setAllPublishedModels(filteredModelPickerModels, false)} disabled={modelSettingsLoading}>{t().settingsModelClearVisible}</button>
				</div>
				<div class="model-picker-count">{t().settingsModelPickerCount(filteredModelPickerModels.length, modelPickerProvider.models.length)}</div>
			</div>
			<div class="model-picker-body">
				<div class="model-picker-list" aria-label={t().settingsModelPublishedModels}>
					{#each filteredModelPickerModels as model, modelIndex (`${model.id}:${modelIndex}`)}
						<article class="model-picker-entry">
							<div class="model-picker-row">
								<label class="model-picker-publish">
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
									<span><strong>{model.label}</strong><small>{model.id}</small>{#if model.notes}<em>{model.notes}</em>{/if}</span>
								</label>
								<div class="model-purpose-controls" aria-label={`${model.label} LLM / Vision`}>
									<button type="button" class:active={modelPurposeSelected(model.id, 'llm')} aria-pressed={modelPurposeSelected(model.id, 'llm')} onclick={() => toggleModelPurpose(model.id, 'llm')}>LLM</button>
									<button type="button" class:active={modelPurposeSelected(model.id, 'vision')} aria-pressed={modelPurposeSelected(model.id, 'vision')} onclick={() => toggleModelPurpose(model.id, 'vision')}>Vision</button>
								</div>
							</div>
							<details class="model-metadata-editor">
								<summary>{t().settingsModelMetadataDetails}</summary>
							<div class="model-metadata-fields">
								<label><span>オススメ度 / Recommendation</span><select value={modelDraft(model).recommendation_level ?? 0} onchange={(event) => updateModelMetadata(model, { recommendation_level: Number(event.currentTarget.value) || undefined })}><option value="0">—</option>{#each [1, 2, 3, 4, 5] as level}<option value={level}>{level} / 5</option>{/each}</select></label>
								<label><span>速度区分 / Speed class</span><select value={modelDraft(model).speed_class ?? ''} onchange={(event) => updateModelMetadata(model, { speed_class: event.currentTarget.value || undefined })}><option value="">—</option><option value="ultra-fast">ultra-fast</option><option value="fast">fast</option><option value="medium">medium</option><option value="slow">slow</option><option value="low-speed-outlier">low-speed-outlier</option></select></label>
								<label class="wide"><span>実測値に基づく速度ラベル / Measured speed label</span><input value={modelDraft(model).speed_label ?? ''} oninput={(event) => updateModelMetadata(model, { speed_label: event.currentTarget.value })} /></label>
								<label class="wide"><span>評価コメント（日本語）</span><textarea rows="2" value={modelDraft(model).comment_ja ?? ''} oninput={(event) => updateModelMetadata(model, { comment_ja: event.currentTarget.value })}></textarea></label>
								<label class="wide"><span>Evaluation comment (English)</span><textarea rows="2" value={modelDraft(model).comment_en ?? ''} oninput={(event) => updateModelMetadata(model, { comment_en: event.currentTarget.value })}></textarea></label>
								</div>
							</details>
						</article>
					{/each}
			</div>
		</div>
			<div class="model-picker-footer">
				<div class="model-picker-summary"><span>{t().settingsModelPublishedCount(modelPickerPublishedCount)}</span>{#if modelPickerDirty}<strong>{t().settingsModelDraftChanges}</strong>{/if}</div>
				{#if modelPickerError}
					<div class="model-picker-result error">{modelPickerError}</div>
				{:else if modelFetchResults[modelPickerProvider.id]}
					<div class:error={modelFetchResults[modelPickerProvider.id].type === 'error'} class="model-picker-result">{modelFetchResults[modelPickerProvider.id].message}</div>
			{/if}
			<button class="ghost-btn" onclick={closeModelPicker}>{t().confirmCancel}</button>
			<button class="ghost-btn primary-inline" onclick={saveModelPicker} disabled={modelSettingsLoading}>{t().profileSaveButton}</button>
		</div>
	</div>
{/if}
