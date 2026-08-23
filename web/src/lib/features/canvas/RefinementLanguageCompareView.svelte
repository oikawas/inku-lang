<script lang="ts">
	import { t } from '$lib/i18n/index.svelte';
	import PaintButton from '$lib/components/PaintButton.svelte';
	import RunStatus from '$lib/components/RunStatus.svelte';
	import WildToggle from '$lib/components/WildToggle.svelte';
	import type { createModelInspection } from '$lib/features/model-inspection/state.svelte';
	import type { RefinementSession } from '$lib/features/canvas/refinement-session.svelte';

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
