<script lang="ts">
	import { t } from '$lib/i18n/index.svelte';
	import type { Provider, ProviderGroup } from '$lib/models';
	import type { DemoSettings } from '$lib/demo';
	import PaintButton from './PaintButton.svelte';
	import RunStatus from './RunStatus.svelte';
	import ModelCardPicker from './ModelCardPicker.svelte';

	type Props = {
		settings: DemoSettings;
		providerGroups: ProviderGroup[];
		running: boolean;
		liveMs: number;
		runTokensIn: number | null;
		runTokensOut: number | null;
		waitingSeconds: number | null;
		currentLiveMs: number | null;
		currentElapsedMs: number | null;
		currentTokensIn: number | null;
		currentTokensOut: number | null;
		totalElapsedMs: number;
		totalTokensIn: number;
		totalTokensOut: number;
		demoRenderCount: number;
		generatedPrompt: string;
		generatedDdlHighlighted: string;
		canSaveCurrent: boolean;
		savingCurrent: boolean;
		actionDisabled: boolean;
		drawingStage1ModelLabel: string;
		drawingStage2ModelLabel: string;
		saveStatus: string | null;
		error: string | null;
		onSettingsChange: (settings: DemoSettings) => void | Promise<void>;
		onSaveCurrent: () => void | Promise<void>;
		onStart: () => void | Promise<void>;
		onStop: () => void;
	};

	let {
		settings = $bindable(),
		providerGroups,
		running,
		liveMs,
		runTokensIn,
		runTokensOut,
		waitingSeconds,
		currentLiveMs,
		currentElapsedMs,
		currentTokensIn,
		currentTokensOut,
		totalElapsedMs,
		totalTokensIn,
		totalTokensOut,
		demoRenderCount,
		generatedPrompt,
		generatedDdlHighlighted,
		canSaveCurrent,
		savingCurrent,
		actionDisabled,
		drawingStage1ModelLabel,
		drawingStage2ModelLabel,
		saveStatus,
		error,
		onSettingsChange,
		onSaveCurrent,
		onStart,
		onStop,
	}: Props = $props();

	const promptModels = $derived(providerGroups.flatMap((group) => group.models));

	function updateSettings(patch: Partial<DemoSettings>) {
		settings = { ...settings, ...patch };
		void onSettingsChange(settings);
	}

	function stepInterval(delta: number) {
		const next = Math.max(1, Math.min(999, Math.round(settings.interval_seconds + delta)));
		updateSettings({ interval_seconds: next });
	}

	function formatMs(ms: number | null) {
		if (ms === null) return t().demoStatsPending;
		return `${(ms / 1000).toFixed(1)}s`;
	}

	function formatTokens(input: number | null, output: number | null) {
		if (input === null || output === null) return t().demoStatsPending;
		return `${input}->${output}tok`;
	}

	const displayedCurrentMs = $derived(currentElapsedMs ?? currentLiveMs);
</script>

<div class="demo-panel">
	<div class="demo-grid">
		<label class="check-row">
			<input
				type="checkbox"
				checked={settings.save_db}
				disabled={running}
				onchange={(event) => updateSettings({ save_db: (event.currentTarget as HTMLInputElement).checked })}
			/>
			<span>{t().demoSaveDb}</span>
		</label>
		<label class="check-row">
			<input
				type="checkbox"
				checked={settings.save_files}
				disabled={running}
				onchange={(event) => updateSettings({ save_files: (event.currentTarget as HTMLInputElement).checked })}
			/>
			<span>{t().demoSaveFiles}</span>
		</label>
		<label class="check-row wide">
			<input
				type="checkbox"
				checked={settings.random_color_catalog}
				disabled={running}
				onchange={(event) => updateSettings({ random_color_catalog: (event.currentTarget as HTMLInputElement).checked })}
			/>
			<span>{t().demoRandomColorCatalog}</span>
		</label>
		<div class="wide"><ModelCardPicker label={t().demoPromptModel} selectedModel={settings.prompt_model} {providerGroups} disabled={running} onSelect={(_provider: Provider, model: string) => updateSettings({ prompt_model: model })} /></div>
		<label class="wide">
			<span>{t().demoSeedPhrase}</span>
			<textarea
				value={settings.seed_phrase}
				rows="3"
				disabled={running}
				spellcheck="false"
				oninput={(event) => updateSettings({ seed_phrase: (event.currentTarget as HTMLTextAreaElement).value })}
			></textarea>
		</label>
		<label>
			<span>{t().demoInterval}</span>
			<div class="interval-control">
				<button type="button" class="step-btn" disabled={running || settings.interval_seconds <= 1} onclick={() => stepInterval(-1)}>−</button>
				<input
					class="interval-input"
					type="number"
					min="1"
					max="999"
					value={settings.interval_seconds}
					disabled={running}
					oninput={(event) => updateSettings({ interval_seconds: Math.max(1, Math.min(999, Number((event.currentTarget as HTMLInputElement).value) || 1)) })}
				/>
				<button type="button" class="step-btn" disabled={running || settings.interval_seconds >= 999} onclick={() => stepInterval(1)}>+</button>
			</div>
		</label>
	</div>

	<div class="demo-actions">
		{#if running}
			<RunStatus
				label={waitingSeconds !== null ? `${t().demoRunning} · ${t().demoWaiting(waitingSeconds)}` : t().demoRunning}
				stage1Model={drawingStage1ModelLabel}
				stage2Model={drawingStage2ModelLabel}
				elapsedMs={liveMs}
				tokensIn={totalTokensIn || runTokensIn}
				tokensOut={totalTokensOut || runTokensOut}
				onStop={onStop}
			/>
		{:else}
			<PaintButton onclick={onStart} disabled={!settings.seed_phrase.trim() || promptModels.length === 0 || actionDisabled}>{t().demoStart}</PaintButton>
		{/if}
	</div>

	{#if running || demoRenderCount > 0}
		<div class="demo-stats">
			<div class="stats-row">
				<span class="stats-label">{t().demoTotalStats}</span>
				<span>{formatMs(totalElapsedMs)} / {formatTokens(totalTokensIn, totalTokensOut)}</span>
				{#if demoRenderCount > 0}<span class="stats-count">{t().demoRenderCount(demoRenderCount)}</span>{/if}
			</div>
			{#if running}
				<div class="stats-row">
					<span class="stats-label">{t().demoCurrentStats}</span>
					<span>{formatMs(displayedCurrentMs)} / {formatTokens(currentTokensIn, currentTokensOut)}</span>
				</div>
			{/if}
		</div>
	{/if}

	<div class="demo-save-row">
		<button class="ghost-btn" onclick={onSaveCurrent} disabled={!canSaveCurrent || savingCurrent}>
			{savingCurrent ? t().historyLoading : t().demoSaveCurrent}
		</button>
		{#if saveStatus}<span>{saveStatus}</span>{/if}
	</div>

	{#if error}<p class="error-text">{error}</p>{/if}

	<div class="demo-observe">
		<div class="observe-block">
			<div class="observe-title">{t().demoGeneratedPrompt}</div>
			<div class="observe-body text">{generatedPrompt || '—'}</div>
		</div>
		<div class="observe-block">
			<div class="observe-title">{t().demoGeneratedDdl}</div>
			<div class="observe-body ddl">{@html generatedDdlHighlighted || '—'}</div>
		</div>
	</div>
</div>

<style>
	.demo-panel { display: flex; flex-direction: column; gap: 10px; }
	.demo-grid {

		display: grid;
		grid-template-columns: 1fr 1fr;
		gap: 8px;
	}
	label {
		display: flex;
		flex-direction: column;
		gap: 4px;
		color: var(--fg2);
		font-size: 11px;
	}
	.check-row {
		flex-direction: row;
		align-items: center;
		min-height: 30px;
	}
	.wide { grid-column: 1 / -1; }
	input,
	textarea {
		border: 1px solid var(--border2);
		border-radius: var(--r);
		background: var(--panel);
		color: var(--fg);
		font: inherit;
		font-size: 12px;
		padding: 6px 8px;
	}
	textarea { resize: vertical; line-height: 1.5; }
	.interval-control {
		display: inline-grid;
		grid-template-columns: 26px 4.5em 26px;
		align-items: stretch;
		gap: 4px;
		width: max-content;
	}
	.interval-input {
		width: 4.5em;
		text-align: right;
		font-variant-numeric: tabular-nums;
	}
	.step-btn {
		border: 1px solid var(--border2);
		border-radius: var(--r);
		background: var(--panel);
		color: var(--fg2);
		font: inherit;
		font-size: 14px;
		line-height: 1;
		cursor: pointer;
	}
	.step-btn:disabled { opacity: 0.42; cursor: not-allowed; }
	.demo-actions {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 8px;
	}
	.demo-stats {
		display: grid;
		gap: 4px;
		padding: 7px 8px;
		border: 1px solid var(--border);
		border-radius: var(--r);
		background: var(--bg2);
		color: var(--fg2);
		font-size: 11px;
		font-variant-numeric: tabular-nums;
	}
	.stats-row {
		display: flex;
		align-items: center;
		gap: 8px;
		min-width: 0;
	}
	.stats-label {
		color: var(--fg3);
		min-width: 4.5em;
	}
	.stats-count {
		color: var(--fg3);
		margin-left: auto;
	}
	.ghost-btn {
		padding: var(--btn-sm-padding);
		border: 1px solid var(--border2);
		border-radius: var(--btn-sm-radius);
		background: var(--panel);
		color: var(--fg2);
		font: inherit;
		font-size: var(--btn-sm-font-size);
		cursor: pointer;
	}
	.ghost-btn:disabled { opacity: 0.45; cursor: not-allowed; }
	.demo-save-row {
		display: flex;
		align-items: center;
		gap: 8px;
		color: var(--fg3);
		font-size: 11px;
		min-height: 26px;
	}
	.error-text {
		margin: 0;
		color: var(--danger);
		font-size: 12px;
	}
	.demo-observe { display: flex; flex-direction: column; gap: 8px; }
	.observe-block {
		border: 1px solid var(--border);
		border-radius: var(--r);
		background: var(--bg2);
		overflow: hidden;
	}
	.observe-title {
		padding: 6px 8px;
		border-bottom: 1px solid var(--border);
		color: var(--fg3);
		font-size: 10px;
		text-transform: uppercase;
		letter-spacing: 0.08em;
	}
	.observe-body {
		min-height: 42px;
		max-height: 130px;
		overflow: auto;
		padding: 8px;
		color: var(--fg);
		font-size: 12px;
		line-height: 1.55;
		white-space: pre-wrap;
	}
</style>
