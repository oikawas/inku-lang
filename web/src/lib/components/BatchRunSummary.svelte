<script lang="ts">
	import { onMount } from 'svelte';
	import { t } from '$lib/i18n/index.svelte';
	import { batchClockTime, batchElapsedTime } from '$lib/features/batch/elapsed';

	let { current, total, startedAt, averageWorkMs = null }: { current: number; total: number; startedAt: number; averageWorkMs?: number | null } = $props();
	let now = $state(Date.now());
	onMount(() => {
		const timer = setInterval(() => { now = Date.now(); }, 1000);
		return () => clearInterval(timer);
	});
</script>

<div class="batch-run-summary">
	<div class="batch-tile" role="group" title={t().batchRowOfTotal(current, total)} aria-label={t().batchRowOfTotal(current, total)}>
		<span class="batch-tile-label">{t().batchTileLine}</span>
		<span class="batch-tile-value">{current} / {total}</span>
	</div>
	<div class="batch-tile" role="group" title={t().batchElapsed(batchElapsedTime(now - startedAt, t()))} aria-label={t().batchElapsed(batchElapsedTime(now - startedAt, t()))}>
		<span class="batch-tile-label">{t().batchTileElapsed}</span>
		<span class="batch-tile-value">{batchClockTime(now - startedAt)}</span>
	</div>
	{#if averageWorkMs !== null}
		<div class="batch-tile" role="group" title={t().batchAverageWork(batchElapsedTime(averageWorkMs, t()))} aria-label={t().batchAverageWork(batchElapsedTime(averageWorkMs, t()))}>
			<span class="batch-tile-label">{t().batchTileAverage}</span>
			<span class="batch-tile-value">{batchClockTime(averageWorkMs)}</span>
		</div>
	{/if}
</div>

<style>
	.batch-run-summary { display: flex; flex-wrap: wrap; gap: 4px 12px; margin-bottom: 6px; }
	.batch-tile { display: flex; flex: 0 0 auto; flex-direction: column; white-space: nowrap; }
	.batch-tile-label { color: var(--fg3); font-size: var(--ui-font-size-10); letter-spacing: .08em; text-transform: uppercase; }
	.batch-tile-value { color: var(--fg); font-size: var(--ui-font-size-14); font-variant-numeric: tabular-nums; }
</style>
