<script lang="ts">
	import { t } from '$lib/i18n/index.svelte';
	type HistoryItem = {
		id?: string;
		svg: string;
		at: number;
		// v1.98: Stage 1 フォールバックで描かれた作品の理由。null = 通常の解釈。
		interpret_fallback?: string | null;
	};

	type Size = 'strip' | 'manager' | 'mini';

	type Props = {
		item: HistoryItem;
		scope: string;
		size?: Size;
	};

	let { item, scope, size = 'strip' }: Props = $props();

	const clipId = $derived(`thumb-clip-${scope}-${String(item.id ?? item.at).replace(/[^a-zA-Z0-9_-]/g, '-')}`);
	const clippedSvg = $derived.by(() => {
		if (!item.svg) return '';
		const viewBox = item.svg.match(/\sviewBox="([^"]+)"/)?.[1]?.split(/\s+/).map(Number);
		const [x, y, w, h] = viewBox && viewBox.length === 4 && viewBox.every(Number.isFinite)
			? viewBox
			: [0, 0, 1000, 1000];
		const clip = `<defs><clipPath id="${clipId}"><rect x="${x}" y="${y}" width="${w}" height="${h}"/></clipPath></defs><g clip-path="url(#${clipId})">`;
		return item.svg
			.replace(/(<svg\b[^>]*)(>)/, (_match, open, close) => {
				const attrs = String(open)
					.replace(/\s+overflow="[^"]*"/g, '')
					.replace(/\s+style="([^"]*)"/, (_styleMatch: string, style: string) => ` style="${style};overflow:hidden"`);
				const withOverflow = attrs.includes(' style=')
					? attrs
					: `${attrs} style="overflow:hidden"`;
				return `${withOverflow} overflow="hidden"${close}${clip}`;
			})
			.replace(/<\/svg>\s*$/i, '</g></svg>');
	});
</script>

<div class="history-thumbnail" class:strip={size === 'strip'} class:manager={size === 'manager'} class:mini={size === 'mini'}>
	{#if item.interpret_fallback}
		<span class="thumb-fallback-mark" title={t().interpretFallbackBadge} aria-label={t().interpretFallbackBadge}></span>
	{/if}
	{@html clippedSvg}
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
	.history-thumbnail :global(svg) {
		width: 100%;
		height: 100%;
		display: block;
		overflow: hidden;
		clip-path: inset(0);
	}
</style>
