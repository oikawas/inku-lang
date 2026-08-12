<script lang="ts">
	/**
	 * The lanes of a fan-out, one per candidate.
	 *
	 * A run of four candidates is four requests in flight at once, but a single
	 * counter that moves only when a job lands draws that as nothing happening
	 * followed by everything arriving. Each lane carries its own mascot, so the
	 * work reads as the several jobs it is, and the mascots are put out of phase
	 * with each other so four lanes do not beat as one.
	 *
	 * A lane that has landed keeps its place and stops moving: the row is then a
	 * record of what is done and what is still out.
	 */
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
</script>

{#if states.length > 1}
	<div class="lanes" aria-live="polite">
		{#each states as state, index (index)}
			<div
				class="lane"
				class:waiting={state === 'waiting'}
				class:done={state === 'done'}
				style={`--lane-phase: -${(index * 0.9).toFixed(1)}s`}
			>
				<div class="lane-mascot">
					{#if state === 'done'}
						<span class="lane-mark" aria-hidden="true">✓</span>
					{:else if getMascot() === 'yuragi'}
						<YuragiMascot />
					{:else}
						<IncuMascot />
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
	/* The one place this component reaches into a mascot: both of them hang their
	   whole-body animation on .mascot-wrapper, and shifting that per lane is what
	   keeps the row from moving as a single body. */
	.lane :global(.mascot-wrapper) {
		animation-delay: var(--lane-phase);
	}
	/* A lane with no free slot yet is present but still, so the row shows how
	   many jobs the fan-out is allowed to run at once. */
	.lane.waiting {
		opacity: 0.45;
	}
	.lane.waiting :global(.mascot-wrapper),
	.lane.waiting :global(.pixel),
	.lane.waiting :global(.bubble) {
		animation-play-state: paused;
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
