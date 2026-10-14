<script lang="ts">
	import { t } from '$lib/i18n/index.svelte';
	import PaintButton from '$lib/components/PaintButton.svelte';
	import RunStatus from '$lib/components/RunStatus.svelte';
	import VariationLanes from '$lib/components/VariationLanes.svelte';
	import RefinementCandidateGrid from './RefinementCandidateGrid.svelte';
	import type { RefinementSession } from '$lib/features/canvas/refinement-session.svelte';

	// The work's touches changed (the author, 2026-10-14): every sentence on one
	// tool, the default, or a different tool for each sentence. Placement, color and
	// ground stay the parent's.
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
						<div class="refine-selection-hint">{t().toolChangeHint}</div>
					</div>
					<div class="recompose-mode-options" role="radiogroup" aria-label={t().workActionTool}>
						<label><input type="radio" name="tool-mode" value="uniform" checked={refinementSession.toolMode === 'uniform'} onchange={() => refinementSession.setToolMode('uniform')} disabled={busy} />{t().toolChangeUniform}</label>
						<label><input type="radio" name="tool-mode" value="per_sentence" checked={refinementSession.toolMode === 'per_sentence'} onchange={() => refinementSession.setToolMode('per_sentence')} disabled={busy} />{t().toolChangePerSentence}</label>
					</div>
				</section>
				<section class="refine-action-section">
					<div class="refine-actions refine-paint-actions">
						<!-- Nothing is drawn until this is pressed; each press replaces the
						     options shown with four new ones in the chosen way. -->
						<div class="refine-action-wrap">
							<PaintButton onclick={onGenerateCandidates} disabled={!resultAvailable || busy}>{t().variationGridDefault}</PaintButton>
						</div>
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
		<RefinementCandidateGrid {isJapanese} {refinementSession} {onSaveAndClose} {onDiscardAndClose} maxColumns={4} placeholder={t().toolChangePlaceholder} />
	</div>
</div>
