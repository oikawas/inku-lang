<script lang="ts">
	import { t } from '$lib/i18n/index.svelte';
	import type { ExportTemplate } from '$lib/exportTemplates';
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
	type SettingsTab = 'connection' | 'db' | 'plugins' | 'users' | 'export' | 'misc';

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
		dbBackupStatus: string | null;
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
		pngAlphaWhite: boolean;
		exportTemplates: ExportTemplate[];
		exportTemplateStatus: string | null;
		saveReplayAsNewVersion: boolean;
		canvasAspectEnabled: boolean;
		onClose: () => void;
		onCloseSettings: () => void;
		onSelectSettingsTab: (tab: SettingsTab) => void;
		onSetStage1Provider: (provider: Provider) => void;
		onSetStage1Model: (model: string) => void;
		onSetStage2Provider: (provider: Provider) => void;
		onSetStage2Model: (model: string) => void;
		onLoadSettingsStatus: () => void;
		onUpdateDbBackupSettings: (intervalDays: number, maxGenerations: number) => void | Promise<void>;
		onRunDbBackupNow: () => void | Promise<void>;
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
		includeThinking = $bindable(),
		settingsStatus,
		settingsStatusError,
		settingsStatusLoading,
		dbBackupStatus,
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
		pngAlphaWhite = $bindable(),
		exportTemplates,
		exportTemplateStatus,
		saveReplayAsNewVersion = $bindable(),
		canvasAspectEnabled,
		onClose,
		onCloseSettings,
		onSelectSettingsTab,
		onSetStage1Provider,
		onSetStage1Model,
		onSetStage2Provider,
		onSetStage2Model,
		onLoadSettingsStatus,
		onUpdateDbBackupSettings,
		onRunDbBackupNow,
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

	const USER_ROLE_OPTIONS: UserRole[] = ['admin', 'group_lead', 'user'];
	const isAdmin = $derived(currentUser?.role === 'admin');

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
	{#if settingsMode === 'settings'}
		<div class="settings-tabs">
			<button class:active={settingsTab === 'plugins'} onclick={() => onSelectSettingsTab('plugins')}>{t().settingsTabPlugins}</button>
			{#if isAdmin}
				<button class:active={settingsTab === 'users'} onclick={() => onSelectSettingsTab('users')}>{t().settingsTabUsers}</button>
				<button class:active={settingsTab === 'db'} onclick={() => onSelectSettingsTab('db')}>{t().settingsTabDb}</button>
			{/if}
			<button class:active={settingsTab === 'export'} onclick={() => onSelectSettingsTab('export')}>{t().settingsTabExport}</button>
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
				<div class="popover-group-label">{t().settingsUserPlugins}</div>
				<div class="user-plugin-skeleton">
					<div>
						<div class="system-plugin-title">{t().settingsUserPluginsAddTitle}</div>
						<div class="system-plugin-desc">{t().settingsUserPluginsAddDescription}</div>
					</div>
					<div class="plugin-add">
						<input placeholder={t().settingsUserPluginPathPlaceholder} disabled />
						<button class="ghost-btn" disabled>{t().addButton}</button>
					</div>
				</div>
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
		position: fixed;
		top: 6vh;
		left: 50%;
		transform: translateX(-50%);
		z-index: 401;
		background: var(--panel2); border-radius: var(--r-lg);
		box-shadow: 0 12px 48px rgba(0,0,0,0.18);
		display: flex; flex-direction: column; overflow: hidden;
		width: min(860px, calc(100vw - 32px)); max-height: 88vh;
		height: min(760px, 88vh);
	}
	.settings-modal.model-modal {
		width: min(calc(35ch + 190px), calc(100vw - 32px));
		height: auto;
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
		background: var(--panel);
	}
	.popover-group-label {
		font-size: 10px; color: var(--fg3); text-transform: uppercase; letter-spacing: 0.08em;
		font-weight: 500; margin-bottom: 7px;
	}
	.form-row {
		display: flex; align-items: center; gap: 8px; margin-bottom: 7px;
	}
	.form-row label { width: 90px; color: var(--fg2); font-size: 12px; flex-shrink: 0; }
	.form-row select, .plugin-add input, .login-grid input, .group-edit-input {
		flex: 1; min-width: 0; padding: 5px 7px;
		border: 1px solid var(--border2); border-radius: var(--r);
		background: var(--panel); color: var(--fg); font-size: 12px; font-family: inherit;
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
	.db-backup-grid input {
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
	.user-plugin-skeleton {
		display: grid;
		grid-template-columns: minmax(0, 1fr);
		gap: 10px;
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
		padding: 4px 10px;
		border: 1px solid var(--border2);
		border-radius: var(--r);
		background: var(--panel);
		color: var(--fg2);
		font-size: 11px;
		cursor: pointer;
		font-family: inherit;
	}
	.ghost-btn:hover { background: var(--bg2); }
	.ghost-btn:disabled { opacity: 0.4; cursor: not-allowed; }
</style>
