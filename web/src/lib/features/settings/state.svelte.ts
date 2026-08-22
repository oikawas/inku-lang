import { getLang, t } from '$lib/i18n/index.svelte';
import {
	canAccessSettingsTab as canAccessSettingsTabFor,
	defaultSettingsTab as defaultSettingsTabFor,
	holdsPermissionGroup,
	type PermissionGroup
} from '$lib/permissionGroups';
import {
	normalizeSettingsDetail,
	settingsTabShownAtDetail,
	type SettingsDetailLevel
} from '$lib/settingsDetail';
import type { ApiFetch } from '$lib/transport/api-fetch';
import { PROVIDER_GROUPS, type ModelOption, type Provider, type ProviderGroup } from '$lib/models';

// The detail level is a preference for this browser screen, not member data;
// persisting it on the Server would require a field the member schema lacks.
const SETTINGS_DETAIL_KEY = 'inku-settings-detail';

export type SettingsMode = 'model' | 'settings';
export type SettingsTab =
	| 'connection'
	| 'models'
	| 'db'
	| 'plugins'
	| 'users'
	| 'unread'
	| 'export'
	| 'misc'
	| 'server_misc'
	| 'logs'
	| 'limits';

export type PluginItem = {
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

export type DbBackupEntry = {
	kind: 'auto' | 'manual';
	name: string;
	at: number;
	size_bytes: number;
	generation: number | null;
};

export type SettingsStatus = {
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
		backup_hour: number;
		backup_minute: number;
		last_auto_backup_at: number;
		next_auto_backup_at: number;
		backup_dir: string;
		auto_count: number;
		manual_count: number;
		backups: DbBackupEntry[];
		backups_total_count: number;
		backups_total_size_bytes: number;
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
	render_concurrency: {
		server_limit: number;
		client_limit: number;
		min_limit: number;
		max_limit: number;
		note: string;
	};
	render_limits: {
		limits: Record<string, number>;
		defaults: Record<string, number>;
		groups: Record<string, string[]>;
		absolute_max: number;
		bytes_per_mark: Record<string, number>;
		note: string;
	};
	log_retention: {
		enabled: boolean;
		retention_days: number;
		rotate: 'daily' | 'weekly' | 'monthly';
		compress: boolean;
		log_dir: string;
		files: string[];
		note: string;
	};
};

export type ModelProviderSetting = {
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

export type ModelSettings = {
	providers: Record<string, ModelProviderSetting>;
};

export type ModelFetchResult = {
	type: 'success' | 'error';
	message: string;
};

export type SettingsConfirmation = {
	message: string;
	run: () => void;
	destructive?: boolean;
	runLabel?: string;
};

export type SettingsUserGroup = {
	id: string;
	name: string;
	at: number;
};

export type SettingsUserItem = {
	id: string;
	username: string;
	email: string;
	permission_groups: PermissionGroup[];
	permission_group_labels: string[];
	group_id: string | null;
	group_name: string | null;
	image_generation_count: number;
	at: number;
};

export type CreateSettingsUserInput = {
	username: string;
	email: string;
	password: string;
	permission_groups: PermissionGroup[];
	group_id: string | null;
};

export type UpdateSettingsUserInput = Omit<CreateSettingsUserInput, 'password'> & {
	password?: string;
};

type SettingsActor = {
	permission_groups?: PermissionGroup[];
	settings_tab?: string | null;
	group_id?: string | null;
};

type SettingsControllerDeps<TActor extends SettingsActor> = {
	apiFetch: ApiFetch;
	currentUser: () => TActor | null;
	setCurrentUser: (actor: TActor) => void;
	loadAvailableModels: () => void | Promise<void>;
	refreshCurrentUserSettings: () => boolean | Promise<boolean>;
	loadExportTemplates: () => void | Promise<void>;
	cancelModelSelection: () => void;
	requestConfirmation: (confirmation: SettingsConfirmation) => void;
	setRenderFanoutLimit: (limit: number) => void;
	describeApiError: (detail: unknown, status: number) => string;
};

export type SettingsController = {
	readonly opened: boolean;
	readonly mode: SettingsMode;
	readonly tab: SettingsTab;
	readonly detail: SettingsDetailLevel;
	readonly status: SettingsStatus | null;
	readonly statusError: string | null;
	readonly statusLoading: boolean;
	readonly dbBackupStatus: string | null;
	readonly outputSaveStatus: string | null;
	readonly logRetentionStatus: string | null;
	readonly renderLimitsStatus: string | null;
	readonly pluginActionStatus: string | null;
	readonly renderConcurrencyStatus: string | null;
	readonly modelSettings: ModelSettings | null;
	readonly modelSettingsStatus: string | null;
	readonly modelFetchResults: Record<string, ModelFetchResult>;
	readonly modelSettingsLoading: boolean;
	readonly modelCatalog: ProviderGroup[];
	readonly users: SettingsUserItem[];
	readonly groups: SettingsUserGroup[];
	readonly userAdministrationStatus: string | null;
	readonly userAdministrationLoading: boolean;
	restoreDetail: () => void;
	setDetail: (detail: SettingsDetailLevel) => void;
	openSettings: (tab?: SettingsTab | null) => void;
	openModelSelection: () => void;
	finishModelSelection: () => void;
	close: () => void;
	selectTab: (tab: SettingsTab) => void;
	loadStatus: () => Promise<void>;
	resetForLoggedOut: () => void;
	loadPluginContent: (id: string) => Promise<string | null>;
	savePlugin: (id: string, content: string) => Promise<string[] | null>;
	createPlugin: (content: string, filename: string) => Promise<string[] | null>;
	deletePlugin: (id: string) => Promise<boolean>;
	setPluginEnabled: (id: string, enabled: boolean) => Promise<boolean>;
	updateDbBackupSettings: (intervalDays: number, maxGenerations: number, backupHour: number, backupMinute: number) => Promise<void>;
	runDbBackupNow: () => Promise<void>;
	updateOutputSaveSettings: (enabled: boolean, outputDir: string, pngSize: number) => Promise<void>;
	updateRenderConcurrencySettings: (serverLimit: number, clientLimit: number) => Promise<void>;
	updateLogRetentionSettings: (enabled: boolean, retentionDays: number, rotate: string, compress: boolean) => Promise<void>;
	updateRenderLimits: (patch: Record<string, number> | null) => Promise<void>;
	updateModelProvider: (provider: Provider, patch: Partial<ModelProviderSetting>) => void;
	addModelProvider: (provider: Provider, patch: Partial<ModelProviderSetting>) => Promise<void>;
	askDeleteModelProvider: (provider: Provider) => void;
	fetchProviderModels: (provider: Provider) => Promise<void>;
	askClearModelApiKey: (provider: Provider) => void;
	saveModelProviderName: (provider: Provider, label: string) => Promise<void>;
	saveModelProviderMemo: (provider: Provider, memo: string) => Promise<void>;
	saveModelProvider: (provider: Provider, patch?: Partial<ModelProviderSetting>) => Promise<void>;
	saveModelSettings: () => Promise<void>;
	loadModelSettings: () => Promise<void>;
	loadUserAdministration: () => Promise<void>;
	addUser: (input: CreateSettingsUserInput) => Promise<boolean>;
	updateUser: (id: string, input: UpdateSettingsUserInput) => Promise<boolean>;
	removeUser: (id: string) => Promise<boolean>;
	addGroup: (name: string) => Promise<boolean>;
	removeGroup: (group: SettingsUserGroup) => Promise<boolean>;
	updateGroup: (id: string, name: string) => Promise<boolean>;
};

function isSettingsContentTab(tab: string | null | undefined): tab is Exclude<SettingsTab, 'connection'> {
	return tab === 'models' || tab === 'db' || tab === 'plugins' || tab === 'users' || tab === 'unread' || tab === 'export' || tab === 'misc' || tab === 'server_misc' || tab === 'logs';
}

export function createSettingsController<TActor extends SettingsActor>(
	deps: SettingsControllerDeps<TActor>
): SettingsController {
	let settingsOpen = $state(false);
	let settingsMode = $state<SettingsMode>('settings');
	let settingsTab = $state<SettingsTab>('connection');
	let settingsDetail = $state<SettingsDetailLevel>('standard');
	let settingsStatus = $state<SettingsStatus | null>(null);
	let settingsStatusError = $state<string | null>(null);
	let settingsStatusLoading = $state(false);
	let dbBackupStatus = $state<string | null>(null);
	let outputSaveStatus = $state<string | null>(null);
	let logRetentionStatus = $state<string | null>(null);
	let renderLimitsStatus = $state<string | null>(null);
	let pluginActionStatus = $state<string | null>(null);
	let renderConcurrencyStatus = $state<string | null>(null);
	let modelSettings = $state<ModelSettings | null>(null);
	let modelSettingsStatus = $state<string | null>(null);
	let modelFetchResults = $state<Record<string, ModelFetchResult>>({});
	let modelSettingsLoading = $state(false);
	let modelCatalog = $state<ProviderGroup[]>(PROVIDER_GROUPS.filter((group) => group.id !== 'nvidia'));
	let users = $state<SettingsUserItem[]>([]);
	let groups = $state<SettingsUserGroup[]>([]);
	let userAdministrationStatus = $state<string | null>(null);
	let userAdministrationLoading = $state(false);
	let userAdministrationRequestId = 0;

	// Both gates must pass: membership controls authority, while detail controls
	// which authorized tabs the reader asked the dialog to show.
	function canAccessSettingsTab(tab: SettingsTab): boolean {
		const currentUser = deps.currentUser();
		return canAccessSettingsTabFor(tab, currentUser) && settingsTabShownAtDetail(tab, settingsDetail);
	}

	function defaultSettingsTab(): SettingsTab {
		const preferred = defaultSettingsTabFor(deps.currentUser());
		// Export is neither administrator-only nor detail-only, so it is a safe fallback.
		return canAccessSettingsTab(preferred) ? preferred : 'export';
	}

	function loadTab(tab: SettingsTab): void {
		if (tab === 'models') void loadModelSettings();
		if (tab === 'db' || tab === 'server_misc' || tab === 'logs') void loadSettingsStatus();
		if (tab === 'users') void loadUserAdministration();
		if (tab === 'export') void deps.loadExportTemplates();
	}

	async function updateUserSettingsTab(tab: SettingsTab): Promise<void> {
		const currentUser = deps.currentUser();
		if (!currentUser || !isSettingsContentTab(tab)) return;
		try {
			const response = await deps.apiFetch('/api/auth/me/settings', {
				method: 'PATCH',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ settings_tab: tab })
			});
			if (!response.ok) {
				const body = await response.json().catch(() => ({})) as { detail?: unknown };
				throw new Error(deps.describeApiError(body.detail, response.status));
			}
			deps.setCurrentUser(await response.json() as TActor);
		} catch (error) {
			console.warn('failed to update settings tab', error);
		}
	}

	function selectSettingsTab(tab: SettingsTab): void {
		if (!canAccessSettingsTab(tab)) return;
		settingsTab = tab;
		void updateUserSettingsTab(tab);
		loadTab(tab);
	}

	function setSettingsDetail(detail: SettingsDetailLevel): void {
		settingsDetail = detail;
		try { localStorage.setItem(SETTINGS_DETAIL_KEY, detail); } catch { /* Private browsing may deny storage. */ }
		// If narrowing hides the active tab, route through normal selection so its data loads.
		if (settingsOpen && !canAccessSettingsTab(settingsTab)) selectSettingsTab(defaultSettingsTab());
	}

	function restoreDetail(): void {
		settingsDetail = normalizeSettingsDetail(localStorage.getItem(SETTINGS_DETAIL_KEY));
	}

	function openSettings(tab: SettingsTab | null = null): void {
		settingsMode = 'settings';
		const saved = deps.currentUser()?.settings_tab;
		const candidate = tab ?? (isSettingsContentTab(saved) ? saved : defaultSettingsTab());
		const nextTab = canAccessSettingsTab(candidate) ? candidate : defaultSettingsTab();
		settingsTab = nextTab;
		settingsOpen = true;
		loadTab(nextTab);
	}

	function openModelSelection(): void {
		settingsMode = 'model';
		settingsTab = 'connection';
		settingsOpen = true;
		void deps.loadAvailableModels();
	}

	function finishModelSelection(): void {
		settingsOpen = false;
	}

	function close(): void {
		if (settingsMode === 'model') deps.cancelModelSelection();
		settingsOpen = false;
	}

	function resetForLoggedOut(): void {
		// Invalidate requests before clearing state so a late administration
		// response cannot repopulate account data after the session has ended.
		++userAdministrationRequestId;
		users = [];
		groups = [];
		userAdministrationStatus = null;
		userAdministrationLoading = false;
		settingsStatus = null;
		settingsStatusError = t().loginRequiredMessage;
	}

	async function loadSettingsStatus(): Promise<void> {
		const currentUser = deps.currentUser();
		const isAdmin = currentUser?.permission_groups?.includes('admins') === true;
		if (!currentUser || !isAdmin) {
			settingsStatus = null;
			settingsStatusError = currentUser ? t().settingsAdminOnlyMessage : t().loginRequiredMessage;
			return;
		}
		settingsStatusLoading = true;
		try {
			const response = await deps.apiFetch('/api/settings/status');
			if (!response.ok) {
				const body = await response.json().catch(() => ({})) as { detail?: unknown };
				throw new Error(deps.describeApiError(body.detail, response.status));
			}
			settingsStatus = await response.json() as SettingsStatus;
			settingsStatusError = null;
			dbBackupStatus = null;
			outputSaveStatus = null;
			logRetentionStatus = null;
			renderLimitsStatus = null;
		} catch (error) {
			settingsStatus = null;
			settingsStatusError = error instanceof Error ? error.message : String(error);
		} finally {
			settingsStatusLoading = false;
		}
	}

	// Some deployed Servers predate plugin management. Keep that compatibility
	// case distinct from validation failures returned by an available endpoint.
	function pluginErrorMessage(status: number, detail: unknown): string {
		if (status === 404 || status === 405 || status === 501) {
			return getLang() === 'ja'
				? 'このプラグイン管理機能はサーバー側が未実装です（バックエンド待ち）。'
				: 'This plugin management endpoint is not implemented on the server yet.';
		}
		if (Array.isArray(detail)) return (detail as string[]).join(' / ');
		if (typeof detail === 'string') return detail;
		return `HTTP ${status}`;
	}

	async function loadPluginContent(id: string): Promise<string | null> {
		pluginActionStatus = null;
		try {
			const response = await deps.apiFetch(`/api/plugins/${encodeURIComponent(id)}/content`);
			if (!response.ok) {
				const body = await response.json().catch(() => ({})) as { detail?: unknown };
				pluginActionStatus = pluginErrorMessage(response.status, body.detail);
				return null;
			}
			const data = await response.json() as { content?: string };
			return data.content ?? '';
		} catch (error) {
			pluginActionStatus = error instanceof Error ? error.message : String(error);
			return null;
		}
	}

	// Returns null on success, or validation messages on failure.
	async function savePlugin(id: string, content: string): Promise<string[] | null> {
		pluginActionStatus = null;
		try {
			const response = await deps.apiFetch(`/api/plugins/${encodeURIComponent(id)}`, {
				method: 'PUT',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ content })
			});
			if (!response.ok) {
				const body = await response.json().catch(() => ({})) as { detail?: unknown };
				return Array.isArray(body.detail) ? body.detail as string[] : [pluginErrorMessage(response.status, body.detail)];
			}
			await loadSettingsStatus();
			return null;
		} catch (error) {
			return [error instanceof Error ? error.message : String(error)];
		}
	}

	async function createPlugin(content: string, filename: string): Promise<string[] | null> {
		pluginActionStatus = null;
		try {
			const response = await deps.apiFetch('/api/plugins', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ content, filename })
			});
			if (!response.ok) {
				const body = await response.json().catch(() => ({})) as { detail?: unknown };
				return Array.isArray(body.detail) ? body.detail as string[] : [pluginErrorMessage(response.status, body.detail)];
			}
			await loadSettingsStatus();
			return null;
		} catch (error) {
			return [error instanceof Error ? error.message : String(error)];
		}
	}

	async function deletePlugin(id: string): Promise<boolean> {
		pluginActionStatus = null;
		try {
			const response = await deps.apiFetch(`/api/plugins/${encodeURIComponent(id)}`, { method: 'DELETE' });
			if (!response.ok) {
				const body = await response.json().catch(() => ({})) as { detail?: unknown };
				pluginActionStatus = pluginErrorMessage(response.status, body.detail);
				return false;
			}
			await loadSettingsStatus();
			return true;
		} catch (error) {
			pluginActionStatus = error instanceof Error ? error.message : String(error);
			return false;
		}
	}

	async function setPluginEnabled(id: string, enabled: boolean): Promise<boolean> {
		pluginActionStatus = null;
		try {
			const response = await deps.apiFetch(`/api/plugins/${encodeURIComponent(id)}/enabled`, {
				method: 'PUT',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ enabled })
			});
			if (!response.ok) {
				const body = await response.json().catch(() => ({})) as { detail?: unknown };
				pluginActionStatus = pluginErrorMessage(response.status, body.detail);
				return false;
			}
			await loadSettingsStatus();
			return true;
		} catch (error) {
			pluginActionStatus = error instanceof Error ? error.message : String(error);
			return false;
		}
	}

	async function updateDbBackupSettings(intervalDays: number, maxGenerations: number, backupHour: number, backupMinute: number): Promise<void> {
		dbBackupStatus = null;
		try {
			const response = await deps.apiFetch('/api/settings/db-backup', {
				method: 'PUT',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ interval_days: intervalDays, max_generations: maxGenerations, backup_hour: backupHour, backup_minute: backupMinute })
			});
			if (!response.ok) {
				const body = await response.json().catch(() => ({})) as { detail?: unknown };
				throw new Error(deps.describeApiError(body.detail, response.status));
			}
			const next = await response.json() as SettingsStatus['db_backup'];
			if (settingsStatus) settingsStatus = { ...settingsStatus, db_backup: next };
		} catch (error) {
			dbBackupStatus = t().settingsDbBackupSaveFailed;
			console.warn('failed to update DB backup settings', error);
		}
	}

	async function runDbBackupNow(): Promise<void> {
		dbBackupStatus = null;
		try {
			const response = await deps.apiFetch('/api/settings/db-backup/run', { method: 'POST' });
			if (!response.ok) {
				const body = await response.json().catch(() => ({})) as { detail?: unknown };
				throw new Error(deps.describeApiError(body.detail, response.status));
			}
			await loadSettingsStatus();
			dbBackupStatus = t().settingsDbBackupRunDone;
		} catch (error) {
			dbBackupStatus = error instanceof Error ? error.message : String(error);
		}
	}

	async function updateOutputSaveSettings(enabled: boolean, outputDir: string, pngSize: number): Promise<void> {
		outputSaveStatus = null;
		try {
			const response = await deps.apiFetch('/api/settings/output-save', {
				method: 'PUT',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ enabled, output_dir: outputDir, png_size: pngSize })
			});
			if (!response.ok) {
				const body = await response.json().catch(() => ({})) as { detail?: unknown };
				throw new Error(deps.describeApiError(body.detail, response.status));
			}
			const next = await response.json() as SettingsStatus['output_save'];
			if (settingsStatus) settingsStatus = { ...settingsStatus, output_save: next };
			outputSaveStatus = t().settingsOutputSaveSaved;
		} catch (error) {
			outputSaveStatus = error instanceof Error ? error.message : String(error);
			console.warn('failed to update output save settings', error);
		}
	}

	async function updateRenderConcurrencySettings(serverLimit: number, clientLimit: number): Promise<void> {
		renderConcurrencyStatus = null;
		try {
			const response = await deps.apiFetch('/api/settings/render-concurrency', {
				method: 'PUT',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ server_limit: serverLimit, client_limit: clientLimit })
			});
			if (!response.ok) {
				const body = await response.json().catch(() => ({})) as { detail?: unknown };
				throw new Error(deps.describeApiError(body.detail, response.status));
			}
			const next = await response.json() as SettingsStatus['render_concurrency'];
			if (settingsStatus) settingsStatus = { ...settingsStatus, render_concurrency: next };
			// Apply the client limit to this tab immediately; other tabs load it later.
			deps.setRenderFanoutLimit(next.client_limit);
			renderConcurrencyStatus = t().settingsRenderConcurrencySaved;
		} catch (error) {
			renderConcurrencyStatus = error instanceof Error ? error.message : String(error);
			console.warn('failed to update render concurrency settings', error);
		}
	}

	// A null patch restores defaults. The response is authoritative after server normalization.
	async function updateRenderLimits(patch: Record<string, number> | null): Promise<void> {
		renderLimitsStatus = null;
		try {
			const response = await deps.apiFetch('/api/settings/limits', {
				method: 'PUT',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify(patch === null ? { reset_to_defaults: true } : patch)
			});
			if (!response.ok) {
				const body = await response.json().catch(() => ({})) as { detail?: unknown };
				throw new Error(deps.describeApiError(body.detail, response.status));
			}
			const next = await response.json() as SettingsStatus['render_limits'];
			if (settingsStatus) settingsStatus = { ...settingsStatus, render_limits: next };
			renderLimitsStatus = t().settingsRenderLimitsSaved;
		} catch (error) {
			renderLimitsStatus = error instanceof Error ? error.message : String(error);
			console.warn('failed to update render limits', error);
		}
	}

	async function updateLogRetentionSettings(enabled: boolean, retentionDays: number, rotate: string, compress: boolean): Promise<void> {
		logRetentionStatus = null;
		try {
			const response = await deps.apiFetch('/api/settings/log-retention', {
				method: 'PUT',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ enabled, retention_days: retentionDays, rotate, compress })
			});
			if (!response.ok) {
				const body = await response.json().catch(() => ({})) as { detail?: unknown };
				throw new Error(deps.describeApiError(body.detail, response.status));
			}
			const next = await response.json() as SettingsStatus['log_retention'];
			if (settingsStatus) settingsStatus = { ...settingsStatus, log_retention: next };
			logRetentionStatus = t().settingsLogRetentionSaved;
		} catch (error) {
			logRetentionStatus = error instanceof Error ? error.message : String(error);
			console.warn('failed to update log retention settings', error);
		}
	}

	function isAdministrator(): boolean {
		return deps.currentUser()?.permission_groups?.includes('admins') === true;
	}

	// The Server response is authoritative for both catalog metadata and stored
	// provider settings; never retain a locally assembled approximation after a save.
	function acceptModelResponse(data: { catalog: ProviderGroup[]; settings: ModelSettings }, status: string): void {
		modelCatalog = data.catalog;
		modelSettings = data.settings;
		modelSettingsStatus = status;
	}

	async function loadModelSettings(): Promise<void> {
		if (!isAdministrator()) {
			modelSettings = null;
			modelSettingsStatus = t().settingsAdminOnlyMessage;
			return;
		}
		modelSettingsLoading = true;
		try {
			const response = await deps.apiFetch('/api/settings/models', { cache: 'no-store' });
			if (!response.ok) throw new Error(`HTTP ${response.status}`);
			acceptModelResponse(await response.json(), '');
			modelSettingsStatus = null;
		} catch (error) {
			modelSettingsStatus = error instanceof Error ? error.message : String(error);
		} finally {
			modelSettingsLoading = false;
		}
	}

	function updateModelProvider(provider: Provider, patch: Partial<ModelProviderSetting>): void {
		if (!modelSettings) return;
		const current = modelSettings.providers[provider] ?? { base_url: '', api_key_set: false, api_key_hint: null };
		modelSettings = {
			...modelSettings,
			providers: { ...modelSettings.providers, [provider]: { ...current, ...patch } }
		};
	}

	async function addModelProvider(provider: Provider, patch: Partial<ModelProviderSetting>): Promise<void> {
		if (!modelSettings || !provider || !isAdministrator()) return;
		modelSettingsLoading = true;
		try {
			const response = await deps.apiFetch('/api/settings/models', {
				method: 'PUT',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ providers: { [provider]: {
					label: patch.label ?? provider,
					kind: patch.kind,
					requires_api_key: patch.requires_api_key,
					memo: patch.memo,
					models: patch.models ?? [],
					base_url: patch.base_url ?? patch.default_base_url ?? '',
					api_key: patch.api_key || undefined,
					enabled_models: patch.enabled_models ?? {}
				} } })
			});
			if (!response.ok) throw new Error(`HTTP ${response.status}`);
			acceptModelResponse(await response.json(), t().settingsModelSaved);
			await deps.loadAvailableModels();
		} catch (error) {
			modelSettingsStatus = error instanceof Error ? error.message : String(error);
			throw error;
		} finally {
			modelSettingsLoading = false;
		}
	}

	function askDeleteModelProvider(provider: Provider): void {
		const label = modelCatalog.find((item) => item.id === provider)?.label ?? provider;
		deps.requestConfirmation({
			message: t().settingsModelDeleteServiceConfirm(label),
			destructive: true,
			run: () => { void deleteModelProvider(provider); }
		});
	}

	async function deleteModelProvider(provider: Provider): Promise<void> {
		if (!isAdministrator()) return;
		modelSettingsLoading = true;
		try {
			const response = await deps.apiFetch('/api/settings/models', {
				method: 'PUT',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ providers: { [provider]: { delete: true } } })
			});
			if (!response.ok) throw new Error(`HTTP ${response.status}`);
			acceptModelResponse(await response.json(), t().settingsModelSaved);
			await deps.loadAvailableModels();
		} catch (error) {
			modelSettingsStatus = error instanceof Error ? error.message : String(error);
		} finally {
			modelSettingsLoading = false;
		}
	}

	async function fetchProviderModels(provider: Provider): Promise<void> {
		if (!isAdministrator()) return;
		modelSettingsLoading = true;
		const nextResults = { ...modelFetchResults };
		delete nextResults[provider];
		modelFetchResults = nextResults;
		try {
			const response = await deps.apiFetch(`/api/settings/models/${encodeURIComponent(provider)}/fetch-models`, { method: 'POST' });
			if (!response.ok) {
				const body = await response.json().catch(() => ({})) as { detail?: unknown };
				throw new Error(deps.describeApiError(body.detail, response.status));
			}
			acceptModelResponse(await response.json(), t().settingsModelFetchModelsSaved);
			modelFetchResults = { ...modelFetchResults, [provider]: { type: 'success', message: t().settingsModelFetchModelsSaved } };
			await deps.loadAvailableModels();
		} catch (error) {
			const message = error instanceof Error ? error.message : String(error);
			modelFetchResults = { ...modelFetchResults, [provider]: { type: 'error', message } };
			modelSettingsStatus = message;
		} finally {
			modelSettingsLoading = false;
		}
	}

	function askClearModelApiKey(provider: Provider): void {
		const label = modelCatalog.find((item) => item.id === provider)?.label ?? provider;
		deps.requestConfirmation({
			message: t().settingsModelClearApiKeyConfirm(label),
			destructive: true,
			runLabel: t().settingsModelClearApiKey,
			run: () => { void clearModelApiKey(provider); }
		});
	}

	async function clearModelApiKey(provider: Provider): Promise<void> {
		if (!isAdministrator()) return;
		modelSettingsLoading = true;
		try {
			const current = modelSettings?.providers[provider];
			const response = await deps.apiFetch('/api/settings/models', {
				method: 'PUT',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ providers: { [provider]: {
					base_url: current?.base_url,
					clear_api_key: true,
					enabled_models: current?.enabled_models ?? {}
				} } })
			});
			if (!response.ok) throw new Error(`HTTP ${response.status}`);
			acceptModelResponse(await response.json(), t().settingsModelApiKeyCleared);
		} catch (error) {
			modelSettingsStatus = error instanceof Error ? error.message : String(error);
		} finally {
			modelSettingsLoading = false;
		}
	}

	// Catalog metadata and the modal draft form one provider payload. Secret
	// input is used only here and is never copied into confirmation or error state.
	function modelProviderPayload(id: string, provider: ModelProviderSetting, labelOverride?: string, memoOverride?: string) {
		const catalogProvider = modelCatalog.find((item) => item.id === id);
		return {
			label: labelOverride ?? catalogProvider?.label,
			kind: catalogProvider?.kind,
			requires_api_key: catalogProvider?.requires_api_key,
			memo: memoOverride ?? catalogProvider?.memo,
			models: provider.models ?? catalogProvider?.models ?? [],
			base_url: provider.base_url,
			api_key: provider.api_key || undefined,
			clear_api_key: !!provider.clear_api_key,
			enabled_models: provider.enabled_models ?? {}
		};
	}

	async function saveProviderPayload(provider: Provider, payload: ReturnType<typeof modelProviderPayload>): Promise<void> {
		const response = await deps.apiFetch('/api/settings/models', {
			method: 'PUT',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({ providers: { [provider]: payload } })
		});
		if (!response.ok) throw new Error(`HTTP ${response.status}`);
		acceptModelResponse(await response.json(), t().settingsModelSaved);
		await deps.loadAvailableModels();
	}

	async function saveModelProviderName(provider: Provider, label: string): Promise<void> {
		if (!modelSettings || !isAdministrator()) return;
		const providerSettings = modelSettings.providers[provider];
		const nextLabel = label.trim();
		if (!providerSettings || !nextLabel) return;
		modelSettingsLoading = true;
		try {
			await saveProviderPayload(provider, modelProviderPayload(provider, providerSettings, nextLabel));
		} catch (error) {
			modelSettingsStatus = error instanceof Error ? error.message : String(error);
		} finally {
			modelSettingsLoading = false;
		}
	}

	async function saveModelProviderMemo(provider: Provider, memo: string): Promise<void> {
		if (!modelSettings || !isAdministrator()) return;
		const providerSettings = modelSettings.providers[provider];
		if (!providerSettings) return;
		modelSettingsLoading = true;
		try {
			await saveProviderPayload(provider, modelProviderPayload(provider, providerSettings, undefined, memo));
		} catch (error) {
			modelSettingsStatus = error instanceof Error ? error.message : String(error);
		} finally {
			modelSettingsLoading = false;
		}
	}

	async function saveModelProvider(provider: Provider, patch: Partial<ModelProviderSetting> = {}): Promise<void> {
		if (!modelSettings || !isAdministrator()) return;
		const current = modelSettings.providers[provider];
		if (!current) return;
		modelSettingsLoading = true;
		try {
			await saveProviderPayload(provider, modelProviderPayload(provider, { ...current, ...patch }));
		} catch (error) {
			modelSettingsStatus = error instanceof Error ? error.message : String(error);
		} finally {
			modelSettingsLoading = false;
		}
	}

	async function saveModelSettings(): Promise<void> {
		if (!modelSettings || !isAdministrator()) return;
		modelSettingsLoading = true;
		try {
			const providers = Object.fromEntries(Object.entries(modelSettings.providers).map(([id, provider]) => [id, modelProviderPayload(id, provider)]));
			const response = await deps.apiFetch('/api/settings/models', {
				method: 'PUT',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ providers })
			});
			if (!response.ok) throw new Error(`HTTP ${response.status}`);
			acceptModelResponse(await response.json(), t().settingsModelSaved);
			await deps.loadAvailableModels();
		} catch (error) {
			modelSettingsStatus = error instanceof Error ? error.message : String(error);
		} finally {
			modelSettingsLoading = false;
		}
	}

	// Session identity and administration lists have independent request clocks.
	// Refresh the page-owned actor first, then guard only the list response here.
	async function loadUserAdministration(): Promise<void> {
		const requestId = ++userAdministrationRequestId;
		userAdministrationLoading = true;
		try {
			const refreshed = await deps.refreshCurrentUserSettings();
			if (requestId !== userAdministrationRequestId) return;
			if (!refreshed) throw new Error(t().loginRequiredMessage);
			const actor = deps.currentUser();
			if (!holdsPermissionGroup(actor, 'admins')) {
				users = [];
				groups = [];
				userAdministrationStatus = null;
				return;
			}
			const [groupsResponse, usersResponse] = await Promise.all([
				deps.apiFetch('/api/user-groups', { cache: 'no-store' }),
				deps.apiFetch('/api/users', { cache: 'no-store' })
			]);
			if (!groupsResponse.ok || !usersResponse.ok) throw new Error(t().userInfoLoadFailed);
			const [nextGroups, nextUsers] = await Promise.all([
				groupsResponse.json() as Promise<SettingsUserGroup[]>,
				usersResponse.json() as Promise<SettingsUserItem[]>
			]);
			if (requestId !== userAdministrationRequestId) return;
			groups = nextGroups;
			users = nextUsers;
			userAdministrationStatus = null;
		} catch (error) {
			if (requestId !== userAdministrationRequestId) return;
			userAdministrationStatus = error instanceof Error ? error.message : String(error);
		} finally {
			if (requestId === userAdministrationRequestId) userAdministrationLoading = false;
		}
	}

	async function administrationRequest(path: string, init: RequestInit): Promise<void> {
		const response = await deps.apiFetch(path, init);
		if (!response.ok) {
			const body = await response.json().catch(() => ({})) as { detail?: unknown };
			throw new Error(deps.describeApiError(body.detail, response.status));
		}
	}

	// Leaders may administer only ordinary users in their own group. Administrators
	// outrank that restriction, so only the leader-without-admin case is reshaped.
	function actorConstrainedUserInput<T extends CreateSettingsUserInput | UpdateSettingsUserInput>(input: T): T {
		const actor = deps.currentUser();
		const leaderOnly = !holdsPermissionGroup(actor, 'admins') && holdsPermissionGroup(actor, 'leaders');
		if (!leaderOnly) return input;
		return { ...input, permission_groups: ['users'], group_id: actor?.group_id ?? null };
	}

	async function addUser(input: CreateSettingsUserInput): Promise<boolean> {
		const constrained = actorConstrainedUserInput({ ...input, username: input.username.trim(), email: input.email.trim() });
		if (!constrained.username || !constrained.email || constrained.password.length < 8) {
			userAdministrationStatus = t().userValidationCreate;
			return false;
		}
		try {
			// The password crosses this operation boundary once for serialization;
			// it is never copied into controller state, status, logs, or confirmation.
			await administrationRequest('/api/users', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify(constrained)
			});
			await loadUserAdministration();
			return true;
		} catch (error) {
			userAdministrationStatus = error instanceof Error ? error.message : String(error);
			return false;
		}
	}

	async function updateUser(id: string, input: UpdateSettingsUserInput): Promise<boolean> {
		const constrained = actorConstrainedUserInput({ ...input, username: input.username.trim(), email: input.email.trim() });
		if (!constrained.username || !constrained.email) {
			userAdministrationStatus = t().userValidationUpdate;
			return false;
		}
		if (constrained.password && constrained.password.length < 8) {
			userAdministrationStatus = t().userPasswordTooShort;
			return false;
		}
		try {
			await administrationRequest(`/api/users/${id}`, {
				method: 'PATCH',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify(constrained)
			});
			await loadUserAdministration();
			return true;
		} catch (error) {
			userAdministrationStatus = error instanceof Error ? error.message : String(error);
			await loadUserAdministration();
			return false;
		}
	}

	async function removeUser(id: string): Promise<boolean> {
		try {
			await administrationRequest(`/api/users/${id}`, { method: 'DELETE' });
			await loadUserAdministration();
			return true;
		} catch (error) {
			userAdministrationStatus = error instanceof Error ? error.message : String(error);
			return false;
		}
	}

	async function addGroup(name: string): Promise<boolean> {
		const nextName = name.trim();
		if (!nextName) return false;
		try {
			await administrationRequest('/api/user-groups', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ name: nextName })
			});
			await loadUserAdministration();
			return true;
		} catch (error) {
			userAdministrationStatus = error instanceof Error ? error.message : String(error);
			return false;
		}
	}

	async function removeGroup(group: SettingsUserGroup): Promise<boolean> {
		try {
			await administrationRequest(`/api/user-groups/${group.id}`, { method: 'DELETE' });
			await loadUserAdministration();
			return true;
		} catch (error) {
			userAdministrationStatus = error instanceof Error ? error.message : String(error);
			return false;
		}
	}

	async function updateGroup(id: string, name: string): Promise<boolean> {
		const nextName = name.trim();
		if (!id || !nextName) return false;
		try {
			await administrationRequest(`/api/user-groups/${id}`, {
				method: 'PATCH',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ name: nextName })
			});
			await loadUserAdministration();
			return true;
		} catch (error) {
			userAdministrationStatus = error instanceof Error ? error.message : String(error);
			return false;
		}
	}

	return {
		get opened() { return settingsOpen; },
		get mode() { return settingsMode; },
		get tab() { return settingsTab; },
		get detail() { return settingsDetail; },
		get status() { return settingsStatus; },
		get statusError() { return settingsStatusError; },
		get statusLoading() { return settingsStatusLoading; },
		get dbBackupStatus() { return dbBackupStatus; },
		get outputSaveStatus() { return outputSaveStatus; },
		get logRetentionStatus() { return logRetentionStatus; },
		get renderLimitsStatus() { return renderLimitsStatus; },
		get pluginActionStatus() { return pluginActionStatus; },
		get renderConcurrencyStatus() { return renderConcurrencyStatus; },
		get modelSettings() { return modelSettings; },
		get modelSettingsStatus() { return modelSettingsStatus; },
		get modelFetchResults() { return modelFetchResults; },
		get modelSettingsLoading() { return modelSettingsLoading; },
		get modelCatalog() { return modelCatalog; },
		get users() { return users; },
		get groups() { return groups; },
		get userAdministrationStatus() { return userAdministrationStatus; },
		get userAdministrationLoading() { return userAdministrationLoading; },
		restoreDetail,
		setDetail: setSettingsDetail,
		openSettings,
		openModelSelection,
		finishModelSelection,
		close,
		selectTab: selectSettingsTab,
		loadStatus: loadSettingsStatus,
		resetForLoggedOut,
		loadPluginContent,
		savePlugin,
		createPlugin,
		deletePlugin,
		setPluginEnabled,
		updateDbBackupSettings,
		runDbBackupNow,
		updateOutputSaveSettings,
		updateRenderConcurrencySettings,
		updateLogRetentionSettings,
		updateRenderLimits,
		updateModelProvider,
		addModelProvider,
		askDeleteModelProvider,
		fetchProviderModels,
		askClearModelApiKey,
		saveModelProviderName,
		saveModelProviderMemo,
		saveModelProvider,
		saveModelSettings,
		loadModelSettings,
		loadUserAdministration,
		addUser,
		updateUser,
		removeUser,
		addGroup,
		removeGroup,
		updateGroup
	};
}
