<script lang="ts">
	import { t } from '$lib/i18n/index.svelte';
	import type { PluginItem, SettingsStatus } from './server-administration.svelte';
	import './plugin-administration-settings.css';

	// The drawing uses only definitions the developers wrote in JSON; a plugin
	// document switches such a package on and off and gives its words, notes
	// and previews. Documents are not written here (I-703): a legacy one without
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
	};

	let {
		pluginsStatus, settingsStatusError, settingsStatusLoading, pluginActionStatus,
		isAdmin, onLoadSettingsStatus, onDeletePlugin, onSetPluginEnabled,
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
	function previewSrc(qualifiedName: string): string {
		return `/api/saijiki/plugin-preview?${new URLSearchParams({ name: qualifiedName, scale: '1' })}`;
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
								<div class="system-plugin-desc">{plugin.path ?? ""}</div>
								<div class="plugin-use-hint">{plugin.has_definitions ? t().settingsPluginDrawnHint : t().settingsPluginNotDrawnHint}</div>
								{#if plugin.reasons?.length}<div class="db-test-result">{plugin.reasons.join(" / ")}</div>{/if}
								{#if plugin.entries?.length}
									<details class="plugin-words">
										<summary>{t().settingsPluginWords}（{plugin.entries.length}）</summary>
										<ul class="plugin-word-list">
											{#each plugin.entries as entry (entry.qualified_name)}
												{@const surfaces = (isJapanese ? entry.surface_ja : entry.surface_en) ?? []}
												{@const note = isJapanese ? entry.note_ja : entry.note_en}
												<li class="plugin-word">
													{#if entry.has_preview}<img class="plugin-word-preview" src={previewSrc(entry.qualified_name)} alt="" loading="lazy" />{:else}<span class="plugin-word-preview" aria-hidden="true"></span>{/if}
													<div class="plugin-word-text">
														<strong>{entry.qualified_name}</strong>
														{#if entry.aliases?.length}<small>{entry.aliases.join(', ')}</small>{/if}
														{#if surfaces.length}<span>{surfaces.join(' | ')}</span>{/if}
														{#if note}<span>{note}</span>{/if}
													</div>
												</li>
											{/each}
										</ul>
									</details>
								{/if}
							</div>
							<div class="user-plugin-controls">
								{#if !plugin.has_definitions}
									{#if pluginDeleteConfirmId === pluginId(plugin)}
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
