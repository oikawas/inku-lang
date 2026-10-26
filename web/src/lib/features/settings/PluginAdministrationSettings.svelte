<script lang="ts">
	import { t } from '$lib/i18n/index.svelte';
	import type { PluginItem, PluginPackageReport, SettingsStatus } from './server-administration.svelte';
	import PluginPackageInstaller from './PluginPackageInstaller.svelte';
	import './plugin-administration-settings.css';

	// The drawing uses only definitions written in JSON. An administrator adds
	// them here as one package file, which is checked before it is installed
	// (2026-10-26, replacing I-703's developer-only packages); the bundled
	// package's document switches it on and off. A legacy document without
	// definitions is shown as not drawn from and may only be deleted.
	type Props = {
		pluginsStatus: SettingsStatus['plugins'] | null;
		settingsStatusError: string | null;
		settingsStatusLoading: boolean;
		pluginActionStatus: string | null;
		isAdmin: boolean;
		onLoadSettingsStatus: () => void;
		onDeletePlugin: (id: string) => Promise<boolean>;
		onSetPluginEnabled: (id: string, enabled: boolean) => Promise<boolean>;
		onCheckPluginPackage: (document: string) => Promise<PluginPackageReport | null>;
		onInstallPluginPackage: (document: string, replace: boolean) => Promise<PluginPackageReport | true | null>;
		onSetPluginWordPicture: (id: string, heading: string, pngBase64: string | null) => Promise<boolean>;
	};

	let {
		pluginsStatus, settingsStatusError, settingsStatusLoading, pluginActionStatus,
		isAdmin, onLoadSettingsStatus, onDeletePlugin, onSetPluginEnabled,
		onCheckPluginPackage, onInstallPluginPackage, onSetPluginWordPicture,
	}: Props = $props();

	let pluginBusy = $state(false);
	let pluginDeleteConfirmId = $state<string | null>(null);
	const isJapanese = $derived(t().code === 'ja');
	const vocabularyPlugins = $derived((pluginsStatus?.loaded ?? []).filter((plugin) => plugin.namespace !== 'system'));

	function pluginId(plugin: PluginItem): string {
		return plugin.id ?? plugin.path ?? `${plugin.namespace ?? ''}.${plugin.name}`;
	}
	function pluginIsEnabled(plugin: PluginItem): boolean {
		return plugin.enabled ?? plugin.status === 'enabled';
	}
	function previewSrc(qualifiedName: string, version = ''): string {
		const query = new URLSearchParams({ name: qualifiedName, scale: '1' });
		if (version) query.set('v', version);
		return `/api/saijiki/plugin-preview?${query}`;
	}
	function pluginIsDeletable(plugin: PluginItem): boolean {
		return plugin.deletable ?? !plugin.has_definitions;
	}

	let pictureTarget = $state<{ id: string; heading: string } | null>(null);
	let pictureInput = $state<HTMLInputElement | null>(null);

	function choosePicture(plugin: PluginItem, qualifiedName: string): void {
		const heading = qualifiedName.slice((plugin.namespace ?? '').length + 1);
		pictureTarget = { id: pluginId(plugin), heading };
		pictureInput?.click();
	}

	async function replacePicture(event: Event): Promise<void> {
		const input = event.currentTarget as HTMLInputElement;
		const file = input.files?.[0];
		input.value = '';
		if (!file || !pictureTarget || pluginBusy) return;
		pluginBusy = true;
		const bytes = new Uint8Array(await file.arrayBuffer());
		let binary = '';
		for (let i = 0; i < bytes.length; i += 0x8000) binary += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
		await onSetPluginWordPicture(pictureTarget.id, pictureTarget.heading, btoa(binary));
		pictureTarget = null;
		pluginBusy = false;
	}

	async function resetPicture(plugin: PluginItem, qualifiedName: string): Promise<void> {
		if (!isAdmin || pluginBusy) return;
		pluginBusy = true;
		await onSetPluginWordPicture(pluginId(plugin), qualifiedName.slice((plugin.namespace ?? '').length + 1), null);
		pluginBusy = false;
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
</script>

			<div class="popover-group">
				<div class="popover-group-label user-plugin-head">
					<span>{t().settingsUserPlugins}</span>
				</div>
				<PluginPackageInstaller {isAdmin} onCheck={onCheckPluginPackage} onInstall={onInstallPluginPackage} />
				<input bind:this={pictureInput} class="plugin-installer-file" type="file" accept="image/png" onchange={replacePicture} />
				{#if pluginActionStatus}<div class="db-test-result">{pluginActionStatus}</div>{/if}
				{#if vocabularyPlugins.length}
					{#each vocabularyPlugins as plugin (pluginId(plugin))}
						<div class="user-plugin-row">
							<div class="user-plugin-info">
								<div class="system-plugin-title-row">
									<div class="system-plugin-title">{plugin.namespace ? `${plugin.namespace}.${plugin.name}` : plugin.name}</div>
									<span class="plugin-version-pill">{plugin.version ? `v${plugin.version}` : plugin.status}</span>
									{#if plugin.status === "rejected"}<span class="plugin-rejected">{plugin.status}</span>{/if}
									<span class="plugin-use-mark" class:not-drawn={!plugin.has_definitions}>{plugin.has_definitions ? t().settingsPluginDrawn : t().settingsPluginNotDrawn}</span>
								</div>
								<div class="system-plugin-desc">{plugin.kind === 'package' ? ((isJapanese ? plugin.description_ja : plugin.description_en) || '') : (plugin.path ?? "")}</div>
								<div class="plugin-use-hint">{plugin.kind === 'package' ? t().settingsPluginPackageHint : plugin.has_definitions ? t().settingsPluginDrawnHint : t().settingsPluginNotDrawnHint}</div>
								{#if plugin.reasons?.length}<div class="db-test-result">{plugin.reasons.join(" / ")}</div>{/if}
								{#if plugin.entries?.length}
									<details class="plugin-words">
										<summary>{t().settingsPluginWords}（{plugin.entries.length}）</summary>
										<ul class="plugin-word-list">
											{#each plugin.entries as entry (entry.qualified_name)}
												{@const surfaces = (isJapanese ? entry.surface_ja : entry.surface_en) ?? []}
												{@const note = isJapanese ? entry.note_ja : entry.note_en}
												{@const example = isJapanese ? entry.example_ja : entry.example_en}
												<li class="plugin-word">
													{#if entry.has_preview}<img class="plugin-word-preview" src={previewSrc(entry.qualified_name, entry.preview_version)} alt="" loading="lazy" />{:else}<span class="plugin-word-preview" aria-hidden="true"></span>{/if}
													<div class="plugin-word-text">
														<strong>{entry.qualified_name}</strong>
														{#if entry.aliases?.length}<small>{entry.aliases.join(', ')}</small>{/if}
														{#if plugin.kind !== 'package' && surfaces.length}<span>{surfaces.join(' | ')}</span>{/if}
														{#if note}<span>{note}</span>{/if}
														{#if example}<span>{t().saijikiPreviewExampleLabel}{example}</span>{/if}
														{#if plugin.kind === 'package' && isAdmin}
															<span class="plugin-word-actions">
																<button class="ghost-btn user-plugin-btn" type="button" onclick={() => choosePicture(plugin, entry.qualified_name)} disabled={pluginBusy}>{t().settingsPluginPictureReplace}</button>
																{#if entry.custom_preview}<button class="ghost-btn user-plugin-btn" type="button" onclick={() => void resetPicture(plugin, entry.qualified_name)} disabled={pluginBusy}>{t().settingsPluginPictureReset}</button>{/if}
															</span>
														{/if}
													</div>
												</li>
											{/each}
										</ul>
									</details>
								{/if}
							</div>
							<div class="user-plugin-controls">
								{#if pluginIsDeletable(plugin)}
									{#if pluginDeleteConfirmId === pluginId(plugin)}
										{#if plugin.kind === 'package'}<span class="plugin-use-hint">{t().settingsPluginPackageDeleteHint}</span>{/if}
										<button class="ghost-btn user-plugin-btn danger" onclick={() => void confirmDeletePlugin(plugin)} disabled={pluginBusy}>{t().settingsPluginDeleteConfirm}</button>
										<button class="ghost-btn user-plugin-btn" onclick={() => (pluginDeleteConfirmId = null)} disabled={pluginBusy}>{t().confirmCancel}</button>
									{:else}
										<button class="ghost-btn user-plugin-btn danger" onclick={() => (pluginDeleteConfirmId = pluginId(plugin))} disabled={!isAdmin || pluginBusy}>{t().settingsPluginDelete}</button>
									{/if}
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
			{#if settingsStatusError}<div class="inline-message">{settingsStatusError}</div>{/if}
