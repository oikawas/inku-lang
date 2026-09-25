<script lang="ts">
	import { getLang, t } from '$lib/i18n/index.svelte';
	import { pluginDisplayName } from '$lib/plugin-names';
	import { SAIJIKI, saijikiWordsFor } from '$lib/saijiki';
	import type { ResolvedInstructionLang } from '$lib/instructionLang';
	import type { PluginEntry, PreviewForPlugin, PreviewForWord, SaijikiPreview } from '$lib/features/ddl-editor/types';

	type Props = {
		activePreview: SaijikiPreview | null;
		/**
		 * The language to offer the words in. This is the DDL's language, not
		 * the UI's: the two are independent (`instruction_lang` is resolved from
		 * the text), and a word inserted from here becomes part of that DDL, so
		 * offering it in the other language is offering the wrong word.
		 */
		wordLang: ResolvedInstructionLang;
		/** Namespaced plugin vocabulary, same list the saijiki drawer shows. */
		pluginEntries?: PluginEntry[];
		onInsertWord: (word: string) => void;
		previewForWord: PreviewForWord;
		/** The same preview a built-in word gets, built from the plugin document. */
		previewForPlugin: PreviewForPlugin;
		disabled?: boolean;
	};

	let {
		activePreview = $bindable(),
		wordLang,
		pluginEntries = [],
		onInsertWord,
		previewForWord,
		previewForPlugin,
		disabled = false,
	}: Props = $props();

	const uiIsJapanese = $derived(getLang() === 'ja');
</script>

<aside class="saijiki-inline">
	<div class="saijiki-head">
		<div class="saijiki-title">{t().saijikiTitle}</div>
		<div class="saijiki-hint">{t().saijikiHint}</div>
	</div>
	<div class="saijiki-body">
		<div class="saijiki-list">
			<div class="saijiki-list-columns">
				{#each SAIJIKI as cat (cat.key)}
					{@const words = saijikiWordsFor(cat.key, wordLang === 'ja')}
					<div class="saijiki-cat" class:plugin-cat={cat.key.startsWith('plugin-')}>
						<div class="saijiki-cat-head">{uiIsJapanese ? cat.label : cat.en}</div>
						<div class="saijiki-chips">
							{#each words as word, wi (word)}
								{@const canonicalWord = cat.words[wi] ?? word}
								<button
									class="saijiki-chip"
									class:plugin-chip={cat.key.startsWith('plugin-')}
									{disabled}
									onpointerdown={(e) => e.preventDefault()}
									onclick={() => onInsertWord(word)}
									onpointerenter={() => (activePreview = previewForWord(cat.key, canonicalWord, word, wordLang))}
									onfocus={() => (activePreview = previewForWord(cat.key, canonicalWord, word, wordLang))}
								>{word}</button>
							{/each}
						</div>
					</div>
				{/each}
				{#if pluginEntries.length > 0}
					<div class="saijiki-cat plugin-cat">
						<div class="saijiki-cat-head">Plugin</div>
						<!-- Packed the same way the built-in words are, and reached the
						     same way: hover or focus shows the word in the preview, a
						     click inserts it. -->
						<div class="saijiki-chips">
							{#each pluginEntries as entry (entry.qualified_name)}
								<button
									class="saijiki-chip plugin-chip"
									{disabled}
									onpointerdown={(e) => e.preventDefault()}
									onclick={() => onInsertWord(pluginDisplayName(entry, wordLang))}
									onpointerenter={() => (activePreview = previewForPlugin(entry, wordLang))}
									onfocus={() => (activePreview = previewForPlugin(entry, wordLang))}
								>{pluginDisplayName(entry, wordLang)}</button>
							{/each}
						</div>
					</div>
				{/if}
			</div>
		</div>
		<div class="saijiki-preview" class:empty={!activePreview}>
			{#if activePreview}
				<!-- A plugin word's artwork is a raster from its own route, so it
				     goes in an <img>: nothing a plugin document ships can put
				     markup on screen. Built-in words keep their inline drawing. -->
				<div class="saijiki-preview-art">
					{#if activePreview.image}
						<img
							src={activePreview.image}
							srcset={activePreview.image2x ? `${activePreview.image} 1x, ${activePreview.image2x} 2x` : undefined}
							alt=""
							loading="lazy"
						/>
					{:else}
						{@html activePreview.svg}
					{/if}
				</div>
				<div class="saijiki-preview-copy">
					<div class="saijiki-preview-title">{activePreview.word}</div>
					<div class="saijiki-preview-effect">{activePreview.effect}</div>
					<div class="saijiki-preview-example">{activePreview.example}</div>
				</div>
			{:else}
				<div class="saijiki-preview-placeholder">{t().saijikiPreviewPlaceholder}</div>
			{/if}
		</div>
	</div>
</aside>

<style>
	.saijiki-inline {
		display: flex;
		flex-direction: column;
		container-type: inline-size;
		min-height: 0;
		max-height: none;
		border: 1px solid var(--border);
		border-radius: var(--r);
		background: var(--panel2);
		overflow: hidden;
	}
	.saijiki-head {
		display: flex;
		align-items: baseline;
		gap: 10px;
		padding: 8px 10px;
		border-bottom: 1px solid var(--border);
		flex-shrink: 0;
	}
	.saijiki-title {
		font-size: var(--ui-font-size-14);
		font-weight: 500;
		letter-spacing: 0.06em;
		color: var(--fg);
	}
	.saijiki-hint {
		min-width: 0;
		font-size: var(--ui-font-size-12);
		line-height: 1.45;
		color: var(--fg3);
	}
	.saijiki-body {
		display: grid;
		grid-template-columns: minmax(0, 1fr) 236px;
		gap: 10px;
		padding: 10px;
		flex: 1;
		min-height: 0;
		overflow: hidden;
	}
	.saijiki-preview {
		box-sizing: border-box;
		padding: 9px;
		border: 1px solid var(--border);
		border-radius: var(--r);
		background: var(--panel);
		flex-shrink: 0;
		overflow: auto;
	}
	.saijiki-preview.empty {
		background: var(--bg2);
	}
	/* Sized to the artwork rather than to the panel: a plugin preview is a
	   raster, and it is baked at exactly these pixels so it is never
	   scaled. Built-in words draw vectors and are unaffected by the
	   width; both sit centred, which is what they did before. */
	.saijiki-preview-art {
		width: 216px;
		max-width: 100%;
		height: 92px;
		margin: 0 auto;
		border: 1px solid var(--border);
		border-radius: var(--r);
		overflow: hidden;
		background: var(--canvas-paper);
	}
	.saijiki-preview-art img,
	.saijiki-preview-art :global(svg) {
		display: block;
		width: 100%;
		height: 100%;
		object-fit: contain;
	}
	.saijiki-preview-copy {
		display: flex;
		flex-direction: column;
		gap: 3px;
		margin-top: 7px;
	}
	.saijiki-preview-title {
		font-size: var(--ui-font-size-12);
		font-weight: 600;
		color: var(--fg);
	}
	.saijiki-preview-effect {
		font-size: var(--ui-font-size-12);
		line-height: 1.45;
		color: var(--fg2);
	}
	.saijiki-preview-example,
	.saijiki-preview-placeholder {
		font-size: var(--ui-font-size-12);
		line-height: 1.45;
		color: var(--fg3);
	}
	.saijiki-list {
		overflow-y: auto;
		overflow-x: hidden;
		min-width: 0;
		min-height: 0;
	}
	.saijiki-list-columns {
		column-count: 4;
		column-gap: 6px;
	}
	.saijiki-cat {
		break-inside: avoid;
		margin-bottom: 6px;
		padding: 7px 8px 8px;
		border: 1px solid var(--border);
		border-radius: var(--r);
		background: var(--panel);
	}
	.saijiki-cat-head {
		margin-bottom: 6px;
		font-size: var(--ui-font-size-12);
		font-weight: 500;
		color: var(--fg);
		letter-spacing: 0.08em;
		text-transform: uppercase;
	}
	.saijiki-chips {
		display: flex;
		flex-wrap: wrap;
		gap: 5px;
	}
	.saijiki-chip {
		padding: var(--btn-sm-padding);
		border: 1px solid var(--border2);
		border-radius: var(--btn-sm-radius);
		background: var(--panel);
		color: var(--fg);
		font-size: var(--btn-sm-font-size);
		cursor: pointer;
		font-family: inherit;
		line-height: 1.25;
		transition: background 0.1s, border-color 0.1s;
	}
	/* The plugin accent is the app's blue, from the tokens, so it follows the
	   theme instead of carrying its own pair of hard-coded colours. Only the
	   accent differs from a built-in chip -- size, padding and packing are the
	   ones above. */
	.saijiki-cat.plugin-cat { border-left: 2px solid var(--accent); }
	.saijiki-chip:hover,
	.saijiki-chip:focus-visible {
		background: var(--bg2);
		border-color: var(--fg3);
		outline: none;
	}
	.saijiki-chip:disabled {
		cursor: not-allowed;
		opacity: 0.58;
	}
	@container (min-width: 681px) and (max-width: 1080px) {
		.saijiki-list-columns { column-count: 3; }
	}
	@container (max-width: 680px) {
		.saijiki-head { align-items: flex-start; flex-direction: column; gap: 2px; }
		.saijiki-body {
			grid-template-columns: minmax(0, 1fr);
			grid-template-rows: minmax(0, 1fr) 126px;
			gap: 8px;
			padding: 8px;
		}
		.saijiki-list-columns { column-count: 2; }
		.saijiki-preview { grid-row: 2; display: flex; align-items: flex-start; gap: 10px; }
		.saijiki-preview-art { flex: 0 0 130px; width: 130px; margin: 0; }
		.saijiki-preview-copy { margin-top: 0; }
	}
</style>
