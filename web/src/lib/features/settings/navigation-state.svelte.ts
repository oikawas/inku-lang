import {
	canAccessSettingsTab as canAccessSettingsTabFor,
	defaultSettingsTab as defaultSettingsTabFor
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

export type SettingsActor = {
	permission_groups?: import('$lib/permissionGroups').PermissionGroup[];
	settings_tab?: string | null;
	group_id?: string | null;
};

type NavigationDeps<TActor extends SettingsActor> = {
	apiFetch: ApiFetch;
	currentUser: () => TActor | null;
	setCurrentUser: (actor: TActor) => void;
	loadTab: (tab: SettingsTab) => void;
	loadAvailableModels: () => void | Promise<void>;
	cancelModelSelection: () => void;
	describeApiError: (detail: unknown, status: number) => string;
};

export type SettingsNavigation = {
	readonly opened: boolean;
	readonly mode: SettingsMode;
	readonly tab: SettingsTab;
	readonly detail: SettingsDetailLevel;
	restoreDetail: () => void;
	setDetail: (detail: SettingsDetailLevel) => void;
	openSettings: (tab?: SettingsTab | null) => void;
	openModelSelection: () => void;
	finishModelSelection: () => void;
	close: () => void;
	selectTab: (tab: SettingsTab) => void;
};

function isSettingsContentTab(tab: string | null | undefined): tab is Exclude<SettingsTab, 'connection'> {
	return tab === 'models' || tab === 'db' || tab === 'plugins' || tab === 'users' || tab === 'unread' || tab === 'export' || tab === 'misc' || tab === 'server_misc' || tab === 'logs' || tab === 'limits';
}

export function createSettingsNavigation<TActor extends SettingsActor>(
	deps: NavigationDeps<TActor>
): SettingsNavigation {
	let settingsOpen = $state(false);
	let settingsMode = $state<SettingsMode>('settings');
	let settingsTab = $state<SettingsTab>('connection');
	let settingsDetail = $state<SettingsDetailLevel>('standard');
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
		deps.loadTab(tab);
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
		deps.loadTab(nextTab);
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

	return {
		get opened() { return settingsOpen; },
		get mode() { return settingsMode; },
		get tab() { return settingsTab; },
		get detail() { return settingsDetail; },
		restoreDetail,
		setDetail: setSettingsDetail,
		openSettings,
		openModelSelection,
		finishModelSelection,
		close,
		selectTab: selectSettingsTab
	};
}
