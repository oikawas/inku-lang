<script lang="ts">
	import { t } from '$lib/i18n/index.svelte';
	import type { ExportTemplate } from '$lib/exportTemplates';
	import type { Provider, ProviderGroup } from '$lib/models';

	type PluginItem = {
		name: string;
		version: string;
		status: string;
	};
	type SettingsStatus = {
		database: {
			backend: string;
			driver: string;
			url: string;
			database: string | null;
			is_default: boolean;
			file_size_bytes: number | null;
			file_path: string | null;
			runtime_editable: boolean;
			note: string;
		};
		db_backup: {
			supported: boolean;
			interval_days: number;
			max_generations: number;
			last_auto_backup_at: number;
			backup_dir: string;
			auto_count: number;
			manual_count: number;
		};
		plugins: {
			enabled: boolean;
			loaded: PluginItem[];
			runtime_editable: boolean;
			note: string;
		};
		output_save: {
			enabled: boolean;
			output_dir: string;
			png_size: number;
			workers: number;
			queue_limit: number;
			submitted: number;
			completed: number;
			failed: number;
			skipped: number;
			note: string;
		};
	};
	type UserRole = 'admin' | 'group_lead' | 'user';
	type UserGroup = {
		id: string;
		name: string;
		at: number;
	};
	type UserItem = {
		id: string;
		username: string;
		email: string;
		role: UserRole;
		role_label: string;
		group_id: string | null;
		group_name: string | null;
		image_generation_count: number;
		at: number;
	};
	type SettingsMode = 'model' | 'settings';
	type SettingsTab = 'connection' | 'models' | 'db' | 'plugins' | 'users' | 'export' | 'misc' | 'server_misc';
	type ModelProviderSetting = {
		label?: string;
		kind?: string;
		default_base_url?: string;
		requires_api_key?: boolean;
		memo?: string;
		models?: { id: string; label: string; notes?: string }[];
		delete?: boolean;
		base_url: string;
		api_key_set: boolean;
		api_key_hint: string | null;
		api_key?: string;
		clear_api_key?: boolean;
		enabled_models?: Record<string, boolean>;
	};
	type ModelSettings = {
		providers: Record<string, ModelProviderSetting>;
	};
	type ModelFetchResult = {
		type: 'success' | 'error';
		message: string;
	};

	type Props = {
		settingsMode: SettingsMode;
		settingsTab: SettingsTab;
		stage1Provider: Provider;
		stage1Model: string;
		stage2Provider: Provider;
		stage2Model: string;
		providerGroups: ProviderGroup[];
		includeThinking: boolean;
		settingsStatus: SettingsStatus | null;
		settingsStatusError: string | null;
		settingsStatusLoading: boolean;
		modelSettings: ModelSettings | null;
		modelSettingsStatus: string | null;
		modelFetchResults: Record<string, ModelFetchResult>;
		modelSettingsLoading: boolean;
		dbBackupStatus: string | null;
		outputSaveStatus: string | null;
		currentUser: UserItem | null;
		userSettingsStatus: string | null;
		userSettingsLoading: boolean;
		loginUserName: string;
		loginPassword: string;
		users: UserItem[];
		groups: UserGroup[];
		newUserName: string;
		newUserEmail: string;
		newUserPassword: string;
		newUserRole: UserRole;
		newUserGroupId: string;
		selectedUserId: string | null;
		editUserName: string;
		editUserEmail: string;
		editUserPassword: string;
		editUserRole: UserRole;
		editUserGroupId: string;
		newGroupName: string;
		editGroupId: string | null;
		editGroupName: string;
		showKiwi: boolean;
		showCrab: boolean;
		pngAlphaWhite: boolean;
		exportTemplates: ExportTemplate[];
		exportTemplateStatus: string | null;
		saveReplayAsNewVersion: boolean;
		canvasAspectEnabled: boolean;
		onClose: () => void;
		onCloseSettings: () => void;
		onSelectSettingsTab: (tab: SettingsTab) => void;
		onSetStage1Provider: (provider: Provider) => void;
		onSetStage1Model: (model: string) => void;
		onSetStage2Provider: (provider: Provider) => void;
		onSetStage2Model: (model: string) => void;
		onUpdateModelProvider: (provider: Provider, patch: Partial<ModelProviderSetting>) => void;
		onAddModelProvider: (provider: Provider, patch: Partial<ModelProviderSetting>) => void;
		onAskDeleteModelProvider: (provider: Provider) => void;
		onAskClearModelApiKey: (provider: Provider) => void;
		onFetchModelList: (provider: Provider) => void | Promise<void>;
		onSaveModelProviderName: (provider: Provider, label: string) => void | Promise<void>;
		onSaveModelProviderMemo: (provider: Provider, memo: string) => void | Promise<void>;
		onSaveModelProvider: (provider: Provider) => void | Promise<void>;
		onSaveModelSettings: () => void | Promise<void>;
		onLoadModelSettings: () => void | Promise<void>;
		onLoadSettingsStatus: () => void;
		onUpdateDbBackupSettings: (intervalDays: number, maxGenerations: number) => void | Promise<void>;
		onRunDbBackupNow: () => void | Promise<void>;
		onUpdateOutputSaveSettings: (enabled: boolean, outputDir: string, pngSize: number) => void | Promise<void>;
		onLoadUserSettings: () => void;
		onLogin: () => void | Promise<void>;
		onLogout: () => void | Promise<void>;
		onAddUser: () => void | Promise<void>;
		onSetEditUser: (user: UserItem) => void;
		onClearEditUser: () => void;
		onSaveUserEdit: () => void | Promise<void>;
		onRemoveUser: (id: string) => void | Promise<void>;
		onAddGroup: () => void | Promise<void>;
		onRemoveGroup: (group: UserGroup) => void | Promise<void>;
		onSetEditGroup: (group: UserGroup) => void;
		onClearEditGroup: () => void;
		onSaveGroupEdit: () => void | Promise<void>;
		onSetCanvasAspectEnabled: (enabled: boolean) => void | Promise<void>;
		onAddExportTemplate: () => void | Promise<void>;
		onUpdateExportTemplate: (id: string, patch: Partial<ExportTemplate>) => void | Promise<void>;
		onRemoveExportTemplate: (id: string) => void | Promise<void>;
		onCancelModelSelection: () => void;
		onConfirmModelSelection: () => void;
	};

	let {
		settingsMode,
		settingsTab,
		stage1Provider,
		stage1Model,
		stage2Provider,
		stage2Model,
		providerGroups,
		includeThinking = $bindable(),
		settingsStatus,
		settingsStatusError,
		settingsStatusLoading,
		modelSettings = $bindable(),
		modelSettingsStatus,
		modelFetchResults,
		modelSettingsLoading,
		dbBackupStatus,
		outputSaveStatus,
		currentUser,
		userSettingsStatus,
		userSettingsLoading,
		loginUserName = $bindable(),
		loginPassword = $bindable(),
		users,
		groups,
		newUserName = $bindable(),
		newUserEmail = $bindable(),
		newUserPassword = $bindable(),
		newUserRole = $bindable(),
		newUserGroupId = $bindable(),
		selectedUserId,
		editUserName = $bindable(),
		editUserEmail = $bindable(),
		editUserPassword = $bindable(),
		editUserRole = $bindable(),
		editUserGroupId = $bindable(),
		newGroupName = $bindable(),
		editGroupId,
		editGroupName = $bindable(),
		showKiwi = $bindable(),
		showCrab = $bindable(),
		pngAlphaWhite = $bindable(),
		exportTemplates,
		exportTemplateStatus,
		saveReplayAsNewVersion = $bindable(),
		canvasAspectEnabled,
		onClose,
		onCloseSettings,
		onSelectSettingsTab,
		onSetStage1Provider,
		onSetStage1Model,
		onSetStage2Provider,
		onSetStage2Model,
		onUpdateModelProvider,
		onAddModelProvider,
		onAskDeleteModelProvider,
		onAskClearModelApiKey,
		onFetchModelList,
		onSaveModelProviderName,
		onSaveModelProviderMemo,
		onSaveModelProvider,
		onSaveModelSettings,
		onLoadModelSettings,
		onLoadSettingsStatus,
		onUpdateDbBackupSettings,
		onRunDbBackupNow,
		onUpdateOutputSaveSettings,
		onLoadUserSettings,
		onLogin,
		onLogout,
		onAddUser,
		onSetEditUser,
		onClearEditUser,
		onSaveUserEdit,
		onRemoveUser,
		onAddGroup,
		onRemoveGroup,
		onSetEditGroup,
		onClearEditGroup,
		onSaveGroupEdit,
		onSetCanvasAspectEnabled,
		onAddExportTemplate,
		onUpdateExportTemplate,
		onRemoveExportTemplate,
		onCancelModelSelection,
		onConfirmModelSelection,
	}: Props = $props();

	const USER_ROLE_OPTIONS: UserRole[] = ['admin', 'group_lead', 'user'];
	const isAdmin = $derived(currentUser?.role === 'admin');
	let newProviderId = $state('');
	let newProviderLabel = $state('');
	let newProviderKind = $state('openai_compatible');
	let newProviderBaseUrl = $state('');
	let newProviderApiKey = $state('');
	let showAddServiceDialog = $state(false);
	let modelPickerProviderId = $state<Provider | null>(null);
	let editProviderId = $state<Provider | null>(null);
	let editProviderLabel = $state('');
	let memoProviderId = $state<Provider | null>(null);
	let memoProviderLabel = $state('');
	let memoProviderText = $state('');
	let baseUrlDrafts = $state<Record<string, string>>({});

	function modelsFor(provider: Provider) {
		return providerGroups.find((group) => group.id === provider)?.models ?? [];
	}

	function addModelProvider() {
		const id = newProviderId.trim().toLowerCase();
		const label = newProviderLabel.trim() || id;
		if (!id || !label || !newProviderBaseUrl.trim()) return;
		onAddModelProvider(id, {
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

	function setAllPublishedModels(provider: Provider, models: { id: string }[], enabled: boolean) {
		onUpdateModelProvider(provider, {
			enabled_models: Object.fromEntries(models.map((model) => [model.id, enabled])),
		});
	}

	function modelEnabled(setting: ModelProviderSetting, modelId: string): boolean {
		return setting.enabled_models?.[modelId] !== false;
	}

	function hasPendingApiKey(setting: ModelProviderSetting): boolean {
		return !setting.api_key_set && !!setting.api_key?.trim();
	}

	function apiKeyInputValue(setting: ModelProviderSetting): string {
		return setting.api_key_set ? t().settingsModelKeepApiKey : (setting.api_key ?? '');
	}

	function selectedModels(provider: ProviderGroup, setting: ModelProviderSetting) {
		return provider.models.filter((model) => modelEnabled(setting, model.id));
	}

	const modelPickerProvider = $derived(providerGroups.find((provider) => provider.id === modelPickerProviderId) ?? null);
	const modelPickerSetting = $derived(
		modelPickerProviderId && modelSettings
			? (modelSettings.providers[modelPickerProviderId] ?? { base_url: '', api_key_set: false, api_key_hint: null, enabled_models: {} })
			: null
	);

	function formatBytes(bytes: number | null | undefined): string {
		if (bytes == null) return '-';
		if (bytes < 1024) return `${bytes} B`;
		const units = ['KB', 'MB', 'GB', 'TB'];
		let value = bytes / 1024;
		let unit = units[0];
		for (let i = 1; i < units.length && value >= 1024; i += 1) {
			value /= 1024;
			unit = units[i];
		}
		return `${value.toFixed(value >= 10 ? 1 : 2)} ${unit}`;
	}

	function formatTimestamp(ms: number): string {
		if (!ms) return '-';
		return new Date(ms).toLocaleString();
	}
</script>

<div class="modal-backdrop" onclick={onClose} aria-hidden="true"></div>
<div class="settings-modal" class:model-modal={settingsMode === 'model'} role="dialog" aria-modal="true" tabindex="-1" onclick={(e) => e.stopPropagation()} onkeydown={(e) => e.stopPropagation()}>
	<div class="modal-head">
		<div class="catalog-modal-title">{settingsMode === 'model' ? t().modelSelectButton : t().settingsTitle}</div>
		{#if settingsMode !== 'model'}
			<button class="catalog-close" onclick={onCloseSettings}>×</button>
		{/if}
	</div>
	{#if settingsMode === 'settings'}
		<div class="settings-tabs">
			{#if isAdmin}
				<button class:active={settingsTab === 'models'} onclick={() => onSelectSettingsTab('models')}>{t().settingsTabModels}</button>
			{/if}
			<button class:active={settingsTab === 'plugins'} onclick={() => onSelectSettingsTab('plugins')}>{t().settingsTabPlugins}</button>
			{#if isAdmin}
				<button class:active={settingsTab === 'users'} onclick={() => onSelectSettingsTab('users')}>{t().settingsTabUsers}</button>
				<button class:active={settingsTab === 'db'} onclick={() => onSelectSettingsTab('db')}>{t().settingsTabDb}</button>
				<button class:active={settingsTab === 'server_misc'} onclick={() => onSelectSettingsTab('server_misc')}>{t().settingsTabServerMisc}</button>
			{/if}
			<button class:active={settingsTab === 'export'} onclick={() => onSelectSettingsTab('export')}>{t().settingsTabExport}</button>
			<button class:active={settingsTab === 'misc'} onclick={() => onSelectSettingsTab('misc')}>{t().settingsTabMisc}</button>
		</div>
	{/if}
	<div class="settings-body">
		{#if settingsMode === 'model'}
			<div class="popover-group">
				<div class="popover-group-label">{t().stage1Label}</div>
				<div class="form-row">
					<label for="settings-stage1-provider">{t().providerLabel}</label>
					<select id="settings-stage1-provider" value={stage1Provider} onchange={(e) => onSetStage1Provider((e.currentTarget as HTMLSelectElement).value as Provider)}>
						{#each providerGroups as pg (pg.id)}<option value={pg.id}>{pg.label}</option>{/each}
					</select>
				</div>
				<div class="form-row">
					<label for="settings-stage1-model">{t().modelLabel}</label>
					<select id="settings-stage1-model" value={stage1Model} onchange={(e) => onSetStage1Model((e.currentTarget as HTMLSelectElement).value)}>
						{#each modelsFor(stage1Provider) as m (m.id)}<option value={m.id}>{m.label}{m.notes ? ` - ${m.notes}` : ''}</option>{/each}
					</select>
				</div>
				{#if stage1Model.includes('qwen3')}
					<label class="check-row">
						<input type="checkbox" bind:checked={includeThinking} />
						<span>{t().showThinkingLabel}</span>
					</label>
				{/if}
			</div>
			<div class="popover-group">
				<div class="popover-group-label">{t().stage2Label}</div>
				<div class="form-row">
					<label for="settings-stage2-provider">{t().providerLabel}</label>
					<select id="settings-stage2-provider" value={stage2Provider} onchange={(e) => onSetStage2Provider((e.currentTarget as HTMLSelectElement).value as Provider)}>
						{#each providerGroups as pg (pg.id)}<option value={pg.id}>{pg.label}</option>{/each}
					</select>
				</div>
				<div class="form-row">
					<label for="settings-stage2-model">{t().modelLabel}</label>
					<select id="settings-stage2-model" value={stage2Model} onchange={(e) => onSetStage2Model((e.currentTarget as HTMLSelectElement).value)}>
						{#each modelsFor(stage2Provider) as m (m.id)}<option value={m.id}>{m.label}{m.notes ? ` - ${m.notes}` : ''}</option>{/each}
					</select>
				</div>
			</div>
		{:else if settingsTab === 'models'}
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
						{#each providerGroups as provider (provider.id)}
							{@const setting = modelSettings.providers[provider.id] ?? { base_url: '', api_key_set: false, api_key_hint: null, enabled_models: {} }}
							<div class="model-provider-row">
								<div class="model-provider-head">
									<div class="model-provider-title-row">
										<strong>{provider.label}</strong>
										<button class="ghost-btn model-provider-edit" onclick={() => openEditProvider(provider)} disabled={modelSettingsLoading}>{t().editButton}</button>
									</div>
									<div class="model-provider-head-actions">
										<span class="model-key-state">
											{setting.api_key_set ? t().settingsModelApiKeySet : t().settingsModelApiKeyUnset}
											{#if !setting.api_key_set}
												<button type="button" class="model-key-info" aria-label={t().settingsModelApiKeyOptionalHint}>
													i
													<span class="model-key-tooltip">{t().settingsModelApiKeyOptionalHint}</span>
												</button>
											{/if}
										</span>
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
										<button class="ghost-btn model-fetch-btn" onclick={() => (modelPickerProviderId = provider.id)} disabled={modelSettingsLoading}>{t().settingsModelSelectModels}</button>
									</div>
									{#if selectedModels(provider, setting).length}
										<div class="model-publish-selected">
											{#each selectedModels(provider, setting) as model, modelIndex (`${model.id}:${modelIndex}`)}
												<span>{model.label}{model.notes ? ` - ${model.notes}` : ''}</span>
											{/each}
										</div>
									{:else}
										<div class="model-publish-empty">{t().settingsModelNoPublishedModels}</div>
									{/if}
								</div>
								<div class="model-provider-actions">
									<button class="ghost-btn model-service-delete" onclick={() => onAskDeleteModelProvider(provider.id)} disabled={modelSettingsLoading}>{t().settingsModelDeleteService}</button>
									<button class="ghost-btn model-service-memo" onclick={() => openMemoProvider(provider)} disabled={modelSettingsLoading}>{t().settingsModelServiceMemoButton}</button>
									<button class="ghost-btn primary-inline model-service-save" onclick={() => saveBaseUrl(provider.id, setting)} disabled={modelSettingsLoading}>{t().profileSaveButton}</button>
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
		{:else if settingsTab === 'db'}
			<div class="popover-group">
				<div class="popover-group-label">{t().settingsCurrentDb}</div>
				{#if settingsStatusLoading}
					<div class="inline-message">{t().settingsLoading}</div>
				{:else if settingsStatus}
					<div class="settings-readonly-grid">
						<span>Backend</span><strong>{settingsStatus.database.backend}</strong>
						<span>Driver</span><strong>{settingsStatus.database.driver}</strong>
						<span>URL</span><code>{settingsStatus.database.url}</code>
						<span>Database</span><strong>{settingsStatus.database.database ?? '-'}</strong>
						<span>Default</span><strong>{settingsStatus.database.is_default ? t().settingsYes : t().settingsNo}</strong>
						<span>{t().settingsDbFileSize}</span><strong>{formatBytes(settingsStatus.database.file_size_bytes)}</strong>
					</div>
					<div class="db-test-result">{settingsStatus.database.note}</div>
				{:else}
					<div class="inline-message">{settingsStatusError ?? t().settingsLoadFailed}</div>
				{/if}
			</div>
			<div class="popover-group">
				<div class="popover-group-label">{t().settingsDbBackupTitle}</div>
				{#if settingsStatusLoading}
					<div class="inline-message">{t().settingsLoading}</div>
				{:else if settingsStatus}
					{#if !settingsStatus.db_backup.supported}
						<div class="inline-message">{t().settingsDbBackupUnsupported}</div>
					{/if}
					<div class="db-backup-grid">
						<label>
							<span>{t().settingsDbBackupInterval}</span>
							<input
								type="number"
								min="1"
								max="365"
								value={settingsStatus.db_backup.interval_days}
								disabled={!settingsStatus.db_backup.supported}
								onchange={(e) => onUpdateDbBackupSettings(Number((e.currentTarget as HTMLInputElement).value), settingsStatus?.db_backup.max_generations ?? 4)}
							/>
						</label>
						<label>
							<span>{t().settingsDbBackupMaxGenerations}</span>
							<input
								type="number"
								min="1"
								max="100"
								value={settingsStatus.db_backup.max_generations}
								disabled={!settingsStatus.db_backup.supported}
								onchange={(e) => onUpdateDbBackupSettings(settingsStatus?.db_backup.interval_days ?? 7, Number((e.currentTarget as HTMLInputElement).value))}
							/>
						</label>
					</div>
					<div class="settings-readonly-grid compact">
						<span>{t().settingsDbBackupLastAuto}</span><strong>{formatTimestamp(settingsStatus.db_backup.last_auto_backup_at)}</strong>
						<span>Directory</span><code>{settingsStatus.db_backup.backup_dir}</code>
						<span>Saved</span><strong>{t().settingsDbBackupStoredCounts(settingsStatus.db_backup.auto_count, settingsStatus.db_backup.manual_count)}</strong>
					</div>
					{#if dbBackupStatus}
						<div class="inline-message">{dbBackupStatus}</div>
					{/if}
				{:else}
					<div class="inline-message">{settingsStatusError ?? t().settingsLoadFailed}</div>
				{/if}
			</div>
			<div class="settings-inline-actions">
				<button class="ghost-btn" onclick={onLoadSettingsStatus} disabled={settingsStatusLoading || currentUser?.role !== 'admin'}>{t().settingsReload}</button>
				<button class="ghost-btn primary-inline" onclick={onRunDbBackupNow} disabled={settingsStatusLoading || currentUser?.role !== 'admin' || !settingsStatus?.db_backup.supported}>{t().settingsDbBackupRunNow}</button>
			</div>
		{:else if settingsTab === 'server_misc'}
			<div class="popover-group">
				<div class="popover-group-label">{t().settingsOutputSaveTitle}</div>
				{#if settingsStatusLoading}
					<div class="inline-message">{t().settingsLoading}</div>
				{:else if settingsStatus}
					<label class="setting-toggle">
						<input
							type="checkbox"
							checked={settingsStatus.output_save.enabled}
							onchange={(e) => onUpdateOutputSaveSettings((e.currentTarget as HTMLInputElement).checked, settingsStatus?.output_save.output_dir ?? '', settingsStatus?.output_save.png_size ?? 2160)}
						/>
						<span>{t().settingsOutputSaveEnabled}</span>
					</label>
					<label class="server-path-row">
						<span>{t().settingsOutputSaveDir}</span>
						<div class="server-path-input-row">
							<input
								value={settingsStatus.output_save.output_dir}
								placeholder={t().settingsOutputSaveDirPlaceholder}
								onchange={(e) => onUpdateOutputSaveSettings(settingsStatus?.output_save.enabled ?? true, (e.currentTarget as HTMLInputElement).value, settingsStatus?.output_save.png_size ?? 2160)}
							/>
							<button class="ghost-btn primary-inline" onclick={() => onUpdateOutputSaveSettings(settingsStatus?.output_save.enabled ?? true, settingsStatus?.output_save.output_dir ?? '', settingsStatus?.output_save.png_size ?? 2160)}>{t().profileSaveButton}</button>
						</div>
					</label>
					<label class="server-path-row compact-control">
						<span>{t().settingsOutputSavePngSize}</span>
						<select
							value={String(settingsStatus.output_save.png_size)}
							onchange={(e) => onUpdateOutputSaveSettings(settingsStatus?.output_save.enabled ?? true, settingsStatus?.output_save.output_dir ?? '', Number((e.currentTarget as HTMLSelectElement).value))}
						>
							<option value="1080">1080px</option>
							<option value="2160">2160px</option>
						</select>
					</label>
					<div class="settings-readonly-grid compact">
						<span class="nowrap-label">
							{t().settingsOutputSaveWorkers}
							<span class="info-dot" aria-label={t().settingsOutputSaveWorkersHelp}>
								i
								<span class="info-tooltip">{t().settingsOutputSaveWorkersHelp}</span>
							</span>
						</span><strong>{settingsStatus.output_save.workers} / {settingsStatus.output_save.queue_limit}</strong>
						<span>{t().settingsOutputSaveStats}</span><strong>{settingsStatus.output_save.submitted} / {settingsStatus.output_save.completed} / {settingsStatus.output_save.failed} / {settingsStatus.output_save.skipped}</strong>
					</div>
					<div class="db-test-result">{t().settingsOutputSaveNoteLabel}: {t().settingsOutputSaveNote}</div>
					{#if outputSaveStatus}
						<div class="inline-message">{outputSaveStatus}</div>
					{/if}
				{:else}
					<div class="inline-message">{settingsStatusError ?? t().settingsLoadFailed}</div>
				{/if}
			</div>
			<div class="settings-inline-actions">
				<button class="ghost-btn" onclick={onLoadSettingsStatus} disabled={settingsStatusLoading || currentUser?.role !== 'admin'}>{t().settingsReloadSettings}</button>
			</div>
		{:else if settingsTab === 'plugins'}
			<div class="popover-group">
				<div class="popover-group-label">{t().settingsSystemPlugins}</div>
				<div class="system-plugin-panel">
					<div class="system-plugin-main">
						<div class="system-plugin-title-row">
							<div class="system-plugin-title">{t().settingsCanvasPluginTitle}</div>
							<span class="plugin-version-pill">v0.1.0</span>
						</div>
						<div class="system-plugin-desc">{t().settingsCanvasPluginDescription}</div>
					</div>
					<button
						type="button"
						class="plugin-switch"
						class:plugin-enabled={canvasAspectEnabled}
						role="switch"
						aria-checked={canvasAspectEnabled}
						disabled={!isAdmin}
						title={isAdmin ? '' : t().settingsPluginAdminOnly}
						onclick={() => { if (isAdmin) void onSetCanvasAspectEnabled(!canvasAspectEnabled); }}
					>
						<span class="switch-track"><span class="switch-knob"></span></span>
						<span class="switch-label">{canvasAspectEnabled ? t().settingsPluginEnabled : t().settingsPluginDisabled}</span>
					</button>
				</div>
				{#if !isAdmin}
					<div class="db-test-result">{t().settingsPluginAdminOnly}</div>
				{/if}
				{#if isAdmin && settingsStatusLoading}
					<div class="inline-message">{t().settingsLoading}</div>
				{:else if isAdmin && settingsStatusError}
					<div class="inline-message">{settingsStatusError}</div>
				{/if}
			</div>
			<div class="popover-group">
				<div class="popover-group-label">{t().settingsUserPlugins}</div>
				<div class="user-plugin-skeleton">
					<div>
						<div class="system-plugin-title">{t().settingsUserPluginsAddTitle}</div>
						<div class="system-plugin-desc">{t().settingsUserPluginsAddDescription}</div>
					</div>
					<div class="plugin-add">
						<input placeholder={t().settingsUserPluginPathPlaceholder} disabled />
						<button class="ghost-btn" disabled>{t().addButton}</button>
					</div>
				</div>
			</div>
			<div class="settings-inline-actions">
				<button class="ghost-btn" onclick={onLoadSettingsStatus} disabled={settingsStatusLoading || currentUser?.role !== 'admin'}>{t().settingsReload}</button>
			</div>
		{:else if settingsTab === 'users'}
			<div class="popover-group user-account-group">
				<div class="popover-group-label">{t().settingsUserSessionLabel}</div>
				{#if userSettingsStatus}
					<div class="inline-message">{userSettingsStatus}</div>
				{/if}
				{#if !currentUser}
					<div class="login-grid">
						<input bind:value={loginUserName} placeholder={t().userNamePlaceholder} />
						<input bind:value={loginPassword} type="password" placeholder={t().userPasswordPlaceholder} onkeydown={(e) => { if (e.key === 'Enter') void onLogin(); }} />
						<button class="ghost-btn" onclick={onLogin}>{t().loginSubmit}</button>
					</div>
					<div class="db-test-result">{t().bootstrapAdminNote}</div>
				{:else}
					<div class="user-session-row">
						<span>{currentUser.username} / {currentUser.role}{currentUser.group_name ? ` / ${currentUser.group_name}` : ''}</span>
						<button class="ghost-btn" onclick={onLogout}>{t().logoutButton}</button>
					</div>
					{#if userSettingsLoading}
						<div class="inline-message">{t().settingsLoading}</div>
					{/if}
				{/if}
			</div>
			{#if currentUser}
				{#if currentUser.role === 'admin'}
					<div class="popover-group">
						<div class="user-management-head">
							<div>
								<div class="popover-group-label">{t().settingsUsersLabel}</div>
								<div class="user-management-count">{t().userCountLabel(users.length)}</div>
							</div>
							<button class="ghost-btn" onclick={onLoadUserSettings} disabled={userSettingsLoading || currentUser.role !== 'admin'}>{t().settingsReload}</button>
						</div>
						<div class="user-management-layout">
							<div class="user-list-panel">
								<div class="user-list-head">
									<span>{t().userNamePlaceholder}</span>
									<span>{t().userEmailPlaceholder}</span>
									<span>{t().userRoleLabel}</span>
									<span>{t().userGroupLabel}</span>
									<span>{t().userGenerationCountLabel}</span>
									<span></span>
								</div>
								<div class="user-list">
									{#each users as user (user.id)}
										<div class="user-row" class:selected={selectedUserId === user.id}>
											<button class="user-select" onclick={() => onSetEditUser(user)}>
												<span class="user-cell user-name">{user.username}</span>
												<span class="user-cell">{user.email}</span>
												<span class="user-cell">{user.role}</span>
												<span class="user-cell">{user.group_name ?? t().userNoGroup}</span>
												<span class="user-cell user-count-cell">{user.image_generation_count.toLocaleString()}</span>
											</button>
											<button class="ghost-btn" onclick={() => onRemoveUser(user.id)}>{t().deleteButton}</button>
										</div>
									{/each}
								</div>
							</div>
							<div class="user-editor-panel">
								<div class="user-editor-title">{t().userAddTitle}</div>
								<div class="user-form-grid">
									<input bind:value={newUserName} placeholder={t().userNamePlaceholder} />
									<input bind:value={newUserEmail} type="email" placeholder={t().userEmailPlaceholder} />
									<input bind:value={newUserPassword} type="password" placeholder={t().userPasswordPlaceholder} />
									<label class="user-form-field">
										<span>{t().userRoleSelectLabel}</span>
										<select bind:value={newUserRole}>
											{#each USER_ROLE_OPTIONS as role (role)}
												<option value={role}>{role}</option>
											{/each}
										</select>
									</label>
									<label class="user-form-field">
										<span>{t().userGroupSelectLabel}</span>
										<select bind:value={newUserGroupId}>
											<option value="">{t().userNoGroup}</option>
											{#each groups as group (group.id)}
												<option value={group.id}>{group.name}</option>
											{/each}
										</select>
									</label>
								</div>
								<div class="user-form-actions">
									<button class="ghost-btn" onclick={onAddUser}>{t().userAddButton}</button>
								</div>
							</div>
							<div class="user-editor-panel">
								<div class="user-editor-title">{t().userEditTitle}</div>
								{#if selectedUserId}
									<div class="user-form-grid">
										<input bind:value={editUserName} placeholder={t().userNamePlaceholder} />
										<input bind:value={editUserEmail} type="email" placeholder={t().userEmailPlaceholder} />
										<input bind:value={editUserPassword} type="password" placeholder={t().userNewPasswordPlaceholder} />
										<label class="user-form-field">
											<span>{t().userRoleSelectLabel}</span>
											<select bind:value={editUserRole}>
												{#each USER_ROLE_OPTIONS as role (role)}
													<option value={role}>{role}</option>
												{/each}
											</select>
										</label>
										<label class="user-form-field">
											<span>{t().userGroupSelectLabel}</span>
											<select bind:value={editUserGroupId}>
												<option value="">{t().userNoGroup}</option>
												{#each groups as group (group.id)}
													<option value={group.id}>{group.name}</option>
												{/each}
											</select>
										</label>
									</div>
									<div class="user-form-actions">
										<button class="ghost-btn" onclick={onClearEditUser}>{t().userClearSelection}</button>
										<button class="ghost-btn primary-inline" onclick={onSaveUserEdit}>{t().userSaveChanges}</button>
									</div>
								{:else}
									<div class="inline-message">{t().userSelectPrompt}</div>
								{/if}
							</div>
						</div>
					</div>
				{:else}
					<div class="popover-group">
						<div class="popover-group-label">{t().settingsUsersLabel}</div>
						<div class="inline-message">{t().userManageUnavailable}</div>
					</div>
				{/if}
			{/if}
			{#if currentUser?.role === 'admin'}
				<div class="popover-group">
					<div class="popover-group-label">{t().userGroupLabel}</div>
					<div class="plugin-add">
						<input bind:value={newGroupName} placeholder={t().groupNamePlaceholder} />
						<button class="ghost-btn" onclick={onAddGroup}>{t().addButton}</button>
					</div>
					<div class="group-list">
						{#each groups as group (group.id)}
							<div class="group-row">
								{#if editGroupId === group.id}
									<input
										class="group-edit-input"
										bind:value={editGroupName}
										placeholder={t().groupNamePlaceholder}
										onkeydown={(e) => { if (e.key === 'Enter') void onSaveGroupEdit(); }}
									/>
									<div class="group-row-actions">
										<button class="ghost-btn" onclick={onClearEditGroup}>{t().confirmCancel}</button>
										<button class="ghost-btn primary-inline" onclick={onSaveGroupEdit}>{t().userSaveChanges}</button>
									</div>
								{:else}
									<span>{group.name}</span>
									<div class="group-row-actions">
										<button class="ghost-btn" onclick={() => onSetEditGroup(group)}>{t().editButton}</button>
										<button class="ghost-btn" onclick={() => onRemoveGroup(group)}>{t().deleteButton}</button>
									</div>
								{/if}
							</div>
						{/each}
					</div>
				</div>
			{/if}
		{:else if settingsTab === 'export'}
			<div class="popover-group">
				<div class="popover-group-label">{t().settingsExportTemplatesTitle}</div>
				<div class="db-test-result">{t().settingsExportTemplatesDescription}</div>
				{#if exportTemplateStatus}
					<div class="inline-message">{exportTemplateStatus}</div>
				{/if}
				<div class="export-template-head">
					<span>{t().settingsExportTemplateName}</span>
					<span>{t().settingsExportTemplateDescription}</span>
					<span>{t().settingsExportTemplateHeight}</span>
					<span></span>
				</div>
				<div class="export-template-list">
					{#each exportTemplates as template (template.id)}
						<div class="export-template-row">
							<input
								value={template.name}
								aria-label={t().settingsExportTemplateName}
								onchange={(e) => onUpdateExportTemplate(template.id, { name: (e.currentTarget as HTMLInputElement).value })}
							/>
							<input
								value={template.description}
								aria-label={t().settingsExportTemplateDescription}
								onchange={(e) => onUpdateExportTemplate(template.id, { description: (e.currentTarget as HTMLInputElement).value })}
							/>
							<input
								value={template.y_px}
								type="number"
								min="64"
								max="12000"
								step="1"
								aria-label={t().settingsExportTemplateHeight}
								onchange={(e) => onUpdateExportTemplate(template.id, { y_px: Number((e.currentTarget as HTMLInputElement).value) })}
							/>
							<button class="ghost-btn" onclick={() => onRemoveExportTemplate(template.id)}>{t().settingsExportTemplateDelete}</button>
						</div>
					{/each}
				</div>
				<div class="settings-inline-actions">
					<button class="ghost-btn primary-inline" onclick={onAddExportTemplate}>{t().settingsExportTemplateAdd}</button>
				</div>
			</div>
			<div class="popover-group">
				<div class="popover-group-label">{t().settingsExportLabel}</div>
				<label class="setting-toggle">
					<input type="checkbox" bind:checked={pngAlphaWhite} />
					<span>{t().settingsPngAlpha}</span>
				</label>
			</div>
		{:else}
			<div class="popover-group">
				<div class="popover-group-label">{t().settingsMascotLabel}</div>
				<label class="setting-toggle">
					<input type="checkbox" bind:checked={showKiwi} />
					<span>{t().settingsShowKiwi}</span>
				</label>
				<label class="setting-toggle">
					<input type="checkbox" bind:checked={showCrab} />
					<span>{t().settingsShowCrab}</span>
				</label>
			</div>
			<div class="popover-group">
				<div class="popover-group-label">{t().settingsHistoryLabel}</div>
				<label class="setting-toggle">
					<input type="checkbox" bind:checked={saveReplayAsNewVersion} />
					<span>{t().settingsSaveReplay}</span>
				</label>
			</div>
		{/if}
	</div>
	{#if settingsMode === 'model'}
		<div class="catalog-modal-foot">
			<button class="ghost-btn" onclick={onCancelModelSelection}>{t().confirmCancel}</button>
			<button class="ghost-btn primary-inline" onclick={onConfirmModelSelection}>{t().colorCatalogConfirm}</button>
		</div>
	{/if}
</div>

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
	<div class="modal-backdrop model-picker-backdrop" onclick={() => (modelPickerProviderId = null)} aria-hidden="true"></div>
	<div class="model-picker-dialog" role="dialog" aria-modal="true" tabindex="-1" onclick={(e) => e.stopPropagation()} onkeydown={(e) => e.stopPropagation()}>
		<div class="modal-head">
			<div class="catalog-modal-title">{t().settingsModelSelectModelsTitle(modelPickerProvider.label)}</div>
			<button class="catalog-close" onclick={() => (modelPickerProviderId = null)}>×</button>
		</div>
		<div class="model-picker-body">
			<div class="model-picker-actions">
				<button class="ghost-btn" onclick={() => onFetchModelList(modelPickerProvider.id)} disabled={modelSettingsLoading}>{t().settingsModelFetchModels}</button>
				<button class="ghost-btn" onclick={() => setAllPublishedModels(modelPickerProvider.id, modelPickerProvider.models, true)} disabled={modelSettingsLoading}>{t().settingsModelSelectAll}</button>
				<button class="ghost-btn" onclick={() => setAllPublishedModels(modelPickerProvider.id, modelPickerProvider.models, false)} disabled={modelSettingsLoading}>{t().settingsModelClearAll}</button>
			</div>
			<div class="model-picker-list" aria-label={t().settingsModelPublishedModels}>
				{#each modelPickerProvider.models as model, modelIndex (`${model.id}:${modelIndex}`)}
					<label class="check-row model-picker-row">
						<input
							type="checkbox"
							checked={modelEnabled(modelPickerSetting, model.id)}
							onchange={(e) => onUpdateModelProvider(modelPickerProvider.id, {
								enabled_models: {
									...(modelPickerSetting.enabled_models ?? {}),
									[model.id]: (e.currentTarget as HTMLInputElement).checked,
								},
							})}
						/>
						<span>{model.label}{model.notes ? ` - ${model.notes}` : ''}</span>
					</label>
				{/each}
			</div>
		</div>
		<div class="model-picker-footer">
			{#if modelFetchResults[modelPickerProvider.id]}
				<div class:error={modelFetchResults[modelPickerProvider.id].type === 'error'} class="model-picker-result">{modelFetchResults[modelPickerProvider.id].message}</div>
			{/if}
			<button class="ghost-btn" onclick={() => (modelPickerProviderId = null)}>{t().confirmCancel}</button>
			<button class="ghost-btn primary-inline" onclick={() => { void saveBaseUrl(modelPickerProvider.id, modelPickerSetting); modelPickerProviderId = null; }} disabled={modelSettingsLoading}>{t().profileSaveButton}</button>
		</div>
	</div>
{/if}

<style>
	.modal-backdrop {
		position: fixed; inset: 0; z-index: 400;
		background: rgba(0,0,0,0.25); backdrop-filter: blur(2px);
	}
	.modal-head {
		display: flex; align-items: center; justify-content: space-between;
		padding: 14px 18px 10px; border-bottom: 1px solid var(--border); flex-shrink: 0;
	}
	.catalog-modal-title { font-size: 15px; font-weight: 300; letter-spacing: 0.05em; }
	.catalog-close {
		width: 24px; height: 24px; border: none; background: none;
		color: var(--fg3); font-size: 18px; cursor: pointer; line-height: 1;
	}
	.settings-modal {
		position: fixed;
		top: 6vh;
		left: 50%;
		transform: translateX(-50%);
		z-index: 401;
		background: var(--panel2); border-radius: var(--r-lg);
		box-shadow: 0 12px 48px rgba(0,0,0,0.18);
		display: flex; flex-direction: column; overflow: hidden;
		width: min(860px, calc(100vw - 32px)); max-height: 88vh;
		height: min(760px, 88vh);
	}
	.settings-modal.model-modal {
		width: min(calc(35ch + 190px), calc(100vw - 32px));
		height: auto;
	}
	.settings-modal.model-modal .form-row label { width: 82px; }
	.settings-tabs {
		display: flex; gap: 0; border-bottom: 1px solid var(--border); background: var(--bg);
	}
	.settings-tabs button {
		padding: 9px 16px; border: none; border-bottom: 2px solid transparent;
		background: none; color: var(--fg2); font-size: 13px; cursor: pointer; font-family: inherit;
	}
	.settings-tabs button.active { color: var(--fg); border-bottom-color: var(--fg); font-weight: 500; }
	.settings-body {
		padding: 14px 16px; overflow-y: auto;
		display: flex; flex-direction: column; gap: 10px;
	}
	.popover-group {
		border: 1px solid var(--border);
		border-radius: var(--r);
		padding: 12px;
		background: var(--panel);
	}
	.popover-group-label {
		font-size: 10px; color: var(--fg3); text-transform: uppercase; letter-spacing: 0.08em;
		font-weight: 500; margin-bottom: 7px;
	}
	.model-connections-heading {
		display: flex;
		align-items: baseline;
		gap: 10px;
		margin-bottom: 7px;
		min-width: 0;
	}
	.model-connections-heading .popover-group-label {
		margin-bottom: 0;
		flex: 0 0 auto;
	}
	.model-security-note {
		min-width: 0;
		color: var(--fg3);
		font-size: 10px;
		line-height: 1.45;
		text-transform: none;
		letter-spacing: 0;
		overflow-wrap: anywhere;
	}
	.form-row {
		display: flex; align-items: center; gap: 8px; margin-bottom: 7px;
	}
	.form-row label { width: 90px; color: var(--fg2); font-size: 12px; flex-shrink: 0; }
	.form-row select, .plugin-add input, .login-grid input, .group-edit-input {
		flex: 1; min-width: 0; padding: 5px 7px;
		border: 1px solid var(--border2); border-radius: var(--r);
		background: var(--panel); color: var(--fg); font-size: 12px; font-family: inherit;
	}
	.check-row { display: flex; align-items: center; gap: 7px; color: var(--fg2); font-size: 12px; }
	.settings-inline-actions { display: flex; align-items: center; gap: 10px; }
	.model-settings-footer-actions { justify-content: flex-end; }
	.db-test-result { color: var(--fg2); font-size: 12px; }
	.settings-readonly-grid {
		display: grid;
		grid-template-columns: max-content minmax(0, 1fr);
		gap: 7px 12px;
		align-items: baseline;
		margin-bottom: 9px;
		font-size: 12px;
	}
	.settings-readonly-grid span { color: var(--fg3); }
	.settings-readonly-grid .nowrap-label { white-space: nowrap; }
	.settings-readonly-grid strong { color: var(--fg); font-weight: 500; min-width: 0; word-break: break-word; }
	.settings-readonly-grid code {
		min-width: 0;
		padding: 2px 4px;
		border-radius: var(--r);
		background: var(--bg);
		color: var(--fg2);
		font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
		font-size: 11px;
		word-break: break-all;
	}
	.settings-readonly-grid.compact {
		margin-top: 10px;
		margin-bottom: 0;
	}
	.db-backup-grid {
		display: grid;
		grid-template-columns: repeat(2, minmax(0, 1fr));
		gap: 10px;
		margin-top: 10px;
	}
	.db-backup-grid label {
		display: flex;
		flex-direction: column;
		gap: 4px;
		color: var(--fg3);
		font-size: 10px;
		text-transform: uppercase;
		letter-spacing: 0.06em;
	}
	.db-backup-grid input {
		min-width: 0;
		padding: 5px 7px;
		border: 1px solid var(--border2);
		border-radius: var(--r);
		background: var(--panel);
		color: var(--fg);
		font-size: 12px;
		font-family: inherit;
		font-variant-numeric: tabular-nums;
	}
	.server-path-row {
		display: flex;
		flex-direction: column;
		gap: 5px;
		margin-top: 10px;
		color: var(--fg3);
		font-size: 10px;
		text-transform: uppercase;
		letter-spacing: 0.06em;
	}
	.server-path-input-row {
		display: flex;
		gap: 8px;
	}
	.server-path-input-row input {
		flex: 1;
		min-width: 0;
		padding: 5px 7px;
		border: 1px solid var(--border2);
		border-radius: var(--r);
		background: var(--panel);
		color: var(--fg);
		font-size: 12px;
		font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
	}
	.server-path-row.compact-control {
		width: max-content;
	}
	.server-path-row select {
		min-width: 110px;
		padding: 5px 7px;
		border: 1px solid var(--border2);
		border-radius: var(--r);
		background: var(--panel);
		color: var(--fg);
		font-size: 12px;
		font-family: inherit;
	}
	.info-dot {
		position: relative;
		display: inline-flex;
		align-items: center;
		justify-content: center;
		width: 14px;
		height: 14px;
		margin-left: 5px;
		border: 1px solid var(--border2);
		border-radius: 50%;
		color: var(--fg3);
		font-size: 10px;
		line-height: 1;
		text-transform: none;
		letter-spacing: 0;
		cursor: help;
	}
	.info-tooltip {
		position: absolute;
		left: 50%;
		bottom: calc(100% + 8px);
		z-index: 20;
		width: min(260px, 70vw);
		transform: translateX(-50%);
		padding: 7px 9px;
		border-radius: var(--r);
		background: var(--tooltip-bg);
		color: #fff;
		font-size: 11px;
		line-height: 1.5;
		text-align: left;
		white-space: normal;
		text-transform: none;
		letter-spacing: 0;
		opacity: 0;
		pointer-events: none;
	}
	.info-dot:hover .info-tooltip,
	.info-dot:focus .info-tooltip {
		opacity: 1;
	}
	.model-provider-row label {
		display: flex;
		flex-direction: column;
		gap: 4px;
		color: var(--fg3);
		font-size: 10px;
		text-transform: uppercase;
		letter-spacing: 0.06em;
	}
	.model-provider-row input {
		min-width: 0;
		padding: 5px 7px;
		border: 1px solid var(--border2);
		border-radius: var(--r);
		background: var(--panel);
		color: var(--fg);
		font-size: 12px;
		font-family: inherit;
	}
	.model-provider-list {
		display: grid;
		grid-template-columns: repeat(2, minmax(0, 1fr));
		gap: 10px;
	}
	.model-add-grid {
		display: grid;
		grid-template-columns: repeat(2, minmax(0, 1fr));
		gap: 10px;
	}
	.model-add-grid label,
	.model-add-readonly-field {
		display: flex;
		flex-direction: column;
		gap: 4px;
		color: var(--fg3);
		font-size: 10px;
		text-transform: uppercase;
		letter-spacing: 0.06em;
	}
	.model-add-grid input,
	.model-add-grid select,
	.readonly-service-id {
		min-width: 0;
		box-sizing: border-box;
		height: 28px;
		padding: 5px 7px;
		border: 1px solid var(--border2);
		border-radius: var(--r);
		background: var(--panel);
		color: var(--fg);
		font-size: 12px;
		font-family: inherit;
	}
	.readonly-service-id {
		border: 1px solid var(--border);
		display: flex;
		align-items: center;
		background: var(--bg);
		color: var(--fg3);
		font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
		user-select: text;
	}
	.model-add-label-with-help {
		display: inline-flex;
		align-items: center;
		gap: 5px;
	}
	.model-service-id-info {
		width: 14px;
		height: 14px;
		font-size: 9px;
	}
	.model-service-id-tooltip {
		left: 0;
		right: auto;
		width: min(320px, 60vw);
		white-space: pre-line;
		text-transform: none;
		letter-spacing: 0;
	}
	.model-provider-row {
		display: flex;
		flex-direction: column;
		gap: 8px;
		padding: 10px;
		border: 1px solid var(--border);
		border-radius: var(--r);
		background: var(--bg);
	}
	.model-provider-head {
		display: flex;
		align-items: baseline;
		justify-content: space-between;
		gap: 8px;
	}
	.model-provider-head strong { font-size: 12px; font-weight: 500; }
	.model-provider-head span { color: var(--fg3); font-size: 11px; }
	.model-provider-title-row {
		display: inline-flex;
		align-items: center;
		gap: 6px;
		min-width: 0;
	}
	.model-provider-edit {
		padding: 2px 6px;
		font-size: 10px;
	}
	.model-provider-head-actions {
		display: inline-flex;
		align-items: center;
		gap: 6px;
	}
	.model-service-delete {
		padding: 2px 6px;
		font-size: 10px;
	}
	.model-key-state {
		display: inline-flex;
		align-items: center;
		gap: 5px;
		position: relative;
	}
	.model-key-info {
		position: relative;
		display: inline-flex;
		align-items: center;
		justify-content: center;
		width: 15px;
		height: 15px;
		border: 1px solid var(--border2);
		border-radius: 999px;
		color: var(--fg2);
		background: var(--panel);
		padding: 0;
		font-size: 10px;
		font-weight: 600;
		line-height: 1;
		cursor: help;
		text-transform: none;
	}
	.model-key-tooltip {
		position: absolute;
		right: 0;
		top: calc(100% + 7px);
		z-index: 20;
		display: none;
		width: min(260px, 42vw);
		padding: 7px 9px;
		border-radius: var(--r);
		background: var(--tooltip-bg);
		color: #fff;
		box-shadow: 0 8px 24px rgba(0,0,0,0.2);
		font-size: 11px;
		line-height: 1.45;
		font-weight: 400;
		text-align: left;
	}
	.model-key-info:hover .model-key-tooltip,
	.model-key-info:focus .model-key-tooltip {
		display: block;
	}
	.model-api-key-row {
		display: grid;
		grid-template-columns: minmax(0, 1fr) auto;
		gap: 6px;
		align-items: center;
	}
	.model-base-url-row {
		display: grid;
		grid-template-columns: minmax(0, 1fr) auto;
		gap: 6px;
		align-items: center;
	}
	.model-base-url-row input { width: 100%; }
	.model-base-url-save {
		white-space: nowrap;
		padding-inline: 8px;
	}
	.model-api-key-row input { width: 100%; }
	.model-api-key-row input:disabled {
		color: var(--fg3);
		-webkit-text-fill-color: var(--fg3);
		opacity: 1;
	}
	.model-key-delete {
		white-space: nowrap;
		padding-inline: 8px;
	}
	.model-publish-summary {
		display: flex;
		flex-direction: column;
		gap: 5px;
		padding-top: 2px;
	}
	.model-publish-head {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 8px;
	}
	.model-publish-title {
		color: var(--fg3);
		font-size: 10px;
		text-transform: uppercase;
		letter-spacing: 0.06em;
	}
	.model-fetch-btn {
		padding: 2px 6px;
		font-size: 10px;
	}
	.model-publish-selected {
		display: flex;
		flex-wrap: wrap;
		gap: 6px;
		max-height: 72px;
		overflow: auto;
	}
	.model-publish-selected span {
		padding: 2px 6px;
		border: 1px solid var(--border);
		border-radius: 999px;
		background: var(--panel);
		color: var(--fg2);
		font-size: 10px;
		line-height: 1.35;
	}
	.model-publish-empty {
		color: var(--fg3);
		font-size: 11px;
	}
	.model-provider-actions {
		display: flex;
		justify-content: flex-end;
		gap: 6px;
		margin-top: 2px;
	}
	.add-service-backdrop { z-index: 650; }
	.add-service-dialog,
	.service-edit-dialog,
	.service-memo-dialog,
	.model-picker-dialog {
		position: fixed;
		z-index: 660;
		left: 50%;
		top: 50%;
		transform: translate(-50%, -50%);
		width: min(720px, 86vw);
		max-height: 86vh;
		display: flex;
		flex-direction: column;
		border: 1px solid var(--border2);
		border-radius: var(--r-lg);
		background: var(--panel);
		box-shadow: var(--shadow);
		overflow: hidden;
	}
	.model-picker-dialog {
		width: min(760px, 88vw);
		max-height: 82vh;
	}
	.add-service-body {
		padding: 14px;
		overflow: auto;
	}
	.model-service-memo-field {
		display: flex;
		flex-direction: column;
		gap: 6px;
		color: var(--fg3);
		font-size: 10px;
		text-transform: uppercase;
		letter-spacing: 0.06em;
	}
	.model-service-memo-field textarea {
		min-width: 0;
		width: 100%;
		box-sizing: border-box;
		resize: vertical;
		padding: 7px 9px;
		border: 1px solid var(--border2);
		border-radius: var(--r);
		background: var(--panel);
		color: var(--fg);
		font-size: 12px;
		line-height: 1.45;
		font-family: inherit;
		text-transform: none;
		letter-spacing: 0;
	}
	.model-picker-body {
		padding: 14px;
		overflow: auto;
		display: flex;
		flex-direction: column;
		gap: 10px;
	}
	.model-picker-actions {
		display: flex;
		align-items: center;
		gap: 8px;
	}
	.model-picker-list {
		display: grid;
		grid-template-columns: repeat(2, minmax(0, 1fr));
		gap: 6px 10px;
	}
	.model-picker-row {
		min-width: 0;
		padding: 5px 7px;
		border: 1px solid var(--border);
		border-radius: var(--r);
		background: var(--bg);
	}
	.model-picker-row span {
		min-width: 0;
		overflow-wrap: anywhere;
	}
	.add-service-actions {
		display: flex;
		justify-content: flex-end;
		gap: 8px;
		padding: 10px 14px;
		border-top: 1px solid var(--border);
		background: var(--panel2);
	}
	.model-picker-footer {
		display: flex;
		justify-content: flex-end;
		align-items: center;
		gap: 8px;
		padding: 10px 14px;
		border-top: 1px solid var(--border);
		background: var(--panel2);
	}
	.model-picker-result {
		margin-right: auto;
		min-width: 0;
		color: var(--fg2);
		font-size: 12px;
		line-height: 1.35;
		overflow-wrap: anywhere;
	}
	.model-picker-result.error {
		color: var(--danger, #b42318);
	}
	.inline-message {
		padding: 7px 9px;
		border: 1px solid var(--border);
		border-radius: var(--r);
		background: var(--panel);
		color: var(--fg2);
		font-size: 12px;
	}
	.plugin-add { display: flex; gap: 8px; align-items: center; }
	.export-template-head,
	.export-template-row {
		display: grid;
		grid-template-columns: minmax(120px, 0.8fr) minmax(180px, 1.4fr) 96px 70px;
		gap: 8px;
		align-items: center;
	}
	.export-template-head {
		margin-top: 10px;
		padding: 0 4px;
		color: var(--fg3);
		font-size: 10px;
		text-transform: uppercase;
		letter-spacing: 0.06em;
	}
	.export-template-list {
		display: flex;
		flex-direction: column;
		gap: 6px;
		margin: 6px 0 10px;
	}
	.export-template-row {
		padding: 7px;
		border: 1px solid var(--border);
		border-radius: var(--r);
		background: var(--panel);
	}
	.export-template-row input {
		min-width: 0;
		padding: 5px 7px;
		border: 1px solid var(--border2);
		border-radius: var(--r);
		background: var(--panel);
		color: var(--fg);
		font-size: 12px;
		font-family: inherit;
	}
	.export-template-row input[type="number"] {
		text-align: right;
		font-variant-numeric: tabular-nums;
	}
	.system-plugin-panel {
		display: grid;
		grid-template-columns: minmax(0, 1fr) auto;
		gap: 12px;
		align-items: center;
		padding: 10px;
		border: 1px solid var(--border);
		border-radius: var(--r);
		background: var(--panel);
	}
	.system-plugin-main { min-width: 0; }
	.system-plugin-title-row {
		display: flex;
		align-items: center;
		gap: 8px;
		margin-bottom: 4px;
	}
	.system-plugin-title {
		font-size: 13px;
		font-weight: 500;
		color: var(--fg);
	}
	.plugin-version-pill {
		padding: 2px 6px;
		border: 1px solid var(--border2);
		border-radius: 999px;
		color: var(--fg3);
		background: var(--bg);
		font-size: 11px;
		line-height: 1.2;
		font-variant-numeric: tabular-nums;
	}
	.system-plugin-desc {
		font-size: 12px;
		color: var(--fg2);
		line-height: 1.45;
	}
	.plugin-switch {
		border: none;
		background: transparent;
		padding: 0;
		display: inline-flex;
		align-items: center;
		gap: 8px;
		color: var(--fg3);
		cursor: pointer;
		font-family: inherit;
		font-size: 12px;
	}
	.switch-track {
		position: relative;
		width: 40px;
		height: 22px;
		border-radius: 999px;
		background: var(--border2);
		box-shadow: inset 0 0 0 1px var(--border2);
		transition: background 0.14s ease;
	}
	.switch-knob {
		position: absolute;
		top: 3px;
		left: 3px;
		width: 16px;
		height: 16px;
		border-radius: 50%;
		background: var(--panel);
		box-shadow: 0 1px 4px rgba(0,0,0,0.22);
		transition: transform 0.14s ease;
	}
	.plugin-switch.plugin-enabled {
		color: var(--accent);
	}
	.plugin-switch.plugin-enabled .switch-track {
		background: var(--accent);
	}
	.plugin-switch.plugin-enabled .switch-knob {
		transform: translateX(18px);
	}
	.plugin-switch:disabled {
		opacity: 0.62;
		cursor: default;
	}
	.user-plugin-skeleton {
		display: grid;
		grid-template-columns: minmax(0, 1fr);
		gap: 10px;
	}
	.login-grid {
		display: grid;
		grid-template-columns: minmax(0, 1fr) minmax(0, 1fr) auto;
		gap: 8px;
		align-items: center;
	}
	.user-account-group {
		background: var(--panel);
	}
	.user-session-row {
		display: flex;
		justify-content: space-between;
		align-items: center;
		gap: 10px;
		padding: 7px 9px;
		border: 1px solid var(--border);
		border-radius: var(--r);
		background: var(--panel);
		color: var(--fg2);
		font-size: 12px;
	}
	.user-management-head {
		display: flex;
		align-items: flex-start;
		justify-content: space-between;
		gap: 12px;
		margin-bottom: 10px;
	}
	.user-management-count {
		color: var(--fg3);
		font-size: 11px;
		line-height: 1.4;
	}
	.user-management-layout {
		display: grid;
		grid-template-columns: minmax(0, 1.15fr) minmax(260px, 0.85fr);
		gap: 10px;
		align-items: start;
	}
	.user-list-panel {
		min-width: 0;
		--user-list-columns: minmax(0, 1fr) minmax(0, 1.35fr) 72px 92px 38px 68px;
	}
	.user-editor-panel {
		border: 1px solid var(--border);
		border-radius: var(--r);
		background: var(--panel);
		padding: 10px;
		min-width: 0;
	}
	.user-editor-title {
		font-size: 12px;
		font-weight: 500;
		color: var(--fg2);
		margin-bottom: 8px;
	}
	.user-form-grid {
		display: grid;
		grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
		gap: 8px;
	}
	.user-form-grid input, .user-form-grid select {
		min-width: 0; padding: 5px 7px;
		border: 1px solid var(--border2); border-radius: var(--r);
		background: var(--panel); color: var(--fg); font-size: 12px; font-family: inherit;
	}
	.user-form-field {
		display: flex;
		flex-direction: column;
		gap: 4px;
		min-width: 0;
		color: var(--fg3);
		font-size: 10px;
		text-transform: uppercase;
		letter-spacing: 0.06em;
	}
	.user-form-field select {
		width: 100%;
		text-transform: none;
		letter-spacing: 0;
	}
	.user-form-actions {
		display: flex;
		justify-content: flex-end;
		gap: 8px;
		margin-top: 8px;
	}
	.user-management-layout .user-editor-panel {
		grid-column: 2;
	}
	.primary-inline {
		border-color: var(--accent);
		background: var(--accent-light);
		color: var(--accent);
	}
	.user-list, .group-list {
		display: flex;
		flex-direction: column;
		gap: 6px;
		margin-top: 10px;
	}
	.user-list-head {
		display: grid;
		grid-template-columns: var(--user-list-columns);
		gap: 8px;
		padding: 0 9px 5px;
		color: var(--fg3);
		font-size: 10px;
		text-transform: uppercase;
		letter-spacing: 0.06em;
	}
	.user-list-head span {
		min-width: 0;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.user-row {
		display: grid;
		grid-template-columns: var(--user-list-columns);
		gap: 8px;
		align-items: center;
		padding: 7px 9px;
		border: 1px solid var(--border);
		border-radius: var(--r);
		background: var(--panel);
	}
	.user-row.selected { border-color: var(--accent); background: var(--accent-light); }
	.user-select {
		grid-column: 1 / 6;
		display: grid;
		grid-template-columns: minmax(0, 1fr) minmax(0, 1.35fr) 72px 92px 38px;
		gap: 8px;
		align-items: center;
		min-width: 0;
		padding: 0;
		border: none;
		background: none;
		color: inherit;
		font-family: inherit;
		text-align: left;
		cursor: pointer;
	}
	.user-row > .ghost-btn {
		width: 68px;
		justify-content: center;
	}
	.user-cell { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--fg2); font-size: 12px; }
	.user-name { color: var(--fg); font-weight: 500; }
	.user-count-cell { text-align: right; font-variant-numeric: tabular-nums; }
	.group-row {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 8px;
		background: var(--panel);
		border: 1px solid var(--border);
		border-radius: var(--r);
		padding: 7px 9px;
		font-size: 12px;
		color: var(--fg2);
	}
	.group-row-actions {
		display: flex;
		align-items: center;
		justify-content: flex-end;
		gap: 6px;
		flex-shrink: 0;
	}
	.group-edit-input {
		flex: 1;
	}
	.setting-toggle {
		display: flex;
		align-items: center;
		gap: 8px;
		font-size: 12px;
		color: var(--fg2);
		cursor: pointer;
	}
	.catalog-modal-foot {
		display: flex;
		justify-content: flex-end;
		gap: 8px;
		padding: 10px 18px 14px;
		border-top: 1px solid var(--border);
		background: var(--panel2);
		flex-shrink: 0;
	}
	.ghost-btn {
		padding: 4px 10px;
		border: 1px solid var(--border2);
		border-radius: var(--r);
		background: var(--panel);
		color: var(--fg2);
		font-size: 11px;
		cursor: pointer;
		font-family: inherit;
	}
	.ghost-btn:hover { background: var(--bg2); }
	.ghost-btn:disabled { opacity: 0.4; cursor: not-allowed; }
</style>
