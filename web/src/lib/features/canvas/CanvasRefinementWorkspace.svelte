<script lang="ts">
	import RefinementAdjustView from './RefinementAdjustView.svelte';
	import RefinementLanguageCompareView from './RefinementLanguageCompareView.svelte';
	import RefinementModelCompareView from './RefinementModelCompareView.svelte';
	import './refinement-workspace.css';
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
		<RefinementAdjustView
			{isJapanese}
			{resultAvailable}
			{artworkUrl}
			{seedSummary}
			{canvasAspectWidth}
			{canvasAspectHeight}
			{refinementSession}
			{statusDdlOrigin}
			{refineKind}
			bind:variationAmplitude
			bind:touchSeedText
			{statusStage1Model}
			{statusStage2Model}
			{refineDrawingModelId}
			{refineDrawingModelGroups}
			{refineWildValue}
			{refineWildInherited}
			{onSetRefineKind}
			{onGenerateVariationCandidates}
			{onSaveSelectedVariationCandidates}
			{onShowVariationCandidate}
			{onSelectRefineDrawingModel}
			{onSetRefineWild}
		/>
	{:else if view === 'compare'}
		<RefinementModelCompareView
			{isJapanese}
			{resultAvailable}
			{canvasAspectWidth}
			{canvasAspectHeight}
			{refinementSession}
			{modelInspection}
			{activeComparisonItem}
			{refineWildValue}
			{refineWildInherited}
			{onSetRefineWild}
		/>
	{:else}
		<RefinementLanguageCompareView
			{isJapanese}
			{resultAvailable}
			{canvasAspectWidth}
			{canvasAspectHeight}
			{refinementSession}
			{modelInspection}
			{activeComparisonItem}
			{refineWildValue}
			{refineWildInherited}
			{onSetRefineWild}
		/>
	{/if}
</div>
