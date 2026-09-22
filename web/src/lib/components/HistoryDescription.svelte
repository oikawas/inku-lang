<script lang="ts">
	import { t } from '$lib/i18n/index.svelte';

	let { text, className = '' }: { text: string; className?: string } = $props();
	let expanded = $state(false);
	let clipped = $state(false);
	function measure(element: HTMLElement) {
		const update = () => {
			if (!expanded) clipped = element.scrollHeight > element.clientHeight + 1;
		};
		const observer = new ResizeObserver(update);
		observer.observe(element);
		update();
		return { destroy: () => observer.disconnect() };
	}
</script>

<div class:expanded class={`history-description ${className}`}>
	<span class="history-description-text" use:measure>{text}</span>
	{#if clipped || expanded}
	<button
		type="button"
		class="history-description-toggle"
		aria-expanded={expanded}
		title={expanded ? t().historyDescriptionCollapseTitle : t().historyDescriptionExpandTitle}
		onclick={() => (expanded = !expanded)}
	>
		{expanded ? t().historyDescriptionCollapse : t().historyDescriptionExpand}
	</button>
	{/if}
</div>

<style>
	.history-description { min-width: 0; }
	.history-description-text {
		display: -webkit-box;
		overflow: hidden;
		-webkit-box-orient: vertical;
		-webkit-line-clamp: 3;
		line-clamp: 3;
		white-space: pre-wrap;
		overflow-wrap: anywhere;
	}
	.history-description.expanded .history-description-text { display: block; }
	.history-description-toggle {
		margin-top: 3px;
		padding: var(--btn-sm-padding);
		border: 0;
		background: transparent;
		color: var(--accent);
		font: inherit;
		font-size: var(--btn-sm-font-size);
		border-radius: var(--btn-sm-radius);
		cursor: pointer;
	}
	.history-description-toggle:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
</style>
