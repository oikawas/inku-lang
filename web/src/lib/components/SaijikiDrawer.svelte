<script lang="ts">
	import { SAIJIKI, saijikiWordsFor } from '$lib/saijiki';
	import { getLang, t } from '$lib/i18n/index.svelte';

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
		open: boolean;
		pluginEntries: PluginEntry[];
		activePreview: SaijikiPreview | null;
		onClose: () => void;
		previewForWord: (categoryKey: string, canonicalWord: string, word: string) => SaijikiPreview;
		/** The same preview a built-in word gets, built from the plugin document. */
		previewForPlugin: (entry: PluginEntry) => SaijikiPreview;
	};

	let {
		open,
		pluginEntries,
		activePreview = $bindable(),
		onClose,
		previewForWord,
		previewForPlugin,
	}: Props = $props();

	let drawerEl = $state<HTMLDivElement | null>(null);
</script>

<svelte:window
	onpointerdown={(event) => {
		// Pressing outside closes it, the way the provenance drawer already does.
		// The button that opens it is not "outside": it toggles itself, so closing
		// here would be undone by the click that follows this pointerdown, and the
		// drawer would never close from its own button. It is found by the
		// attribute rather than by a class, because a class is a style that can be
		// renamed without anything noticing this reads it.
		if (!open) return;
		const target = event.target as Element | null;
		if (!target) return;
		if (drawerEl?.contains(target)) return;
		if (target.closest?.('[data-saijiki-toggle]')) return;
		onClose();
	}}
/>

<div bind:this={drawerEl} class="saijiki-drawer" class:open aria-hidden={!open}>
	<div class="saijiki-inner">
		<div class="saijiki-head">
			<div>
				<div class="saijiki-title">{t().saijikiTitle}</div>
				<div class="saijiki-hint">{t().saijikiHint}</div>
			</div>
			<button class="saijiki-close" onclick={onClose} aria-label={t().closeLabel}>×</button>
		</div>
		<div class="saijiki-body">
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
			{#each SAIJIKI as cat, ci (cat.key)}
				{@const words = saijikiWordsFor(cat.key, getLang() === 'ja')}
				<div class="saijiki-cat" class:plugin-cat={cat.key.startsWith("plugin-")} style="border-bottom: {ci < SAIJIKI.length - 1 ? '1px solid var(--border)' : 'none'}">
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
								onclick={() => (activePreview = previewForWord(cat.key, canonicalWord, word))}
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
					<!-- Packed the same way the built-in words are: the note that
					     used to sit under each chip is what the preview above now
					     says, so the chips need no column of their own. -->
					<div class="saijiki-chips">
						{#each pluginEntries as entry (entry.qualified_name)}
							<button
								class="saijiki-chip plugin-chip"
								onpointerdown={(e) => e.preventDefault()}
								onclick={() => (activePreview = previewForPlugin(entry))}
								onpointerenter={() => (activePreview = previewForPlugin(entry))}
								onfocus={() => (activePreview = previewForPlugin(entry))}
							>{entry.qualified_name}</button>
						{/each}
					</div>
				</div>
			{/if}
		</div>
	</div>
</div>

<style>
	.saijiki-drawer {
		position: fixed; top: 0; right: 0; bottom: 0;
		width: 0; overflow: hidden; z-index: 300;
		transition: width 0.25s cubic-bezier(0.4,0,0.2,1);
		pointer-events: none;
	}
	.saijiki-drawer.open { width: 460px; pointer-events: all; }

	.saijiki-inner {
		width: 460px; height: 100%;
		background: var(--panel2); border-left: 1px solid var(--border);
		display: flex; flex-direction: column;
		box-shadow: -4px 0 24px rgba(0,0,0,0.08);
	}
	.saijiki-head {
		padding: 16px 18px 12px;
		border-bottom: 1px solid var(--border);
		display: flex; align-items: flex-start; justify-content: space-between;
		flex-shrink: 0;
	}
	.saijiki-title {
		font-size: 17px; font-weight: 300; letter-spacing: 0.06em; color: var(--fg);
	}
	.saijiki-hint { font-size: 10px; color: var(--fg3); margin-top: 3px; line-height: 1.5; }
	.saijiki-close {
		width: 24px; height: 24px; border: none; background: none;
		color: var(--fg3); font-size: 16px; cursor: pointer; flex-shrink: 0; margin-top: 2px;
	}
	.saijiki-body { flex: 1; overflow-y: auto; padding: 8px 0; }

	.saijiki-preview {
		position: sticky;
		top: 0;
		z-index: 2;
		margin: 0 12px 8px;
		padding: 10px;
		border: 1px solid var(--border);
		border-radius: var(--r);
		background: rgba(255, 253, 248, 0.96);
		box-shadow: 0 6px 18px rgba(37, 34, 26, 0.08);
		backdrop-filter: blur(4px);
	}
	.saijiki-preview.empty {
		box-shadow: none;
		background: rgba(255, 255, 255, 0.72);
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
		margin-top: 8px;
	}
	.saijiki-preview-title {
		font-size: 13px;
		font-weight: 600;
		color: var(--fg);
	}
	.saijiki-preview-effect {
		font-size: 11px;
		line-height: 1.45;
		color: var(--fg2);
	}
	.saijiki-preview-example {
		font-size: 10px;
		line-height: 1.4;
		color: var(--fg3);
	}
	.saijiki-preview-placeholder {
		font-size: 11px;
		line-height: 1.5;
		color: var(--fg3);
	}
	.saijiki-cat { padding: 10px 18px; }
	.saijiki-cat-head { display: flex; align-items: baseline; gap: 7px; margin-bottom: 8px; }
	.saijiki-cat-ja { font-size: 13px; font-weight: 400; color: var(--fg); letter-spacing: 0.05em; }
	.saijiki-cat-en { font-size: 9px; color: var(--fg3); letter-spacing: 0.1em; text-transform: uppercase; font-weight: 500; }

	.saijiki-chips { display: flex; flex-wrap: wrap; gap: 5px; }
	.saijiki-chip {
		padding: 4px 9px; border: 1px solid var(--border2); border-radius: 3px;
		background: var(--panel); color: var(--fg); font-size: 12px; cursor: pointer;
		font-family: inherit; line-height: 1.3; transition: background 0.1s, border-color 0.1s;
	}
	/* The plugin accent is the app's blue, from the tokens, so it follows the
	   theme instead of carrying its own pair of hard-coded colours. Only the
	   accent differs from a built-in chip -- size, padding and packing are the
	   ones above. */
	.saijiki-cat.plugin-cat { border-left: 2px solid var(--accent); }
	.saijiki-chip.plugin-chip { color: var(--accent); border-color: var(--accent); background: var(--accent-light); }
	.saijiki-chip:hover { background: var(--bg2); border-color: var(--fg3); }
</style>
