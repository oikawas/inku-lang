<script lang="ts">
	import { t } from '$lib/i18n/index.svelte';
	import BatchPanel from './BatchPanel.svelte';
	import CanvasAspectPlugin from './CanvasAspectPlugin.svelte';
	import DemoPanel from './DemoPanel.svelte';
	import DdlEditPanel from './DdlEditPanel.svelte';
	import KiwiMascot from './KiwiMascot.svelte';
	import PaintButton from './PaintButton.svelte';
	import StopButton from './StopButton.svelte';
	import type { DemoSettings } from '$lib/demo';
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
	type SaijikiPreview = {
		categoryKey: string;
		word: string;
		canonicalWord: string;
		effect: string;
		example: string;
		svg: string;
	};

	type Props = {
		inputMode: 'single' | 'ddl' | 'batch' | 'demo';
		input: string;
		batchInput: string;
		ddl: string | null;
		ddlHighlighted: string;
		ddlTextareaEl: HTMLTextAreaElement | null;
		ddlHighlightEl: HTMLDivElement | null;
		ddlFocused: boolean;
		lineNumbersText: string;
		batchNonEmpty: number;
		batchRunning: boolean;
		singleRunning: boolean;
		reloading: boolean;
		reloadError: string | null;
		loading: boolean;
		batchActiveLine: number | null;
		batchActiveDdlHighlighted: string;
		batchTotal: number;
		batchCurrent: number;
		batchActiveTokensIn: number | null;
		batchActiveTokensOut: number | null;
		batchTokensInTotal: number;
		batchTokensOutTotal: number;
		liveMs: number;
		tokenSummary: string;
		batchFailureReport: BatchFailureReport | null;
		canSubmit: boolean;
		error: string | null;
		batchPromptHistory: string[];
		demoSettings: DemoSettings;
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
		showKiwi: boolean;
		showCrab: boolean;
		activeSaijikiPreview: SaijikiPreview | null;
		canvasAspectEnabled: boolean;
		canvasAspectId: CanvasAspectId;
		canvasAspectMenuOpen: boolean;
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
		onInsertWord: (word: string) => void;
		previewForWord: (categoryKey: string, canonicalWord: string, word: string) => SaijikiPreview;
		onRememberDDLSelection: () => void;
		onSyncDDLHighlightScroll: () => void;
		onReplay: () => void | Promise<void>;
		onStopReplay: () => void;
	};

	let {
		inputMode = $bindable('single'),
		input = $bindable(''),
		batchInput = $bindable(''),
		ddl = $bindable(''),
		ddlHighlighted,
		ddlTextareaEl = $bindable(null),
		ddlHighlightEl = $bindable(null),
		ddlFocused = $bindable(false),
		lineNumbersText,
		batchNonEmpty,
		batchRunning,
		singleRunning,
		reloading,
		reloadError,
		loading,
		batchActiveLine,
		batchActiveDdlHighlighted,
		batchTotal,
		batchCurrent,
		batchActiveTokensIn,
		batchActiveTokensOut,
		batchTokensInTotal,
		batchTokensOutTotal,
		liveMs,
		tokenSummary,
		batchFailureReport,
		canSubmit,
		error,
		batchPromptHistory,
		demoSettings = $bindable(),
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
		showKiwi,
		showCrab,
		activeSaijikiPreview = $bindable(),
		canvasAspectEnabled,
		canvasAspectId,
		canvasAspectMenuOpen,
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
		onInsertWord,
		previewForWord,
		onRememberDDLSelection,
		onSyncDDLHighlightScroll,
		onReplay,
		onStopReplay,
	}: Props = $props();

	const tabItems = $derived([
		{ mode: 'single' as const, label: t().modeSingle, running: singleRunning },
		{ mode: 'ddl' as const, label: t().modeDdlEdit, running: reloading },
		{ mode: 'batch' as const, label: t().modeBatch, running: batchRunning },
		{ mode: 'demo' as const, label: t().modeDemo, running: demoRunning },
	]);
</script>

<div class="panel-tabs">
	{#each tabItems as item (item.mode)}
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
	{/each}
</div>

<section class="panel-section">
	<div class="section-head">
		<span class="section-label">{inputMode === 'ddl' ? t().ddlEditSectionLabel : t().inputSectionLabel}</span>
		<div class="section-actions">
			{#if canvasAspectEnabled}
				<CanvasAspectPlugin
					selected={canvasAspectId}
					open={canvasAspectMenuOpen}
					onToggle={onToggleCanvasAspectMenu}
					onSelect={onSelectCanvasAspect}
				/>
			{/if}
			<button class="ghost-btn" onclick={onOpenModelSelection}>{t().modelSelectButton}</button>
			<button class="ghost-btn" onclick={onOpenCatalogModal}>{t().colorCatalogButton}</button>
			{#if inputMode !== 'demo'}
				<button class="ghost-btn create-btn" onclick={onClearInput}>{t().clearInputBtn}</button>
			{/if}
		</div>
	</div>

	{#if inputMode === 'single'}
		<textarea
			bind:value={input}
			rows="5"
			spellcheck="false"
			placeholder={t().inputPlaceholder}
			class="input-ta"
		></textarea>

		{#if singleRunning}
			<div class="progress-wrap">
				<div class="progress-phases">
					{#each [{ key: '解釈', label: t().statsInterp }, { key: '構造化', label: t().statsStruct }] as ph, i (ph.key)}
						{#if i > 0}<span class="phase-sep">›</span>{/if}
						<span class="phase-item" class:phase-done={stageLabel.includes('構造化') && ph.key === '解釈'} class:phase-active={stageLabel.includes(ph.key) && !(stageLabel.includes('構造化') && ph.key === '解釈')}>
							{#if stageLabel.includes('構造化') && ph.key === '解釈'}<span class="phase-check">✓</span>{/if}
							{#if !(stageLabel.includes('構造化') && ph.key === '解釈') && stageLabel.includes(ph.key)}<span class="phase-dot"></span>{/if}
							{ph.label}
						</span>
					{/each}
				</div>
				<div class="progress-right">
					<span class="progress-time">{(liveMs / 1000).toFixed(1)}s</span>
					<StopButton onclick={onStop}>{t().stopBtn}</StopButton>
				</div>
			</div>
			<div
				class="progress-bar-track"
				style="--progress-target: {stageLabel.includes('構造化') ? '65%' : '30%'}"
			>
				<div class="progress-bar-fill"></div>
				{#if showKiwi}
					<KiwiMascot />
				{/if}
			</div>
			<div class="progress-stage-text">{stageLabel}</div>
		{:else}
			<PaintButton onclick={onSubmit} disabled={!canSubmit}>{t().submitBtn}</PaintButton>
		{/if}

		{#if error}<p class="error-text">{error}</p>{/if}
	{:else if inputMode === 'ddl'}
		<DdlEditPanel
			bind:ddl
			{ddlHighlighted}
			bind:ddlTextareaEl
			bind:ddlHighlightEl
			bind:ddlFocused
			{reloading}
			{reloadError}
			{loading}
			{liveMs}
			{tokenSummary}
			{showKiwi}
			bind:activeSaijikiPreview
			{onInsertWord}
			{previewForWord}
			onRememberSelection={onRememberDDLSelection}
			onSyncHighlightScroll={onSyncDDLHighlightScroll}
			onReplay={onReplay}
			{onStopReplay}
		/>
	{:else if inputMode === 'batch'}
		<BatchPanel
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
			{error}
			{batchPromptHistory}
			{showCrab}
			{onRememberBatchPrompt}
			onSubmit={onSubmit}
			onStop={onStop}
		/>
	{:else}
		<DemoPanel
			bind:settings={demoSettings}
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
		font-size: 10px; font-weight: 500; letter-spacing: 0.08em;
		color: var(--fg3); text-transform: uppercase;
	}
	.section-actions { display: flex; gap: 5px; }
	.ghost-btn {
		padding: 4px 10px;
		border: 1px solid var(--border2);
		border-radius: var(--r);
		background: var(--panel);
		color: var(--fg2);
		font-size: 11px;
		cursor: pointer;
		font-family: inherit;
	}
	.ghost-btn:hover { background: var(--bg2); }
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
	.input-ta {
		width: 100%; padding: 9px 10px;
		border: 1px solid var(--border2); border-radius: var(--r);
		background: var(--panel); color: var(--fg);
		font-family: inherit; font-size: 13px; line-height: 1.65;
		resize: vertical; outline: none;
	}
	.input-ta:focus { border-color: var(--accent); }
	.progress-wrap {
		display: flex; align-items: center; justify-content: space-between;
		padding: 8px 10px 6px;
		border: 1px solid var(--border2); border-radius: var(--r) var(--r) 0 0;
		background: var(--panel);
		margin-top: 8px;
	}
	.progress-phases { display: flex; align-items: center; gap: 4px; }
	.phase-sep { color: var(--border); font-size: 9px; margin: 0 1px; }
	.phase-item { font-size: 11px; color: var(--border2); display: flex; align-items: center; gap: 3px; }
	.phase-item.phase-active { color: var(--fg); font-weight: 500; }
	.phase-item.phase-done { color: var(--fg3); }
	.phase-dot {
		display: inline-block; width: 6px; height: 6px; border-radius: 50%;
		background: var(--accent); flex-shrink: 0;
		animation: inkupulse 1s ease-in-out infinite;
	}
	.phase-check { color: #27ae60; font-size: 10px; }
	.progress-right { display: flex; align-items: center; gap: 7px; }
	.progress-time { font-size: 11px; color: var(--fg3); font-variant-numeric: tabular-nums; }
	.progress-bar-track {
		position: relative;
		height: 32px; background: transparent;
		border-left: 1px solid var(--border2); border-right: 1px solid var(--border2);
		overflow: visible;
	}
	.progress-bar-track::before {
		content: "";
		position: absolute; top: 18px; left: 0; right: 0; height: 3px;
		background: var(--bg3);
	}
	.progress-bar-fill {
		position: absolute; top: 18px; left: 0; height: 3px;
		width: var(--progress-target, 50%);
		background: var(--accent); transition: width 0.3s ease;
	}
	.progress-stage-text {
		font-size: 11px; color: var(--fg3);
		padding: 5px 10px 7px;
		border: 1px solid var(--border2); border-top: none;
		border-radius: 0 0 var(--r) var(--r);
		background: var(--panel);
	}
	.error-text { color: #a2342a; font-size: 12px; }
	@keyframes inkupulse {
		0%, 100% { opacity: 1; transform: scale(1); }
		50% { opacity: 0.4; transform: scale(0.7); }
	}
	@keyframes tabrun {
		from { background-position: 180% 0; }
		to { background-position: -180% 0; }
	}
</style>
