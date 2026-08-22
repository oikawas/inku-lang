<script lang="ts">
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

	function onSetEditUser(user: SettingsUserItem): void {
		selectedUserId = user.id;
		editUserName = user.username;
		editUserEmail = user.email;
		editUserPassword = '';
		editUserPermissionGroups = [...user.permission_groups];
		editUserGroupId = user.group_id ?? '';
	}

	function onClearEditUser(): void {
		selectedUserId = null;
		editUserName = '';
		editUserEmail = '';
		editUserPassword = '';
		editUserPermissionGroups = ['users'];
		editUserGroupId = '';
	}

	$effect(() => {
		const nextGroups = groups;
		if (nextGroups === groupListDefaulted) return;
		groupListDefaulted = nextGroups;
		if (!newUserGroupId && nextGroups[0]) newUserGroupId = nextGroups[0].id;
	});

	// An authoritative reload refreshes the selected draft or clears a selection
	// whose user was removed; ordinary typing does not retrigger this reconciliation.
	$effect(() => {
		const availableUsers = users;
		if (!selectedUserId) return;
		const selected = availableUsers.find((user) => user.id === selectedUserId);
		if (selected) onSetEditUser(selected);
		else onClearEditUser();
	});

	async function onAddUser(): Promise<void> {
		const input: CreateSettingsUserInput = {
			username: newUserName,
			email: newUserEmail,
			password: newUserPassword,
			permission_groups: newUserPermissionGroups,
			group_id: newUserGroupId || null
		};
		if (!await administration.addUser(input)) return;
		newUserName = '';
		newUserEmail = '';
		newUserPassword = '';
		newUserPermissionGroups = ['users'];
	}

	async function onSaveUserEdit(): Promise<void> {
		if (!selectedUserId) return;
		const input: UpdateSettingsUserInput = {
			username: editUserName,
			email: editUserEmail,
			permission_groups: editUserPermissionGroups,
			group_id: editUserGroupId || null
		};
		if (editUserPassword) input.password = editUserPassword;
		if (await administration.updateUser(selectedUserId, input)) editUserPassword = '';
	}

	async function onRemoveUser(id: string): Promise<void> {
		if (await administration.removeUser(id) && selectedUserId === id) onClearEditUser();
	}

	async function onAddGroup(): Promise<void> {
		if (await administration.addGroup(newGroupName)) newGroupName = '';
	}

	async function onRemoveGroup(group: SettingsUserGroup): Promise<void> {
		await administration.removeGroup(group);
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
		if (!editGroupId) return;
		if (await administration.updateGroup(editGroupId, editGroupName)) onClearEditGroup();
	}
</script>

<div class="user-administration-settings">
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
				<span>{currentUser.username} / {currentUser.permission_groups.map(permissionGroupLabel).join(' + ')}{currentUser.group_name ? ` / ${currentUser.group_name}` : ''}</span>
				{#if !singleUserMode}
					<button class="ghost-btn" onclick={onLogout}>{t().logoutButton}</button>
				{/if}
			</div>
			{#if singleUserMode}
				<div class="db-test-result">{t().singleUserPasswordNote}</div>
			{/if}
			{#if userSettingsLoading}
				<div class="inline-message">{t().settingsLoading}</div>
			{/if}
		{/if}
	</div>
	{#if currentUser}
		{#if isAdmin}
			<div class="popover-group">
				<div class="user-management-head">
					<div>
						<div class="popover-group-label">{t().settingsUsersLabel}</div>
						<div class="user-management-count">{t().userCountLabel(users.length)}</div>
					</div>
					<button class="ghost-btn" onclick={() => void administration.load()} disabled={userSettingsLoading || !isAdmin}>{t().settingsReload}</button>
				</div>
				<div class="user-management-layout">
					<div class="user-list-panel">
						<div class="user-list-head">
							<span>{t().userNamePlaceholder}</span>
							<span>{t().userEmailPlaceholder}</span>
							<span>{t().permissionGroupLabel}</span>
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
										<span class="user-cell">{user.permission_groups.map(permissionGroupLabel).join(' + ')}</span>
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
							<div class="user-form-field">
								<span>{t().permissionGroupSelectLabel}</span>
								<div class="permission-group-choices">
									{#each PERMISSION_GROUP_OPTIONS as name (name)}
										<label class="permission-group-choice">
											<input
												type="checkbox"
												checked={newUserPermissionGroups.includes(name)}
												onchange={() => (newUserPermissionGroups = togglePermissionGroup(newUserPermissionGroups, name))}
											/>
											<span>{permissionGroupLabel(name)}</span>
										</label>
									{/each}
								</div>
							</div>
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
								<div class="user-form-field">
									<span>{t().permissionGroupSelectLabel}</span>
									<div class="permission-group-choices">
										{#each PERMISSION_GROUP_OPTIONS as name (name)}
											<label class="permission-group-choice">
												<input
													type="checkbox"
													checked={editUserPermissionGroups.includes(name)}
													onchange={() => (editUserPermissionGroups = togglePermissionGroup(editUserPermissionGroups, name))}
												/>
												<span>{permissionGroupLabel(name)}</span>
											</label>
										{/each}
									</div>
								</div>
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
	{#if isAdmin}
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
	.plugin-add { display: flex; gap: 8px; align-items: center; }
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
</style>
