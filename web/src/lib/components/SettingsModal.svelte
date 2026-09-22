<script lang="ts">
	import { t } from '$lib/i18n/index.svelte';
	import { onMount, tick } from 'svelte';
	import type { Snippet } from 'svelte';
	import UnreadWordsPanel from '$lib/components/UnreadWordsPanel.svelte';
	import DatabaseAdministrationSettings from '$lib/features/settings/DatabaseAdministrationSettings.svelte';
	import RenderLimitsSettings from '$lib/features/settings/RenderLimitsSettings.svelte';
	import ServerRuntimeSettings from '$lib/features/settings/ServerRuntimeSettings.svelte';
	import UserAdministrationSettings from '$lib/features/settings/UserAdministrationSettings.svelte';
	import ModelSelectionSettings from '$lib/features/settings/ModelSelectionSettings.svelte';
	import ModelAdministrationSettings from '$lib/features/settings/ModelAdministrationSettings.svelte';
	import PluginAdministrationSettings from '$lib/features/settings/PluginAdministrationSettings.svelte';
	import ExportSettings from '$lib/features/settings/ExportSettings.svelte';
	import AppearanceSettings from '$lib/features/settings/AppearanceSettings.svelte';
	import '$lib/features/settings/settings-modal.css';
	import type { ExportTemplate } from '$lib/exportTemplates';
	import type { AnimationExportSettings } from '$lib/animationExport';
	import type { CardExportSettings } from '$lib/cardExport';
	import type { Provider, ProviderGroup } from '$lib/models';
	import type { UiCustomVisibility, UiMode, UiVisibilityKey } from '$lib/uiMode';
	import type { HistoryStripField } from '$lib/historyStripFields';
	import { settingsTabShownAtDetail, type SettingsDetailLevel } from '$lib/settingsDetail';
	import type { SettingsController, SettingsTab, SettingsUserItem } from '$lib/features/settings/state.svelte';

	type Props = {
		settings: SettingsController;
		demoContent?: Snippet;
		singleUserMode: boolean;
		stage1Provider: Provider;
		stage1Model: string;
		stage2Provider: Provider;
		stage2Model: string;
		visionProvider: Provider;
		visionModel: string;
		providerGroups: ProviderGroup[];
		visionProviderGroups: ProviderGroup[];
		allowVisionSelection: boolean;
		includeThinking: boolean;
		currentUser: SettingsUserItem | null;
		uiMode: UiMode;
		uiCustom: UiCustomVisibility;
		uiModeSaving: boolean;
		uiModeSaveError: boolean;
		historyStripFields: HistoryStripField[];
		historyStripFieldsSaving: boolean;
		historyStripFieldsSaveError: boolean;
		onToggleHistoryStripField: (field: HistoryStripField) => void;
		onSetUiMode: (mode: UiMode) => void | Promise<void>;
		onSetUiCustomItem: (key: UiVisibilityKey, visible: boolean) => void;
		loginStatus: string | null;
		loginUserName: string;
		loginPassword: string;
		pngAlphaWhite: boolean;
		exportTemplates: ExportTemplate[];
		exportTemplateStatus: string | null;
		animationExportSettings: AnimationExportSettings;
		cardExportSettings: CardExportSettings;
		onChooseDownloadFolder: () => void | Promise<void>;
		onClearDownloadFolder: () => void | Promise<void>;
		onSetStage1Provider: (provider: Provider) => void;
		onSetStage1Model: (model: string) => void;
		onSetStage2Provider: (provider: Provider) => void;
		onSetStage2Model: (model: string) => void;
		onSetVisionProvider: (provider: Provider) => void;
		onSetVisionModel: (model: string) => void;
		onLogin: () => void | Promise<void>;
		onLogout: () => void | Promise<void>;
		onAddExportTemplate: () => boolean | Promise<boolean>;
		onUpdateExportTemplate: (id: string, patch: Partial<ExportTemplate>) => boolean | Promise<boolean>;
		onRemoveExportTemplate: (id: string) => boolean | Promise<boolean>;
		onConfirmModelSelection: () => void;
	};

	let {
		settings,
		demoContent,
		singleUserMode,
		stage1Provider,
		stage1Model,
		stage2Provider,
		stage2Model,
		visionProvider,
		visionModel,
		providerGroups,
		visionProviderGroups,
		allowVisionSelection,
		includeThinking = $bindable(),
		currentUser,
		uiMode,
		uiCustom,
		uiModeSaving,
		uiModeSaveError,
		historyStripFields,
		historyStripFieldsSaving,
		historyStripFieldsSaveError,
		onToggleHistoryStripField,
		onSetUiMode,
		onSetUiCustomItem,
		loginStatus,
		loginUserName = $bindable(),
		loginPassword = $bindable(),
		pngAlphaWhite = $bindable(),
		exportTemplates,
		exportTemplateStatus,
		animationExportSettings = $bindable(),
		cardExportSettings = $bindable(),
		onChooseDownloadFolder,
		onClearDownloadFolder,
		onSetStage1Provider,
		onSetStage1Model,
		onSetStage2Provider,
		onSetStage2Model,
		onSetVisionProvider,
		onSetVisionModel,
		onLogin,
		onLogout,
		onAddExportTemplate,
		onUpdateExportTemplate,
		onRemoveExportTemplate,
		onConfirmModelSelection,
	}: Props = $props();

	const settingsMode = $derived(settings.mode);
	const settingsTab = $derived(settings.tab);
	const settingsDetail = $derived(settings.detail);
	const settingsStatus = $derived(settings.status);
	const settingsStatusError = $derived(settings.statusError);
	const settingsStatusLoading = $derived(settings.statusLoading);
	const dbBackupStatus = $derived(settings.dbBackupStatus);
	const outputSaveStatus = $derived(settings.outputSaveStatus);
	const logRetentionStatus = $derived(settings.logRetentionStatus);
	const renderLimitsStatus = $derived(settings.renderLimitsStatus);
	const renderConcurrencyStatus = $derived(settings.renderConcurrencyStatus);
	const onClose = () => settings.close();
	const onSelectSettingsTab = (tab: SettingsTab) => settings.selectTab(tab);
	const onSetSettingsDetail = (detail: SettingsDetailLevel) => settings.setDetail(detail);
	const onLoadSettingsStatus = () => void settings.loadStatus();
	const onUpdateDbBackupSettings = (intervalDays: number, maxGenerations: number, backupHour: number, backupMinute: number) => settings.updateDbBackupSettings(intervalDays, maxGenerations, backupHour, backupMinute);
	const onRunDbBackupNow = () => settings.runDbBackupNow();
	const onUpdateOutputSaveSettings = (enabled: boolean, outputDir: string, pngSize: number) => settings.updateOutputSaveSettings(enabled, outputDir, pngSize);
	const onUpdateRenderConcurrencySettings = (serverLimit: number, clientLimit: number) => settings.updateRenderConcurrencySettings(serverLimit, clientLimit);
	const onUpdateLogRetentionSettings = (enabled: boolean, retentionDays: number, rotate: string, compress: boolean) => settings.updateLogRetentionSettings(enabled, retentionDays, rotate, compress);
	const onUpdateRenderLimits = (patch: Record<string, number> | null) => settings.updateRenderLimits(patch);
	// The category navigation asks the same question as the navigation guard from the same module.
	const showsTab = (tab: string) => settingsTabShownAtDetail(tab, settingsDetail);
	const detailed = $derived(settingsDetail === 'detailed');
	const isAdmin = $derived(currentUser?.permission_groups?.includes('admins') === true);
	let appearanceSection = $state<'display' | 'making'>('display');
	const settingsPage = $derived.by(() => {
		const strings = t();
		switch (settingsTab) {
			case 'models': return { title: strings.settingsTabModels, hint: strings.settingsModelsHint };
			case 'users': return { title: strings.settingsTabUsers, hint: strings.settingsUsersHint };
			case 'db': return { title: strings.settingsTabDb, hint: strings.settingsDatabaseHint };
			case 'server_misc': return { title: strings.settingsTabServerMisc, hint: strings.settingsServerHint };
			case 'logs': return { title: strings.settingsTabLogs, hint: strings.settingsLogsHint };
			case 'limits': return { title: strings.settingsTabLimits, hint: strings.settingsLimitsHint };
			case 'plugins': return { title: strings.settingsTabPlugins, hint: strings.settingsPluginsHint };
			case 'unread': return { title: strings.settingsTabUnreadWords, hint: strings.settingsUnreadHint };
			case 'export': return { title: strings.settingsTabExport, hint: strings.settingsExportHint };
			case 'demo': return { title: strings.modeDemo, hint: strings.tooltipInputTabDemo };
			default: return appearanceSection === 'making'
				? { title: strings.settingsCategoryMaking, hint: strings.settingsMakingHint }
				: { title: strings.settingsCategoryDisplayOperation, hint: strings.settingsDisplayHint };
		}
	});
	let modalElement = $state<HTMLDivElement | null>(null);
	let restoreFocusTo: HTMLElement | null = null;

	function visibleEnabledControls(): HTMLElement[] {
		if (!modalElement) return [];
		return [...modalElement.querySelectorAll<HTMLElement>('button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), summary, textarea:not([disabled]), [tabindex]:not([tabindex="-1"])')]
			.filter((element) => !element.closest('[inert]') && element.getClientRects().length > 0);
	}

	function trapTab(event: KeyboardEvent): void {
		if (event.key !== 'Tab') return;
		if (event.target instanceof Element && event.target.closest('[data-settings-nested-dialog], [role="dialog"][aria-modal="true"]:not(.settings-modal)')) return;
		const controls = visibleEnabledControls();
		if (controls.length === 0) {
			event.preventDefault();
			modalElement?.focus();
			return;
		}
		const first = controls[0];
		const last = controls[controls.length - 1];
		if (!controls.includes(document.activeElement as HTMLElement)) {
			event.preventDefault();
			(event.shiftKey ? last : first).focus();
		} else if (event.shiftKey && document.activeElement === first) {
			event.preventDefault();
			last.focus();
		} else if (!event.shiftKey && document.activeElement === last) {
			event.preventDefault();
			first.focus();
		}
	}

	onMount(() => {
		const activeElement = document.activeElement;
		restoreFocusTo = activeElement instanceof HTMLElement && activeElement !== document.body ? activeElement : null;
		void tick().then(() => (visibleEnabledControls()[0] ?? modalElement)?.focus());
		return () => {
			if (restoreFocusTo?.isConnected) restoreFocusTo.focus();
		};
	});

	function selectAppearanceSection(section: 'display' | 'making') {
		appearanceSection = section;
		onSelectSettingsTab('misc');
	}
</script>

<div class="settings-feature-root">
<div class="modal-backdrop" onclick={onClose} aria-hidden="true"></div>
<div bind:this={modalElement} class="settings-modal" class:model-modal={settingsMode === 'model'} role="dialog" aria-modal="true" aria-labelledby="settings-dialog-title" tabindex="-1" onclick={(e) => e.stopPropagation()} onkeydown={trapTab}>
	<div class="modal-head">
		<h1 id="settings-dialog-title" class="catalog-modal-title">{settingsMode === 'model' ? t().modelSelectButton : t().settingsTitle}</h1>
		<div class="modal-head-tools">
			<!-- Model mode has its own four tabs and none of them is detail-gated,
			     so the switch would govern nothing there. -->
			{#if settingsMode !== 'model'}
				<button
					type="button"
					class="detail-switch"
					class:detail-on={detailed}
					role="switch"
					aria-checked={detailed}
					aria-label={t().settingsDetailLabel}
					title={t().settingsDetailHint}
					onclick={() => onSetSettingsDetail(detailed ? 'standard' : 'detailed')}
				>
					<span class="switch-label">{detailed ? t().settingsDetailDetailed : t().settingsDetailStandard}</span>
					<span class="switch-track"><span class="switch-knob"></span></span>
				</button>
			{/if}
			<!-- onClose, not a bare `settingsOpen = false`: in model mode the close has to
			     roll back the pending picker selection, the way the backdrop and Esc do. -->
			<button class="catalog-close" onclick={onClose} aria-label={t().closeLabel}>×</button>
		</div>
	</div>

	{#if settingsMode === 'model'}
		<ModelSelectionSettings
			bind:includeThinking {stage1Provider} {stage1Model} {stage2Provider} {stage2Model}
			{visionProvider} {visionModel} {providerGroups} {visionProviderGroups} {allowVisionSelection}
			{onSetStage1Provider} {onSetStage1Model} {onSetStage2Provider} {onSetStage2Model}
			{onSetVisionProvider} {onSetVisionModel} onCancel={settings.close} onConfirm={onConfirmModelSelection}
		/>
	{:else}
		<div class="settings-workspace">
			<nav class="settings-category-nav" aria-label={t().settingsTitle}>
				<section class="settings-category">
					<div class="settings-category-label">{t().settingsCategoryDisplayOperation}</div>
					<button aria-current={settingsTab === 'misc' && appearanceSection === 'display' ? 'page' : undefined} class:active={settingsTab === 'misc' && appearanceSection === 'display'} onclick={() => selectAppearanceSection('display')}>{t().settingsCategoryDisplayOperation}</button>
				</section>
				<section class="settings-category">
					<div class="settings-category-label">{t().settingsCategoryMaking}</div>
					<button aria-current={settingsTab === 'misc' && appearanceSection === 'making' ? 'page' : undefined} class:active={settingsTab === 'misc' && appearanceSection === 'making'} onclick={() => selectAppearanceSection('making')}>{t().settingsBatchRetryLabel}</button>
					<button aria-current={settingsTab === 'demo' ? 'page' : undefined} class:active={settingsTab === 'demo'} onclick={() => onSelectSettingsTab('demo')}>{t().modeDemo}</button>
				</section>
				<section class="settings-category">
					<div class="settings-category-label">{t().settingsTabExport}</div>
					<button aria-current={settingsTab === 'export' ? 'page' : undefined} class:active={settingsTab === 'export'} onclick={() => onSelectSettingsTab('export')}>{t().settingsTabExport}</button>
				</section>
				{#if isAdmin}
					<section class="settings-category">
						<div class="settings-category-label">{t().settingsCategoryAdministration}</div>
						<button aria-current={settingsTab === 'models' ? 'page' : undefined} class:active={settingsTab === 'models'} onclick={() => onSelectSettingsTab('models')}>{t().settingsTabModels}</button>
						<button aria-current={settingsTab === 'users' ? 'page' : undefined} class:active={settingsTab === 'users'} onclick={() => onSelectSettingsTab('users')}>{t().settingsTabUsers}</button>
						<button aria-current={settingsTab === 'db' ? 'page' : undefined} class:active={settingsTab === 'db'} onclick={() => onSelectSettingsTab('db')}>{t().settingsTabDb}</button>
						{#if showsTab('server_misc')}
							<button aria-current={settingsTab === 'server_misc' ? 'page' : undefined} class:active={settingsTab === 'server_misc'} onclick={() => onSelectSettingsTab('server_misc')}>{t().settingsTabServerMisc}</button>
						{/if}
						<button aria-current={settingsTab === 'logs' ? 'page' : undefined} class:active={settingsTab === 'logs'} onclick={() => onSelectSettingsTab('logs')}>{t().settingsTabLogs}</button>
						{#if showsTab('limits')}
							<button aria-current={settingsTab === 'limits' ? 'page' : undefined} class:active={settingsTab === 'limits'} onclick={() => onSelectSettingsTab('limits')}>{t().settingsTabLimits}</button>
						{/if}
					</section>
				{/if}
				{#if showsTab('plugins') || showsTab('unread')}
					<section class="settings-category">
						<div class="settings-category-label">{t().settingsCategoryExtensions}</div>
						{#if showsTab('plugins')}
							<button aria-current={settingsTab === 'plugins' ? 'page' : undefined} class:active={settingsTab === 'plugins'} onclick={() => onSelectSettingsTab('plugins')}>{t().settingsTabPlugins}</button>
						{/if}
						{#if showsTab('unread')}
							<button aria-current={settingsTab === 'unread' ? 'page' : undefined} class:active={settingsTab === 'unread'} onclick={() => onSelectSettingsTab('unread')}>{t().settingsTabUnreadWords}</button>
						{/if}
					</section>
				{/if}
			</nav>

			<section class="settings-content" aria-labelledby="settings-page-title">
				<header class="settings-page-heading">
					<h2 id="settings-page-title">{settingsPage.title}</h2>
					<p>{settingsPage.hint}</p>
				</header>
			<div class:limits-body={settingsTab === 'limits'} class="settings-body">
			{#if settingsTab === 'models'}
				<ModelAdministrationSettings administration={settings.modelAdministration} {providerGroups} />
		{:else if settingsTab === 'db'}
			<DatabaseAdministrationSettings
				status={settingsStatus ? { database: settingsStatus.database, db_backup: settingsStatus.db_backup } : null}
				statusError={settingsStatusError}
				loading={settingsStatusLoading}
				backupStatus={dbBackupStatus}
				{isAdmin}
				onReload={onLoadSettingsStatus}
				onUpdateBackupSettings={onUpdateDbBackupSettings}
				onRunBackupNow={onRunDbBackupNow}
			/>
		{:else if settingsTab === 'server_misc'}
			<ServerRuntimeSettings
				status={settingsStatus ? { output_save: settingsStatus.output_save, render_concurrency: settingsStatus.render_concurrency } : null}
				statusError={settingsStatusError}
				loading={settingsStatusLoading}
				{outputSaveStatus}
				{renderConcurrencyStatus}
				{isAdmin}
				onReload={onLoadSettingsStatus}
				onUpdateOutputSave={onUpdateOutputSaveSettings}
				onUpdateRenderConcurrency={onUpdateRenderConcurrencySettings}
			/>
		{:else if settingsTab === 'logs'}
			<div class="popover-group">
				<div class="popover-group-label">{t().settingsLogRetentionTitle}</div>
				{#if settingsStatusLoading}
					<div class="inline-message">{t().settingsLoading}</div>
				{:else if settingsStatus}
					<label class="setting-toggle">
						<input
							type="checkbox"
							checked={settingsStatus.log_retention.enabled}
							onchange={(e) => onUpdateLogRetentionSettings((e.currentTarget as HTMLInputElement).checked, settingsStatus?.log_retention.retention_days ?? 90, settingsStatus?.log_retention.rotate ?? 'daily', settingsStatus?.log_retention.compress ?? true)}
						/>
						<span>{t().settingsLogRetentionEnabled}</span>
					</label>
					<div class="db-backup-grid">
						<label>
							<span>{t().settingsLogRetentionDays}</span>
							<input
								type="number"
								min="1"
								max="3650"
								value={settingsStatus.log_retention.retention_days}
								onchange={(e) => onUpdateLogRetentionSettings(settingsStatus?.log_retention.enabled ?? true, Number((e.currentTarget as HTMLInputElement).value), settingsStatus?.log_retention.rotate ?? 'daily', settingsStatus?.log_retention.compress ?? true)}
							/>
						</label>
						<label>
							<span>{t().settingsLogRetentionRotate}</span>
							<select
								value={settingsStatus.log_retention.rotate}
								onchange={(e) => onUpdateLogRetentionSettings(settingsStatus?.log_retention.enabled ?? true, settingsStatus?.log_retention.retention_days ?? 90, (e.currentTarget as HTMLSelectElement).value, settingsStatus?.log_retention.compress ?? true)}
							>
								<option value="daily">{t().settingsLogRetentionDaily}</option>
								<option value="weekly">{t().settingsLogRetentionWeekly}</option>
								<option value="monthly">{t().settingsLogRetentionMonthly}</option>
							</select>
						</label>
					</div>
					<label class="setting-toggle">
						<input
							type="checkbox"
							checked={settingsStatus.log_retention.compress}
							onchange={(e) => onUpdateLogRetentionSettings(settingsStatus?.log_retention.enabled ?? true, settingsStatus?.log_retention.retention_days ?? 90, settingsStatus?.log_retention.rotate ?? 'daily', (e.currentTarget as HTMLInputElement).checked)}
						/>
						<span>{t().settingsLogRetentionCompress}</span>
					</label>
					<div class="settings-readonly-grid compact">
						<span>{t().settingsLogRetentionLogDir}</span><code>{settingsStatus.log_retention.log_dir}</code>
						<span>{t().settingsLogRetentionFiles}</span
						><strong>{settingsStatus.log_retention.files.length > 0
							? settingsStatus.log_retention.files.join(', ')
							: t().settingsLogRetentionNoFiles}</strong>
					</div>
					<div class="db-test-result">{t().settingsOutputSaveNoteLabel}: {t().settingsLogRetentionNote}</div>
					{#if logRetentionStatus}
						<div class="inline-message">{logRetentionStatus}</div>
					{/if}
				{:else}
					<div class="inline-message">{settingsStatusError ?? t().settingsLoadFailed}</div>
				{/if}
			</div>
			<div class="settings-inline-actions">
				<button class="ghost-btn" onclick={onLoadSettingsStatus} disabled={settingsStatusLoading || !isAdmin}>{t().settingsReloadSettings}</button>
			</div>
		{:else if settingsTab === 'limits'}
			<RenderLimitsSettings
				status={settingsStatus?.render_limits ?? null}
				statusError={settingsStatusError}
				loading={settingsStatusLoading}
				saveStatus={renderLimitsStatus}
				{isAdmin}
				onReload={onLoadSettingsStatus}
				onUpdate={onUpdateRenderLimits}
			/>

			{:else if settingsTab === 'plugins'}
				<PluginAdministrationSettings
					pluginsStatus={settingsStatus?.plugins ?? null}
					{settingsStatusError} {settingsStatusLoading} pluginActionStatus={settings.pluginActionStatus}
					{isAdmin} onLoadSettingsStatus={settings.loadStatus}
					onLoadPluginContent={settings.loadPluginContent} onSavePlugin={settings.savePlugin}
					onCreatePlugin={settings.createPlugin} onDeletePlugin={settings.deletePlugin}
					onSetPluginEnabled={settings.setPluginEnabled}
				/>
		{:else if settingsTab === 'users'}
			<UserAdministrationSettings
				administration={settings.userAdministration}
				{singleUserMode}
				{currentUser}
				{loginStatus}
				bind:loginUserName
				bind:loginPassword
				{onLogin}
				{onLogout}
			/>
		{:else if settingsTab === 'unread'}
			<UnreadWordsPanel {isAdmin} />

			{:else if settingsTab === 'export'}
				<ExportSettings
					bind:pngAlphaWhite bind:animationExportSettings bind:cardExportSettings
					{exportTemplates} {exportTemplateStatus} {onChooseDownloadFolder} {onClearDownloadFolder}
					{onAddExportTemplate} {onUpdateExportTemplate} {onRemoveExportTemplate}
				/>
			{:else if settingsTab === 'demo'}
				{@render demoContent?.()}
			{:else}
				<AppearanceSettings
					section={appearanceSection}
					{uiMode} {uiCustom} {uiModeSaving} {uiModeSaveError}
					{historyStripFields} {historyStripFieldsSaving} {historyStripFieldsSaveError}
					{onToggleHistoryStripField} {onSetUiMode} {onSetUiCustomItem}
				/>
			{/if}
			</div>
			</section>
		</div>
	{/if}
</div>
</div>
