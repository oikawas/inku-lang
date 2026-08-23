import { t } from '$lib/i18n/index.svelte';
import { holdsPermissionGroup, type PermissionGroup } from '$lib/permissionGroups';
import type { ApiFetch } from '$lib/transport/api-fetch';
import type { SettingsActor } from './navigation-state.svelte';

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

type UserAdministrationDeps<TActor extends SettingsActor> = {
	apiFetch: ApiFetch;
	currentUser: () => TActor | null;
	refreshCurrentUserSettings: () => boolean | Promise<boolean>;
	describeApiError: (detail: unknown, status: number) => string;
};

export type SettingsUserAdministration = {
	readonly users: SettingsUserItem[];
	readonly groups: SettingsUserGroup[];
	readonly status: string | null;
	readonly loading: boolean;
	load: () => Promise<void>;
	addUser: (input: CreateSettingsUserInput) => Promise<boolean>;
	updateUser: (id: string, input: UpdateSettingsUserInput) => Promise<boolean>;
	removeUser: (id: string) => Promise<boolean>;
	addGroup: (name: string) => Promise<boolean>;
	removeGroup: (group: SettingsUserGroup) => Promise<boolean>;
	updateGroup: (id: string, name: string) => Promise<boolean>;
};

export type UserAdministrationOwner = SettingsUserAdministration & {
	resetForLoggedOut: () => void;
};

export function createUserAdministration<TActor extends SettingsActor>(
	deps: UserAdministrationDeps<TActor>
): UserAdministrationOwner {
	let users = $state<SettingsUserItem[]>([]);
	let groups = $state<SettingsUserGroup[]>([]);
	let userAdministrationStatus = $state<string | null>(null);
	let userAdministrationLoading = $state(false);
	let userAdministrationRequestId = 0;

	function resetForLoggedOut(): void {
		// Invalidate requests before clearing state so a late administration
		// response cannot repopulate account data after the session has ended.
		++userAdministrationRequestId;
		users = [];
		groups = [];
		userAdministrationStatus = null;
		userAdministrationLoading = false;
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
		get users() { return users; },
		get groups() { return groups; },
		get status() { return userAdministrationStatus; },
		get loading() { return userAdministrationLoading; },
		load: loadUserAdministration,
		addUser,
		updateUser,
		removeUser,
		addGroup,
		removeGroup,
		updateGroup,
		resetForLoggedOut
	};
}
