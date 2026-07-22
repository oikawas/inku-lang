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
	};

	type PluginEntry = {
		qualified_name: string;
		note_ja: string;
		note_en: string;
	};

	type Props = {
		activePreview: SaijikiPreview | null;
		/** Namespaced plugin vocabulary, same list the saijiki drawer shows. */
		pluginEntries?: PluginEntry[];
		onInsertWord: (word: string) => void;
		previewForWord: (categoryKey: string, canonicalWord: string, word: string) => SaijikiPreview;
	};

	let {
		activePreview = $bindable(),
		pluginEntries = [],
		onInsertWord,
		previewForWord,
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
			<div class="saijiki-preview-art">{@html activePreview.svg}</div>
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
				<div class="saijiki-chips">
					{#each pluginEntries as entry (entry.qualified_name)}
						<div class="plugin-word-with-note">
							<button
								class="saijiki-chip plugin-chip"
								onpointerdown={(e) => e.preventDefault()}
								onclick={() => onInsertWord(entry.qualified_name)}
							>{entry.qualified_name}</button>
							{#if isJapanese ? entry.note_ja : entry.note_en}
								<span class="plugin-note">{isJapanese ? entry.note_ja : entry.note_en}</span>
							{/if}
						</div>
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
	.saijiki-preview-art {
		height: 76px;
		border: 1px solid var(--border);
		border-radius: var(--r);
		overflow: hidden;
		background: var(--canvas-paper);
	}
	.saijiki-preview-art :global(svg) {
		display: block;
		width: 100%;
		height: 100%;
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
	.saijiki-cat.plugin-cat { border-left: 2px solid rgba(185, 88, 69, 0.45); }
	.saijiki-chip.plugin-chip { color: #9f4b3b; border-color: rgba(185, 88, 69, 0.35); background: rgba(185, 88, 69, 0.08); }
	:global(html[data-theme='dark']) .saijiki-chip.plugin-chip { color: #f0a58f; border-color: rgba(226, 138, 112, 0.45); background: rgba(185, 88, 69, 0.22); }
	.plugin-word-with-note { display: flex; flex-direction: column; gap: 3px; max-width: 18rem; }
	.plugin-note { color: var(--fg3); font-size: 0.68rem; line-height: 1.25; }
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
