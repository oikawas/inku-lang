<script lang="ts">
	import { t } from '$lib/i18n/index.svelte';

	type PromptsData = { stage1_system: string; stage2_system: string };

	type Props = {
		outputTab: 'prompts' | 'score';
		promptsData: PromptsData | null;
		stage1PromptText: string;
		ddl: string | null;
		promptStage1Expanded: boolean;
		promptStage2Expanded: boolean;
		copiedPrompt: 'stage1' | 'stage2' | null;
		scoreJsonLines: string[];
		scoreJsonHighlighted: string;
		onCopyPromptText: (kind: 'stage1' | 'stage2', text: string | null | undefined) => void | Promise<void>;
	};

	let {
		outputTab,
		promptsData,
		stage1PromptText,
		ddl,
		promptStage1Expanded = $bindable(false),
		promptStage2Expanded = $bindable(false),
		copiedPrompt,
		scoreJsonLines,
		scoreJsonHighlighted,
		onCopyPromptText,
	}: Props = $props();
</script>

{#if outputTab === 'prompts' && promptsData}
	<div class="prompt-section">
		<div class="prompt-head">
			<p class="prompt-label">{t().promptStage1Input}</p>
			<button
				class="prompt-copy-btn"
				class:copied={copiedPrompt === 'stage1'}
				type="button"
				title={copiedPrompt === 'stage1' ? t().promptCopied : t().promptCopy}
				aria-label={copiedPrompt === 'stage1' ? t().promptCopied : t().promptCopy}
				onclick={() => onCopyPromptText('stage1', stage1PromptText)}
			>
				<svg viewBox="0 0 24 24" aria-hidden="true">
					<rect x="9" y="9" width="10" height="10" rx="2"></rect>
					<path d="M5 15V7a2 2 0 0 1 2-2h8"></path>
				</svg>
			</button>
		</div>
		<textarea class="prompt-textarea prompt-user" readonly value={stage1PromptText}></textarea>
		<div class="prompt-collapsible-head">
			<p class="prompt-label">{t().promptStage1System}</p>
			<button class="ghost-btn" onclick={() => (promptStage1Expanded = !promptStage1Expanded)}>{promptStage1Expanded ? t().promptCollapse : t().promptExpand}</button>
		</div>
		<div class="prompt-collapse" class:expanded={promptStage1Expanded}>
			<textarea class="prompt-textarea prompt-system" readonly value={promptsData.stage1_system}></textarea>
			{#if !promptStage1Expanded}<div class="prompt-fade"></div>{/if}
		</div>
		{#if ddl}
			<div class="prompt-head">
				<p class="prompt-label">{t().promptStage2Input}</p>
				<button
					class="prompt-copy-btn"
					class:copied={copiedPrompt === 'stage2'}
					type="button"
					title={copiedPrompt === 'stage2' ? t().promptCopied : t().promptCopy}
					aria-label={copiedPrompt === 'stage2' ? t().promptCopied : t().promptCopy}
					onclick={() => onCopyPromptText('stage2', ddl)}
				>
					<svg viewBox="0 0 24 24" aria-hidden="true">
						<rect x="9" y="9" width="10" height="10" rx="2"></rect>
						<path d="M5 15V7a2 2 0 0 1 2-2h8"></path>
					</svg>
				</button>
			</div>
			<textarea class="prompt-textarea prompt-user" readonly value={ddl}></textarea>
		{/if}
		<div class="prompt-collapsible-head">
			<p class="prompt-label">{t().promptStage2System}</p>
			<button class="ghost-btn" onclick={() => (promptStage2Expanded = !promptStage2Expanded)}>{promptStage2Expanded ? t().promptCollapse : t().promptExpand}</button>
		</div>
		<div class="prompt-collapse" class:expanded={promptStage2Expanded}>
			<textarea class="prompt-textarea prompt-system" readonly value={promptsData.stage2_system}></textarea>
			{#if !promptStage2Expanded}<div class="prompt-fade"></div>{/if}
		</div>
	</div>
{:else if outputTab === 'prompts'}
	<p class="muted-center">{t().promptLoading}</p>
{/if}

{#if outputTab === 'score'}
	<div class="score-view">
		<div class="score-line-nums" aria-hidden="true">
			{#each scoreJsonLines as _, i (i)}
				<div>{i + 1}</div>
			{/each}
		</div>
		<pre class="score-pre">{@html scoreJsonHighlighted}</pre>
	</div>
{/if}

<style>
	.prompt-section {
		flex: 1;
		display: flex;
		flex-direction: column;
		gap: 4px;
		overflow-y: auto;
		padding: 12px;
		width: 100%;
		align-self: stretch;
		min-height: 0;
	}
	.prompt-head {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 8px;
		margin-top: 8px;
	}
	.prompt-head .prompt-label { margin: 0; }
	.prompt-label { margin: 8px 0 3px; font-size: 11px; font-weight: 600; color: var(--fg2); }
	.prompt-copy-btn {
		width: 24px;
		height: 24px;
		display: inline-flex;
		align-items: center;
		justify-content: center;
		flex: 0 0 auto;
		border: 1px solid transparent;
		border-radius: 4px;
		background: transparent;
		color: var(--fg3);
		cursor: pointer;
	}
	.prompt-copy-btn:hover {
		border-color: var(--border);
		background: var(--bg2);
		color: var(--fg);
	}
	.prompt-copy-btn.copied {
		color: #2f6f45;
		background: rgba(47, 111, 69, 0.08);
	}
	.prompt-copy-btn svg {
		width: 15px;
		height: 15px;
		fill: none;
		stroke: currentColor;
		stroke-width: 1.8;
		stroke-linecap: round;
		stroke-linejoin: round;
	}
	.prompt-collapsible-head {
		display: flex;
		align-items: center;
		justify-content: space-between;
		margin-top: 8px;
	}
	.prompt-collapsible-head .prompt-label { margin: 0; }
	.prompt-textarea {
		width: 100%;
		background: var(--bg2);
		padding: 8px 10px;
		border-radius: var(--r);
		border: 1px solid var(--border);
		overflow: auto;
		white-space: pre-wrap;
		word-break: break-word;
		font-size: 11px;
		line-height: 1.5;
		margin: 0;
		font-family: inherit;
		color: var(--fg);
		resize: vertical;
	}
	.prompt-user { min-height: 120px; }
	.prompt-system { min-height: 120px; height: 220px; }
	.prompt-collapse {
		position: relative;
		max-height: 80px;
		overflow: hidden;
	}
	.prompt-collapse.expanded {
		max-height: none;
		overflow: visible;
	}
	.prompt-collapse:not(.expanded) .prompt-system {
		height: 120px;
		resize: none;
	}
	.prompt-fade {
		position: absolute;
		left: 0;
		right: 0;
		bottom: 0;
		height: 32px;
		background: linear-gradient(transparent, var(--bg));
		pointer-events: none;
	}
	.score-view {
		display: flex;
		width: 100%;
		height: 100%;
		min-height: 0;
		align-self: stretch;
		background: #fff;
		border: 1px solid var(--border);
		border-radius: var(--r);
		overflow: auto;
		font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace;
		font-size: 12px;
		line-height: 1.5;
	}
	.score-line-nums {
		flex-shrink: 0;
		min-width: 42px;
		min-height: 100%;
		height: max-content;
		padding: 12px 8px;
		border-right: 1px solid var(--border);
		background: var(--bg2);
		color: var(--fg3);
		text-align: right;
		user-select: none;
		font-variant-numeric: tabular-nums;
	}
	.score-pre {
		background: #fff;
		padding: 12px;
		overflow: visible;
		font-size: inherit;
		line-height: inherit;
		white-space: pre;
		word-break: normal;
		width: 100%;
		min-height: 100%;
		height: max-content;
		margin: 0;
		font-family: inherit;
		align-self: flex-start;
	}
	.score-pre :global(.json-key) { color: #6f4bb8; font-weight: 600; }
	.score-pre :global(.json-string) { color: #116329; }
	.score-pre :global(.json-number) { color: #0b63ce; }
	.score-pre :global(.json-bool) { color: #b54708; font-weight: 600; }
	.score-pre :global(.json-null) { color: #6b7280; font-style: italic; }
	.muted-center { color: var(--fg3); font-size: 13px; padding: 16px; }
	.ghost-btn {
		padding: 4px 10px;
		border: 1px solid var(--border2);
		border-radius: var(--r);
		background: #fff;
		color: var(--fg2);
		font-size: 11px;
		cursor: pointer;
		font-family: inherit;
	}
	.ghost-btn:hover { background: var(--bg2); }
</style>
