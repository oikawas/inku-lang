<!--
	LLM and Vision side by side, the purpose a model cannot be chosen for greyed
	out (the author, 2026-10-13). Shared by the hover card and the picker's card so
	the two read the same. Display-only, inside a tooltip.
-->
<script lang="ts">
	import type { ModelOption } from '$lib/models';
	import { modelPurposeBadges } from '$lib/modelMeta';

	let { model, isJapanese }: { model: ModelOption; isJapanese: boolean } = $props();
</script>

<span class="purpose-badges">
	{#each modelPurposeBadges(model) as badge (badge.purpose)}
		<span class="purpose-badge" class:unavailable={!badge.selectable}>{badge.label}{#if !badge.selectable}<span class="sr-only">{isJapanese ? '（選べません）' : ' (not selectable)'}</span>{/if}</span>
	{/each}
</span>

<style>
	.purpose-badges { display: flex; flex-wrap: wrap; gap: 4px; }
	.purpose-badge { padding: 0 7px; border: 1px solid var(--tooltip-border); border-radius: 999px; color: var(--tooltip-fg); font-size: var(--ui-font-size-10); line-height: 1.7; }
	.purpose-badge.unavailable { color: var(--tooltip-muted); opacity: .45; }
	.sr-only { position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip: rect(0, 0, 0, 0); white-space: nowrap; border: 0; }
</style>
