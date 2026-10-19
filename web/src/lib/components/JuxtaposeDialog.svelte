<script lang="ts">
	import { onDestroy, onMount, tick } from 'svelte';
	import { t } from '$lib/i18n/index.svelte';
	import { qualifiedModelId, type Provider, type ProviderGroup } from '$lib/models';
	import ModelCardPicker from './ModelCardPicker.svelte';
	import RunStatus from './RunStatus.svelte';
	import type { LineageNode } from '$lib/features/history/types';
	import type { ProviderAttemptCount } from '$lib/paintStream';
	import { joinJuxtaposition, juxtapositionMetadata, type JuxtapositionResult } from '$lib/features/juxtaposition/juxtaposition';
	import { restoreWorkActionFocus } from './WorkActionMenu.svelte';

	type Props = {
		node: LineageNode;
		visionModel: string;
		visionProviderGroups: ProviderGroup[];
		stageLabel: string;
		stage1ModelLabel: string;
		stage2ModelLabel: string;
		tokensIn: number | null;
		tokensOut: number | null;
		attempt?: ProviderAttemptCount | null;
		onClose: () => void;
		onSaveVisionModel: (provider: Provider, model: string) => void | Promise<void>;
		/** Four sentences from the author's other works; `exclude` holds those shown before. */
		onJuxtapose: (historyId: string, model: string, exclude: string[], signal: AbortSignal) => Promise<JuxtapositionResult>;
		onDrawDescription: (node: LineageNode, text: string, signal?: AbortSignal, wild?: boolean | null, metadata?: Record<string, unknown>) => void | Promise<void>;
	};

	let { node, visionModel, visionProviderGroups, stageLabel, stage1ModelLabel, stage2ModelLabel, tokensIn, tokensOut, attempt = null, onClose, onSaveVisionModel, onJuxtapose, onDrawDescription }: Props = $props();
	let selectedModel = $state('');
	$effect(() => { if (!selectedModel) selectedModel = visionModel; });
	let result = $state<JuxtapositionResult | null>(null);
	let shown = $state<string[]>([]);
	let chosen = $state<number | null>(null);
	let asking = $state(false);
	let drawing = $state(false);
	let error = $state<string | null>(null);
	let elapsedMs = $state(0);
	let controller: AbortController | null = null;
	let dialogEl = $state<HTMLDialogElement | null>(null);
	let fallbackFocus: HTMLElement | null = null;
	const description = $derived(node.history?.source_text ?? node.history?.input ?? '');
	const choice = $derived(result && chosen !== null ? result.choices[chosen] ?? null : null);
	const joined = $derived(choice ? joinJuxtaposition(description, choice.sentence) : '');
	const busy = $derived(asking || drawing);

	onMount(() => {
		fallbackFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
		dialogEl?.showModal();
	});

	onDestroy(() => { controller?.abort(); dialogEl?.close(); });

	$effect(() => {
		if (!busy) return;
		elapsedMs = 0;
		const startedAt = Date.now();
		const handle = setInterval(() => { elapsedMs = Date.now() - startedAt; }, 100);
		return () => clearInterval(handle);
	});

	function close(): void {
		if (busy) return;
		onClose();
		void tick().then(() => {
			if (!restoreWorkActionFocus()) fallbackFocus?.focus();
		});
	}

	function failure(cause: unknown): string | null {
		if (cause instanceof Error && cause.name === 'AbortError') return null;
		return cause instanceof Error ? cause.message : String(cause);
	}

	async function ask(): Promise<void> {
		if (busy || !node.history?.id || !selectedModel) return;
		asking = true;
		error = null;
		controller = new AbortController();
		try {
			const next = await onJuxtapose(node.history.id, selectedModel, shown, controller.signal);
			result = next;
			chosen = null;
			// "Pick again" leaves out every sentence already shown in this dialog.
			shown = [...shown, ...next.choices.map((item) => item.sentence)];
		} catch (cause) {
			error = failure(cause);
		} finally {
			controller = null;
			asking = false;
		}
	}

	async function draw(): Promise<void> {
		if (busy || !choice || !result) return;
		drawing = true;
		error = null;
		controller = new AbortController();
		let saved = false;
		try {
			// null wild = inherit the parent work's setting, as the description edit does.
			await onDrawDescription(node, joined, controller.signal, null, juxtapositionMetadata(choice, result));
			saved = true;
		} catch (cause) {
			error = failure(cause);
		} finally {
			controller = null;
			drawing = false;
			if (saved) close();
		}
	}
</script>

<dialog bind:this={dialogEl} class="juxtapose-dialog" aria-labelledby="juxtapose-title"
	oncancel={(event) => { event.preventDefault(); close(); }}
	onkeydown={(event) => event.stopPropagation()}>
	<header>
		<div>
			<h2 id="juxtapose-title">{t().juxtaposeTitle}</h2>
			<p>{t().juxtaposeHelp}</p>
		</div>
		<button type="button" disabled={busy} aria-label={t().closeLabel} onclick={close}>×</button>
	</header>
	<div class="juxtapose-body">
		<span class="juxtapose-label">{t().inputSectionLabel}</span>
		<p class="juxtapose-text">{description}</p>
		<ModelCardPicker label={t().juxtaposeModel} {selectedModel} providerGroups={visionProviderGroups} purpose="vision" disabled={busy} onSelect={(provider: Provider, model: string) => { selectedModel = qualifiedModelId(provider, model); void onSaveVisionModel(provider, model); }} />
		{#if result}
			<fieldset class="juxtapose-choices" disabled={busy}>
				<legend>{t().juxtaposeChoices.replace('{count}', String(result.candidates))}</legend>
				{#each result.choices as item, index (item.sentence)}
					<label class="juxtapose-choice" class:chosen={chosen === index}>
						<input type="radio" name="juxtapose-choice" checked={chosen === index} onchange={() => (chosen = index)} />
						<span class="juxtapose-sentence">{item.sentence}</span>
						<span class="juxtapose-reason">{item.reason}</span>
					</label>
				{/each}
			</fieldset>
		{/if}
		{#if choice}
			<span class="juxtapose-label">{t().juxtaposeJoined}</span>
			<p class="juxtapose-text joined">{joined}</p>
		{/if}
		{#if error}<div class="juxtapose-error">{error}</div>{/if}
	</div>
	<footer>
		{#if busy}
			<RunStatus variant="inline" label={asking ? t().juxtaposeAsking : (stageLabel || t().pipelineWorking)} stage1Model={asking ? null : stage1ModelLabel} stage2Model={asking ? null : stage2ModelLabel} {elapsedMs} tokensIn={asking ? null : tokensIn} tokensOut={asking ? null : tokensOut} attempt={asking ? null : attempt} onStop={() => controller?.abort()} />
		{:else}
			<button type="button" onclick={close}>{t().pipelineCancel}</button>
			<button type="button" disabled={!selectedModel || !node.history?.id} onclick={ask}>{result ? t().juxtaposeAskAgain : t().juxtaposeAsk}</button>
			<button type="button" class="juxtapose-draw" disabled={!choice} onclick={draw}>{t().juxtaposeDraw}</button>
		{/if}
	</footer>
</dialog>

<style>
	.juxtapose-dialog::backdrop { background: #0009; }
	.juxtapose-dialog { padding: 0; color: var(--fg); }
	/* Centred by its margins, not by a transform: a transform makes the dialog the box the model list's fixed layers are laid out in, and squeezes the list into it. */
	.juxtapose-dialog { position: fixed; z-index: 1461; inset: 0; margin: auto; box-sizing: border-box; width: min(780px, 96vw); height: fit-content; max-height: 92vh; overflow: hidden; display: flex; flex-direction: column; border: 1px solid var(--border2); border-radius: 12px; background: var(--panel); box-shadow: 0 24px 80px #000a; }
	.juxtapose-dialog > header { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; padding: 18px 20px 14px; margin: 0; border-bottom: 1px solid var(--border); }
	.juxtapose-dialog > header h2 { margin: 0 0 4px; font-size: 1.05rem; }
	.juxtapose-dialog > header p { margin: 0; color: var(--fg2); font-size: var(--ui-font-size-12); }
	.juxtapose-dialog > header button { border: 0; background: transparent; color: var(--fg2); font-size: 1.35rem; cursor: pointer; }
	.juxtapose-body { min-height: 0; overflow-y: auto; display: grid; gap: 8px; padding: 18px 20px; }
	.juxtapose-label { color: var(--fg2); font-size: var(--ui-font-size-12); font-weight: 700; }
	.juxtapose-text { margin: 0; padding: 8px 10px; border: 1px solid var(--border); border-radius: 6px; background: var(--bg); white-space: pre-wrap; line-height: 1.55; }
	.juxtapose-text.joined { border-color: var(--border2); }
	.juxtapose-choices { margin: 4px 0 0; padding: 10px 12px; display: grid; gap: 6px; border: 1px solid var(--border); border-radius: 8px; }
	.juxtapose-choices legend { padding: 0 4px; color: var(--fg2); font-size: var(--ui-font-size-12); font-weight: 700; }
	.juxtapose-choice { display: grid; grid-template-columns: auto 1fr; column-gap: 8px; row-gap: 2px; padding: 6px 8px; border-radius: 6px; cursor: pointer; }
	.juxtapose-choice.chosen { background: var(--bg2); }
	.juxtapose-choice input { grid-row: span 2; margin: 3px 0 0; accent-color: var(--accent); }
	.juxtapose-sentence { line-height: 1.5; }
	.juxtapose-reason { color: var(--fg2); font-size: var(--ui-font-size-12); line-height: 1.45; }
	.juxtapose-error { padding: 8px 12px; border: 1px solid var(--danger, #9b3d32); border-radius: 6px; color: var(--danger, #9b3d32); font-size: var(--ui-font-size-12); white-space: pre-line; }
	.juxtapose-dialog > footer { display: flex; justify-content: flex-end; gap: 8px; padding: 12px 20px 16px; border-top: 1px solid var(--border); }
	.juxtapose-dialog > footer button { border: 1px solid var(--border2); border-radius: 7px; padding: 9px 15px; background: var(--panel); color: var(--fg); cursor: pointer; }
	.juxtapose-dialog > footer .juxtapose-draw { border-color: var(--action-bg); background: var(--action-bg); color: var(--action-fg); font-weight: 700; }
	.juxtapose-dialog > footer .juxtapose-draw:hover:not(:disabled) { border-color: var(--action-hover); background: var(--action-hover); }
	.juxtapose-dialog button:disabled { opacity: .55; cursor: default; }
</style>
