<script lang="ts">
	import { onMount } from 'svelte';
	import { t } from '$lib/i18n/index.svelte';
	import { batchElapsedTime } from '$lib/features/batch/elapsed';

	let { current, total, startedAt }: { current: number; total: number; startedAt: number } = $props();
	let now = $state(Date.now());
	onMount(() => {
		const timer = setInterval(() => { now = Date.now(); }, 1000);
		return () => clearInterval(timer);
	});
</script>

<div class="batch-run-summary">
	<span>{t().batchRowOfTotal(current, total)}</span>
	<span>{t().batchElapsed(batchElapsedTime(now - startedAt, t()))}</span>
</div>

<style>
	.batch-run-summary { display: flex; gap: 12px; margin-bottom: 6px; color: var(--fg); font-size: var(--ui-font-size-12); white-space: nowrap; }
</style>
