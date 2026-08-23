<script lang="ts">
	import OutputTabsContent from '$lib/components/OutputTabsContent.svelte';
	import Tooltip from '$lib/components/Tooltip.svelte';
	import { colorMapEntries, colorWordLabel, type ColorMap } from '$lib/colors';
	import type { ComposeFallbackState } from '$lib/composeFallback';
	import { derivationKindLabel } from '$lib/derivation';
	import type { DrawerTab } from '$lib/drawerScroll';
	import { formatByteSize, groupDigits } from '$lib/formatNumber';
	import { hashDigest, hashRowLabel } from '$lib/hashIdentity';
	import { t } from '$lib/i18n/index.svelte';
	import { normalizeSketchGrain, normalizeSketchState, sketchModeLabel, sketchStateNote } from '$lib/sketch';
	import type { SvgWeight } from '$lib/svgWeight';

	type PromptsData = { stage1_system: string; stage2_system: string };

	export type GenerationInfoWork = {
		note?: string | null;
		description_hash?: string | null;
		render_hash?: string | null;
		render_build_number?: string | null;
		render_engine_version?: string | null;
		ddl_version?: string | null;
		ddl_engine_version?: string | null;
		render_seed?: number | string | null;
		render_wild?: boolean | null;
		seed_text?: string | null;
		focus?: string | null;
		composition_seed?: number | string | null;
		interpretation_seed?: string | null;
		variation_amplitude?: string | null;
		variation_seed?: number | string | null;
		stage1_prompt_digest?: string | null;
		stage1_prompt_base_digest?: string | null;
		stage2_prompt_digest?: string | null;
		render_color_map?: ColorMap | null;
		render_canvas_aspect_ratio?: number | null;
		derivation_kind?: string | null;
		batch_run_id?: string | null;
		batch_line_number?: number | null;
		instruction_lang_requested?: string | null;
		instruction_lang_resolved?: string | null;
		ui_lang?: string | null;
		sketch_grain?: string | null;
		sketch_state?: string | null;
		derivation_metadata?: Record<string, unknown>;
		elapsed_ms?: number | null;
		elapsed_total_ms?: number | null;
		tokens_in?: number | null;
		tokens_out?: number | null;
		tokens_in_stage1?: number | null;
		tokens_out_stage1?: number | null;
		tokens_in_stage2?: number | null;
		tokens_out_stage2?: number | null;
	};

	type Props = {
		open: boolean;
		tab: DrawerTab;
		drawerEl?: HTMLElement | null;
		detailsScrollEl?: HTMLElement | null;
		tabsScrollEl?: HTMLElement | null;
		result: GenerationInfoWork | null;
		statusHistoryItem: GenerationInfoWork | null;
		isJapanese: boolean;
		developerMode: boolean;
		statusTenkei: string | null;
		statusGeneration: number | null;
		statusStage1Model: string;
		statusStage2Model: string;
		statusCatalogName: string;
		statusCanvasName: string;
		currentRenderedAt: string | null;
		interpretFallbackReason: string | null;
		composeFallbackRecord: ComposeFallbackState;
		composeFallbackDrawnReason: string | null;
		detailSvgWeight: SvgWeight | null;
		detailSvgBytes: number | null;
		statusHashLabel: string;
		statusHashCopied: boolean;
		promptsData: PromptsData | null;
		stage1PromptText: string;
		ddl: string | null;
		promptStage1Expanded: boolean;
		promptStage2Expanded: boolean;
		copiedPrompt: 'stage1' | 'stage2' | 'score' | null;
		scoreJsonText: string;
		scoreJsonLines: string[];
		scoreJsonHighlighted: string;
		scoreJsonSeparatorLine: number | null;
		onClose: () => void;
		onCopyStatusHash: () => void | Promise<void>;
		onCopyPromptText: (kind: 'stage1' | 'stage2' | 'score', text: string | null | undefined) => void | Promise<void>;
	};

	let {
		open,
		tab = $bindable('details'),
		drawerEl = $bindable(null),
		detailsScrollEl = $bindable(null),
		tabsScrollEl = $bindable(null),
		result,
		statusHistoryItem,
		isJapanese,
		developerMode,
		statusTenkei,
		statusGeneration,
		statusStage1Model,
		statusStage2Model,
		statusCatalogName,
		statusCanvasName,
		currentRenderedAt,
		interpretFallbackReason,
		composeFallbackRecord,
		composeFallbackDrawnReason,
		detailSvgWeight,
		detailSvgBytes,
		statusHashLabel,
		statusHashCopied,
		promptsData,
		stage1PromptText,
		ddl,
		promptStage1Expanded = $bindable(false),
		promptStage2Expanded = $bindable(false),
		copiedPrompt,
		scoreJsonText,
		scoreJsonLines,
		scoreJsonHighlighted,
		scoreJsonSeparatorLine,
		onClose,
		onCopyStatusHash,
		onCopyPromptText
	}: Props = $props();

	const detailRenderSeed = $derived(statusHistoryItem?.render_seed ?? result?.render_seed ?? null);
	const detailVarySeed = $derived(statusHistoryItem?.composition_seed ?? result?.composition_seed ?? null);
	const detailInterpretationSeed = $derived(statusHistoryItem?.interpretation_seed ?? result?.interpretation_seed ?? null);
	// The stored form is `<scheme>:<digest>`. The scheme is named in the row's
	// label and the digest stands alone in the cell, so the value shown is the
	// value copied. See $lib/hashIdentity.
	const storedDescriptionHash = $derived(statusHistoryItem?.description_hash ?? result?.description_hash ?? '');
	const storedRenderHash = $derived(statusHistoryItem?.render_hash ?? result?.render_hash ?? '');
	const detailDescriptionHash = $derived(hashDigest(storedDescriptionHash));
	const detailRenderHash = $derived(hashDigest(storedRenderHash));
	const detailDescriptionHashLabel = $derived(hashRowLabel('description hash', storedDescriptionHash));
	const detailRenderHashLabel = $derived(hashRowLabel('render hash', storedRenderHash));
	const detailEngineVersion = $derived(statusHistoryItem?.render_engine_version ?? result?.render_engine_version ?? '');
	const detailDdlVersion = $derived(statusHistoryItem?.ddl_version ?? result?.ddl_version ?? '');
	const detailDdlEngineVersion = $derived(statusHistoryItem?.ddl_engine_version ?? result?.ddl_engine_version ?? '');
	const detailBuild = $derived(statusHistoryItem?.render_build_number ?? result?.render_build_number ?? '');
	const detailDerivationMetadata = $derived(statusHistoryItem?.derivation_metadata ?? result?.derivation_metadata ?? {});
	const detailResolvedLang = $derived(statusHistoryItem?.instruction_lang_resolved ?? result?.instruction_lang_resolved ?? '');
	const detailStage1Lang = $derived(typeof detailDerivationMetadata.stage1_language === 'string' ? detailDerivationMetadata.stage1_language : detailResolvedLang);
	const detailStage2Lang = $derived(typeof detailDerivationMetadata.stage2_language === 'string' ? detailDerivationMetadata.stage2_language : detailResolvedLang);
	const displayLanguageName = (lang: string) => lang === 'ja' ? (isJapanese ? '日本語' : 'Japanese') : lang === 'en' ? 'English' : lang || '-';
	const detailElapsedMs = $derived(statusHistoryItem?.elapsed_ms ?? result?.elapsed_total_ms ?? null);
	const detailTokensIn = $derived(statusHistoryItem?.tokens_in ?? ((result?.tokens_in_stage1 ?? 0) + (result?.tokens_in_stage2 ?? 0) || null));
	const detailTokensOut = $derived(statusHistoryItem?.tokens_out ?? ((result?.tokens_out_stage1 ?? 0) + (result?.tokens_out_stage2 ?? 0) || null));
	const detailRequestedLang = $derived(statusHistoryItem?.instruction_lang_requested ?? result?.instruction_lang_requested ?? '');
	const detailUiLang = $derived(statusHistoryItem?.ui_lang ?? result?.ui_lang ?? '');
	const detailFocus = $derived(statusHistoryItem?.focus ?? result?.focus ?? '');
	const detailSeedText = $derived(statusHistoryItem?.seed_text ?? result?.seed_text ?? '');
	// Null predates the Wild field and is different from an explicit Off.
	const detailWild = $derived(statusHistoryItem?.render_wild ?? result?.render_wild ?? null);
	const detailVariationAmplitude = $derived(statusHistoryItem?.variation_amplitude ?? result?.variation_amplitude ?? '');
	const detailVariationSeed = $derived(statusHistoryItem?.variation_seed ?? result?.variation_seed ?? null);
	// Sketch from life (Stage 0.5) records both what the layer did (fine, coarse,
	// fallback, off, or not applicable) and the requested grain. The prose the
	// layer wrote is deliberately absent here because the describe panel already
	// gives it enough room. A missing state belongs to work drawn before the field
	// existed and is not Off, so absence keeps its own sentence.
	const detailSketchState = $derived(normalizeSketchState(statusHistoryItem?.sketch_state ?? result?.sketch_state));
	const detailSketchGrain = $derived(
		detailSketchState === 'fine' || detailSketchState === 'coarse'
			? detailSketchState
			: normalizeSketchGrain(statusHistoryItem?.sketch_grain ?? result?.sketch_grain)
	);
	// Plain fine and coarse runs need no note because the grain row says enough.
	const detailSketchNote = $derived(sketchStateNote(detailSketchState, isJapanese));
	// An empty canvas has no work to report; it is not a pre-field historical work.
	const hasSketchDetails = $derived(!!(statusHistoryItem ?? result));
	// The colors this work was actually drawn in are authoritative here. The
	// catalog names the table, while this is the row the work retained; an empty
	// list means no map was recorded, not that nine defaults were used.
	const detailColorMap = $derived(colorMapEntries(statusHistoryItem?.render_color_map ?? result?.render_color_map));
	const detailCanvasRatio = $derived(statusHistoryItem?.render_canvas_aspect_ratio ?? result?.render_canvas_aspect_ratio ?? null);
	const detailStage1PromptDigest = $derived(statusHistoryItem?.stage1_prompt_digest ?? result?.stage1_prompt_digest ?? '');
	const detailStage1PromptBaseDigest = $derived(statusHistoryItem?.stage1_prompt_base_digest ?? result?.stage1_prompt_base_digest ?? '');
	const detailStage2PromptDigest = $derived(statusHistoryItem?.stage2_prompt_digest ?? result?.stage2_prompt_digest ?? '');
	const detailDerivationKind = $derived(statusHistoryItem?.derivation_kind ?? result?.derivation_kind ?? null);
	const detailBatchRunId = $derived(statusHistoryItem?.batch_run_id ?? '');
	const detailBatchLine = $derived(statusHistoryItem?.batch_line_number ?? null);
	const detailNote = $derived((statusHistoryItem?.note ?? '').trim());
	const variationAmplitudeLabel = (amplitude: string) =>
		amplitude === 'small' ? t().variationSmall
		: amplitude === 'medium' ? t().variationMedium
		: amplitude === 'large' ? t().variationLarge
		: amplitude;
	// Hide provenance when the work has no lineage, derivation, batch, or note.
	const hasOriginDetails = $derived(
		statusGeneration != null || detailDerivationKind != null || !!detailBatchRunId || !!detailNote
	);
</script>

<aside
	bind:this={drawerEl}
	class="generation-info"
	class:open
	aria-hidden={!open}
	aria-label={isJapanese ? '生成情報' : 'Provenance'}
>
	<header class="generation-info-head">
		<strong>{isJapanese ? '生成情報' : 'Provenance'}</strong>
		<button type="button" class="generation-info-close" onclick={onClose} aria-label="Close">&times;</button>
	</header>
	<div class="generation-info-tabs" role="tablist">
		<button type="button" role="tab" aria-selected={tab === 'details'} class:active={tab === 'details'} onclick={() => (tab = 'details')}>{isJapanese ? '詳細' : 'Details'}</button>
		<button type="button" role="tab" aria-selected={tab === 'prompts'} class:active={tab === 'prompts'} onclick={() => (tab = 'prompts')}>{t().tabPrompts}</button>
		<button type="button" role="tab" aria-selected={tab === 'score'} class:active={tab === 'score'} onclick={() => (tab = 'score')}>{t().tabScore}</button>
	</div>
	<div class="generation-info-content">
		{#if tab === 'details'}
			{#snippet term(label: string, hint: string)}
				<dt><Tooltip placement="right" text={hint}><span>{label}</span></Tooltip></dt>
			{/snippet}
			<div class="generation-details" bind:this={detailsScrollEl}>
				{#if hasSketchDetails}
					<section class="detail-group">
						<h4>{t().sketchLabel}</h4>
						<dl>
							{#if detailSketchGrain}
								{@render term(t().sketchGrainLabel, t().provenanceHintSketchGrain)}<dd>{sketchModeLabel(detailSketchGrain, isJapanese)}</dd>
							{/if}
							{#if detailSketchNote}
								{@render term(t().provenanceLabelSketchRecord, t().provenanceHintSketchRecord)}<dd>{detailSketchNote}</dd>
							{/if}
						</dl>
					</section>
				{/if}
				<section class="detail-group">
					<h4>{t().provenanceSectionInterpretation}</h4>
					<dl>
						{@render term(`Stage 1 (${isJapanese ? '解釈' : 'Interpretation'})`, t().provenanceHintStage1Model)}<dd>{statusStage1Model}</dd>
						{@render term(`Stage 1 ${isJapanese ? '言語' : 'Language'}`, t().provenanceHintStage1Lang)}<dd>{displayLanguageName(detailStage1Lang)}</dd>
						{@render term(t().provenanceLabelLangRequested, t().provenanceHintLangRequested)}<dd>{detailRequestedLang ? displayLanguageName(detailRequestedLang) : '-'}</dd>
						{@render term(isJapanese ? '解釈 seed' : 'Interpretation seed', t().provenanceHintInterpretationSeed)}<dd>{detailInterpretationSeed ?? '-'}</dd>
						{#if interpretFallbackReason}
							{@render term(t().provenanceLabelInterpretFallback, t().provenanceHintInterpretFallback)}<dd>{interpretFallbackReason}</dd>
						{/if}
						<!-- Always shown in three states: an unrecorded value is itself a fact.
						     Hiding it would make older work look as though compose succeeded. -->
						{@render term(t().provenanceLabelComposeFallback, t().provenanceHintComposeFallback)}<dd>{t().composeFallbackRecord(composeFallbackRecord)}{composeFallbackDrawnReason ? ` (${composeFallbackDrawnReason})` : ''}</dd>
					</dl>
				</section>
				<section class="detail-group">
					<h4>{t().provenanceSectionPerformance}</h4>
					<dl>
						{@render term(`Stage 2 (${isJapanese ? '描画' : 'Performance'})`, t().provenanceHintStage2Model)}<dd>{statusStage2Model}</dd>
						{@render term(`Stage 2 ${isJapanese ? '言語' : 'Language'}`, t().provenanceHintStage2Lang)}<dd>{displayLanguageName(detailStage2Lang)}</dd>
						{@render term(t().provenanceLabelFocus, t().provenanceHintFocus)}<dd>{detailFocus || '-'}</dd>
						{#if detailVariationAmplitude}
							{@render term(t().provenanceLabelVariation, t().provenanceHintVariation)}<dd>{variationAmplitudeLabel(detailVariationAmplitude)}</dd>
						{/if}
						{#if detailVariationSeed != null}
							{@render term(t().provenanceLabelVariationSeed, t().provenanceHintVariationSeed)}<dd>{detailVariationSeed}</dd>
						{/if}
						{@render term(isJapanese ? '配置 seed' : 'Composition seed', t().provenanceHintCompositionSeed)}<dd>{detailVarySeed ?? t().seedBaseLabel}</dd>
						{@render term('render seed', t().provenanceHintRenderSeed)}<dd>{detailRenderSeed ?? '-'}</dd>
						{@render term(t().provenanceLabelSeedText, t().provenanceHintSeedText)}<dd>{detailSeedText || '-'}</dd>
						{@render term(t().provenanceLabelWild, t().provenanceHintWild)}<dd>{detailWild == null ? t().historyVersionNotRecorded : detailWild ? t().provenanceWildOn : t().provenanceWildOff}</dd>
						<!-- Works drawn before the staffage axis was retired retain their level.
						     New work records none, so only past work in developer mode shows it. -->
						{#if developerMode && statusTenkei}
							<dt><span>{isJapanese ? '添景' : 'Staffage'}</span></dt><dd>{statusTenkei}</dd>
						{/if}
						{@render term(isJapanese ? '色カタログ' : 'Color catalog', t().provenanceHintCatalog)}<dd>{statusCatalogName}</dd>
						{#if detailColorMap.length > 0}
							{@render term(t().provenanceLabelColorMap, t().provenanceHintColorMap)}<dd class="detail-color-map">
								{#each detailColorMap as entry (entry.key)}
									<span class="color-map-entry" title={entry.code}>
										<span class="color-map-chip" style="background: {entry.code}"></span>{colorWordLabel(entry.key, isJapanese)}
									</span>
								{/each}
							</dd>
						{/if}
						{@render term(isJapanese ? 'キャンバス' : 'Canvas', t().provenanceHintCanvas)}<dd>{statusCanvasName}</dd>
						{@render term(t().provenanceLabelCanvasRatio, t().provenanceHintCanvasRatio)}<dd>{detailCanvasRatio == null ? '-' : detailCanvasRatio.toFixed(3)}</dd>
						{@render term(isJapanese ? 'SVG サイズ' : 'SVG size', t().provenanceHintSvgSize)}<dd>{formatByteSize(detailSvgBytes)}</dd>
						{@render term(isJapanese ? 'SVG オブジェクト数' : 'SVG objects', t().provenanceHintSvgObjects)}<dd>{detailSvgWeight ? groupDigits(detailSvgWeight.objects) : '-'}</dd>
						{@render term(isJapanese ? 'SVG 点数' : 'SVG points', t().provenanceHintSvgPoints)}<dd>{detailSvgWeight ? groupDigits(detailSvgWeight.points) : '-'}</dd>
					</dl>
				</section>
				<section class="detail-group">
					<h4>{t().provenanceSectionIdentity}</h4>
					<dl>
						{@render term(detailRenderHashLabel, t().provenanceHintRenderHash)}<dd class="detail-copy-row"><code>{detailRenderHash || '-'}</code><button type="button" disabled={!statusHashLabel} onclick={onCopyStatusHash}>{statusHashCopied ? t().promptCopied : t().promptCopy}</button></dd>
						{@render term(detailDescriptionHashLabel, t().provenanceHintDescriptionHash)}<dd><code>{detailDescriptionHash || '-'}</code></dd>
						{@render term('Render engine version', t().provenanceHintRenderEngine)}<dd>{detailEngineVersion || '-'}</dd>
						{@render term(t().provenanceLabelDdlSpec, t().provenanceHintDdlSpec)}<dd>{detailDdlVersion || t().historyVersionNotRecorded}</dd>
						{@render term(t().provenanceLabelTransformLayer, t().provenanceHintTransformLayer)}<dd>{detailDdlEngineVersion || t().historyVersionNotRecorded}</dd>
						{@render term(t().provenanceLabelStage1PromptDigest, t().provenanceHintStage1PromptDigest)}<dd><code>{detailStage1PromptDigest || t().historyVersionNotRecorded}</code></dd>
						{@render term(t().provenanceLabelStage1PromptBaseDigest, t().provenanceHintStage1PromptBaseDigest)}<dd><code>{detailStage1PromptBaseDigest || t().historyVersionNotRecorded}</code></dd>
						{@render term(t().provenanceLabelStage2PromptDigest, t().provenanceHintStage2PromptDigest)}<dd><code>{detailStage2PromptDigest || t().historyVersionNotRecorded}</code></dd>
						{@render term('Build', t().provenanceHintBuild)}<dd>{detailBuild || '-'}</dd>
					</dl>
				</section>
				{#if hasOriginDetails}
					<section class="detail-group">
						<h4>{t().provenanceSectionOrigin}</h4>
						<dl>
							{#if statusGeneration != null}
								{@render term(t().provenanceLabelGeneration, t().provenanceHintGeneration)}<dd>{statusGeneration}</dd>
							{/if}
							{@render term(t().provenanceLabelDerivation, t().provenanceHintDerivation)}<dd>{derivationKindLabel(detailDerivationKind, isJapanese)}</dd>
							{#if detailBatchRunId}
								{@render term(t().provenanceLabelBatchRun, t().provenanceHintBatchRun)}<dd><code>{detailBatchRunId}</code></dd>
							{/if}
							{#if detailBatchLine != null}
								{@render term(t().provenanceLabelBatchLine, t().provenanceHintBatchLine)}<dd>{detailBatchLine}</dd>
							{/if}
							{#if detailNote}
								{@render term(t().provenanceLabelComment, t().provenanceHintComment)}<dd class="detail-note">{detailNote}</dd>
							{/if}
						</dl>
					</section>
				{/if}
				<section class="detail-group">
					<h4>{t().provenanceSectionRun}</h4>
					<dl>
						{@render term(isJapanese ? '作成日' : 'Created', t().provenanceHintCreated)}<dd>{currentRenderedAt ?? '-'}</dd>
						{@render term(isJapanese ? '処理時間' : 'Elapsed', t().provenanceHintElapsed)}<dd>{detailElapsedMs == null ? '-' : (detailElapsedMs / 1000).toFixed(1) + 's'}</dd>
						{@render term('tokens in / out', t().provenanceHintTokens)}<dd>{detailTokensIn == null ? '-' : groupDigits(detailTokensIn)} / {detailTokensOut == null ? '-' : groupDigits(detailTokensOut)}</dd>
						{@render term(t().provenanceLabelUiLang, t().provenanceHintUiLang)}<dd>{detailUiLang ? displayLanguageName(detailUiLang) : '-'}</dd>
					</dl>
				</section>
			</div>
		{:else}
			<OutputTabsContent
				bind:scrollEl={tabsScrollEl}
				outputTab={tab}
				{promptsData}
				{stage1PromptText}
				{ddl}
				bind:promptStage1Expanded
				bind:promptStage2Expanded
				{copiedPrompt}
				{scoreJsonText}
				{scoreJsonLines}
				{scoreJsonHighlighted}
				{scoreJsonSeparatorLine}
				{onCopyPromptText}
			/>
		{/if}
	</div>
</aside>

<style>
	/* Open and close like the saijiki drawer: reveal from the right edge over the
	   same 0.25s and curve while the content stands still.

	   Saijiki animates a wrapper around a fixed 460px inner box. This drawer is
	   responsive -- min(760px, 100% - 72px) -- so an inner percentage resolves
	   against the wrapper while it is changing and leaves a gap. Clipping reveals
	   the responsive box itself without a second box or content reflow. */
	.generation-info {
		position: absolute;
		z-index: 90;
		top: 41px;
		right: 0;
		bottom: 49px;
		box-sizing: border-box;
		width: min(760px, calc(100% - 72px));
		display: flex;
		flex-direction: column;
		background: var(--bg);
		border-left: 1px solid var(--border2);
		box-shadow: -14px 0 34px rgba(0, 0, 0, .18);
		clip-path: inset(0 0 0 100%);
		pointer-events: none;
		transition: clip-path 0.25s cubic-bezier(0.4, 0, 0.2, 1);
	}
	.generation-info.open { clip-path: inset(0 0 0 0); pointer-events: all; }
	.generation-info-head { height: 44px; flex: 0 0 auto; display: flex; align-items: center; justify-content: space-between; padding: 0 12px 0 16px; border-bottom: 1px solid var(--border); }
	.generation-info-head strong { font-size: 13px; font-weight: 600; }
	.generation-info-close { width: 30px; height: 30px; border: 0; border-radius: 6px; background: transparent; color: var(--fg2); font-size: 20px; cursor: pointer; }
	.generation-info-close:hover { background: var(--bg2); color: var(--fg); }
	.generation-info-tabs { flex: 0 0 auto; display: flex; padding: 0 12px; border-bottom: 1px solid var(--border); }
	.generation-info-tabs button { padding: 9px 14px 8px; border: 0; border-bottom: 2px solid transparent; background: transparent; color: var(--fg2); font: inherit; font-size: 12px; cursor: pointer; }
	.generation-info-tabs button.active { border-bottom-color: var(--fg); color: var(--fg); font-weight: 600; }
	.generation-info-content { min-height: 0; flex: 1; display: flex; padding: 10px; overflow: hidden; }
	.generation-details { width: 100%; overflow: auto; padding: 8px 10px; }
	.detail-group + .detail-group { margin-top: 16px; padding-top: 12px; border-top: 1px solid var(--border); }
	.detail-group h4 { margin: 0 0 8px; color: var(--fg2); font-size: 11px; font-weight: 600; letter-spacing: .04em; }
	.generation-details dl { display: grid; grid-template-columns: minmax(120px, auto) minmax(0, 1fr); gap: 10px 16px; margin: 0; font-size: 12px; }
	.generation-details dt { min-width: 0; color: var(--fg3); }
	.generation-details dt :global(.tooltip-wrap) { max-width: 100%; }
	.detail-note { white-space: pre-wrap; }
	/* The recorded color words are displayed as chip-and-word pairs, so each chip
	   travels with its label instead of reading as an unrelated run of swatches. */
	.detail-color-map { display: flex; flex-wrap: wrap; gap: 4px 10px; }
	.color-map-entry { display: inline-flex; align-items: center; gap: 4px; }
	.color-map-chip { width: 11px; height: 11px; border-radius: 2px; border: 1px solid var(--border2); flex-shrink: 0; }
	.generation-details dd { min-width: 0; margin: 0; color: var(--fg); overflow-wrap: anywhere; }
	.generation-details code { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 11px; }
	.detail-copy-row { display: flex; align-items: flex-start; gap: 8px; }
	.detail-copy-row code { min-width: 0; flex: 1; }
	.detail-copy-row button { flex: 0 0 auto; border: 1px solid var(--border2); border-radius: 5px; padding: 3px 7px; background: var(--panel); color: var(--fg2); font: inherit; font-size: 10px; cursor: pointer; }

	@media (max-width: 720px) {
		.generation-info { top: 68px; }
	}
</style>
