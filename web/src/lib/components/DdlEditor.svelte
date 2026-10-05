<script lang="ts">
	import { onMount, tick } from 'svelte';
	import { t } from '$lib/i18n/index.svelte';
	import { buildPluginNameIndex, unknownPluginNames } from '$lib/plugin-names';
	import { resolveInstructionLang } from '$lib/instructionLang';
	import { createDdlEditor, type DdlEditorControl, type DdlEditorOptions } from '$lib/features/ddl-editor/codemirror';
	import type { RangeEditorStatus } from '$lib/features/ddl-editor/codemirror-ranges';
	import type { CompositionRange } from '$lib/composition-ranges';
	import Tooltip from './Tooltip.svelte';
	import SaijikiInline from './SaijikiInline.svelte';
	import type { PluginEntry, PreviewForPlugin, PreviewForWord, SaijikiPreview } from '$lib/features/ddl-editor/types';

	type Props = {
		value?: string;
		isJapanese: boolean;
		disabled?: boolean;
		pluginEntries?: PluginEntry[];
		previewForWord: PreviewForWord;
		previewForPlugin: PreviewForPlugin;
		ranges?: CompositionRange[];
		onRanges?: (status: RangeEditorStatus) => void;
	};

	let {
		value = $bindable(''),
		isJapanese,
		disabled = false,
		pluginEntries = [],
		previewForWord,
		previewForPlugin,
		ranges = [],
		onRanges,
	}: Props = $props();

	let editorHost = $state<HTMLDivElement | null>(null);
	let control = $state.raw<DdlEditorControl | null>(null);
	let activeSaijikiPreview = $state<SaijikiPreview | null>(null);
	let showVocabulary = $state(true);
	let showGuide = $state(false);

	const lineNumbers = $derived(value.split('\n'));
	const pluginNameIndex = $derived(buildPluginNameIndex(pluginEntries));
	const unknownNames = $derived(unknownPluginNames(value, pluginNameIndex));
	const wordLang = $derived(resolveInstructionLang(value, isJapanese ? 'ja' : 'en'));

	function configuration(): DdlEditorOptions {
		return { isJapanese, disabled, pluginEntries, pluginNameIndex, ranges, previewForWord, previewForPlugin,
			label: t().ddlEditorInstructions, placeholder: t().ddlEditPlaceholder,
			onChange: (next) => value = next, onPreview: (next) => activeSaijikiPreview = next, onRanges: (status) => onRanges?.(status) };
	}

	onMount(() => {
		if (!editorHost) return;
		const mounted = createDdlEditor(editorHost, value, configuration());
		control = mounted;
		return () => { control = null; mounted.destroy(); onRanges?.({ preview: null, invalid: false, composing: false }); };
	});

	$effect(() => {
		control?.configure(configuration());
		control?.setValue(value);
	});

	export function focus(): void { void tick().then(() => control?.focus()); }
	function insertWord(word: string): void { if (!disabled) control?.insertWord(word); }
</script>

<section class="ddl-editor">
	<div class="ddl-editor-toolbar">
		<!-- The Server resolves the language by the same rule when the DDL is drawn. -->
		<Tooltip placement="bottom-right" text={t().tooltipDdlLang}>
			<div class="ddl-editor-toolbar-title">{t().ddlLabelIn(wordLang)}</div>
		</Tooltip>
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
			<div class="ddl-editor-frame" class:readonly={disabled} bind:this={editorHost}></div>

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
		grid-template-rows: minmax(180px, 50%) minmax(0, 1fr);
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
		flex: 1;
		min-height: 80px;
		border: 1px solid var(--accent);
		border-radius: var(--r);
		background: var(--panel);
		overflow: hidden;
	}
	.ddl-editor-frame :global(.cm-editor) { height: 100%; color: var(--fg); font-size: var(--ui-font-size-14); }
	.ddl-editor-frame :global(.cm-focused) { outline: none; }
	.ddl-editor-frame :global(.cm-scroller) { font-family: inherit; line-height: 1.7; overflow: auto; scrollbar-gutter: stable; }
	.ddl-editor-frame :global(.cm-content) { padding: 10px 11px; caret-color: var(--fg); }
	.ddl-editor-frame :global(.cm-gutters) { background: var(--bg2); color: var(--fg3); border-right: 1px solid var(--border2); }
	.ddl-editor-frame :global(.cm-lineNumbers .cm-gutterElement) { padding: 0 8px; min-width: 36px; font-variant-numeric: tabular-nums; }
	.ddl-editor-frame :global(.cm-cursor) { border-left-color: var(--fg); }
	.ddl-editor-frame :global(.cm-selectionBackground) { background: color-mix(in srgb, var(--accent) 28%, transparent) !important; }
	.ddl-editor-frame :global(.cm-placeholder) { color: var(--fg3); }
	.ddl-editor-frame :global(.cm-ddl-range-name) { text-decoration: underline dotted; text-underline-offset: 3px; cursor: pointer; }
	.ddl-editor-frame :global(.cm-tooltip) { border: 1px solid var(--border2); background: var(--panel); color: var(--fg); }
	.ddl-editor-frame :global(.cm-tooltip-autocomplete li[aria-selected]) { background: var(--accent); color: var(--panel); }
	.ddl-editor-frame.readonly { opacity: .72; }
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
