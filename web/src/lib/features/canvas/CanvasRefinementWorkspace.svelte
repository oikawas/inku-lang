<script lang="ts">
	import RefinementAdjustView from './RefinementAdjustView.svelte';
	import RefinementColorCatalogView from './RefinementColorCatalogView.svelte';
	import RefinementGroundView from './RefinementGroundView.svelte';
	import RefinementToolView from './RefinementToolView.svelte';
	import RefinementModelCompareView from './RefinementModelCompareView.svelte';
	import './refinement-workspace.css';
	import { t } from '$lib/i18n/index.svelte';
	import type { Provider, ProviderGroup } from '$lib/models';
	import type { createModelInspection } from '$lib/features/model-inspection/state.svelte';
	import type {
		RefinementSession,
		RefinementView,
		RefineKind
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
		statusDescriptionLocked: boolean;
		statusStage1Model: string;
		statusStage2Model: string;
		refineDrawingModelId: string;
		refineDrawingModelGroups: ProviderGroup[];
		refineWildValue: boolean;
		refineWildInherited: boolean;
		/** The catalog the work uses, named in the color change dialog. */
		catalogName: string;
		onClose: () => void;
		onGenerateVariationCandidates: (kind: RefineKind, count: 1 | 4) => void | Promise<void>;
		onGenerateColorCatalogCandidates: () => void | Promise<void>;
		onGenerateColorArrangementCandidates: () => void | Promise<void>;
		onGenerateGroundCandidates: () => void | Promise<void>;
		onGenerateToolCandidates: () => void | Promise<void>;
		onGenerateModelCandidates: () => void | Promise<void>;
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
		statusDescriptionLocked,
		statusStage1Model,
		statusStage2Model,
		refineDrawingModelId,
		refineDrawingModelGroups,
		refineWildValue,
		refineWildInherited,
		catalogName,
		onClose,
		onGenerateVariationCandidates,
		onGenerateColorCatalogCandidates,
		onGenerateColorArrangementCandidates,
		onGenerateGroundCandidates,
		onGenerateToolCandidates,
		onGenerateModelCandidates,
		onSaveAndClose,
		onDiscardAndClose,
		onSelectRefineDrawingModel,
		onSetRefineWild
	}: Props = $props();

	const dialogTitle = $derived(
		view === 'layout'
				? t().canvasVaryComposition
				: view === 'color-arrangement'
					? t().workActionColorArrangement
				: view === 'ground'
					? t().workActionGround
				: view === 'tool'
					? t().workActionTool
					: view === 'color'
					? t().canvasVaryColor
					: t().workActionModels
	);
</script>

{#if modalOpen}
	<button type="button" class="refine-modal-backdrop" aria-label={isJapanese ? '比較ダイアログを閉じる' : 'Close comparison dialog'} onclick={onClose} onpointerdown={(event) => event.stopPropagation()}></button>
{/if}
<div class="refine-shell" class:menu-modal={modalOpen} role={modalOpen ? 'dialog' : undefined} aria-modal={modalOpen ? 'true' : undefined} aria-labelledby={modalOpen ? 'lineage-refine-dialog-title' : undefined} onpointerdown={(event) => event.stopPropagation()}>
	{#if modalOpen}
		<div class="refine-modal-header">
			<h2 id="lineage-refine-dialog-title">{dialogTitle}</h2>
			<!-- Unsaved options can leave only by saving or discarding them, so × is not offered then. -->
			{#if !refinementSession.hasUnsaved}
				<button type="button" aria-label={isJapanese ? '閉じる' : 'Close'} onclick={onClose}>×</button>
			{/if}
		</div>
	{/if}
	{#if view === 'layout'}
		<RefinementAdjustView
			{isJapanese}
			{resultAvailable}
			{artworkUrl}
			{seedSummary}
			{canvasAspectWidth}
			{canvasAspectHeight}
			{refinementSession}
			{statusStage1Model}
			{statusStage2Model}
			{refineDrawingModelId}
			{refineDrawingModelGroups}
			{refineWildValue}
			{refineWildInherited}
			{onGenerateVariationCandidates}
			{onSaveAndClose}
			{onDiscardAndClose}
			{onSelectRefineDrawingModel}
			{onSetRefineWild}
		/>
	{:else if view === 'color' || view === 'color-arrangement'}
		<RefinementColorCatalogView
			mode={view === 'color-arrangement' ? 'arrangement' : 'catalog'}
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
			onGenerateCandidates={view === 'color-arrangement' ? onGenerateColorArrangementCandidates : onGenerateColorCatalogCandidates}
			{onSaveAndClose}
			{onDiscardAndClose}
		/>
	{:else if view === 'ground'}
		<RefinementGroundView
			{isJapanese}
			{resultAvailable}
			{artworkUrl}
			{seedSummary}
			{canvasAspectWidth}
			{canvasAspectHeight}
			{refinementSession}
			onGenerateCandidates={onGenerateGroundCandidates}
			{onSaveAndClose}
			{onDiscardAndClose}
		/>
	{:else if view === 'tool'}
		<RefinementToolView
			{isJapanese}
			{resultAvailable}
			{artworkUrl}
			{seedSummary}
			{canvasAspectWidth}
			{canvasAspectHeight}
			{refinementSession}
			onGenerateCandidates={onGenerateToolCandidates}
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
			{artworkUrl}
			{seedSummary}
			{canvasAspectWidth}
			{canvasAspectHeight}
			{refinementSession}
			{modelInspection}
			{refineWildValue}
			{refineWildInherited}
			{onSetRefineWild}
			{onGenerateModelCandidates}
			{onSaveAndClose}
			{onDiscardAndClose}
		/>
	{/if}
</div>
