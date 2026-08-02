<!--
	「暴れる」 (wild) toggle for the refine dialogs.

	Mirrors TenkeiSelect's compact form: the parent artwork's setting is
	preselected and `inherited` marks that nothing will be sent unless the user
	picks. Staffage and wild are the two things a refine dialog can override, so
	they read the same way and sit next to each other.

	The button styling follows InputPanel's .wild-btn -- ghost-btn with an accent
	fill when on -- so the same control looks the same wherever it appears.
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
	{#if inherited}<span class="wild-inherit">{isJapanese ? '（継承）' : '(inherited)'}</span>{/if}
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
	.wild-inherit { color: var(--fg3); font-size: 10px; }
	/* Svelte scopes styles per component, so `ghost-btn` alone would style nothing
	   here and the button would fall back to the browser's own. The definition is
	   the same one InputPanel and the other panels carry. */
	.ghost-btn {
		padding: var(--btn-sm-padding);
		border: 1px solid var(--border2);
		border-radius: var(--btn-sm-radius);
		background: var(--panel);
		color: var(--fg2);
		font-size: var(--btn-sm-font-size);
		cursor: pointer;
		font-family: inherit;
		white-space: nowrap;
	}
	.ghost-btn:hover { background: var(--bg2); }
	.ghost-btn:disabled { cursor: not-allowed; opacity: 0.55; }
	.wild-btn.active { background: var(--accent); border-color: var(--accent); color: var(--accent-fg); }
	.wild-btn.active:hover { background: var(--accent); }
</style>
