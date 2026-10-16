<script lang="ts">
	import { onDestroy } from 'svelte';
	import { t } from '$lib/i18n/index.svelte';

	type Props = {
		value: string;
		busy: boolean;
		failed: boolean;
		total: number;
		onSearch: (value: string) => void;
	};
	let { value = $bindable(''), busy, failed, total, onSearch }: Props = $props();
	let inputEl: HTMLInputElement;
	let timer: ReturnType<typeof setTimeout> | undefined;
	let pending = $state(false);
	function search(): void {
		clearTimeout(timer);
		pending = false;
		onSearch(value);
	}
	function schedule(event: Event): void {
		clearTimeout(timer);
		pending = true;
		if (!(event instanceof InputEvent && event.isComposing)) timer = setTimeout(search, 250);
	}
	function clear(): void {
		value = '';
		search();
		inputEl.focus();
	}
	onDestroy(() => clearTimeout(timer));
</script>

<form class="canvas-work-search" role="search" aria-label={t().canvasSearchLabel} onsubmit={(event) => { event.preventDefault(); search(); }}>
	<div class="search-input-wrap">
		<input type="search" bind:this={inputEl} bind:value maxlength="200"
			aria-label={t().canvasSearchLabel} title={t().canvasSearchHint} placeholder={t().canvasSearchPlaceholder}
			aria-busy={busy} oninput={schedule} oncompositionend={() => { clearTimeout(timer); timer = setTimeout(search, 250); }} />
		<button type="button" aria-label={t().historySearchClear} title={t().historySearchClear} disabled={!value} onclick={clear}>×</button>
	</div>
	{#if !pending && (failed || (value.trim() && !busy && total === 0))}
		<span class="search-status" role="status">{failed ? t().canvasSearchFailed : t().canvasSearchEmpty}</span>
	{/if}
</form>

<style>
	.canvas-work-search { position: relative; flex: 1 1 14rem; min-width: min(10rem, 100%); max-width: 22rem; margin: 5px 8px; }
	.search-input-wrap { display: flex; align-items: center; border: 1px solid var(--border2); border-radius: var(--btn-sm-radius); background: var(--panel); }
	.search-input-wrap:focus-within { outline: 1px solid var(--fg3); }
	input { flex: 1; min-width: 0; width: 100%; border: 0; padding: var(--btn-sm-padding); background: transparent; color: var(--fg); font: inherit; font-size: var(--btn-sm-font-size); outline: none; }
	input::-webkit-search-cancel-button { display: none; }
	button { flex: 0 0 auto; border: 0; border-radius: var(--btn-sm-radius); padding: var(--btn-sm-padding); background: transparent; color: var(--fg2); font: inherit; font-size: var(--btn-sm-font-size); cursor: pointer; }
	button:hover:enabled { background: var(--bg2); color: var(--fg); }
	button:disabled { opacity: .35; cursor: default; }
	.search-status { position: absolute; top: 100%; left: 0; z-index: 100; max-width: 100%; padding: 6px 8px; border: 1px solid var(--border2); border-radius: var(--btn-sm-radius); background: var(--panel); color: var(--fg2); font-size: var(--btn-sm-font-size); }
</style>
