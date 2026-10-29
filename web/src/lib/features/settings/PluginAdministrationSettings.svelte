<script lang="ts">
	import { t } from '$lib/i18n/index.svelte';
	import type { PluginItem, PluginPackageReport, PluginPackageUpload, SettingsStatus } from './server-administration.svelte';
	import PluginPackageInstaller from './PluginPackageInstaller.svelte';
	import { fileToBase64, saveBlob } from './plugin-files';
	import './plugin-administration-settings.css';

	// The drawing uses only definitions written in JSON. An administrator adds
	// them here as one package file (or a zip with its pictures), which is
	// checked before it is installed, and exports an installed one as a zip
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
		onCheckPluginPackage: (upload: PluginPackageUpload) => Promise<PluginPackageReport | null>;
		onInstallPluginPackage: (upload: PluginPackageUpload, replace: boolean) => Promise<PluginPackageReport | true | null>;
		onSetPluginWordPicture: (id: string, heading: string, pngBase64: string | null) => Promise<boolean>;
		onExportPluginPackage: (id: string) => Promise<{ name: string; blob: Blob } | null>;
	};

	let {
		pluginsStatus, settingsStatusError, settingsStatusLoading, pluginActionStatus,
		isAdmin, onLoadSettingsStatus, onDeletePlugin, onSetPluginEnabled,
		onCheckPluginPackage, onInstallPluginPackage, onSetPluginWordPicture, onExportPluginPackage,
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
	function previewSrc(plugin: PluginItem, wordId: string, version = ''): string {
		const query = new URLSearchParams();
		if (version) query.set('v', version);
		return `/api/plugins/${encodeURIComponent(pluginId(plugin))}/words/${encodeURIComponent(wordId)}/preview?${query}`;
	}
	function pluginIsDeletable(plugin: PluginItem): boolean {
		return plugin.deletable ?? !plugin.has_definitions;
	}

	let pictureTarget = $state<{ id: string; heading: string } | null>(null);
	let pictureInput = $state<HTMLInputElement | null>(null);

	function choosePicture(plugin: PluginItem, wordId: string): void {
		pictureTarget = { id: pluginId(plugin), heading: wordId };
		pictureInput?.click();
	}

	async function replacePicture(event: Event): Promise<void> {
		const input = event.currentTarget as HTMLInputElement;
		const file = input.files?.[0];
		input.value = '';
		if (!file || !pictureTarget || pluginBusy) return;
		pluginBusy = true;
		await onSetPluginWordPicture(pictureTarget.id, pictureTarget.heading, await fileToBase64(file));
		pictureTarget = null;
		pluginBusy = false;
	}

	async function exportPlugin(plugin: PluginItem): Promise<void> {
		if (!isAdmin || pluginBusy) return;
		pluginBusy = true;
		const exported = await onExportPluginPackage(pluginId(plugin));
		if (exported) saveBlob(exported.name, exported.blob);
		pluginBusy = false;
	}

	async function resetPicture(plugin: PluginItem, wordId: string): Promise<void> {
		if (!isAdmin || pluginBusy) return;
		pluginBusy = true;
		await onSetPluginWordPicture(pluginId(plugin), wordId, null);
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
					{#each vocabularyPlugins as plugin (`${pluginId(plugin)}:${plugin.status}`)}
						<div class="user-plugin-row">
							<div class="user-plugin-info">
								<div class="system-plugin-title-row">
									<div class="system-plugin-title">{plugin.namespace ? `${plugin.namespace}.${plugin.name}` : plugin.name}</div>
									<span class="plugin-version-pill">{plugin.version ? `v${plugin.version}` : plugin.status}</span>
									{#if plugin.status === "rejected"}<span class="plugin-rejected">{plugin.status}</span>{/if}
								{#if plugin.status !== 'rejected'}<span class="plugin-use-mark">{t().settingsPluginDrawn}</span>{/if}
								</div>
								<div class="system-plugin-desc">{(isJapanese ? plugin.description_ja : plugin.description_en) || ''}</div>
								<div class="plugin-use-hint">{t().settingsPluginPackageHint}</div>
								{#if plugin.reasons?.length}<div class="db-test-result">{plugin.reasons.join(" / ")}</div>{/if}
								{#if plugin.entries?.length}
									<details class="plugin-words">
										<summary>{t().settingsPluginWords}（{plugin.entries.length}）</summary>
										<ul class="plugin-word-list">
											{#each plugin.entries as entry (entry.qualified_name)}
												{@const otherNames = [...(entry.surface_ja ?? []).slice(1), ...(entry.surface_en ?? []).slice(1)]}
												{@const note = isJapanese ? entry.note_ja : entry.note_en}
												{@const example = isJapanese ? entry.example_ja : entry.example_en}
												<li class="plugin-word">
											{#if entry.has_preview}<img class="plugin-word-preview" src={previewSrc(plugin, entry.word_id, entry.preview_version)} alt="" loading="lazy" />{:else}<span class="plugin-word-preview" aria-hidden="true"></span>{/if}
													<div class="plugin-word-text">
												<strong>{entry.written_ja} / {entry.written_en}</strong>
														{#if otherNames.length}<small>{otherNames.join(' / ')}</small>{/if}
												<span>{entry.word_kind === 'object' ? t().pluginObject : t().pluginScene}</span>
														{#if note}<span>{note}</span>{/if}
														{#if example}<span>{t().saijikiPreviewExampleLabel}{example}</span>{/if}
														{#if plugin.kind === 'package' && isAdmin}
															<span class="plugin-word-actions">
														<button class="ghost-btn user-plugin-btn" type="button" onclick={() => choosePicture(plugin, entry.word_id)} disabled={pluginBusy}>{t().settingsPluginPictureReplace}</button>
														{#if entry.custom_preview}<button class="ghost-btn user-plugin-btn" type="button" onclick={() => void resetPicture(plugin, entry.word_id)} disabled={pluginBusy}>{t().settingsPluginPictureReset}</button>{/if}
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
								{#if plugin.kind === 'package' && plugin.status !== 'rejected'}
									<button class="ghost-btn user-plugin-btn" type="button" onclick={() => void exportPlugin(plugin)} disabled={!isAdmin || pluginBusy}>{t().settingsPluginPackageExport}</button>
								{/if}
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
