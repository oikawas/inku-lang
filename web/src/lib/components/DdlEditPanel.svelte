<script lang="ts">
	import { tick } from 'svelte';
	import { t } from '$lib/i18n/index.svelte';
	import KiwiMascot from './KiwiMascot.svelte';
	import PaintButton from './PaintButton.svelte';
	import SaijikiInline from './SaijikiInline.svelte';
	import StopButton from './StopButton.svelte';

	type SaijikiPreview = {
		categoryKey: string;
		word: string;
		canonicalWord: string;
		effect: string;
		example: string;
		svg: string;
	};

	type Props = {
		ddl: string | null;
		ddlHighlighted: string;
		ddlTextareaEl: HTMLTextAreaElement | null;
		ddlHighlightEl: HTMLDivElement | null;
		ddlFocused: boolean;
		reloading: boolean;
		reloadError: string | null;
		loading: boolean;
		liveMs: number;
		tokenSummary: string;
		showKiwi: boolean;
		activeSaijikiPreview: SaijikiPreview | null;
		onInsertWord: (word: string) => void;
		previewForWord: (categoryKey: string, canonicalWord: string, word: string) => SaijikiPreview;
		onRememberSelection: () => void;
		onSyncHighlightScroll: () => void;
		onReplay: () => void | Promise<void>;
		onStopReplay: () => void;
	};

	let {
		ddl = $bindable(''),
		ddlHighlighted,
		ddlTextareaEl = $bindable(null),
		ddlHighlightEl = $bindable(null),
		ddlFocused = $bindable(false),
		reloading,
		reloadError,
		loading,
		liveMs,
		tokenSummary,
		showKiwi,
		activeSaijikiPreview = $bindable(),
		onInsertWord,
		previewForWord,
		onRememberSelection,
		onSyncHighlightScroll,
		onReplay,
		onStopReplay,
	}: Props = $props();

	let dialogOpen = $state(false);
	let ddlLineNumberEl = $state<HTMLDivElement | null>(null);
	const ddlLineNumbers = $derived((ddl ?? '').split('\n'));

	async function openEditorDialog() {
		if (reloading || loading) return;
		dialogOpen = true;
		await tick();
		ddlTextareaEl?.focus();
		onRememberSelection();
		syncEditorScroll();
	}

	function closeEditorDialog() {
		onRememberSelection();
		ddlFocused = false;
		dialogOpen = false;
	}

	async function replayFromDialog() {
		if (reloading || !(ddl ?? '').trim() || loading) return;
		closeEditorDialog();
		await onReplay();
	}

	function syncEditorScroll() {
		onSyncHighlightScroll();
		if (ddlLineNumberEl && ddlTextareaEl) {
			ddlLineNumberEl.scrollTop = ddlTextareaEl.scrollTop;
		}
	}
</script>

<div class="ddl-edit-layout">
	<div class="ddl-edit-main">
		<button
			type="button"
			class="ddl-summary-box"
			disabled={reloading || loading}
			onclick={openEditorDialog}
		>
			{#if ddl?.trim()}
				<span class="ddl-summary-highlight">{@html ddlHighlighted}</span>
			{:else}
				<span class="ddl-summary-placeholder">{t().ddlEditPlaceholder}</span>
			{/if}
		</button>

		{#if reloading}
			<div class="progress-wrap">
				<div class="progress-phases">
					<span class="phase-item phase-active"><span class="phase-dot"></span>{t().statsStruct}</span>
				</div>
				<div class="progress-right">
					<span class="progress-token">{tokenSummary || '-→-tok'}</span>
					<span class="progress-time">{(liveMs / 1000).toFixed(1)}s</span>
					<StopButton onclick={onStopReplay}>{t().stopBtn}</StopButton>
				</div>
			</div>
			<div class="progress-bar-track" style="--progress-target: 55%">
				<div class="progress-bar-fill"></div>
				{#if showKiwi}
					<KiwiMascot />
				{/if}
			</div>
		{/if}
		{#if reloadError}<p class="error-text">{reloadError}</p>{/if}
	</div>
</div>

{#if dialogOpen}
	<div
		class="ddl-dialog-backdrop"
		role="button"
		tabindex="0"
		aria-label={t().closeLabel}
		onclick={closeEditorDialog}
		onkeydown={(e) => { if (e.key === 'Enter' || e.key === ' ' || e.key === 'Escape') closeEditorDialog(); }}
	></div>
	<div
		class="ddl-dialog"
		role="dialog"
		aria-modal="true"
		tabindex="-1"
		onclick={(e) => e.stopPropagation()}
		onkeydown={(e) => { if (e.key === 'Escape') closeEditorDialog(); }}
	>
		<div class="ddl-dialog-head">
			<div>
				<div class="ddl-dialog-title">{t().ddlEditSectionLabel}</div>
				<div class="ddl-dialog-subtitle">{t().ddlEditNote}</div>
			</div>
			<button class="ddl-dialog-close" onclick={closeEditorDialog} aria-label={t().closeLabel}>×</button>
		</div>
		<div class="ddl-dialog-body">
			<div class="ddl-editor-column">
				<div class="ddl-editor-frame">
					<div class="ddl-line-numbers" bind:this={ddlLineNumberEl} aria-hidden="true">
						{#each ddlLineNumbers as _, i}
							<span>{i + 1}</span>
						{/each}
					</div>
					<div class="ddl-highlight-wrap dialog-editor">
						<div class="ddl-highlight" bind:this={ddlHighlightEl} aria-hidden="true">{@html ddlHighlighted}</div>
						<textarea
							class="ddl-edit-ta"
							bind:this={ddlTextareaEl}
							bind:value={ddl}
							rows="18"
							spellcheck="false"
							placeholder={t().ddlEditPlaceholder}
							onclick={onRememberSelection}
							onfocus={() => { ddlFocused = true; onRememberSelection(); }}
							onblur={() => { onRememberSelection(); ddlFocused = false; }}
							oninput={() => { onRememberSelection(); syncEditorScroll(); }}
							onkeyup={onRememberSelection}
							onmouseup={onRememberSelection}
							onselect={onRememberSelection}
							onscroll={syncEditorScroll}
						></textarea>
					</div>
				</div>
				<PaintButton onclick={replayFromDialog} disabled={reloading || !(ddl ?? '').trim() || loading}>
					{t().ddlPaintButton}
				</PaintButton>
			</div>
			<SaijikiInline
				bind:activePreview={activeSaijikiPreview}
				{onInsertWord}
				{previewForWord}
			/>
		</div>
	</div>
{/if}

<style>
	.ddl-edit-layout {
		display: flex;
		flex-direction: column;
		gap: 10px;
		min-height: 0;
	}
	.ddl-edit-main {
		display: flex;
		flex-direction: column;
		min-width: 0;
		gap: 8px;
	}
	.ddl-summary-box {
		display: flex;
		align-items: flex-start;
		justify-content: flex-start;
		flex-direction: column;
		width: 100%;
		min-height: 16em;
		padding: 10px 11px;
		border: 1px solid var(--accent);
		border-left: 3px solid var(--border2);
		border-radius: 0 var(--r) var(--r) 0;
		background: var(--panel);
		color: var(--fg);
		appearance: none;
		font-family: inherit;
		font-size: 13px;
		line-height: 1.78;
		text-align: left;
		cursor: text;
		white-space: pre-wrap;
		word-break: break-word;
		overflow: hidden;
	}
	.ddl-summary-box:hover:not(:disabled),
	.ddl-summary-box:focus-visible {
		border-color: var(--accent);
		box-shadow: 0 0 0 2px color-mix(in srgb, var(--accent) 18%, transparent);
		outline: none;
	}
	.ddl-summary-box:disabled {
		cursor: not-allowed;
		opacity: 0.72;
	}
	.ddl-summary-highlight {
		display: block;
		width: 100%;
		max-height: 15em;
		overflow: hidden;
	}
	.ddl-summary-placeholder {
		display: block;
		width: 100%;
		color: var(--fg3);
		opacity: 0.72;
	}
	.ddl-highlight-wrap {
		position: relative;
		width: 100%;
		min-height: 24em;
		border: 1px solid var(--accent);
		border-left: 3px solid var(--border2);
		border-radius: 0 var(--r) var(--r) 0;
		background: var(--panel);
		overflow: hidden;
	}
	.ddl-highlight-wrap.dialog-editor {
		flex: 1;
		min-height: 0;
		height: 100%;
	}
	.ddl-editor-frame {
		display: grid;
		grid-template-columns: 46px minmax(0, 1fr);
		min-height: 0;
	}
	.ddl-editor-column {
		display: flex;
		flex-direction: column;
		gap: 10px;
		min-height: 0;
	}
	.ddl-line-numbers {
		padding: 11px 8px 10px 6px;
		border: 1px solid var(--border2);
		border-right: none;
		border-radius: var(--r) 0 0 var(--r);
		background: var(--bg2);
		color: var(--fg3);
		font-family: inherit;
		font-size: 12px;
		line-height: 1.78;
		text-align: right;
		overflow: hidden;
		user-select: none;
		box-sizing: border-box;
	}
	.ddl-line-numbers span {
		display: block;
		height: calc(13px * 1.78);
		line-height: calc(13px * 1.78);
		font-variant-numeric: tabular-nums;
	}
	.ddl-editor-frame .ddl-highlight-wrap {
		border-radius: 0 var(--r) var(--r) 0;
	}
	.ddl-highlight,
	.ddl-edit-ta {
		width: 100%;
		min-height: 100%;
		padding: 10px 11px;
		box-sizing: border-box;
		margin: 0;
		font-family: inherit;
		font-size: 13px;
		font-weight: 400;
		font-style: normal;
		letter-spacing: 0;
		line-height: 1.78;
		resize: vertical;
		outline: none;
		white-space: pre-wrap;
		word-break: break-word;
		tab-size: 4;
		scrollbar-gutter: stable;
		vertical-align: top;
	}
	.dialog-editor .ddl-highlight,
	.dialog-editor .ddl-edit-ta {
		display: block;
		height: 100%;
		min-height: 0;
		resize: none;
	}
	.ddl-highlight {
		position: absolute;
		inset: 0;
		z-index: 0;
		overflow: auto;
		color: var(--fg);
		pointer-events: none;
		scrollbar-width: none;
	}
	.ddl-highlight::-webkit-scrollbar {
		display: none;
	}
	.ddl-edit-ta {
		position: relative;
		z-index: 1;
		border: none;
		background: transparent;
		color: transparent;
		caret-color: transparent;
		overflow: auto;
	}
	.ddl-edit-ta::placeholder {
		color: var(--fg3);
		opacity: 0.65;
	}
	.ddl-edit-ta::selection {
		background: rgba(44, 62, 145, 0.22);
	}
	.ddl-highlight :global(.ddl-token) {
		border-radius: 2px;
		font-weight: inherit;
	}
	.ddl-highlight :global(.ddl-custom-caret) {
		position: relative;
		display: inline-block;
		width: 0;
		height: 1em;
		vertical-align: text-bottom;
	}
	.ddl-highlight :global(.ddl-custom-caret)::after {
		content: '';
		position: absolute;
		left: 0;
		top: -0.18em;
		width: 3px;
		height: 1.45em;
		border-radius: 2px;
		background: var(--fg);
		animation: ddl-caret-blink 1s steps(2, start) infinite;
	}
	.ddl-highlight :global(.ddl-token-shape) { color: #2c5fb8; background: rgba(44, 95, 184, 0.08); }
	.ddl-highlight :global(.ddl-token-touch) { color: #7a5b2f; background: rgba(122, 91, 47, 0.10); }
	.ddl-highlight :global(.ddl-token-line) { color: #53606b; background: rgba(83, 96, 107, 0.10); }
	.ddl-highlight :global(.ddl-token-color) { color: #b12a6b; background: rgba(177, 42, 107, 0.09); }
	.ddl-highlight :global(.ddl-token-motion) { color: #197a74; background: rgba(25, 122, 116, 0.10); }
	.ddl-highlight :global(.ddl-token-place) { color: #6b4cb3; background: rgba(107, 76, 179, 0.09); }
	.ddl-highlight :global(.ddl-token-action) { color: #9a4a1d; background: rgba(154, 74, 29, 0.10); }
	.ddl-highlight :global(.ddl-token-angle) { color: #3d6f2c; background: rgba(61, 111, 44, 0.10); }
	.ddl-highlight :global(.ddl-token-ratio) { color: #9a3d3d; background: rgba(154, 61, 61, 0.09); }
	.ddl-highlight :global(.ddl-token-word) { color: #2c3e91; background: rgba(44, 62, 145, 0.08); }
	.ddl-highlight :global(.ddl-token-emotion) {
		color: #9b7a66;
		font-style: inherit;
	}
	.ddl-summary-box :global(.ddl-token) {
		border-radius: 2px;
	}
	.ddl-summary-box :global(.ddl-token-shape) { color: #2c5fb8; background: rgba(44, 95, 184, 0.08); }
	.ddl-summary-box :global(.ddl-token-touch) { color: #7a5b2f; background: rgba(122, 91, 47, 0.10); }
	.ddl-summary-box :global(.ddl-token-line) { color: #53606b; background: rgba(83, 96, 107, 0.10); }
	.ddl-summary-box :global(.ddl-token-color) { color: #b12a6b; background: rgba(177, 42, 107, 0.09); }
	.ddl-summary-box :global(.ddl-token-motion) { color: #197a74; background: rgba(25, 122, 116, 0.10); }
	.ddl-summary-box :global(.ddl-token-place) { color: #6b4cb3; background: rgba(107, 76, 179, 0.09); }
	.ddl-summary-box :global(.ddl-token-action) { color: #9a4a1d; background: rgba(154, 74, 29, 0.10); }
	.ddl-summary-box :global(.ddl-token-angle) { color: #3d6f2c; background: rgba(61, 111, 44, 0.10); }
	.ddl-summary-box :global(.ddl-token-ratio) { color: #9a3d3d; background: rgba(154, 61, 61, 0.09); }
	.ddl-summary-box :global(.ddl-token-word) { color: #2c3e91; background: rgba(44, 62, 145, 0.08); }
	.ddl-summary-box :global(.ddl-token-emotion) { color: #9b7a66; }
	:global(html[data-theme='dark']) .ddl-highlight :global(.ddl-token-shape),
	:global(html[data-theme='dark']) .ddl-summary-box :global(.ddl-token-shape) {
		color: #9cc4ff;
		background: rgba(92, 143, 220, 0.26);
	}
	:global(html[data-theme='dark']) .ddl-highlight :global(.ddl-token-touch),
	:global(html[data-theme='dark']) .ddl-summary-box :global(.ddl-token-touch) {
		color: #e2bf82;
		background: rgba(188, 139, 62, 0.24);
	}
	:global(html[data-theme='dark']) .ddl-highlight :global(.ddl-token-line),
	:global(html[data-theme='dark']) .ddl-summary-box :global(.ddl-token-line) {
		color: #c4ccd5;
		background: rgba(147, 160, 176, 0.22);
	}
	:global(html[data-theme='dark']) .ddl-highlight :global(.ddl-token-color),
	:global(html[data-theme='dark']) .ddl-summary-box :global(.ddl-token-color) {
		color: #ff91c7;
		background: rgba(215, 80, 149, 0.24);
	}
	:global(html[data-theme='dark']) .ddl-highlight :global(.ddl-token-motion),
	:global(html[data-theme='dark']) .ddl-summary-box :global(.ddl-token-motion) {
		color: #7ce1d4;
		background: rgba(50, 157, 147, 0.24);
	}
	:global(html[data-theme='dark']) .ddl-highlight :global(.ddl-token-place),
	:global(html[data-theme='dark']) .ddl-summary-box :global(.ddl-token-place) {
		color: #c2a9ff;
		background: rgba(133, 99, 214, 0.26);
	}
	:global(html[data-theme='dark']) .ddl-highlight :global(.ddl-token-action),
	:global(html[data-theme='dark']) .ddl-summary-box :global(.ddl-token-action) {
		color: #f0aa73;
		background: rgba(197, 105, 45, 0.24);
	}
	:global(html[data-theme='dark']) .ddl-highlight :global(.ddl-token-angle),
	:global(html[data-theme='dark']) .ddl-summary-box :global(.ddl-token-angle) {
		color: #a7d88e;
		background: rgba(89, 142, 65, 0.25);
	}
	:global(html[data-theme='dark']) .ddl-highlight :global(.ddl-token-ratio),
	:global(html[data-theme='dark']) .ddl-summary-box :global(.ddl-token-ratio) {
		color: #f0a0a0;
		background: rgba(196, 78, 78, 0.24);
	}
	:global(html[data-theme='dark']) .ddl-highlight :global(.ddl-token-word),
	:global(html[data-theme='dark']) .ddl-summary-box :global(.ddl-token-word) {
		color: #b8c7ff;
		background: rgba(92, 111, 205, 0.26);
	}
	:global(html[data-theme='dark']) .ddl-highlight :global(.ddl-token-emotion),
	:global(html[data-theme='dark']) .ddl-summary-box :global(.ddl-token-emotion) {
		color: #d8b8a6;
	}
	:global(html[data-theme='dark']) .ddl-line-numbers {
		background: #1a1918;
		color: #8c857a;
		border-color: #3b3834;
	}
	.progress-wrap {
		display: flex;
		align-items: center;
		justify-content: space-between;
		padding: 8px 10px 6px;
		border: 1px solid var(--border2);
		border-radius: var(--r) var(--r) 0 0;
		background: var(--panel);
		margin-top: 2px;
	}
	.progress-phases {
		display: flex;
		align-items: center;
		gap: 4px;
	}
	.phase-item {
		font-size: 11px;
		color: var(--border2);
		display: flex;
		align-items: center;
		gap: 3px;
	}
	.phase-item.phase-active {
		color: var(--fg);
		font-weight: 500;
	}
	.phase-dot {
		display: inline-block;
		width: 6px;
		height: 6px;
		border-radius: 50%;
		background: var(--accent);
		flex-shrink: 0;
		animation: inkupulse 1s ease-in-out infinite;
	}
	.progress-right {
		display: flex;
		align-items: center;
		gap: 7px;
	}
	.progress-token {
		font-size: 11px;
		color: var(--fg3);
		font-variant-numeric: tabular-nums;
		white-space: nowrap;
	}
	.progress-time {
		font-size: 11px;
		color: var(--fg3);
		font-variant-numeric: tabular-nums;
	}
	.progress-bar-track {
		position: relative;
		height: 32px;
		background: transparent;
		border-left: 1px solid var(--border2);
		border-right: 1px solid var(--border2);
		overflow: visible;
	}
	.progress-bar-track::before {
		content: "";
		position: absolute;
		top: 18px;
		left: 0;
		right: 0;
		height: 3px;
		background: var(--bg3);
	}
	.progress-bar-fill {
		position: absolute;
		top: 18px;
		left: 0;
		height: 3px;
		width: var(--progress-target, 50%);
		background: var(--accent);
		transition: width 0.3s ease;
	}
	.error-text {
		color: #a2342a;
		font-size: 12px;
	}
	.ddl-dialog-backdrop {
		position: fixed;
		inset: 0;
		z-index: 360;
		background: rgba(0, 0, 0, 0.28);
		backdrop-filter: blur(2px);
	}
	.ddl-dialog {
		position: fixed;
		left: 50%;
		top: 50%;
		z-index: 361;
		transform: translate(-50%, -50%);
		width: min(1120px, calc(100vw - 48px));
		height: min(820px, calc(100vh - 48px));
		display: flex;
		flex-direction: column;
		border: 1px solid var(--border);
		border-radius: var(--r);
		background: var(--panel2);
		box-shadow: 0 18px 56px rgba(0, 0, 0, 0.22);
		overflow: hidden;
	}
	.ddl-dialog-head {
		display: flex;
		align-items: flex-start;
		justify-content: space-between;
		gap: 16px;
		padding: 14px 16px 12px;
		border-bottom: 1px solid var(--border);
		flex-shrink: 0;
	}
	.ddl-dialog-title {
		font-size: 15px;
		font-weight: 500;
		letter-spacing: 0.05em;
		color: var(--fg);
	}
	.ddl-dialog-subtitle {
		margin-top: 3px;
		font-size: 11px;
		color: var(--fg3);
	}
	.ddl-dialog-close {
		width: 28px;
		height: 28px;
		border: 1px solid var(--border2);
		border-radius: var(--r);
		background: var(--panel);
		color: var(--fg2);
		font-size: 18px;
		line-height: 1;
		cursor: pointer;
	}
	.ddl-dialog-close:hover {
		background: var(--bg2);
	}
	.ddl-dialog-body {
		display: grid;
		grid-template-columns: minmax(0, 1fr) minmax(360px, 42%);
		gap: 10px;
		min-height: 0;
		flex: 1;
		padding: 14px 16px;
	}
	@media (max-width: 900px) {
		.ddl-edit-layout {
			min-height: 0;
		}
		.ddl-highlight-wrap {
			min-height: 20em;
		}
		.ddl-summary-box {
			min-height: 14em;
		}
		.ddl-dialog {
			width: calc(100vw - 20px);
			height: calc(100vh - 20px);
		}
		.ddl-dialog-body {
			display: flex;
			flex-direction: column;
			padding: 10px;
		}
		.ddl-editor-frame {
			min-height: 22em;
		}
	}
	@keyframes ddl-caret-blink {
		50% { opacity: 0; }
	}
	@keyframes inkupulse {
		0%, 100% { opacity: 1; transform: scale(1); }
		50% { opacity: 0.4; transform: scale(0.7); }
	}
</style>
