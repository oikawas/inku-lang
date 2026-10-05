<script lang="ts">
	import { t } from '$lib/i18n/index.svelte';
	import type { RangePreview } from '$lib/composition-ranges';
	let { artworkUrl = null, preview = null }: { artworkUrl?: string | null; preview?: RangePreview | null } = $props();
</script>

<figure class="ddl-range-preview">
	{#if artworkUrl}
		<div class="ddl-range-artwork">
			<img src={artworkUrl} alt={t().ddlEditorArtwork} />
			{#if preview}
				<div class="ddl-range-frame" class:invalid={preview.invalid} aria-hidden="true"
					style:left={`${preview.bounds[0] * 100}%`} style:top={`${preview.bounds[1] * 100}%`}
					style:width={`${(preview.bounds[2] - preview.bounds[0]) * 100}%`} style:height={`${(preview.bounds[3] - preview.bounds[1]) * 100}%`}></div>
			{/if}
		</div>
	{:else}
		<p class="ddl-range-empty">{t().ddlEditorNoArtwork}</p>
	{/if}
	<figcaption>{t().ddlEditorRangeHint}</figcaption>
</figure>

<style>
	.ddl-range-preview { margin: 0; flex-shrink: 0; width: min(210px, 28%); display: flex; flex-direction: column; align-items: center; gap: 8px; }
	.ddl-range-artwork { display: inline-block; position: relative; line-height: 0; max-width: 100%; }
	.ddl-range-artwork img { display: block; max-width: 100%; max-height: 150px; width: auto; height: auto; }
	.ddl-range-frame { position: absolute; box-sizing: border-box; border: 2px dashed var(--accent); pointer-events: none; }
	.ddl-range-frame.invalid { border-style: dotted; }
	.ddl-range-empty, figcaption { margin: 0; color: var(--fg3); font-size: var(--ui-font-size-12); line-height: 1.5; }
	@media (max-width: 760px) {
		.ddl-range-preview { width: 100%; flex-direction: row; justify-content: flex-start; }
		.ddl-range-artwork { flex-shrink: 0; max-width: 100px; }
		.ddl-range-artwork img { max-height: 72px; }
	}
</style>
