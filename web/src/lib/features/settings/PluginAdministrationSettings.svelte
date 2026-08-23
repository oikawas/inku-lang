<script lang="ts">
	import { t } from '$lib/i18n/index.svelte';
	import type { PluginItem, SettingsStatus } from './server-administration.svelte';
	import './plugin-administration-settings.css';

	type Props = {
		pluginsStatus: SettingsStatus['plugins'] | null;
		settingsStatusError: string | null;
		settingsStatusLoading: boolean;
		pluginActionStatus: string | null;
		isAdmin: boolean;
		canvasAspectEnabled: boolean;
		onLoadSettingsStatus: () => void;
		onLoadPluginContent: (id: string) => Promise<string | null>;
		onSavePlugin: (id: string, content: string) => Promise<string[] | null>;
		onCreatePlugin: (content: string, filename: string) => Promise<string[] | null>;
		onDeletePlugin: (id: string) => Promise<boolean>;
		onSetPluginEnabled: (id: string, enabled: boolean) => Promise<boolean>;
		onSetCanvasAspectEnabled: (enabled: boolean) => void | Promise<void>;
	};

	let {
		pluginsStatus, settingsStatusError, settingsStatusLoading, pluginActionStatus,
		isAdmin, canvasAspectEnabled, onLoadSettingsStatus, onLoadPluginContent,
		onSavePlugin, onCreatePlugin, onDeletePlugin, onSetPluginEnabled,
		onSetCanvasAspectEnabled
	}: Props = $props();

	let pluginFileInput = $state<HTMLInputElement | null>(null);
	let pluginBusy = $state(false);
	let pluginDeleteConfirmId = $state<string | null>(null);
	let pluginSectionReasons = $state<string[]>([]);
	let pluginEditorOpen = $state(false);
	let pluginEditorId = $state<string | null>(null);
	let pluginEditorTitle = $state('');
	let pluginEditorContent = $state('');
	let pluginEditorLoading = $state(false);
	let pluginEditorSaving = $state(false);
	let pluginEditorReasons = $state<string[]>([]);

	function pluginId(plugin: PluginItem): string {
		return plugin.id ?? plugin.path ?? `${plugin.namespace ?? ''}.${plugin.name}`;
	}
	function pluginIsEnabled(plugin: PluginItem): boolean {
		return plugin.enabled ?? plugin.status === 'enabled';
	}

	async function togglePluginEnabled(plugin: PluginItem): Promise<void> {
		if (!isAdmin || pluginBusy) return;
		pluginBusy = true;
		await onSetPluginEnabled(pluginId(plugin), !pluginIsEnabled(plugin));
		pluginBusy = false;
	}

	async function confirmDeletePlugin(plugin: PluginItem): Promise<void> {
		if (!isAdmin || pluginBusy) return;
		pluginBusy = true;
		await onDeletePlugin(pluginId(plugin));
		pluginDeleteConfirmId = null;
		pluginBusy = false;
	}

	function triggerPluginFile(): void {
		pluginSectionReasons = [];
		pluginFileInput?.click();
	}

	async function onPluginFileChange(event: Event): Promise<void> {
		const input = event.currentTarget as HTMLInputElement;
		const file = input.files?.[0];
		input.value = '';
		if (!file) return;
		pluginBusy = true;
		const content = await file.text();
		const reasons = await onCreatePlugin(content, file.name);
		pluginBusy = false;
		pluginSectionReasons = reasons ?? [];
	}

	async function openPluginEditor(plugin: PluginItem): Promise<void> {
		pluginEditorId = pluginId(plugin);
		pluginEditorTitle = plugin.namespace ? `${plugin.namespace}.${plugin.name}` : plugin.name;
		pluginEditorReasons = [];
		pluginEditorContent = '';
		pluginEditorOpen = true;
		pluginEditorLoading = true;
		const content = await onLoadPluginContent(pluginEditorId);
		pluginEditorLoading = false;
		if (content === null) { pluginEditorOpen = false; pluginEditorId = null; return; }
		pluginEditorContent = content;
	}

	function closePluginEditor(): void {
		if (pluginEditorSaving) return;
		pluginEditorOpen = false;
		pluginEditorId = null;
	}

	async function savePluginEditor(): Promise<void> {
		if (!pluginEditorId || pluginEditorSaving) return;
		pluginEditorSaving = true;
		const reasons = await onSavePlugin(pluginEditorId, pluginEditorContent);
		pluginEditorSaving = false;
		if (reasons === null) { pluginEditorOpen = false; pluginEditorId = null; pluginEditorReasons = []; }
		else pluginEditorReasons = reasons;
	}


</script>

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
				<div class="popover-group-label user-plugin-head">
					<span>{t().settingsUserPlugins}</span>
					<button class="ghost-btn" onclick={triggerPluginFile} disabled={!isAdmin || pluginBusy}>{t().settingsPluginLoadFile}</button>
					<input type="file" accept=".md" bind:this={pluginFileInput} onchange={onPluginFileChange} style="display:none" />
				</div>
				{#if pluginActionStatus}<div class="db-test-result">{pluginActionStatus}</div>{/if}
				{#if pluginSectionReasons.length}<div class="db-test-result">{t().settingsPluginInvalid}: {pluginSectionReasons.join(" / ")}</div>{/if}
			{#if pluginsStatus?.loaded.filter((plugin) => plugin.namespace !== "system").length}
				{#each pluginsStatus.loaded.filter((plugin) => plugin.namespace !== "system") as plugin (plugin.id ?? plugin.path ?? `${plugin.namespace}.${plugin.name}`)}
						<div class="user-plugin-row">
							<div class="user-plugin-info">
								<div class="system-plugin-title-row">
									<div class="system-plugin-title">{plugin.namespace ? `${plugin.namespace}.${plugin.name}` : plugin.name}</div>
									<span class="plugin-version-pill">{plugin.version ? `v${plugin.version}` : plugin.status}</span>
									{#if plugin.status === "rejected"}<span class="plugin-rejected">{plugin.status}</span>{/if}
								</div>
								<div class="system-plugin-desc">{plugin.path ?? ""}</div>
								{#if plugin.reasons?.length}<div class="db-test-result">{plugin.reasons.join(" / ")}</div>{/if}
							</div>
							<div class="user-plugin-controls">
								<button class="ghost-btn user-plugin-btn" onclick={() => void openPluginEditor(plugin)} disabled={!isAdmin || pluginBusy}>{t().settingsPluginViewEdit}</button>
								{#if pluginDeleteConfirmId === pluginId(plugin)}
									<button class="ghost-btn user-plugin-btn danger" onclick={() => void confirmDeletePlugin(plugin)} disabled={pluginBusy}>{t().settingsPluginDeleteConfirm}</button>
									<button class="ghost-btn user-plugin-btn" onclick={() => (pluginDeleteConfirmId = null)} disabled={pluginBusy}>{t().confirmCancel}</button>
								{:else}
									<button class="ghost-btn user-plugin-btn danger" onclick={() => (pluginDeleteConfirmId = pluginId(plugin))} disabled={!isAdmin || pluginBusy}>{t().settingsPluginDelete}</button>
								{/if}
								{#if plugin.status !== "rejected"}
									<button
										type="button"
										class="plugin-switch"
										class:plugin-enabled={pluginIsEnabled(plugin)}
										role="switch"
										aria-checked={pluginIsEnabled(plugin)}
										disabled={!isAdmin || pluginBusy}
										onclick={() => void togglePluginEnabled(plugin)}
									>
										<span class="switch-track"><span class="switch-knob"></span></span>
										<span class="switch-label">{pluginIsEnabled(plugin) ? t().settingsPluginEnabled : t().settingsPluginDisabled}</span>
									</button>
								{/if}
							</div>
						</div>
					{/each}
				{:else}
					<div class="inline-message">{t().settingsPluginsEmpty}</div>
				{/if}
			</div>
			<div class="settings-inline-actions">
				<button class="ghost-btn" onclick={onLoadSettingsStatus} disabled={settingsStatusLoading || !isAdmin}>{t().settingsReload}</button>
			</div>
{#if pluginEditorOpen}
	<div class="modal-backdrop" onclick={closePluginEditor} aria-hidden="true"></div>
	<div class="plugin-editor-dialog" role="dialog" aria-modal="true" tabindex="-1" onclick={(e) => e.stopPropagation()} onkeydown={(e) => { if (e.key === 'Escape') closePluginEditor(); }}>
		<div class="modal-head">
			<div class="catalog-modal-title">{t().settingsPluginEditorTitle} — {pluginEditorTitle}</div>
			<button class="catalog-close" onclick={closePluginEditor} disabled={pluginEditorSaving}>×</button>
		</div>
		<div class="plugin-editor-body">
			{#if pluginEditorLoading}
				<div class="inline-message">{t().settingsLoading}</div>
			{:else}
				<textarea class="plugin-editor-ta" bind:value={pluginEditorContent} spellcheck="false" disabled={pluginEditorSaving}></textarea>
			{/if}
			{#if pluginEditorReasons.length}<div class="db-test-result">{t().settingsPluginInvalid}: {pluginEditorReasons.join(" / ")}</div>{/if}
		</div>
		<div class="plugin-editor-foot">
			<button class="ghost-btn" onclick={closePluginEditor} disabled={pluginEditorSaving}>{t().confirmCancel}</button>
			<button class="ghost-btn primary" onclick={savePluginEditor} disabled={pluginEditorSaving || pluginEditorLoading || !isAdmin}>{pluginEditorSaving ? t().settingsLoading : t().settingsPluginSave}</button>
		</div>
	</div>
{/if}
