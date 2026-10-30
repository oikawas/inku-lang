<!--
	「筆致制限を外す」 (wild) toggle for the refine dialogs. Named 暴れる and
	labelled 筆致制限 until 2026-10-27, when the author renamed it by what lighting
	it does; the button now carries the whole name, so no label precedes it.

	Each dialog starts with the saved default and can choose its own value.

	The button is a ghost-btn with an accent fill when on, the same in every
	dialog. The next work's conditions show the switch as a SwitchChip instead
	(2026-10-27), on their Options line.
-->
<script lang="ts">
	import { t } from '$lib/i18n/index.svelte';

	type Props = {
		value: boolean;
		disabled?: boolean;
		onSelect: (value: boolean) => void;
	};

	let { value, disabled = false, onSelect }: Props = $props();
</script>

<div class="wild-inline" role="group" aria-label={t().wildButton}>
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
	/* Svelte scopes styles per component, so `ghost-btn` alone would style nothing
	   here and the button would fall back to the browser's own. */
	.wild-btn.active { background: var(--accent); border-color: var(--accent); color: var(--accent-fg); }
	.wild-btn.active:hover { background: var(--accent); }
</style>
