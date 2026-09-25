<script lang="ts">
	import { t } from '$lib/i18n/index.svelte';
	import type { SystemPromptsState } from '$lib/features/canvas/system-prompts';

	type Props = {
		outputTab: 'prompts' | 'score';
		/** The pane that scrolls in whichever tab is showing. The drawer that
		    holds this reads it to put the reader back where they closed it. */
		scrollEl?: HTMLElement | null;
		stage1PromptText: string;
		/** The system prompts this work sent, as its execution kept them. */
		systemPrompts?: SystemPromptsState;
		ddl: string | null;
		copiedPrompt: 'stage1' | 'stage2' | 'score' | null;
		scoreJsonText: string;
		scoreJsonLines: string[];
		scoreJsonHighlighted: string;
		scoreJsonSeparatorLine: number | null;
		onCopyPromptText: (kind: 'stage1' | 'stage2' | 'score', text: string | null | undefined) => void | Promise<void>;
	};

	let {
		outputTab,
		scrollEl = $bindable(null),
		stage1PromptText,
		systemPrompts = { state: 'not_recorded' },
		ddl,
		copiedPrompt,
		scoreJsonText,
		scoreJsonLines,
		scoreJsonHighlighted,
		scoreJsonSeparatorLine,
		onCopyPromptText,
	}: Props = $props();

	const scoreJsonHighlightedLines = $derived(scoreJsonHighlighted ? scoreJsonHighlighted.split('\n') : []);

	let stage1SystemExpanded = $state(false);
	let stage2SystemExpanded = $state(false);
	const stage1System = $derived(systemPrompts.state === 'recorded' ? systemPrompts.stage1 : null);
	const stage2System = $derived(systemPrompts.state === 'recorded' ? systemPrompts.stage2 : null);
	// Said in place of a stage's system prompt when there is none to show.
	const systemPromptNote = $derived(
		systemPrompts.state === 'loading'
			? t().promptLoading
			: systemPrompts.state === 'recorded'
				? t().promptSystemNotSent
				: systemPrompts.state === 'not_recorded'
					? t().promptSystemNotRecorded
					: t().promptSystemUnavailable
	);
</script>

{#if outputTab === 'prompts'}
	<div class="prompt-section" bind:this={scrollEl}>
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
		<textarea class="prompt-textarea prompt-user stage1-user" readonly value={stage1PromptText}></textarea>
		<div class="prompt-collapsible-head">
			<p class="prompt-label">{t().promptStage1System}</p>
			{#if stage1System}
				<button class="ghost-btn" type="button" onclick={() => (stage1SystemExpanded = !stage1SystemExpanded)}>{stage1SystemExpanded ? t().promptCollapse : t().promptExpand}</button>
			{/if}
		</div>
		{#if stage1System}
			<div class="prompt-collapse" class:expanded={stage1SystemExpanded}>
				<textarea class="prompt-textarea prompt-system" readonly value={stage1System.system}></textarea>
				{#if !stage1SystemExpanded}<div class="prompt-fade"></div>{/if}
			</div>
		{:else}
			<p class="prompt-note">{systemPromptNote}</p>
		{/if}
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
			{#if stage2System}
				<button class="ghost-btn" type="button" onclick={() => (stage2SystemExpanded = !stage2SystemExpanded)}>{stage2SystemExpanded ? t().promptCollapse : t().promptExpand}</button>
			{/if}
		</div>
		{#if stage2System}
			<div class="prompt-collapse" class:expanded={stage2SystemExpanded}>
				<textarea class="prompt-textarea prompt-system stage2-system" readonly value={stage2System.system}></textarea>
				{#if !stage2SystemExpanded}<div class="prompt-fade"></div>{/if}
			</div>
		{:else}
			<p class="prompt-note">{systemPromptNote}</p>
		{/if}
	</div>
{/if}

{#if outputTab === 'score'}
	<div class="score-shell">
		<div class="score-toolbar">
			<button
				class="prompt-copy-btn score-copy-btn"
				class:copied={copiedPrompt === 'score'}
				type="button"
				title={copiedPrompt === 'score' ? t().promptCopied : t().promptCopy}
				aria-label={copiedPrompt === 'score' ? t().promptCopied : t().promptCopy}
				onclick={() => onCopyPromptText('score', scoreJsonText)}
			>
				<svg viewBox="0 0 24 24" aria-hidden="true">
					<rect x="9" y="9" width="10" height="10" rx="2"></rect>
					<path d="M5 15V7a2 2 0 0 1 2-2h8"></path>
				</svg>
			</button>
		</div>
		<div class="score-view" bind:this={scrollEl}>
			<div class="score-line-nums" aria-hidden="true">
				{#each scoreJsonLines as _, i (i)}
					<div class="score-line-num" class:section-start={scoreJsonSeparatorLine === i}>{i + 1}</div>
				{/each}
			</div>
			<div class="score-pre">
				{#each scoreJsonHighlightedLines as line, i (i)}
					<span class="score-code-line" class:section-start={scoreJsonSeparatorLine === i}>{@html line || '&nbsp;'}</span>
				{/each}
			</div>
		</div>
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
	.prompt-label { margin: 8px 0 3px; font-size: var(--ui-font-size-11); font-weight: 600; color: var(--fg2); }
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
	:global(html[data-theme='dark']) .prompt-copy-btn.copied {
		color: #86d8a4;
		background: rgba(47, 111, 69, 0.28);
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
	.prompt-textarea {
		width: 100%;
		background: var(--bg2);
		padding: 8px 10px;
		border-radius: var(--r);
		border: 1px solid var(--border);
		overflow: auto;
		white-space: pre-wrap;
		word-break: break-word;
		font-size: var(--ui-font-size-11);
		line-height: 1.5;
		margin: 0;
		font-family: inherit;
		color: var(--fg);
		resize: vertical;
	}
	.prompt-user { min-height: 120px; }
	.stage1-user { min-height: 60px; height: 60px; }
	.prompt-collapsible-head {
		display: flex;
		align-items: center;
		justify-content: space-between;
		margin-top: 8px;
	}
	.prompt-collapsible-head .prompt-label { margin: 0; }
	.prompt-system { min-height: 120px; height: 220px; }
	.stage2-system { min-height: 60px; height: 110px; }
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
	.prompt-collapse:not(.expanded) .stage2-system { min-height: 60px; height: 60px; }
	.prompt-fade {
		position: absolute;
		left: 0;
		right: 0;
		bottom: 0;
		height: 32px;
		background: linear-gradient(transparent, var(--bg));
		pointer-events: none;
	}
	.prompt-note { margin: 2px 0 0; font-size: var(--ui-font-size-11); color: var(--fg3); }
	.score-shell {
		position: relative;
		width: 100%;
		height: 100%;
		min-height: 0;
		align-self: stretch;
		display: flex;
		flex-direction: column;
		background: var(--panel);
		border: 1px solid var(--border);
		border-radius: var(--r);
		overflow: hidden;
	}
	.score-toolbar {
		display: flex;
		justify-content: flex-end;
		padding: 6px 8px;
		border-bottom: 1px solid var(--border);
		background: var(--bg2);
	}
	.score-copy-btn {
		color: var(--fg2);
		background: var(--panel);
		border-color: var(--border);
	}
	.score-copy-btn.copied {
		color: #2f6f45;
		background: rgba(47, 111, 69, 0.10);
	}
	:global(html[data-theme='dark']) .score-copy-btn.copied {
		color: #86d8a4;
		background: rgba(47, 111, 69, 0.28);
	}
	.score-view {
		display: flex;
		width: 100%;
		flex: 1;
		min-height: 0;
		align-self: stretch;
		background: var(--panel);
		overflow: auto;
		font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace;
		font-size: var(--ui-font-size-12);
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
	.score-line-num,
	.score-code-line {
		min-height: 18px;
	}
	.score-line-num.section-start,
	.score-code-line.section-start {
		border-top: 1px solid var(--border2);
		margin-top: 6px;
		padding-top: 6px;
	}
	.score-pre {
		background: var(--panel);
		padding: 12px;
		overflow: visible;
		font-size: inherit;
		line-height: inherit;
		white-space: nowrap;
		word-break: normal;
		width: 100%;
		min-height: 100%;
		height: max-content;
		margin: 0;
		font-family: inherit;
		align-self: flex-start;
		color: var(--fg);
	}
	.score-code-line {
		display: block;
		white-space: pre;
	}
	.score-pre :global(.json-key) { color: #5b3f99; font-weight: 600; }
	.score-pre :global(.json-string) { color: #0f6b2f; }
	.score-pre :global(.json-number) { color: #075ca8; }
	.score-pre :global(.json-bool) { color: #9a3f05; font-weight: 600; }
	.score-pre :global(.json-null) { color: #5e6672; font-style: italic; }
	:global(html[data-theme='dark']) .score-pre :global(.json-key) { color: #d6c5ff; }
	:global(html[data-theme='dark']) .score-pre :global(.json-string) { color: #8ce99a; }
	:global(html[data-theme='dark']) .score-pre :global(.json-number) { color: #91caff; }
	:global(html[data-theme='dark']) .score-pre :global(.json-bool) { color: #ffc078; }
	:global(html[data-theme='dark']) .score-pre :global(.json-null) { color: #b8c0cc; }
	:global(html[data-theme='dark']) .score-copy-btn.copied {
		color: #8ce99a;
		background: rgba(140, 233, 154, 0.12);
	}
</style>
