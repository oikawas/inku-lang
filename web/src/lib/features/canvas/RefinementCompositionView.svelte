<script lang="ts">
	// "Change the composition and laws" (step 2, 2026-11-13; the mock's section 6):
	// choose what to change, the form or the main law, and see what stays and
	// what is decided again. The list scrolls; what stays and the draw buttons
	// stay in view.
	import { t } from '$lib/i18n/index.svelte';
	import PaintButton from '$lib/components/PaintButton.svelte';
	import RunStatus from '$lib/components/RunStatus.svelte';
	import VariationLanes from '$lib/components/VariationLanes.svelte';
	import RefinementCandidateGrid from './RefinementCandidateGrid.svelte';
	import CompositionChips from '$lib/features/composition-record/CompositionChips.svelte';
	import CompositionFigure from '$lib/features/composition-record/CompositionFigure.svelte';
	import { formName } from '$lib/features/composition-record/composition-names';
	import type { CompositionSummary } from '$lib/features/composition-record/record';
	import { compositionFormOptions, isCompositionForm, isMainLaw, mainLawFamilies, MAX_THESIS_CHARS, thesisWritable,
		type CompositionForm, type CompositionRequest, type MainLaw } from './composition-form';
	import type { RefinementSession } from './refinement-session.svelte';

	let { isJapanese, resultAvailable, artworkUrl, canvasAspectWidth, canvasAspectHeight, refinementSession,
		compositionForm, compositionFormSwitch, targetComposition, onGenerateCandidates, onSaveAndClose, onDiscardAndClose }: {
		isJapanese: boolean; resultAvailable: boolean; artworkUrl: string | null;
		canvasAspectWidth: number; canvasAspectHeight: number; refinementSession: RefinementSession;
		compositionForm: string | null; compositionFormSwitch: boolean;
		targetComposition: CompositionSummary | null;
		onGenerateCandidates: (change: CompositionRequest, count: 1 | 4) => void | Promise<void>;
		onSaveAndClose: () => void | Promise<void>; onDiscardAndClose: () => void | Promise<void>;
	} = $props();
	type What = 'form' | 'main_law' | 'thesis';
	// The thesis (step 4c, the mock's section 6): the author writes one and draws
	// one option, or the AI proposes four and each is drawn.
	type ThesisHow = 'write' | 'propose';
	let thesisHow = $state<ThesisHow>('write');
	let thesisText = $state('');
	let what = $state<What>('form');
	let selectedForm = $state<CompositionForm>('one_corner');
	let selectedLaw = $state<MainLaw>('B1');
	// The parent's form and main law, as its own record answered them.
	const currentForm = $derived(isCompositionForm(compositionForm) ? compositionForm : null);
	const currentLaw = $derived(compositionFormSwitch ? null : targetComposition?.mainLaw ?? null);
	$effect(() => { selectedForm = currentForm ?? 'one_corner'; });
	$effect(() => { selectedLaw = isMainLaw(currentLaw) ? currentLaw : 'B1'; });
	const busy = $derived(refinementSession.busy || refinementSession.gridBusy);
	const families = $derived(mainLawFamilies(isJapanese));
	const selectedSummary = $derived(families.flatMap((family) => family.laws).find((law) => law.code === selectedLaw)?.summary ?? '');
	const change = $derived<CompositionRequest>(what === 'form'
		? { kind: 'form', form: selectedForm }
		: what === 'main_law' ? { kind: 'main_law', mainLaw: selectedLaw, form: currentForm }
		: thesisHow === 'write' ? { kind: 'thesis', thesis: thesisText, source: 'author' } : { kind: 'proposed_theses' });
	const keeps = $derived(what === 'form' ? t().compositionFormKeeps
		: what === 'thesis' ? t().compositionThesisKeeps
		: t().compositionMainLawKeeps(currentForm ? formName(currentForm, isJapanese) : null));
	const redecides = $derived(what === 'form' ? t().compositionFormRedecides
		: what === 'thesis' ? t().compositionThesisRedecides : t().compositionMainLawRedecides(currentForm !== null));
	// A thesis written by the author draws one option; the AI's draw four (the mock's rule).
	const oneAllowed = $derived(what !== 'thesis' || (thesisHow === 'write' && thesisWritable(thesisText)));
	const fourAllowed = $derived(what !== 'thesis' || thesisHow === 'propose');
</script>

<div class="refine-panel"><div class="refine-stage wide">
	<div class="refine-target-column wide">
		<div class="refine-target-card"><div class="comparison-label">{t().refineTargetTitle}</div>
			<div class="comparison-art" style="aspect-ratio: {canvasAspectWidth} / {canvasAspectHeight}">{#if artworkUrl}<img class="canvas-art" src={artworkUrl} alt="" />{/if}</div>
			{#if targetComposition && targetComposition.state !== 'none'}
				<div class="target-now"><span class="target-now-label">{t().compositionTargetNow}</span><CompositionChips summary={targetComposition} {isJapanese} />
					{#if targetComposition.thesis}<p class="target-thesis">{targetComposition.thesis}</p>{/if}
				</div>
			{/if}
		</div>
		<div class="refine-target-controls"><section class="refine-action-section">
			{#if compositionFormSwitch}<p>{t().compositionFormSwitchNotice}</p>{/if}
			<div class="what-head">{t().compositionWhatToChange}</div>
			<div class="segmented what-tabs" role="group" aria-label={t().compositionWhatToChange}>
				<button type="button" class:on={what === 'form'} aria-pressed={what === 'form'} disabled={busy} onclick={() => { what = 'form'; }}>{t().compositionFormTerm}</button>
				<button type="button" class:on={what === 'main_law'} aria-pressed={what === 'main_law'} disabled={busy} onclick={() => { what = 'main_law'; }}>{t().compositionMainLawTerm}</button>
				<button type="button" class:on={what === 'thesis'} aria-pressed={what === 'thesis'} disabled={busy} onclick={() => { what = 'thesis'; }}>{t().compositionThesisLabel}</button>
			</div>
			<div class="what-scroll">
				{#if what === 'form'}
					<div class="form-options" role="radiogroup" aria-label={t().compositionFormTerm}>
						{#each compositionFormOptions(isJapanese) as form}
							<label class="form-option" class:on={selectedForm === form.id}><input type="radio" name="composition-form" value={form.id} bind:group={selectedForm} disabled={busy} />
								<CompositionFigure figure={form.id} size={28} />
								<span><strong>{form.name}</strong>{#if form.id === currentForm} ({t().compositionFormCurrent}){/if}<br /><span class="form-desc">{form.description}</span></span>
							</label>
						{/each}
					</div>
				{:else if what === 'thesis'}
					<div class="thesis-options" role="radiogroup" aria-label={t().compositionThesisLabel}>
						<label class="thesis-choice" class:on={thesisHow === 'write'}><input type="radio" name="composition-thesis-how" value="write" bind:group={thesisHow} disabled={busy} />
							<span><strong>{t().compositionThesisWrite}</strong><br /><span class="form-desc">{t().compositionThesisWriteNote}</span></span>
						</label>
						<textarea class="thesis-input" rows="3" maxlength={MAX_THESIS_CHARS} aria-label={t().compositionThesisWrite}
							bind:value={thesisText} disabled={busy} onfocus={() => { thesisHow = 'write'; }}></textarea>
						<label class="thesis-choice" class:on={thesisHow === 'propose'}><input type="radio" name="composition-thesis-how" value="propose" bind:group={thesisHow} disabled={busy} />
							<span><strong>{t().compositionThesisPropose}</strong><br /><span class="form-desc">{t().compositionThesisProposeNote}</span></span>
						</label>
					</div>
				{:else}
					<div class="law-families" role="radiogroup" aria-label={t().compositionMainLawTerm}>
						{#each families as family}
							<div class="law-family"><div class="law-family-name">{family.family}</div>
								<div class="law-tiles">
									{#each family.laws as law}
										<label class="law-tile" class:on={selectedLaw === law.code} title={law.summary}>
											<input type="radio" name="composition-main-law" value={law.code} bind:group={selectedLaw} disabled={busy} />
											{#if law.code === currentLaw}<span class="tile-now">{t().compositionTargetNow}</span>{/if}
											<CompositionFigure figure={law.code} size={28} />
											<span>{law.name}</span>
										</label>
									{/each}
								</div>
							</div>
						{/each}
					</div>
				{/if}
			</div>
			{#if what === 'main_law' && selectedSummary}<p class="law-sentence">{selectedSummary}</p>{/if}
			<dl class="keeps"><dt>{t().compositionKeepsTerm}</dt><dd>{keeps}</dd><dt>{t().compositionRedecidesTerm}</dt><dd>{redecides}</dd></dl>
			<div class="refine-actions refine-paint-actions">
				<PaintButton onclick={() => onGenerateCandidates(change, 1)} disabled={!resultAvailable || busy || refinementSession.hasUnsaved || !oneAllowed}>{t().refineSingleButton}</PaintButton>
				<PaintButton onclick={() => onGenerateCandidates(change, 4)} disabled={!resultAvailable || busy || refinementSession.hasUnsaved || !fourAllowed}>{t().variationGridDefault}</PaintButton>
				{#if busy}<RunStatus label={t().refineGeneratingTask(refinementSession.gridTaskLabel)}
					progressDone={refinementSession.gridDone} progressTotal={refinementSession.gridTotal}
					elapsedMs={refinementSession.elapsedMs} progress={refinementSession.gridProgress}
					tokensIn={refinementSession.tokensIn} tokensOut={refinementSession.tokensOut}
					onStop={refinementSession.gridBusy && refinementSession.gridCanAbort ? () => refinementSession.abort() : null} />
					<VariationLanes states={refinementSession.gridSlots} labels={refinementSession.gridSlotLabels} />
				{/if}
			</div>
		</section></div>
	</div>
	<RefinementCandidateGrid {isJapanese} {refinementSession} {onSaveAndClose} {onDiscardAndClose} maxColumns={4}
		target={{ artworkUrl, aspectWidth: canvasAspectWidth, aspectHeight: canvasAspectHeight, composition: targetComposition }} />
</div></div>

<style>
	/* The mock's wide left column: the target sits beside its "Now", so the
	   list, what stays and the draw buttons fit below it (section 6). */
	.refine-stage.wide { grid-template-columns: 388px minmax(0, 1fr); }
	.refine-target-column.wide .refine-target-card { display: grid; grid-template-columns: 150px minmax(0, 1fr); gap: 4px 12px; }
	.refine-target-column.wide .refine-target-card > :global(.comparison-label) { grid-column: 1 / -1; margin: 0; }
	.refine-target-column.wide .target-now { margin-top: 0; align-content: start; }
	.what-head { color: var(--fg); font-size: var(--ui-font-size-12); font-weight: 600; }
	.segmented { display: inline-flex; padding: 2px; border: 1px solid var(--border2); border-radius: 6px; background: var(--bg); }
	.segmented button { padding: 4px 14px; border: 0; border-radius: 4px; background: none; color: var(--fg2); font-size: var(--ui-font-size-12); cursor: pointer; white-space: nowrap; }
	.segmented button.on { background: var(--bg3); color: var(--fg); font-weight: 600; }
	.what-tabs { display: grid; grid-template-columns: repeat(3, 1fr); }
	.thesis-options { display: grid; gap: 6px; font-size: var(--ui-font-size-12); }
	.thesis-choice { display: grid; grid-template-columns: auto minmax(0, 1fr); gap: 8px; align-items: start; padding: 5px 8px; border: 1px solid transparent; border-radius: var(--r, 6px); cursor: pointer; color: var(--fg2); }
	.thesis-choice.on { border-color: var(--accent); background: var(--accent-light); color: var(--fg); }
	.thesis-choice input { accent-color: var(--accent); margin: 3px 0 0; }
	.thesis-input { width: 100%; box-sizing: border-box; padding: 6px 8px; border: 1px solid var(--border2); border-radius: var(--r, 6px); background: var(--bg); color: var(--fg); font: inherit; line-height: 1.6; resize: vertical; }
	.what-scroll { max-height: 322px; overflow: auto; padding-right: 4px; }
	.form-options { display: grid; gap: 4px; font-size: var(--ui-font-size-12); }
	.form-option { display: grid; grid-template-columns: auto 30px minmax(0, 1fr); gap: 8px; align-items: center; padding: 5px 8px; border: 1px solid transparent; border-radius: var(--r, 6px); cursor: pointer; color: var(--fg2); }
	.form-option.on { border-color: var(--accent); background: var(--accent-light); color: var(--fg); }
	.form-option input, .law-tile input { accent-color: var(--accent); margin: 0; }
	.form-desc { color: var(--fg3); font-size: var(--ui-font-size-11, 11.5px); line-height: 1.5; }
	.law-families { display: flex; flex-direction: column; gap: 8px; }
	.law-family { display: grid; grid-template-columns: 3.4em minmax(0, 1fr); gap: 6px; align-items: start; }
	.law-family-name { padding-top: 12px; color: var(--fg3); font-size: var(--ui-font-size-11, 11px); }
	.law-tiles { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 4px; }
	.law-tile { position: relative; display: flex; flex-direction: column; align-items: center; gap: 3px; padding: 7px 2px 6px; border: 1px solid var(--border); border-radius: var(--r, 6px); color: var(--fg2); font-size: var(--ui-font-size-11, 11px); text-align: center; cursor: pointer; }
	.law-tile input { position: absolute; opacity: 0; }
	.law-tile.on { border-color: var(--accent); background: var(--accent-light); color: var(--fg); }
	.law-tile:has(input:focus-visible) { outline: 2px solid var(--accent); outline-offset: 1px; }
	.tile-now { position: absolute; top: 3px; right: 3px; padding: 0 4px; color: var(--fg3); font-size: 10px; }
	.law-tile :global(.composition-figure), .form-option :global(.composition-figure) { color: var(--fg2); }
	.law-sentence { margin: 0; padding: 8px 10px; border-left: 2px solid var(--accent); color: var(--fg2); font-size: var(--ui-font-size-12); line-height: 1.7; }
	.keeps { display: grid; grid-template-columns: auto minmax(0, 1fr); gap: 3px 10px; margin: 2px 0 0; padding: 8px 10px; border: 1px solid var(--border); border-radius: var(--r, 6px); background: var(--panel2, var(--bg2)); font-size: var(--ui-font-size-12); line-height: 1.6; }
	.keeps dt { color: var(--fg3); white-space: nowrap; }
	.keeps dd { margin: 0; color: var(--fg2); }
</style>
