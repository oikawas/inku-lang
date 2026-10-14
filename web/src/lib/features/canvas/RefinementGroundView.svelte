<script lang="ts">
	import { t } from '$lib/i18n/index.svelte';
	import PaintButton from '$lib/components/PaintButton.svelte';
	import RunStatus from '$lib/components/RunStatus.svelte';
	import VariationLanes from '$lib/components/VariationLanes.svelte';
	import RefinementCandidateGrid from './RefinementCandidateGrid.svelte';
	import type { RefinementSession } from '$lib/features/canvas/refinement-session.svelte';

	// The work's ground swapped for each named support it is not on (the author,
	// 2026-10-14): placement, color and touch stay the parent's.
	type Props = {
		isJapanese: boolean;
		resultAvailable: boolean;
		artworkUrl: string | null;
		seedSummary: string;
		canvasAspectWidth: number;
		canvasAspectHeight: number;
		refinementSession: RefinementSession;
		onGenerateCandidates: () => void | Promise<void>;
		onSaveAndClose: () => void | Promise<void>;
		onDiscardAndClose: () => void | Promise<void>;
	};

	let {
		isJapanese,
		resultAvailable,
		artworkUrl,
		seedSummary,
		canvasAspectWidth,
		canvasAspectHeight,
		refinementSession,
		onGenerateCandidates,
		onSaveAndClose,
		onDiscardAndClose
	}: Props = $props();

	const busy = $derived(refinementSession.busy || refinementSession.gridBusy);
	const current = $derived(refinementSession.groundCurrent);
</script>

<div class="refine-panel">
	<div class="refine-stage">
		<div class="refine-target-column">
			<div class="refine-target-card">
				<div class="comparison-label">{t().refineTargetTitle}</div>
				<div class="comparison-art" style="aspect-ratio: {canvasAspectWidth} / {canvasAspectHeight};">{#if artworkUrl}<img class="canvas-art" src={artworkUrl} alt="" />{/if}</div>
				{#if resultAvailable}<div class="model-target-meta">{seedSummary}</div>{/if}
			</div>
			<div class="refine-target-controls">
				<section class="refine-action-section">
					<div class="refine-section-head">
						{#if current}<div class="refine-section-title">{t().groundChangeCurrent}: {current}</div>{/if}
						<div class="refine-selection-hint">{t().groundChangeHint}</div>
					</div>
					<div class="refine-actions refine-paint-actions">
						<!-- The options are drawn when the dialog opens; this redraws
						     them after a stop or a failure. -->
						{#if !busy && refinementSession.candidates.length === 0}
							<div class="refine-action-wrap">
								<PaintButton onclick={onGenerateCandidates} disabled={!resultAvailable}>{t().groundChangeDraw}</PaintButton>
							</div>
						{/if}
						<div class="refine-cost-indicator" aria-live="polite">
							<svg viewBox="0 0 24 24" aria-hidden="true">
								<circle cx="12" cy="12" r="8.5" />
								<path d="M12 7.5v5l3 2" />
							</svg>
							<span>{t().refineCostColor}</span>
						</div>
						{#if busy}
							<RunStatus
								label={t().refineGeneratingTask(refinementSession.gridTaskLabel)}
								progressDone={refinementSession.gridDone}
								progressTotal={refinementSession.gridTotal}
								elapsedMs={refinementSession.elapsedMs}
								tokensIn={refinementSession.tokensIn}
								tokensOut={refinementSession.tokensOut}
								onStop={refinementSession.gridBusy && refinementSession.gridCanAbort ? () => refinementSession.abort() : null}
							/>
							{#if refinementSession.gridBusy}
								<VariationLanes states={refinementSession.gridSlots} labels={refinementSession.gridSlotLabels} />
							{/if}
						{/if}
					</div>
				</section>
			</div>
		</div>
		<RefinementCandidateGrid {isJapanese} {refinementSession} {onSaveAndClose} {onDiscardAndClose} maxColumns={4} placeholder={t().groundChangePlaceholder} />
	</div>
</div>
