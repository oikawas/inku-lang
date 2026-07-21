<script lang="ts">
	import { t } from '$lib/i18n/index.svelte';
	import ModelMetaCard from './ModelMetaCard.svelte';
	import { modelEolLabel, sortModels } from '$lib/modelMeta';
	import UnreadWordsPanel from '$lib/components/UnreadWordsPanel.svelte';
	import type { ExportTemplate } from '$lib/exportTemplates';
	import type { ModelOption, Provider, ProviderGroup } from '$lib/models';

	type PluginItem = {
		name: string;
		namespace?: string;
		version: string;
		status: string;
		path?: string;
		reasons?: string[];
		entries?: Array<{ qualified_name: string; note_ja: string; note_en: string }>;
		id?: string;
		enabled?: boolean;
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
		log_retention: {
			enabled: boolean;
			retention_days: number;
			rotate: 'daily' | 'weekly' | 'monthly';
			compress: boolean;
			log_dir: string;
			services: string[];
			systemd_dropins: Record<string, string>;
			logrotate_config: string;
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
	type SettingsTab = 'connection' | 'models' | 'db' | 'plugins' | 'users' | 'unread' | 'export' | 'misc' | 'server_misc' | 'logs';
	type HistorySelectionBehavior = 'history' | 'current';
	type ModelProviderSetting = {
		label?: string;
		kind?: string;
		default_base_url?: string;
		requires_api_key?: boolean;
		memo?: string;
		models?: ModelOption[];
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
		visionProvider: Provider;
		visionModel: string;
		providerGroups: ProviderGroup[];
		visionProviderGroups: ProviderGroup[];
		allowVisionSelection: boolean;
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
		logRetentionStatus: string | null;
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
		autoRepairEnabled: boolean;
		pngAlphaWhite: boolean;
		exportTemplates: ExportTemplate[];
		exportTemplateStatus: string | null;
		saveReplayAsNewVersion: boolean;
		historySelectionCanvas: HistorySelectionBehavior;
		historySelectionCatalog: HistorySelectionBehavior;
		canvasAspectEnabled: boolean;
		onClose: () => void;
		onCloseSettings: () => void;
		onSelectSettingsTab: (tab: SettingsTab) => void;
		onSetStage1Provider: (provider: Provider) => void;
		onSetStage1Model: (model: string) => void;
		onSetStage2Provider: (provider: Provider) => void;
		onSetStage2Model: (model: string) => void;
		onSetVisionProvider: (provider: Provider) => void;
		onSetVisionModel: (model: string) => void;
		onUpdateModelProvider: (provider: Provider, patch: Partial<ModelProviderSetting>) => void;
		onAddModelProvider: (provider: Provider, patch: Partial<ModelProviderSetting>) => void | Promise<void>;
		onAskDeleteModelProvider: (provider: Provider) => void;
		onAskClearModelApiKey: (provider: Provider) => void;
		onFetchModelList: (provider: Provider) => void | Promise<void>;
		onSaveModelProviderName: (provider: Provider, label: string) => void | Promise<void>;
		onSaveModelProviderMemo: (provider: Provider, memo: string) => void | Promise<void>;
		onSaveModelProvider: (provider: Provider, patch?: Partial<ModelProviderSetting>) => void | Promise<void>;
		onSaveModelSettings: () => void | Promise<void>;
		onLoadModelSettings: () => void | Promise<void>;
		onLoadSettingsStatus: () => void;
		pluginActionStatus: string | null;
		onLoadPluginContent: (id: string) => Promise<string | null>;
		onSavePlugin: (id: string, content: string) => Promise<string[] | null>;
		onCreatePlugin: (content: string, filename: string) => Promise<string[] | null>;
		onDeletePlugin: (id: string) => Promise<boolean>;
		onSetPluginEnabled: (id: string, enabled: boolean) => Promise<boolean>;
		onUpdateDbBackupSettings: (intervalDays: number, maxGenerations: number) => void | Promise<void>;
		onRunDbBackupNow: () => void | Promise<void>;
		onUpdateOutputSaveSettings: (enabled: boolean, outputDir: string, pngSize: number) => void | Promise<void>;
		onUpdateLogRetentionSettings: (enabled: boolean, retentionDays: number, rotate: string, compress: boolean) => void | Promise<void>;
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
		visionProvider,
		visionModel,
		providerGroups,
		visionProviderGroups,
		allowVisionSelection,
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
		logRetentionStatus,
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
		autoRepairEnabled = $bindable(true),
		pngAlphaWhite = $bindable(),
		exportTemplates,
		exportTemplateStatus,
		saveReplayAsNewVersion = $bindable(),
		historySelectionCanvas = $bindable(),
		historySelectionCatalog = $bindable(),
		canvasAspectEnabled,
		onClose,
		onCloseSettings,
		onSelectSettingsTab,
		onSetStage1Provider,
		onSetStage1Model,
		onSetStage2Provider,
		onSetStage2Model,
		onSetVisionProvider,
		onSetVisionModel,
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
		pluginActionStatus,
		onLoadPluginContent,
		onSavePlugin,
		onCreatePlugin,
		onDeletePlugin,
		onSetPluginEnabled,
		onUpdateDbBackupSettings,
		onRunDbBackupNow,
		onUpdateOutputSaveSettings,
		onUpdateLogRetentionSettings,
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

	// ── User plugin management (plugins tab) ──
	let pluginFileInput = $state<HTMLInputElement | null>(null);
	let pluginBusy = $state(false);
	let pluginDeleteConfirmId = $state<string | null>(null);
	let pluginSectionReasons = $state<string[]>([]);
	let pluginEditorOpen = $state(false);
	let pluginEditorId = $state<string | null>(null);
	let pluginEditorTitle = $state('');
	let pluginEditorContent = $state('');
	let pluginEditorLoading = $state(false);
	let pluginEditorSaving = $state(false);
	let pluginEditorReasons = $state<string[]>([]);

	function pluginId(plugin: PluginItem): string {
		return plugin.id ?? plugin.path ?? `${plugin.namespace ?? ''}.${plugin.name}`;
	}
	function pluginIsEnabled(plugin: PluginItem): boolean {
		return plugin.enabled ?? plugin.status === 'enabled';
	}

	async function togglePluginEnabled(plugin: PluginItem): Promise<void> {
		if (!isAdmin || pluginBusy) return;
		pluginBusy = true;
		await onSetPluginEnabled(pluginId(plugin), !pluginIsEnabled(plugin));
		pluginBusy = false;
	}

	async function confirmDeletePlugin(plugin: PluginItem): Promise<void> {
		if (!isAdmin || pluginBusy) return;
		pluginBusy = true;
		await onDeletePlugin(pluginId(plugin));
		pluginDeleteConfirmId = null;
		pluginBusy = false;
	}

	function triggerPluginFile(): void {
		pluginSectionReasons = [];
		pluginFileInput?.click();
	}

	async function onPluginFileChange(event: Event): Promise<void> {
		const input = event.currentTarget as HTMLInputElement;
		const file = input.files?.[0];
		input.value = '';
		if (!file) return;
		pluginBusy = true;
		const content = await file.text();
		const reasons = await onCreatePlugin(content, file.name);
		pluginBusy = false;
		pluginSectionReasons = reasons ?? [];
	}

	async function openPluginEditor(plugin: PluginItem): Promise<void> {
		pluginEditorId = pluginId(plugin);
		pluginEditorTitle = plugin.namespace ? `${plugin.namespace}.${plugin.name}` : plugin.name;
		pluginEditorReasons = [];
		pluginEditorContent = '';
		pluginEditorOpen = true;
		pluginEditorLoading = true;
		const content = await onLoadPluginContent(pluginEditorId);
		pluginEditorLoading = false;
		if (content === null) { pluginEditorOpen = false; pluginEditorId = null; return; }
		pluginEditorContent = content;
	}

	function closePluginEditor(): void {
		if (pluginEditorSaving) return;
		pluginEditorOpen = false;
		pluginEditorId = null;
	}

	async function savePluginEditor(): Promise<void> {
		if (!pluginEditorId || pluginEditorSaving) return;
		pluginEditorSaving = true;
		const reasons = await onSavePlugin(pluginEditorId, pluginEditorContent);
		pluginEditorSaving = false;
		if (reasons === null) { pluginEditorOpen = false; pluginEditorId = null; pluginEditorReasons = []; }
		else pluginEditorReasons = reasons;
	}

	const USER_ROLE_OPTIONS: UserRole[] = ['admin', 'group_lead', 'user'];
	const isAdmin = $derived(currentUser?.role === 'admin');
	type ModelSelectionTab = 'shared' | 'stage1' | 'stage2' | 'vision';
	let modelSelectionTab = $state<ModelSelectionTab>('shared');
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
	{#if settingsMode === 'model'}
		<div class="settings-tabs model-selection-tabs" role="tablist" aria-label={t().modelSelectButton}>
			<button role="tab" aria-selected={modelSelectionTab === 'shared'} class:active={modelSelectionTab === 'shared'} onclick={() => (modelSelectionTab = 'shared')}>Stage 1/2</button>
			<button role="tab" aria-selected={modelSelectionTab === 'stage1'} class:active={modelSelectionTab === 'stage1'} onclick={() => (modelSelectionTab = 'stage1')}>Stage 1</button>
			<button role="tab" aria-selected={modelSelectionTab === 'stage2'} class:active={modelSelectionTab === 'stage2'} onclick={() => (modelSelectionTab = 'stage2')}>Stage 2</button>
			{#if allowVisionSelection}<button role="tab" aria-selected={modelSelectionTab === 'vision'} class:active={modelSelectionTab === 'vision'} onclick={() => (modelSelectionTab = 'vision')}>Vision</button>{/if}
		</div>
	{:else}
		<div class="settings-tabs">
			{#if isAdmin}
				<button class:active={settingsTab === 'models'} onclick={() => onSelectSettingsTab('models')}>{t().settingsTabModels}</button>
			{/if}
			<button class:active={settingsTab === 'plugins'} onclick={() => onSelectSettingsTab('plugins')}>{t().settingsTabPlugins}</button>
			{#if isAdmin}
				<button class:active={settingsTab === 'users'} onclick={() => onSelectSettingsTab('users')}>{t().settingsTabUsers}</button>
				<button class:active={settingsTab === 'db'} onclick={() => onSelectSettingsTab('db')}>{t().settingsTabDb}</button>
				<button class:active={settingsTab === 'server_misc'} onclick={() => onSelectSettingsTab('server_misc')}>{t().settingsTabServerMisc}</button>
				<button class:active={settingsTab === 'logs'} onclick={() => onSelectSettingsTab('logs')}>{t().settingsTabLogs}</button>
			{/if}
			<button class:active={settingsTab === 'unread'} onclick={() => onSelectSettingsTab('unread')}>{t().settingsTabUnreadWords}</button>
			<button class:active={settingsTab === 'export'} onclick={() => onSelectSettingsTab('export')}>{t().settingsTabExport}</button>
			<button class:active={settingsTab === 'misc'} onclick={() => onSelectSettingsTab('misc')}>{t().settingsTabMisc}</button>
		</div>
	{/if}
	<div class="settings-body">
		{#if settingsMode === 'model'}
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
								{#each sortModels(provider.models, modelSelectionTab === 'vision' ? 'vision' : 'llm') as model (model.id)}
								<button
									type="button"
									class="model-metadata-hover"
									class:selected={modelSelected(provider.id, model.id)}
									class:eol={model.eol}
									disabled={model.eol}
									aria-pressed={modelSelected(provider.id, model.id)}
									onclick={() => selectGenerationModel(provider.id, model.id)}
								>
									<strong>{model.label}</strong>
									{#if model.eol}<span class="eol-mark">{modelEolLabel(model, isJapanese)}</span>{/if}
									{#if model.notes}<span>{model.notes}</span>{/if}
									<ModelMetaCard {model} {isJapanese} />
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
		{:else if settingsTab === 'logs'}
			<div class="popover-group">
				<div class="popover-group-label">{t().settingsLogRetentionTitle}</div>
				{#if settingsStatusLoading}
					<div class="inline-message">{t().settingsLoading}</div>
				{:else if settingsStatus}
					<label class="setting-toggle">
						<input
							type="checkbox"
							checked={settingsStatus.log_retention.enabled}
							onchange={(e) => onUpdateLogRetentionSettings((e.currentTarget as HTMLInputElement).checked, settingsStatus?.log_retention.retention_days ?? 90, settingsStatus?.log_retention.rotate ?? 'daily', settingsStatus?.log_retention.compress ?? true)}
						/>
						<span>{t().settingsLogRetentionEnabled}</span>
					</label>
					<div class="db-backup-grid">
						<label>
							<span>{t().settingsLogRetentionDays}</span>
							<input
								type="number"
								min="1"
								max="3650"
								value={settingsStatus.log_retention.retention_days}
								onchange={(e) => onUpdateLogRetentionSettings(settingsStatus?.log_retention.enabled ?? true, Number((e.currentTarget as HTMLInputElement).value), settingsStatus?.log_retention.rotate ?? 'daily', settingsStatus?.log_retention.compress ?? true)}
							/>
						</label>
						<label>
							<span>{t().settingsLogRetentionRotate}</span>
							<select
								value={settingsStatus.log_retention.rotate}
								onchange={(e) => onUpdateLogRetentionSettings(settingsStatus?.log_retention.enabled ?? true, settingsStatus?.log_retention.retention_days ?? 90, (e.currentTarget as HTMLSelectElement).value, settingsStatus?.log_retention.compress ?? true)}
							>
								<option value="daily">{t().settingsLogRetentionDaily}</option>
								<option value="weekly">{t().settingsLogRetentionWeekly}</option>
								<option value="monthly">{t().settingsLogRetentionMonthly}</option>
							</select>
						</label>
					</div>
					<label class="setting-toggle">
						<input
							type="checkbox"
							checked={settingsStatus.log_retention.compress}
							onchange={(e) => onUpdateLogRetentionSettings(settingsStatus?.log_retention.enabled ?? true, settingsStatus?.log_retention.retention_days ?? 90, settingsStatus?.log_retention.rotate ?? 'daily', (e.currentTarget as HTMLInputElement).checked)}
						/>
						<span>{t().settingsLogRetentionCompress}</span>
					</label>
					<div class="settings-readonly-grid compact">
						<span>{t().settingsLogRetentionLogDir}</span><code>{settingsStatus.log_retention.log_dir}</code>
						<span>{t().settingsLogRetentionServices}</span><strong>{settingsStatus.log_retention.services.join(', ')}</strong>
					</div>
					<div class="db-test-result">{t().settingsOutputSaveNoteLabel}: {t().settingsLogRetentionNote}</div>
					<div class="settings-config-preview">
						<div class="settings-config-preview-title">{t().settingsLogRetentionLogrotatePreview}</div>
						<pre>{settingsStatus.log_retention.logrotate_config}</pre>
					</div>
					<div class="settings-config-preview">
						<div class="settings-config-preview-title">{t().settingsLogRetentionSystemdPreview}</div>
						{#each Object.entries(settingsStatus.log_retention.systemd_dropins) as [service, config]}
							<div class="settings-config-service">{service}</div>
							<pre>{config}</pre>
						{/each}
					</div>
					{#if logRetentionStatus}
						<div class="inline-message">{logRetentionStatus}</div>
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
				<div class="popover-group-label user-plugin-head">
					<span>{t().settingsUserPlugins}</span>
					<button class="ghost-btn" onclick={triggerPluginFile} disabled={!isAdmin || pluginBusy}>{t().settingsPluginLoadFile}</button>
					<input type="file" accept=".md" bind:this={pluginFileInput} onchange={onPluginFileChange} style="display:none" />
				</div>
				{#if pluginActionStatus}<div class="db-test-result">{pluginActionStatus}</div>{/if}
				{#if pluginSectionReasons.length}<div class="db-test-result">{t().settingsPluginInvalid}: {pluginSectionReasons.join(" / ")}</div>{/if}
				{#if settingsStatus?.plugins.loaded.filter((plugin) => plugin.namespace !== "system").length}
					{#each settingsStatus.plugins.loaded.filter((plugin) => plugin.namespace !== "system") as plugin (plugin.id ?? plugin.path ?? `${plugin.namespace}.${plugin.name}`)}
						<div class="user-plugin-row">
							<div class="user-plugin-info">
								<div class="system-plugin-title-row">
									<div class="system-plugin-title">{plugin.namespace ? `${plugin.namespace}.${plugin.name}` : plugin.name}</div>
									<span class="plugin-version-pill">{plugin.version ? `v${plugin.version}` : plugin.status}</span>
									{#if plugin.status === "rejected"}<span class="plugin-rejected">{plugin.status}</span>{/if}
								</div>
								<div class="system-plugin-desc">{plugin.path ?? ""}</div>
								{#if plugin.reasons?.length}<div class="db-test-result">{plugin.reasons.join(" / ")}</div>{/if}
							</div>
							<div class="user-plugin-controls">
								{#if plugin.status !== "rejected"}
									<button
										type="button"
										class="plugin-switch"
										class:plugin-enabled={pluginIsEnabled(plugin)}
										role="switch"
										aria-checked={pluginIsEnabled(plugin)}
										disabled={!isAdmin || pluginBusy}
										onclick={() => void togglePluginEnabled(plugin)}
									>
										<span class="switch-track"><span class="switch-knob"></span></span>
										<span class="switch-label">{pluginIsEnabled(plugin) ? t().settingsPluginEnabled : t().settingsPluginDisabled}</span>
									</button>
								{/if}
								<button class="ghost-btn user-plugin-btn" onclick={() => void openPluginEditor(plugin)} disabled={!isAdmin || pluginBusy}>{t().settingsPluginViewEdit}</button>
								{#if pluginDeleteConfirmId === pluginId(plugin)}
									<button class="ghost-btn user-plugin-btn danger" onclick={() => void confirmDeletePlugin(plugin)} disabled={pluginBusy}>{t().settingsPluginDeleteConfirm}</button>
									<button class="ghost-btn user-plugin-btn" onclick={() => (pluginDeleteConfirmId = null)} disabled={pluginBusy}>{t().confirmCancel}</button>
								{:else}
									<button class="ghost-btn user-plugin-btn danger" onclick={() => (pluginDeleteConfirmId = pluginId(plugin))} disabled={!isAdmin || pluginBusy}>{t().settingsPluginDelete}</button>
								{/if}
							</div>
						</div>
					{/each}
				{:else}
					<div class="inline-message">{t().settingsPluginsEmpty}</div>
				{/if}
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
		{:else if settingsTab === 'unread'}
			<UnreadWordsPanel {isAdmin} />
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
				<div class="popover-group-label">{t().settingsGenerationLabel}</div>
				<label class="setting-toggle" title={t().tooltipDdlAutoRepair}>
					<input type="checkbox" bind:checked={autoRepairEnabled} />
					<span>{t().ddlAutoRepairLabel}</span>
				</label>
			</div>
			<div class="popover-group">
				<div class="popover-group-label">{t().settingsHistoryLabel}</div>
				<div class="settings-radio-title">{t().settingsHistorySelectionTitle}</div>
				<div class="settings-radio-set">
					<label class="setting-toggle">
						<input type="radio" name="history-selection-canvas" value="history" bind:group={historySelectionCanvas} />
						<span>{t().settingsHistorySelectionCanvasHistory}</span>
					</label>
					<label class="setting-toggle">
						<input type="radio" name="history-selection-canvas" value="current" bind:group={historySelectionCanvas} />
						<span>{t().settingsHistorySelectionCanvasCurrent}</span>
					</label>
				</div>
				<div class="settings-radio-set">
					<label class="setting-toggle">
						<input type="radio" name="history-selection-catalog" value="history" bind:group={historySelectionCatalog} />
						<span>{t().settingsHistorySelectionCatalogHistory}</span>
					</label>
					<label class="setting-toggle">
						<input type="radio" name="history-selection-catalog" value="current" bind:group={historySelectionCatalog} />
						<span>{t().settingsHistorySelectionCatalogCurrent}</span>
					</label>
				</div>
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

{#if pluginEditorOpen}
	<div class="modal-backdrop" onclick={closePluginEditor} aria-hidden="true"></div>
	<div class="plugin-editor-dialog" role="dialog" aria-modal="true" tabindex="-1" onclick={(e) => e.stopPropagation()} onkeydown={(e) => { if (e.key === 'Escape') closePluginEditor(); }}>
		<div class="modal-head">
			<div class="catalog-modal-title">{t().settingsPluginEditorTitle} — {pluginEditorTitle}</div>
			<button class="catalog-close" onclick={closePluginEditor} disabled={pluginEditorSaving}>×</button>
		</div>
		<div class="plugin-editor-body">
			{#if pluginEditorLoading}
				<div class="inline-message">{t().settingsLoading}</div>
			{:else}
				<textarea class="plugin-editor-ta" bind:value={pluginEditorContent} spellcheck="false" disabled={pluginEditorSaving}></textarea>
			{/if}
			{#if pluginEditorReasons.length}<div class="db-test-result">{t().settingsPluginInvalid}: {pluginEditorReasons.join(" / ")}</div>{/if}
		</div>
		<div class="plugin-editor-foot">
			<button class="ghost-btn" onclick={closePluginEditor} disabled={pluginEditorSaving}>{t().confirmCancel}</button>
			<button class="ghost-btn primary" onclick={savePluginEditor} disabled={pluginEditorSaving || pluginEditorLoading || !isAdmin}>{pluginEditorSaving ? t().settingsLoading : t().settingsPluginSave}</button>
		</div>
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
		width: min(1120px, calc(100vw - 48px)); max-height: 88vh;
		height: min(760px, 88vh);
	}
	.settings-modal.model-modal {
		width: min(820px, calc(100vw - 32px));
		height: min(760px, 88vh);
	}
	.settings-tabs.model-selection-tabs button { flex: 1 1 0; text-align: center; }
	.model-selection-summary { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; }
	.model-selection-summary span {
		display: flex; flex-direction: column; gap: 3px; min-width: 0; padding: 8px 10px;
		border: 1px solid var(--border); border-radius: var(--r); background: var(--panel);
		color: var(--fg2); font-size: 11px; overflow-wrap: anywhere;
	}
	.model-selection-summary strong { color: var(--fg3); font-size: 9px; letter-spacing: .08em; text-transform: uppercase; }
	.model-selection-hint { margin: 0; color: var(--fg3); font-size: 11px; line-height: 1.5; }
	.generation-model-groups { display: flex; flex-direction: column; gap: 12px; }
	.generation-model-provider h3 { margin: 0 0 6px; color: var(--fg3); font-size: 10px; font-weight: 500; letter-spacing: .06em; }
	.generation-model-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(190px, 1fr)); gap: 7px; }
	.generation-model-grid button {
		display: flex; flex-direction: column; align-items: flex-start; gap: 3px; min-width: 0;
		padding: 9px 10px; border: 1px solid var(--border2); border-radius: var(--r);
		background: var(--panel); color: var(--fg2); cursor: pointer; text-align: left; font-family: inherit;
	}
	.generation-model-grid button:hover { border-color: var(--accent); background: var(--bg2); }
	.generation-model-grid button.eol { opacity: 0.55; cursor: not-allowed; }
	.generation-model-grid button.eol strong { text-decoration: line-through; }
	.eol-mark { color: var(--danger); font-weight: 600; }
	.generation-model-grid button.selected { border-color: var(--accent); box-shadow: inset 0 0 0 1px var(--accent); background: var(--accent-light); color: var(--fg); }
	.generation-model-grid strong { font-size: 12px; font-weight: 500; overflow-wrap: anywhere; }
	.generation-model-grid span { color: var(--fg3); font-size: 10px; }
	.model-thinking-row { padding: 8px 10px; border: 1px solid var(--border); border-radius: var(--r); background: var(--panel); }
	.model-metadata-hover { position: relative; }
	.model-metadata-hover:hover :global(.model-hover-card),
	.model-metadata-hover:focus-visible :global(.model-hover-card),
	.model-metadata-hover:focus-within :global(.model-hover-card) { display: block; }
	.settings-tabs {
		display: flex; flex: 0 0 auto; gap: 0; overflow-x: auto; border-bottom: 1px solid var(--border); background: var(--bg);
	}
	.settings-tabs button {
		flex: 0 0 auto; white-space: nowrap; padding: 9px 16px; border: none; border-bottom: 2px solid transparent;
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
	.plugin-add input, .login-grid input, .group-edit-input {
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
	.db-backup-grid input,
	.db-backup-grid select {
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
	.settings-config-preview {
		margin-top: 10px;
		display: flex;
		flex-direction: column;
		gap: 5px;
	}
	.settings-config-preview-title,
	.settings-config-service {
		color: var(--fg3);
		font-size: 10px;
		text-transform: uppercase;
		letter-spacing: 0.06em;
	}
	.settings-config-service {
		margin-top: 5px;
		text-transform: none;
		letter-spacing: 0;
	}
	.settings-config-preview pre {
		max-height: 160px;
		overflow: auto;
		margin: 0;
		padding: 8px;
		border: 1px solid var(--border2);
		border-radius: var(--r);
		background: var(--bg);
		color: var(--fg2);
		font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
		font-size: 11px;
		line-height: 1.45;
		white-space: pre-wrap;
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
	.model-picker-search {
		width: 100%;
		box-sizing: border-box;
		padding: 7px 9px;
		border: 1px solid var(--border2);
		border-radius: var(--r);
		background: var(--panel);
		color: var(--fg);
		font: inherit;
		font-size: 12px;
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
	.model-purpose-label { margin-left: auto; display: inline-flex; gap: 4px; }
	.model-purpose-label button { border: 1px solid var(--border); border-radius: 999px; padding: 2px 8px; background: transparent; color: var(--fg3); font-size: .7rem; }
	.model-purpose-label button.active { border-color: var(--accent); background: color-mix(in srgb, var(--accent) 14%, transparent); color: var(--fg); }
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
	.user-plugin-head {
		display: flex;
		align-items: center;
		gap: 10px;
	}
	.user-plugin-head span { margin-right: auto; }
	.user-plugin-row {
		display: flex;
		align-items: flex-start;
		justify-content: space-between;
		gap: 12px;
		padding: 10px 0;
		border-top: 1px solid var(--border);
	}
	.user-plugin-info { min-width: 0; }
	.user-plugin-controls {
		display: flex;
		align-items: center;
		gap: 8px;
		flex-shrink: 0;
		flex-wrap: wrap;
		justify-content: flex-end;
	}
	.user-plugin-btn { padding: 5px 10px; font-size: 12px; }
	.user-plugin-btn.danger { color: var(--danger, #9b3d32); border-color: var(--danger, #9b3d32); }
	.plugin-editor-dialog {
		position: fixed;
		left: 50%;
		top: 50%;
		z-index: 1002;
		transform: translate(-50%, -50%);
		width: min(880px, calc(100vw - 40px));
		height: min(680px, calc(100vh - 40px));
		display: flex;
		flex-direction: column;
		border: 1px solid var(--border);
		border-radius: var(--r);
		background: var(--panel2, var(--panel));
		box-shadow: 0 18px 56px rgba(0, 0, 0, 0.28);
		overflow: hidden;
	}
	.plugin-editor-body {
		flex: 1;
		min-height: 0;
		display: flex;
		flex-direction: column;
		gap: 8px;
		padding: 14px 16px;
	}
	.plugin-editor-ta {
		flex: 1;
		min-height: 0;
		width: 100%;
		box-sizing: border-box;
		resize: none;
		border: 1px solid var(--border2);
		border-radius: var(--r);
		padding: 10px 11px;
		background: var(--bg);
		color: var(--fg);
		font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
		font-size: 12.5px;
		line-height: 1.6;
		white-space: pre;
		tab-size: 4;
	}
	.plugin-editor-foot {
		display: flex;
		align-items: center;
		justify-content: flex-end;
		gap: 8px;
		padding: 12px 16px;
		border-top: 1px solid var(--border);
	}
	.plugin-editor-foot .primary { background: var(--accent); color: #fff; border-color: var(--accent); }
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
	.settings-radio-set {
		display: flex;
		flex-direction: column;
		gap: 6px;
		margin-bottom: 10px;
	}
	.settings-radio-title {
		font-size: 12px;
		font-weight: 600;
		color: var(--fg);
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
		padding: var(--btn-sm-padding);
		border: 1px solid var(--border2);
		border-radius: var(--btn-sm-radius);
		background: var(--panel);
		color: var(--fg2);
		font-size: var(--btn-sm-font-size);
		cursor: pointer;
		font-family: inherit;
	}
	.ghost-btn:hover { background: var(--bg2); }
	.ghost-btn:disabled { opacity: 0.4; cursor: not-allowed; }
	.model-picker-entry { min-width: 0; }
	.model-metadata-editor { margin-top: 3px; padding: 0 7px 6px; border: 1px solid var(--border); border-radius: var(--r); background: var(--panel); }
	.model-metadata-editor summary { padding: 6px 0; color: var(--fg3); font-size: 10px; cursor: pointer; }
	.model-metadata-fields { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 7px; }
	.model-metadata-fields label { display: grid; gap: 3px; min-width: 0; color: var(--fg3); font-size: 9px; letter-spacing: .03em; }
	.model-metadata-fields label.wide { grid-column: 1 / -1; }
	.model-metadata-fields input, .model-metadata-fields select, .model-metadata-fields textarea { min-width: 0; width: 100%; box-sizing: border-box; padding: 6px 7px; border: 1px solid var(--border2); border-radius: var(--r); background: var(--bg); color: var(--fg); font: inherit; font-size: 11px; }
	.model-metadata-fields textarea { resize: vertical; line-height: 1.4; }
</style>
