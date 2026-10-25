import { getLang, t } from '$lib/i18n/index.svelte';
import type { ApiFetch } from '$lib/transport/api-fetch';
import type { SettingsActor } from './navigation-state.svelte';
import type { SettingsConfirmation } from './model-administration.svelte';
import { applyMeterSwitches } from '$lib/descriptionMeter.svelte';
import { applyImageUploadNotice } from '$lib/features/image-provenance/upload-notice';
import type { MeterSwitches } from '$lib/verseForm';

export type PluginItem = {
	name: string;
	namespace?: string;
	version: string;
	status: string;
	path?: string;
	reasons?: string[];
	entries?: Array<{
		qualified_name: string;
		aliases?: string[];
		surface_ja?: string[];
		surface_en?: string[];
		note_ja: string;
		note_en: string;
		has_preview?: boolean;
	}>;
	id?: string;
	enabled?: boolean;
	/** Whether the drawing uses definitions this document switches (a package
	    bundled with the core). A legacy document without them is not drawn from. */
	has_definitions?: boolean;
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
	description_meter: MeterSwitches;
	image_upload_notice: { enabled: boolean };
	db_write_lock: { locked: boolean };
	juxtaposition: { candidate_limit: number; min_limit: number; max_limit: number };
	render_limits: {
		limits: Record<string, number>;
		defaults: Record<string, number>;
		groups: Record<string, string[]>;
		absolute_max: number;
		field_bounds?: Record<string, { min: number; max: number; step: number }>;
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

type ServerAdministrationDeps<TActor extends SettingsActor> = {
	apiFetch: ApiFetch;
	currentUser: () => TActor | null;
	setRenderFanoutLimit: (limit: number) => void;
	describeApiError: (detail: unknown, status: number) => string;
	requestConfirmation: (confirmation: SettingsConfirmation) => void;
	reloadPage?: () => void;
};

export type ServerAdministration = {
	readonly status: SettingsStatus | null;
	readonly statusError: string | null;
	readonly statusLoading: boolean;
	readonly dbBackupStatus: string | null;
	readonly outputSaveStatus: string | null;
	readonly logRetentionStatus: string | null;
	readonly renderLimitsStatus: string | null;
	readonly pluginActionStatus: string | null;
	readonly renderConcurrencyStatus: string | null;
	readonly descriptionMeterStatus: string | null;
	readonly imageUploadNoticeStatus: string | null;
	readonly dbWriteLockStatus: string | null;
	readonly juxtapositionStatus: string | null;
	loadStatus: () => Promise<void>;
	resetForLoggedOut: () => void;
	deletePlugin: (id: string) => Promise<boolean>;
	setPluginEnabled: (id: string, enabled: boolean) => Promise<boolean>;
	updateDbBackupSettings: (intervalDays: number, maxGenerations: number, backupHour: number, backupMinute: number) => Promise<void>;
	runDbBackupNow: () => Promise<void>;
	deleteDbBackup: (entry: DbBackupEntry) => void;
	restoreDbBackup: (entry: DbBackupEntry) => void;
	updateOutputSaveSettings: (enabled: boolean, outputDir: string, pngSize: number) => Promise<void>;
	updateRenderConcurrencySettings: (serverLimit: number, clientLimit: number) => Promise<void>;
	updateDescriptionMeterSettings: (switches: MeterSwitches) => Promise<void>;
	updateImageUploadNotice: (enabled: boolean) => Promise<void>;
	updateDbWriteLock: (locked: boolean) => Promise<void>;
	updateJuxtapositionSettings: (candidateLimit: number) => Promise<void>;
	updateLogRetentionSettings: (enabled: boolean, retentionDays: number, rotate: string, compress: boolean) => Promise<void>;
	updateRenderLimits: (patch: Record<string, number> | null) => Promise<SettingsStatus['render_limits'] | null>;
};

export function createServerAdministration<TActor extends SettingsActor>(
	deps: ServerAdministrationDeps<TActor>
): ServerAdministration {
	let settingsStatus = $state<SettingsStatus | null>(null);
	let settingsStatusError = $state<string | null>(null);
	let settingsStatusLoading = $state(false);
	let dbBackupStatus = $state<string | null>(null);
	let outputSaveStatus = $state<string | null>(null);
	let logRetentionStatus = $state<string | null>(null);
	let renderLimitsStatus = $state<string | null>(null);
	let pluginActionStatus = $state<string | null>(null);
	let renderConcurrencyStatus = $state<string | null>(null);
	let descriptionMeterStatus = $state<string | null>(null);
	let imageUploadNoticeStatus = $state<string | null>(null);
	let dbWriteLockStatus = $state<string | null>(null);
	let juxtapositionStatus = $state<string | null>(null);

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

	const backupPath = (entry: DbBackupEntry) => '/api/settings/db-backup/' + entry.kind + '/' + encodeURIComponent(entry.name);
	const backupLabel = (entry: DbBackupEntry) => new Date(entry.at).toLocaleString()
		+ ' (' + (entry.kind === 'auto' ? t().settingsDbBackupKindAuto : t().settingsDbBackupKindManual) + ')';

	function deleteDbBackup(entry: DbBackupEntry): void {
		deps.requestConfirmation({
			message: t().settingsDbBackupDeleteConfirm(backupLabel(entry)), runLabel: t().settingsDbBackupDelete, destructive: true,
			run: () => void (async () => {
				dbBackupStatus = null;
				try {
					const response = await deps.apiFetch(backupPath(entry), { method: 'DELETE' });
					if (!response.ok) {
						const body = await response.json().catch(() => ({})) as { detail?: unknown };
						throw new Error(deps.describeApiError(body.detail, response.status));
					}
					const next = await response.json() as SettingsStatus['db_backup'];
					if (settingsStatus) settingsStatus = { ...settingsStatus, db_backup: next };
					dbBackupStatus = t().settingsDbBackupDeleted;
				} catch (error) {
					dbBackupStatus = error instanceof Error ? error.message : String(error);
				}
			})()
		});
	}

	// A restore replaces every saved record, so it asks twice: what it does, then
	// whether to do it. Every screen then reads the restored contents afresh.
	function restoreDbBackup(entry: DbBackupEntry): void {
		const restore = async () => {
			dbBackupStatus = t().settingsDbBackupRestoring;
			try {
				const response = await deps.apiFetch(backupPath(entry) + '/restore', { method: 'POST' });
				if (!response.ok) {
					const body = await response.json().catch(() => ({})) as { detail?: unknown };
					throw new Error(deps.describeApiError(body.detail, response.status));
				}
				const result = await response.json() as { safety_backup: string };
				dbBackupStatus = null;
				deps.requestConfirmation({
					message: t().settingsDbBackupRestoreDone(result.safety_backup), runLabel: t().settingsDbBackupReload,
					run: () => (deps.reloadPage ?? (() => window.location.reload()))()
				});
			} catch (error) {
				dbBackupStatus = error instanceof Error ? error.message : String(error);
			}
		};
		deps.requestConfirmation({
			message: t().settingsDbBackupRestoreConfirm(backupLabel(entry)), runLabel: t().settingsDbBackupRestoreNext, destructive: true,
			run: () => deps.requestConfirmation({
				message: t().settingsDbBackupRestoreFinalConfirm(backupLabel(entry)), runLabel: t().settingsDbBackupRestore, destructive: true,
				run: () => void restore()
			})
		});
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

	async function updateDescriptionMeterSettings(switches: MeterSwitches): Promise<void> {
		descriptionMeterStatus = null;
		try {
			const response = await deps.apiFetch('/api/settings/description-meter', {
				method: 'PUT',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify(switches)
			});
			if (!response.ok) {
				const body = await response.json().catch(() => ({})) as { detail?: unknown };
				throw new Error(deps.describeApiError(body.detail, response.status));
			}
			const next = await response.json() as MeterSwitches;
			if (settingsStatus) settingsStatus = { ...settingsStatus, description_meter: next };
			// This tab's meter follows at once; other tabs read it when they load.
			applyMeterSwitches(next);
			descriptionMeterStatus = t().settingsDescriptionMeterSaved;
		} catch (error) {
			descriptionMeterStatus = error instanceof Error ? error.message : String(error);
			console.warn('failed to update description meter settings', error);
		}
	}

	async function updateImageUploadNotice(enabled: boolean): Promise<void> {
		imageUploadNoticeStatus = null;
		try {
			const response = await deps.apiFetch('/api/settings/image-upload-notice', {
				method: 'PUT',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ enabled })
			});
			if (!response.ok) {
				const body = await response.json().catch(() => ({})) as { detail?: unknown };
				throw new Error(deps.describeApiError(body.detail, response.status));
			}
			const next = await response.json() as { enabled: boolean };
			if (settingsStatus) settingsStatus = { ...settingsStatus, image_upload_notice: next };
			// This tab follows at once; other tabs read it when they load.
			applyImageUploadNotice(next);
			imageUploadNoticeStatus = t().settingsImageUploadNoticeSaved;
		} catch (error) {
			imageUploadNoticeStatus = error instanceof Error ? error.message : String(error);
			console.warn('failed to update the picture upload warning switch', error);
		}
	}

	// The switch itself is never refused by the lock, so a locked server can always be unlocked here.
	async function updateDbWriteLock(locked: boolean): Promise<void> {
		dbWriteLockStatus = null;
		try {
			const response = await deps.apiFetch('/api/settings/db-write-lock', {
				method: 'PUT',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ locked })
			});
			if (!response.ok) {
				const body = await response.json().catch(() => ({})) as { detail?: unknown };
				throw new Error(deps.describeApiError(body.detail, response.status));
			}
			const next = await response.json() as SettingsStatus['db_write_lock'];
			if (settingsStatus) settingsStatus = { ...settingsStatus, db_write_lock: next };
			dbWriteLockStatus = next.locked ? t().settingsDbWriteLockOn : t().settingsDbWriteLockOff;
		} catch (error) {
			dbWriteLockStatus = error instanceof Error ? error.message : String(error);
			console.warn('failed to update the database write lock', error);
		}
	}

	async function updateJuxtapositionSettings(candidateLimit: number): Promise<void> {
		juxtapositionStatus = null;
		try {
			const response = await deps.apiFetch('/api/settings/juxtaposition', {
				method: 'PUT',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ candidate_limit: candidateLimit })
			});
			if (!response.ok) {
				const body = await response.json().catch(() => ({})) as { detail?: unknown };
				throw new Error(deps.describeApiError(body.detail, response.status));
			}
			const next = await response.json() as SettingsStatus['juxtaposition'];
			if (settingsStatus) settingsStatus = { ...settingsStatus, juxtaposition: next };
			juxtapositionStatus = t().settingsJuxtapositionSaved;
		} catch (error) {
			juxtapositionStatus = error instanceof Error ? error.message : String(error);
			console.warn('failed to update juxtaposition settings', error);
		}
	}

	// A null patch restores defaults. The response is authoritative after server normalization.
	async function updateRenderLimits(
		patch: Record<string, number> | null
	): Promise<SettingsStatus['render_limits'] | null> {
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
			return next;
		} catch (error) {
			renderLimitsStatus = error instanceof Error ? error.message : String(error);
			console.warn('failed to update render limits', error);
			return null;
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
		get status() { return settingsStatus; },
		get statusError() { return settingsStatusError; },
		get statusLoading() { return settingsStatusLoading; },
		get dbBackupStatus() { return dbBackupStatus; },
		get outputSaveStatus() { return outputSaveStatus; },
		get logRetentionStatus() { return logRetentionStatus; },
		get renderLimitsStatus() { return renderLimitsStatus; },
		get pluginActionStatus() { return pluginActionStatus; },
		get renderConcurrencyStatus() { return renderConcurrencyStatus; },
		get descriptionMeterStatus() { return descriptionMeterStatus; },
		get imageUploadNoticeStatus() { return imageUploadNoticeStatus; },
		get dbWriteLockStatus() { return dbWriteLockStatus; },
		get juxtapositionStatus() { return juxtapositionStatus; },
		loadStatus: loadSettingsStatus,
		resetForLoggedOut,
		deletePlugin,
		setPluginEnabled,
		updateDbBackupSettings,
		runDbBackupNow,
		deleteDbBackup,
		restoreDbBackup,
		updateOutputSaveSettings,
		updateRenderConcurrencySettings,
		updateDescriptionMeterSettings,
		updateImageUploadNotice,
		updateDbWriteLock,
		updateJuxtapositionSettings,
		updateLogRetentionSettings,
		updateRenderLimits
	};
}
