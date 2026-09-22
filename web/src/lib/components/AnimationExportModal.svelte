<script lang="ts">
	import { onMount } from 'svelte';
	import { t } from '$lib/i18n/index.svelte';
	import AnimationExportFields from '$lib/features/export/AnimationExportFields.svelte';
	import { downloadFolderSettings } from '$lib/features/export/download-folder.svelte';
	import { supportsDirectoryPicker } from '$lib/features/export/save-target';
	import {
		DEFAULT_ANIMATION_EXPORT_SETTINGS,
		normalizeAnimationExportSettings,
		type AnimationExportSettings
	} from '$lib/animationExport';

	type Props = {
		initialSettings: AnimationExportSettings;
		count: number;
		mode?: 'layer' | 'transition';
		scopeDescription?: string | null;
		onSave: (settings: AnimationExportSettings, directory?: FileSystemDirectoryHandle) => Promise<void>;
		onClose: () => void;
	};

	let { initialSettings, count, mode: requestedMode, scopeDescription = null, onSave, onClose }: Props = $props();
	let dialog: HTMLDialogElement;
	let settings = $state<AnimationExportSettings>({ ...DEFAULT_ANIMATION_EXPORT_SETTINGS });
	let directory = $state<FileSystemDirectoryHandle | null>(null);
	let pickerSupported = $state(false);
	let picking = $state(false);
	let saving = $state(false);
	let error = $state<string | null>(null);
	const busy = $derived(picking || saving);
	const mode = $derived(requestedMode ?? (count === 1 ? 'layer' : 'transition'));
	const title = $derived(mode === 'layer' ? t().animationExportLayerTitle : t().animationExportTransitionTitle);
	const description = $derived(scopeDescription ?? t().animationExportSelection(count));

	onMount(() => {
		settings = normalizeAnimationExportSettings(initialSettings);
		pickerSupported = supportsDirectoryPicker();
		const mountedDialog = dialog;
		mountedDialog.showModal();
		return () => mountedDialog.close();
	});

	function close() {
		if (!busy) onClose();
	}

	async function chooseDirectory() {
		if (busy || !window.showDirectoryPicker) return;
		picking = true;
		error = null;
		try {
			// Keep this export's destination separate from the user's default folder.
			directory = await window.showDirectoryPicker({ mode: 'readwrite' });
		} catch (cause) {
			if (!(cause instanceof DOMException && cause.name === 'AbortError')) {
				error = t().animationExportFolderFailed;
			}
		} finally {
			picking = false;
		}
	}

	async function save(event: SubmitEvent) {
		event.preventDefault();
		if (busy) return;
		saving = true;
		error = null;
		try {
			await onSave(normalizeAnimationExportSettings(settings), directory ?? undefined);
			onClose();
		} catch (cause) {
			const reason = cause instanceof Error ? cause.message : String(cause);
			error = t().animationExportFailed(reason);
		} finally {
			saving = false;
		}
	}
</script>

<dialog
	bind:this={dialog}
	aria-labelledby="animation-export-title"
	aria-describedby="animation-export-description"
	oncancel={(event) => { event.preventDefault(); close(); }}
	onkeydown={(event) => event.stopPropagation()}
>
	<form onsubmit={save} aria-busy={busy}>
		<header>
			<h2 id="animation-export-title">{title}</h2>
			<button type="button" onclick={close} disabled={busy}>{t().closeLabel}</button>
		</header>
		<p id="animation-export-description">{description}</p>
		<AnimationExportFields bind:settings {mode} disabled={busy} />
		<section class="destination" aria-labelledby="animation-export-destination">
			<h3 id="animation-export-destination">{t().settingsDownloadFolderLabel}</h3>
			<div class="destination-row">
				<span class="destination-name">
					{#if directory}
						{directory.name}
					{:else if pickerSupported && downloadFolderSettings.enabled && downloadFolderSettings.name}
						{t().settingsDownloadFolderCurrent(downloadFolderSettings.name)}
					{:else}
						{t().settingsDownloadFolderNone}
					{/if}
				</span>
				<button type="button" onclick={chooseDirectory} disabled={busy || !pickerSupported}>
					{t().animationExportChoosePath}
				</button>
			</div>
			{#if !pickerSupported}
				<p class="hint">{t().animationExportFolderUnsupported}</p>
			{:else if !directory && downloadFolderSettings.needsPicking}
				<p class="hint">{t().settingsDownloadFolderNeedsPicking}</p>
			{/if}
		</section>
		{#if error}<p class="error" role="alert">{error}</p>{/if}
		<footer>
			<button class="save" type="submit" disabled={busy}>
				{saving ? t().animationExportBusy : t().animationExportSave}
			</button>
		</footer>
	</form>
</dialog>

<style>
	dialog {
		inset: 0;
		margin: auto;
		width: min(560px, calc(100vw - 32px));
		max-height: calc(100dvh - 32px);
		box-sizing: border-box;
		padding: 20px;
		border: 1px solid var(--border);
		border-radius: var(--r-lg);
		background: var(--panel2);
		color: var(--fg);
		box-shadow: 0 12px 48px rgba(0, 0, 0, 0.18);
	}
	dialog::backdrop { background: rgba(0, 0, 0, 0.35); }
	form { display: grid; gap: 16px; }
	header, .destination-row { display: flex; align-items: center; gap: 12px; }
	header { justify-content: space-between; }
	h2 { margin: 0; font-size: 16px; }
	h3 { margin: 0; font-size: 13px; font-weight: 500; }
	p { margin: 0; color: var(--fg2); font-size: 12px; }
	.destination { display: grid; gap: 8px; border-top: 1px solid var(--border); padding-top: 16px; }
	.destination-row { flex-wrap: wrap; }
	.destination-name { flex: 1; min-width: 120px; overflow-wrap: anywhere; font-size: 12px; }
	.hint { color: var(--fg3); }
	.error { color: var(--danger); overflow-wrap: anywhere; }
	footer { display: flex; justify-content: flex-end; }
	button {
		padding: var(--btn-sm-padding);
		border-radius: var(--btn-sm-radius);
		font-size: var(--btn-sm-font-size);
		font-family: inherit;
		border: 1px solid var(--border);
		background: var(--action-bg);
		color: var(--action-fg);
		cursor: pointer;
	}
	button:hover:not(:disabled) { background: var(--action-hover); }
	button.save { background: var(--accent); color: var(--accent-fg); border-color: var(--accent); }
	button:disabled { opacity: 0.55; cursor: default; }
</style>
