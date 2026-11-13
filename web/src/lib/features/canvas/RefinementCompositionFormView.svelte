<script lang="ts">
	import { t } from '$lib/i18n/index.svelte';
	import PaintButton from '$lib/components/PaintButton.svelte';
	import RunStatus from '$lib/components/RunStatus.svelte';
	import VariationLanes from '$lib/components/VariationLanes.svelte';
	import RefinementCandidateGrid from './RefinementCandidateGrid.svelte';
	import CompositionChips from '$lib/features/composition-record/CompositionChips.svelte';
	import CompositionFigure from '$lib/features/composition-record/CompositionFigure.svelte';
	import type { CompositionSummary } from '$lib/features/composition-record/record';
	import { COMPOSITION_FORMS, compositionFormOptions, type CompositionForm } from './composition-form';
	import type { RefinementSession } from './refinement-session.svelte';

	let { isJapanese, resultAvailable, artworkUrl, canvasAspectWidth, canvasAspectHeight, refinementSession,
		compositionForm, compositionFormSwitch, targetComposition, onGenerateCandidates, onSaveAndClose, onDiscardAndClose }: {
		isJapanese: boolean; resultAvailable: boolean; artworkUrl: string | null;
		canvasAspectWidth: number; canvasAspectHeight: number; refinementSession: RefinementSession;
		compositionForm: string | null; compositionFormSwitch: boolean;
		targetComposition: CompositionSummary | null;
		onGenerateCandidates: (form: CompositionForm, count: 1 | 4) => void | Promise<void>;
		onSaveAndClose: () => void | Promise<void>; onDiscardAndClose: () => void | Promise<void>;
	} = $props();
	let selected = $state<CompositionForm>('one_corner');
	$effect(() => { selected = COMPOSITION_FORMS.includes(compositionForm as CompositionForm) ? compositionForm as CompositionForm : 'one_corner'; });
	const busy = $derived(refinementSession.busy || refinementSession.gridBusy);
</script>

<div class="refine-panel"><div class="refine-stage">
	<div class="refine-target-column">
		<div class="refine-target-card"><div class="comparison-label">{t().refineTargetTitle}</div>
			<div class="comparison-art" style="aspect-ratio: {canvasAspectWidth} / {canvasAspectHeight}">{#if artworkUrl}<img class="canvas-art" src={artworkUrl} alt="" />{/if}</div>
			{#if targetComposition && targetComposition.state !== 'none'}
				<div class="target-now"><span class="target-now-label">{t().compositionTargetNow}</span><CompositionChips summary={targetComposition} {isJapanese} />
					{#if targetComposition.thesis}<p class="target-thesis">{targetComposition.thesis}</p>{/if}
				</div>
			{/if}
		</div>
		<div class="refine-target-controls"><section class="refine-action-section">
			{#if compositionFormSwitch}<p>{t().compositionFormSwitchNotice}</p>{/if}
			<div class="form-options" role="radiogroup" aria-label={t().workActionCompositionForm}>
				{#each compositionFormOptions(isJapanese) as form}
					<label><input type="radio" name="composition-form" value={form.id} bind:group={selected} disabled={busy} />
						<CompositionFigure figure={form.id} size={28} />
						<span><strong>{form.name}</strong>{#if form.id === compositionForm} ({t().compositionFormCurrent}){/if}<br />{form.description}</span>
					</label>
				{/each}
			</div>
			<div class="refine-actions refine-paint-actions">
				<PaintButton onclick={() => onGenerateCandidates(selected, 1)} disabled={!resultAvailable || busy || refinementSession.hasUnsaved}>{t().refineSingleButton}</PaintButton>
				<PaintButton onclick={() => onGenerateCandidates(selected, 4)} disabled={!resultAvailable || busy || refinementSession.hasUnsaved}>{t().variationGridDefault}</PaintButton>
				{#if busy}<RunStatus label={t().refineGeneratingTask(refinementSession.gridTaskLabel)}
					progressDone={refinementSession.gridDone} progressTotal={refinementSession.gridTotal}
					elapsedMs={refinementSession.elapsedMs} progress={refinementSession.gridProgress}
					tokensIn={refinementSession.tokensIn} tokensOut={refinementSession.tokensOut}
					onStop={refinementSession.gridBusy && refinementSession.gridCanAbort ? () => refinementSession.abort() : null} />
					<VariationLanes states={refinementSession.gridSlots} labels={refinementSession.gridSlotLabels} />
				{/if}
			</div>
		</section></div>
	</div>
	<RefinementCandidateGrid {isJapanese} {refinementSession} {onSaveAndClose} {onDiscardAndClose} maxColumns={4}
		target={{ artworkUrl, aspectWidth: canvasAspectWidth, aspectHeight: canvasAspectHeight, composition: targetComposition }} />
</div></div>

<style>
	.form-options { display: grid; gap: 7px; font-size: var(--ui-font-size-12); }
	.form-options label { display: flex; align-items: start; gap: 6px; }
	.form-options label :global(.composition-figure) { color: var(--fg2); }
</style>
