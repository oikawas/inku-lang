<script lang="ts">
	import { t } from '$lib/i18n/index.svelte';
	import { thumbnailConditions, thumbnailSrc } from '$lib/thumbnailSource';
	import { composeFallbackReason, hasFallbackMark } from '$lib/composeFallback';
	import { svgImage } from '$lib/svgImage';
	type HistoryItem = {
		id?: string;
		svg: string;
		at: number;
		render_hash?: string | null;
		// v1.98: Why Stage 1 used its fallback. null means ordinary interpretation.
		interpret_fallback?: string | null;
		// Stage 2's. 'none' is not a mark -- see lib/composeFallback.ts.
		compose_fallback?: string | null;
	};

	type Size = 'strip' | 'manager' | 'mini';

	type Props = {
		item: HistoryItem;
		scope: string;
		size?: Size;
	};

	let { item, size = 'strip' }: Props = $props();

	// A work has no thumbnail until one has been baked for it, and the one on
	// screen the moment it is drawn never does. Missing is answered with 404, so
	// the picture that is already in hand is what gets drawn instead.
	let thumbMissing = $state(false);
	const pngSrc = $derived(thumbMissing ? null : thumbnailSrc(item, thumbnailConditions()));

	// One mark for both layers, worded so it names the one that fell. The
	// condition itself lives in $lib/composeFallback so this and the canvas
	// badge cannot drift into disagreeing about the same work.
	const fallbackMarkLabel = $derived(
		[
			item.interpret_fallback ? t().interpretFallbackBadge : null,
			composeFallbackReason(item.compose_fallback) ? t().composeFallbackBadge : null
		].filter(Boolean).join(' / ')
	);
</script>

<div class="history-thumbnail" class:strip={size === 'strip'} class:manager={size === 'manager'} class:mini={size === 'mini'}>
	{#if hasFallbackMark(item)}
		<span class="thumb-fallback-mark" title={fallbackMarkLabel} aria-label={fallbackMarkLabel}></span>
	{/if}
	{#if pngSrc}
		<img src={pngSrc} alt="" loading="lazy" decoding="async" onerror={() => (thumbMissing = true)} />
	{:else}
		<img use:svgImage={item.svg} alt="" decoding="async" />
	{/if}
</div>

<style>
	.thumb-fallback-mark {
		position: absolute;
		top: 3px;
		right: 3px;
		z-index: 2;
		width: 7px;
		height: 7px;
		border: 1px solid #6b4410;
		border-radius: 50%;
		background: #e0a850;
	}
	.history-thumbnail {
		position: relative;
		overflow: hidden;
		overflow: clip;
		clip-path: inset(0);
		contain: paint;
		background: var(--panel);
	}
	.history-thumbnail.strip {
		width: 82px;
		height: 58px;
	}
	.history-thumbnail.manager {
		width: 100%;
		aspect-ratio: 82 / 58;
		height: auto;
	}
	.history-thumbnail.mini {
		width: 48px;
		height: 36px;
		border: 1px solid var(--border);
	}
	/* `contain` preserves the artwork's aspect ratio for both PNG thumbnails and
	   Blob-backed SVG fallbacks. A work does not change shape between sources. */
	.history-thumbnail img {
		width: 100%;
		height: 100%;
		display: block;
		object-fit: contain;
	}
</style>
