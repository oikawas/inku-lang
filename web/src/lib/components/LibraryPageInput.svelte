<script lang="ts">
	import { t } from '$lib/i18n/index.svelte';

	type Props = {
		/** Counted from the newest, as the pager prints it. */
		current: number;
		total: number;
		onJump: (page: number) => void;
	};
	let { current, total, onJump }: Props = $props();

	// What the reader is typing, kept apart from the page shown so a listing
	// that answers mid-edit does not overwrite it.
	let draft = $state('');
	let editing = $state(false);
	const shown = $derived(editing ? draft : String(current));

	function begin(event: FocusEvent & { currentTarget: HTMLInputElement }): void {
		draft = String(current);
		editing = true;
		event.currentTarget.select();
	}

	function commit(): void {
		if (!editing) return;
		editing = false;
		const typed = draft.trim();
		const page = Number(typed);
		// Not a number: the page shown stays, as if nothing was typed.
		if (!typed || !Number.isFinite(page)) return;
		const target = Math.max(1, Math.min(Math.trunc(page), total));
		if (target !== current) onJump(target);
	}

	function handleKeydown(event: KeyboardEvent & { currentTarget: HTMLInputElement }): void {
		if (event.key === 'Enter') {
			event.preventDefault();
			commit();
			event.currentTarget.blur();
		} else if (event.key === 'Escape') {
			// The Library closes on Escape; here it only puts the number back
			// (the page's own handler steps aside for data-escape-undoes-edit).
			event.preventDefault();
			editing = false;
			event.currentTarget.blur();
		}
	}
</script>

<span class="library-page">
	<input
		type="text"
		inputmode="numeric"
		autocomplete="off"
		data-escape-undoes-edit
		value={shown}
		aria-label={t().historyPageJumpLabel(total)}
		title={t().historyPageJumpLabel(total)}
		style:width={`${String(total).length + 1.5}ch`}
		onfocus={begin}
		oninput={(event) => { draft = event.currentTarget.value; }}
		onkeydown={handleKeydown}
		onblur={commit}
	/>
	<span>/ {total}</span>
</span>

<style>
	.library-page { display: inline-flex; align-items: center; gap: 4px; }
	input {
		box-sizing: border-box;
		min-width: 3ch;
		border: 1px solid var(--border2);
		border-radius: var(--btn-sm-radius);
		padding: 2px 4px;
		background: var(--panel);
		color: var(--fg);
		font: inherit;
		font-variant-numeric: tabular-nums;
		text-align: right;
	}
	input:focus { outline: 1px solid var(--fg3); }
</style>
