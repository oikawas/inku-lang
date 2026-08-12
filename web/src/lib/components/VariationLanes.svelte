<script lang="ts">
	/**
	 * The lanes of a fan-out, one per candidate.
	 *
	 * A run of four candidates is four requests in flight at once, but a single
	 * counter that moves only when a job lands draws that as nothing happening
	 * followed by everything arriving. Each lane carries its own mascot, so the
	 * work reads as the several jobs it is.
	 *
	 * The lanes wear the mascot the user did not choose: the run status directly
	 * above shows the chosen one, and the row beside it is a different thing --
	 * several jobs rather than the run as a whole -- so it should not read as
	 * more copies of that one indicator.
	 *
	 * A lane that has landed keeps its place and stops moving: the row is then a
	 * record of what is done and what is still out.
	 */
	import { untrack } from 'svelte';
	import IncuMascot from './IncuMascot.svelte';
	import YuragiMascot from './YuragiMascot.svelte';
	import { getMascot } from '$lib/mascot.svelte';

	type LaneState = 'waiting' | 'running' | 'done';

	type Props = {
		states: LaneState[];
		/** Same order as `states`. An empty string is a lane not yet named. */
		labels?: string[];
	};

	let { states, labels = [] }: Props = $props();

	// The phase offset is made by starting each mascot at a different moment
	// rather than by reaching into its animations: the two mascots hang their
	// motion on different elements, so a CSS delay written for one of them
	// leaves the other beating in unison. A mascot that is mounted late is
	// simply late, whatever it animates.
	//
	// Drawn rather than stepped -- an even step is itself a rhythm, and four
	// bodies moving one after another read as a queue rather than as four
	// workers. The row is mounted and unmounted with the run, so the offsets are
	// drawn once and held.
	const STAGGER_MS = 900;
	let started = $state<boolean[]>([]);
	// Read untracked, so this runs once for the row rather than on every lane
	// that lands: `states` is a fresh array each time one does, and re-running
	// would cancel the timers of the lanes that had not started yet.
	$effect(() => {
		const count = untrack(() => states.length);
		started = Array.from({ length: count }, () => false);
		const timers = Array.from({ length: count }, (_, index) => window.setTimeout(() => {
			started = started.map((value, i) => i === index ? true : value);
		}, Math.random() * STAGGER_MS));
		return () => timers.forEach((timer) => window.clearTimeout(timer));
	});
</script>

{#if states.length > 1}
	<div class="lanes" aria-live="polite">
		{#each states as state, index (index)}
			<div
				class="lane"
				class:waiting={state === 'waiting'}
				class:done={state === 'done'}
			>
				<div class="lane-mascot">
					{#if state === 'done'}
						<span class="lane-mark" aria-hidden="true">✓</span>
					{:else if state === 'waiting'}
						<!-- Present but not working: the row shows how many jobs the
						     fan-out is allowed to have in flight at once. -->
						<span class="lane-mark lane-idle" aria-hidden="true">·</span>
					{:else if started[index] ?? true}
						{#if getMascot() === 'yuragi'}<IncuMascot />{:else}<YuragiMascot />{/if}
					{/if}
				</div>
				<!-- The number, not the task name: four lanes have to fit across a
				     narrow panel, and the name is already on the status line above.
				     The full label stays reachable as the tooltip. -->
				<span class="lane-label" title={labels[index] || ''}>{index + 1}</span>
			</div>
		{/each}
	</div>
{/if}

<style>
	.lanes {
		/* Full width and a small minimum, so four lanes sit side by side in the
		   refine panel's narrow column rather than stacking into a list. */
		width: 100%;
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(48px, 1fr));
		gap: 6px;
		margin-top: 6px;
	}
	.lane {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 2px;
		min-width: 0;
		padding: 6px 4px;
		border: 1px solid var(--border2);
		border-radius: var(--r);
		background: var(--panel);
	}
	.lane.waiting {
		opacity: 0.45;
	}
	.lane-mascot {
		display: flex;
		align-items: center;
		justify-content: center;
		min-height: 34px;
	}
	.lane-mark {
		color: var(--accent);
		font-size: 18px;
		line-height: 1;
	}
	.lane-idle {
		color: var(--fg3);
	}
	.lane.done {
		border-color: var(--accent);
	}
	.lane-label {
		max-width: 100%;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
		color: var(--fg3);
		font-size: 11px;
	}
	.lane.done .lane-label {
		color: var(--fg2);
	}
</style>
