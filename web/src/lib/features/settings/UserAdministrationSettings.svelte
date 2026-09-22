<script lang="ts">
	import { untrack } from 'svelte';
	import { t } from '$lib/i18n/index.svelte';
	import type { PermissionGroup } from '$lib/permissionGroups';
	import type {
		CreateSettingsUserInput,
		SettingsUserAdministration,
		SettingsUserGroup,
		SettingsUserItem,
		UpdateSettingsUserInput
	} from './state.svelte';

	type Props = {
		administration: SettingsUserAdministration;
		singleUserMode: boolean;
		currentUser: SettingsUserItem | null;
		loginStatus: string | null;
		loginUserName: string;
		loginPassword: string;
		onLogin: () => void | Promise<void>;
		onLogout: () => void | Promise<void>;
	};

	let {
		administration,
		singleUserMode,
		currentUser,
		loginStatus,
		loginUserName = $bindable(),
		loginPassword = $bindable(),
		onLogin,
		onLogout
	}: Props = $props();

	const users = $derived(administration.users);
	const groups = $derived(administration.groups);
	const userSettingsStatus = $derived(loginStatus ?? administration.status);
	const userSettingsLoading = $derived(administration.loading);
	const isAdmin = $derived(currentUser?.permission_groups?.includes('admins') === true);

	// Unsaved account drafts stay with these inputs. Passwords cross into the
	// controller only as transient operation arguments and are never controller state.
	let newUserName = $state('');
	let newUserEmail = $state('');
	let newUserPassword = $state('');
	let newUserPermissionGroups = $state<PermissionGroup[]>(['users']);
	let newUserGroupId = $state('');
	let showAddUser = $state(false);
	let userSearch = $state('');
	let userFilter = $state<'all' | 'admins' | 'leaders' | 'users' | 'ungrouped'>('all');
	let selectedUserId = $state<string | null>(null);
	let editUserName = $state('');
	let editUserEmail = $state('');
	let editUserPassword = $state('');
	let editUserPermissionGroups = $state<PermissionGroup[]>(['users']);
	let editUserGroupId = $state('');
	let newGroupName = $state('');
	let editGroupId = $state<string | null>(null);
	let editGroupName = $state('');
	let groupListDefaulted = $state<SettingsUserGroup[] | null>(null);
	let editUserInitialDraft = $state('');
	let userMutationPending = $state(false);

	const PERMISSION_GROUP_OPTIONS: PermissionGroup[] = ['admins', 'leaders', 'users'];

	function togglePermissionGroup(held: PermissionGroup[], name: PermissionGroup): PermissionGroup[] {
		// Never hand back an empty selection: the server refuses it, and a member
		// who holds nothing would be a member nobody could sign in as.
		const next = held.includes(name) ? held.filter((item) => item !== name) : [...held, name];
		return next.length ? PERMISSION_GROUP_OPTIONS.filter((item) => next.includes(item)) : held;
	}

	function permissionGroupLabel(name: PermissionGroup): string {
		if (name === 'admins') return t().permissionGroupAdmins;
		if (name === 'leaders') return t().permissionGroupLeaders;
		return t().permissionGroupUsers;
	}

	function editUserSignature(): string {
		return JSON.stringify({
			username: editUserName,
			email: editUserEmail,
			password: editUserPassword,
			permissionGroups: editUserPermissionGroups,
			groupId: editUserGroupId,
		});
	}

	function onSetEditUser(user: SettingsUserItem, saved = false): void {
		if (editUserDirty && !saved) return;
		selectedUserId = user.id;
		editUserName = user.username;
		editUserEmail = user.email;
		editUserPassword = '';
		editUserPermissionGroups = [...user.permission_groups];
		editUserGroupId = user.group_id ?? '';
		editUserInitialDraft = editUserSignature();
	}

	function onClearEditUser(): void {
		selectedUserId = null;
		editUserName = '';
		editUserEmail = '';
		editUserPassword = '';
		editUserPermissionGroups = ['users'];
		editUserGroupId = '';
		editUserInitialDraft = '';
	}

	$effect(() => {
		const nextGroups = groups;
		if (nextGroups === groupListDefaulted) return;
		groupListDefaulted = nextGroups;
		if (!newUserGroupId && nextGroups[0]) newUserGroupId = nextGroups[0].id;
	});

	const editUserDirty = $derived(!!selectedUserId && editUserSignature() !== editUserInitialDraft);
	const newUserDirty = $derived(!!(newUserName || newUserEmail || newUserPassword || newUserPermissionGroups.join(',') !== 'users' || newUserGroupId !== (groups[0]?.id ?? '')));
	const administrationDirty = $derived(editUserDirty || (showAddUser && newUserDirty));
	const userBusy = $derived(userSettingsLoading || userMutationPending);
	const selectedUser = $derived(users.find((user) => user.id === selectedUserId) ?? null);
	const filteredUsers = $derived.by(() => {
		const query = userSearch.trim().toLowerCase();
		return users.filter((user) => {
			if (userFilter === 'ungrouped' && user.group_id) return false;
			if (userFilter !== 'all' && userFilter !== 'ungrouped' && !user.permission_groups.includes(userFilter)) return false;
			return !query || `${user.username} ${user.email} ${user.group_name ?? ''} ${user.permission_groups.join(' ')}`.toLowerCase().includes(query);
		});
	});

	// A reload keeps a user's local changes until the user saves or discards them.
	// It still clears an edit target that was removed by another administrator.
	$effect(() => {
		const availableUsers = users;
		if (!selectedUserId) return;
		const selected = availableUsers.find((user) => user.id === selectedUserId);
		// Only a refreshed list or a new target starts synchronization. Draft
		// assignments inside it must not subscribe this effect to their own values.
		untrack(() => {
			if (!selected) onClearEditUser();
			else if (!editUserDirty) onSetEditUser(selected);
		});
	});

	function cancelAddUser(): void {
		showAddUser = false;
		newUserName = '';
		newUserEmail = '';
		newUserPassword = '';
		newUserPermissionGroups = ['users'];
		newUserGroupId = groups[0]?.id ?? '';
	}

	async function onAddUser(): Promise<void> {
		if (userMutationPending) return;
		const input: CreateSettingsUserInput = {
			username: newUserName,
			email: newUserEmail,
			password: newUserPassword,
			permission_groups: newUserPermissionGroups,
			group_id: newUserGroupId || null
		};
		userMutationPending = true;
		try {
			if (!await administration.addUser(input)) return;
			newUserName = '';
			newUserEmail = '';
			newUserPassword = '';
			newUserPermissionGroups = ['users'];
			showAddUser = false;
		} finally {
			userMutationPending = false;
		}
	}

	async function onSaveUserEdit(): Promise<void> {
		if (!selectedUserId || userMutationPending) return;
		const input: UpdateSettingsUserInput = {
			username: editUserName,
			email: editUserEmail,
			permission_groups: editUserPermissionGroups,
			group_id: editUserGroupId || null
		};
		if (editUserPassword) input.password = editUserPassword;
		userMutationPending = true;
		try {
			if (await administration.updateUser(selectedUserId, input)) {
				const saved = users.find((user) => user.id === selectedUserId);
				if (saved) onSetEditUser(saved, true);
			}
		} finally {
			userMutationPending = false;
		}
	}

	async function onRemoveUser(id: string): Promise<void> {
		if (userMutationPending) return;
		userMutationPending = true;
		try {
			if (await administration.removeUser(id) && selectedUserId === id) onClearEditUser();
		} finally {
			userMutationPending = false;
		}
	}

	async function onAddGroup(): Promise<void> {
		if (userMutationPending) return;
		userMutationPending = true;
		try {
			if (await administration.addGroup(newGroupName)) newGroupName = '';
		} finally {
			userMutationPending = false;
		}
	}

	async function onRemoveGroup(group: SettingsUserGroup): Promise<void> {
		if (userMutationPending) return;
		userMutationPending = true;
		try {
			await administration.removeGroup(group);
		} finally {
			userMutationPending = false;
		}
	}

	function onSetEditGroup(group: SettingsUserGroup): void {
		editGroupId = group.id;
		editGroupName = group.name;
	}

	function onClearEditGroup(): void {
		editGroupId = null;
		editGroupName = '';
	}

	async function onSaveGroupEdit(): Promise<void> {
		if (!editGroupId || userMutationPending) return;
		userMutationPending = true;
		try {
			if (await administration.updateGroup(editGroupId, editGroupName)) onClearEditGroup();
		} finally {
			userMutationPending = false;
		}
	}
</script>

<div class="user-administration-settings">
	<div class="popover-group user-account-group">
		<div class="popover-group-label">{t().settingsUserSessionLabel}</div>
		{#if userSettingsStatus && (!currentUser || !isAdmin)}<div class="inline-message">{userSettingsStatus}</div>{/if}
		{#if !currentUser}
			<div class="login-grid">
				<input bind:value={loginUserName} placeholder={t().userNamePlaceholder} />
				<input bind:value={loginPassword} type="password" placeholder={t().userPasswordPlaceholder} onkeydown={(e) => { if (e.key === 'Enter') void onLogin(); }} />
				<button class="ghost-btn" onclick={onLogin}>{t().loginSubmit}</button>
			</div>
			<div class="db-test-result">{t().bootstrapAdminNote}</div>
		{:else}
			<div class="user-session-row"><span>{currentUser.username} / {currentUser.permission_groups.map(permissionGroupLabel).join(' + ')}{currentUser.group_name ? ` / ${currentUser.group_name}` : ''}</span>{#if !singleUserMode}<button class="ghost-btn" onclick={onLogout}>{t().logoutButton}</button>{/if}</div>
			{#if singleUserMode}<div class="db-test-result">{t().singleUserPasswordNote}</div>{/if}
			{#if userSettingsLoading}<div class="inline-message">{t().settingsLoading}</div>{/if}
		{/if}
	</div>
	{#if currentUser && isAdmin}
		<section class="popover-group user-management-group">
			<div class="user-management-head"><div><div class="popover-group-label">{t().settingsUsersLabel}</div><div class="user-management-count">{t().userCountLabel(users.length)}</div></div><div class="user-management-actions"><button class="ghost-btn" onclick={() => (showAddUser = true)} disabled={userBusy || showAddUser}>{t().userAddOpen}</button><button class="ghost-btn" onclick={() => void administration.load()} disabled={userBusy || administrationDirty}>{t().settingsReload}</button></div></div>
			{#if userSettingsStatus}<div class="inline-message user-operation-status" aria-live="polite">{userSettingsStatus}</div>{/if}
			<div class="user-management-layout">
				<section class="user-list-panel" aria-label={t().settingsUsersLabel}>
					<div class="user-list-toolbar"><input type="search" bind:value={userSearch} placeholder={t().userSearchPlaceholder} aria-label={t().userSearchPlaceholder} /><label><span>{t().settingsUsersLabel}</span><select bind:value={userFilter}><option value="all">{t().userFilterAll}</option><option value="admins">{t().permissionGroupAdmins}</option><option value="leaders">{t().permissionGroupLeaders}</option><option value="users">{t().permissionGroupUsers}</option><option value="ungrouped">{t().userFilterNoGroup}</option></select></label></div>
					<div class="user-list">
						{#each filteredUsers as user (user.id)}
							<div class="user-row" class:selected={selectedUserId === user.id}>
						<button class="user-select" aria-pressed={selectedUserId === user.id} onclick={() => onSetEditUser(user)} disabled={userBusy || editUserDirty}>
						<span class="user-cell user-name">{user.username}</span>
						<span class="user-cell">
						<small>{t().userEmailPlaceholder}</small>{user.email}</span>
						<span class="user-cell">
						<small>{t().permissionGroupLabel}</small>{user.permission_groups.map(permissionGroupLabel).join(' + ')}</span>
						<span class="user-cell">
						<small>{t().userGroupLabel}</small>{user.group_name ?? t().userNoGroup}</span>
						<span class="user-cell user-count-cell">
						<small>{t().userGenerationCountLabel}</small>{user.image_generation_count.toLocaleString()}</span>
						</button>
						<button class="ghost-btn" onclick={() => onRemoveUser(user.id)} disabled={userBusy}>{t().deleteButton}</button>
						</div>
						{:else}<div class="inline-message">{t().userNoSearchResults}</div>
						{/each}
					</div>
				</section>
				<div class="user-editor-column">
					{#if showAddUser}
						<section class="user-editor-panel">
						<div class="user-editor-title">{t().userAddTitle}</div>
						<fieldset class="user-form-grid" disabled={userBusy}>
						<label class="user-form-field">
						<span>{t().userNamePlaceholder}</span>
						<input bind:value={newUserName} />
						</label>
						<label class="user-form-field">
						<span>{t().userEmailPlaceholder}</span>
						<input bind:value={newUserEmail} type="email" />
						</label>
						<label class="user-form-field">
						<span>{t().userPasswordPlaceholder}</span>
						<input bind:value={newUserPassword} type="password" autocomplete="new-password" />
						</label>
						<div class="user-form-field">
						<span>{t().permissionGroupSelectLabel}</span>
						<small>{t().userPermissionGroupsHint}</small>
						<div class="permission-group-choices">
						{#each PERMISSION_GROUP_OPTIONS as name (name)}<label class="permission-group-choice">
						<input type="checkbox" checked={newUserPermissionGroups.includes(name)} onchange={() => (newUserPermissionGroups = togglePermissionGroup(newUserPermissionGroups, name))} />
						<span>{permissionGroupLabel(name)}</span>
						</label>{/each}</div>
						</div>
						<label class="user-form-field">
						<span>{t().userGroupSelectLabel}</span>
						<small>{t().userGroupMembershipHint}</small>
						<select bind:value={newUserGroupId}>
						<option value="">{t().userNoGroup}</option>
						{#each groups as group (group.id)}<option value={group.id}>{group.name}</option>{/each}</select>
						</label>
						</fieldset>
						<div class="user-form-actions">
						<button class="ghost-btn" onclick={cancelAddUser} disabled={userBusy}>{t().confirmCancel}</button>
						<button class="ghost-btn primary-inline" onclick={onAddUser} disabled={userBusy || !newUserName.trim() || !newUserEmail.trim() || newUserPassword.length < 8}>{t().userAddButton}</button>
						</div>
						</section>
					{/if}
					<section class="user-editor-panel" aria-live="polite">
						<div class="user-editor-title">{t().userEditTitle}</div>
						{#if selectedUser}<div class="selected-user-summary">
						<strong>{selectedUser.username}</strong>
						<span>{selectedUser.email}</span>
						{#if editUserDirty}<em>{t().userDraftChanges}</em>{/if}</div>
						<fieldset class="user-form-grid" disabled={userBusy}>
						<label class="user-form-field">
						<span>{t().userNamePlaceholder}</span>
						<input bind:value={editUserName} />
						</label>
						<label class="user-form-field">
						<span>{t().userEmailPlaceholder}</span>
						<input bind:value={editUserEmail} type="email" />
						</label>
						<label class="user-form-field">
						<span>{t().userNewPasswordPlaceholder}</span>
						<input bind:value={editUserPassword} type="password" autocomplete="new-password" />
						</label>
						<div class="user-form-field">
						<span>{t().permissionGroupSelectLabel}</span>
						<small>{t().userPermissionGroupsHint}</small>
						<div class="permission-group-choices">
						{#each PERMISSION_GROUP_OPTIONS as name (name)}<label class="permission-group-choice">
						<input type="checkbox" checked={editUserPermissionGroups.includes(name)} onchange={() => (editUserPermissionGroups = togglePermissionGroup(editUserPermissionGroups, name))} />
						<span>{permissionGroupLabel(name)}</span>
						</label>{/each}</div>
						</div>
						<label class="user-form-field">
						<span>{t().userGroupSelectLabel}</span>
						<small>{t().userGroupMembershipHint}</small>
						<select bind:value={editUserGroupId}>
						<option value="">{t().userNoGroup}</option>
						{#each groups as group (group.id)}<option value={group.id}>{group.name}</option>{/each}</select>
						</label>
						</fieldset>
						<div class="user-form-actions">
						<button class="ghost-btn" onclick={onClearEditUser} disabled={userBusy}>{t().userClearSelection}</button>
						<button class="ghost-btn primary-inline" onclick={onSaveUserEdit} disabled={userBusy || !editUserDirty || !editUserName.trim() || !editUserEmail.trim() || (!!editUserPassword && editUserPassword.length < 8)}>{t().userSaveChanges}</button>
						</div>{:else}<div class="inline-message">{t().userSelectPrompt}</div>{/if}</section>
				</div>
			</div>
			<details class="group-administration">
						<summary>{t().userGroupLabel}</summary>
						<div class="plugin-add">
						<input bind:value={newGroupName} placeholder={t().groupNamePlaceholder} />
						<button class="ghost-btn" onclick={onAddGroup} disabled={userBusy || !newGroupName.trim()}>{t().addButton}</button>
						</div>
						<div class="group-list">
						{#each groups as group (group.id)}<div class="group-row">
						{#if editGroupId === group.id}<input class="group-edit-input" bind:value={editGroupName} placeholder={t().groupNamePlaceholder} onkeydown={(e) => { if (e.key === 'Enter') void onSaveGroupEdit(); }} />
						<div class="group-row-actions">
						<button class="ghost-btn" onclick={onClearEditGroup} disabled={userBusy}>{t().confirmCancel}</button>
						<button class="ghost-btn primary-inline" onclick={onSaveGroupEdit} disabled={userBusy || !editGroupName.trim()}>{t().userSaveChanges}</button>
						</div>{:else}<span>{group.name}</span>
						<div class="group-row-actions">
						<button class="ghost-btn" onclick={() => onSetEditGroup(group)} disabled={userBusy}>{t().editButton}</button>
						<button class="ghost-btn" onclick={() => onRemoveGroup(group)} disabled={userBusy}>{t().deleteButton}</button>
						</div>{/if}</div>{/each}</div>
						</details>
		</section>
	{:else if currentUser}
		<div class="popover-group"><div class="popover-group-label">{t().settingsUsersLabel}</div><div class="inline-message">{t().userManageUnavailable}</div></div>
	{/if}
</div>

<style>
	.user-administration-settings {
		display: flex;
		flex-direction: column;
		gap: 10px;
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
	.db-test-result { color: var(--fg2); font-size: 12px; }
	.inline-message {
		padding: 7px 9px;
		border: 1px solid var(--border);
		border-radius: var(--r);
		background: var(--panel);
		color: var(--fg2);
		font-size: 12px;
	}
	.plugin-add { display: flex; gap: 8px; align-items: center; max-width: 520px; }
	.plugin-add input, .login-grid input, .group-edit-input {
		flex: 1; min-width: 0; padding: 5px 7px;
		border: 1px solid var(--border2); border-radius: var(--r);
		background: var(--panel); color: var(--fg); font-size: 12px; font-family: inherit;
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
	.user-session-row > span { min-width: 0; overflow-wrap: anywhere; }
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
	.user-management-actions { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 8px; }
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
	}
	.user-list-toolbar { display: grid; grid-template-columns: minmax(0, 1fr) minmax(100px, .6fr); gap: 8px; }
	.user-list-toolbar input, .user-list-toolbar select { min-width: 0; min-height: 34px; box-sizing: border-box; padding: 7px 9px; border: 1px solid var(--border2); border-radius: var(--r); background: var(--panel); color: var(--fg); font: inherit; font-size: 13px; }
	.user-list-toolbar label { display: grid; gap: 3px; color: var(--fg3); font-size: 12px; }
	.user-editor-column { display: grid; align-content: start; gap: 10px; min-width: 0; }
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
		margin: 0;
		padding: 0;
		border: 0;
		min-width: 0;
		display: grid;
		grid-template-columns: minmax(0, 1fr);
		gap: 10px;
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
		font-size: 12px;
		font-weight: 500;
	}
	.user-form-field select {
		width: 100%;
		text-transform: none;
		letter-spacing: 0;
	}
	.permission-group-choices {
		display: flex;
		flex-wrap: wrap;
		gap: 4px 12px;
	}
	.permission-group-choice {
		display: flex;
		align-items: center;
		gap: 4px;
		text-transform: none;
		letter-spacing: 0;
		white-space: nowrap;
	}
	.user-form-actions {
		display: flex;
		justify-content: flex-end;
		gap: 8px;
		margin-top: 8px;
	}
	.user-management-layout .user-editor-panel { grid-column: auto; }
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
	.user-row {
		display: grid;
		grid-template-columns: minmax(0, 1fr) auto;
		gap: 8px;
		align-items: center;
		padding: 7px 9px;
		border: 1px solid var(--border);
		border-radius: var(--r);
		background: var(--panel);
	}
	.user-row.selected { border-color: var(--accent); background: var(--accent-light); }
	.user-select {
		display: grid;
		grid-template-columns: repeat(2, minmax(0, 1fr));
		gap: 7px 14px;
		align-items: start;
		min-width: 0;
		padding: 0;
		border: none;
		background: none;
		color: inherit;
		font-family: inherit;
		text-align: left;
		cursor: pointer;
	}
	.user-row > .ghost-btn { align-self: start; min-height: 34px; justify-content: center; }
	.user-cell { display: grid; gap: 2px; min-width: 0; overflow-wrap: anywhere; color: var(--fg2); font-size: 13px; line-height: 1.35; }
	.user-cell small { color: var(--fg3); font-size: 11px; }
	.user-name { grid-column: 1 / -1; color: var(--fg); font-weight: 500; }
	.user-count-cell { font-variant-numeric: tabular-nums; }
	.selected-user-summary { display: grid; gap: 3px; margin-bottom: 10px; padding: 9px; border: 1px solid var(--border); border-radius: var(--r); background: var(--bg); }
	.selected-user-summary strong { overflow-wrap: anywhere; font-size: 14px; }
	.selected-user-summary span { overflow-wrap: anywhere; color: var(--fg2); font-size: 13px; }
	.selected-user-summary em { color: var(--accent); font-size: 12px; font-style: normal; font-weight: 600; }
	.user-form-field small { color: var(--fg3); font-size: 11px; font-weight: 400; line-height: 1.4; }
	.group-administration { margin-top: 12px; border-top: 1px solid var(--border); padding-top: 10px; }
	.group-administration summary { color: var(--fg2); font-size: 13px; font-weight: 600; cursor: pointer; }
	.group-administration .plugin-add { margin-top: 10px; }
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
	.group-row > span { min-width: 0; overflow-wrap: anywhere; }
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
	@media (max-width: 820px) {
		.user-management-layout { grid-template-columns: 1fr; }
		.user-management-layout .user-editor-panel { grid-column: auto; }
		.user-select { grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); }
	}
	@media (max-width: 560px) {
		.login-grid, .user-form-grid { grid-template-columns: 1fr; }
		.user-session-row, .user-management-head, .group-row { align-items: flex-start; flex-direction: column; }
		.user-management-actions, .user-management-head .ghost-btn, .group-row-actions { width: 100%; }
		.user-management-actions { justify-content: flex-start; }
		.group-row-actions { justify-content: flex-start; }
		.plugin-add { align-items: stretch; flex-direction: column; }
		.plugin-add .ghost-btn { width: 100%; justify-content: center; }
		.user-list-toolbar, .user-select { grid-template-columns: 1fr; }
		.user-row { grid-template-columns: 1fr; }
		.user-row > .ghost-btn { justify-self: stretch; }
	}
</style>
