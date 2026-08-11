<script lang="ts">
	import { tick } from 'svelte';
	import { t } from '$lib/i18n/index.svelte';
	import { highlightDDL } from '$lib/highlight';
	import { buildPluginNameIndex, unknownPluginNames } from '$lib/plugin-names';
	import SaijikiInline from './SaijikiInline.svelte';
	import RunStatus from './RunStatus.svelte';
	import WildToggle from './WildToggle.svelte';
	import ModelCardPicker from './ModelCardPicker.svelte';
	import type { Provider, ProviderGroup } from '$lib/models';

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
		stage1ModelLabel: string;
		stage2ModelLabel: string;
		// Drawing here runs Stage 2 only (DDL -> Score), so the picker selects
		// the Stage 2 model and changes the global selection like the main screen.
		drawingModelId: string;
		drawingModelGroups: ProviderGroup[];
		onSelectDrawingModel: (provider: Provider, model: string) => void | Promise<void>;
		runTokensIn: number | null;
		runTokensOut: number | null;
		error: string | null;
		previewForWord: (categoryKey: string, canonicalWord: string, word: string) => SaijikiPreview;
		// `fires_on_*` is what lets the editor say which plain word a wrong
		// qualified name would have fired (GET /api/saijiki carries them).
		pluginEntries?: { qualified_name: string; note_ja: string; note_en: string; fires_on_ja?: string[]; fires_on_en?: string[] }[];
		showSettings?: boolean;
		wildValue?: boolean;
		wildInherited?: boolean;
		onSelectWild?: (value: boolean) => void;
		onDraw: (ddl: string, signal?: AbortSignal) => void | Promise<void>;
		onClose: () => void;
	};

	let { open, isJapanese, title, subtitle, initialDdl, drawing, stage1ModelLabel, stage2ModelLabel, drawingModelId, drawingModelGroups, onSelectDrawingModel, runTokensIn, runTokensOut, error, previewForWord, pluginEntries = [], showSettings = false, wildValue = false, wildInherited = true, onSelectWild, onDraw, onClose }: Props = $props();

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
	// This editor is the one surface that knows which qualified names exist, so
	// it is the only caller that hands the index to the highlighter.
	const pluginNameIndex = $derived(buildPluginNameIndex(pluginEntries));
	const highlighted = $derived(highlightDDL(value, focused && selection.start === selection.end ? selection.start : null, pluginNameIndex));
	// Named while it is being typed: the expansion layer drops such a reference
	// together with the sentence around it, and nothing says so afterwards.
	const unknownNames = $derived(unknownPluginNames(value, pluginNameIndex));

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
					{#if unknownNames.length > 0}
						<div class="ddl-unknown-names">
							<span class="ddl-unknown-title">{t().ddlUnknownNameTitle}</span>
							{#each unknownNames as unknown (unknown.text)}
								<span class="ddl-unknown-row">
									<code class="ddl-unknown-name">{unknown.text}</code>
									<span class="ddl-unknown-hint">
										{unknown.firesAs
											? t().ddlUnknownNameFires(unknown.namespace, unknown.firesAs)
											: t().ddlUnknownNameUnregistered}
									</span>
								</span>
							{/each}
						</div>
					{/if}
					<p class="ddl-syntax-guide">{t().ddlSyntaxGuide}</p>
				</div>
			</div>
			<SaijikiInline
				bind:activePreview={activeSaijikiPreview}
				{pluginEntries}
				onInsertWord={insertWord}
				{previewForWord}
			/>
		</div>
		{#if error}<div class="ddled-error">{error}</div>{/if}
		<div class="ddled-foot">
			{#if drawing}
				<RunStatus
					variant="inline"
					label={t().stageImageGenerating}
					stage1Model={stage1ModelLabel}
					stage2Model={stage2ModelLabel}
					elapsedMs={elapsedMs}
					tokensIn={runTokensIn}
					tokensOut={runTokensOut}
					onStop={stopDraw}
				/>
			{:else}
				<div class="ddled-model">
					<ModelCardPicker
						label={t().ddlDialogDrawingModel}
						selectedModel={drawingModelId}
						providerGroups={drawingModelGroups}
						onSelect={onSelectDrawingModel}
					/>
				</div>
				{#if showSettings && onSelectWild}
					<!-- One box: the left-aligning margin belongs to the settings, or
					     the switch drifts toward the buttons. -->
					<div class="ddled-settings">
						<WildToggle value={wildValue} {isJapanese} inherited={wildInherited} onSelect={onSelectWild} />
					</div>
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
		gap: 8px;
	}
	/* Same amber as the token in the text above it: the strip and the mark are
	   one statement, and neither is red -- the name may exist tomorrow. */
	.ddl-unknown-names {
		display: flex;
		flex-direction: column;
		gap: 4px;
		padding: 8px 10px;
		border: 1px solid var(--ddl-token-unknown-border);
		border-radius: var(--r);
		background: var(--ddl-token-unknown-bg);
		font-size: 11px;
		line-height: 1.5;
	}
	.ddl-unknown-title {
		color: var(--ddl-token-unknown-fg);
		font-weight: 500;
	}
	.ddl-unknown-row {
		display: flex;
		align-items: baseline;
		gap: 8px;
		flex-wrap: wrap;
	}
	.ddl-unknown-name {
		color: var(--ddl-token-unknown-fg);
		font-family: inherit;
	}
	.ddl-unknown-hint {
		color: var(--fg2);
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
	:global(html[data-theme='dark']) .ddl-line-numbers { background: #1a1918; color: #8c857a; border-color: #3b3834; }
	.ddled-error {
		margin: 0 16px;
		padding: 8px 12px;
		background: color-mix(in srgb, var(--danger, #9b3d32) 10%, var(--panel));
		border: 1px solid var(--danger, #9b3d32);
		border-radius: var(--r);
		color: var(--danger, #9b3d32);
		white-space: pre-line;
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
	.ddled-model {
		margin-right: auto;
		min-width: 0;
		max-width: 280px;
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
	/* Same shell as the main paint button (no ▶ mark: footer buttons carry none).
	   Scoped under .ddled-foot: the `.ddled-foot button` rule above is one element
	   selector more specific, so a bare `.ddled-draw` never painted the button. */
	.ddled-foot .ddled-draw {
		background: var(--action-bg);
		color: var(--action-fg);
		border-color: var(--action-bg);
	}
	.ddled-foot .ddled-draw:hover:not(:disabled) {
		background: var(--action-hover);
		border-color: var(--action-hover);
	}
	.ddled-foot .ddled-draw:disabled {
		background: var(--action-disabled-bg);
		color: var(--action-disabled-fg);
		border-color: var(--action-disabled-bg);
		opacity: 1;
	}
	.ddled-settings { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-right: auto; }
	.ddled-cancel:hover:not(:disabled) {
		background: var(--bg2);
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
