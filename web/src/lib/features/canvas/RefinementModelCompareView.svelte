<script lang="ts">
	import { t } from '$lib/i18n/index.svelte';
	import ModelMetaCard from '$lib/components/ModelMetaCard.svelte';
	import PaintButton from '$lib/components/PaintButton.svelte';
	import RunStatus from '$lib/components/RunStatus.svelte';
	import Tooltip from '$lib/components/Tooltip.svelte';
	import WildToggle from '$lib/components/WildToggle.svelte';
	import type { createModelInspection } from '$lib/features/model-inspection/state.svelte';
	import type { RefinementSession } from '$lib/features/canvas/refinement-session.svelte';
	import { svgImage } from '$lib/svgImage';

	type ModelInspection = ReturnType<typeof createModelInspection>;
	type Props = {
		isJapanese: boolean;
		resultAvailable: boolean;
		canvasAspectWidth: number;
		canvasAspectHeight: number;
		refinementSession: RefinementSession;
		modelInspection: ModelInspection;
		activeComparisonItem: { svg: string } | null;
		refineWildValue: boolean;
		refineWildInherited: boolean;
		onSetRefineWild: (value: boolean | null) => void;
	};

	let {
		isJapanese,
		resultAvailable,
		canvasAspectWidth,
		canvasAspectHeight,
		refinementSession,
		modelInspection,
		activeComparisonItem,
		refineWildValue,
		refineWildInherited,
		onSetRefineWild
	}: Props = $props();
</script>

	<div class="compare-panel">
	<div class="compare-head">
		<!-- One box, so `space-between` puts the settings at the left and the
		     action at the right instead of stranding the switch between them. -->
		<div class="compare-head-settings"><WildToggle value={refineWildValue} {isJapanese} inherited={refineWildInherited} onSelect={(next) => onSetRefineWild(next)} /></div>
		<div class="compare-action-wrap" class:running={modelInspection.busy}>
			{#if modelInspection.busy}
				<RunStatus
					variant="inline"
					label={t().modelCompareBusy}
					model={modelInspection.currentModel}
					elapsedMs={modelInspection.elapsedMs}
					tokensIn={modelInspection.tokensIn}
					tokensOut={modelInspection.tokensOut}
					onStop={modelInspection.abort}
				/>
			{:else}
				<Tooltip placement="bottom-left" text={t().tooltipModelCompare}><PaintButton onclick={modelInspection.run} disabled={!resultAvailable || refinementSession.gridBusy || modelInspection.selectedModels.length === 0}>{t().modelCompareButton}</PaintButton></Tooltip>
			{/if}
		</div>
	</div>
	<div class="compare-mode-tabs" role="tablist" aria-label={t().modelCompareModeLabel}>
		<button class:active={modelInspection.compareMode === 'common'} onclick={() => modelInspection.setCompareMode('common')}>{t().modelCompareModeCommon}</button>
		<button class:active={modelInspection.compareMode === 'stage1_fixed'} onclick={() => modelInspection.setCompareMode('stage1_fixed')}>{t().modelCompareModeStage1Fixed}</button>
		<button class:active={modelInspection.compareMode === 'stage2_fixed'} onclick={() => modelInspection.setCompareMode('stage2_fixed')}>{t().modelCompareModeStage2Fixed}</button>
	</div>
	{#if modelInspection.compareMode !== 'common'}
		<label class="compare-fixed-model"><span>{modelInspection.compareMode === 'stage1_fixed' ? t().modelCompareFixedStage1 : t().modelCompareFixedStage2}</span><select value={modelInspection.compareFixedModel} disabled={modelInspection.busy} onchange={(event) => modelInspection.setCompareFixedModel(event.currentTarget.value)}>{#each modelInspection.choices as choice (choice.id)}<option value={choice.id}>{choice.label} · {choice.providerLabel}</option>{/each}</select></label>
	{/if}
	<div class="model-choice-grid" aria-label={t().modelCompareModelSelectLabel}>
		{#each modelInspection.choices as choice (choice.id)}
			{@const blocked = modelInspection.isChoiceBlocked(choice.id)}
			{@const checked = modelInspection.selectedModels.includes(choice.id)}
			{@const failed = !!modelInspection.failedModels[choice.id]}
			{@const choiceExtra = [blocked ? t().modelCompareTargetDisabledTooltip : '', failed ? t().modelCompareFailedModel : ''].filter(Boolean).join(' · ')}
			<div class="model-metadata-hover">
				<label class="model-choice" class:checked={checked} class:target={blocked} class:failed={failed} class:disabled={blocked || (!checked && modelInspection.selectedModels.length >= 4)}>
					<input type="checkbox" checked={checked} disabled={modelInspection.busy || blocked || (!checked && modelInspection.selectedModels.length >= 4)} onchange={() => modelInspection.toggleModel(choice.id)} />
					<span><strong>{choice.label}</strong><small>{choice.providerLabel}{blocked ? ` · ${t().modelCompareTargetModel}` : ''}{failed ? ` · ${t().modelCompareFailedModel}` : ''}</small></span>
				</label>
				<ModelMetaCard model={choice.model} {isJapanese} extra={choiceExtra} purpose="llm" />
			</div>
		{/each}
	</div>
	<div class="model-choice-count">{t().modelCompareSelectedCount(modelInspection.selectedModels.length, 4)}</div>
	{#if modelInspection.status}<div class="variation-grid-status">{modelInspection.status}</div>{/if}
	<div class="model-compare-stage" class:busy={modelInspection.busy}>
		<div class="model-target-card"><div class="comparison-label">{t().modelCompareTargetTitle}</div><div class="comparison-art" style="aspect-ratio: {canvasAspectWidth} / {canvasAspectHeight};">{#if activeComparisonItem}<img use:svgImage={activeComparisonItem.svg} alt="" />{/if}</div><div class="model-target-meta">Stage 1: {modelInspection.targetStage1Model}<br />Stage 2: {modelInspection.targetStage2Model}</div></div>
		<div class="model-results-column">
			{#if modelInspection.results.length > 0}
				<div class="model-inspection-grid">
					{#each modelInspection.results as item (item.id)}
						<div class="model-inspection-card" class:saved={!!item.savedHistoryId}>
							<div class="comparison-label">{item.label}</div>
							<div class="model-comparison-art-wrap">
								<div class="comparison-art" style="aspect-ratio: {canvasAspectWidth} / {canvasAspectHeight};"><img use:svgImage={item.svg} alt="" /></div>
								<button
									class="variation-select model-adopt-select"
									class:selected={!!item.savedHistoryId}
									type="button"
									disabled={item.saving || !!item.savedHistoryId}
									onclick={() => modelInspection.saveResult(item)}
									title={item.saving ? t().modelCompareSaving : item.savedHistoryId ? t().modelCompareAdopted : t().modelCompareAdoptTooltip}
									aria-label={item.saving ? t().modelCompareSaving : item.savedHistoryId ? t().modelCompareAdopted : t().modelCompareAdoptTooltip}
								>{item.saving ? '…' : item.savedHistoryId ? '✓' : '+'}</button>
							</div>
							<div class="model-result-actions">
								<Tooltip text={item.starred ? t().starOn : t().modelCompareStarTooltip}>
									<button class="model-result-star" class:starred={!!item.starred} type="button" disabled={item.saving} onclick={() => modelInspection.saveResult(item, { star: true })} aria-label={item.starred ? t().starOn : t().starOff}>{item.starred ? '★' : '☆'}</button>
								</Tooltip>
							</div>
							<pre>{item.ddl}</pre>
						</div>
					{/each}
				</div>
			{/if}
		</div>
	</div>
	</div>
