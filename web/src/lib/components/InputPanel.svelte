<script lang="ts">
	import { t } from '$lib/i18n/index.svelte';
	import { placeIn } from '$lib/place-in';
	import type { ModelReadiness } from '$lib/model-readiness';
	import LabelHighlight from './LabelHighlight.svelte';
	import Tooltip from './Tooltip.svelte';
	import BatchPanel from './BatchPanel.svelte';
	import ImageFolderBatchPanel from './ImageFolderBatchPanel.svelte';
	import type { ImageFolderBatch } from '$lib/features/batch/image-folder.svelte';
	import CanvasAspectPlugin from './CanvasAspectPlugin.svelte';
	import DrawConditions from './DrawConditions.svelte';
	import { type SketchMode } from '$lib/sketch';
	import { type CompositionMode, type DrawRoute } from '$lib/draw-route';
	import PaintButton from './PaintButton.svelte';
	import RunStatus from './RunStatus.svelte';
	import DescriptionMeter from './DescriptionMeter.svelte';
	import type { CanvasAspectId, CanvasAspectOption } from '$lib/plugins/system/canvas-aspect';
	import type { ProviderAttemptCount } from '$lib/paintStream';
	import type { UploadedPipelineImage } from '$lib/features/pipeline/api';

	type BatchFailure = {
		line: number;
		input: string;
		message: string;
	};
	type BatchFailureReport = {
		success: number;
		total: number;
		failures: BatchFailure[];
	};
	type Props = {
		drawActionTarget?: HTMLElement | null;
		tabsTarget?: HTMLElement | null;
		visionCatalogReady?: boolean;
		visionUnavailableReason?: 'unpublished' | 'disconnected' | 'not_vision' | 'missing';
		nextDrawParentNodeId?: string | null;
		chatgptPlanSelected?: boolean;
		chatgptUsageUrl?: string | null;
		modelReadiness?: ModelReadiness;
		onOpenConnectionSettings: (provider?: string) => void;
		inputMode: 'single' | 'image' | 'batch';
		imageProvenance: string;
		uploadedImage: UploadedPipelineImage | null;
		imageFileName: string;
		imageUploading: boolean;
		imageRunning: boolean;
		imageCanvasAspectId: CanvasAspectId;
		visionModelName: string;
		visionModelAvailable: boolean;
		onSelectImage: (file: File) => void | Promise<void>;
		/** The author typed in the source note; a chosen image then leaves it alone. */
		onImageProvenanceInput?: () => void;
		onSubmitImage: () => void | Promise<void>;
		onSelectImageCanvasAspect: (id: CanvasAspectId) => void;
		onOpenImageModelSelection: () => void;
		/** The batch tab's picture side: a picked folder painted picture by picture. */
		imageFolder: ImageFolderBatch;
		onRunImageFolder: (fromStart: boolean) => void | Promise<void>;
		input: string;
		batchInput: string;
		lineNumbersText: string;
		batchNonEmpty: number;
		batchRunning: boolean;
		singleRunning: boolean;
		descriptionLocked: boolean;
		/** The run shows its status elsewhere (the instruction sheet draws its own). */
		hideRunStatus?: boolean;
		runTokensIn: number | null;
		runTokensOut: number | null;
		runAttempt?: ProviderAttemptCount | null;
		runProgress?: import('$lib/paintStream').PaintProgressEvent | null;
		singleDdlReady: boolean;
		batchActiveLine: number | null;
		batchObservedLine: number | null;
		batchRunningLineText: string;
		batchSketchText: string | null;
		batchSketchGrainLabel: string;
		batchActiveDdlHighlighted: string;
		batchTotal: number;
		batchCurrent: number;
		batchSummaryCurrent: number;
		batchSummaryTotal: number;
		batchStartedAt: number;
		batchWorkStartedAt: number | null;
		batchAverageWorkMs: number | null;
		batchRetryRound: number;
		batchActiveTokensIn: number | null;
		batchActiveTokensOut: number | null;
		batchTokensInTotal: number;
		batchTokensOutTotal: number;
		liveMs: number;
		batchFailureReport: BatchFailureReport | null;
		canSubmit: boolean;
		generationDisabled: boolean;
		error: string | null;
		batchPromptHistory: string[];
		canResumeBatch: boolean;
		canRetryBatchFailures: boolean;
		batchResumeInfo: { nextLine: number | null; pending: number | null; total: number; reason?: 'failed'; failureCount?: number } | null;
		batchResuming: boolean;
		batchInterrupted: boolean;
		batchWaitingLine?: number | null;
		batchServerLost?: boolean;
		batchSuccess: number;
		onResumeBatch: () => void;
		onRetryBatchFailures: () => void;
		stageLabel: string;
		canvasAspectId: CanvasAspectId;
		canvasAspectOptions: CanvasAspectOption[];
		canvasAspectMenuOpen: boolean;
		stage1ModelLabel: string;
		stage2ModelLabel: string;
		/** Sketch from life (Stage 0.5). Chosen per draw, not stored as a user setting. */
		sketchMode: SketchMode;
		wild: boolean;
		onSelectWild: (value: boolean) => void;
		onSelectSketchMode: (mode: SketchMode) => void;
		/** How a description is drawn. Chosen per draw, like the sketch. */
		drawRoute: DrawRoute;
		onSelectDrawRoute: (route: DrawRoute) => void;
		/** The composition and laws inside read and draw. Chosen per draw, like the route. */
		compositionMode: CompositionMode;
		onSelectCompositionMode: (mode: CompositionMode) => void;
		nextStage1Model: string;
		nextStage2Model: string;
		nextCatalogName: string;
		onToggleCanvasAspectMenu: () => void;
		onSelectCanvasAspect: (id: CanvasAspectId) => void | Promise<void>;
		onOpenModelSelection: () => void;
		onOpenCatalogModal: () => void;
		onClearInput: () => void;
		onRememberBatchPrompt: (prompt: string) => void | Promise<void>;
		onSubmit: () => void | Promise<void>;
		onForkDescription: () => void | Promise<void>;
		onStop: () => void;
	};

	let {
		drawActionTarget = null, tabsTarget = null, visionCatalogReady = false, visionUnavailableReason = 'missing', nextDrawParentNodeId = null,
		chatgptPlanSelected = false,
		chatgptUsageUrl = null,
		modelReadiness = null, onOpenConnectionSettings,
		inputMode = $bindable('single'),
		imageProvenance = $bindable(''), uploadedImage, imageFileName, imageUploading, imageRunning,
		imageCanvasAspectId, visionModelName, visionModelAvailable,
		onSelectImage, onImageProvenanceInput, onSubmitImage, onSelectImageCanvasAspect, onOpenImageModelSelection,
		imageFolder, onRunImageFolder,
		input = $bindable(''),
		batchInput = $bindable(''),
		lineNumbersText,
		batchNonEmpty,
		batchRunning,
		singleRunning,
		descriptionLocked,
		hideRunStatus = false,
		runTokensIn,
		runTokensOut,
		runAttempt = null,
		runProgress = null,
		singleDdlReady,
		batchActiveLine,
		batchObservedLine,
		batchRunningLineText,
		batchSketchText,
		batchSketchGrainLabel,
		batchActiveDdlHighlighted,
		batchTotal,
		batchCurrent,
		batchSummaryCurrent,
		batchSummaryTotal,
		batchStartedAt,
		batchWorkStartedAt,
		batchAverageWorkMs,
		batchRetryRound,
		batchActiveTokensIn,
		batchActiveTokensOut,
		batchTokensInTotal,
		batchTokensOutTotal,
		liveMs,
		batchFailureReport,
		canSubmit,
		generationDisabled,
		error,
		batchPromptHistory,
		canResumeBatch,
		canRetryBatchFailures,
		batchResumeInfo,
		batchResuming,
		batchInterrupted,
		batchWaitingLine = null,
		batchServerLost = false,
		batchSuccess,
		onResumeBatch,
		onRetryBatchFailures,
		stageLabel,
		canvasAspectId,
		canvasAspectOptions,
		canvasAspectMenuOpen,
		stage1ModelLabel,
		stage2ModelLabel,
		sketchMode,
		wild,
		onSelectWild,
		onSelectSketchMode,
		drawRoute,
		onSelectDrawRoute,
		compositionMode,
		onSelectCompositionMode,
		nextStage1Model,
		nextStage2Model,
		nextCatalogName,
		onToggleCanvasAspectMenu,
		onSelectCanvasAspect,
		onOpenModelSelection,
		onOpenCatalogModal,
		onClearInput,
		onRememberBatchPrompt,
		onSubmit,
		onForkDescription,
		onStop,
	}: Props = $props();

	const isJapanese = $derived(t().code === 'ja');
	let imageInputEl = $state<HTMLInputElement | null>(null);

	// Progress sits on the tab only while the batch is running, so the tab returns
	// to its plain label the moment the run stops. batchCurrent is 0 outside a run.
	// During a retry round the counter runs over that round's own lines, marked
	// with ↻n so the numbers restarting does not read as the batch restarting.
	const batchRetryMark = $derived(batchRetryRound > 0 ? ` ↻${batchRetryRound}` : '');
	// The picture batch counts its pictures the same way.
	const folderRunning = $derived(imageFolder.running);
	const progressTotal = $derived(folderRunning ? imageFolder.total : batchTotal);
	const batchProgress = $derived(
		folderRunning && imageFolder.total > 0 && imageFolder.current > 0
			? `(${imageFolder.current}/${imageFolder.total})`
			: batchRunning && batchTotal > 0 && batchCurrent > 0
				? `(${batchCurrent}/${batchTotal}${batchRetryMark})`
				: '',
	);
	// The counter is reserved at its widest form -- "(NN/NN)" for a two-digit total --
	// so the label beside it does not shuffle as the count crosses a digit boundary.
	// The tabs themselves are flex: 1 with a zero basis, so no tab can push another.
	const batchProgressWidth = $derived(
		2 * String(progressTotal).length + 3 + (!folderRunning && batchRetryRound > 0 ? 2 + String(batchRetryRound).length : 0),
	);

	// The batch tab paints pictures with the picture tab's settings.
	const pictureConditions = $derived(inputMode === 'image' || (inputMode === 'batch' && imageFolder.source === 'image'));
	const conditionModelName = $derived(pictureConditions ? visionModelName
		: nextStage1Model === nextStage2Model ? nextStage1Model
		: `${isJapanese ? '解釈' : 'Interpretation'} ${nextStage1Model} ／ ${isJapanese ? '描画' : 'Performance'} ${nextStage2Model}`);

	const tabItems = $derived([
		{ mode: 'single' as const, label: t().modeSingle, running: singleRunning && !imageRunning, progress: '' },
		{ mode: 'image' as const, label: t().imageTab, running: imageRunning, progress: '' },
		{ mode: 'batch' as const, label: t().modeBatch, running: batchRunning || folderRunning, progress: batchProgress },
	]);

</script>

<div class="tabs-placeholder"><div class="panel-tabs" use:placeIn={tabsTarget}>
	{#each tabItems as item (item.mode)}
		<Tooltip
			placement={item.mode === 'single' ? 'bottom-right' : 'bottom-left'}
			text={item.mode === 'single' ? t().tooltipInputTabSingle : item.mode === 'image' ? t().imageTabHint : t().tooltipInputTabBatch}
		>
			<button
				class="panel-tab"
				class:active={inputMode === item.mode}
				class:running={item.running}
				aria-busy={item.running}
				onclick={() => (inputMode = item.mode)}
			>
				<span class="tab-label">{item.label}</span>
				{#if item.progress}<span class="tab-progress" style="min-width: {batchProgressWidth}ch">{item.progress}</span>{/if}
				{#if item.running}<span class="tab-running-dot" aria-hidden="true"></span>{/if}
			</button>
		</Tooltip>
	{/each}
</div></div>

<section class="panel-section">
	{#snippet modelReadinessStatus()}
		{#if modelReadiness}
			<div role="status">
				<p>{modelReadiness.kind === 'chatgpt_unavailable' ? t().chatgptModelUnavailable : modelReadiness.kind === 'chatgpt_unpublished' ? t().chatgptModelUnpublished : modelReadiness.kind === 'no_models_admin' ? t().drawingNoModelsAdmin : modelReadiness.kind === 'no_models_user' ? t().drawingNoModelsUser : modelReadiness.kind === 'unavailable' ? t().drawingModelUnavailable : modelReadiness.kind === 'missing_key_admin' ? t().drawingKeyMissingAdmin : t().drawingKeyMissingUser}</p>
				{#if modelReadiness.action === 'choose'}<button class="ghost-btn" type="button" onclick={onOpenModelSelection}>{t().modelSelectButton}</button>{/if}
				{#if modelReadiness.action === 'settings'}<button class="ghost-btn" type="button" onclick={() => onOpenConnectionSettings(modelReadiness?.provider)}>{t().drawingOpenConnection}</button>{/if}
			</div>
		{/if}
	{/snippet}
	<!-- The description is written before its conditions, immediately before painting. -->
	{#snippet inputConditionRows()}
		<div class="conditions-head">
			<h3 class="conditions-heading">{inputMode === 'batch' ? t().batchNextConditionsLabel : t().nextWorkConditions}</h3>
			<Tooltip text={t().tooltipInputCanvas}>
				<CanvasAspectPlugin row selected={pictureConditions ? imageCanvasAspectId : canvasAspectId}
					options={pictureConditions ? [{ id: 'image', label: t().imageCanvasAspect, category: 'Vision', ratio: '', ratioW: 1, ratioH: 1, intentJa: t().imageCanvasAspect, intentEn: t().imageCanvasAspect }, ...canvasAspectOptions] : canvasAspectOptions}
					open={canvasAspectMenuOpen} onToggle={onToggleCanvasAspectMenu} onSelect={pictureConditions ? onSelectImageCanvasAspect : onSelectCanvasAspect} />
			</Tooltip>
		</div>
		<div class="condition-rows" aria-label={t().nextWorkConditions}>
			<div class="condition-selection">
				<span class="condition-inline-label">{t().modelButton}</span>
				<span class="condition-value" class:invalid-vision={pictureConditions && visionCatalogReady && !visionModelAvailable} title={conditionModelName}>{conditionModelName}</span>
				{#if pictureConditions && visionCatalogReady && !visionModelAvailable}
					<span class="invalid-vision-note">{visionUnavailableReason === 'not_vision' ? t().imageVisionUnavailableShort : visionUnavailableReason === 'unpublished' ? t().imageVisionNotPublished : visionUnavailableReason === 'disconnected' ? t().imageVisionNotConnected : t().imageVisionNotListed}</span>
				{/if}
				{#if chatgptPlanSelected && inputMode === 'single' && chatgptUsageUrl}
					<a class="chatgpt-plan-label" href={chatgptUsageUrl} target="_blank" rel="noopener noreferrer">{t().chatgptManageUsage}</a>
				{/if}
				<Tooltip text={pictureConditions ? t().modelSelectionVisionHint : t().tooltipInputModel} placement="top-left">
					<button class="ghost-btn condition-change" aria-label={pictureConditions ? t().modelSelectionVisionHint : t().tooltipInputModel} onclick={pictureConditions ? onOpenImageModelSelection : onOpenModelSelection}>{t().editButton}</button>
				</Tooltip>
			</div>
			<div class="condition-selection">
				<span class="condition-inline-label">{t().colorCatalogButton}</span>
				<span class="condition-value" title={nextCatalogName}>{nextCatalogName}</span>
				<Tooltip text={t().tooltipInputCatalog} placement="top-left">
					<button class="ghost-btn condition-change" aria-label={t().tooltipInputCatalog} onclick={onOpenCatalogModal}>{t().editButton}</button>
				</Tooltip>
			</div>
			<div class="condition-compact-rows">
				{#if !pictureConditions}
				<div class="condition-draw">
					<DrawConditions route={drawRoute} {sketchMode} {compositionMode} {isJapanese} {wild}
						onSelectRoute={onSelectDrawRoute} {onSelectSketchMode} {onSelectCompositionMode} />
				</div>
				{/if}
			</div>
		</div>
	{/snippet}
	{#snippet inputSettings()}
		{@render inputConditionRows()}
	{/snippet}

	{#if inputMode === 'single'}
		<div class="input-label">
			<div class="input-label-text">
				<div class="input-heading">
					{t().inputSectionLabel}
					{#if descriptionLocked}
						<!-- A label, not a control: it says why the box below does not take input. -->
						<span class="description-lock-mark"><svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="5" y="11" width="14" height="10" rx="2"></rect><path d="M8 11V7a4 4 0 0 1 8 0v4"></path></svg>{t().descriptionLockedMark}</span>
					{/if}
				</div>
				<div class="input-description">{t().inputSectionHint}</div>
			</div>
			<Tooltip placement="left" text={t().tooltipDescriptionNew}>
				<button class="ghost-btn" onclick={onClearInput}>{t().clearInputBtn}</button>
			</Tooltip>
		</div>
		<!-- The grey ranges are painted behind the textarea, which cannot colour
		     its own text. -->
		<div class="input-ta-wrap">
			<LabelHighlight text={input} />
			<textarea
				bind:value={input}
				readonly={descriptionLocked}
				rows="5"
				spellcheck="false"
				placeholder={t().inputPlaceholder}
				class="input-ta"
			></textarea>
		</div>
		{#if descriptionLocked}
			<p class="description-lock">{t().pipelineDescriptionLocked}</p>
		{/if}
		<div class="input-meta-row">
			<span class="input-comment-hint">{t().inputCommentHint}</span>
			<DescriptionMeter text={input} />
		</div>

		{@render inputSettings()}

		<div class="description-action-placeholder"><div class="description-action" use:placeIn={drawActionTarget}>
		{#if singleRunning && !hideRunStatus}
			<div class="gen-status-wrap">
			<RunStatus
				label={stageLabel || t().stageDdlGenerating}
				stage1Model={stage1ModelLabel}
				stage2Model={stage2ModelLabel}
				elapsedMs={liveMs}
				tokensIn={runTokensIn}
				tokensOut={runTokensOut}
				attempt={runAttempt}
				progress={runProgress}
				onStop={onStop}
			/>
			</div>
		{:else}
			{#if descriptionLocked}
				<!-- Drawing a held work from its description is the fork, named as such,
				     never a plain "draw" that throws the edited DDL away. -->
				<Tooltip placement="top" text={t().tooltipForkDescription}>
					<PaintButton onclick={onForkDescription} disabled={!canSubmit || generationDisabled}>{t().pipelineForkDescription}</PaintButton>
				</Tooltip>
			{:else}
				<Tooltip placement="top" text={t().tooltipSubmit}>
					<PaintButton onclick={onSubmit} disabled={!canSubmit || generationDisabled}>{t().submitBtn}</PaintButton>
				</Tooltip>
			{/if}
			{#if nextDrawParentNodeId !== null}<p class="description-parent-note">{t().nextDrawChildNotice}</p>{/if}
			{@render modelReadinessStatus()}
		{/if}
		{#if error}<p class="error-text">{error}</p>{/if}
		</div></div>
	{:else if inputMode === 'image'}
		<div class="image-pick-row">
			<input bind:this={imageInputEl} class="image-input" type="file" accept=".jpeg,.jpg,.png,.gif,.tiff,.tif,image/jpeg,image/png,image/gif,image/tiff" disabled={imageUploading || singleRunning || generationDisabled} onchange={(event) => { const file = event.currentTarget.files?.[0]; if (file) void onSelectImage(file); event.currentTarget.value = ''; }} />
			{#if uploadedImage}<img src={uploadedImage.thumbnail} alt={t().imageThumbnailAlt} /><span class="image-pick-name">{imageFileName}<small>{uploadedImage.original_width} × {uploadedImage.original_height}</small></span>{/if}
			{#if imageUploading}<span role="status">{t().imageUploading}</span>{/if}
			<button type="button" class="ghost-btn image-pick-button" class:full={!uploadedImage} disabled={imageUploading || singleRunning || generationDisabled} onclick={() => imageInputEl?.click()}>{t().imageChooseButton}</button>
		</div>
		{#if error && !uploadedImage}<p class="error-text">{error}</p>{/if}
		<label class="input-heading" for="image-provenance">{t().imageProvenanceLabel}</label>
		<textarea id="image-provenance" class="input-ta image-provenance" rows="3" bind:value={imageProvenance} oninput={() => onImageProvenanceInput?.()} placeholder={t().imageProvenanceHint}></textarea>
		{@render inputSettings()}
		<div><div class="description-action" use:placeIn={drawActionTarget}>
		{#if singleRunning && !hideRunStatus}
			<RunStatus label={stageLabel || t().imageWritingDdl} stage1Model={visionModelName} elapsedMs={liveMs} tokensIn={runTokensIn} tokensOut={runTokensOut} attempt={runAttempt} progress={runProgress} onStop={onStop} />
		{:else}
			<PaintButton onclick={onSubmitImage} disabled={!uploadedImage || imageUploading || !visionModelAvailable || generationDisabled || singleRunning}>{t().submitBtn}</PaintButton>
		{/if}
		{#if error && uploadedImage}<p class="error-text">{error}</p>{/if}
		</div></div>
	{:else if inputMode === 'batch'}
		<!-- Descriptions or pictures; locked while either side runs. Each panel puts
		     it at the right end of its own heading line. -->
		{#snippet batchSourceSwitch()}
			<span class="batch-source">
				<span class="batch-source-name" class:on={imageFolder.source === 'text'}>{t().batchSourceText}</span>
				<button
					type="button"
					class="batch-source-switch"
					role="switch"
					aria-label={t().batchSourceLabel}
					aria-checked={imageFolder.source === 'image'}
					disabled={batchRunning || batchResuming || folderRunning}
					onclick={() => imageFolder.setSource(imageFolder.source === 'image' ? 'text' : 'image')}
				><span class="batch-source-knob" aria-hidden="true"></span></button>
				<span class="batch-source-name" class:on={imageFolder.source === 'image'}>{t().batchSourceImage}</span>
			</span>
		{/snippet}
		{#if imageFolder.source === 'image'}
			<ImageFolderBatchPanel
				actionTarget={drawActionTarget}
				sourceSwitch={batchSourceSwitch}
				folder={imageFolder}
				busy={singleRunning || generationDisabled || batchRunning}
				{visionModelName}
				{visionModelAvailable}
				{stageLabel}
				{liveMs}
				{runTokensIn}
				{runTokensOut}
				{runAttempt}
				{runProgress}
				{error}
				onRun={onRunImageFolder}
				{onStop}
				settings={inputConditionRows}
			/>
		{:else}
		<BatchPanel
			actionTarget={drawActionTarget}
			sourceSwitch={batchSourceSwitch}
			settings={inputConditionRows}
			readiness={modelReadinessStatus}
			{runTokensIn}
			{runTokensOut}
			{runAttempt}
			{runProgress}
			bind:batchInput
			{lineNumbersText}
			{batchNonEmpty}
			{batchRunning}
			{batchActiveLine}
			{batchObservedLine}
			{batchRunningLineText}
			{batchSketchText}
			{batchSketchGrainLabel}
			{batchActiveDdlHighlighted}
			{batchTotal}
			{batchCurrent}
			{batchSummaryCurrent}
			{batchSummaryTotal}
			{batchStartedAt}
			{batchWorkStartedAt}
			{batchAverageWorkMs}
			{batchRetryRound}
			{batchActiveTokensIn}
			{batchActiveTokensOut}
			{batchTokensInTotal}
			{batchTokensOutTotal}
			{liveMs}
			{batchFailureReport}
			canSubmit={canSubmit && !modelReadiness}
			actionDisabled={singleRunning || generationDisabled}
			{error}
			{batchPromptHistory}
			{canResumeBatch}
			{canRetryBatchFailures}
			{batchResumeInfo}
			{batchResuming}
			{batchInterrupted}
			{batchWaitingLine}
			{batchServerLost}
			{batchSuccess}
			{onResumeBatch}
			{onRetryBatchFailures}
			{stage1ModelLabel}
			{stage2ModelLabel}
			{onRememberBatchPrompt}
			{onClearInput}
			onSubmit={onSubmit}
			onStop={onStop}
		/>
		{/if}
	{/if}
</section>

<style>
	.batch-source { display: inline-flex; flex: 0 0 auto; align-items: center; gap: 6px; font-size: var(--ui-font-size-12); font-weight: 400; white-space: nowrap; }
	.batch-source-name { color: var(--fg3); }
	.batch-source-name.on { color: var(--fg); font-weight: 600; }
	.batch-source-switch {
		position: relative; flex: 0 0 auto; width: 34px; height: 18px; padding: 0;
		border: 1px solid var(--border2); border-radius: 9px; background: var(--bg2); cursor: pointer;
	}
	.batch-source-switch:disabled { cursor: default; opacity: 0.55; }
	.batch-source-knob {
		position: absolute; top: 2px; left: 2px; width: 12px; height: 12px;
		border-radius: 50%; background: var(--fg2); transition: transform 0.15s;
	}
	.batch-source-switch[aria-checked='true'] .batch-source-knob { transform: translateX(16px); background: var(--fg); }
	.image-input { display: none; }
	.image-pick-row { display: flex; align-items: center; gap: 8px; min-height: 40px; }
	.image-pick-row img { width: 40px; height: 40px; object-fit: cover; }
	.image-pick-name { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: var(--ui-font-size-12); }
	.image-pick-name small { display: block; color: var(--fg3); }
	.image-pick-button.full { width: 100%; }
	.image-provenance { resize: none; }
	label.input-heading { font-size: var(--ui-font-size-12); font-weight: 400; }
	.panel-tabs { display: flex; border-bottom: 1px solid var(--border); }
	.panel-tabs :global(.tooltip-wrap) { flex: 1; }
	.panel-section > :global(.tooltip-wrap) { width: 100%; }
	.panel-tab {
		position: relative;
		flex: 1; padding: 10px; background: none; border: none;
		color: var(--fg3); font-size: var(--ui-font-size-12); cursor: pointer;
		font-family: inherit; border-bottom: 2px solid transparent;
		display: flex; align-items: center; justify-content: center; gap: 6px;
		min-height: 38px;
	}
	.panel-tab.active { color: var(--fg); border-bottom-color: var(--accent); }
	.panel-tab.running {
		color: var(--fg);
		background: color-mix(in srgb, var(--accent) 8%, transparent);
	}
	.panel-tab.running::before {
		content: "";
		position: absolute;
		left: 12px;
		right: 12px;
		bottom: -2px;
		height: 2px;
		background: linear-gradient(90deg, transparent, var(--accent), transparent);
		background-size: 180% 100%;
		animation: tabrun 1.1s linear infinite;
	}
	.panel-tab.active.running::before { background: var(--accent); animation: none; }
	/* Neither half of a running tab may break across lines. */
	.tab-label { line-height: 1; white-space: nowrap; }
	.tab-progress {
		line-height: 1;
		font-size: var(--ui-font-size-11);
		color: var(--fg3);
		font-variant-numeric: tabular-nums;
		text-align: center;
		/* The retry form carries a space, which is a break opportunity. */
		white-space: nowrap;
	}
	.tab-running-dot {
		width: 6px;
		height: 6px;
		border-radius: 50%;
		background: var(--accent);
		box-shadow: 0 0 0 3px color-mix(in srgb, var(--accent) 18%, transparent);
		animation: inkupulse 1s ease-in-out infinite;
	}
	.panel-section { display: flex; flex-direction: column; gap: 6px; }
	.description-action { display: flex; flex-direction: column; gap: 6px; }
	.description-action :global(.tooltip-wrap) { width: 100%; }
	.description-parent-note { margin: 0; color: var(--fg2); font-size: var(--ui-font-size-11); line-height: 1.5; }
	.conditions-heading { margin: 8px 0 2px; font-size: var(--ui-font-size-12); font-weight: 500; color: var(--fg2); }
	.conditions-head { display: flex; align-items: center; justify-content: space-between; gap: 4px; min-width: 0; }
	.invalid-vision, .invalid-vision-note { color: var(--danger); }
	.invalid-vision-note { font-size: var(--ui-font-size-10); white-space: nowrap; }
	.condition-rows {
		display: grid;
		gap: 6px;
		min-width: 0;
	}
	.condition-selection { display: flex; align-items: center; gap: 8px; min-width: 0; }
	.condition-selection > .condition-inline-label { flex: 0 0 auto; }
	.condition-selection :global(.tooltip-wrap) { flex: 0 0 auto; margin-left: auto; }
	.condition-value {
		flex: 1 1 auto;
		min-width: 0;
		color: var(--fg);
		font-size: var(--ui-font-size-12);
		line-height: 1.35;
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
	}
	.chatgpt-plan-label {
		flex: none;
		white-space: nowrap;
		color: var(--accent);
		font-size: var(--ui-font-size-11);
		line-height: 1.35;
		text-decoration: underline;
		text-underline-offset: 2px;
	}
	.condition-change { white-space: nowrap; }
	.condition-compact-rows {
		position: relative;
		display: flex;
		flex-wrap: wrap;
		gap: 6px;
	}
	/* Its bubble anchors to the chip, not to the whole row of chips. */
	.condition-inline-label {
		color: var(--fg3);
		font-size: var(--ui-font-size-11);
		line-height: 1.35;
		white-space: nowrap;
	}
	/* The route and the steps it passes sit apart from the chips below them. */
	.condition-draw {
		flex: 1 0 100%;
		min-width: 0;
		padding-bottom: 8px;
		margin-bottom: 2px;
	}
	.input-label {
		display: flex;
		align-items: flex-start;
		justify-content: space-between;
		gap: 8px;
	}
	.input-label-text { min-width: 0; }
	.input-label :global(.tooltip-wrap) { flex: none; }
	.input-heading { color: var(--fg); font-size: var(--ui-font-size-14); line-height: 1.35; font-weight: 600; }
	.input-description { margin-top: 1px; color: var(--fg2); font-size: var(--ui-font-size-12); line-height: 1.45; }
	.input-ta-wrap {
		position: relative;
		display: flex;
		/* The mirror is inset to this box, so the box has to be the textarea's. */
		background: var(--panel);
		border-radius: var(--r);
	}
	/* The textarea draws its own 1px border and the mirror has none, so the
	   grey band sat 1px up and left of its words, and wrapped 2px wider. */
	.input-ta-wrap :global(.label-mirror) { inset: 1px; }
	.input-ta {
		width: 100%; padding: 9px 10px;
		border: 1px solid var(--border2); border-radius: var(--r);
		background: transparent; color: var(--fg);
		position: relative;
		z-index: 1;
		font-family: inherit; font-size: var(--ui-font-size-14); line-height: 1.65;
		resize: vertical; outline: none;
	}
	.input-ta:focus { border-color: var(--accent); }
	.input-ta[readonly] { background: var(--bg2); color: var(--fg2); }
	.description-lock { margin: 0; font-size: var(--ui-font-size-12); line-height: 1.55; color: var(--fg2); }
	.description-lock-mark { display: inline-flex; align-items: center; gap: 4px; margin-left: 8px; color: var(--fg2); font-size: var(--ui-font-size-11); font-weight: 500; vertical-align: middle; }
	/* Held: the box reads as fixed, not as a field waiting for input. */
	.input-ta[readonly] { cursor: default; border-style: dashed; }
	.input-meta-row {
		display: flex;
		flex-wrap: wrap;
		align-items: flex-start;
		justify-content: space-between;
		gap: 2px 12px;
		margin-top: -3px;
	}
	.input-comment-hint {
		font-size: var(--ui-font-size-12);
		line-height: 1.5;
		color: var(--fg3);
	}
	.gen-status-wrap { margin-top: 4px; }
	.error-text { color: var(--danger); font-size: var(--ui-font-size-12); white-space: pre-line; }
	@keyframes inkupulse {
		0%, 100% { opacity: 1; transform: scale(1); }
		50% { opacity: 0.4; transform: scale(0.7); }
	}
	@keyframes tabrun {
		from { background-position: 180% 0; }
		to { background-position: -180% 0; }
	}
</style>
