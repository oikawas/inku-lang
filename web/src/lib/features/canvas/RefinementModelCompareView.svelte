<script lang="ts">
	import { t } from '$lib/i18n/index.svelte';
	import ModelMetaCard from '$lib/components/ModelMetaCard.svelte';
	import PaintButton from '$lib/components/PaintButton.svelte';
	import RunStatus from '$lib/components/RunStatus.svelte';
	import Tooltip from '$lib/components/Tooltip.svelte';
	import VariationLanes from '$lib/components/VariationLanes.svelte';
	import WildToggle from '$lib/components/WildToggle.svelte';
	import RefinementCandidateGrid from './RefinementCandidateGrid.svelte';
	import type { createModelInspection } from '$lib/features/model-inspection/state.svelte';
	import type { RefinementSession } from '$lib/features/canvas/refinement-session.svelte';

	type ModelInspection = ReturnType<typeof createModelInspection>;
	type Props = {
		isJapanese: boolean;
		resultAvailable: boolean;
		artworkUrl: string | null;
		seedSummary: string;
		canvasAspectWidth: number;
		canvasAspectHeight: number;
		refinementSession: RefinementSession;
		modelInspection: ModelInspection;
		refineWildValue: boolean;
		refineWildInherited: boolean;
		onSetRefineWild: (value: boolean | null) => void;
		/** Draws the work with each picked model, as options like the color change's. */
		onGenerateModelCandidates: () => void | Promise<void>;
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
		modelInspection,
		refineWildValue,
		refineWildInherited,
		onSetRefineWild,
		onGenerateModelCandidates,
		onSaveAndClose,
		onDiscardAndClose
	}: Props = $props();

	const busy = $derived(refinementSession.busy || refinementSession.gridBusy);
</script>

<div class="refine-panel">
	<!-- The picker spans the dialog, as it did before the options: the models
	     sit side by side rather than in a column the button hides below. -->
	<div class="compare-head">
		<div class="compare-head-settings"><WildToggle value={refineWildValue} {isJapanese} inherited={refineWildInherited} onSelect={(next) => onSetRefineWild(next)} /></div>
		<div class="compare-action-wrap">
			<Tooltip placement="bottom-left" text={t().tooltipModelCompare}>
				<PaintButton onclick={onGenerateModelCandidates} disabled={busy || !resultAvailable || modelInspection.drawableModels().length === 0}>
					{t().modelCompareButton}
				</PaintButton>
			</Tooltip>
		</div>
	</div>
	<div class="model-choice-grid" aria-label={t().modelCompareModelSelectLabel}>
		{#each modelInspection.choices as choice (choice.id)}
			{@const blocked = modelInspection.isChoiceBlocked(choice.id)}
			{@const checked = modelInspection.selectedModels.includes(choice.id)}
			{@const failed = !!modelInspection.failedModels[choice.id]}
			{@const full = !checked && modelInspection.selectedModels.length >= 4}
			{@const choiceExtra = [blocked ? t().modelCompareTargetDisabledTooltip : '', failed ? t().modelCompareFailedModel : ''].filter(Boolean).join(' · ')}
			<div class="model-metadata-hover">
				<label class="model-choice" class:checked={checked} class:target={blocked} class:failed={failed} class:disabled={blocked || full}>
					<input type="checkbox" checked={checked} disabled={busy || blocked || full} onchange={() => modelInspection.toggleModel(choice.id)} />
					<span><strong>{choice.label}</strong><small>{choice.providerLabel}{blocked ? ` · ${t().modelCompareTargetModel}` : ''}{failed ? ` · ${t().modelCompareFailedModel}` : ''}</small></span>
				</label>
				<ModelMetaCard model={choice.model} {isJapanese} extra={choiceExtra} purpose="llm" />
			</div>
		{/each}
	</div>
	<div class="model-choice-count">{t().modelCompareSelectedCount(modelInspection.selectedModels.length, 4)}</div>
	{#if modelInspection.status}<div class="variation-grid-status">{modelInspection.status}</div>{/if}
	<div class="refine-stage">
		<div class="refine-target-column">
			<div class="refine-target-card">
				<div class="comparison-label">{t().modelCompareTargetTitle}</div>
				<div class="comparison-art" style="aspect-ratio: {canvasAspectWidth} / {canvasAspectHeight};">{#if artworkUrl}<img class="canvas-art" src={artworkUrl} alt="" />{/if}</div>
				<div class="model-target-meta">{modelInspection.targetModel}{#if resultAvailable}<br />{seedSummary}{/if}</div>
			</div>
			<div class="refine-target-controls">
				<div class="refine-actions refine-paint-actions">
					<div class="refine-cost-indicator" aria-live="polite">
						<svg viewBox="0 0 24 24" aria-hidden="true">
							<circle cx="12" cy="12" r="8.5" />
							<path d="M12 7.5v5l3 2" />
						</svg>
						<span>{t().refineCostReading}</span>
					</div>
					{#if busy}
						<RunStatus
							label={t().refineGeneratingTask(refinementSession.gridTaskLabel)}
							progressDone={refinementSession.gridDone}
							progressTotal={refinementSession.gridTotal}
							model={refinementSession.gridSlotLabels.filter(Boolean).join(' · ')}
							elapsedMs={refinementSession.elapsedMs}
							tokensIn={refinementSession.tokensIn}
							tokensOut={refinementSession.tokensOut}
							onStop={refinementSession.gridBusy && refinementSession.gridCanAbort ? () => refinementSession.abort() : null}
						/>
						{#if refinementSession.gridBusy}
							<VariationLanes states={refinementSession.gridSlots} labels={refinementSession.gridSlotLabels} named />
						{/if}
					{/if}
				</div>
			</div>
		</div>
		<RefinementCandidateGrid {isJapanese} {refinementSession} {onSaveAndClose} {onDiscardAndClose} placeholder={t().modelChangePlaceholder} />
	</div>
</div>
