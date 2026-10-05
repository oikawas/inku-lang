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
		isJapanese: boolean;
		resultAvailable: boolean;
		artworkUrl: string | null;
		seedSummary: string;
		canvasAspectWidth: number;
		canvasAspectHeight: number;
		refinementSession: RefinementSession;
		statusDdlOrigin: boolean;
		statusDescriptionLocked: boolean;
		refineKind: RefineKind;
		touchSeedText: string;
		statusStage1Model: string;
		statusStage2Model: string;
		refineDrawingModelId: string;
		refineDrawingModelGroups: ProviderGroup[];
		refineWildValue: boolean;
		refineWildInherited: boolean;
		onSetRefineKind: (kind: RefineKind) => void;
		onGenerateVariationCandidates: (kind: RefineKind, count: 1 | 4, touchWords?: string) => void | Promise<void>;
		/** Save the chosen options, then leave; the rest are dropped. */
		onSaveAndClose: () => void | Promise<void>;
		/** Drop every unsaved option, then leave. */
		onDiscardAndClose: () => void | Promise<void>;
		onSelectRefineDrawingModel: (provider: Provider, model: string) => void | Promise<void>;
		onSetRefineWild: (value: boolean | null) => void;
	};

	let {
		isJapanese,
		resultAvailable,
		artworkUrl,
		seedSummary,
		canvasAspectWidth,
		canvasAspectHeight,
		refinementSession,
		statusDdlOrigin,
		statusDescriptionLocked,
		refineKind,
		touchSeedText = $bindable(''),
		statusStage1Model,
		statusStage2Model,
		refineDrawingModelId,
		refineDrawingModelGroups,
		refineWildValue,
		refineWildInherited,
		onSetRefineKind,
		onGenerateVariationCandidates,
		onSaveAndClose,
		onDiscardAndClose,
		onSelectRefineDrawingModel,
		onSetRefineWild
	}: Props = $props();

	const costLabel = $derived(
		refineKind === 'reading'
			? t().refineCostReading
			: refineKind === 'layout'
				? t().refineCostLayout
				: t().refineCostTouch
	);
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
						<div class="refine-section-title">{t().refineSingleTitle}</div>
						<div class="refine-selection-hint">{t().refineSingleSelectionHint}</div>
					</div>
					<div class="model-choice-grid" role="radiogroup" aria-label={t().refineSingleSelectionHint}>
						<label class="model-choice" class:checked={refineKind === 'layout'}>
							<input type="radio" name="refine-kind" value="layout" checked={refineKind === 'layout'} onchange={() => onSetRefineKind('layout')} disabled={refinementSession.busy || refinementSession.gridBusy} />
							<Tooltip placement="bottom" text={t().tooltipCanvasVaryComposition}>
								<span class="refine-choice-label">
									<strong>{t().canvasVaryComposition}</strong>
									<span class="refine-info-mark" aria-hidden="true">i</span>
								</span>
							</Tooltip>
						</label>
						{#if !statusDdlOrigin}
							<!-- Held by its edited DDL: another reading is shown, not offered. -->
							<label class="model-choice" class:checked={refineKind === 'reading'} class:held={statusDescriptionLocked}>
								<input type="radio" name="refine-kind" value="reading" checked={refineKind === 'reading'} onchange={() => onSetRefineKind('reading')} disabled={statusDescriptionLocked || refinementSession.busy || refinementSession.gridBusy} />
								<Tooltip placement={statusDescriptionLocked ? 'right' : 'bottom'} text={statusDescriptionLocked ? t().descriptionLockedReason : t().tooltipCanvasVaryInterpretation}>
									<span class="refine-choice-label">
										<strong>{t().canvasVaryInterpretation}</strong>
										<span class="refine-info-mark" aria-hidden="true">i</span>
									</span>
								</Tooltip>
							</label>
						{/if}
						<label class="model-choice" class:checked={refineKind === 'touch'}>
							<input type="radio" name="refine-kind" value="touch" checked={refineKind === 'touch'} onchange={() => onSetRefineKind('touch')} disabled={refinementSession.busy || refinementSession.gridBusy} />
							<Tooltip placement="bottom" text={t().tooltipCanvasVaryPerformance}>
								<span class="refine-choice-label">
									<strong>{t().canvasVaryPerformance}</strong>
									<span class="refine-info-mark" aria-hidden="true">i</span>
								</span>
							</Tooltip>
						</label>
					</div>
					{#if refineKind === 'layout'}
						<div class="recompose-mode-options" role="radiogroup" aria-label={t().canvasVaryComposition}>
							<label><input type="radio" name="recompose-mode" value="principled" checked={refinementSession.recomposeMode === 'principled'} onchange={() => refinementSession.setRecomposeMode('principled')} disabled={refinementSession.busy || refinementSession.gridBusy} />{t().recomposeByPrinciple}</label>
							<label><input type="radio" name="recompose-mode" value="chance" checked={refinementSession.recomposeMode === 'chance'} onchange={() => refinementSession.setRecomposeMode('chance')} disabled={refinementSession.busy || refinementSession.gridBusy} />{t().recomposeByChance}</label>
						</div>
					{/if}
					{#if refineKind === 'touch'}
						<label class="touch-seed-field">
							<input bind:value={touchSeedText} aria-label={t().canvasVaryPerformance} placeholder={isJapanese ? 'タッチへ託す言葉' : 'Words for the touch'} disabled={refinementSession.busy || refinementSession.gridBusy} />
							<small>{isJapanese ? '同じ言葉は同じタッチ(Seed)になります。1案だけ生成可能です。' : 'The same words produce the same touch (Seed). Only one option can be made.'}</small>
						</label>
					{/if}
				</section>
				<section class="refine-action-section">
					<div class="refine-actions refine-paint-actions">
						<Tooltip text={t().tooltipRefineSingle}>
							<div class="refine-action-wrap">
								<PaintButton
								onclick={() => onGenerateVariationCandidates(refineKind, 1, refineKind === 'touch' ? touchSeedText : undefined)}
								disabled={!resultAvailable || refinementSession.busy || refinementSession.gridBusy || (refineKind === 'touch' && !touchSeedText.trim())}
								>
									{t().refineSingleButton}
								</PaintButton>
							</div>
						</Tooltip>
						<Tooltip text={t().tooltipVariationGridDefault}>
							<div class="refine-action-wrap">
								<PaintButton
								onclick={() => onGenerateVariationCandidates(refineKind, 4, undefined)}
								disabled={!resultAvailable || refinementSession.busy || refinementSession.gridBusy || refineKind === 'touch'}
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
