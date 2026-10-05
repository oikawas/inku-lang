<script lang="ts">
	import { onDestroy, untrack } from 'svelte';
	import { highlightDDL } from '$lib/highlight';
	import { matchingRange, scanNumericRanges, type CompositionRange, type NumericRange, type RangePreview } from '$lib/composition-ranges';
	import { createRangeEditState } from '$lib/range-edit.svelte';
	import { t } from '$lib/i18n/index.svelte';

	let { ddl, ranges, workKey, lang = null, disabled = false, onChange = null, onPreview = null, onInvalid = null }: {
		ddl: string; ranges: CompositionRange[]; workKey: unknown; lang?: 'ja' | 'en' | null; disabled?: boolean;
		onChange?: ((ddl: string) => void) | null;
		onPreview?: ((preview: RangePreview | null) => void) | null;
		onInvalid?: ((invalid: boolean) => void) | null;
	} = $props();
	const editor = createRangeEditState({ source: () => ddl, ranges: () => ranges, disabled: () => disabled || !onChange,
		change: (source) => onChange?.(source), preview: (preview) => onPreview?.(preview), invalid: (invalid) => onInvalid?.(invalid) });
	const active = $derived(editor.active);
	const parts = $derived.by(() => {
		const found = scanNumericRanges(ddl).filter((range) => (!lang || range.lang === lang) && (!active || range.end <= active.range.start || range.start >= active.range.end));
		if (active) found.push(active.range);
		found.sort((a, b) => a.start - b.start);
		let offset = 0;
		const result: { text?: string; range?: NumericRange }[] = [];
		for (const range of found) {
			result.push({ text: ddl.slice(offset, range.start) }, { range });
			offset = range.end;
		}
		result.push({ text: ddl.slice(offset) });
		return result;
	});
	$effect(() => {
		workKey;
		untrack(() => editor.reset(true));
	});
	$effect(() => {
		ddl;
		untrack(() => editor.sync());
	});
	$effect(() => {
		if (active && ddl !== active.source) {
			untrack(editor.reset);
		}
	});
	onDestroy(editor.reset);
</script>

<!-- Touch keeps its preview after release; leaving by mouse clears it. -->
<span class="range-ddl-body" role="group" onpointerleave={(event) => { if (event.pointerType !== 'touch') onPreview?.(null); }}>
	{#each parts as part}
		{#if part.range}
			{@const range = part.range}
			{@const folded = !!matchingRange(range, ranges) && active?.range.start !== range.start}
			<button type="button" class="range-name ddl-token ddl-token-place" class:folded
				aria-expanded={!folded} aria-disabled={disabled}
				onpointerenter={() => editor.show(range)} onfocus={() => editor.show(range)} onblur={() => onPreview?.(null)}
				onpointerleave={(event) => { if (event.pointerType !== 'touch' && !active) onPreview?.(null); }}
				onclick={() => {
					if (active?.range.start === range.start) { if (range.bounds) editor.reset(); else editor.show(range); }
					else editor.open(range);
				}}>{folded ? range.name : ddl.slice(range.nameStart, range.nameEnd)}</button>{#if !folded}{ddl.slice(range.nameEnd, range.bodyStart)}{#if active?.range.start === range.start}<input
				class="range-numbers" class:invalid={!range.bounds} aria-invalid={!range.bounds}
				aria-label={t().ddlRangeNumbers} title={!range.bounds ? t().ddlRangeInvalid : t().ddlRangeNumbers}
				value={range.body} style:width="{Math.max(14, range.body.length + 1)}ch" disabled={disabled}
				oninput={(event) => editor.edit(event.currentTarget.value)} onfocus={() => editor.show(range)} onblur={() => onPreview?.(null)}
			/>{:else}<span class="range-numbers">{range.body}</span>{/if}{ddl.slice(range.bodyEnd, range.end)}{#if active?.range.start === range.start && !range.bounds}<span class="range-error" role="status">{t().ddlRangeInvalid}</span>{/if}{/if}
		{:else}{@html highlightDDL(part.text ?? '')}{/if}
	{/each}
</span>

<style>
	.range-name { font: inherit; border: 0; padding: 0; cursor: pointer; }
	.range-name.folded { text-decoration: underline dotted; text-underline-offset: 0.22em; }
	.range-name[aria-disabled='true'] { cursor: default; }
	.range-numbers { color: var(--fg3); }
	input.range-numbers { max-width: 100%; font: inherit; padding: 0; border: 0; border-bottom: 1px dotted var(--border2); background: transparent; }
	input.range-numbers.invalid { border-bottom-color: var(--error, var(--fg)); }
	.range-error { display: inline-block; color: var(--fg2); font-size: var(--ui-font-size-12); margin-inline: 0.5em; }
</style>
