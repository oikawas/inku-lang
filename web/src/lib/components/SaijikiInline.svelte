<script lang="ts">
	import { t } from '$lib/i18n/index.svelte';
	import { SAIJIKI, saijikiWordsFor } from '$lib/saijiki';

	type SaijikiPreview = {
		categoryKey: string;
		word: string;
		canonicalWord: string;
		effect: string;
		example: string;
		svg: string;
		/** Raster artwork, served by its own route. Set for plugin words;
		    built-in words carry their drawing in `svg` instead. */
		image?: string;
		image2x?: string;
	};

	type PluginEntry = {
		qualified_name: string;
		note_ja: string;
		note_en: string;
		fires_on_ja?: string[];
		fires_on_en?: string[];
		preview_url?: string;
		preview_url_2x?: string;
	};

	type Props = {
		activePreview: SaijikiPreview | null;
		/** Namespaced plugin vocabulary, same list the saijiki drawer shows. */
		pluginEntries?: PluginEntry[];
		onInsertWord: (word: string) => void;
		previewForWord: (categoryKey: string, canonicalWord: string, word: string) => SaijikiPreview;
		/** The same preview a built-in word gets, built from the plugin document. */
		previewForPlugin: (entry: PluginEntry) => SaijikiPreview;
	};

	let {
		activePreview = $bindable(),
		pluginEntries = [],
		onInsertWord,
		previewForWord,
		previewForPlugin,
	}: Props = $props();

	const isJapanese = $derived(t().code === 'ja');
</script>

<aside class="saijiki-inline">
	<div class="saijiki-head">
		<div class="saijiki-title">{t().saijikiTitle}</div>
		<div class="saijiki-hint">{t().saijikiHint}</div>
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
	<div class="saijiki-list">
		{#each SAIJIKI as cat (cat.key)}
			{@const words = saijikiWordsFor(cat.key, isJapanese)}
			<div class="saijiki-cat" class:plugin-cat={cat.key.startsWith("plugin-")}>
				<div class="saijiki-cat-head">
					<span class="saijiki-cat-ja">{cat.label}</span>
					<span class="saijiki-cat-en">{cat.en}</span>
				</div>
				<div class="saijiki-chips">
					{#each words as word, wi (word)}
						{@const canonicalWord = cat.words[wi] ?? word}
						<button
							class="saijiki-chip"
							class:plugin-chip={cat.key.startsWith("plugin-")}
							onpointerdown={(e) => e.preventDefault()}
							onclick={() => onInsertWord(word)}
							onpointerenter={() => (activePreview = previewForWord(cat.key, canonicalWord, word))}
							onfocus={() => (activePreview = previewForWord(cat.key, canonicalWord, word))}
						>{word}</button>
					{/each}
				</div>
			</div>
		{/each}
		{#if pluginEntries.length > 0}
			<div class="saijiki-cat plugin-cat">
				<div class="saijiki-cat-head">
					<span class="saijiki-cat-ja">Plugin</span>
					<span class="saijiki-cat-en">namespaced vocabulary</span>
				</div>
				<!-- Packed the same way the built-in words are, and reached the
				     same way: hover or focus shows the word in the preview above,
				     a click inserts it. The note that used to sit under each chip
				     is what the preview now says. -->
				<div class="saijiki-chips">
					{#each pluginEntries as entry (entry.qualified_name)}
						<button
							class="saijiki-chip plugin-chip"
							onpointerdown={(e) => e.preventDefault()}
							onclick={() => onInsertWord(entry.qualified_name)}
							onpointerenter={() => (activePreview = previewForPlugin(entry))}
							onfocus={() => (activePreview = previewForPlugin(entry))}
						>{entry.qualified_name}</button>
					{/each}
				</div>
			</div>
		{/if}
	</div>
</aside>

<style>
	.saijiki-inline {
		display: flex;
		flex-direction: column;
		min-height: 0;
		max-height: none;
		border: 1px solid var(--border);
		border-radius: var(--r);
		background: var(--panel2);
		overflow: hidden;
	}
	.saijiki-head {
		padding: 12px 12px 10px;
		border-bottom: 1px solid var(--border);
		flex-shrink: 0;
	}
	.saijiki-title {
		font-size: 14px;
		font-weight: 500;
		letter-spacing: 0.06em;
		color: var(--fg);
	}
	.saijiki-hint {
		margin-top: 3px;
		font-size: 10px;
		line-height: 1.45;
		color: var(--fg3);
	}
	.saijiki-preview {
		margin: 10px;
		padding: 9px;
		border: 1px solid var(--border);
		border-radius: var(--r);
		background: var(--panel);
		flex-shrink: 0;
		overflow: hidden;
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
		font-size: 12px;
		font-weight: 600;
		color: var(--fg);
	}
	.saijiki-preview-effect {
		font-size: 10px;
		line-height: 1.45;
		color: var(--fg2);
	}
	.saijiki-preview-example,
	.saijiki-preview-placeholder {
		font-size: 10px;
		line-height: 1.45;
		color: var(--fg3);
	}
	.saijiki-list {
		display: grid;
		grid-template-columns: repeat(2, minmax(0, 1fr));
		gap: 0;
		overflow-y: auto;
		overflow-x: hidden;
		padding: 0 0 10px;
		min-width: 0;
		min-height: 0;
	}
	.saijiki-cat {
		padding: 8px 12px 10px;
		border-bottom: 1px solid var(--border);
	}
	.saijiki-cat:nth-child(2n) {
		border-left: 1px solid var(--border);
	}
	.saijiki-cat-head {
		display: flex;
		align-items: baseline;
		gap: 7px;
		margin-bottom: 7px;
	}
	.saijiki-cat-ja {
		font-size: 12px;
		font-weight: 500;
		color: var(--fg);
		letter-spacing: 0.04em;
	}
	.saijiki-cat-en {
		font-size: 9px;
		color: var(--fg3);
		letter-spacing: 0.08em;
		text-transform: uppercase;
		font-weight: 500;
	}
	.saijiki-chips {
		display: flex;
		flex-wrap: wrap;
		gap: 5px;
	}
	.saijiki-chip {
		padding: 4px 8px;
		border: 1px solid var(--border2);
		border-radius: 3px;
		background: var(--panel);
		color: var(--fg);
		font-size: 12px;
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
	.saijiki-chip.plugin-chip { color: var(--accent); border-color: var(--accent); background: var(--accent-light); }
	.saijiki-chip:hover,
	.saijiki-chip:focus-visible {
		background: var(--bg2);
		border-color: var(--fg3);
		outline: none;
	}
	@media (max-width: 900px) {
		.saijiki-inline {
			max-height: none;
		}
		.saijiki-head {
			border-bottom: 1px solid var(--border);
		}
		.saijiki-preview {
			width: auto;
		}
		.saijiki-list {
			padding: 0 0 10px;
		}
	}
</style>
