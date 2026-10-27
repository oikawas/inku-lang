<!--
	A step or option that is on or off, shown as a chip that lights when on
	(2026-10-27, the author's plan C for the next work's conditions). Locked
	keeps it on without being disabled, so a surrounding tooltip still shows.
-->
<script lang="ts">
	type Props = {
		label: string;
		on: boolean;
		locked?: boolean;
		onToggle: () => void;
	};

	let { label, on, locked = false, onToggle }: Props = $props();
</script>

<button
	type="button"
	class="switch-chip"
	class:on
	class:locked
	aria-pressed={on}
	aria-disabled={locked}
	onclick={() => { if (!locked) onToggle(); }}
>
	<svg class="switch-mark" width="12" height="12" viewBox="0 0 12 12" aria-hidden="true">
		{#if locked}
			<rect x="2.5" y="5.5" width="7" height="5" rx="1" />
			<path d="M4 5.5 V4 a2 2 0 0 1 4 0 V5.5" />
		{:else if on}
			<path d="M2.5 6.2 L5 8.5 L9.5 3.5" />
		{:else}
			<circle cx="6" cy="6" r="4" />
		{/if}
	</svg>
	{label}
</button>

<style>
	.switch-chip {
		display: inline-flex;
		align-items: center;
		gap: 6px;
		height: 26px;
		padding: 0 11px 0 9px;
		border: 1px solid var(--border2);
		border-radius: 13px;
		background: transparent;
		color: var(--fg2);
		font-family: inherit;
		font-size: var(--ui-font-size-12);
		white-space: nowrap;
		cursor: pointer;
	}
	.switch-chip:hover:not(.locked) { background: var(--bg2); }
	.switch-chip.on {
		border-color: var(--accent);
		background: var(--accent-light);
		color: var(--fg);
	}
	.switch-chip.on:hover:not(.locked) { background: var(--accent-light); }
	.switch-chip.locked { cursor: default; }
	.switch-chip:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
	.switch-mark {
		flex: none;
		fill: none;
		stroke: var(--fg3);
		stroke-width: 1.4;
		stroke-linecap: round;
		stroke-linejoin: round;
	}
	.switch-chip.on .switch-mark { stroke: var(--accent); }
</style>
