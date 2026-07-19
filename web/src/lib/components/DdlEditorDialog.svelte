<script lang="ts">
	import { tick } from 'svelte';
	import { t } from '$lib/i18n/index.svelte';
	import { highlightDDL } from '$lib/highlight';
	import SaijikiInline from './SaijikiInline.svelte';
	import InkuMascot from './InkuMascot.svelte';
	import StopButton from './StopButton.svelte';
	import TenkeiSelect from './TenkeiSelect.svelte';
	import type { TenkeiLevel } from '$lib/tenkei';

	type SaijikiPreview = {
		categoryKey: string;
		word: string;
		canonicalWord: string;
		effect: string;
		example: string;
		svg: string;
	};

	type Props = {
		open: boolean;
		isJapanese: boolean;
		title: string;
		subtitle: string;
		initialDdl: string;
		drawing: boolean;
		error: string | null;
		previewForWord: (categoryKey: string, canonicalWord: string, word: string) => SaijikiPreview;
		showTenkei?: boolean;
		tenkeiValue?: TenkeiLevel;
		tenkeiInherited?: boolean;
		onSelectTenkei?: (level: TenkeiLevel) => void;
		onDraw: (ddl: string, signal?: AbortSignal) => void | Promise<void>;
		onClose: () => void;
	};

	let { open, isJapanese, title, subtitle, initialDdl, drawing, error, previewForWord, showTenkei = false, tenkeiValue = 'auto', tenkeiInherited = true, onSelectTenkei, onDraw, onClose }: Props = $props();

	let value = $state('');
	let focused = $state(false);
	let selection = $state({ start: 0, end: 0 });
	let textareaEl = $state<HTMLTextAreaElement | null>(null);
	let highlightEl = $state<HTMLDivElement | null>(null);
	let lineNumberEl = $state<HTMLDivElement | null>(null);
	let activeSaijikiPreview = $state<SaijikiPreview | null>(null);
	let lastOpen = false;
	let elapsedMs = $state(0);
	let drawController: AbortController | null = null;

	// While drawing, tick an elapsed timer for the on-dialog status element.
	$effect(() => {
		if (!drawing) return;
		elapsedMs = 0;
		const startedAt = Date.now();
		const handle = setInterval(() => { elapsedMs = Date.now() - startedAt; }, 100);
		return () => clearInterval(handle);
	});

	const lineNumbers = $derived(value.split('\n'));
	const highlighted = $derived(highlightDDL(value, focused && selection.start === selection.end ? selection.start : null));

	$effect(() => {
		if (open && !lastOpen) {
			value = initialDdl;
			selection = { start: initialDdl.length, end: initialDdl.length };
			activeSaijikiPreview = null;
			void tick().then(() => {
				textareaEl?.focus();
				rememberSelection();
				syncScroll();
			});
		}
		lastOpen = open;
	});

	function rememberSelection(): void {
		if (!textareaEl) return;
		selection = { start: textareaEl.selectionStart ?? 0, end: textareaEl.selectionEnd ?? 0 };
	}

	function syncScroll(): void {
		if (highlightEl && textareaEl) highlightEl.scrollTop = textareaEl.scrollTop;
		if (lineNumberEl && textareaEl) lineNumberEl.scrollTop = textareaEl.scrollTop;
	}

	function insertWord(word: string): void {
		const ta = textareaEl;
		if (!ta) {
			value = value + word;
			selection = { start: value.length, end: value.length };
			return;
		}
		const hasFocus = document.activeElement === ta;
		const liveStart = ta.selectionStart ?? selection.start;
		const liveEnd = ta.selectionEnd ?? selection.end;
		const start = Math.max(0, Math.min(value.length, hasFocus ? liveStart : selection.start));
		const end = Math.max(start, Math.min(value.length, hasFocus ? liveEnd : selection.end));
		value = value.slice(0, start) + word + value.slice(end);
		const caret = start + word.length;
		selection = { start: caret, end: caret };
		void tick().then(() => {
			textareaEl?.focus();
			textareaEl?.setSelectionRange(caret, caret);
			rememberSelection();
			syncScroll();
		});
	}

	function requestClose(): void {
		if (drawing) return;
		onClose();
	}

	async function requestDraw(): Promise<void> {
		if (drawing || !value.trim()) return;
		drawController = new AbortController();
		try {
			await onDraw(value, drawController.signal);
		} finally {
			drawController = null;
		}
	}

	function stopDraw(): void {
		drawController?.abort();
	}
</script>

{#if open}
	<div
		class="ddled-backdrop"
		role="button"
		tabindex="0"
		aria-label={t().closeLabel}
		onclick={requestClose}
		onkeydown={(e) => { if (e.key === 'Enter' || e.key === ' ' || e.key === 'Escape') requestClose(); }}
	></div>
	<div
		class="ddled-dialog"
		role="dialog"
		aria-modal="true"
		aria-labelledby="ddled-title"
		tabindex="-1"
		onkeydown={(e) => { if (e.key === 'Escape') requestClose(); }}
	>
		<div class="ddled-head">
			<div>
				<div class="ddled-title" id="ddled-title">{title}</div>
				{#if subtitle}<p class="ddled-subtitle">{subtitle}</p>{/if}
			</div>
			<button class="ddled-close" type="button" disabled={drawing} onclick={requestClose} aria-label={t().closeLabel}>×</button>
		</div>
		<div class="ddled-body">
			<div class="ddl-editor-column">
				<div class="ddl-editor-frame">
					<div class="ddl-line-numbers" bind:this={lineNumberEl} aria-hidden="true">
						{#each lineNumbers as _, i}
							<span>{i + 1}</span>
						{/each}
					</div>
					<div class="ddl-highlight-wrap dialog-editor">
						<div class="ddl-highlight" bind:this={highlightEl} aria-hidden="true">{@html highlighted}</div>
						<textarea
							class="ddl-edit-ta"
							bind:this={textareaEl}
							bind:value
							rows="18"
							spellcheck="false"
							placeholder={t().ddlEditPlaceholder}
							disabled={drawing}
							onclick={rememberSelection}
							onfocus={() => { focused = true; rememberSelection(); }}
							onblur={() => { rememberSelection(); focused = false; }}
							oninput={() => { rememberSelection(); syncScroll(); }}
							onkeyup={rememberSelection}
							onmouseup={rememberSelection}
							onselect={rememberSelection}
							onscroll={syncScroll}
						></textarea>
					</div>
				</div>
				<div class="ddl-editor-foot">
					<p class="ddl-syntax-guide">{t().ddlSyntaxGuide}</p>
				</div>
			</div>
			<SaijikiInline
				bind:activePreview={activeSaijikiPreview}
				onInsertWord={insertWord}
				{previewForWord}
			/>
		</div>
		{#if error}<div class="ddled-error">{error}</div>{/if}
		<div class="ddled-foot">
			{#if drawing}
				<div class="ddled-status" aria-live="polite">
					<div class="ddled-mascot"><InkuMascot /></div>
					<div class="ddled-status-info">
						<span class="ddled-stage">{t().stageImageGenerating}</span>
						<span class="ddled-elapsed">{isJapanese ? '経過' : 'Elapsed'} {(elapsedMs / 1000).toFixed(1)}s</span>
					</div>
					<StopButton onclick={stopDraw}>{t().stopBtn}</StopButton>
				</div>
			{:else}
				{#if showTenkei && onSelectTenkei}
					<TenkeiSelect compact value={tenkeiValue} {isJapanese} inherited={tenkeiInherited} onSelect={onSelectTenkei} />
				{/if}
				<button type="button" class="ddled-cancel" onclick={requestClose}>{isJapanese ? 'キャンセル' : 'Cancel'}</button>
				<button type="button" class="ddled-draw" disabled={!value.trim()} onclick={requestDraw}>{isJapanese ? '描画' : 'Draw'}</button>
			{/if}
		</div>
	</div>
{/if}

<style>
	.ddled-backdrop {
		position: fixed;
		inset: 0;
		z-index: 360;
		background: rgba(0, 0, 0, 0.28);
		backdrop-filter: blur(2px);
	}
	.ddled-dialog {
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
	.ddled-head {
		display: flex;
		align-items: flex-start;
		justify-content: space-between;
		gap: 16px;
		padding: 14px 16px 12px;
		border-bottom: 1px solid var(--border);
		flex-shrink: 0;
	}
	.ddled-title {
		font-size: 15px;
		font-weight: 500;
		letter-spacing: 0.05em;
		color: var(--fg);
	}
	.ddled-subtitle {
		margin: 4px 0 0;
		color: var(--fg3);
		font-size: 12px;
		line-height: 1.5;
	}
	.ddled-close {
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
	.ddled-close:hover:not(:disabled) {
		background: var(--bg2);
	}
	.ddled-close:disabled {
		cursor: not-allowed;
		opacity: 0.5;
	}
	.ddled-body {
		display: grid;
		grid-template-columns: minmax(0, 1fr) minmax(360px, 42%);
		gap: 10px;
		min-height: 0;
		flex: 1;
		padding: 14px 16px;
	}
	.ddl-editor-column {
		display: flex;
		flex-direction: column;
		gap: 10px;
		min-height: 0;
	}
	.ddl-editor-frame {
		display: grid;
		grid-template-columns: 46px minmax(0, 1fr);
		min-height: 0;
		flex: 1;
	}
	.ddl-editor-foot {
		display: flex;
		flex-direction: column;
		align-items: stretch;
		justify-content: flex-end;
	}
	.ddl-syntax-guide {
		margin: 0;
		padding: 9px 10px;
		border: 1px solid var(--border2);
		border-radius: var(--r);
		background: var(--panel);
		color: var(--fg3);
		font-size: 11px;
		line-height: 1.55;
		white-space: pre-line;
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
	.ddl-edit-ta:disabled {
		cursor: not-allowed;
		opacity: 0.72;
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
	.ddl-highlight :global(.ddl-token-plugin) { color: #9f4b3b; background: rgba(185, 88, 69, 0.10); }
	.ddl-highlight :global(.ddl-token-word) { color: #2c3e91; background: rgba(44, 62, 145, 0.08); }
	.ddl-highlight :global(.ddl-token-emotion) {
		color: #9b7a66;
		font-style: inherit;
	}
	:global(html[data-theme='dark']) .ddl-highlight :global(.ddl-token-shape) { color: #9cc4ff; background: rgba(92, 143, 220, 0.26); }
	:global(html[data-theme='dark']) .ddl-highlight :global(.ddl-token-touch) { color: #e2bf82; background: rgba(188, 139, 62, 0.24); }
	:global(html[data-theme='dark']) .ddl-highlight :global(.ddl-token-line) { color: #c4ccd5; background: rgba(147, 160, 176, 0.22); }
	:global(html[data-theme='dark']) .ddl-highlight :global(.ddl-token-color) { color: #ff91c7; background: rgba(215, 80, 149, 0.24); }
	:global(html[data-theme='dark']) .ddl-highlight :global(.ddl-token-motion) { color: #7ce1d4; background: rgba(50, 157, 147, 0.24); }
	:global(html[data-theme='dark']) .ddl-highlight :global(.ddl-token-place) { color: #c2a9ff; background: rgba(133, 99, 214, 0.26); }
	:global(html[data-theme='dark']) .ddl-highlight :global(.ddl-token-action) { color: #f0aa73; background: rgba(197, 105, 45, 0.24); }
	:global(html[data-theme='dark']) .ddl-highlight :global(.ddl-token-angle) { color: #a7d88e; background: rgba(89, 142, 65, 0.25); }
	:global(html[data-theme='dark']) .ddl-highlight :global(.ddl-token-ratio) { color: #f0a0a0; background: rgba(196, 78, 78, 0.24); }
	:global(html[data-theme='dark']) .ddl-highlight :global(.ddl-token-word) { color: #b8c7ff; background: rgba(92, 111, 205, 0.26); }
	:global(html[data-theme='dark']) .ddl-highlight :global(.ddl-token-emotion) { color: #d8b8a6; }
	:global(html[data-theme='dark']) .ddl-line-numbers { background: #1a1918; color: #8c857a; border-color: #3b3834; }
	.ddled-error {
		margin: 0 16px;
		padding: 8px 12px;
		background: color-mix(in srgb, var(--danger, #9b3d32) 10%, var(--panel));
		border: 1px solid var(--danger, #9b3d32);
		border-radius: var(--r);
		color: var(--danger, #9b3d32);
		font-size: 12px;
		line-height: 1.4;
	}
	.ddled-foot {
		display: flex;
		align-items: center;
		justify-content: flex-end;
		flex-wrap: wrap;
		gap: 8px;
		padding: 12px 16px;
		border-top: 1px solid var(--border);
		flex-shrink: 0;
	}
	.ddled-foot button {
		border: 1px solid var(--border2);
		border-radius: var(--r);
		padding: 7px 16px;
		font: inherit;
		font-size: 13px;
		cursor: pointer;
		background: var(--panel);
		color: var(--fg);
	}
	.ddled-foot button:disabled {
		cursor: not-allowed;
		opacity: 0.5;
	}
	.ddled-draw {
		background: var(--accent);
		color: #fff;
		border-color: var(--accent);
	}
	.ddled-foot > :global(.tenkei-inline) { margin-right: auto; }
	.ddled-cancel:hover:not(:disabled) {
		background: var(--bg2);
	}
	.ddled-status {
		flex: 0 0 auto;
		margin-left: auto;
		display: flex;
		align-items: center;
		gap: 10px;
	}
	.ddled-mascot { flex: 0 0 auto; display: flex; align-items: center; }
	.ddled-status-info {
		flex: 0 0 auto; min-width: 0;
		display: flex; flex-direction: column; gap: 2px;
		text-align: right;
	}
	.ddled-stage {
		font-size: 12px; font-weight: 500; color: var(--fg);
		white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
	}
	.ddled-elapsed {
		font-size: 11px; color: var(--fg3);
		font-variant-numeric: tabular-nums; white-space: nowrap;
	}
	.ddled-status :global(.stop-btn) {
		flex: 0 0 auto; width: auto; min-width: 0;
		padding: 7px 14px; font-size: 13px; letter-spacing: 0.06em;
	}
	@keyframes ddl-caret-blink {
		50% { opacity: 0; }
	}
	@media (max-width: 900px) {
		.ddled-dialog {
			width: calc(100vw - 20px);
			height: calc(100vh - 20px);
		}
		.ddled-body {
			display: flex;
			flex-direction: column;
			padding: 10px;
		}
		.ddl-highlight-wrap {
			min-height: 20em;
		}
		.ddl-editor-frame {
			min-height: 22em;
		}
	}
</style>
