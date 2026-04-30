<script lang="ts">
	import { t } from '$lib/i18n/index.svelte';
	import { PROVIDER_GROUPS, modelsForProvider, type Provider } from '$lib/models';

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
			runtime_editable: boolean;
			note: string;
		};
		plugins: {
			enabled: boolean;
			loaded: PluginItem[];
			runtime_editable: boolean;
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
		at: number;
	};
	type SettingsMode = 'model' | 'settings';
	type SettingsTab = 'connection' | 'db' | 'plugins' | 'users' | 'misc';

	type Props = {
		settingsMode: SettingsMode;
		settingsTab: SettingsTab;
		stage1Provider: Provider;
		stage1Model: string;
		stage2Provider: Provider;
		stage2Model: string;
		includeThinking: boolean;
		settingsStatus: SettingsStatus | null;
		settingsStatusError: string | null;
		settingsStatusLoading: boolean;
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
		showBirds: boolean;
		pngAlphaWhite: boolean;
		saveReplayAsNewVersion: boolean;
		onClose: () => void;
		onCloseSettings: () => void;
		onSelectSettingsTab: (tab: SettingsTab) => void;
		onSetStage1Provider: (provider: Provider) => void;
		onSetStage1Model: (model: string) => void;
		onSetStage2Provider: (provider: Provider) => void;
		onSetStage2Model: (model: string) => void;
		onLoadSettingsStatus: () => void;
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
		includeThinking = $bindable(),
		settingsStatus,
		settingsStatusError,
		settingsStatusLoading,
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
		showBirds = $bindable(),
		pngAlphaWhite = $bindable(),
		saveReplayAsNewVersion = $bindable(),
		onClose,
		onCloseSettings,
		onSelectSettingsTab,
		onSetStage1Provider,
		onSetStage1Model,
		onSetStage2Provider,
		onSetStage2Model,
		onLoadSettingsStatus,
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
		onCancelModelSelection,
		onConfirmModelSelection,
	}: Props = $props();

	const USER_ROLE_OPTIONS: { value: UserRole; label: string }[] = [
		{ value: 'admin', label: 'admin' },
		{ value: 'group_lead', label: 'group_lead' },
		{ value: 'user', label: 'user' },
	];

	function userRoleLabel(role: UserRole) {
		if (role === 'admin') return t().userRoleAdmin;
		if (role === 'group_lead') return t().userRoleGroupLead;
		return t().userRoleUser;
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
			<button class:active={settingsTab === 'db'} onclick={() => onSelectSettingsTab('db')}>{t().settingsTabDb}</button>
			<button class:active={settingsTab === 'plugins'} onclick={() => onSelectSettingsTab('plugins')}>{t().settingsTabPlugins}</button>
			<button class:active={settingsTab === 'users'} onclick={() => onSelectSettingsTab('users')}>{t().settingsTabUsers}</button>
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
						{#each PROVIDER_GROUPS as pg (pg.id)}<option value={pg.id}>{pg.label}</option>{/each}
					</select>
				</div>
				<div class="form-row">
					<label for="settings-stage1-model">{t().modelLabel}</label>
					<select id="settings-stage1-model" value={stage1Model} onchange={(e) => onSetStage1Model((e.currentTarget as HTMLSelectElement).value)}>
						{#each modelsForProvider(stage1Provider) as m (m.id)}<option value={m.id}>{m.label}{m.notes ? ` - ${m.notes}` : ''}</option>{/each}
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
						{#each PROVIDER_GROUPS as pg (pg.id)}<option value={pg.id}>{pg.label}</option>{/each}
					</select>
				</div>
				<div class="form-row">
					<label for="settings-stage2-model">{t().modelLabel}</label>
					<select id="settings-stage2-model" value={stage2Model} onchange={(e) => onSetStage2Model((e.currentTarget as HTMLSelectElement).value)}>
						{#each modelsForProvider(stage2Provider) as m (m.id)}<option value={m.id}>{m.label}{m.notes ? ` - ${m.notes}` : ''}</option>{/each}
					</select>
				</div>
			</div>
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
					</div>
					<div class="db-test-result">{settingsStatus.database.note}</div>
				{:else}
					<div class="inline-message">{settingsStatusError ?? t().settingsLoadFailed}</div>
				{/if}
			</div>
			<div class="settings-inline-actions">
				<button class="ghost-btn" onclick={onLoadSettingsStatus} disabled={settingsStatusLoading || currentUser?.role !== 'admin'}>{t().settingsReload}</button>
			</div>
		{:else if settingsTab === 'plugins'}
			<div class="popover-group">
				<div class="popover-group-label">{t().settingsPluginsStatus}</div>
				{#if settingsStatusLoading}
					<div class="inline-message">{t().settingsLoading}</div>
				{:else if settingsStatus}
					<div class="settings-readonly-grid">
						<span>Loader</span><strong>{settingsStatus.plugins.enabled ? t().settingsYes : t().settingsUnavailable}</strong>
						<span>Runtime edit</span><strong>{settingsStatus.plugins.runtime_editable ? t().settingsYes : t().settingsUnavailable}</strong>
					</div>
					{#if settingsStatus.plugins.loaded.length > 0}
						<div class="plugin-list">
							{#each settingsStatus.plugins.loaded as plugin (plugin.name)}
								<div class="plugin-row">
									<span>{plugin.name}</span>
									<span class="plugin-version">{plugin.version}</span>
									<span class="plugin-version">{plugin.status}</span>
								</div>
							{/each}
						</div>
					{:else}
						<div class="inline-message">{t().settingsPluginsEmpty}</div>
					{/if}
					<div class="db-test-result">{settingsStatus.plugins.note}</div>
				{:else}
					<div class="inline-message">{settingsStatusError ?? t().settingsLoadFailed}</div>
				{/if}
			</div>
			<div class="settings-inline-actions">
				<button class="ghost-btn" onclick={onLoadSettingsStatus} disabled={settingsStatusLoading || currentUser?.role !== 'admin'}>{t().settingsReload}</button>
			</div>
		{:else if settingsTab === 'users'}
			<div class="popover-group">
				<div class="popover-group-label">{t().settingsUsersLabel}</div>
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
					<div class="settings-inline-actions">
						<button class="ghost-btn" onclick={onLoadUserSettings} disabled={userSettingsLoading || !['admin', 'group_lead'].includes(currentUser.role)}>{t().settingsReload}</button>
					</div>
					{#if userSettingsLoading}
						<div class="inline-message">{t().settingsLoading}</div>
					{/if}
					{#if currentUser.role === 'admin' || currentUser.role === 'group_lead'}
						<div class="user-editor-grid">
							<div class="user-editor-panel">
								<div class="user-editor-title">{t().userAddTitle}</div>
								<div class="user-form-grid">
									<input bind:value={newUserName} placeholder={t().userNamePlaceholder} />
									<input bind:value={newUserEmail} type="email" placeholder={t().userEmailPlaceholder} />
									<input bind:value={newUserPassword} type="password" placeholder={t().userPasswordPlaceholder} />
									<select bind:value={newUserRole} disabled={currentUser.role === 'group_lead'}>
										{#each USER_ROLE_OPTIONS as role (role.value)}
											<option value={role.value}>{userRoleLabel(role.value)}</option>
										{/each}
									</select>
									<select bind:value={newUserGroupId} disabled={currentUser.role === 'group_lead'}>
										<option value="">{t().userNoGroup}</option>
										{#each groups as group (group.id)}
											<option value={group.id}>{group.name}</option>
										{/each}
									</select>
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
										<select bind:value={editUserRole} disabled={currentUser.role === 'group_lead'}>
											{#each USER_ROLE_OPTIONS as role (role.value)}
												<option value={role.value}>{userRoleLabel(role.value)}</option>
											{/each}
										</select>
										<select bind:value={editUserGroupId} disabled={currentUser.role === 'group_lead'}>
											<option value="">{t().userNoGroup}</option>
											{#each groups as group (group.id)}
												<option value={group.id}>{group.name}</option>
											{/each}
										</select>
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
						<div class="user-list">
							{#each users as user (user.id)}
								<div class="user-row" class:selected={selectedUserId === user.id}>
									<button class="ghost-btn" onclick={() => onSetEditUser(user)}>{t().editButton}</button>
									<span class="user-cell user-name">{user.username}</span>
									<span class="user-cell">{user.email}</span>
									<span class="user-cell">{user.role}</span>
									<span class="user-cell">{user.group_name ?? t().userNoGroup}</span>
									<button class="ghost-btn" onclick={() => onRemoveUser(user.id)}>{t().deleteButton}</button>
								</div>
							{/each}
						</div>
					{:else}
						<div class="inline-message">{t().userManageUnavailable}</div>
					{/if}
				{/if}
			</div>
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
								<span>{group.name}</span>
								<button class="ghost-btn" onclick={() => onRemoveGroup(group)}>{t().deleteButton}</button>
							</div>
						{/each}
					</div>
				</div>
			{/if}
		{:else}
			<div class="popover-group">
				<div class="popover-group-label">{t().settingsDisplayLabel}</div>
				<label class="setting-toggle">
					<input type="checkbox" bind:checked={showBirds} />
					<span>{t().settingsShowBirds}</span>
				</label>
			</div>
			<div class="popover-group">
				<div class="popover-group-label">{t().settingsExportLabel}</div>
				<label class="setting-toggle">
					<input type="checkbox" bind:checked={pngAlphaWhite} />
					<span>{t().settingsPngAlpha}</span>
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
		position: fixed; top: 50%; left: 50%; transform: translate(-50%, -50%);
		z-index: 401;
		background: #faf9f6; border-radius: var(--r-lg);
		box-shadow: 0 12px 48px rgba(0,0,0,0.18);
		display: flex; flex-direction: column; overflow: hidden;
		width: min(860px, calc(100vw - 32px)); max-height: 88vh;
	}
	.settings-modal.model-modal {
		width: min(calc(35ch + 190px), calc(100vw - 32px));
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
		background: #fff;
	}
	.popover-group-label {
		font-size: 10px; color: var(--fg3); text-transform: uppercase; letter-spacing: 0.08em;
		font-weight: 500; margin-bottom: 7px;
	}
	.form-row {
		display: flex; align-items: center; gap: 8px; margin-bottom: 7px;
	}
	.form-row label { width: 90px; color: var(--fg2); font-size: 12px; flex-shrink: 0; }
	.form-row select, .plugin-add input, .login-grid input {
		flex: 1; min-width: 0; padding: 5px 7px;
		border: 1px solid var(--border2); border-radius: var(--r);
		background: #fff; color: var(--fg); font-size: 12px; font-family: inherit;
	}
	.check-row { display: flex; align-items: center; gap: 7px; color: var(--fg2); font-size: 12px; }
	.settings-inline-actions { display: flex; align-items: center; gap: 10px; }
	.db-test-result { color: var(--fg2); font-size: 12px; }
	.settings-readonly-grid {
		display: grid;
		grid-template-columns: 120px minmax(0, 1fr);
		gap: 7px 12px;
		align-items: baseline;
		margin-bottom: 9px;
		font-size: 12px;
	}
	.settings-readonly-grid span { color: var(--fg3); }
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
	.inline-message {
		padding: 7px 9px;
		border: 1px solid var(--border);
		border-radius: var(--r);
		background: #fff;
		color: var(--fg2);
		font-size: 12px;
	}
	.plugin-list {
		border: 1px solid var(--border); border-radius: var(--r);
		background: #fff; overflow: hidden;
	}
	.plugin-row {
		display: grid; grid-template-columns: 1fr auto auto; gap: 10px;
		align-items: center; padding: 9px 10px; border-bottom: 1px solid var(--border);
	}
	.plugin-row:last-child { border-bottom: none; }
	.plugin-version { color: var(--fg3); font-size: 11px; }
	.plugin-add { display: flex; gap: 8px; align-items: center; }
	.login-grid {
		display: grid;
		grid-template-columns: minmax(0, 1fr) minmax(0, 1fr) auto;
		gap: 8px;
		align-items: center;
	}
	.user-session-row {
		display: flex;
		justify-content: space-between;
		align-items: center;
		gap: 10px;
		padding: 7px 9px;
		border: 1px solid var(--border);
		border-radius: var(--r);
		background: #fff;
		color: var(--fg2);
		font-size: 12px;
	}
	.user-editor-grid {
		display: grid;
		grid-template-columns: repeat(2, minmax(0, 1fr));
		gap: 10px;
		margin-top: 10px;
	}
	.user-editor-panel {
		border: 1px solid var(--border);
		border-radius: var(--r);
		background: #fff;
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
		background: #fff; color: var(--fg); font-size: 12px; font-family: inherit;
	}
	.user-form-actions {
		display: flex;
		justify-content: flex-end;
		gap: 8px;
		margin-top: 8px;
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
	.user-row {
		display: grid;
		grid-template-columns: auto minmax(0, 1fr) minmax(0, 1.35fr) 120px 120px auto;
		gap: 8px;
		align-items: center;
		padding: 7px 9px;
		border: 1px solid var(--border);
		border-radius: var(--r);
		background: #fff;
	}
	.user-row.selected { border-color: var(--accent); background: var(--accent-light); }
	.user-cell { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--fg2); font-size: 12px; }
	.user-name { color: var(--fg); font-weight: 500; }
	.group-row {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 8px;
		background: #fff;
		border: 1px solid var(--border);
		border-radius: var(--r);
		padding: 7px 9px;
		font-size: 12px;
		color: var(--fg2);
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
		background: #faf9f6;
		flex-shrink: 0;
	}
	.ghost-btn {
		padding: 4px 10px;
		border: 1px solid var(--border2);
		border-radius: var(--r);
		background: #fff;
		color: var(--fg2);
		font-size: 11px;
		cursor: pointer;
		font-family: inherit;
	}
	.ghost-btn:hover { background: var(--bg2); }
	.ghost-btn:disabled { opacity: 0.4; cursor: not-allowed; }
</style>
