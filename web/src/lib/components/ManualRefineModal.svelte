<script lang="ts">
	import { onMount } from 'svelte';
	import type { LineageNode } from './LineagePanel.svelte';
	import { t } from '$lib/i18n/index.svelte';

	type Props = {
		node: LineageNode;
		onClose: () => void;
		onPaintOne: (text: string, options: any) => Promise<any>;
		onLoadBranch: (nodeId: string) => void | Promise<void>;
		selectedCatalogId: string;
	};

	let { node, onClose, onPaintOne, onLoadBranch, selectedCatalogId }: Props = $props();

	type ColorCatalog = { id: string; name: string; name_ja: string; sub?: string; sub_ja?: string };
	let colorCatalogs = $state<ColorCatalog[]>([]);
	let selectedCatalog = $state('');

	let derivationKind = $state<string>('touch_change');
	let ddlText = $state('');
	let saijikiText = $state('');

	let running = $state(false);
	let errorText = $state('');

	const kinds = $derived([
		{ id: 'touch_change', label: t().refineCostTouch },
		{ id: 'layout_change', label: t().refineCostLayout },
		{ id: 'catalog_change', label: t().refineCostColor },
		{ id: 'reinterpretation', label: t().refineCostReading }
	]);

	onMount(async () => {
		ddlText = node.history?.ddl ?? '';
		selectedCatalog = selectedCatalogId;
		
		try {
			const res = await fetch('/api/color-catalogs');
			if (res.ok) {
				const data = await res.json() as { catalogs: ColorCatalog[] };
				colorCatalogs = data.catalogs || [];
			}
		} catch (e) {
			console.error('Failed to fetch color catalogs:', e);
		}
	});

	async function executeRefinement() {
		running = true;
		errorText = '';

		let paintText = node.history?.source_text ?? node.history?.input ?? '';
		if (derivationKind === 'reinterpretation' && saijikiText.trim()) {
			paintText = `${paintText}、${saijikiText.trim()}`;
		}

		const options: any = {
			lineageParentNodeId: node.id,
			derivationKind: derivationKind,
			historyVisibility: 'normal',
			saveHistory: true,
			countGeneration: true,
			catalogId: selectedCatalog
		};

		try {
			await onPaintOne(paintText, options);
			await onLoadBranch(node.id);
			onClose();
		} catch (err: any) {
			errorText = err.message || String(err);
		} finally {
			running = false;
		}
	}
</script>

<div class="modal-backdrop" onclick={!running ? onClose : undefined} onkeydown={(e) => { if (e.key === 'Escape' && !running) onClose(); }} role="presentation">
	<div class="modal-content" onclick={(e) => e.stopPropagation()} role="dialog" aria-modal="true" aria-labelledby="modal-title" tabindex="-1">
		<header>
			<h3 id="modal-title">{t().manualRefineTitle}</h3>
			{#if !running}
				<button class="close-btn" type="button" onclick={onClose} aria-label={t().closeLabel}>&times;</button>
			{/if}
		</header>

		<div class="modal-body">
			<div class="form-group">
				<label for="refine-kind">{t().manualRefineKindLabel}</label>
				<select id="refine-kind" bind:value={derivationKind} disabled={running}>
					{#each kinds as kind}
						<option value={kind.id}>{kind.label}</option>
					{/each}
				</select>
			</div>

			{#if derivationKind === 'reinterpretation'}
				<div class="form-group">
					<label for="saijiki-input">{t().manualRefineSaijikiLabel}</label>
					<input
						id="saijiki-input"
						type="text"
						placeholder={t().manualRefineSaijikiPlaceholder}
						bind:value={saijikiText}
						disabled={running}
					/>
				</div>
			{/if}

			<div class="form-group">
				<label for="catalog-select">{t().manualRefineColorLabel}</label>
				<select id="catalog-select" bind:value={selectedCatalog} disabled={running}>
					{#each colorCatalogs as cat}
						<option value={cat.id}>
							{t().closeLabel === 'Close' ? cat.name : cat.name_ja}
							{cat.sub ? ` (${t().closeLabel === 'Close' ? cat.sub : (cat.sub_ja || cat.sub)})` : ''}
						</option>
					{/each}
				</select>
			</div>

			<div class="parent-info">
				<h4>{t().manualRefineParentDdl}</h4>
				<pre>{ddlText || t().manualRefineNoDdl}</pre>
			</div>

			{#if errorText}
				<div class="error-banner">{errorText}</div>
			{/if}
		</div>

		<footer>
			{#if !running}
				<button class="cancel-action" type="button" onclick={onClose}>{t().confirmCancel}</button>
				<button class="confirm-action" type="button" onclick={executeRefinement}>
					{t().manualRefineGenerateButton}
				</button>
			{:else}
				<button class="confirm-action active-loading" type="button" disabled>{t().manualRefineGeneratingButton}</button>
			{/if}
		</footer>
	</div>
</div>

<style>
	.modal-backdrop { position: fixed; inset: 0; z-index: 1500; display: grid; place-items: center; padding: 20px; background: rgba(0, 0, 0, 0.6); backdrop-filter: blur(2px); }
	.modal-content { box-sizing: border-box; width: 100%; max-width: 440px; display: flex; flex-direction: column; background: var(--panel); border: 1px solid var(--border2); border-radius: 12px; color: var(--fg); box-shadow: 0 20px 60px rgba(0, 0, 0, 0.45); overflow: hidden; }
	header { display: flex; align-items: center; justify-content: space-between; padding: 14px 18px; border-bottom: 1px solid var(--border); }
	header h3 { margin: 0; font-size: 1rem; font-weight: 600; }
	.close-btn { border: 0; background: transparent; color: var(--fg3); font-size: 1.4rem; cursor: pointer; padding: 0 4px; }
	.modal-body { padding: 18px; min-height: 180px; display: flex; flex-direction: column; gap: 14px; overflow-y: auto; max-height: 60vh; }
	.form-group { display: flex; flex-direction: column; gap: 6px; }
	.form-group label { font-size: 0.76rem; color: var(--fg3); font-weight: 500; }
	select, input[type="text"] { box-sizing: border-box; width: 100%; border: 1px solid var(--border2); border-radius: 6px; padding: 7px 10px; background: var(--bg); color: var(--fg); font: inherit; font-size: 0.82rem; }
	.parent-info { border: 1px solid var(--border); border-radius: 8px; padding: 10px 12px; background: var(--bg2); }
	.parent-info h4 { margin: 0 0 6px; font-size: 0.72rem; color: var(--fg3); font-weight: 600; }
	.parent-info pre { margin: 0; font-family: monospace; font-size: 0.72rem; white-space: pre-wrap; word-break: break-all; color: var(--fg2); max-height: 5.5em; overflow-y: auto; line-height: 1.4; }
	.error-banner { padding: 8px 12px; background: color-mix(in srgb, var(--danger, #9b3d32) 10%, var(--panel)); border: 1px solid var(--danger, #9b3d32); border-radius: 6px; color: var(--danger, #9b3d32); font-size: 0.74rem; line-height: 1.35; white-space: pre-line; }
	footer { display: flex; align-items: center; justify-content: flex-end; gap: 8px; padding: 12px 18px; border-top: 1px solid var(--border); background: var(--bg2); }
	footer button { border: 1px solid var(--border2); border-radius: 6px; padding: 7px 14px; font-size: 0.8rem; font-weight: 500; cursor: pointer; background: var(--panel); color: var(--fg); }
	.confirm-action { background: var(--action-bg); color: var(--action-fg); border-color: var(--action-bg); }
	.confirm-action:hover:not(:disabled) { background: var(--action-hover); border-color: var(--action-hover); }
	.confirm-action:disabled { opacity: 0.5; cursor: default; }
	.confirm-action.active-loading { opacity: 0.8; cursor: default; }
	.cancel-action:hover { background: var(--bg); }
</style>
