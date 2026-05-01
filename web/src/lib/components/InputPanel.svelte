<script lang="ts">
	import { t } from '$lib/i18n/index.svelte';
	import BatchPanel from './BatchPanel.svelte';
	import DemoPanel from './DemoPanel.svelte';
	import type { DemoSettings } from '$lib/demo';

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
		showBirds: boolean;
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
		showBirds,
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

	const tabItems = $derived([
		{ mode: 'single' as const, label: t().modeSingle, running: singleRunning },
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
		<span class="section-label">{t().inputSectionLabel}</span>
		<div class="section-actions">
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
					<button class="stop-sm" onclick={onStop}>{t().stopBtn}</button>
				</div>
			</div>
			<div
				class="progress-bar-track"
				style="--progress-target: {stageLabel.includes('構造化') ? '65%' : '30%'}"
			>
				<div class="progress-bar-fill"></div>
				{#if showBirds}
					<svg class="progress-bird" viewBox="0 0 52 44" aria-hidden="true">
						<g class="bird-peck">
							<ellipse class="bird-shadow" cx="26" cy="38" rx="12" ry="2.4" />
							<g class="bird-preen">
								<g class="bird-view bird-view-side">
									<path class="bird-tail" d="M33 25 Q43 24 47 19 Q44 29 34 30 Z" />
									<ellipse class="bird-body" cx="27" cy="25" rx="11" ry="8" />
									<path class="bird-wing" d="M24 23 Q31 15 37 24 Q31 30 25 29 Z" />
									<g class="bird-head">
										<circle class="bird-head-fill" cx="17" cy="19" r="5.8" />
										<path class="bird-beak" d="M11.5 19 L5 16.9 L5 21.1 Z" />
										<circle class="bird-eye" cx="15.4" cy="17.5" r="0.95" />
									</g>
								</g>
								<g class="bird-view bird-view-front">
									<ellipse class="bird-body" cx="26" cy="25.5" rx="9.2" ry="8.8" />
									<circle class="bird-head-fill" cx="26" cy="17" r="6.4" />
									<path class="bird-wing bird-wing-left" d="M18 24 Q13 25 11 30 Q18 31 22 27 Z" />
									<path class="bird-wing bird-wing-right" d="M34 24 Q39 25 41 30 Q34 31 30 27 Z" />
									<path class="bird-beak" d="M23 18.7 L26 22.4 L29 18.7 Z" />
									<circle class="bird-eye" cx="23.4" cy="16.3" r="0.9" />
									<circle class="bird-eye" cx="28.6" cy="16.3" r="0.9" />
								</g>
								<g class="bird-view bird-view-three">
									<path class="bird-tail" d="M33 25 Q41 23 44 18 Q43 27 35 30 Z" />
									<ellipse class="bird-body" cx="27" cy="25" rx="10" ry="8.5" />
									<path class="bird-wing" d="M24 23 Q30 17 36 24 Q31 29 25 29 Z" />
									<circle class="bird-head-fill" cx="20" cy="18" r="6.1" />
									<path class="bird-beak" d="M16 19 L9.8 17.2 L10.8 21.2 Z" />
									<circle class="bird-eye" cx="18.3" cy="16.5" r="0.95" />
								</g>
								<g class="bird-legs">
									<path class="bird-leg bird-leg-a" d="M22 32 L20 37" />
									<path class="bird-leg bird-leg-b" d="M30 32 L32 37" />
								</g>
							</g>
						</g>
					</svg>
				{/if}
			</div>
			<div class="progress-stage-text">{stageLabel}</div>
		{:else}
			<button class="play-btn" onclick={onSubmit} disabled={!canSubmit}>▶ <span>{t().submitBtn}</span></button>
		{/if}

		{#if error}<p class="error-text">{error}</p>{/if}
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
	.stop-sm {
		padding: 2px 7px; border: 1px solid var(--border2);
		border-radius: var(--r); background: none;
		color: var(--fg2); font-size: 11px; cursor: pointer; font-family: inherit;
	}
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
	.progress-bird {
		position: absolute;
		left: calc(var(--progress-target, 50%) - 26px);
		bottom: 8px;
		width: 52px;
		height: 44px;
		pointer-events: none;
		overflow: visible;
		filter: drop-shadow(0 2px 3px rgba(107, 123, 42, 0.18));
		animation: birdWalk 12s ease-in-out infinite;
	}
	.bird-peck { transform-origin: 22px 35px; animation: birdPeck 7.8s ease-in-out infinite; }
	.bird-preen { transform-origin: 28px 26px; animation: birdPreen 11.5s ease-in-out infinite; }
	.bird-shadow { fill: rgba(60, 55, 39, 0.18); }
	.bird-body, .bird-head-fill { fill: #7f8f35; }
	.bird-tail { fill: #536523; }
	.bird-view-side { transform-origin: 26px 25px; animation: birdSideView 12s ease-in-out infinite; }
	.bird-view-front { opacity: 0; transform-origin: 26px 25px; animation: birdFrontView 12s ease-in-out infinite; }
	.bird-view-three { opacity: 0; transform-origin: 26px 25px; animation: birdThreeQuarterView 12s ease-in-out infinite; }
	.bird-wing { fill: #a7b45a; transform-origin: 28px 25px; animation: birdWing 5.6s ease-in-out infinite; }
	.bird-wing-left, .bird-wing-right { animation: none; }
	.bird-head { transform-origin: 21px 25px; animation: birdHead 7.8s ease-in-out infinite; }
	.bird-beak { fill: #bd8f34; }
	.bird-eye { fill: #1f2114; }
	.bird-leg {
		fill: none;
		stroke: #7a5a18;
		stroke-width: 1.5;
		stroke-linecap: round;
		transform-origin: 26px 33px;
	}
	.bird-leg-a { animation: birdStepA 1.25s ease-in-out infinite; }
	.bird-leg-b { animation: birdStepB 1.25s ease-in-out infinite; }
	.progress-stage-text {
		font-size: 11px; color: var(--fg3);
		padding: 5px 10px 7px;
		border: 1px solid var(--border2); border-top: none;
		border-radius: 0 0 var(--r) var(--r);
		background: var(--panel);
	}
	.play-btn {
		width: 100%; margin-top: 8px; padding: 9px;
		font-size: 14px; font-weight: 500;
		background: var(--action-bg); color: var(--action-fg);
		border: none; border-radius: var(--r);
		letter-spacing: 0.08em; cursor: pointer;
		display: flex; align-items: center; justify-content: center; gap: 8px;
		font-family: inherit; transition: background 0.15s;
	}
	.play-btn:hover:not(:disabled) { background: var(--action-hover); }
	.play-btn:disabled {
		background: var(--action-disabled-bg);
		color: var(--action-disabled-fg);
		cursor: not-allowed;
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
	@keyframes birdWalk {
		0% { transform: translate(-28px, 0) scaleX(1); }
		9% { transform: translate(-14px, -1px) scaleX(1); }
		18% { transform: translate(-14px, 0) scaleX(1); }
		28% { transform: translate(12px, -1px) scaleX(1); }
		36% { transform: translate(12px, 0) scaleX(1); }
		44% { transform: translate(5px, 0) scaleX(1); }
		48% { transform: translate(2px, 0) scaleX(1); }
		52% { transform: translate(0, 0) scaleX(-1); }
		62% { transform: translate(-18px, -1px) scaleX(-1); }
		72% { transform: translate(-18px, 0) scaleX(-1); }
		82% { transform: translate(10px, -1px) scaleX(-1); }
		90% { transform: translate(10px, 0) scaleX(-1); }
		96% { transform: translate(-6px, 0) scaleX(-1); }
		100% { transform: translate(-28px, 0) scaleX(1); }
	}
	@keyframes birdSideView {
		0%, 40%, 56%, 94%, 100% { opacity: 1; transform: scaleX(1); }
		46%, 50%, 98% { opacity: 0; transform: scaleX(0.72); }
	}
	@keyframes birdFrontView {
		0%, 42%, 56%, 96%, 100% { opacity: 0; transform: scaleX(0.86); }
		47%, 50%, 53%, 98% { opacity: 1; transform: scaleX(1); }
	}
	@keyframes birdThreeQuarterView {
		0%, 39%, 57%, 93%, 100% { opacity: 0; transform: rotate(0deg); }
		43%, 55%, 95%, 99% { opacity: 0.92; transform: rotate(3deg); }
	}
	@keyframes birdWing {
		0%, 18%, 38%, 55%, 72%, 100% { transform: rotate(0deg) scaleY(1); }
		22%, 24%, 26% { transform: rotate(-28deg) scaleY(0.75); }
		29% { transform: rotate(8deg) scaleY(1.08); }
		78%, 80% { transform: rotate(-18deg) scaleY(0.82); }
		82% { transform: rotate(6deg) scaleY(1.06); }
	}
	@keyframes birdPeck {
		0%, 42%, 58%, 100% { transform: rotate(0deg) translateY(0); }
		46%, 50%, 54% { transform: rotate(-16deg) translateY(5px); }
		48%, 52%, 56% { transform: rotate(5deg) translateY(0); }
	}
	@keyframes birdPreen {
		0%, 62%, 78%, 100% { transform: rotate(0deg); }
		66%, 70%, 74% { transform: rotate(9deg) translateX(1px); }
		68%, 72% { transform: rotate(-5deg) translateX(-1px); }
	}
	@keyframes birdHead {
		0%, 42%, 58%, 62%, 100% { transform: rotate(0deg); }
		46%, 50%, 54% { transform: rotate(-22deg) translate(-1px, 4px); }
		66%, 70%, 74% { transform: rotate(18deg) translate(5px, 2px); }
	}
	@keyframes birdStepA {
		0%, 100% { transform: rotate(0deg); }
		45% { transform: rotate(14deg) translateX(1px); }
	}
	@keyframes birdStepB {
		0%, 100% { transform: rotate(0deg); }
		45% { transform: rotate(-14deg) translateX(-1px); }
	}
</style>
