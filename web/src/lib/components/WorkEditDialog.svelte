<script lang="ts">
	import { onDestroy, onMount, tick } from 'svelte';
	import { t } from '$lib/i18n/index.svelte';
	import SketchSelect from './SketchSelect.svelte';
	import RunStatus from './RunStatus.svelte';
	import WildToggle from './WildToggle.svelte';
	import { DEFAULT_SKETCH_GRAIN, normalizeSketchGrain, sketchModeLabel, type SketchGrain, type SketchMode } from '$lib/sketch';
	import type { LineageNode } from '$lib/features/history/types';
	import { restoreWorkActionFocus } from './WorkActionMenu.svelte';

	type Props = {
		node: LineageNode;
		mode: 'description' | 'sketch-grain';
		isJapanese: boolean;
		stageLabel: string;
		stage1ModelLabel: string;
		stage2ModelLabel: string;
		tokensIn: number | null;
		tokensOut: number | null;
		onClose: () => void;
		onDrawDescription: (node: LineageNode, text: string, signal?: AbortSignal, wild?: boolean | null) => void | Promise<void>;
		onDrawSketchGrain: (node: LineageNode, grain: SketchGrain, signal?: AbortSignal) => void | Promise<void>;
	};

	let { node, mode, isJapanese, stageLabel, stage1ModelLabel, stage2ModelLabel, tokensIn, tokensOut, onClose, onDrawDescription, onDrawSketchGrain }: Props = $props();
	let draft = $state('');
	let wildOverride = $state<boolean | null>(null);
	let grain = $state<SketchGrain>(DEFAULT_SKETCH_GRAIN);
	let drawing = $state(false);
	let error = $state<string | null>(null);
	let elapsedMs = $state(0);
	let controller: AbortController | null = null;
	let initializedKey = $state('');
	let dialogEl = $state<HTMLDialogElement | null>(null);
	let fallbackFocus: HTMLElement | null = null;

	onMount(() => {
		fallbackFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
		dialogEl?.showModal();
	});

	onDestroy(() => { controller?.abort(); dialogEl?.close(); });

	$effect(() => {
		const nextKey = `${node.id}:${mode}`;
		if (nextKey === initializedKey) return;
		initializedKey = nextKey;
		draft = mode === 'description' ? (node.history?.source_text ?? node.history?.input ?? '') : '';
		wildOverride = null;
		grain = normalizeSketchGrain(node.history?.sketch_grain) ?? DEFAULT_SKETCH_GRAIN;
		error = null;
	});

	$effect(() => {
		if (!drawing) return;
		elapsedMs = 0;
		const startedAt = Date.now();
		const handle = setInterval(() => { elapsedMs = Date.now() - startedAt; }, 100);
		return () => clearInterval(handle);
	});

	function close(): void {
		if (drawing) return;
		onClose();
		void tick().then(() => {
			if (!restoreWorkActionFocus()) fallbackFocus?.focus();
		});
	}

	async function draw(): Promise<void> {
		if (drawing || (mode === 'description' && !draft.trim())) return;
		drawing = true;
		error = null;
		controller = new AbortController();
		let saved = false;
		try {
			if (mode === 'description') await onDrawDescription(node, draft, controller.signal, wildOverride);
			else await onDrawSketchGrain(node, grain, controller.signal);
			saved = true;
		} catch (cause) {
			if (!(cause instanceof Error && cause.name === 'AbortError')) error = cause instanceof Error ? cause.message : String(cause);
		} finally {
			controller = null;
			drawing = false;
			if (saved) close();
		}
	}
</script>

<dialog bind:this={dialogEl} class="work-edit-dialog" aria-labelledby="work-edit-title"
	oncancel={(event) => { event.preventDefault(); close(); }}
	onkeydown={(event) => event.stopPropagation()}>
	<header>
		<div>
			<h2 id="work-edit-title">{mode === 'description' ? t().workEditDescriptionTitle : t().workEditSketchTitle}</h2>
			<p>{mode === 'description' ? t().workEditDescriptionHelp : t().workEditSketchHelp}</p>
		</div>
		<button type="button" disabled={drawing} aria-label={t().closeLabel} onclick={close}>×</button>
	</header>
	<div class="work-edit-body">
		{#if mode === 'description'}
			<label for="work-edit-text">{t().workActionDescription}</label>
			<textarea id="work-edit-text" rows="9" bind:value={draft} spellcheck disabled={drawing}></textarea>
		{:else}
			<SketchSelect compact value={grain as SketchMode} {isJapanese} disabled={drawing} onSelect={(next: SketchMode) => { if (next !== 'off') grain = next; }} />
			{#if node.history?.sketch_text}<p class="sketch-parent-prose">{node.history.sketch_text}</p>
			{:else}<p class="sketch-parent-prose empty">{t().workEditNoSketch}</p>{/if}
		{/if}
		{#if error}<div class="work-edit-error">{error}</div>{/if}
	</div>
	<footer>
		{#if drawing}
			<RunStatus variant="inline" label={stageLabel || t().pipelineWorking} stage1Model={stage1ModelLabel} stage2Model={stage2ModelLabel} {elapsedMs} tokensIn={tokensIn} tokensOut={tokensOut} onStop={() => controller?.abort()} />
		{:else}
			{#if mode === 'description'}
				<WildToggle value={wildOverride ?? (node.history?.render_wild === true)} {isJapanese} inherited={wildOverride === null} onSelect={(next) => (wildOverride = next)} />
			{:else}
				<span class="sketch-current">{t().workEditParentGrain}: {sketchModeLabel((normalizeSketchGrain(node.history?.sketch_grain) ?? 'off') as SketchMode, isJapanese)}</span>
			{/if}
			<button type="button" onclick={close}>{t().pipelineCancel}</button>
			<button type="button" class="work-edit-draw" disabled={mode === 'description' && !draft.trim()} onclick={draw}>{t().pipelinePerform}</button>
		{/if}
	</footer>
</dialog>

<style>
	.work-edit-dialog::backdrop { background: #0009; }
	.work-edit-dialog { margin: 0; padding: 0; color: var(--fg); }
	.work-edit-dialog { position: fixed; z-index: 1461; top: 50%; left: 50%; transform: translate(-50%, -50%); box-sizing: border-box; width: min(780px, 96vw); max-height: 92vh; overflow: hidden; display: flex; flex-direction: column; border: 1px solid var(--border2); border-radius: 12px; background: var(--panel); box-shadow: 0 24px 80px #000a; }
	.work-edit-dialog > header { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; padding: 18px 20px 14px; margin: 0; border-bottom: 1px solid var(--border); }
	.work-edit-dialog > header h2 { margin: 0 0 4px; font-size: 1.05rem; }
	.work-edit-dialog > header p { margin: 0; color: var(--fg2); font-size: 12px; }
	.work-edit-dialog > header button { border: 0; background: transparent; color: var(--fg2); font-size: 1.35rem; cursor: pointer; }
	.work-edit-body { min-height: 0; overflow-y: auto; display: grid; gap: 8px; padding: 18px 20px; }
	.work-edit-body label { color: var(--fg2); font-size: 12px; font-weight: 700; }
	.work-edit-body textarea { box-sizing: border-box; width: 100%; min-height: 180px; resize: vertical; border: 1px solid var(--border2); border-radius: 8px; padding: 12px 14px; background: var(--bg); color: var(--fg); font: inherit; line-height: 1.65; }
	.work-edit-dialog > footer { display: flex; justify-content: flex-end; gap: 8px; padding: 12px 20px 16px; border-top: 1px solid var(--border); }
	.work-edit-dialog > footer :global(.wild-inline), .sketch-current { margin-right: auto; }
	.work-edit-dialog > footer button { border: 1px solid var(--border2); border-radius: 7px; padding: 9px 15px; background: var(--panel); color: var(--fg); cursor: pointer; }
	.work-edit-dialog > footer .work-edit-draw { border-color: var(--action-bg); background: var(--action-bg); color: var(--action-fg); font-weight: 700; }
	.work-edit-dialog > footer .work-edit-draw:hover:not(:disabled) { border-color: var(--action-hover); background: var(--action-hover); }
	.work-edit-dialog button:disabled, .work-edit-dialog textarea:disabled { opacity: .55; cursor: default; }
	.sketch-parent-prose { margin: 0; font-size: 12px; line-height: 1.7; color: var(--fg2); white-space: pre-wrap; }
	.sketch-parent-prose.empty, .sketch-current { color: var(--fg2); }
	.sketch-current { font-size: 12px; }
	.work-edit-error { color: var(--danger, #9b3d32); white-space: pre-line; }
</style>
