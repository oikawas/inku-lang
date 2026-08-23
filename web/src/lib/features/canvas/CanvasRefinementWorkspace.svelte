<script lang="ts">
	import { t } from '$lib/i18n/index.svelte';
	import ModelCardPicker from '$lib/components/ModelCardPicker.svelte';
	import ModelMetaCard from '$lib/components/ModelMetaCard.svelte';
	import PaintButton from '$lib/components/PaintButton.svelte';
	import RunStatus from '$lib/components/RunStatus.svelte';
	import Tooltip from '$lib/components/Tooltip.svelte';
	import VariationLanes from '$lib/components/VariationLanes.svelte';
	import WildToggle from '$lib/components/WildToggle.svelte';
	import type { Provider, ProviderGroup } from '$lib/models';
	import type { createModelInspection } from '$lib/features/model-inspection/state.svelte';
	import type {
		RefinementSession,
		RefineKind,
		VariationAmplitude,
		VariationCandidate
	} from '$lib/features/canvas/refinement-session.svelte';

	type ModelInspection = ReturnType<typeof createModelInspection>;
	type RefinementView = 'adjust' | 'compare' | 'language';

	type Props = {
		view: RefinementView;
		modalOpen: boolean;
		isJapanese: boolean;
		resultAvailable: boolean;
		artworkUrl: string | null;
		seedSummary: string;
		canvasAspectWidth: number;
		canvasAspectHeight: number;
		refinementSession: RefinementSession;
		modelInspection: ModelInspection;
		activeComparisonItem: { svg: string } | null;
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
		onClose: () => void;
		onSetRefineKind: (kind: RefineKind) => void;
		onGenerateVariationCandidates: (kind: RefineKind, count: 1 | 4, touchWords?: string, amplitude?: VariationAmplitude) => void | Promise<void>;
		onSaveSelectedVariationCandidates: () => void | Promise<void>;
		onShowVariationCandidate: (candidate: VariationCandidate) => void;
		onSelectRefineDrawingModel: (provider: Provider, model: string) => void | Promise<void>;
		onSetRefineWild: (value: boolean | null) => void;
	};

	let {
		view,
		modalOpen = false,
		isJapanese,
		resultAvailable,
		artworkUrl,
		seedSummary,
		canvasAspectWidth,
		canvasAspectHeight,
		refinementSession,
		modelInspection,
		activeComparisonItem,
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
		onClose,
		onSetRefineKind,
		onGenerateVariationCandidates,
		onSaveSelectedVariationCandidates,
		onShowVariationCandidate,
		onSelectRefineDrawingModel,
		onSetRefineWild
	}: Props = $props();

	const dialogTitle = $derived(
		view === 'adjust'
			? (isJapanese ? '描画要素を編集' : 'Edit drawing elements')
			: view === 'compare'
				? (isJapanese ? 'モデルを編集' : 'Edit models')
				: (isJapanese ? '言語を編集' : 'Edit languages')
	);
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
	const LANGUAGE_COMBOS: Array<['ja' | 'en', 'ja' | 'en']> = [
		['ja', 'ja'],
		['ja', 'en'],
		['en', 'ja'],
		['en', 'en']
	];
	function langName(lang: 'ja' | 'en'): string {
		return lang === 'ja' ? (isJapanese ? '日本語' : 'Japanese') : 'English';
	}
</script>

{#if modalOpen}
	<button type="button" class="refine-modal-backdrop" aria-label={isJapanese ? '比較ダイアログを閉じる' : 'Close comparison dialog'} onclick={onClose} onpointerdown={(event) => event.stopPropagation()}></button>
{/if}
<div class="refine-shell" class:menu-modal={modalOpen} role={modalOpen ? 'dialog' : undefined} aria-modal={modalOpen ? 'true' : undefined} aria-labelledby={modalOpen ? 'lineage-refine-dialog-title' : undefined} onpointerdown={(event) => event.stopPropagation()}>
	{#if modalOpen}
		<div class="refine-modal-header">
			<h2 id="lineage-refine-dialog-title">{dialogTitle}</h2>
			<button type="button" aria-label={isJapanese ? '閉じる' : 'Close'} onclick={onClose}>×</button>
		</div>
	{/if}
	{#if view === 'adjust'}
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
	{:else if view === 'compare'}
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
		<div class="model-target-card"><div class="comparison-label">{t().modelCompareTargetTitle}</div><div class="comparison-art" style="aspect-ratio: {canvasAspectWidth} / {canvasAspectHeight};">{#if activeComparisonItem}{@html activeComparisonItem.svg}{/if}</div><div class="model-target-meta">Stage 1: {modelInspection.targetStage1Model}<br />Stage 2: {modelInspection.targetStage2Model}</div></div>
		<div class="model-results-column">
			{#if modelInspection.results.length > 0}
				<div class="model-inspection-grid">
					{#each modelInspection.results as item (item.id)}
						<div class="model-inspection-card" class:saved={!!item.savedHistoryId}>
							<div class="comparison-label">{item.label}</div>
							<div class="model-comparison-art-wrap">
								<div class="comparison-art" style="aspect-ratio: {canvasAspectWidth} / {canvasAspectHeight};">{@html item.svg}</div>
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
	{:else}
	<div class="compare-panel">
		<div class="compare-head">
			<div class="compare-head-settings"><WildToggle value={refineWildValue} {isJapanese} inherited={refineWildInherited} onSelect={(next) => onSetRefineWild(next)} /></div>
			<div class="compare-action-wrap" class:running={modelInspection.languageBusy}>
				{#if modelInspection.languageBusy}
					<RunStatus
						variant="inline"
						label={isJapanese ? '比較中' : 'Comparing'}
						model={modelInspection.languageCurrentLabel}
						elapsedMs={modelInspection.languageElapsedMs}
						tokensIn={modelInspection.languageTokensIn}
						tokensOut={modelInspection.languageTokensOut}
						onStop={modelInspection.abortLanguage}
					/>
				{:else}
					<PaintButton onclick={modelInspection.runLanguage} disabled={!resultAvailable || refinementSession.gridBusy || modelInspection.languageSelectedCombos.length === 0}>{isJapanese ? '選んだ組み合わせで比較' : 'Compare selected combinations'}</PaintButton>
				{/if}
			</div>
		</div>
		<p class="lang-combo-hint">{isJapanese ? 'Stage 1（解釈）と Stage 2（描画）の言語の組み合わせを選びます。' : 'Pick the Stage 1 (interpretation) × Stage 2 (performance) language combination.'}</p>
		<div class="model-choice-grid lang-combo-grid" aria-label={isJapanese ? '比較する言語の組み合わせ' : 'Language combinations to compare'}>
			{#each LANGUAGE_COMBOS as combo (combo.join(':'))}
				{@const stage1 = combo[0]}
				{@const stage2 = combo[1]}
				{@const comboId = `${stage1}:${stage2}`}
				{@const blocked = stage1 === modelInspection.languageTargetLang && stage2 === modelInspection.languageTargetLang}
				{@const checked = modelInspection.languageSelectedCombos.includes(comboId)}
				<label class="model-choice lang-combo" class:checked={checked} class:target={blocked} class:disabled={blocked}>
					<input type="checkbox" checked={checked} disabled={modelInspection.languageBusy || blocked} onchange={() => modelInspection.toggleLanguageCombo(comboId)} />
					<span><strong>Stage 1: {langName(stage1)} ／ Stage 2: {langName(stage2)}</strong><small>{blocked ? (isJapanese ? '対象作品で使用中' : 'Used by target') : ''}</small></span>
				</label>
			{/each}
		</div>
		{#if modelInspection.languageStatus}<div class="variation-grid-status">{modelInspection.languageStatus}</div>{/if}
		<div class="model-compare-stage" class:busy={modelInspection.languageBusy}>
			<div class="model-target-card"><div class="comparison-label">{t().modelCompareTargetTitle}</div><div class="comparison-art" style="aspect-ratio: {canvasAspectWidth} / {canvasAspectHeight};">{#if activeComparisonItem}{@html activeComparisonItem.svg}{/if}</div><div class="model-target-meta">Stage 1: {langName(modelInspection.languageTargetLang)}<br />Stage 2: {langName(modelInspection.languageTargetLang)}</div></div>
			<div class="model-results-column">
				{#if modelInspection.languageResults.length > 0}<div class="model-inspection-grid">{#each modelInspection.languageResults as item (item.id)}<div class="model-inspection-card" class:saved={!!item.savedHistoryId}><div class="comparison-label">{item.label}</div><div class="model-comparison-art-wrap"><div class="comparison-art" style="aspect-ratio: {canvasAspectWidth} / {canvasAspectHeight};">{@html item.svg}</div><button class="variation-select model-adopt-select" class:selected={!!item.savedHistoryId} type="button" disabled={item.saving || !!item.savedHistoryId} onclick={() => modelInspection.saveResult(item)}>{item.saving ? '…' : item.savedHistoryId ? '✓' : '+'}</button></div><div class="model-result-actions"><button class="model-result-star" class:starred={!!item.starred} type="button" disabled={item.saving} onclick={() => modelInspection.saveResult(item, { star: true })}>{item.starred ? '★' : '☆'}</button></div><pre>{item.ddl}</pre></div>{/each}</div>{/if}
			</div>
		</div>
	</div>
	{/if}
</div>

<style>
	.refine-shell {
		align-self: stretch;
		width: min(1120px, calc(100% - 136px));
		max-height: calc(100% - 28px);
		min-height: 0;
		display: flex;
		flex-direction: column;
	}
	.refine-modal-backdrop { position: fixed; inset: 0; z-index: 1390; border: 0; padding: 0; background: rgba(0, 0, 0, .68); cursor: default; }
	.refine-shell.menu-modal { position: fixed; z-index: 1400; inset: 24px; align-self: auto; width: auto; height: auto; max-height: none; overflow: hidden; border: 1px solid var(--border2); border-radius: 12px; background: var(--panel); box-shadow: 0 24px 80px rgba(0, 0, 0, .55); }
	.refine-modal-header { flex: 0 0 auto; display: flex; align-items: center; justify-content: space-between; gap: 16px; min-height: 48px; padding: 0 16px; border-bottom: 1px solid var(--border); background: var(--panel); }
	.refine-modal-header h2 { margin: 0; color: var(--fg); font-size: 1rem; }
	.refine-modal-header button { display: grid; place-items: center; width: 30px; height: 30px; border: 1px solid var(--border2); border-radius: 6px; background: var(--bg); color: var(--fg); font-size: 1.25rem; line-height: 1; cursor: pointer; }
	.refine-shell .refine-panel,
	.refine-shell .compare-panel {
		align-self: auto;
		width: 100%;
		max-height: none;
		min-height: 0;
		flex: 1;
	}
	.refine-panel {
		align-self: stretch;
		width: min(980px, calc(100% - 136px));
		max-height: calc(100% - 28px);
		overflow: auto;
		display: flex;
		flex-direction: column;
		gap: 12px;
		padding: 16px;
		box-sizing: border-box;
	}
	.variation-grid-status {
		font-size: 12px;
		color: var(--fg3);
		line-height: 1.5;
	}
	.refine-stage {
		display: grid;
		grid-template-columns: minmax(220px, 280px) minmax(0, 1fr);
		gap: 14px;
		align-items: start;
	}
	.refine-target-column {
		position: sticky;
		top: 0;
		display: flex;
		flex-direction: column;
		gap: 12px;
		min-width: 0;
	}
	.refine-target-controls {
		display: flex;
		flex-direction: column;
		gap: 10px;
		min-width: 0;
	}
	.refine-target-card {
		border: 1px solid var(--border);
		background: var(--panel);
		padding: 8px;
		min-width: 0;
	}
	.refine-workspace {
		display: flex;
		flex-direction: column;
		gap: 10px;
		min-width: 0;
	}
	.refine-action-section {
		display: flex;
		flex-direction: column;
		gap: 8px;
		padding-bottom: 2px;
	}
	.refine-section-head {
		display: flex;
		flex-direction: column;
		gap: 2px;
	}
	.refine-section-title {
		font-size: 12px;
		font-weight: 600;
		color: var(--fg);
	}
	.refine-selection-hint {
		font-size: 11px;
		color: var(--fg3);
	}
	.touch-seed-field { display: grid; gap: 5px; color: var(--fg2); font-size: 12px; }
	.touch-seed-field input { width: 100%; box-sizing: border-box; border: 1px solid var(--border); border-radius: var(--r); padding: 8px 9px; color: var(--fg); background: var(--bg); font: inherit; }
	.touch-seed-field small { color: var(--fg3); font-size: 11px; line-height: 1.4; }
	.refine-actions {
		display: flex;
		flex-wrap: wrap;
		gap: 8px;
	}
	.refine-choice-label {
		display: inline-flex;
		align-items: center;
		gap: 6px;
		min-width: 0;
	}
	.refine-info-mark {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		width: 15px;
		height: 15px;
		border: 1px solid var(--border2);
		border-radius: 50%;
		color: var(--fg3);
		font-size: 10px;
		font-weight: 600;
		font-style: normal;
		flex: 0 0 auto;
	}
	.refine-cost-indicator {
		display: inline-flex;
		align-items: center;
		gap: 5px;
		min-height: 34px;
		color: var(--fg3);
		font-size: 11px;
		white-space: nowrap;
	}
	.refine-cost-indicator svg {
		width: 15px;
		height: 15px;
		fill: none;
		stroke: currentColor;
		stroke-width: 1.7;
		stroke-linecap: round;
		stroke-linejoin: round;
	}
	.refine-paint-actions { align-items: stretch; }
	/* Keep the speed estimate on its own row directly below the draw button. */
	.refine-paint-actions .refine-cost-indicator { flex: 0 0 100%; min-height: 0; }
	/* Indent amplitude below Variation to make the parent-child relation visible. */
	.variation-amplitude-field { display: grid; gap: 5px; grid-column: 1 / -1; margin: -2px 0 2px 18px; padding-left: 10px; border-left: 2px solid var(--border2); }
	/* Small, medium, and large stay in three columns; beat the later model grid. */
	.variation-amplitude-field .model-choice-grid.variation-amplitude-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 6px; }
	.variation-amplitude-field .model-choice { padding: 6px; gap: 5px; }
	.variation-amplitude-field .refine-info-mark { width: 13px; height: 13px; font-size: 9px; }
	.variation-card-moved { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 2px; }
	.variation-moved-axis { padding: 1px 5px; border: 1px solid var(--line); border-radius: 3px; font-size: 10px; color: var(--fg2); white-space: nowrap; }
	.refine-action-wrap { width: min(210px, 100%); }
	.refine-action-wrap :global(.tooltip-wrap),
	.refine-action-wrap :global(.paint-btn) { width: 100%; }
	.refine-action-wrap :global(.paint-btn) { margin-top: 0; min-height: 34px; font-size: 12px; letter-spacing: 0.03em; }
	.refine-save-actions {
		margin-bottom: 12px;
		display: flex;
		justify-content: flex-end;
	}
	.refine-save-actions :global(.tooltip-wrap) { width: fit-content; max-width: 100%; }
	.refine-save-actions button {
		width: auto;
		max-width: 100%;
		padding: 10px 16px;
		font-weight: 500;
	}
	.refine-candidates-section {
		border-top: 1px dashed var(--border);
		flex: 1 1 auto;
		min-height: 0;
	}

	.refine-save-btn { border: 1px solid var(--action-bg); border-radius: var(--r); background: var(--action-bg); color: var(--action-fg); cursor: pointer; }
	.refine-save-btn:hover:not(:disabled) { background: var(--action-hover); }
	.refine-save-btn:disabled { border-color: var(--border); background: var(--bg2); color: var(--fg3); cursor: not-allowed; }
	.variation-ddl-popup { position: absolute; z-index: 8; left: 10px; right: 10px; bottom: calc(100% - 10px); display: none; max-height: 220px; overflow: auto; padding: 10px; border: 1px solid var(--border2); border-radius: var(--r); background: var(--tooltip-bg); color: var(--tooltip-fg); font: 11px/1.5 ui-monospace, monospace; white-space: pre-wrap; word-break: break-word; box-shadow: 0 8px 24px rgba(0,0,0,.24); pointer-events: none; }
	.variation-card-wrap:hover .variation-ddl-popup { display: block; }
	/* Fit candidates into the remaining height; rows divide it and cards fill each row. */
	/* A single candidate uses one column and fills the dialog width. */
	.variation-grid {
		display: grid;
		grid-template-columns: repeat(var(--variation-cols, 2), minmax(0, 1fr));
		grid-auto-rows: minmax(0, 1fr);
		gap: 10px;
		min-height: 0;
		max-height: calc(100vh - 200px);
	}
	.variation-card-wrap {
		position: relative;
		min-width: 0;
		min-height: 0;
	}
	/* A dashed frame marks the candidate slot before it has been drawn. */
	.variation-grid-placeholder {
		display: grid;
		place-items: center;
		flex: 1 1 auto;
		min-height: 180px;
		max-height: calc(100vh - 200px);
		padding: 24px;
		border: 1px dashed var(--border2);
		border-radius: var(--r);
		background: var(--bg2);
		text-align: center;
	}
	.variation-grid-placeholder span {
		max-width: 30em;
		color: var(--fg3);
		font-size: 12px;
		line-height: 1.6;
	}
	.variation-card {
		display: grid;
		grid-template-rows: minmax(0, 1fr) auto;
		width: 100%;
		height: 100%;
		min-height: 150px;
		padding: 0;
		border: 1px solid var(--border);
		border-radius: var(--r);
		background: var(--panel);
		color: var(--fg);
		overflow: hidden;
		cursor: pointer;
	}
	.variation-card.selected { border-color: var(--accent); box-shadow: inset 0 0 0 1px var(--accent); }
	.variation-card.saved { opacity: 0.62; }
	.variation-card-art {
		display: block;
		min-height: 0;
		background: var(--bg2);
	}
	.variation-card-art :global(svg) {
		display: block;
		width: 100%;
		height: 100%;
	}
	.variation-card-meta {
		display: grid;
		grid-template-columns: minmax(0, 1fr);
		gap: 1px;
		padding: 6px 8px;
		font-size: 10px;
		line-height: 1.25;
		text-align: left;
		color: var(--fg3);
	}
	.variation-card-meta span {
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.variation-select {
		position: absolute;
		top: 6px;
		right: 6px;
		width: 30px;
		height: 30px;
		border-radius: 50%;
		border: 1px solid var(--border2);
		background: color-mix(in srgb, var(--panel) 88%, transparent);
		color: var(--fg2);
		font-size: 15px;
		line-height: 1;
		cursor: pointer;
	}
	.variation-select.selected {
		border-color: var(--accent);
		background: var(--accent);
		color: var(--accent-fg);
	}
	/* A saved candidate has a distinct fill and cannot be pressed again. */
	.variation-select.saved {
		border-color: var(--accent);
		background: color-mix(in srgb, var(--accent) 20%, var(--panel));
		color: var(--accent);
		cursor: default;
		opacity: 1;
	}

	.compare-panel {
		align-self: stretch;
		width: min(1120px, calc(100% - 136px));
		max-height: calc(100% - 28px);
		overflow: auto;
		display: flex;
		flex-direction: column;
		gap: 12px;
		padding: 16px;
		box-sizing: border-box;
	}
	.compare-head {
		display: flex;
		align-items: flex-start;
		justify-content: space-between;
		gap: 16px;
	}
	.compare-head-settings { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; min-width: 0; }
	.compare-action-wrap {
		width: min(260px, 34%);
		min-width: 210px;
	}
	.compare-action-wrap :global(.tooltip-wrap) { width: 100%; }
	.compare-action-wrap :global(.paint-btn) { margin-top: 0; }
	/* While comparing, let the status widen past the button width so the full
	   model name shows without truncation.  Keyed on a class this component
	   writes: the status element belongs to RunStatus, so a selector naming it
	   would be scoped away and match nothing. */
	.compare-action-wrap.running { width: auto; min-width: 0; max-width: 62%; }
	.model-metadata-hover { position: relative; display: flex; min-width: 0; }
	.model-metadata-hover > .model-choice { width: 100%; }
	.model-metadata-hover:hover :global(.model-hover-card),
	.model-metadata-hover:focus-within :global(.model-hover-card) { display: block; }
	.refine-settings-row { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-top: 6px; }
	.refine-model-row { margin-top: 6px; }

	.compare-mode-tabs { display: flex; gap: 0; border-bottom: 1px solid var(--border); }
	.compare-mode-tabs button { padding: 8px 12px; border: 0; border-bottom: 2px solid transparent; background: transparent; color: var(--fg3); font: inherit; cursor: pointer; }
	.compare-mode-tabs button.active { border-bottom-color: var(--accent); color: var(--fg); font-weight: 600; }
	.compare-fixed-model { display: flex; align-items: center; gap: 10px; font-size: 12px; color: var(--fg2); }
	.compare-fixed-model select { min-width: 240px; padding: 7px 9px; border: 1px solid var(--border); border-radius: var(--r); background: var(--panel); color: var(--fg); font: inherit; }
	.model-choice-grid {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
		gap: 8px;
	}
	.lang-combo-hint { margin: 8px 0 0; font-size: 11px; color: var(--fg3); }
	.lang-combo-grid { grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); }
	.lang-combo strong { white-space: nowrap; }
	.model-choice {
		display: grid;
		grid-template-columns: auto minmax(0, 1fr);
		gap: 8px;
		align-items: start;
		padding: 8px;
		border: 1px solid var(--border);
		border-radius: var(--r);
		background: var(--panel);
		color: var(--fg2);
		font-size: 11px;
	}
	.model-choice.checked { border-color: var(--accent); color: var(--fg); }
	.model-choice.target {
		border-color: color-mix(in srgb, var(--accent) 62%, var(--border));
		border-left-width: 4px;
		background: color-mix(in srgb, var(--accent) 13%, var(--panel));
		color: var(--fg);
	}
	.model-choice.target small { color: color-mix(in srgb, var(--accent) 72%, var(--fg3)); }
	.model-choice.failed {
		border-color: color-mix(in srgb, #cf3f35 70%, var(--border));
		background: color-mix(in srgb, #cf3f35 12%, var(--panel));
		color: var(--fg);
	}
	.model-choice.failed small { color: #b8332d; }
	.model-choice.disabled { opacity: 0.48; }
	.model-choice strong,
	.model-choice small {
		display: block;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.model-choice small { color: var(--fg3); margin-top: 2px; }
	.model-choice-count,
	.model-target-meta {
		font-size: 11px;
		color: var(--fg3);
	}
	.model-compare-stage {
		display: grid;
		grid-template-columns: minmax(220px, 280px) minmax(0, 1fr);
		gap: 14px;
		align-items: start;
	}
	.model-target-card,
	.model-inspection-card {
		border: 1px solid var(--border);
		background: var(--panel);
		padding: 8px;
		min-width: 0;
	}
	.model-target-card {
		position: sticky;
		top: 0;
	}
	.comparison-label {
		font-size: 11px;
		color: var(--fg3);
		margin-bottom: 5px;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.comparison-art {
		background: var(--bg2);
		overflow: hidden;
	}
	.comparison-art :global(> svg) { width: 100%; height: 100%; display: block; }
	.comparison-art > .canvas-art { width: 100%; height: 100%; display: block; }
	.model-target-meta { margin-top: 7px; }
	.model-results-column {
		display: flex;
		flex-direction: column;
		gap: 10px;
		min-width: 0;
	}
	.model-inspection-grid {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
		gap: 10px;
	}
	.model-inspection-card { position: relative; }
	.model-inspection-card.saved {
		border-color: color-mix(in srgb, var(--accent) 55%, var(--border));
	}
	.model-comparison-art-wrap { position: relative; }
	.model-adopt-select:disabled { cursor: default; opacity: 1; }
	.model-result-actions {
		display: flex;
		align-items: center;
		justify-content: flex-end;
		gap: 8px;
		margin-top: 8px;
	}
	.model-result-star {
		width: 30px;
		height: 30px;
		border: 1px solid var(--border);
		background: var(--panel);
		color: var(--fg3);
		font-size: 17px;
		cursor: pointer;
	}
	.model-result-star.starred {
		color: var(--star-fg);
		border-color: var(--star-border);
		background: var(--star-bg);
	}
	.model-result-star:disabled { opacity: 0.45; cursor: not-allowed; }
	.model-inspection-card pre {
		margin: 8px 0 0;
		max-height: 120px;
		overflow: auto;
		white-space: pre-wrap;
		font-size: 10px;
		line-height: 1.45;
		color: var(--fg3);
	}
</style>
