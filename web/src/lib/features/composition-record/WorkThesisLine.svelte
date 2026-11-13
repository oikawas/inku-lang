<script lang="ts">
	// The thesis line under the condition strip (2026-11-13): the displayed
	// work's thesis on one line, with its form and main law by name. It only
	// reads; a work whose record has no thesis shows no line at all.
	import { t } from '$lib/i18n/index.svelte';
	import CompositionFigure from './CompositionFigure.svelte';
	import { formName, lawName } from './composition-names';
	import { compositionOf, thesisOf } from './record';

	let { work, isJapanese }: { work: { description_ddl?: unknown } | null | undefined; isJapanese: boolean } = $props();
	const record = $derived(compositionOf(work));
	const thesis = $derived(thesisOf(record));
	const form = $derived(record?.answer?.form ?? null);
	const mainLaw = $derived(record?.answer?.main_law ?? null);
</script>

{#if thesis}
	<div class="work-thesis-line" title={thesis}>
		<span class="work-thesis-label">{t().compositionThesisLabel}</span>
		<span class="work-thesis-text">{thesis}</span>
		<span class="work-thesis-names">
			{#if form}<span class="name-fig"><CompositionFigure figure={form} />{formName(form, isJapanese)}</span>{/if}
			{#if form && mainLaw}<span aria-hidden="true">·</span>{/if}
			{#if mainLaw}<span class="name-fig"><CompositionFigure figure={mainLaw} />{lawName(mainLaw, isJapanese)}</span>{/if}
		</span>
	</div>
{/if}

<style>
	.work-thesis-line { display: flex; align-items: baseline; gap: 10px; flex-shrink: 0; padding: 6px 16px 6px 32px; border-bottom: 1px solid var(--border); background: var(--bg); min-width: 0; }
	.work-thesis-label { flex: 0 0 auto; color: var(--fg3); font-size: var(--ui-font-size-11); line-height: 1.5; }
	.work-thesis-text { flex: 1 1 0; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--fg); font-size: var(--ui-font-size-13); line-height: 1.5; }
	.work-thesis-names { flex: 0 0 auto; display: inline-flex; align-items: center; gap: 4px; color: var(--fg2); font-size: var(--ui-font-size-12); white-space: nowrap; }
	.name-fig { display: inline-flex; align-items: center; gap: 4px; }
	/* A narrow canvas keeps the thesis and hides the names. */
	@container canvas-panel (max-width: 560px) {
		.work-thesis-names { display: none; }
	}
</style>
