import { getLang, t } from '$lib/i18n/index.svelte';
import {
	canAccessSettingsTab as canAccessSettingsTabFor,
	defaultSettingsTab as defaultSettingsTabFor,
	type PermissionGroup
} from '$lib/permissionGroups';
import {
	normalizeSettingsDetail,
	settingsTabShownAtDetail,
	type SettingsDetailLevel
} from '$lib/settingsDetail';
import type { ApiFetch } from '$lib/transport/api-fetch';

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

type SettingsActor = {
	permission_groups?: PermissionGroup[];
	settings_tab?: string | null;
};

type SettingsControllerDeps<TActor extends SettingsActor> = {
	apiFetch: ApiFetch;
	currentUser: () => TActor | null;
	setCurrentUser: (actor: TActor) => void;
	loadAvailableModels: () => void | Promise<void>;
	loadModelSettings: () => void | Promise<void>;
	loadUserSettings: () => void | Promise<void>;
	loadExportTemplates: () => void | Promise<void>;
	cancelModelSelection: () => void;
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
		if (tab === 'models') void deps.loadModelSettings();
		if (tab === 'db' || tab === 'server_misc' || tab === 'logs') void loadSettingsStatus();
		if (tab === 'users') void deps.loadUserSettings();
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
		updateRenderLimits
	};
}
