<script lang="ts">
	import RefinementAdjustView from './RefinementAdjustView.svelte';
	import RefinementColorCatalogView from './RefinementColorCatalogView.svelte';
	import RefinementModelCompareView from './RefinementModelCompareView.svelte';
	import './refinement-workspace.css';
	import { t } from '$lib/i18n/index.svelte';
	import type { Provider, ProviderGroup } from '$lib/models';
	import type { createModelInspection } from '$lib/features/model-inspection/state.svelte';
	import type {
		RefinementSession,
		RefinementView,
		RefineKind,
		VariationAmplitude
	} from '$lib/features/canvas/refinement-session.svelte';

	type ModelInspection = ReturnType<typeof createModelInspection>;
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
		statusDescriptionLocked: boolean;
		refineKind: RefineKind;
		variationAmplitude: VariationAmplitude;
		touchSeedText: string;
		statusStage1Model: string;
		statusStage2Model: string;
		refineDrawingModelId: string;
		refineDrawingModelGroups: ProviderGroup[];
		refineWildValue: boolean;
		refineWildInherited: boolean;
		/** The catalog the work uses, named in the color change dialog. */
		catalogName: string;
		onClose: () => void;
		onSetRefineKind: (kind: RefineKind) => void;
		onGenerateVariationCandidates: (kind: RefineKind, count: 1 | 4, touchWords?: string, amplitude?: VariationAmplitude) => void | Promise<void>;
		onGenerateColorCatalogCandidates: () => void | Promise<void>;
		onSaveAndClose: () => void | Promise<void>;
		onDiscardAndClose: () => void | Promise<void>;
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
		statusDescriptionLocked,
		refineKind,
		variationAmplitude = $bindable('medium'),
		touchSeedText = $bindable(''),
		statusStage1Model,
		statusStage2Model,
		refineDrawingModelId,
		refineDrawingModelGroups,
		refineWildValue,
		refineWildInherited,
		catalogName,
		onClose,
		onSetRefineKind,
		onGenerateVariationCandidates,
		onGenerateColorCatalogCandidates,
		onSaveAndClose,
		onDiscardAndClose,
		onSelectRefineDrawingModel,
		onSetRefineWild
	}: Props = $props();

	const dialogTitle = $derived(
		view === 'adjust'
			? (isJapanese ? '描画要素を編集' : 'Edit drawing elements')
			: view === 'color'
				? t().canvasVaryColor
				: (isJapanese ? 'モデルを編集' : 'Edit models')
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
			{statusDescriptionLocked}
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
			{onSaveAndClose}
			{onDiscardAndClose}
			{onSelectRefineDrawingModel}
			{onSetRefineWild}
		/>
	{:else if view === 'color'}
		<RefinementColorCatalogView
			{isJapanese}
			{resultAvailable}
			{artworkUrl}
			{seedSummary}
			{canvasAspectWidth}
			{canvasAspectHeight}
			{refinementSession}
			{catalogName}
			{statusStage1Model}
			{statusStage2Model}
			{onGenerateColorCatalogCandidates}
			{onSaveAndClose}
			{onDiscardAndClose}
		/>
	{:else if statusDescriptionLocked}
		<!-- Comparing models reads the description again, which a work its DDL
		     holds is not drawn from. -->
		<p class="refine-held-note">{t().descriptionLockedReason}</p>
	{:else}
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
	{/if}
</div>
