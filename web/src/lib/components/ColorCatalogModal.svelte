<script lang="ts">
	import { getLang, t } from '$lib/i18n/index.svelte';
	import type { ColorCatalog } from '$lib/colors';
	import { AUTO_CATALOG_ID } from '$lib/features/color-catalog/render';

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
		currentCatalog: _currentCatalog,
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

	const autoActive = $derived(selectedCatalog === AUTO_CATALOG_ID);

	function catalogSub(catalog: ColorCatalog): string {
		return getLang() === 'ja' ? (catalog.sub_ja ?? catalog.sub) : catalog.sub;
	}

	function localizedPaletteName(color: { name: string; name_ja?: string }): string | undefined {
		if (getLang() !== 'ja' || !color.name_ja) return undefined;
		return color.name_ja;
	}
</script>

<div class="modal-backdrop" onclick={onConfirm} aria-hidden="true"></div>
<div class="catalog-modal" role="dialog" aria-modal="true" tabindex="-1">
	<div class="catalog-modal-head">
		<div class="catalog-modal-title">{t().colorCatalogTitle}</div>
		<!-- Same handler as the backdrop, so the two dismissal paths agree. -->
		<button class="catalog-close" onclick={onConfirm} aria-label={t().closeLabel}>×</button>
	</div>
	<div class="catalog-body">
		<div class="catalog-scroll">
			<!-- Above the catalogs, and not one of them: it has no palette to show
			     because the server picks per drawing. -->
			<button
				class="catalog-item"
				class:active={autoActive}
				onclick={() => onSelectCatalog(AUTO_CATALOG_ID)}
				aria-pressed={autoActive}
			>
				<div class="catalog-info">
					<div class="catalog-name-row">
						<div class="catalog-name">{t().colorCatalogAuto}</div>
						{#if autoActive}<span class="catalog-check" aria-hidden="true">✓</span>{/if}
					</div>
					<div class="catalog-sub">{t().colorCatalogAutoSub}</div>
				</div>
			</button>
			{#each catalogs as cat (cat.id)}
				{@const active = selectedCatalog === cat.id}
				<button
					class="catalog-item"
					class:active
					onclick={() => onSelectCatalog(cat.id)}
					aria-pressed={active}
				>
					<div class="catalog-info">
						<div class="catalog-name-row">
							<div class="catalog-name">{cat.name}</div>
							{#if active}<span class="catalog-check" aria-hidden="true">✓</span>{/if}
						</div>
						<div class="catalog-id">{cat.id}</div>
						<div class="catalog-sub">{catalogSub(cat)}</div>
					</div>
					<div class="catalog-palette">
						{#each cat.palette as color (color.code)}
							<div class="catalog-color">
								<div class="catalog-color-box" class:light={isLightColor(color.code)} style="background:{color.code}"></div>
								<span class="catalog-color-code">{color.code}</span>
								<span class="catalog-color-name">{color.name}</span>
								{#if localizedPaletteName(color)}
									<span class="catalog-color-localized">{localizedPaletteName(color)}</span>
								{/if}
							</div>
						{/each}
					</div>
				</button>
			{/each}
		</div>
	</div>
	<div class="catalog-modal-foot">
		<button class="ghost-btn" onclick={onCancel}>{t().confirmCancel}</button>
		<button class="ghost-btn" onclick={onConfirm}>{t().colorCatalogConfirm}</button>
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
		width: min(1180px, calc(100vw - 32px)); max-height: 92vh;
		background: var(--panel2); border-radius: var(--r-lg);
		box-shadow: 0 12px 48px rgba(0,0,0,0.18);
		display: flex; flex-direction: column; overflow: hidden;
	}
	.catalog-modal-head {
		display: flex; align-items: center; justify-content: space-between;
		padding: 14px 18px 10px; border-bottom: 1px solid var(--border); flex-shrink: 0;
	}
	.catalog-modal-title { font-size: 15px; font-weight: 300; letter-spacing: 0.05em; }
	.catalog-close {
		width: 24px; height: 24px; border: none; background: none;
		color: var(--fg3); font-size: 18px; cursor: pointer; line-height: 1;
	}
	.catalog-body { flex: 1; min-height: 0; }
	.catalog-scroll { height: 100%; overflow-y: auto; padding: 10px; display: flex; flex-direction: column; gap: 8px; }
	.catalog-item {
		display: grid; grid-template-columns: minmax(112px, 0.16fr) minmax(0, 1fr);
		align-items: start; gap: 12px; padding: 8px;
		border: 1px solid var(--border); border-radius: var(--r);
		background: var(--panel); cursor: pointer; text-align: left;
		transition: border-color 0.12s, background 0.12s; font-family: inherit; width: 100%;
	}
	.catalog-item.active { border-color: var(--accent); background: var(--accent-light); box-shadow: inset 3px 0 0 var(--accent); }
	.catalog-item:hover:not(.active) { background: var(--bg); }
	.catalog-info { min-width: 0; padding: 2px 2px 0; }
	.catalog-name-row { display: flex; align-items: baseline; gap: 5px; }
	.catalog-name { font-size: 12px; font-weight: 600; color: var(--fg); line-height: 1.15; }
	.catalog-id { margin-top: 1px; color: var(--fg3); font: 9px/1.15 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }
	.catalog-sub { margin-top: 5px; font-size: 9px; line-height: 1.25; color: var(--fg3); }
	.catalog-check { color: var(--accent); font-size: 12px; flex-shrink: 0; }
	.catalog-palette {
		display: grid;
		grid-template-columns: repeat(10, minmax(56px, 1fr));
		gap: 5px;
		min-width: 0;
	}
	.catalog-color { min-width: 0; text-align: center; }
	.catalog-color-box { width: 100%; height: 38px; border-radius: 2px; }
	.catalog-color-box.light { border: 1px solid var(--border); }
	.catalog-color-name, .catalog-color-localized {
		display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
	}
	.catalog-color-name { margin-top: 1px; color: var(--fg2); font-size: 8px; line-height: 1.15; }
	.catalog-color-localized { color: var(--fg3); font-size: 7px; line-height: 1.15; }
	.catalog-color-code {
		display: block; margin-top: 2px; font-size: 7px; line-height: 1.1; color: var(--fg3);
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
	@media (max-width: 980px) {
		.catalog-palette { grid-template-columns: repeat(5, minmax(64px, 1fr)); row-gap: 8px; }
	}
	@media (max-width: 640px) {
		.catalog-modal { width: calc(100vw - 16px); max-height: calc(100dvh - 16px); }
		.catalog-modal-head { padding: 12px 14px 9px; }
		.catalog-scroll { padding: 8px; }
		.catalog-item { grid-template-columns: 1fr; gap: 7px; }
		.catalog-info { display: grid; grid-template-columns: minmax(0, 1fr) auto; column-gap: 8px; }
		.catalog-name-row { min-width: 0; }
		.catalog-id { grid-column: 1; }
		.catalog-sub { grid-column: 2; grid-row: 1 / span 2; align-self: center; margin: 0; text-align: right; }
		.catalog-palette { grid-template-columns: repeat(5, minmax(44px, 1fr)); gap: 5px; row-gap: 8px; }
		.catalog-color-box { height: 32px; }
		.catalog-modal-foot { padding: 9px 12px 11px; }
	}
	@media (max-width: 380px) {
		.catalog-palette { grid-template-columns: repeat(3, minmax(56px, 1fr)); }
		.catalog-sub { display: none; }
	}
</style>
