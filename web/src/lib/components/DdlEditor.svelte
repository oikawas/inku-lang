<script lang="ts">
	import { onMount, tick } from 'svelte';
	import { t } from '$lib/i18n/index.svelte';
	import { highlightDDL } from '$lib/highlight';
	import { buildPluginNameIndex, unknownPluginNames } from '$lib/plugin-names';
	import { resolveInstructionLang } from '$lib/instructionLang';
	import SaijikiInline from './SaijikiInline.svelte';
	import type { PluginEntry, PreviewForPlugin, PreviewForWord, SaijikiPreview } from '$lib/features/ddl-editor/types';

	type Props = {
		value?: string;
		isJapanese: boolean;
		disabled?: boolean;
		pluginEntries?: PluginEntry[];
		previewForWord: PreviewForWord;
		previewForPlugin: PreviewForPlugin;
	};

	let {
		value = $bindable(''),
		isJapanese,
		disabled = false,
		pluginEntries = [],
		previewForWord,
		previewForPlugin,
	}: Props = $props();

	let selection = $state({ start: 0, end: 0 });
	let textareaEl = $state<HTMLTextAreaElement | null>(null);
	let highlightEl = $state<HTMLDivElement | null>(null);
	let lineNumberEl = $state<HTMLDivElement | null>(null);
	let lineMirrorEl = $state<HTMLDivElement | null>(null);
	let activeSaijikiPreview = $state<SaijikiPreview | null>(null);
	let showVocabulary = $state(true);
	let showGuide = $state(false);
	let lineMirrorWidth = $state(0);
	let scrollbarWidth = $state(0);
	let lineHeights = $state<number[]>([]);

	const editorHorizontalPadding = 22;

	const lineNumbers = $derived(value.split('\n'));
	const pluginNameIndex = $derived(buildPluginNameIndex(pluginEntries));
	const highlighted = $derived(highlightDDL(value, null, pluginNameIndex));
	const unknownNames = $derived(unknownPluginNames(value, pluginNameIndex));
	const wordLang = $derived(resolveInstructionLang(value, isJapanese ? 'ja' : 'en'));

	onMount(() => {
		const observer = new ResizeObserver(() => {
			updateTextMetrics();
			measureLineHeights();
		});
		if (textareaEl) observer.observe(textareaEl);
		if (lineMirrorEl) observer.observe(lineMirrorEl);
		updateTextMetrics();
		measureLineHeights();
		return () => observer.disconnect();
	});

	$effect(() => {
		value;
		lineMirrorWidth;
		lineMirrorEl;
		void tick().then(measureLineHeights);
	});

	/** Focus the native text control after the editor has entered the document. */
	export function focus(): void {
		void tick().then(() => {
			textareaEl?.focus();
			rememberSelection();
			syncScroll();
		});
	}

	function updateTextMetrics(): void {
		if (!textareaEl) return;
		const nextScrollbarWidth = textareaEl.offsetWidth - textareaEl.clientWidth;
		const nextMirrorWidth = Math.max(0, textareaEl.clientWidth - editorHorizontalPadding);
		if (scrollbarWidth !== nextScrollbarWidth) scrollbarWidth = nextScrollbarWidth;
		if (lineMirrorWidth !== nextMirrorWidth) lineMirrorWidth = nextMirrorWidth;
	}

	function measureLineHeights(): void {
		if (!lineMirrorEl) return;
		const nextHeights = Array.from(lineMirrorEl.children, (line) => line.getBoundingClientRect().height);
		if (
			nextHeights.length !== lineHeights.length ||
			nextHeights.some((height, index) => height !== lineHeights[index])
		) {
			lineHeights = nextHeights;
		}
	}

	function rememberSelection(): void {
		if (!textareaEl) return;
		selection = {
			start: textareaEl.selectionStart ?? 0,
			end: textareaEl.selectionEnd ?? 0,
		};
	}

	function syncScroll(): void {
		if (!textareaEl) return;
		if (highlightEl) {
			highlightEl.scrollTop = textareaEl.scrollTop;
			highlightEl.scrollLeft = textareaEl.scrollLeft;
		}
		if (lineNumberEl) lineNumberEl.scrollTop = textareaEl.scrollTop;
	}

	function insertWord(word: string): void {
		if (disabled) return;
		const ta = textareaEl;
		if (!ta) {
			value += word;
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
</script>

<section class="ddl-editor" style={`--ddl-editor-scrollbar-width: ${scrollbarWidth}px`}>
	<div class="ddl-editor-toolbar">
		<div class="ddl-editor-toolbar-title">{t().ddlEditorInstructions}</div>
		<div class="ddl-editor-toolbar-actions">
			<button
				type="button"
				class:active={showVocabulary}
				aria-pressed={showVocabulary}
				onclick={() => (showVocabulary = !showVocabulary)}
			>{t().ddlEditorVocabulary}</button>
			<button
				type="button"
				class:active={showGuide}
				aria-expanded={showGuide}
				aria-controls="ddl-editor-guide"
				onclick={() => (showGuide = !showGuide)}
			>{t().ddlEditorSyntaxGuideToggle}</button>
		</div>
		<div class="ddl-editor-status">{t().ddlEditorStatus(lineNumbers.length, value.length)}</div>
	</div>

	<div class="ddl-editor-workspace" class:with-vocabulary={showVocabulary} class:with-support={showGuide || unknownNames.length > 0}>
		<div class="ddl-editor-main">
			<div class="ddl-editor-frame">
				<div class="ddl-line-numbers" bind:this={lineNumberEl} aria-hidden="true">
					{#each lineNumbers as _, i}
						<span style:height={lineHeights[i] ? `${lineHeights[i]}px` : undefined}>{i + 1}</span>
					{/each}
				</div>
				<div class="ddl-highlight-wrap">
					<div class="ddl-highlight" bind:this={highlightEl} aria-hidden="true">{@html highlighted}{#if value.endsWith('\n')}{'\u200b'}{/if}</div>
					<div
						class="ddl-line-mirror"
						bind:this={lineMirrorEl}
						aria-hidden="true"
						style:width={`${lineMirrorWidth}px`}
					>
						{#each lineNumbers as line}
							<span>{line || '\u00a0'}</span>
						{/each}
					</div>
					<textarea
						class="ddl-edit-ta"
						bind:this={textareaEl}
						bind:value
						rows="5"
						spellcheck="false"
						placeholder={t().ddlEditPlaceholder}
						aria-label={t().ddlEditorInstructions}
						{disabled}
						onclick={rememberSelection}
						onfocus={rememberSelection}
						onblur={rememberSelection}
						oninput={() => { rememberSelection(); syncScroll(); }}
						onkeyup={rememberSelection}
						onmouseup={rememberSelection}
						onselect={rememberSelection}
						onscroll={syncScroll}
					></textarea>
				</div>
			</div>

			{#if unknownNames.length > 0 || showGuide}
				<div class="ddl-editor-support">
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
					{#if showGuide}
						<details id="ddl-editor-guide" class="ddl-editor-guide" bind:open={showGuide}>
							<summary>{t().ddlEditorSyntaxGuideToggle}</summary>
							<p>{t().ddlSyntaxGuide}</p>
						</details>
					{/if}
				</div>
			{/if}
		</div>

		{#if showVocabulary}
			<div class="ddl-editor-vocabulary">
				<SaijikiInline
					bind:activePreview={activeSaijikiPreview}
					{wordLang}
					{pluginEntries}
					onInsertWord={insertWord}
					{previewForWord}
					{previewForPlugin}
					{disabled}
				/>
			</div>
		{/if}
	</div>
</section>

<style>
	.ddl-editor {
		display: flex;
		flex: 1;
		flex-direction: column;
		min-height: 0;
		min-width: 0;
		gap: 8px;
	}
	.ddl-editor-toolbar {
		display: flex;
		align-items: center;
		gap: 8px;
		min-width: 0;
		font-size: var(--btn-sm-font-size);
	}
	.ddl-editor-toolbar-title {
		color: var(--fg2);
		font-weight: 500;
		letter-spacing: 0.04em;
		white-space: nowrap;
	}
	.ddl-editor-toolbar-actions {
		display: flex;
		gap: 5px;
		min-width: 0;
	}
	.ddl-editor-toolbar button {
		border: 1px solid var(--border2);
		border-radius: var(--btn-sm-radius);
		padding: var(--btn-sm-padding);
		background: var(--panel);
		color: var(--fg2);
		font: inherit;
		font-size: var(--btn-sm-font-size);
		line-height: 1.25;
		cursor: pointer;
	}
	.ddl-editor-toolbar button:hover,
	.ddl-editor-toolbar button:focus-visible {
		border-color: var(--accent);
		color: var(--fg);
		outline: none;
	}
	.ddl-editor-toolbar button.active {
		border-color: var(--accent);
		background: var(--accent-light);
		color: var(--accent);
	}
	.ddl-editor-status {
		margin-left: auto;
		color: var(--fg3);
		white-space: nowrap;
	}
	.ddl-editor-workspace {
		display: grid;
		flex: 1;
		min-height: 0;
		min-width: 0;
	}
	.ddl-editor-workspace.with-vocabulary {
		grid-template-rows: minmax(100px, 22%) minmax(0, 1fr);
		gap: 10px;
	}
	.ddl-editor-workspace.with-vocabulary.with-support {
		grid-template-rows: minmax(160px, 36%) minmax(0, 1fr);
	}
	.ddl-editor-main,
	.ddl-editor-vocabulary {
		display: flex;
		flex-direction: column;
		min-width: 0;
		min-height: 0;
	}
	.ddl-editor-frame {
		display: grid;
		grid-template-columns: 48px minmax(0, 1fr);
		flex: 1;
		min-height: 0;
	}
	.ddl-line-numbers {
		box-sizing: border-box;
		overflow: hidden;
		padding: 10px 8px 10px 6px;
		border: 1px solid var(--border2);
		border-right: 0;
		border-radius: var(--r) 0 0 var(--r);
		background: var(--bg2);
		color: var(--fg3);
		font-family: inherit;
		font-size: var(--ui-font-size-14);
		line-height: 1.7;
		text-align: right;
		user-select: none;
	}
	.ddl-line-numbers span {
		display: block;
		min-height: 1.7em;
		line-height: 1.7;
		font-variant-numeric: tabular-nums;
	}
	.ddl-highlight-wrap {
		position: relative;
		min-width: 0;
		min-height: 0;
		border: 1px solid var(--accent);
		border-left: 3px solid var(--border2);
		border-radius: 0 var(--r) var(--r) 0;
		background: var(--panel);
		overflow: hidden;
	}
	.ddl-highlight,
	.ddl-edit-ta {
		box-sizing: border-box;
		width: 100%;
		height: 100%;
		min-width: 100%;
		min-height: 100%;
		margin: 0;
		padding: 10px 11px;
		font-family: inherit;
		font-size: var(--ui-font-size-14);
		font-weight: 400;
		font-style: normal;
		letter-spacing: 0;
		line-height: 1.7;
		white-space: pre-wrap;
		overflow-wrap: break-word;
		word-break: break-word;
		tab-size: 4;
		vertical-align: top;
	}
	.ddl-highlight {
		position: absolute;
		inset: 0;
		z-index: 0;
		overflow: hidden;
		padding-right: calc(11px + var(--ddl-editor-scrollbar-width));
		color: var(--fg);
		pointer-events: none;
		scrollbar-width: none;
	}
	.ddl-line-mirror {
		position: absolute;
		top: 10px;
		left: 11px;
		z-index: 0;
		visibility: hidden;
		pointer-events: none;
		font-family: inherit;
		font-size: var(--ui-font-size-14);
		font-weight: 400;
		font-style: normal;
		letter-spacing: 0;
		line-height: 1.7;
		white-space: pre-wrap;
		overflow-wrap: break-word;
		word-break: break-word;
		tab-size: 4;
	}
	.ddl-line-mirror span {
		display: block;
		min-height: 1.7em;
	}
	.ddl-edit-ta {
		position: relative;
		z-index: 1;
		resize: none;
		border: 0;
		outline: 0;
		background: transparent;
		color: transparent;
		caret-color: var(--fg);
		overflow: auto;
		scrollbar-gutter: stable;
	}
	.ddl-edit-ta::placeholder { color: var(--fg3); opacity: 0.7; }
	.ddl-edit-ta::selection { background: color-mix(in srgb, var(--accent) 28%, transparent); }
	.ddl-edit-ta:disabled { cursor: not-allowed; opacity: 0.72; }
	.ddl-editor-support {
		display: flex;
		flex-direction: column;
		gap: 7px;
		max-height: min(210px, 35%);
		overflow: auto;
		padding-top: 8px;
	}
	.ddl-unknown-names {
		display: flex;
		flex-direction: column;
		gap: 4px;
		padding: 8px 10px;
		border: 1px solid var(--ddl-token-unknown-border);
		border-radius: var(--r);
		background: var(--ddl-token-unknown-bg);
		font-size: var(--ui-font-size-11);
		line-height: 1.5;
	}
	.ddl-unknown-title,
	.ddl-unknown-name { color: var(--ddl-token-unknown-fg); }
	.ddl-unknown-title { font-weight: 500; }
	.ddl-unknown-name { font-family: inherit; }
	.ddl-unknown-row { display: flex; flex-wrap: wrap; align-items: baseline; gap: 8px; }
	.ddl-unknown-hint { color: var(--fg2); }
	.ddl-editor-guide {
		border: 1px solid var(--border2);
		border-radius: var(--r);
		background: var(--panel);
		color: var(--fg3);
		font-size: var(--ui-font-size-11);
		line-height: 1.55;
	}
	.ddl-editor-guide summary {
		padding: 8px 10px;
		color: var(--fg2);
		cursor: pointer;
	}
	.ddl-editor-guide p { margin: 0; padding: 0 10px 10px; white-space: pre-line; }
	.ddl-editor-vocabulary :global(.saijiki-inline) { height: 100%; }
	@media (max-width: 760px) {
		.ddl-editor-toolbar { flex-wrap: wrap; }
		.ddl-editor-status { margin-left: 0; }
	}
</style>
