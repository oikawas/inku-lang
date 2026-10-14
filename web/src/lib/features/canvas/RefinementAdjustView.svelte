<script lang="ts">
	import { t } from '$lib/i18n/index.svelte';
	import ModelCardPicker from '$lib/components/ModelCardPicker.svelte';
	import PaintButton from '$lib/components/PaintButton.svelte';
	import RunStatus from '$lib/components/RunStatus.svelte';
	import Tooltip from '$lib/components/Tooltip.svelte';
	import VariationLanes from '$lib/components/VariationLanes.svelte';
	import WildToggle from '$lib/components/WildToggle.svelte';
	import type { Provider, ProviderGroup } from '$lib/models';
	import RefinementCandidateGrid from './RefinementCandidateGrid.svelte';
	import type {
		RefinementSession,
		RefineKind
	} from '$lib/features/canvas/refinement-session.svelte';

	type Props = {
		layoutOnly?: boolean;
		isJapanese: boolean;
		resultAvailable: boolean;
		artworkUrl: string | null;
		seedSummary: string;
		canvasAspectWidth: number;
		canvasAspectHeight: number;
		refinementSession: RefinementSession;
		statusDdlOrigin: boolean;
		statusDescriptionLocked: boolean;
		statusStage1Model: string;
		statusStage2Model: string;
		refineDrawingModelId: string;
		refineDrawingModelGroups: ProviderGroup[];
		refineWildValue: boolean;
		refineWildInherited: boolean;
		onGenerateVariationCandidates: (kind: RefineKind, count: 1 | 4) => void | Promise<void>;
		/** Save the chosen options, then leave; the rest are dropped. */
		onSaveAndClose: () => void | Promise<void>;
		/** Drop every unsaved option, then leave. */
		onDiscardAndClose: () => void | Promise<void>;
		onSelectRefineDrawingModel: (provider: Provider, model: string) => void | Promise<void>;
		onSetRefineWild: (value: boolean | null) => void;
	};

	let {
		layoutOnly = false,
		isJapanese,
		resultAvailable,
		artworkUrl,
		seedSummary,
		canvasAspectWidth,
		canvasAspectHeight,
		refinementSession,
		statusDdlOrigin,
		statusDescriptionLocked,
		statusStage1Model,
		statusStage2Model,
		refineDrawingModelId,
		refineDrawingModelGroups,
		refineWildValue,
		refineWildInherited,
		onGenerateVariationCandidates,
		onSaveAndClose,
		onDiscardAndClose,
		onSelectRefineDrawingModel,
		onSetRefineWild
	}: Props = $props();

	// The layout dialog draws layout options; the drawing parameters draw
	// another reading, the one element left there once words no longer chose
	// the touch (removed 2026-10-14, the author).
	const activeKind = $derived<RefineKind>(layoutOnly ? 'layout' : 'reading');
	const costLabel = $derived(activeKind === 'reading' ? t().refineCostReading : t().refineCostLayout);
	// A work its DDL holds, or one drawn from DDL, has no reading to draw again.
	const readingHeld = $derived(!layoutOnly && (statusDdlOrigin || statusDescriptionLocked));
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
						{#if layoutOnly}
							<Tooltip placement="bottom" text={t().tooltipCanvasVaryComposition}>
								<span class="refine-section-title refine-choice-label">
									<strong>{t().canvasVaryComposition}</strong>
									<span class="refine-info-mark" aria-hidden="true">i</span>
								</span>
							</Tooltip>
						{:else}
							<Tooltip placement="bottom" text={readingHeld ? t().descriptionLockedReason : t().tooltipCanvasVaryInterpretation}>
								<span class="refine-section-title refine-choice-label">
									<strong>{t().canvasVaryInterpretation}</strong>
									<span class="refine-info-mark" aria-hidden="true">i</span>
								</span>
							</Tooltip>
							{#if readingHeld}<div class="refine-selection-hint">{t().descriptionLockedReason}</div>{/if}
						{/if}
					</div>
					{#if activeKind === 'layout'}
						<div class="recompose-mode-options" role="radiogroup" aria-label={t().canvasVaryComposition}>
							<label><input type="radio" name="recompose-mode" value="principled" checked={refinementSession.recomposeMode === 'principled'} onchange={() => refinementSession.setRecomposeMode('principled')} disabled={refinementSession.busy || refinementSession.gridBusy} />{t().recomposeByPrinciple}</label>
							<label><input type="radio" name="recompose-mode" value="chance" checked={refinementSession.recomposeMode === 'chance'} onchange={() => refinementSession.setRecomposeMode('chance')} disabled={refinementSession.busy || refinementSession.gridBusy} />{t().recomposeByChance}</label>
						</div>
					{/if}
				</section>
				<section class="refine-action-section">
					<div class="refine-actions refine-paint-actions">
						<Tooltip text={t().tooltipRefineSingle}>
							<div class="refine-action-wrap">
								<PaintButton
								onclick={() => onGenerateVariationCandidates(activeKind, 1)}
								disabled={!resultAvailable || readingHeld || refinementSession.busy || refinementSession.gridBusy}
								>
									{t().refineSingleButton}
								</PaintButton>
							</div>
						</Tooltip>
						<Tooltip text={t().tooltipVariationGridDefault}>
							<div class="refine-action-wrap">
								<PaintButton
								onclick={() => onGenerateVariationCandidates(activeKind, 4)}
								disabled={!resultAvailable || readingHeld || refinementSession.busy || refinementSession.gridBusy}
								>
									{t().variationGridDefault}
								</PaintButton>
							</div>
						</Tooltip>
						{#if costLabel}
							<div class="refine-cost-indicator" aria-live="polite">
								<svg viewBox="0 0 24 24" aria-hidden="true">
									<circle cx="12" cy="12" r="8.5" />
									<path d="M12 7.5v5l3 2" />
								</svg>
								<span>{costLabel}</span>
							</div>
						{/if}
						<!-- Same picker and same semantics as DdlEditorDialog: it rewrites
						     the saved default, which the status row above shows. Stage 1 is
						     not touched here; the model-comparison view changes that. -->
						<div class="refine-model-row">
							<ModelCardPicker
								label={t().ddlDialogDrawingModel}
								selectedModel={refineDrawingModelId}
								providerGroups={refineDrawingModelGroups}
								onSelect={onSelectRefineDrawingModel}
							/>
						</div>
						<div class="refine-settings-row"><WildToggle value={refineWildValue} {isJapanese} inherited={refineWildInherited} onSelect={(next) => onSetRefineWild(next)} /></div>

					{#if refinementSession.busy || refinementSession.gridBusy}
						<RunStatus
							label={t().refineGeneratingTask(refinementSession.gridTaskLabel)}
							progressDone={refinementSession.gridDone}
							progressTotal={refinementSession.gridTotal}
							stage1Model={statusStage1Model}
							stage2Model={statusStage2Model}
							elapsedMs={refinementSession.elapsedMs}
							tokensIn={refinementSession.tokensIn}
							tokensOut={refinementSession.tokensOut}
							onStop={refinementSession.gridBusy && refinementSession.gridCanAbort ? () => refinementSession.abort() : null}
						/>
						<!-- The candidates are drawn side by side, so the waiting
						     is shown side by side too. -->
						{#if refinementSession.gridBusy}
							<VariationLanes states={refinementSession.gridSlots} labels={refinementSession.gridSlotLabels} />
						{/if}
					{/if}
					</div>
				</section>
			</div>
		</div>
		<RefinementCandidateGrid {isJapanese} {refinementSession} {onSaveAndClose} {onDiscardAndClose} />
	</div>
</div>
