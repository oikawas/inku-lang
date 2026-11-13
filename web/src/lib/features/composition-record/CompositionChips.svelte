<script lang="ts">
	// The form and main law of a drawn option or work, as two chips (2026-11-13).
	// Against a target, a chip that differs from the target's takes the accent
	// colour, and its title names the target's value. A record that fell back
	// shows one "no composition" chip; no record shows nothing.
	import { t } from '$lib/i18n/index.svelte';
	import CompositionFigure from './CompositionFigure.svelte';
	import { formName, lawName } from './composition-names';
	import type { CompositionSummary } from './record';

	let { summary, target = null, isJapanese }: {
		summary: CompositionSummary;
		target?: CompositionSummary | null;
		isJapanese: boolean;
	} = $props();

	const versus = (term: string, value: string | null) =>
		value ? t().compositionChipVersusTarget(term, value) : term;
	const formTitle = $derived(target ? versus(t().compositionFormTerm, target.form ? formName(target.form, isJapanese) : null) : t().compositionFormTerm);
	const lawTitle = $derived(target ? versus(t().compositionMainLawTerm, target.mainLaw ? lawName(target.mainLaw, isJapanese) : null) : t().compositionMainLawTerm);
</script>

{#if summary.state === 'used' && (summary.form || summary.mainLaw)}
	<span class="cand-chips">
		{#if summary.form}
			<span class="chip" class:diff={!!target && target.state === 'used' && target.form !== summary.form} title={formTitle}><CompositionFigure figure={summary.form} />{formName(summary.form, isJapanese)}</span>
		{/if}
		{#if summary.mainLaw}
			<span class="chip" class:diff={!!target && target.state === 'used' && target.mainLaw !== summary.mainLaw} title={lawTitle}><CompositionFigure figure={summary.mainLaw} />{lawName(summary.mainLaw, isJapanese)}</span>
		{/if}
	</span>
{:else if summary.state === 'fallback'}
	<span class="cand-chips"><span class="chip">{t().compositionFallback}</span></span>
{/if}

<style>
	.cand-chips { display: inline-flex; flex-wrap: wrap; gap: 5px; min-width: 0; }
	.chip { display: inline-flex; align-items: center; gap: 4px; padding: 1px 8px 1px 6px; border: 1px solid var(--border2); border-radius: 999px; color: var(--fg2); font-size: var(--ui-font-size-11); line-height: 1.6; white-space: nowrap; }
	.chip.diff { border-color: var(--accent); color: var(--accent); }
</style>
