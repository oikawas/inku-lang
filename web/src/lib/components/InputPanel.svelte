<script lang="ts">
	import { t } from '$lib/i18n/index.svelte';
	import Tooltip from './Tooltip.svelte';
	import BatchPanel from './BatchPanel.svelte';
	import CanvasAspectPlugin from './CanvasAspectPlugin.svelte';
	import DemoPanel from './DemoPanel.svelte';
	import TenkeiSelect from './TenkeiSelect.svelte';
	import { tenkeiLabel, type TenkeiLevel } from '$lib/tenkei';
	import PaintButton from './PaintButton.svelte';
	import RunStatus from './RunStatus.svelte';
	import type { DemoSettings } from '$lib/demo';
	import type { ProviderGroup } from '$lib/models';
	import type { CanvasAspectId } from '$lib/plugins/system/canvas-aspect';

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
		inputMode: 'single' | 'batch' | 'demo';
		input: string;
		batchInput: string;
		lineNumbersText: string;
		batchNonEmpty: number;
		batchRunning: boolean;
		singleRunning: boolean;
		runTokensIn: number | null;
		runTokensOut: number | null;
		singleDdlReady: boolean;
		batchActiveLine: number | null;
		batchActiveDdlHighlighted: string;
		batchTotal: number;
		batchCurrent: number;
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
		batchRandomColorCatalog: boolean;
		demoSettings: DemoSettings;
		demoModelProviderGroups: ProviderGroup[];
		demoRunning: boolean;
		demoWaitingSeconds: number | null;
		demoCurrentLiveMs: number | null;
		demoCurrentElapsedMs: number | null;
		demoCurrentTokensIn: number | null;
		demoCurrentTokensOut: number | null;
		demoTotalElapsedMs: number;
		demoTotalTokensIn: number;
		demoTotalTokensOut: number;
		demoRenderCount: number;
		demoGeneratedPrompt: string;
		demoGeneratedDdlHighlighted: string;
		demoCanSaveCurrent: boolean;
		demoSavingCurrent: boolean;
		demoSaveStatus: string | null;
		demoError: string | null;
		lockNonDemo: boolean;
		stageLabel: string;
		tenkeiLevel: TenkeiLevel;
		onSelectTenkei: (level: TenkeiLevel) => void;
		showKiwi: boolean;
		showCrab: boolean;
		canvasAspectEnabled: boolean;
		canvasAspectId: CanvasAspectId;
		canvasAspectMenuOpen: boolean;
		stage1ModelLabel: string;
		stage2ModelLabel: string;
		nextStage1Model: string;
		nextStage2Model: string;
		nextCatalogName: string;
		nextCanvasName: string;
		onToggleCanvasAspectMenu: () => void;
		onSelectCanvasAspect: (id: CanvasAspectId) => void | Promise<void>;
		onOpenModelSelection: () => void;
		onOpenCatalogModal: () => void;
		onClearInput: () => void;
		onRememberBatchPrompt: (prompt: string) => void | Promise<void>;
		onDemoSettingsChange: (settings: DemoSettings) => void | Promise<void>;
		onSaveCurrentDemo: () => void | Promise<void>;
		onStartDemo: () => void | Promise<void>;
		onStopDemo: () => void;
		onSubmit: () => void | Promise<void>;
		onStop: () => void;
	};

	let {
		inputMode = $bindable('single'),
		input = $bindable(''),
		batchInput = $bindable(''),
		lineNumbersText,
		batchNonEmpty,
		batchRunning,
		singleRunning,
		runTokensIn,
		runTokensOut,
		singleDdlReady,
		batchActiveLine,
		batchActiveDdlHighlighted,
		batchTotal,
		batchCurrent,
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
		batchRandomColorCatalog = $bindable(false),
		demoSettings = $bindable(),
		demoModelProviderGroups,
		demoRunning,
		demoWaitingSeconds,
		demoCurrentLiveMs,
		demoCurrentElapsedMs,
		demoCurrentTokensIn,
		demoCurrentTokensOut,
		demoTotalElapsedMs,
		demoTotalTokensIn,
		demoTotalTokensOut,
		demoRenderCount,
		demoGeneratedPrompt,
		demoGeneratedDdlHighlighted,
		demoCanSaveCurrent,
		demoSavingCurrent,
		demoSaveStatus,
		demoError,
		lockNonDemo,
		stageLabel,
		tenkeiLevel,
		onSelectTenkei,
		showKiwi,
		showCrab,
		canvasAspectEnabled,
		canvasAspectId,
		canvasAspectMenuOpen,
		stage1ModelLabel,
		stage2ModelLabel,
		nextStage1Model,
		nextStage2Model,
		nextCatalogName,
		nextCanvasName,
		onToggleCanvasAspectMenu,
		onSelectCanvasAspect,
		onOpenModelSelection,
		onOpenCatalogModal,
		onClearInput,
		onRememberBatchPrompt,
		onDemoSettingsChange,
		onSaveCurrentDemo,
		onStartDemo,
		onStopDemo,
		onSubmit,
		onStop,
	}: Props = $props();

	const isJapanese = $derived(t().code === 'ja');
	const randomCatalogActive = $derived(
		(inputMode === 'batch' && batchRandomColorCatalog)
		|| (inputMode === 'demo' && demoSettings.random_color_catalog)
	);

	const tabItems = $derived([
		{ mode: 'single' as const, label: t().modeSingle, running: singleRunning },
		{ mode: 'batch' as const, label: t().modeBatch, running: batchRunning },
		{ mode: 'demo' as const, label: t().modeDemo, running: demoRunning },
	]);

	const singleInputStats = $derived.by(() => {
		const source = input.trim();
		const asciiMostly = source.length > 0 && /^[\x00-\x7F\s.,;:!?()"-]+$/.test(source);
		const hasJapanese = /[\u3040-\u30ff\u3400-\u9fff]/.test(source);
		const useWords = !hasJapanese && (asciiMostly || (!source && t().code === 'en'));
		const guide = useWords ? 12 : 31;
		const count = useWords
			? (source.match(/[A-Za-z0-9]+(?:[-][A-Za-z0-9]+)*/g) ?? []).length
			: Array.from(source.replace(/\s/g, "")).length;
		return { count, guide, over: count > guide };
	});
</script>

<div class="panel-tabs">
	{#each tabItems as item (item.mode)}
		<Tooltip
			placement={item.mode === 'single' ? 'bottom-right' : item.mode === 'demo' ? 'bottom-left' : 'bottom'}
			text={item.mode === 'single' ? t().tooltipInputTabSingle : item.mode === 'batch' ? t().tooltipInputTabBatch : t().tooltipInputTabDemo}
		>
			<button
				class="panel-tab"
				class:active={inputMode === item.mode}
				class:running={item.running}
				aria-busy={item.running}
				disabled={lockNonDemo && item.mode !== 'demo'}
				onclick={() => {
					if (lockNonDemo && item.mode !== 'demo') return;
					inputMode = item.mode;
				}}
			>
				<span class="tab-label">{item.label}</span>
				{#if item.running}<span class="tab-running-dot" aria-hidden="true"></span>{/if}
			</button>
		</Tooltip>
	{/each}
</div>

<section class="panel-section">
	<div class="section-head">
		<span class="section-label">{t().inputSectionLabel}</span>
		<div class="section-actions">
			<!-- Model / catalog / staffage / canvas apply to every input mode, so the
			     button row is identical across the three tabs. -->
			<Tooltip text={t().tooltipInputModel}>
				<button class="ghost-btn" onclick={onOpenModelSelection}>{t().modelSelectButton}</button>
			</Tooltip>
			<Tooltip text={t().tooltipInputCatalog}>
				<button class="ghost-btn catalog-btn" onclick={onOpenCatalogModal}>{t().colorCatalogButton}</button>
			</Tooltip>
			<Tooltip text={t().tooltipInputTenkei}>
				<TenkeiSelect value={tenkeiLevel} {isJapanese} onSelect={onSelectTenkei} />
			</Tooltip>
			{#if canvasAspectEnabled}
				<Tooltip text={t().tooltipInputCanvas}>
					<CanvasAspectPlugin
						selected={canvasAspectId}
						open={canvasAspectMenuOpen}
						onToggle={onToggleCanvasAspectMenu}
						onSelect={onSelectCanvasAspect}
					/>
				</Tooltip>
			{/if}
			{#if inputMode !== 'demo'}
				<Tooltip placement="left" text={t().tooltipInputClear}>
					<button class="ghost-btn create-btn" onclick={onClearInput}>{t().clearInputBtn}</button>
				</Tooltip>
			{/if}
		</div>
	</div>

	<div class="current-selection" aria-label={isJapanese ? '現在選択中の設定' : 'Current selection'}>
		<span class="cs-group">
			<span class="cs-label">{isJapanese ? 'モデル' : 'Model'}</span>
			{#if nextStage1Model === nextStage2Model}
				<span class="cs-value" title={nextStage1Model}>{nextStage1Model}</span>
			{:else}
				<span class="cs-sub">{isJapanese ? '解釈' : 'Interpretation'}</span>
				<span class="cs-value" title={nextStage1Model}>{nextStage1Model}</span>
				<span class="cs-sub">{isJapanese ? '描画' : 'Rendering'}</span>
				<span class="cs-value" title={nextStage2Model}>{nextStage2Model}</span>
			{/if}
		</span>
		{#if inputMode === 'demo'}
			<span class="cs-divider"></span>
			<span class="cs-group">
				<span class="cs-label">{isJapanese ? '指示生成' : 'Instruction'}</span>
				<span class="cs-value" title={demoSettings.prompt_model}>{demoSettings.prompt_model}</span>
			</span>
		{/if}
		<span class="cs-divider"></span>
		<span class="cs-group">
			<span class="cs-label">{isJapanese ? '色カタログ' : 'Catalog'}</span>
			<!-- Batch and demo can randomise the catalog per line / per loop, in which
			     case the picked catalog is not knowable in advance. -->
			{#if randomCatalogActive}
				<span class="cs-value">{t().batchRandomColorCatalog}</span>
			{:else}
				<span class="cs-value" title={nextCatalogName}>{nextCatalogName}</span>
			{/if}
		</span>
		<span class="cs-divider"></span>
		<span class="cs-group">
			<span class="cs-label">{isJapanese ? '添景' : 'Staffage'}</span>
			<span class="cs-value">{tenkeiLabel(tenkeiLevel, isJapanese)}</span>
		</span>
		<span class="cs-divider"></span>
		<span class="cs-group">
			<span class="cs-label">{isJapanese ? 'キャンバス' : 'Canvas'}</span>
			<span class="cs-value" title={nextCanvasName}>{nextCanvasName}</span>
		</span>
	</div>

	{#if inputMode === 'single'}
		<textarea
			bind:value={input}
			rows="5"
			spellcheck="false"
			placeholder={t().inputPlaceholder}
			class="input-ta"
		></textarea>
		<div class="input-meter" class:soft-over={singleInputStats.over} aria-hidden="true">{singleInputStats.count} / {singleInputStats.guide}</div>

		{#if singleRunning}
			<div class="gen-status-wrap">
			<RunStatus
				label={stageLabel || t().stageDdlGenerating}
				stage1Model={stage1ModelLabel}
				stage2Model={stage2ModelLabel}
				elapsedMs={liveMs}
				tokensIn={runTokensIn}
				tokensOut={runTokensOut}
				onStop={onStop}
			/>
			</div>
		{:else}
			<Tooltip placement="top" text={t().tooltipSubmit}>
				<PaintButton onclick={onSubmit} disabled={!canSubmit || generationDisabled}>{t().submitBtn}</PaintButton>
			</Tooltip>
		{/if}

		{#if error}<p class="error-text">{error}</p>{/if}
	{:else if inputMode === 'batch'}
		<BatchPanel
			{runTokensIn}
			{runTokensOut}
			bind:batchInput
			{lineNumbersText}
			{batchNonEmpty}
			{batchRunning}
			{batchActiveLine}
			{batchActiveDdlHighlighted}
			{batchTotal}
			{batchCurrent}
			{batchActiveTokensIn}
			{batchActiveTokensOut}
			{batchTokensInTotal}
			{batchTokensOutTotal}
			{liveMs}
			{batchFailureReport}
			{canSubmit}
			actionDisabled={singleRunning || generationDisabled}
			{error}
			{batchPromptHistory}
			bind:randomColorCatalog={batchRandomColorCatalog}
			{showCrab}
			{stage1ModelLabel}
			{stage2ModelLabel}
			{onRememberBatchPrompt}
			onSubmit={onSubmit}
			onStop={onStop}
		/>
	{:else}
		<DemoPanel
			{runTokensIn}
			{runTokensOut}
			bind:settings={demoSettings}
			providerGroups={demoModelProviderGroups}
			running={demoRunning}
			{liveMs}
			waitingSeconds={demoWaitingSeconds}
			currentLiveMs={demoCurrentLiveMs}
			currentElapsedMs={demoCurrentElapsedMs}
			currentTokensIn={demoCurrentTokensIn}
			currentTokensOut={demoCurrentTokensOut}
			totalElapsedMs={demoTotalElapsedMs}
			totalTokensIn={demoTotalTokensIn}
			totalTokensOut={demoTotalTokensOut}
			{demoRenderCount}
			generatedPrompt={demoGeneratedPrompt}
			generatedDdlHighlighted={demoGeneratedDdlHighlighted}
			canSaveCurrent={demoCanSaveCurrent}
			savingCurrent={demoSavingCurrent}
			actionDisabled={singleRunning || generationDisabled}
			drawingStage1ModelLabel={stage1ModelLabel}
			drawingStage2ModelLabel={stage2ModelLabel}
			saveStatus={demoSaveStatus}
			error={demoError}
			onSettingsChange={onDemoSettingsChange}
			onSaveCurrent={onSaveCurrentDemo}
			onStart={onStartDemo}
			onStop={onStopDemo}
		/>
	{/if}
</section>

<style>
	.panel-tabs { display: flex; border-bottom: 1px solid var(--border); }
	.panel-tabs :global(.tooltip-wrap) { flex: 1; }
	.panel-section > :global(.tooltip-wrap) { width: 100%; }
	.panel-tab {
		position: relative;
		flex: 1; padding: 10px; background: none; border: none;
		color: var(--fg3); font-size: 12px; cursor: pointer;
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
	.panel-tab:disabled { opacity: 0.38; cursor: not-allowed; }
	.tab-label { line-height: 1; }
	.tab-running-dot {
		width: 6px;
		height: 6px;
		border-radius: 50%;
		background: var(--accent);
		box-shadow: 0 0 0 3px color-mix(in srgb, var(--accent) 18%, transparent);
		animation: inkupulse 1s ease-in-out infinite;
	}
	.panel-section { display: flex; flex-direction: column; gap: 6px; }
	.section-head {
		display: flex;
		justify-content: space-between;
		align-items: center;
	}
	.section-label {
		font-size: 12px; font-weight: 600; letter-spacing: 0.04em;
		color: var(--fg2);
	}
	.section-actions { display: flex; gap: 5px; min-width: 0; }
	.ghost-btn {
		padding: var(--btn-sm-padding);
		border: 1px solid var(--border2);
		border-radius: var(--btn-sm-radius);
		background: var(--panel);
		color: var(--fg2);
		font-size: var(--btn-sm-font-size);
		cursor: pointer;
		font-family: inherit;
		white-space: nowrap;
	}
	.ghost-btn:hover { background: var(--bg2); }
	.catalog-btn {
		display: inline-block;
		max-width: 128px;
		overflow: hidden;
		text-overflow: ellipsis;
		vertical-align: bottom;
	}
	.create-btn {
		background: #fff7e8;
		border-color: #d8b36a;
		color: #6c4a10;
		font-weight: 600;
		box-shadow: 0 1px 3px rgba(108,74,16,0.12);
	}
	.create-btn:hover {
		background: #ffefd0;
		border-color: #bd8f34;
		color: #4f360b;
	}
	.current-selection {
		display: flex;
		align-items: center;
		flex-wrap: wrap;
		gap: 6px 10px;
		padding: 6px 9px;
		border: 1px solid var(--border);
		border-radius: var(--r);
		background: var(--bg2);
		font-size: 11px;
		line-height: 1;
		min-width: 0;
	}
	.cs-group {
		display: inline-flex;
		align-items: center;
		gap: 5px;
		min-width: 0;
	}
	.cs-label { color: var(--fg3); flex-shrink: 0; }
	.cs-sub { color: var(--fg3); flex-shrink: 0; font-size: 10px; }
	.cs-value {
		min-width: 0;
		overflow-wrap: anywhere;
		color: #4d5f86;
		font-weight: 500;
	}
	:global(html[data-theme='dark']) .cs-value { color: #a9c0ee; }
	.cs-divider {
		width: 1px;
		height: 12px;
		background: var(--border2);
		flex-shrink: 0;
	}
	.input-ta {
		width: 100%; padding: 9px 10px;
		border: 1px solid var(--border2); border-radius: var(--r);
		background: var(--panel); color: var(--fg);
		font-family: inherit; font-size: 13px; line-height: 1.65;
		resize: vertical; outline: none;
	}
	.input-ta:focus { border-color: var(--accent); }
	.input-meter {
		align-self: flex-end;
		min-width: 54px;
		min-height: 16px;
		margin-top: -3px;
		font-size: 10px;
		line-height: 16px;
		font-variant-numeric: tabular-nums;
		text-align: right;
		color: color-mix(in srgb, var(--fg3) 68%, transparent);
	}
	.input-meter.soft-over { color: color-mix(in srgb, var(--fg) 78%, transparent); }
	.gen-status-wrap { margin-top: 8px; }
	.error-text { color: var(--danger); font-size: 12px; white-space: pre-line; }
	@keyframes inkupulse {
		0%, 100% { opacity: 1; transform: scale(1); }
		50% { opacity: 0.4; transform: scale(0.7); }
	}
	@keyframes tabrun {
		from { background-position: 180% 0; }
		to { background-position: -180% 0; }
	}
</style>
