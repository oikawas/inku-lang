<!--
	How the next description is drawn (2026-10-27, the author's plan C): the
	route as two buttons, the two steps a run can leave out as switches named
	the same on both routes, and under them the steps the run will pass. The
	stages always pass the composition and laws, so that switch shows on and
	locked there. In the describe tab's condition rows, which the batch shares.
-->
<script lang="ts">
	import { t } from '$lib/i18n/index.svelte';
	import Tooltip from './Tooltip.svelte';
	import SwitchChip from './SwitchChip.svelte';
	import {
		DRAW_ROUTES, compositionPassed, drawFlow, drawRouteLabel, drawSwitchLabel,
		type CompositionMode, type DrawRoute
	} from '$lib/draw-route';
	import type { SketchMode } from '$lib/sketch';

	type Props = {
		route: DrawRoute;
		sketchMode: SketchMode;
		compositionMode: CompositionMode;
		isJapanese: boolean;
		onSelectRoute: (route: DrawRoute) => void;
		onSelectSketchMode: (mode: SketchMode) => void;
		onSelectCompositionMode: (mode: CompositionMode) => void;
	};

	let { route, sketchMode, compositionMode, isJapanese, onSelectRoute, onSelectSketchMode, onSelectCompositionMode }: Props = $props();

	const sketchOn = $derived(sketchMode === 'on');
	const compositionOn = $derived(compositionPassed(route, compositionMode));
	const compositionLocked = $derived(route === 'stages');
	const flow = $derived(drawFlow(route, sketchMode, compositionMode, isJapanese));
</script>

<div class="draw-conditions">
	<span class="draw-label">{isJapanese ? '描き方' : 'Drawing'}</span>
	<Tooltip text={t().tooltipInputRoute}>
		<div class="route-segments" role="group" aria-label={isJapanese ? '描き方' : 'Drawing'}>
			{#each DRAW_ROUTES as option (option)}
				<button
					type="button"
					class:selected={option === route}
					aria-pressed={option === route}
					onclick={() => onSelectRoute(option)}
				>{drawRouteLabel(option, isJapanese)}</button>
			{/each}
		</div>
	</Tooltip>

	<span class="draw-label">{isJapanese ? '通す段' : 'Steps'}</span>
	<div class="draw-switches">
		<Tooltip text={t().tooltipInputSketch}>
			<SwitchChip label={drawSwitchLabel('sketch', isJapanese)} on={sketchOn}
				onToggle={() => onSelectSketchMode(sketchOn ? 'off' : 'on')} />
		</Tooltip>
		<Tooltip text={t().tooltipInputComposition}>
			<SwitchChip label={drawSwitchLabel('composition', isJapanese)} on={compositionOn} locked={compositionLocked}
				onToggle={() => onSelectCompositionMode(compositionMode === 'on' ? 'off' : 'on')} />
		</Tooltip>
	</div>

	<span class="draw-label flow-label">{isJapanese ? '流れ' : 'Flow'}</span>
	<ol class="draw-flow" aria-label={isJapanese ? '通る段' : 'Steps the run passes'}>
		{#each flow as step, index (index)}
			<li class="flow-{step.kind}">{step.label}</li>
		{/each}
	</ol>
</div>

<style>
	.draw-conditions {
		position: relative;
		display: grid;
		grid-template-columns: auto minmax(0, 1fr);
		align-items: center;
		gap: 8px 10px;
		min-width: 0;
	}
	/* Bubbles anchor to the whole block, as the compact rows' do, so a long
	   one stays inside the narrow input panel. */
	.draw-conditions :global(.tooltip-wrap) { position: static; min-width: 0; }
	.draw-label {
		color: var(--fg3);
		font-size: var(--ui-font-size-11);
		line-height: 1.35;
		white-space: nowrap;
	}
	.flow-label { align-self: start; padding-top: 1px; }
	.route-segments {
		display: flex;
		flex: 1;
		gap: 2px;
		min-width: 0;
		padding: 2px;
		border: 1px solid var(--border2);
		border-radius: 7px;
		background: var(--bg);
	}
	.route-segments button {
		flex: 1;
		min-width: 0;
		height: 26px;
		padding: 0 8px;
		border: 0;
		border-radius: 5px;
		background: transparent;
		color: var(--fg2);
		font-family: inherit;
		font-size: var(--ui-font-size-12);
		white-space: nowrap;
		cursor: pointer;
	}
	.route-segments button:hover:not(.selected) { color: var(--fg); }
	.route-segments button.selected {
		background: var(--bg3);
		color: var(--fg);
		font-weight: 600;
	}
	.draw-switches {
		display: flex;
		flex-wrap: wrap;
		gap: 6px;
		min-width: 0;
	}
	.route-segments button:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
	.draw-flow {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 2px 4px;
		min-width: 0;
		margin: 0;
		padding: 0;
		list-style: none;
		font-size: var(--ui-font-size-11);
		line-height: 1.6;
	}
	.draw-flow li + li::before {
		content: '›';
		margin-right: 4px;
		color: var(--fg3);
	}
	.flow-end { color: var(--fg3); }
	.flow-fixed { color: var(--fg); }
	.flow-switch { color: var(--accent); }
</style>
