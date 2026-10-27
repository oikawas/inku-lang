<!--
	「暴れる」 (wild) toggle for the refine dialogs.

	The parent artwork's setting is preselected and `inherited` marks that
	nothing will be sent unless the user picks.

	The button is a ghost-btn with an accent fill when on, the same in every
	dialog. The next work's conditions show the switch as a SwitchChip instead
	(2026-10-27), beside the route's chips.
-->
<script lang="ts">
	import { t } from '$lib/i18n/index.svelte';

	type Props = {
		value: boolean;
		isJapanese: boolean;
		inherited?: boolean;
		disabled?: boolean;
		onSelect: (value: boolean) => void;
	};

	let { value, isJapanese, inherited = false, disabled = false, onSelect }: Props = $props();
</script>

<div class="wild-inline" role="group" aria-label={t().wildButton}>
	<!-- The label reads as one row: what the switch governs, then whether it
	     is inherited. -->
	<span class="wild-inline-label"
		>{isJapanese ? '筆致制限' : 'Stroke limit'}{#if inherited}<span class="wild-inherit"
				>{isJapanese ? '（継承）' : '(inherited)'}</span
			>{/if}{isJapanese ? '：' : ':'}</span
	>
	<button
		type="button"
		class="ghost-btn wild-btn"
		class:active={value}
		aria-pressed={value}
		{disabled}
		onclick={() => onSelect(!value)}
	>{t().wildButton}</button>
</div>

<style>
	.wild-inline { display: inline-flex; align-items: center; gap: 4px; }
	.wild-inline-label { font-size: var(--ui-font-size-11); color: var(--fg3); white-space: nowrap; }
	.wild-inherit { margin-left: 2px; color: var(--fg3); }
	/* Svelte scopes styles per component, so `ghost-btn` alone would style nothing
	   here and the button would fall back to the browser's own. */
	.wild-btn.active { background: var(--accent); border-color: var(--accent); color: var(--accent-fg); }
	.wild-btn.active:hover { background: var(--accent); }
</style>
