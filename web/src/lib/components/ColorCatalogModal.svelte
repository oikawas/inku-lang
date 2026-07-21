<script lang="ts">
	import { getLang, t } from '$lib/i18n/index.svelte';
	import type { ColorCatalog } from '$lib/colors';

	type Props = {
		catalogs: ColorCatalog[];
		selectedCatalog: string;
		currentCatalog: ColorCatalog;
		onSelectCatalog: (id: string) => void;
		onCancel: () => void;
		onConfirm: () => void;
	};

	let {
		selectedCatalog,
		currentCatalog,
		catalogs,
		onSelectCatalog,
		onCancel,
		onConfirm,
	}: Props = $props();

	function isLightColor(hex: string): boolean {
		const value = hex.replace('#', '');
		const r = parseInt(value.slice(0, 2), 16);
		const g = parseInt(value.slice(2, 4), 16);
		const b = parseInt(value.slice(4, 6), 16);
		return (r * 299 + g * 587 + b * 114) / 1000 > 224;
	}

	function catalogSub(catalog: ColorCatalog): string {
		return getLang() === 'ja' ? (catalog.sub_ja ?? catalog.sub) : catalog.sub;
	}

	function paletteName(color: { name: string; name_ja?: string }): string {
		if (getLang() !== 'ja' || !color.name_ja) return color.name;
		return `${color.name}（${color.name_ja}）`;
	}
</script>

<div class="modal-backdrop" onclick={onConfirm} aria-hidden="true"></div>
<div class="catalog-modal" role="dialog" aria-modal="true" tabindex="-1">
	<div class="catalog-modal-head">
		<div class="catalog-modal-title">{t().colorCatalogTitle}</div>
	</div>
	<div class="catalog-body">
		<div class="catalog-scroll">
			{#each catalogs as cat (cat.id)}
				{@const active = selectedCatalog === cat.id}
				<button
					class="catalog-item"
					class:active
					onclick={() => onSelectCatalog(cat.id)}
				>
					<div class="catalog-swatches">
						{#each cat.swatches as hex (hex)}
							<div class="catalog-swatch" style="background:{hex}"></div>
						{/each}
					</div>
					<div class="catalog-info">
						<div class="catalog-name">{cat.name}</div>
						<div class="catalog-sub">{catalogSub(cat)}</div>
					</div>
					{#if active}<span class="catalog-check">✓</span>{/if}
				</button>
			{/each}
		</div>
		<div class="catalog-detail">
			<div class="section-label">{currentCatalog.name} — {t().colorCatalogDetail}</div>
			<div class="catalog-detail-list">
				{#each currentCatalog.palette as color (color.code)}
					<div class="catalog-color-row">
						<div class="catalog-color-box" class:light={isLightColor(color.code)} style="background:{color.code}"></div>
						<span class="catalog-color-name">{paletteName(color)}</span>
						<span class="catalog-color-code">{color.code}</span>
					</div>
				{/each}
			</div>
		</div>
	</div>
	<div class="catalog-modal-foot">
		<button class="ghost-btn" onclick={onCancel}>{t().confirmCancel}</button>
		<button class="ghost-btn primary-inline" onclick={onConfirm}>{t().colorCatalogConfirm}</button>
	</div>
</div>

<style>
	.modal-backdrop {
		position: fixed; inset: 0; z-index: 400;
		background: rgba(0,0,0,0.25); backdrop-filter: blur(2px);
	}
	.catalog-modal {
		position: fixed; top: 50%; left: 50%; transform: translate(-50%, -50%);
		z-index: 401;
		width: min(820px, calc(100vw - 32px)); max-height: 88vh;
		background: var(--panel2); border-radius: var(--r-lg);
		box-shadow: 0 12px 48px rgba(0,0,0,0.18);
		display: flex; flex-direction: column; overflow: hidden;
	}
	.catalog-modal-head {
		display: flex; align-items: center; justify-content: space-between;
		padding: 14px 18px 10px; border-bottom: 1px solid var(--border); flex-shrink: 0;
	}
	.catalog-modal-title { font-size: 15px; font-weight: 300; letter-spacing: 0.05em; }
	.catalog-body {
		display: grid;
		grid-template-columns: minmax(340px, 1fr) minmax(260px, 0.75fr);
		flex: 1;
		min-height: 0;
	}
	.catalog-scroll { min-height: 0; overflow-y: auto; padding: 12px; display: flex; flex-direction: column; gap: 6px; }
	.catalog-item {
		display: flex; align-items: center; gap: 12px; padding: 10px 12px;
		border: 1px solid var(--border); border-radius: var(--r);
		background: var(--panel); cursor: pointer; text-align: left;
		transition: border-color 0.12s, background 0.12s; font-family: inherit; width: 100%;
	}
	.catalog-item.active { border: 1.5px solid var(--accent); background: var(--accent-light); }
	.catalog-item:hover:not(.active) { background: var(--bg); }
	.catalog-swatches {
		display: flex; flex-shrink: 0; border-radius: 3px; overflow: hidden; height: 32px; width: 64px;
	}
	.catalog-swatch { flex: 1; }
	.catalog-info { flex: 1; min-width: 0; }
	.catalog-name { font-size: 12px; font-weight: 500; color: var(--fg); margin-bottom: 1px; }
	.catalog-sub { font-size: 11px; color: var(--fg3); }
	.catalog-check { color: var(--accent); font-size: 13px; flex-shrink: 0; }
	.catalog-detail {
		border-left: 1px solid var(--border);
		padding: 12px 16px 14px;
		background: var(--panel);
		min-height: 0;
		overflow-y: auto;
	}
	.section-label {
		font-size: 10px; font-weight: 500; letter-spacing: 0.08em;
		color: var(--fg3); text-transform: uppercase;
	}
	.catalog-detail-list { display: flex; flex-direction: column; gap: 4px; margin-top: 8px; }
	.catalog-color-row {
		display: flex; align-items: center; gap: 10px;
		font-size: 12px;
	}
	.catalog-color-box {
		width: 28px; height: 28px; border-radius: 3px; flex-shrink: 0;
	}
	.catalog-color-box.light { border: 1px solid var(--border); }
	.catalog-color-name { color: var(--fg); flex: 1; }
	.catalog-color-code {
		font-size: 11px; color: var(--fg3);
		font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
	}
	.catalog-modal-foot {
		display: flex;
		justify-content: flex-end;
		gap: 8px;
		padding: 10px 18px 14px;
		border-top: 1px solid var(--border);
		background: var(--panel2);
		flex-shrink: 0;
	}
	.ghost-btn {
		padding: var(--btn-sm-padding);
		border: 1px solid var(--border2);
		border-radius: var(--btn-sm-radius);
		background: var(--panel);
		color: var(--fg2);
		font-size: var(--btn-sm-font-size);
		cursor: pointer;
		font-family: inherit;
	}
	.ghost-btn:hover { background: var(--bg2); }
	.primary-inline {
		background: var(--fg);
		color: #fff;
		border-color: var(--fg);
	}
	@media (max-width: 760px) {
		.catalog-body { grid-template-columns: 1fr; }
		.catalog-detail { border-left: none; border-top: 1px solid var(--border); }
	}
</style>
