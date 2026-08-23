import { holdsPermissionGroup, type PermissionGroup } from '$lib/permissionGroups';
import { t } from '$lib/i18n/index.svelte';
import {
	normalizeUiCustom,
	normalizeUiMode,
	resolveUiVisibility,
	UI_VISIBILITY_KEYS,
	type UiCustomVisibility,
	type UiMode,
	type UiVisibilityKey
} from '$lib/uiMode';
import {
	normalizeHistoryStripFields,
	type HistoryStripField
} from '$lib/historyStripFields';
import type { Provider } from '$lib/models';
import type { SettingsTab } from '$lib/features/settings/state.svelte';
import { downloadFolderSettings } from '$lib/features/export/download-folder.svelte';

export type UserModelSettings = {
	stage1_provider: Provider;
	stage1_model: string;
	stage2_provider: Provider;
	stage2_model: string;
	vision_provider: Provider;
	vision_model: string;
	okugaki_provider?: Provider;
	okugaki_model?: string;
	instruction_caption_visible?: boolean;
	color_catalog_id?: string;
	sketch_open?: boolean;
	ddl_expanded_open?: boolean;
};

export type UserItem = {
	id: string;
	username: string;
	email: string;
	permission_groups: PermissionGroup[];
	permission_group_labels: string[];
	group_id: string | null;
	group_name: string | null;
	ui_theme?: 'light' | 'dark';
	ui_mode?: UiMode;
	ui_custom?: UiCustomVisibility;
	history_strip_fields?: HistoryStripField[];
	tooltips_enabled?: boolean;
	download_folder_enabled?: boolean;
	download_folder_name?: string | null;
	settings_tab?: SettingsTab;
	model_settings?: UserModelSettings;
	image_generation_count: number;
	at: number;
};

type ApiFetch = (path: string, init?: RequestInit) => Promise<Response>;

type SessionStateDeps = {
	apiFetch: ApiFetch;
	describeApiError: (detail: unknown, status: number) => string;
	applyModelSettings: (actor: UserItem | null) => void;
	afterAuthenticated: (source: 'resume' | 'login') => Promise<void>;
	afterSignedOut: () => void;
	refreshUserAdministration: () => Promise<void>;
	onVisibilityChanged: (visibility: ReturnType<typeof resolveUiVisibility>) => void;
};

export class SessionState {
	private currentUserSettingsRequestId = 0;
	private deps: SessionStateDeps;

	authToken = $state<string | null>(null);
	currentUser = $state<UserItem | null>(null);
	darkMode = $state(true);
	uiModeSaving = $state(false);
	uiModeSaveError = $state(false);
	historyStripFieldsSaving = $state(false);
	historyStripFieldsSaveError = $state(false);
	loginUserName = $state('admin');
	loginPassword = $state('');
	loginPasswordVisible = $state(false);
	loginStatus = $state<string | null>(null);
	profileOpen = $state(false);
	profileEmail = $state('');
	profileCurrentPassword = $state('');
	profileNewPassword = $state('');
	profileStatus = $state<string | null>(null);
	profileSaving = $state(false);

	constructor(deps: SessionStateDeps) {
		this.deps = deps;
	}

	get isAdmin(): boolean {
		return holdsPermissionGroup(this.currentUser, 'admins');
	}

	get tooltipsEnabled(): boolean {
		return this.currentUser?.tooltips_enabled !== false;
	}

	get historyStripFields(): HistoryStripField[] {
		return normalizeHistoryStripFields(this.currentUser?.history_strip_fields);
	}

	get uiMode(): UiMode {
		return normalizeUiMode(this.currentUser?.ui_mode);
	}

	get uiCustom(): UiCustomVisibility {
		return normalizeUiCustom(this.currentUser?.ui_custom);
	}

	get uiVisibility(): ReturnType<typeof resolveUiVisibility> {
		return resolveUiVisibility(this.uiMode, this.uiCustom);
	}

	setCurrentUser(actor: UserItem | null): void {
		this.currentUser = actor;
	}

	updateGenerationCount(count: number): void {
		if (this.currentUser) this.currentUser = { ...this.currentUser, image_generation_count: count };
	}

	private applyDownloadFolderSettings(actor: UserItem | null): void {
		downloadFolderSettings.applyUser(actor);
		void downloadFolderSettings.refresh();
	}

	private applyUserTheme(actor: UserItem | null): void {
		// No stored preference follows the release default instead of light mode.
		this.darkMode = (actor?.ui_theme ?? 'dark') === 'dark';
	}

	private applyActorPreferences(actor: UserItem | null): void {
		this.applyUserTheme(actor);
		this.applyDownloadFolderSettings(actor);
		this.deps.applyModelSettings(actor);
	}

	private clearActor(): void {
		this.authToken = null;
		this.currentUser = null;
		this.uiModeSaveError = false;
		this.applyActorPreferences(null);
		this.loginStatus = null;
		this.deps.afterSignedOut();
	}

	async refreshCurrentUserSettings(): Promise<boolean> {
		const requestId = ++this.currentUserSettingsRequestId;
		try {
			const response = await this.deps.apiFetch('/api/auth/me', { cache: 'no-store' });
			if (!response.ok) throw new Error(t().loginRequiredMessage);
			const actor = await response.json() as UserItem;
			if (requestId !== this.currentUserSettingsRequestId) return false;
			this.currentUser = actor;
			this.applyActorPreferences(actor);
			this.authToken = 'cookie';
			return true;
		} catch {
			return false;
		}
	}

	async loadCurrentUser(): Promise<void> {
		try {
			const response = await this.deps.apiFetch('/api/auth/me');
			if (!response.ok) throw new Error('session expired');
			this.currentUser = await response.json() as UserItem;
			this.applyActorPreferences(this.currentUser);
			this.authToken = 'cookie';
			this.loginStatus = null;
			await this.deps.afterAuthenticated('resume');
		} catch {
			this.clearActor();
		}
	}

	async login(): Promise<void> {
		this.loginStatus = null;
		try {
			const response = await fetch('/api/auth/login', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				credentials: 'same-origin',
				body: JSON.stringify({ username: this.loginUserName, password: this.loginPassword })
			});
			if (!response.ok) {
				const data = await response.json().catch(() => ({})) as { detail?: unknown };
				throw new Error(this.deps.describeApiError(data.detail, response.status));
			}
			const data = await response.json() as { user: UserItem };
			this.authToken = 'cookie';
			this.currentUser = data.user;
			this.applyActorPreferences(data.user);
			this.loginPassword = '';
			await this.deps.afterAuthenticated('login');
		} catch (cause) {
			this.loginStatus = cause instanceof Error ? cause.message : String(cause);
		}
	}

	async logout(): Promise<void> {
		if (this.currentUser || this.authToken) {
			try { await this.deps.apiFetch('/api/auth/logout', { method: 'POST' }); } catch {}
		}
		this.profileOpen = false;
		this.clearActor();
	}

	openProfile(): void {
		if (!this.currentUser) return;
		this.profileEmail = this.currentUser.email;
		this.profileCurrentPassword = '';
		this.profileNewPassword = '';
		this.profileStatus = null;
		this.profileOpen = true;
	}

	closeProfile(): void {
		if (this.profileSaving) return;
		this.profileOpen = false;
		this.profileCurrentPassword = '';
		this.profileNewPassword = '';
	}

	async saveProfile(): Promise<void> {
		if (!this.currentUser) return;
		const email = this.profileEmail.trim();
		if (!email) {
			this.profileStatus = t().userValidationUpdate;
			return;
		}
		if (this.profileNewPassword && this.profileNewPassword.length < 8) {
			this.profileStatus = t().userPasswordTooShort;
			return;
		}
		if (this.profileNewPassword && !this.profileCurrentPassword) {
			this.profileStatus = t().profileCurrentPasswordRequired;
			return;
		}
		this.profileSaving = true;
		this.profileStatus = null;
		try {
			const body: { email: string; password?: string; current_password?: string } = { email };
			if (this.profileNewPassword) {
				body.password = this.profileNewPassword;
				body.current_password = this.profileCurrentPassword;
			}
			const response = await this.deps.apiFetch('/api/auth/me/profile', {
				method: 'PATCH',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify(body)
			});
			if (!response.ok) {
				const data = await response.json().catch(() => ({})) as { detail?: unknown };
				throw new Error(this.deps.describeApiError(data.detail, response.status));
			}
			this.currentUser = await response.json() as UserItem;
			this.applyActorPreferences(this.currentUser);
			this.profileEmail = this.currentUser.email;
			this.profileCurrentPassword = '';
			this.profileNewPassword = '';
			this.profileStatus = t().profileSavedMessage;
			await this.deps.refreshUserAdministration();
		} catch (cause) {
			this.profileStatus = cause instanceof Error ? cause.message : String(cause);
		} finally {
			this.profileSaving = false;
		}
	}

	async updateDownloadFolder(update: { enabled?: boolean; name?: string | null }): Promise<void> {
		if (!this.currentUser) return;
		const previous = this.currentUser;
		const body: Record<string, unknown> = {};
		if (update.enabled !== undefined) body.download_folder_enabled = update.enabled;
		if (update.name !== undefined) body.download_folder_name = update.name ?? '';
		this.currentUser = {
			...this.currentUser,
			...(update.enabled !== undefined ? { download_folder_enabled: update.enabled } : {}),
			...(update.name !== undefined ? { download_folder_name: update.name } : {})
		};
		downloadFolderSettings.applyUser(this.currentUser);
		try {
			const response = await this.deps.apiFetch('/api/auth/me/settings', {
				method: 'PATCH',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify(body)
			});
			if (!response.ok) {
				const data = await response.json().catch(() => ({})) as { detail?: unknown };
				throw new Error(this.deps.describeApiError(data.detail, response.status));
			}
			this.currentUser = await response.json() as UserItem;
			downloadFolderSettings.applyUser(this.currentUser);
		} catch (cause) {
			this.currentUser = previous;
			downloadFolderSettings.applyUser(previous);
			console.warn('failed to update the download folder setting', cause);
		}
	}

	async chooseDownloadFolder(): Promise<void> {
		const name = await downloadFolderSettings.choose();
		if (name !== null) await this.updateDownloadFolder({ enabled: true, name });
	}

	async clearDownloadFolder(): Promise<void> {
		await downloadFolderSettings.clear();
		await this.updateDownloadFolder({ enabled: false, name: null });
	}

	async updateUiTheme(nextDarkMode: boolean): Promise<void> {
		if (!this.currentUser) return;
		const previousDarkMode = this.darkMode;
		const previous = this.currentUser;
		this.darkMode = nextDarkMode;
		try {
			const response = await this.deps.apiFetch('/api/auth/me/settings', {
				method: 'PATCH',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ ui_theme: nextDarkMode ? 'dark' : 'light' })
			});
			if (!response.ok) {
				const data = await response.json().catch(() => ({})) as { detail?: unknown };
				throw new Error(this.deps.describeApiError(data.detail, response.status));
			}
			this.currentUser = await response.json() as UserItem;
			this.applyUserTheme(this.currentUser);
			this.applyDownloadFolderSettings(this.currentUser);
		} catch (cause) {
			this.currentUser = previous;
			this.darkMode = previousDarkMode;
			console.warn('failed to update UI theme', cause);
		}
	}

	async updateUiMode(nextMode: UiMode, nextCustom: UiCustomVisibility = this.uiCustom): Promise<void> {
		if (!this.currentUser || this.uiModeSaving) return;
		const previous = this.currentUser;
		const normalizedCustom = nextMode === 'simple' ? {} : normalizeUiCustom(nextCustom);
		this.uiModeSaving = true;
		this.uiModeSaveError = false;
		this.currentUser = { ...this.currentUser, ui_mode: nextMode, ui_custom: normalizedCustom };
		this.deps.onVisibilityChanged(resolveUiVisibility(nextMode, normalizedCustom));
		try {
			const response = await this.deps.apiFetch('/api/auth/me/settings', {
				method: 'PATCH',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ ui_mode: nextMode, ui_custom: normalizedCustom })
			});
			if (!response.ok) {
				const data = await response.json().catch(() => ({})) as { detail?: unknown };
				throw new Error(this.deps.describeApiError(data.detail, response.status));
			}
			const actor = await response.json() as UserItem;
			const savedCustom = normalizeUiCustom(actor.ui_custom);
			const customMatches = UI_VISIBILITY_KEYS.every((key) => savedCustom[key] === normalizedCustom[key]);
			if (actor.ui_mode !== nextMode || !customMatches) throw new Error('UI mode settings were not persisted by the server');
			this.currentUser = actor;
		} catch (cause) {
			this.currentUser = previous;
			this.uiModeSaveError = true;
			console.warn('failed to update UI mode', cause);
		} finally {
			this.uiModeSaving = false;
		}
	}

	updateUiCustomItem(key: UiVisibilityKey, visible: boolean): void {
		void this.updateUiMode('custom', { ...this.uiCustom, [key]: visible });
	}

	async updateHistoryStripFields(next: HistoryStripField[]): Promise<void> {
		if (!this.currentUser || this.historyStripFieldsSaving) return;
		const previous = this.currentUser;
		this.historyStripFieldsSaving = true;
		this.historyStripFieldsSaveError = false;
		this.currentUser = { ...this.currentUser, history_strip_fields: next };
		try {
			const response = await this.deps.apiFetch('/api/auth/me/settings', {
				method: 'PATCH',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ history_strip_fields: next })
			});
			if (!response.ok) {
				const data = await response.json().catch(() => ({})) as { detail?: unknown };
				throw new Error(this.deps.describeApiError(data.detail, response.status));
			}
			const actor = await response.json() as UserItem;
			const saved = normalizeHistoryStripFields(actor.history_strip_fields);
			if (saved.length !== next.length || saved.some((field, index) => field !== next[index])) {
				throw new Error('history strip fields were not persisted by the server');
			}
			this.currentUser = actor;
		} catch (cause) {
			this.currentUser = previous;
			this.historyStripFieldsSaveError = true;
			console.warn('failed to update history strip fields', cause);
		} finally {
			this.historyStripFieldsSaving = false;
		}
	}

	async updateTooltipsEnabled(enabled: boolean): Promise<void> {
		if (!this.currentUser) return;
		const previous = this.currentUser;
		this.currentUser = { ...this.currentUser, tooltips_enabled: enabled };
		try {
			const response = await this.deps.apiFetch('/api/auth/me/settings', {
				method: 'PATCH',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ tooltips_enabled: enabled })
			});
			if (!response.ok) {
				const data = await response.json().catch(() => ({})) as { detail?: unknown };
				throw new Error(this.deps.describeApiError(data.detail, response.status));
			}
			const actor = await response.json() as UserItem;
			if (actor.tooltips_enabled !== enabled) throw new Error('Tooltip settings were not persisted by the server');
			this.currentUser = actor;
		} catch (cause) {
			this.currentUser = previous;
			console.warn('failed to update tooltip settings', cause);
		}
	}
}

export function createSessionState(deps: SessionStateDeps): SessionState {
	return new SessionState(deps);
}
