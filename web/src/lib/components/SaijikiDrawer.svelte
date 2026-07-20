<script lang="ts">
	import { SAIJIKI } from '$lib/saijiki';
	import { getLang, t } from '$lib/i18n/index.svelte';

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
		open: boolean;
		pluginEntries: PluginEntry[];
		activePreview: SaijikiPreview | null;
		onClose: () => void;
		previewForWord: (categoryKey: string, canonicalWord: string, word: string) => SaijikiPreview;
	};

	let {
		open,
		pluginEntries,
		activePreview = $bindable(),
		onClose,
		previewForWord,
	}: Props = $props();
</script>

<div class="saijiki-drawer" class:open aria-hidden={!open}>
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
			{#each SAIJIKI as cat, ci (cat.key)}
				{@const words = t().saijikiWords[cat.key] ?? cat.words}
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
					<div class="saijiki-chips">
						{#each pluginEntries as entry (entry.qualified_name)}
							<div class="plugin-word-with-note">
								<button
									class="saijiki-chip plugin-chip"
									title={getLang() === "ja" ? entry.note_ja : entry.note_en}
									onpointerdown={(e) => e.preventDefault()}
								>{entry.qualified_name}</button>
								{#if getLang() === "ja" ? entry.note_ja : entry.note_en}
									<span class="plugin-note">{getLang() === "ja" ? entry.note_ja : entry.note_en}</span>
								{/if}
							</div>
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
	.saijiki-preview-art {
		height: 92px;
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
	.saijiki-cat.plugin-cat { border-left: 2px solid rgba(185, 88, 69, 0.45); }
	.saijiki-chip.plugin-chip { color: #9f4b3b; border-color: rgba(185, 88, 69, 0.35); background: rgba(185, 88, 69, 0.08); }
	.plugin-word-with-note { display: flex; flex-direction: column; gap: 3px; max-width: 18rem; }
	.plugin-note { color: var(--muted); font-size: 0.68rem; line-height: 1.25; }
	.saijiki-chip:hover { background: var(--bg2); border-color: var(--fg3); }
</style>
