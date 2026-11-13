<script lang="ts">
	// "Composition and laws" in the left panel, between the sketch from life and
	// the instructions (2026-11-13, the author's mock). Folded, it shows the
	// thesis (two lines) and the form and main law by name; open, the record the
	// work keeps: form, main law, laws, colors, reason and the things. It reads
	// only; its one button opens the work menu's "change the form" dialog.
	import { t } from '$lib/i18n/index.svelte';
	import { compositionStateNote } from '$lib/draw-route';
	import { describePanelSettings } from '$lib/features/describe-panel/settings.svelte';
	import CompositionFigure from './CompositionFigure.svelte';
	import { colorLawName, formName, lawName, roleName } from './composition-names';
	import { compositionShown, quoteInDescription, shownRecordOf, shownThingPlaces } from './record';
	import { derivationKindLabel } from '$lib/derivation';
	import { formatHistoryMinute } from '$lib/historyManagerPresentation';

	type Props = {
		work: { description_ddl?: unknown; composition_inherited?: unknown } | null | undefined;
		description: string | null | undefined;
		isJapanese: boolean;
		/** Whether the work menu offers the description group at all (not for a DDL work). */
		offersDescriptionActions: boolean;
		/** Held by its DDL: the actions that read the description again are greyed. */
		descriptionLocked: boolean;
		onChangeForm: () => void | Promise<void>;
		/** Opens "Change the layout", which moves one thing to a place (step 3); it keeps the DDL, so a held work may use it. */
		onChangeLayout?: () => void | Promise<void>;
		/** The thing pointed at anywhere on the page, and the reports of this list (step 1c). */
		activeThing?: number | null;
		onPointThing?: (thing: number | null) => void;
		/** A pressed row sends the instructions to its thing's chunk. */
		onRevealThing?: (thing: number) => void;
	};

	let { work, description, isJapanese, offersDescriptionActions, descriptionLocked, onChangeForm, onChangeLayout,
		activeThing = null, onPointThing = () => {}, onRevealThing = () => {} }: Props = $props();

	const view = $derived(shownRecordOf(work));
	const record = $derived(view.record);
	// A child drawn without reading the description again shows its ancestor's record, marked (step 1d).
	const inherited = $derived(view.inherited);
	const inheritedNote = $derived(inherited
		? t().compositionInheritedNote(derivationKindLabel(inherited.via[0] ?? null, isJapanese),
			inherited.at === null ? '—' : formatHistoryMinute(inherited.at, isJapanese ? 'ja-JP' : 'en-US'))
		: null);
	const shown = $derived(compositionShown(record));
	const answer = $derived(shown.kind === 'used' ? shown.record.answer ?? null : null);
	const form = $derived(typeof answer?.form === 'string' ? answer.form : null);
	const mainLaw = $derived(typeof answer?.main_law === 'string' ? answer.main_law : null);
	const otherLaws = $derived(Object.keys(answer?.laws ?? {}).filter((code) => code !== mainLaw));
	const colors = $derived(shown.kind === 'used' ? shown.record.colors ?? null : null);
	const colorLaws = $derived(colors?.state === 'used'
		? (Array.isArray((colors as { laws?: unknown }).laws) ? ((colors as { laws: unknown[] }).laws.filter((code): code is string => typeof code === 'string')) : [])
		: []);
	// A thing "change the layout" moved shows its new place, not the parent's (step 3).
	const places = $derived(shownThingPlaces(answer, inherited?.moved, isJapanese, t().compositionMovedNote));
	const things = $derived((answer?.things ?? []).filter((thing) => Number.isInteger(thing.thing)));
	const open = $derived(describePanelSettings.compositionOpen);
</script>

<section class="panel-section composition-section" class:open>
	<div class="composition-head">
		<button class="composition-toggle" type="button" aria-expanded={open} onclick={describePanelSettings.toggleComposition}>
			<span class="composition-arrow" class:open>▶</span>
			<span class="composition-title">{t().compositionSectionTitle}</span>
		</button>
		<span class="composition-summary">
			{#if inherited}<span class="inherited-mark">{t().compositionInheritedMark}</span>{/if}
			{#if shown.kind === 'used'}
				{#if form}<span class="name-fig"><CompositionFigure figure={form} />{formName(form, isJapanese)}</span>{/if}
				{#if form && mainLaw}<span aria-hidden="true">·</span>{/if}
				{#if mainLaw}<span class="name-fig"><CompositionFigure figure={mainLaw} />{lawName(mainLaw, isJapanese)}</span>{/if}
			{:else if shown.kind === 'fallback'}
				<span class="summary-plain">{t().compositionFallback}</span>
			{:else}
				<span class="summary-plain">{t().compositionNoRecord}</span>
			{/if}
		</span>
	</div>

	{#if shown.kind === 'used'}
		{#if answer?.thesis}<p class="composition-thesis" class:open>{answer.thesis}</p>{/if}
		{#if open}
			<div class="composition-body">
				{#if inheritedNote}<p class="inherited-note">{inheritedNote}</p>{/if}
				{#if offersDescriptionActions || onChangeLayout}
					<div class="comp-actions">
						{#if offersDescriptionActions}
							<button class="ghost-btn" type="button" aria-disabled={descriptionLocked} class:held={descriptionLocked}
								title={descriptionLocked ? t().descriptionLockedReason : undefined}
								onclick={() => { if (!descriptionLocked) void onChangeForm(); }}>{t().workActionComposition}</button>
						{/if}
						{#if onChangeLayout}
							<button class="ghost-btn" type="button" onclick={() => void onChangeLayout()}>{t().canvasVaryComposition}</button>
						{/if}
					</div>
				{/if}
				<dl class="comp-grid">
					{#if form}
						<dt>{t().compositionFormTerm}</dt>
						<dd><CompositionFigure figure={form} size={22} /><strong>{formName(form, isJapanese)}</strong></dd>
					{/if}
					{#if mainLaw}
						<dt>{t().compositionMainLawTerm}</dt>
						<dd><CompositionFigure figure={mainLaw} size={22} /><strong>{lawName(mainLaw, isJapanese)}</strong></dd>
					{/if}
					{#if otherLaws.length}
						<dt>{t().compositionLawsTerm}</dt>
						<dd>{otherLaws.map((code) => lawName(code, isJapanese)).join(isJapanese ? '・' : ', ')}</dd>
					{/if}
					{#if colorLaws.length}
						<dt>{t().compositionColorsTerm}</dt>
						<dd>{colorLaws.map((code) => colorLawName(code, isJapanese)).join(isJapanese ? '・' : ', ')}</dd>
					{/if}
					{#if answer?.reason}
						<dt>{t().compositionReasonTerm}</dt>
						<dd class="comp-reason">{answer.reason}</dd>
					{/if}
				</dl>
				{#if things.length}
					<div class="comp-things-head">{t().compositionThingsHead}</div>
					<ol class="thing-list">
						{#each things as thing (thing.thing)}
							<li><button type="button" class="thing-row" class:active={activeThing === thing.thing} data-thing={thing.thing}
								onmouseenter={() => onPointThing(thing.thing as number)} onmouseleave={() => onPointThing(null)}
								onfocus={() => onPointThing(thing.thing as number)} onblur={() => onPointThing(null)}
								onclick={() => onRevealThing(thing.thing as number)}>
								<span class="thing-no">{thing.thing}</span>
								<span class="thing-role">{thing.role ? roleName(thing.role, isJapanese) : ''}</span>
								<span class="thing-main">
									<span class="thing-what">{thing.what ?? ''}</span>
									<span class="thing-place">{places.get(thing.thing as number) ?? ''}</span>
									{#if thing.quote}
										<span class="thing-quote">「{thing.quote}」{#if !quoteInDescription(thing.quote, description)}<span class="thing-from">{t().compositionFromReading}</span>{/if}</span>
									{/if}
								</span>
							</button></li>
						{/each}
					</ol>
				{/if}
			</div>
		{/if}
	{:else if open}
		<p class="composition-note">{shown.kind === 'fallback' ? compositionStateNote(shown.record, isJapanese) : t().compositionNoRecordNote}</p>
	{/if}
</section>

<style>
	.composition-section { display: grid; gap: 6px; }
	.composition-head { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; }
	/* The same fold as the sketch section above it. */
	.composition-toggle { display: flex; align-items: center; gap: 5px; padding: 6px 0; border: 0; background: none; color: var(--fg3); font-family: inherit; cursor: pointer; text-align: left; }
	.composition-arrow { display: inline-block; font-size: var(--ui-font-size-8); transition: transform 0.15s ease; }
	.composition-arrow.open { transform: rotate(90deg); }
	.composition-title { font-size: var(--ui-font-size-12); color: var(--fg2); }
	.composition-summary { margin-left: auto; display: inline-flex; align-items: center; gap: 4px; font-size: var(--ui-font-size-12); color: var(--fg2); white-space: nowrap; }
	.summary-plain { color: var(--fg3); }
	.inherited-mark { padding: 0 6px; border: 1px solid var(--border2); border-radius: 999px; color: var(--fg3); font-size: var(--ui-font-size-10); line-height: 1.6; }
	.inherited-note { margin: 0; color: var(--fg3); font-size: var(--ui-font-size-12); line-height: 1.6; }
	.name-fig { display: inline-flex; align-items: center; gap: 4px; }
	.composition-thesis { margin: -2px 0 0 13px; color: var(--fg); font-size: var(--ui-font-size-13); line-height: 1.7; display: -webkit-box; -webkit-line-clamp: 2; line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
	.composition-thesis.open { display: block; }
	.composition-note { margin: 0 0 0 13px; color: var(--fg3); font-size: var(--ui-font-size-12); line-height: 1.6; }
	.composition-body { display: flex; flex-direction: column; gap: 10px; margin: 6px 0 2px 13px; }
	.comp-actions { display: flex; gap: 6px; justify-content: flex-end; }
	.comp-actions .held { opacity: .5; cursor: not-allowed; }
	.comp-grid { display: grid; grid-template-columns: 4.6em minmax(0, 1fr); gap: 7px 10px; align-items: baseline; margin: 0; }
	.comp-grid dt { color: var(--fg3); font-size: var(--ui-font-size-11); line-height: 1.6; white-space: nowrap; }
	.comp-grid dd { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; margin: 0; color: var(--fg2); font-size: var(--ui-font-size-12); line-height: 1.6; min-width: 0; }
	.comp-grid dd strong { color: var(--fg); font-weight: 500; }
	.comp-grid dd.comp-reason { display: block; line-height: 1.75; }
	.comp-things-head { margin-top: 2px; color: var(--fg3); font-size: var(--ui-font-size-11); }
	.thing-list { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 1px; }
	/* Top-aligned: the things' names can wrap, and the number and role stay on their first line. */
	.thing-row { display: grid; grid-template-columns: 18px 2.6em minmax(0, 1fr); gap: 2px 8px; align-items: start; width: 100%; padding: 5px 8px 5px 6px; border: 0; border-left: 2px solid transparent; background: none; color: inherit; font: inherit; text-align: left; cursor: pointer; }
	/* The thing pointed at here, on the drawing or in the instructions (step 1c). */
	.thing-row.active, .thing-row:hover { border-left-color: var(--accent); background: color-mix(in srgb, var(--accent) 8%, transparent); }
	.thing-no { display: grid; place-items: center; width: 16px; height: 16px; margin-top: 1px; border: 1px solid var(--border2); border-radius: 50%; color: var(--fg2); font-size: var(--ui-font-size-10); line-height: 1; }
	.thing-role { color: var(--fg3); font-size: var(--ui-font-size-11); line-height: 1.7; white-space: nowrap; }
	.thing-main { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 1px 10px; min-width: 0; }
	.thing-what { color: var(--fg); font-size: var(--ui-font-size-12); line-height: 1.55; }
	.thing-place { color: var(--fg3); font-size: var(--ui-font-size-11); white-space: nowrap; align-self: baseline; }
	.thing-quote { grid-column: 1 / -1; color: var(--fg3); font-size: var(--ui-font-size-12); line-height: 1.5; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
	.thing-from { margin-left: 6px; padding: 0 5px; border: 1px solid var(--border2); border-radius: 999px; font-size: var(--ui-font-size-10); }
</style>
