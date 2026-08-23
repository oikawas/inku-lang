<script lang="ts">
	import { t } from '$lib/i18n/index.svelte';
	import ModelCardPicker from '$lib/components/ModelCardPicker.svelte';
	import PaintButton from '$lib/components/PaintButton.svelte';
	import RunStatus from '$lib/components/RunStatus.svelte';
	import Tooltip from '$lib/components/Tooltip.svelte';
	import VariationLanes from '$lib/components/VariationLanes.svelte';
	import WildToggle from '$lib/components/WildToggle.svelte';
	import type { Provider, ProviderGroup } from '$lib/models';
	import type {
		RefinementSession,
		RefineKind,
		VariationAmplitude,
		VariationCandidate
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
		refineKind: RefineKind;
		variationAmplitude: VariationAmplitude;
		touchSeedText: string;
		statusStage1Model: string;
		statusStage2Model: string;
		refineDrawingModelId: string;
		refineDrawingModelGroups: ProviderGroup[];
		refineWildValue: boolean;
		refineWildInherited: boolean;
		onSetRefineKind: (kind: RefineKind) => void;
		onGenerateVariationCandidates: (kind: RefineKind, count: 1 | 4, touchWords?: string, amplitude?: VariationAmplitude) => void | Promise<void>;
		onSaveSelectedVariationCandidates: () => void | Promise<void>;
		onShowVariationCandidate: (candidate: VariationCandidate) => void;
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
		refineKind,
		variationAmplitude = $bindable('medium'),
		touchSeedText = $bindable(''),
		statusStage1Model,
		statusStage2Model,
		refineDrawingModelId,
		refineDrawingModelGroups,
		refineWildValue,
		refineWildInherited,
		onSetRefineKind,
		onGenerateVariationCandidates,
		onSaveSelectedVariationCandidates,
		onShowVariationCandidate,
		onSelectRefineDrawingModel,
		onSetRefineWild
	}: Props = $props();

	const costLabel = $derived(
		refineKind === 'reading'
			? t().refineCostReading
			: refineKind === 'layout'
				? t().refineCostLayout
				: refineKind === 'color'
					? t().refineCostColor
					: refineKind === 'variation'
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
							<label class="model-choice" class:checked={refineKind === 'reading'}>
								<input type="radio" name="refine-kind" value="reading" checked={refineKind === 'reading'} onchange={() => onSetRefineKind('reading')} disabled={refinementSession.busy || refinementSession.gridBusy} />
								<Tooltip placement="bottom" text={t().tooltipCanvasVaryInterpretation}>
									<span class="refine-choice-label">
										<strong>{t().canvasVaryInterpretation}</strong>
										<span class="refine-info-mark" aria-hidden="true">i</span>
									</span>
								</Tooltip>
							</label>
						{/if}
						<label class="model-choice" class:checked={refineKind === 'color'}>
							<input type="radio" name="refine-kind" value="color" checked={refineKind === 'color'} onchange={() => onSetRefineKind('color')} disabled={refinementSession.busy || refinementSession.gridBusy} />
							<Tooltip placement="bottom" text={t().tooltipCanvasVaryColor}>
								<span class="refine-choice-label">
									<strong>{t().canvasVaryColor}</strong>
									<span class="refine-info-mark" aria-hidden="true">i</span>
								</span>
							</Tooltip>
						</label>
						<label class="model-choice" class:checked={refineKind === 'variation'}>
							<input type="radio" name="refine-kind" value="variation" checked={refineKind === 'variation'} onchange={() => onSetRefineKind('variation')} disabled={refinementSession.busy || refinementSession.gridBusy} />
							<Tooltip placement="bottom" text={t().tooltipVariation}>
								<span class="refine-choice-label">
									<strong>{t().variationRadioLabel}</strong>
									<span class="refine-info-mark" aria-hidden="true">i</span>
								</span>
							</Tooltip>
						</label>
						{#if refineKind === 'variation'}
							<div class="variation-amplitude-field">
								<div class="model-choice-grid variation-amplitude-grid" role="radiogroup" aria-label={t().variationTitle}>
									{#each [['small', t().variationSmall, t().variationTooltipSmall, 'bottom-right'], ['medium', t().variationMedium, t().variationTooltipMedium, 'bottom'], ['large', t().variationLarge, t().variationTooltipLarge, 'bottom-left']] as [level, label, hint, place] (level)}
										<label class="model-choice" class:checked={variationAmplitude === level}>
											<input type="radio" name="variation-amplitude" value={level} checked={variationAmplitude === level} onchange={() => (variationAmplitude = level as VariationAmplitude)} disabled={refinementSession.busy || refinementSession.gridBusy} />
											<Tooltip placement={place as 'bottom' | 'bottom-left' | 'bottom-right'} text={hint}>
												<span class="refine-choice-label">
													<strong>{label}</strong>
													<span class="refine-info-mark" aria-hidden="true">i</span>
												</span>
											</Tooltip>
										</label>
									{/each}
								</div>
							</div>
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
								onclick={() => onGenerateVariationCandidates(refineKind, 1, refineKind === 'touch' ? touchSeedText : undefined, refineKind === 'variation' ? variationAmplitude : undefined)}
								disabled={!resultAvailable || refinementSession.busy || refinementSession.gridBusy || (refineKind === 'touch' && !touchSeedText.trim())}
								>
									{t().refineSingleButton}
								</PaintButton>
							</div>
						</Tooltip>
						<Tooltip text={t().tooltipVariationGridDefault}>
							<div class="refine-action-wrap">
								<PaintButton
								onclick={() => onGenerateVariationCandidates(refineKind, 4, undefined, refineKind === 'variation' ? variationAmplitude : undefined)}
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
		<div class="refine-workspace">
			<section class="refine-action-section refine-candidates-section">
				{#if refinementSession.candidates.length > 0}
					<div class="refine-actions refine-save-actions">
						<Tooltip placement="top-left" text={t().tooltipVariationGridSaveSelected}>
							<button class="refine-save-btn" onclick={onSaveSelectedVariationCandidates} disabled={refinementSession.busy || refinementSession.gridBusy || refinementSession.candidates.every((candidate) => !candidate.selected)}>
								{t().variationGridSaveSelected}
							</button>
						</Tooltip>
					</div>
					<div class="variation-grid" style="--variation-cols: {refinementSession.candidates.length > 1 ? 2 : 1};">
						{#each refinementSession.candidates as candidate (candidate.id)}
							<div class="variation-card-wrap">
								<button class="variation-card" class:selected={candidate.selected} class:saved={candidate.saved} onclick={() => onShowVariationCandidate(candidate)} type="button">
									<span class="variation-card-art">{@html candidate.result.svg}</span>
									<span class="variation-card-meta">
										<span>{candidate.label}</span>
										<span>r {candidate.result.render_seed ?? "-"} / v {candidate.result.composition_seed ?? t().seedBaseLabel}{candidate.result.interpretation_seed ? ` / i ${candidate.result.interpretation_seed.slice(0, 8)}` : ""}</span>
										{#if candidate.result.variation_moved_axes?.length}
											<span class="variation-card-moved">
												{#each candidate.result.variation_moved_axes as moved (moved.axis)}
													<span class="variation-moved-axis">{t().variationAxis(moved.axis)} {moved.to}</span>
												{/each}
											</span>
										{/if}
									</span>
								</button>
							{#if refinementSession.gridIncludesReading}<pre class="variation-ddl-popup">{candidate.result.ddl}</pre>{/if}
								<button
									class="variation-select"
									class:selected={candidate.selected}
									class:saved={candidate.saved}
								disabled={candidate.saved}
								title={candidate.saved ? (isJapanese ? '保存済み' : 'Saved') : undefined}
								aria-label={candidate.saved ? (isJapanese ? '保存済み' : 'Saved') : undefined}
								onclick={() => refinementSession.toggleCandidate(candidate.id)}
								type="button"
								>{candidate.saved ? "✔" : candidate.selected ? "✓" : "+"}</button>
							</div>
						{/each}
					</div>
				{:else}
					<div class="variation-grid-placeholder">
						<span>{t().refineCandidatePlaceholder}</span>
					</div>
				{/if}
			</section>
			{#if refinementSession.status}<div class="variation-grid-status">{refinementSession.status}</div>{/if}
		</div>
	</div>
</div>
