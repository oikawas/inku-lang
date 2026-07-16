<script lang="ts">
	import type { LineageNode } from './LineagePanel.svelte';
	import HistoryThumbnail from './HistoryThumbnail.svelte';

	type Props = {
		node: LineageNode;
		isJapanese: boolean;
		onClose: () => void;
		onPaintOne: (text: string, options: any) => Promise<any>;
		onLoadBranch: (nodeId: string) => void | Promise<void>;
	};

	let { node, isJapanese, onClose, onPaintOne, onLoadBranch }: Props = $props();

	let prompt = $state('');
	let generations = $state(5);
	let enableReading = $state(true);
	let enableColor = $state(true);
	let enableLayout = $state(true);
	let enableTouch = $state(true);

	let running = $state(false);
	let currentStep = $state(0);
	let statusText = $state('');
	let errorText = $state('');
	let lastGeneratedItem = $state<any>(null);

	const activeKinds = $derived.by(() => {
		const kinds: string[] = [];
		if (enableReading) kinds.push('reinterpretation');
		if (enableColor) kinds.push('catalog_change');
		if (enableLayout) kinds.push('layout_variation');
		if (enableTouch) kinds.push('touch_variation');
		return kinds;
	});

	function kindLabel(kind: string): string {
		const ja: Record<string, string> = { touch_variation: 'タッチ', layout_variation: '構図', catalog_change: '配色', reinterpretation: '再解釈' };
		const en: Record<string, string> = { touch_variation: 'Touch', layout_variation: 'Layout', catalog_change: 'Color', reinterpretation: 'Reading' };
		return (isJapanese ? ja : en)[kind] ?? kind;
	}

	async function startRefinement() {
		if (activeKinds.length === 0) {
			errorText = isJapanese ? '少なくとも1つの要素を有効にしてください。' : 'Please enable at least one element.';
			return;
		}

		running = true;
		errorText = '';
		currentStep = 0;
		lastGeneratedItem = null;

		let parentNodeId = node.id;
		let currentText = node.history?.source_text ?? node.history?.input ?? '';

		try {
			for (let i = 0; i < generations; i++) {
				currentStep = i + 1;

				// どの Vary Kind を使うか決定
				// プロンプト指示がある場合、1ステップ目は再解釈 (reinterpretation) を優先する
				let kind = activeKinds[Math.floor(Math.random() * activeKinds.length)];
				if (prompt && enableReading && i === 0) {
					kind = 'reinterpretation';
				}

				statusText = isJapanese
					? `${generations}世代中 ${currentStep}世代目を生成中 (${kindLabel(kind)})...`
					: `Generating Gen ${currentStep}/${generations} (${kindLabel(kind)})...`;

				let paintText = currentText;
				// 解釈変動の場合にのみ、プロンプト指示を反映させて DDL を再解釈させる
				if (prompt && kind === 'reinterpretation') {
					paintText = `${currentText}、${prompt}`;
				}

				const options: any = {
					lineageParentNodeId: parentNodeId,
					derivationKind: kind,
					// 最後の世代だけを通常履歴（normal）にし、途中世代は中間系譜（lineage_only）として作成
					historyVisibility: i === generations - 1 ? 'normal' : 'lineage_only',
					saveHistory: true,
					countGeneration: true
				};

				if (kind === 'catalog_change') {
					options.randomColorCatalog = true;
				}

				const result = await onPaintOne(paintText, options);
				parentNodeId = result.lineage_node_id;
				lastGeneratedItem = result.history_id ? result : null;

				if (result.source_text) {
					currentText = result.source_text;
				}
			}

			statusText = isJapanese ? '自律推敲が完了しました！' : 'Autonomous refinement completed successfully!';
			await onLoadBranch(node.id);
		} catch (err: any) {
			errorText = err.message || String(err);
		} finally {
			running = false;
		}
	}
</script>

<div class="modal-backdrop" onclick={!running ? onClose : undefined} role="presentation">
	<div class="modal-content" onclick={(e) => e.stopPropagation()} role="dialog" aria-modal="true" aria-labelledby="modal-title">
		<header>
			<h3 id="modal-title">{isJapanese ? 'AIに自律推敲させる' : 'Autonomous AI Refinement'}</h3>
			{#if !running}
				<button class="close-btn" type="button" onclick={onClose} aria-label={isJapanese ? '閉じる' : 'Close'}>&times;</button>
			{/if}
		</header>

		<div class="modal-body">
			{#if running}
				<div class="running-state">
					<div class="spinner"></div>
					<p class="status-message">{statusText}</p>
					{#if lastGeneratedItem}
						<div class="progress-preview">
							<HistoryThumbnail item={lastGeneratedItem} scope="ai-refine-progress" size="manager" />
						</div>
					{/if}
				</div>
			{:else}
				<div class="form-group">
					<label for="ai-direction">{isJapanese ? 'AIに指示する方向性（プロンプト）' : 'AI Direction (Prompt)'}</label>
					<textarea
						id="ai-direction"
						placeholder={isJapanese ? '例：華やかで、かつ、涼しげに' : 'e.g., vibrant and cool'}
						bind:value={prompt}
						maxlength="160"
						rows="2"
					></textarea>
				</div>

				<div class="form-row">
					<div class="form-group select-generations">
						<label for="ai-gens">{isJapanese ? '試行の世代数' : 'Generations to evolve'}</label>
						<input id="ai-gens" type="number" min="1" max="10" bind:value={generations} />
					</div>
				</div>

				<details class="advanced-settings" open>
					<summary>{isJapanese ? '使用する推敲要素（詳細設定）' : 'Evolutionary Elements (Advanced)'}</summary>
					<div class="checkbox-group">
						<label>
							<input type="checkbox" bind:checked={enableReading} />
							<span>{isJapanese ? '解釈・概念 (Reading)' : 'Concept (Reading)'}</span>
						</label>
						<label>
							<input type="checkbox" bind:checked={enableColor} />
							<span>{isJapanese ? '配色・カタログ (Color)' : 'Colors (Catalog)'}</span>
						</label>
						<label>
							<input type="checkbox" bind:checked={enableLayout} />
							<span>{isJapanese ? '構図・配置 (Layout)' : 'Composition (Layout)'}</span>
						</label>
						<label>
							<input type="checkbox" bind:checked={enableTouch} />
							<span>{isJapanese ? 'タッチ・質感 (Touch)' : 'Texture (Touch)'}</span>
						</label>
					</div>
				</details>
			{/if}

			{#if errorText}
				<div class="error-banner">{errorText}</div>
			{/if}
		</div>

		<footer>
			{#if !running}
				<button class="cancel-action" type="button" onclick={onClose}>{isJapanese ? 'キャンセル' : 'Cancel'}</button>
				<button class="confirm-action" type="button" disabled={activeKinds.length === 0} onclick={startRefinement}>
					{isJapanese ? '推敲を開始' : 'Start Evolving'}
				</button>
			{:else}
				<button class="confirm-action active-loading" type="button" disabled>{isJapanese ? '推敲中...' : 'Evolving...'}</button>
			{/if}
		</footer>
	</div>
</div>

<style>
	.modal-backdrop { position: fixed; inset: 0; z-index: 1500; display: grid; place-items: center; padding: 20px; background: rgba(0, 0, 0, 0.6); backdrop-filter: blur(2px); }
	.modal-content { box-sizing: border-box; width: 100%; max-width: 480px; display: flex; flex-direction: column; background: var(--panel); border: 1px solid var(--border2); border-radius: 12px; color: var(--fg); box-shadow: 0 20px 60px rgba(0, 0, 0, 0.45); overflow: hidden; }
	header { display: flex; align-items: center; justify-content: space-between; padding: 14px 18px; border-bottom: 1px solid var(--border); }
	header h3 { margin: 0; font-size: 1rem; font-weight: 600; }
	.close-btn { border: 0; background: transparent; color: var(--fg3); font-size: 1.4rem; cursor: pointer; padding: 0 4px; }
	.modal-body { padding: 18px; min-height: 200px; display: flex; flex-direction: column; gap: 14px; overflow-y: auto; max-height: 60vh; }
	.form-group { display: flex; flex-direction: column; gap: 6px; }
	.form-group label { font-size: 0.76rem; color: var(--fg3); font-weight: 500; }
	textarea { box-sizing: border-box; width: 100%; border: 1px solid var(--border2); border-radius: 6px; padding: 8px 10px; background: var(--bg); color: var(--fg); font: inherit; font-size: 0.82rem; resize: none; line-height: 1.4; }
	.form-row { display: flex; gap: 12px; }
	.select-generations { width: 120px; }
	input[type="number"] { box-sizing: border-box; width: 100%; border: 1px solid var(--border2); border-radius: 6px; padding: 6px 10px; background: var(--bg); color: var(--fg); font: inherit; font-size: 0.85rem; }
	.advanced-settings { border: 1px solid var(--border); border-radius: 8px; padding: 8px 12px; background: var(--bg2); }
	.advanced-settings summary { font-size: 0.75rem; font-weight: 600; color: var(--fg2); cursor: pointer; user-select: none; }
	.checkbox-group { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-top: 8px; }
	.checkbox-group label { display: flex; align-items: center; gap: 8px; font-size: 0.74rem; cursor: pointer; }
	.checkbox-group input[type="checkbox"] { width: 14px; height: 14px; accent-color: var(--accent); margin: 0; }
	.running-state { margin: auto; display: flex; flex-direction: column; align-items: center; text-align: center; gap: 14px; padding: 10px 0; }
	.spinner { width: 28px; height: 28px; border: 3px solid var(--border2); border-top-color: var(--accent); border-radius: 50%; animation: spin 0.8s linear infinite; }
	@keyframes spin { to { transform: rotate(360deg); } }
	.status-message { font-size: 0.82rem; color: var(--fg2); margin: 0; }
	.progress-preview { width: 110px; height: 110px; border-radius: 6px; overflow: hidden; background: var(--bg2); border: 1px solid var(--border); box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15); }
	.progress-preview :global(.history-thumbnail) { width: 100%; height: 100%; aspect-ratio: auto; }
	.progress-preview :global(svg) { width: 100%; height: 100%; display: block; }
	.error-banner { padding: 8px 12px; background: color-mix(in srgb, var(--danger, #9b3d32) 10%, var(--panel)); border: 1px solid var(--danger, #9b3d32); border-radius: 6px; color: var(--danger, #9b3d32); font-size: 0.74rem; line-height: 1.35; }
	footer { display: flex; align-items: center; justify-content: flex-end; gap: 8px; padding: 12px 18px; border-top: 1px solid var(--border); background: var(--bg2); }
	footer button { border: 1px solid var(--border2); border-radius: 6px; padding: 7px 14px; font-size: 0.8rem; font-weight: 500; cursor: pointer; background: var(--panel); color: var(--fg); }
	.confirm-action { background: var(--accent); color: white; border-color: var(--accent); }
	.confirm-action:disabled { opacity: 0.5; cursor: default; }
	.confirm-action.active-loading { opacity: 0.8; cursor: default; }
	.cancel-action:hover { background: var(--bg); }
</style>
