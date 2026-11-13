<script lang="ts">
	// "Change the layout" on a work written in words (step 3, 2026-11-13; the mock's
	// section 7): choose a thing, press a place, and an option drawn with the thing
	// there joins the others. Nothing is sent. A place the thing cannot take is not
	// pressable and says why; the thing's own place is marked.
	import { t } from '$lib/i18n/index.svelte';
	import RunStatus from '$lib/components/RunStatus.svelte';
	import VariationLanes from '$lib/components/VariationLanes.svelte';
	import RefinementCandidateGrid from './RefinementCandidateGrid.svelte';
	import CompositionChips from '$lib/features/composition-record/CompositionChips.svelte';
	import { placeName } from '$lib/features/composition-record/composition-names';
	import type { CompositionSummary } from '$lib/features/composition-record/record';
	import { PLACES, movable, placeLabel, placeRows, type PlaceId, type PlaceTarget } from './place';
	import type { RefinementSession } from './refinement-session.svelte';

	let { isJapanese, resultAvailable, artworkUrl, canvasAspectWidth, canvasAspectHeight, refinementSession,
		targetComposition, target, onGeneratePlaceCandidate, onSaveAndClose, onDiscardAndClose }: {
		isJapanese: boolean; resultAvailable: boolean; artworkUrl: string | null;
		canvasAspectWidth: number; canvasAspectHeight: number; refinementSession: RefinementSession;
		targetComposition: CompositionSummary | null;
		target: PlaceTarget;
		onGeneratePlaceCandidate: (chunk: string, at: string, label: string) => Promise<string | null>;
		onSaveAndClose: () => void | Promise<void>; onDiscardAndClose: () => void | Promise<void>;
	} = $props();

	const rows = $derived(placeRows(target, isJapanese));
	let chosen = $state<string | null>(null);
	$effect(() => {
		if (!rows.some((row) => row.title === chosen)) chosen = rows.find((row) => row.movable)?.title ?? null;
	});
	const row = $derived(rows.find((entry) => entry.title === chosen) ?? null);
	const busy = $derived(refinementSession.busy || refinementSession.gridBusy);
	let refused = $state<string | null>(null);
	const drawn = (at: PlaceId) => !!row && refinementSession.candidates.some((candidate) => candidate.id === `place-${row.title}-${at}`);
	// Each press adds an option to the others (as Change the model does), so unsaved
	// options do not hold the places.
	const pressable = (at: PlaceId) => !!row && movable(row.places[at]) && !drawn(at) && resultAvailable && !busy;
	const title = (at: PlaceId) => {
		if (!row) return placeName(at, isJapanese);
		const outcome = row.places[at];
		const name = placeName(at, isJapanese);
		if (row.now === at) return `${name}（${t().compositionTargetNow}）`;
		if (!movable(outcome)) return `${name}: ${t().placeRefused(outcome ?? 'no_chunk')}`;
		return outcome === 'clamped' ? `${name}${t().placeClamped}` : name;
	};
	async function press(at: PlaceId) {
		if (!row || !pressable(at)) return;
		refused = null;
		const reason = await onGeneratePlaceCandidate(row.title, at, placeLabel(row, at, isJapanese, t().placeClamped));
		if (reason) refused = t().placeRefused(reason);
	}
	const frame = $derived(row?.box ? {
		left: row.box[0] * 100, top: row.box[1] * 100, width: (row.box[2] - row.box[0]) * 100, height: (row.box[3] - row.box[1]) * 100,
	} : null);
</script>

<div class="refine-panel"><div class="refine-stage wide">
	<div class="refine-target-column wide">
		<div class="refine-target-card"><div class="comparison-label">{t().refineTargetTitle}</div>
			<div class="comparison-art" style="aspect-ratio: {canvasAspectWidth} / {canvasAspectHeight}">
				{#if artworkUrl}<img class="canvas-art" src={artworkUrl} alt="" />{/if}
				{#if frame && row}<div class="thing-frame" style="left:{frame.left}%;top:{frame.top}%;width:{frame.width}%;height:{frame.height}%"><span>{row.number} {row.what}</span></div>{/if}
			</div>
			{#if targetComposition && targetComposition.state !== 'none'}
				<div class="target-now"><span class="target-now-label">{t().compositionTargetNow}</span><CompositionChips summary={targetComposition} {isJapanese} /></div>
			{/if}
		</div>
		<div class="refine-target-controls"><section class="refine-action-section">
			<div class="what-head">{t().placeThingsHead}</div>
			<div class="place-things" role="radiogroup" aria-label={t().placeThingsHead}>
				{#each rows as entry (entry.title)}
					<label class="place-thing" class:on={entry.title === chosen} class:held={!entry.movable}>
						<input type="radio" name="place-thing" value={entry.title} bind:group={chosen} disabled={busy || !entry.movable} />
						<span class="thing-no">{entry.number}</span>
						<span class="thing-role">{entry.role}</span>
						<span class="thing-main"><span class="thing-what">{entry.what}</span>
							<span class="thing-place">{entry.now ? t().placeNow(placeName(entry.now, isJapanese)) : ''}</span></span>
					</label>
				{/each}
			</div>
			<div class="what-head">{t().placePlacesHead}<span class="comp-hint">{t().placeHint}</span></div>
			<div class="pads">
				{#each [['golden', t().placePadGolden], ['third', t().placePadThirds], ['center', t().placePadCenter]] as [pad, name] (pad)}
					<div class="pad-wrap"><div class="pad {pad}">
						{#if pad === 'golden'}<i style="left:38.2%"></i><i style="left:61.8%"></i><b style="top:38.2%"></b><b style="top:61.8%"></b>{/if}
						{#each PLACES.filter((place) => place.pad === pad) as place (place.id)}
							<button type="button" class={place.x !== null && place.y !== null ? 'pad-point' : place.x !== null ? 'pad-line v' : 'pad-line h'}
								class:now={row?.now === place.id} class:done={drawn(place.id)} class:held={!!row && !movable(row.places[place.id])}
								style={place.x !== null && place.y !== null ? `left:${place.x * 100}%;top:${place.y * 100}%` : place.x !== null ? `left:${place.x * 100}%` : `top:${(place.y ?? 0) * 100}%`}
								title={title(place.id)} aria-label={title(place.id)} aria-disabled={!pressable(place.id)}
								onclick={() => press(place.id)}></button>
						{/each}
					</div><div class="pad-name">{name}</div></div>
				{/each}
			</div>
			{#if refused}<p class="place-refused">{refused}</p>{/if}
			<dl class="keeps"><dt>{t().compositionKeepsTerm}</dt><dd>{t().placeKeeps}</dd><dt>{t().placeChangesTerm}</dt><dd>{t().placeChanges}</dd></dl>
			{#if busy}<RunStatus label={t().refineGeneratingTask(refinementSession.gridTaskLabel)}
				progressDone={refinementSession.gridDone} progressTotal={refinementSession.gridTotal}
				elapsedMs={refinementSession.elapsedMs} progress={refinementSession.gridProgress}
				tokensIn={refinementSession.tokensIn} tokensOut={refinementSession.tokensOut}
				onStop={refinementSession.gridBusy && refinementSession.gridCanAbort ? () => refinementSession.abort() : null} />
				<VariationLanes states={refinementSession.gridSlots} labels={refinementSession.gridSlotLabels} />
			{/if}
		</section></div>
	</div>
	<RefinementCandidateGrid {isJapanese} {refinementSession} {onSaveAndClose} {onDiscardAndClose} maxColumns={3}
		target={{ artworkUrl, aspectWidth: canvasAspectWidth, aspectHeight: canvasAspectHeight, composition: null }} />
</div></div>

<style>
	.refine-stage.wide { grid-template-columns: 388px minmax(0, 1fr); }
	.refine-target-column.wide .refine-target-card { display: grid; grid-template-columns: 150px minmax(0, 1fr); gap: 4px 12px; }
	.refine-target-column.wide .refine-target-card > :global(.comparison-label) { grid-column: 1 / -1; margin: 0; }
	.refine-target-column.wide .target-now { margin-top: 0; align-content: start; }
	.thing-frame { position: absolute; border: 1.5px solid var(--accent); border-radius: 2px; box-shadow: 0 0 0 1px rgba(0,0,0,.55), inset 0 0 0 1px rgba(0,0,0,.35); pointer-events: none; }
	.thing-frame span { position: absolute; left: -1.5px; bottom: 100%; margin-bottom: 2px; padding: 1px 7px; border-radius: 3px; background: var(--accent); color: var(--accent-fg); font-size: var(--ui-font-size-11); white-space: nowrap; }
	.what-head { display: flex; align-items: baseline; gap: 10px; color: var(--fg); font-size: var(--ui-font-size-12); font-weight: 600; }
	.comp-hint { color: var(--fg3); font-size: var(--ui-font-size-11); font-weight: 400; opacity: .85; }
	.place-things { display: flex; flex-direction: column; gap: 2px; max-height: 210px; overflow: auto; }
	.place-thing { display: grid; grid-template-columns: auto 18px 2.6em minmax(0, 1fr); gap: 8px; align-items: center; padding: 5px 8px; border: 1px solid transparent; border-radius: var(--r); cursor: pointer; }
	.place-thing.on { border-color: var(--accent); background: var(--accent-light); }
	.place-thing.held { opacity: .5; cursor: default; }
	.place-thing input { accent-color: var(--accent); margin: 0; }
	.thing-no { display: grid; place-items: center; width: 16px; height: 16px; border: 1px solid var(--border2); border-radius: 50%; color: var(--fg2); font-size: 10px; line-height: 1; }
	.place-thing.on .thing-no { border-color: var(--accent); color: var(--accent); }
	.thing-role { color: var(--fg3); font-size: var(--ui-font-size-11); white-space: nowrap; }
	.thing-main { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 1px 10px; min-width: 0; }
	.thing-what { color: var(--fg); font-size: var(--ui-font-size-12); line-height: 1.55; }
	.thing-place { color: var(--fg3); font-size: var(--ui-font-size-11); white-space: nowrap; }
	.pads { display: flex; gap: 16px; align-items: flex-start; }
	.pad-wrap { display: flex; flex-direction: column; align-items: center; gap: 6px; }
	.pad { position: relative; width: 128px; height: 128px; border: 1px solid var(--border2); border-radius: 3px; background: var(--bg); }
	.pad.center { width: 64px; height: 64px; margin-top: 32px; }
	.pad i, .pad b { position: absolute; background: var(--border2); }
	.pad i { top: 0; bottom: 0; width: 1px; }
	.pad b { left: 0; right: 0; height: 1px; }
	.pad-point { position: absolute; width: 18px; height: 18px; margin: -9px 0 0 -9px; padding: 0; border: 1.5px solid var(--fg2); border-radius: 50%; background: var(--bg); cursor: pointer; }
	.pad-line { position: absolute; padding: 0; border: 1.5px solid var(--fg2); border-radius: 3px; background: var(--bg); cursor: pointer; }
	.pad-line.v { top: 6px; bottom: 6px; width: 7px; margin-left: -3.5px; }
	.pad-line.h { left: 6px; right: 6px; height: 7px; margin-top: -3.5px; }
	.pad-point:not([aria-disabled='true']):hover, .pad-line:not([aria-disabled='true']):hover { border-color: var(--accent); box-shadow: 0 0 0 3px color-mix(in srgb, var(--accent) 30%, transparent); }
	.pad-point.now, .pad-line.now { background: var(--fg3); border-color: var(--fg3); cursor: default; }
	.pad-point.done, .pad-line.done { background: var(--accent); border-color: var(--accent); cursor: default; }
	.pad-point.held:not(.now), .pad-line.held:not(.now) { opacity: .35; border-style: dashed; cursor: not-allowed; }
	.pad-point[aria-disabled='true'], .pad-line[aria-disabled='true'] { cursor: default; }
	.pad-name { color: var(--fg3); font-size: var(--ui-font-size-11); }
	.place-refused { margin: 0; color: var(--danger, var(--fg2)); font-size: var(--ui-font-size-12); }
	.keeps { display: grid; grid-template-columns: auto minmax(0, 1fr); gap: 3px 10px; margin: 2px 0 0; padding: 8px 10px; border: 1px solid var(--border); border-radius: var(--r); background: var(--panel2); font-size: var(--ui-font-size-12); line-height: 1.6; }
	.keeps dt { color: var(--fg3); white-space: nowrap; }
	.keeps dd { margin: 0; color: var(--fg2); }
</style>
