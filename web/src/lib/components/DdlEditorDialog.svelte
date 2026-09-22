<script lang="ts">
	import { onDestroy, tick } from 'svelte';
	import { t } from '$lib/i18n/index.svelte';
	import DdlEditor from './DdlEditor.svelte';
	import RunStatus from './RunStatus.svelte';
	import WildToggle from './WildToggle.svelte';
	import ModelCardPicker from './ModelCardPicker.svelte';
	import { restoreWorkActionFocus } from './WorkActionMenu.svelte';
	import type { Provider, ProviderGroup } from '$lib/models';
	import type { PluginEntry, PreviewForPlugin, PreviewForWord } from '$lib/features/ddl-editor/types';

	type Props = {
		open: boolean;
		mode: 'new' | 'edit';
		isJapanese: boolean;
		initialDdl: string;
		returnFocusTo?: HTMLElement | null;
		drawing: boolean;
		stage2ModelLabel: string;
		drawingModelId: string;
		drawingModelGroups: ProviderGroup[];
		onSelectDrawingModel: (provider: Provider, model: string) => void | Promise<void>;
		runTokensIn: number | null;
		runTokensOut: number | null;
		error: string | null;
		previewForWord: PreviewForWord;
		previewForPlugin: PreviewForPlugin;
		pluginEntries?: PluginEntry[];
		wildValue?: boolean;
		wildInherited?: boolean;
		onSelectWild?: (value: boolean) => void;
		onDraw: (ddl: string, signal?: AbortSignal) => void | Promise<void>;
		onClose: () => void;
	};

	let {
		open, mode, isJapanese, initialDdl, returnFocusTo = null, drawing,
		stage2ModelLabel, drawingModelId, drawingModelGroups, onSelectDrawingModel,
		runTokensIn, runTokensOut, error, previewForWord, previewForPlugin,
		pluginEntries = [], wildValue = false, wildInherited = true, onSelectWild, onDraw, onClose,
	}: Props = $props();

	let value = $state('');
	let editor = $state<DdlEditor>();
	let dialogEl = $state<HTMLDivElement>();
	let lastOpen = false;
	let fallbackFocus: HTMLElement | null = null;
	let elapsedMs = $state(0);
	let drawController: AbortController | null = null;
	const title = $derived(mode === 'new' ? t().ddlNewDialogTitle : t().ddlEditButton);
	const subtitle = $derived(mode === 'new' ? t().ddlNewDialogSubtitle : t().ddlEditDialogSubtitle);

	onDestroy(() => drawController?.abort());
	onDestroy(restoreFocus);

	function restoreFocus(): void {
		const target = returnFocusTo ?? fallbackFocus;
		void tick().then(() => {
			if (target?.isConnected && target.getClientRects().length > 0 && !target.closest('[inert]')) target.focus();
			else restoreWorkActionFocus();
		});
	}

	$effect(() => {
		if (open && !lastOpen) {
			fallbackFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
			value = initialDdl;
			void tick().then(() => editor?.focus());
		} else if (!open && lastOpen) {
			restoreFocus();
		}
		lastOpen = open;
	});

	$effect(() => {
		if (!drawing) return;
		elapsedMs = 0;
		const startedAt = Date.now();
		const handle = setInterval(() => { elapsedMs = Date.now() - startedAt; }, 100);
		return () => clearInterval(handle);
	});

	function requestClose(): void {
		if (!drawing) onClose();
	}

	async function requestDraw(): Promise<void> {
		if (drawing || drawController || !value.trim()) return;
		drawController = new AbortController();
		try {
			await onDraw(value, drawController.signal);
		} finally {
			drawController = null;
		}
	}

	function stopDraw(): void {
		drawController?.abort();
	}

	function handleKeydown(event: KeyboardEvent): void {
		// Nested model selection owns its keyboard events and focus boundary.
		if (!dialogEl || (event.target as Element).closest('[role="dialog"]') !== dialogEl) return;
		event.stopPropagation();
		if (event.isComposing) return;
		if (event.key === 'Escape') {
			event.preventDefault();
			requestClose();
		} else if (event.key === 'Tab') {
			const controls = [...dialogEl.querySelectorAll<HTMLElement>('button:not(:disabled), textarea:not(:disabled), input:not(:disabled), select:not(:disabled), summary, [tabindex="0"]')]
				.filter((el) => el.getClientRects().length > 0 && !el.closest('[inert]') && el.closest('[role="dialog"]') === dialogEl);
			const first = controls[0];
			const last = controls.at(-1);
			if (!first || !last) {
				event.preventDefault();
				dialogEl.focus();
			} else if (event.shiftKey && (document.activeElement === first || document.activeElement === dialogEl)) {
				event.preventDefault();
				last.focus();
			} else if (!event.shiftKey && (document.activeElement === last || document.activeElement === dialogEl)) {
				event.preventDefault();
				first.focus();
			}
		}
	}
</script>

{#if open}
	<div class="ddled-backdrop" role="presentation" onclick={requestClose}></div>
	<div class="ddled-dialog" role="dialog" aria-modal="true" aria-labelledby="ddled-title" aria-describedby="ddled-subtitle" tabindex="-1" bind:this={dialogEl} onkeydown={handleKeydown}>
		<header class="ddled-head">
			<div>
				<h2 id="ddled-title">{title}</h2>
				<p id="ddled-subtitle">{subtitle}</p>
			</div>
			<button class="ddled-close" type="button" disabled={drawing} onclick={requestClose} aria-label={t().closeLabel}>×</button>
		</header>
		<div class="ddled-body">
			<DdlEditor bind:this={editor} bind:value {isJapanese} disabled={drawing} {pluginEntries} {previewForWord} {previewForPlugin} />
		</div>
		<div class="ddled-bottom">
			<div class="ddled-conditions">
				<div class="ddled-model">
					<ModelCardPicker label={t().ddlDialogDrawingModel} selectedModel={drawingModelId} providerGroups={drawingModelGroups} disabled={drawing} onSelect={onSelectDrawingModel} />
				</div>
				{#if mode === 'edit' && onSelectWild}
					<div class="ddled-settings" inert={drawing}>
						<WildToggle value={wildValue} {isJapanese} inherited={wildInherited} onSelect={onSelectWild} />
					</div>
				{/if}
			</div>
			<footer class="ddled-foot">
				{#if error}<div class="ddled-error" role="alert">{error}</div>{/if}
				{#if drawing}
					<RunStatus variant="inline" label={t().stageImageGenerating} stage2Model={stage2ModelLabel} {elapsedMs} tokensIn={runTokensIn} tokensOut={runTokensOut} onStop={stopDraw} />
				{:else}
					<div class="ddled-actions">
						<button type="button" class="ddled-cancel" onclick={requestClose}>{t().pipelineCancel}</button>
						<button type="button" class="ddled-draw" disabled={!value.trim()} onclick={requestDraw}>{t().submitBtn}</button>
					</div>
				{/if}
			</footer>
		</div>
	</div>
{/if}

<style>
	.ddled-backdrop { position: fixed; inset: 0; z-index: 1450; background: rgba(0, 0, 0, .28); backdrop-filter: blur(2px); }
	.ddled-dialog {
		position: fixed; inset: 0; margin: auto; z-index: 1451;
		box-sizing: border-box; width: min(1360px, calc(100vw - 40px)); height: min(940px, calc(100dvh - 40px));
		display: flex; flex-direction: column; border: 1px solid var(--border2); border-radius: 12px;
		background: var(--panel2); box-shadow: 0 18px 56px rgba(0, 0, 0, .22); overflow: hidden;
	}
	.ddled-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; padding: 14px 18px; border-bottom: 1px solid var(--border); flex-shrink: 0; }
	.ddled-head h2 { margin: 0; color: var(--fg); font-size: 16px; font-weight: 500; }
	.ddled-head p { margin: 4px 0 0; color: var(--fg3); font-size: 12px; line-height: 1.5; }
	.ddled-close { flex-shrink: 0; width: 30px; height: 30px; padding: 0; border: 1px solid var(--border2); border-radius: var(--r); background: var(--panel); color: var(--fg2); font-size: 20px; cursor: pointer; }
	.ddled-close:hover:not(:disabled) { background: var(--bg2); }
	.ddled-body { display: flex; min-height: 0; flex: 1; padding: 14px 18px; }
	.ddled-bottom { display: flex; align-items: flex-end; gap: 16px; padding: 10px 18px 14px; border-top: 1px solid var(--border); flex-shrink: 0; }
	.ddled-conditions { display: flex; align-items: center; gap: 18px; min-width: 0; flex: 1; }
	.ddled-model { flex: 1; min-width: 0; max-width: 520px; }
	.ddled-settings { min-width: 0; }
	.ddled-settings[inert] { opacity: .5; }
	.ddled-foot { display: flex; flex-direction: column; gap: 8px; min-width: 0; max-width: 44%; }
	.ddled-error { max-height: 80px; overflow: auto; color: var(--danger); font-size: 12px; overflow-wrap: anywhere; }
	.ddled-actions { display: flex; justify-content: flex-end; gap: 8px; }
	.ddled-actions button { border: 1px solid var(--border2); border-radius: var(--btn-sm-radius); padding: 8px 18px; background: var(--panel); color: var(--fg2); font: inherit; font-size: var(--btn-sm-font-size); cursor: pointer; }
	.ddled-actions .ddled-draw { border-color: var(--action-bg); background: var(--action-bg); color: var(--action-fg); min-width: 96px; }
	.ddled-actions .ddled-draw:hover:not(:disabled) { background: var(--action-hover); }
	button:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
	button:disabled { opacity: .5; cursor: not-allowed; }
	@media (max-width: 760px) {
		.ddled-dialog { width: calc(100vw - 16px); height: calc(100dvh - 16px); }
		.ddled-head { padding: 12px; gap: 8px; }
		.ddled-body { padding: 10px 12px; }
		.ddled-bottom { flex-direction: column; align-items: stretch; gap: 10px; padding: 8px 12px 12px; }
		.ddled-conditions { gap: 8px; flex-wrap: wrap; max-height: 26dvh; overflow: auto; }
		.ddled-model { flex-basis: 100%; max-width: none; }
		.ddled-foot { max-width: none; }
	}
</style>
