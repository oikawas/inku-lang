<script lang="ts">
	type HistoryItem = {
		id?: string;
		svg: string;
		at: number;
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
	{@html clippedSvg}
</div>

<style>
	.history-thumbnail {
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
