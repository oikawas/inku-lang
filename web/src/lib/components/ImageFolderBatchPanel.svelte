<script lang="ts">
	import type { Snippet } from 'svelte';
	import { t } from '$lib/i18n/index.svelte';
	import PaintButton from './PaintButton.svelte';
	import RunStatus from './RunStatus.svelte';
	import type { ImageFolderBatch } from '$lib/features/batch/image-folder.svelte';
	import type { ProviderAttemptCount } from '$lib/paintStream';

	type Props = {
		folder: ImageFolderBatch;
		/** Another run (one work, the description batch, a demo) holds the Server. */
		busy: boolean;
		visionModelName: string;
		visionModelAvailable: boolean;
		stageLabel: string;
		liveMs: number;
		runTokensIn: number | null;
		runTokensOut: number | null;
		runAttempt?: ProviderAttemptCount | null;
		error: string | null;
		onRun: (fromStart: boolean) => void | Promise<void>;
		onStop: () => void;
		// The picture tab's settings rows, rendered by the parent.
		settings?: Snippet;
		/** The descriptions / pictures switch, at the right end of the heading line. */
		sourceSwitch?: Snippet;
	};

	let {
		folder, busy, visionModelName, visionModelAvailable, stageLabel, liveMs,
		runTokensIn, runTokensOut, runAttempt = null, error, onRun, onStop, settings, sourceSwitch,
	}: Props = $props();

	let folderInputEl = $state<HTMLInputElement | null>(null);

	const pending = $derived(folder.pending.length);
	const done = $derived(folder.doneCount);
	const disabled = $derived(busy || !visionModelAvailable);
	const pastFolders = $derived(folder.history.filter((item) => item.name !== folder.folderName || folder.pictures.length === 0));

	function chooseFolder() {
		if (!folder.running) folderInputEl?.click();
	}

	function dateOf(time: number): string {
		return new Date(time).toLocaleString(t().code === 'ja' ? 'ja-JP' : 'en-US', {
			month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit',
		});
	}
</script>

<div class="batch-label">
	<span class="batch-label-text"><strong>{t().imageFolderLabel}</strong><span class="batch-label-hint">{t().imageFolderHint}</span></span>
	<span class="batch-label-end">
		{#if folder.interrupted && !folder.running}
			<span class="batch-interrupted-mark">{t().batchInterruptedLabel}</span>
		{/if}
		{@render sourceSwitch?.()}
	</span>
</div>

<!-- The browser reads a folder only when it is picked in its own dialog; a typed
     path cannot be opened, so there is no path field. -->
<div class="folder-pick">
	<input
		bind:this={folderInputEl}
		class="folder-input"
		type="file"
		multiple
		{...{ webkitdirectory: true }}
		disabled={folder.running}
		onchange={(event) => {
			const files = event.currentTarget.files;
			if (files) folder.pick(Array.from(files));
			event.currentTarget.value = '';
		}}
	/>
	<button type="button" class="ghost-btn" onclick={chooseFolder} disabled={folder.running}>{t().imageFolderChoose}</button>
	{#if folder.folderName}
		<span class="folder-summary">{t().imageFolderSummary(folder.folderName, folder.pictures.length, done)}</span>
	{/if}
</div>
{#if folder.folderName && folder.pictures.length === 0}<p class="batch-info">{t().imageFolderEmpty}</p>{/if}

<section class="batch-next-conditions" aria-label={t().batchNextConditionsLabel}>
	<div class="batch-next-conditions-head"><span>{t().batchNextConditionsLabel}</span></div>
	{@render settings?.()}
</section>

{#if folder.running}
	<div class="batch-progress-wrap">
		<RunStatus
			label={`${t().imageFolderProgress(folder.current, folder.total, folder.activePath)}${stageLabel ? ` · ${stageLabel}` : ''}`}
			stage1Model={visionModelName}
			elapsedMs={liveMs}
			tokensIn={runTokensIn}
			tokensOut={runTokensOut}
			attempt={runAttempt}
			{onStop}
		/>
	</div>
{:else if folder.pictures.length > 0}
	<div class="batch-actions">
		{#if pending === 0}
			<p class="batch-info">{t().imageFolderAllDone}</p>
			<button type="button" class="ghost-btn" onclick={() => onRun(true)} {disabled}>{t().imageFolderRestart}</button>
		{:else if done > 0 || folder.failures.length > 0}
			<PaintButton onclick={() => onRun(false)} {disabled}>{t().imageFolderResume(pending)}</PaintButton>
			<button type="button" class="ghost-btn" onclick={() => onRun(true)} {disabled}>{t().imageFolderRestart}</button>
		{:else}
			<PaintButton onclick={() => onRun(true)} {disabled}>{t().imageFolderRun(pending)}</PaintButton>
		{/if}
	</div>
	{#if !visionModelAvailable}<p role="status">{t().imageVisionRequired}</p>{/if}
{/if}

{#if !folder.running && folder.stopReason}
	<p class="error-text">{t().imageFolderServerLost(folder.stopReason)}</p>
{:else if !folder.running && folder.interrupted}
	<p class="batch-info">{t().imageFolderInterrupted}</p>
{/if}
{#if error}<p class="error-text">{error}</p>{/if}

{#if !folder.running && folder.failures.length > 0}
	<details class="folder-failures">
		<summary>{t().imageFolderFailures(folder.failures.length)}</summary>
		<ul>
			{#each folder.failures as failure (failure.key)}
				<li><span class="failure-path">{failure.path}</span><span>{failure.message}</span></li>
			{/each}
		</ul>
	</details>
{/if}

{#if pastFolders.length > 0}
	<section class="folder-history" aria-label={t().imageFolderHistoryLabel}>
		<div class="batch-next-conditions-head"><span>{t().imageFolderHistoryLabel}</span></div>
		<p class="folder-history-hint">{t().imageFolderHistoryHint}</p>
		<ul>
			{#each pastFolders as item (item.name)}
				<li>
					<button type="button" class="folder-history-item" onclick={chooseFolder} disabled={folder.running}>
						<span class="folder-history-name">{item.name}</span>
						<span class="folder-history-meta">{t().imageFolderHistoryEntry(item.done.length, item.total, dateOf(item.updatedAt))}</span>
					</button>
				</li>
			{/each}
		</ul>
	</section>
{/if}

<style>
	/* Same shape as the description batch's label in BatchPanel. */
	.batch-label {
		display: flex; align-items: baseline; justify-content: space-between; gap: 8px;
		font-size: var(--ui-font-size-14); line-height: 1.5; color: var(--fg2);
	}
	.batch-label-text { display: grid; min-width: 0; gap: 2px; }
	.batch-label strong { font-weight: 600; color: var(--fg); }
	.batch-label-hint { color: var(--fg2); font-size: var(--ui-font-size-12); }
	.batch-label-end { display: flex; flex: 0 0 auto; align-items: center; gap: 10px; margin-left: auto; }
	.batch-interrupted-mark { flex: 0 0 auto; color: var(--danger); font-size: var(--ui-font-size-12); font-weight: 500; }
	.error-text { color: var(--danger); font-size: var(--ui-font-size-12); white-space: pre-line; }
	.folder-pick { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; margin: 8px 0 4px; }
	.folder-input { display: none; }
	.folder-summary { min-width: 0; color: var(--fg2); font-size: var(--ui-font-size-12); overflow-wrap: anywhere; }
	.batch-info { margin: 4px 0; color: var(--fg2); font-size: var(--ui-font-size-12); }
	.batch-next-conditions { margin-top: 12px; padding-top: 10px; border-top: 1px solid var(--border); }
	.batch-next-conditions-head {
		display: flex; justify-content: space-between; gap: 8px; margin-bottom: 6px;
		color: var(--fg2); font-size: var(--ui-font-size-12); font-weight: 600;
	}
	.batch-progress-wrap { margin: 8px 0; }
	.batch-actions { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; margin: 8px 0; }
	.folder-failures { margin: 6px 0; color: var(--fg2); font-size: var(--ui-font-size-12); }
	.folder-failures ul { margin: 4px 0 0; padding-left: 16px; }
	.folder-failures li { display: grid; gap: 2px; margin-bottom: 4px; }
	.failure-path { color: var(--fg); overflow-wrap: anywhere; }
	.folder-history { margin-top: 12px; }
	.folder-history-hint { margin: 0 0 6px; color: var(--fg3); font-size: var(--ui-font-size-12); line-height: 1.5; }
	.folder-history ul { list-style: none; margin: 0; padding: 0; display: grid; gap: 4px; }
	.folder-history-item {
		display: flex; justify-content: space-between; gap: 8px; width: 100%;
		padding: 6px 8px; border: 1px solid var(--border2); border-radius: var(--r);
		background: transparent; color: var(--fg); font: inherit; font-size: var(--ui-font-size-12); text-align: left; cursor: pointer;
	}
	.folder-history-item:hover:not(:disabled) { background: var(--bg2); }
	.folder-history-name { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
	.folder-history-meta { flex: 0 0 auto; color: var(--fg3); }
</style>
