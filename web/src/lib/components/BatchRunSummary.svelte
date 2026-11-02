<script lang="ts">
	import { onMount } from 'svelte';
	import { t } from '$lib/i18n/index.svelte';
	import { batchElapsedTime } from '$lib/features/batch/elapsed';

	let { current, total, startedAt, averageWorkMs = null }: { current: number; total: number; startedAt: number; averageWorkMs?: number | null } = $props();
	let now = $state(Date.now());
	onMount(() => {
		const timer = setInterval(() => { now = Date.now(); }, 1000);
		return () => clearInterval(timer);
	});
</script>

<div class="batch-run-summary">
	<span>{t().batchRowOfTotal(current, total)}</span>
	<span>{t().batchElapsed(batchElapsedTime(now - startedAt, t()))}</span>
	{#if averageWorkMs !== null}<span class="batch-average">{t().batchAverageWork(batchElapsedTime(averageWorkMs, t()))}</span>{/if}
</div>

<style>
	.batch-run-summary { display: flex; flex-wrap: wrap; gap: 4px 12px; margin-bottom: 6px; color: var(--fg); font-size: var(--ui-font-size-12); }
	.batch-run-summary > span { min-width: 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
	.batch-average { margin-left: auto; text-align: right; }
</style>
