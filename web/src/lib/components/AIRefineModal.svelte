<script lang="ts">
	import { onDestroy, onMount, tick } from 'svelte';
	import { t } from '$lib/i18n/index.svelte';
	import { qualifiedModelId, type Provider, type ProviderGroup } from '$lib/models';
	import type { LineageNode } from '$lib/features/history/types';
	import type { HistoryItem } from '$lib/historyManagerState.svelte';
	import HistoryThumbnail from './HistoryThumbnail.svelte';
	import ModelCardPicker from './ModelCardPicker.svelte';
	import WildToggle from './WildToggle.svelte';
	import { loadAiRefineSettings, saveAiRefineSettings } from '$lib/features/canvas/ai-refine-settings';
	import {
		AUTONOMOUS_NOTE_LIMIT, AUTONOMOUS_POLL_MS, runToResume, sharePercent, triesOf,
		type AutonomousKind, type AutonomousOutcome, type AutonomousRun, type AutonomousRunsApi
	} from '$lib/features/autonomous/runs';
	import { restoreWorkActionFocus } from './WorkActionMenu.svelte';

	// The Server takes the run (the author, 2026-10-20): this dialog starts it,
	// reads how it stands every few seconds, and can stop it. Closing the dialog
	// only stops the reading; opening the work again shows a run still going.
	type Props = {
		node: LineageNode;
		visionModel: string;
		visionProviderGroups: ProviderGroup[];
		autonomousRuns: AutonomousRunsApi;
		onClose: () => void;
		onSaveVisionModel: (provider: Provider, model: string) => void | Promise<void>;
		/** Open a child the run kept; the last one is in the history once the run ends. */
		onOpenChild: (historyId: string, nodeId: string | null) => void | Promise<void>;
	};

	let { node, visionModel, visionProviderGroups, autonomousRuns, onClose, onSaveVisionModel, onOpenChild }: Props = $props();

	// The choices made last time (kept in this browser).
	const saved = loadAiRefineSettings();
	let moves = $state(saved.moves);
	let useLaws = $state(saved.laws);
	let useJuxtaposition = $state(saved.juxtaposition);
	let note = $state(saved.note);
	$effect(() => { saveAiRefineSettings({ moves, laws: useLaws, juxtaposition: useJuxtaposition, note }); });
	// One model chooses the sentence, takes the laws stage and draws every child.
	let selectedModel = $state('');
	$effect(() => { if (!selectedModel) selectedModel = visionModel; });
	// null = each child keeps its parent work's setting.
	let wildOverride = $state<boolean | null>(null);
	const parentWild = $derived(node.history?.render_wild === true);
	// A work its edited DDL holds takes no sentence; the run takes laws moves from it.
	const held = $derived(node.history?.description_locked === true);
	const isJapanese = $derived(t().code === 'ja');

	let run = $state<AutonomousRun | null>(null);
	let starting = $state(false);
	let error = $state<string | null>(null);
	let dialogEl = $state<HTMLDialogElement | null>(null);
	let fallbackFocus: HTMLElement | null = null;
	let poll: ReturnType<typeof setTimeout> | null = null;
	let controller: AbortController | null = null;
	let closed = false;

	const kinds = $derived([...(useLaws ? ['laws'] : []), ...(useJuxtaposition ? ['juxtaposition'] : [])] as AutonomousKind[]);
	const running = $derived(run?.state === 'running');
	const tries = $derived(run ? triesOf(run) : []);

	onMount(() => {
		fallbackFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
		dialogEl?.showModal();
		void resume();
	});

	// Closing stops the reading; the run itself goes on in the Server.
	onDestroy(() => {
		closed = true;
		if (poll !== null) clearTimeout(poll);
		controller?.abort();
		dialogEl?.close();
	});

	function failure(cause: unknown): string | null {
		if (cause instanceof Error && cause.name === 'AbortError') return null;
		return cause instanceof Error ? cause.message : String(cause);
	}

	async function resume(): Promise<void> {
		const historyId = node.history?.id;
		if (!historyId) return;
		controller = new AbortController();
		try {
			const going = runToResume(await autonomousRuns.forHistory(historyId, controller.signal));
			if (going && !closed) {
				run = going;
				schedule();
			}
		} catch (cause) {
			error = failure(cause);
		} finally {
			controller = null;
		}
	}

	function schedule(): void {
		if (closed || run?.state !== 'running') return;
		poll = setTimeout(() => { void read(); }, AUTONOMOUS_POLL_MS);
	}

	async function read(): Promise<void> {
		poll = null;
		if (!run || closed) return;
		controller = new AbortController();
		try {
			run = await autonomousRuns.read(run.id, controller.signal);
		} catch (cause) {
			error = failure(cause);
		} finally {
			controller = null;
			schedule();
		}
	}

	async function start(): Promise<void> {
		if (starting || running || !node.history?.id || !selectedModel) return;
		if (kinds.length === 0) {
			error = t().aiRefineKindsError;
			return;
		}
		starting = true;
		error = null;
		try {
			run = await autonomousRuns.start({
				history_id: node.history.id, moves, kinds, note: note.trim() || null, model: selectedModel, wild: wildOverride
			});
			schedule();
		} catch (cause) {
			error = failure(cause);
		} finally {
			starting = false;
		}
	}

	async function stop(): Promise<void> {
		if (!run || !running) return;
		try {
			run = await autonomousRuns.stop(run.id);
		} catch (cause) {
			error = failure(cause);
		}
	}

	function close(): void {
		onClose();
		void tick().then(() => {
			if (!restoreWorkActionFocus()) fallbackFocus?.focus();
		});
	}

	async function openLast(): Promise<void> {
		const last = run?.last_kept_history_id;
		if (!last) return;
		const kept = tries.find(({ attempt }) => attempt.history_id === last)?.attempt;
		close();
		await onOpenChild(last, kept?.lineage_node_id ?? null);
	}

	function kindLabel(kind: AutonomousKind): string {
		return kind === 'laws' ? t().aiRefineKindLaws : t().aiRefineKindJuxtaposition;
	}

	function outcomeLabel(outcome: AutonomousOutcome): string {
		return {
			kept: t().aiRefineOutcomeKept,
			not_visible: t().aiRefineOutcomeNotVisible,
			unavailable: t().aiRefineOutcomeUnavailable,
			failed: t().aiRefineOutcomeFailed
		}[outcome];
	}

	const status = $derived.by(() => {
		if (!run) return '';
		if (run.state === 'running') {
			if (run.stopping) return t().aiRefineStopping;
			return run.current ? t().aiRefineTaking(run.current.turn, kindLabel(run.current.kind)) : t().pipelineWorking;
		}
		const ended = {
			moves_done: t().aiRefineEndedMovesDone,
			nothing_available: t().aiRefineEndedNothingAvailable,
			stalled: t().aiRefineEndedStalled,
			stopped: t().aiRefineEndedStopped,
			interrupted: t().aiRefineEndedInterrupted
		}[run.stop_reason ?? ''] ?? t().aiRefineEndedFailed;
		return run.last_kept_history_id ? ended : `${ended}${t().aiRefineNoneKept}`;
	});

	// A thumbnail needs only the work's id: it is fetched by it.
	function child(historyId: string): HistoryItem {
		return { id: historyId } as HistoryItem;
	}
</script>

<dialog bind:this={dialogEl} class="ai-refine-dialog" aria-labelledby="ai-refine-title"
	oncancel={(event) => { event.preventDefault(); close(); }}
	onkeydown={(event) => event.stopPropagation()}>
	<header>
		<div>
			<h2 id="ai-refine-title">{t().aiRefineTitle}</h2>
			<p>{t().aiRefineHelp}</p>
		</div>
		<button type="button" aria-label={t().closeLabel} onclick={close}>×</button>
	</header>
	<div class="ai-refine-body">
		{#if run}
			<p class="ai-refine-status" aria-live="polite">{status}</p>
			{#if tries.length > 0}
				<ol class="ai-refine-tries">
					{#each tries as { turn, attempt } (`${turn}-${attempt.attempt}`)}
						<li class="ai-refine-try" class:kept={attempt.outcome === 'kept'}>
							<div class="ai-refine-thumb">
								{#if attempt.history_id}<HistoryThumbnail item={child(attempt.history_id)} scope="ai-refine-progress" size="mini" />{/if}
							</div>
							<div class="ai-refine-try-text">
								<span class="ai-refine-try-head">{t().aiRefineTurn(turn)} · {kindLabel(attempt.kind)} · {outcomeLabel(attempt.outcome)}{#if sharePercent(attempt.share)} · {t().aiRefineShare(sharePercent(attempt.share) ?? '')}{/if}</span>
								{#if attempt.sentence}<span class="ai-refine-try-detail">{attempt.sentence}</span>{:else if attempt.main_law}<span class="ai-refine-try-detail">{attempt.main_law}</span>{/if}
								{#if attempt.reason && (attempt.outcome === 'unavailable' || attempt.outcome === 'failed')}<span class="ai-refine-try-reason">{attempt.reason}</span>{/if}
							</div>
						</li>
					{/each}
				</ol>
			{/if}
			{#if running}<p class="ai-refine-note">{t().aiRefineGoesOn}</p>{/if}
		{:else}
			{#if held}<p class="ai-refine-note">{t().aiRefineHeldNote}</p>{/if}
			<ModelCardPicker label={t().aiRefineModel} {selectedModel} providerGroups={visionProviderGroups} purpose="vision" disabled={starting} onSelect={(provider: Provider, model: string) => { selectedModel = qualifiedModelId(provider, model); void onSaveVisionModel(provider, model); }} />
			<fieldset class="ai-refine-kinds" disabled={starting}>
				<legend>{t().aiRefineKindsLabel}</legend>
				<label><input type="checkbox" bind:checked={useLaws} /><span>{t().aiRefineKindLaws}</span></label>
				<label><input type="checkbox" bind:checked={useJuxtaposition} /><span>{t().aiRefineKindJuxtaposition}</span></label>
			</fieldset>
			<div class="ai-refine-row">
				<div class="ai-refine-field">
					<span class="ai-refine-label">{t().aiRefineMovesLabel}</span>
					<div class="ai-refine-stepper">
						<button type="button" aria-label="−" onclick={() => (moves = Math.max(1, moves - 1))} disabled={starting || moves <= 1}>−</button>
						<span class="ai-refine-moves">{moves}</span>
						<button type="button" aria-label="＋" onclick={() => (moves = Math.min(10, moves + 1))} disabled={starting || moves >= 10}>＋</button>
					</div>
				</div>
				<WildToggle value={wildOverride ?? parentWild} {isJapanese} inherited={wildOverride === null} onSelect={(next) => (wildOverride = next)} />
			</div>
			<label class="ai-refine-field">
				<span class="ai-refine-label">{t().aiRefineDirectionLabel}</span>
				<textarea bind:value={note} maxlength={AUTONOMOUS_NOTE_LIMIT} rows="3" placeholder={t().aiRefineDirectionPlaceholder} disabled={starting}></textarea>
			</label>
		{/if}
		{#if error}<div class="ai-refine-error">{error}</div>{/if}
	</div>
	<footer>
		{#if running}
			<button type="button" onclick={close}>{t().closeLabel}</button>
			<button type="button" class="ai-refine-primary" disabled={run?.stopping} onclick={stop}>{run?.stopping ? t().aiRefineStopping : t().aiRefineStop}</button>
		{:else if run}
			<button type="button" onclick={close}>{t().closeLabel}</button>
			{#if run.last_kept_history_id}<button type="button" class="ai-refine-primary" onclick={openLast}>{t().aiRefineOpenLast}</button>{/if}
		{:else}
			<button type="button" onclick={close}>{t().pipelineCancel}</button>
			<button type="button" class="ai-refine-primary" disabled={starting || kinds.length === 0 || !selectedModel || !node.history?.id} onclick={start}>{t().aiRefineStartButton}</button>
		{/if}
	</footer>
</dialog>

<style>
	.ai-refine-dialog::backdrop { background: #0009; }
	.ai-refine-dialog { padding: 0; color: var(--fg); }
	/* Centred by its margins, not by a transform: a transform makes the dialog the box the model list's fixed layers are laid out in, and squeezes the list into it. */
	.ai-refine-dialog { position: fixed; z-index: 1461; inset: 0; margin: auto; box-sizing: border-box; width: min(720px, 96vw); height: fit-content; max-height: 92vh; overflow: hidden; display: flex; flex-direction: column; border: 1px solid var(--border2); border-radius: 12px; background: var(--panel); box-shadow: 0 24px 80px #000a; }
	.ai-refine-dialog > header { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; padding: 18px 20px 14px; margin: 0; border-bottom: 1px solid var(--border); }
	.ai-refine-dialog > header h2 { margin: 0 0 4px; font-size: 1.05rem; }
	.ai-refine-dialog > header p { margin: 0; color: var(--fg2); font-size: var(--ui-font-size-12); line-height: 1.5; }
	.ai-refine-dialog > header button { border: 0; background: transparent; color: var(--fg2); font-size: 1.35rem; cursor: pointer; }
	.ai-refine-body { min-height: 0; overflow-y: auto; display: grid; gap: 12px; padding: 18px 20px; }
	.ai-refine-note { margin: 0; padding: 8px 10px; border: 1px solid var(--border); border-radius: 6px; background: var(--bg2); color: var(--fg2); font-size: var(--ui-font-size-12); line-height: 1.55; }
	.ai-refine-status { margin: 0; font-weight: 700; }
	.ai-refine-kinds { margin: 0; padding: 8px 12px 10px; display: flex; flex-wrap: wrap; gap: 8px 18px; border: 1px solid var(--border); border-radius: 8px; }
	.ai-refine-kinds legend { padding: 0 4px; color: var(--fg2); font-size: var(--ui-font-size-12); font-weight: 700; }
	.ai-refine-kinds label { display: flex; align-items: center; gap: 6px; cursor: pointer; }
	.ai-refine-kinds input { accent-color: var(--accent); margin: 0; }
	.ai-refine-row { display: flex; flex-wrap: wrap; align-items: flex-end; gap: 12px 24px; }
	.ai-refine-field { display: grid; gap: 6px; }
	.ai-refine-label { color: var(--fg2); font-size: var(--ui-font-size-12); font-weight: 700; }
	.ai-refine-stepper { display: flex; align-items: center; width: fit-content; border: 1px solid var(--border2); border-radius: 6px; overflow: hidden; }
	.ai-refine-stepper button { width: 34px; height: 32px; border: 0; background: var(--bg); color: var(--fg); font-size: 1rem; line-height: 1; cursor: pointer; }
	.ai-refine-stepper button:hover:not(:disabled) { background: var(--bg2); }
	.ai-refine-moves { min-width: 38px; text-align: center; font-variant-numeric: tabular-nums; }
	textarea { box-sizing: border-box; width: 100%; border: 1px solid var(--border2); border-radius: 6px; padding: 8px 10px; background: var(--bg); color: var(--fg); font: inherit; resize: vertical; line-height: 1.45; }
	.ai-refine-tries { margin: 0; padding: 0; list-style: none; display: grid; gap: 6px; }
	.ai-refine-try { display: grid; grid-template-columns: 56px 1fr; align-items: start; gap: 10px; padding: 6px 8px; border: 1px solid var(--border); border-radius: 8px; }
	.ai-refine-try.kept { border-color: var(--accent); }
	.ai-refine-thumb { width: 56px; height: 56px; border-radius: 4px; overflow: hidden; background: var(--bg2); }
	.ai-refine-thumb :global(.history-thumbnail) { width: 100%; height: 100%; aspect-ratio: auto; }
	.ai-refine-try-text { display: grid; gap: 2px; min-width: 0; }
	.ai-refine-try-head { font-size: var(--ui-font-size-12); font-weight: 700; }
	.ai-refine-try-detail { line-height: 1.45; overflow-wrap: anywhere; }
	.ai-refine-try-reason { color: var(--fg3); font-size: var(--ui-font-size-12); overflow-wrap: anywhere; }
	.ai-refine-error { padding: 8px 12px; border: 1px solid var(--danger, #9b3d32); border-radius: 6px; color: var(--danger, #9b3d32); font-size: var(--ui-font-size-12); white-space: pre-line; }
	.ai-refine-dialog > footer { display: flex; justify-content: flex-end; gap: 8px; padding: 12px 20px 16px; border-top: 1px solid var(--border); }
	.ai-refine-dialog > footer button { border: 1px solid var(--border2); border-radius: 7px; padding: 9px 15px; background: var(--panel); color: var(--fg); cursor: pointer; }
	.ai-refine-dialog > footer .ai-refine-primary { border-color: var(--action-bg); background: var(--action-bg); color: var(--action-fg); font-weight: 700; }
	.ai-refine-dialog > footer .ai-refine-primary:hover:not(:disabled) { border-color: var(--action-hover); background: var(--action-hover); }
	.ai-refine-dialog button:disabled { opacity: .55; cursor: default; }
</style>
